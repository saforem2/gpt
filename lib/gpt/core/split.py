#
#    GPT - Grid Python Toolkit
#    Copyright (C) 2020  Christoph Lehner (christoph.lehner@ur.de, https://github.com/lehner/gpt)
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
import gpt
import cgpt
import numpy
import sys


# Implement policies as classes, may want to add more variables/methods later
class split_group_policy:
    class together:
        pass

    class separate:
        pass


def split_lattices(lattices, lcoor, gcoor, split_grid, N, cache, group_policy):
    # Example:
    #
    # Original
    #
    # lattice1,...,latticen | lattice1,...,latticen
    #
    # New
    #
    # lattice1,...,latticeN | latticeN+1,...,lattice2N
    #
    # Q = n // N = 2

    # N is desired number of parallel split lattices per unsplit lattice
    # 1 <= N <= sranks, sranks % N == 0

    n = len(lattices)
    assert n > 0
    assert n % N == 0
    Q = n // N

    # Save memory by performing each group separately
    if N != 1 and group_policy == split_group_policy.separate:
        res = []
        for i in range(N):
            res += split_lattices(
                [lattices[q * N + i] for q in range(Q)],
                lcoor,
                gcoor,
                split_grid,
                1,
                cache,
                group_policy,
            )
        return res

    assert len(lcoor) == len(gcoor)
    grid = lattices[0].grid
    assert all([lattices[i].grid.obj == grid.obj for i in range(1, n)])
    cb = lattices[0].checkerboard()
    assert all([lattices[i].checkerboard() is cb for i in range(1, n)])
    otype = lattices[0].otype
    assert all([lattices[i].otype.__name__ == otype.__name__ for i in range(1, n)])

    l = [gpt.lattice(split_grid, otype) for i in range(N)]

    for x in l:
        x.checkerboard(cb)
        x.split_lcoor = lcoor
        x.split_gcoor = gcoor
    sranks = split_grid.sranks
    srank = split_grid.srank

    src_data = lattices
    dst_data = l

    # build views
    if cache is None:
        cache = {}

    cache_key = f"split_plan_{lattices[0].grid.obj}_{l[0].grid.obj}_{lattices[0].otype.__name__}_{l[0].otype.__name__}_{n}_{N}"
    if cache_key not in cache:
        plan = gpt.copy_plan(dst_data, src_data, embed_in_communicator=lattices[0].grid)
        i = srank // (sranks // Q)
        for x in lattices[i * N : (i + 1) * N]:
            plan.source += x.view[gcoor]
        for x in l:
            plan.destination += x.view[lcoor]
        cache[cache_key] = plan()

    cache[cache_key](dst_data, src_data)

    return l


def unsplit(first, second, cache=None, group_policy=split_group_policy.separate):
    if type(first) != list:
        return unsplit([first], [second])

    n = len(first)
    N = len(second)
    Q = n // N
    assert n % N == 0

    # Save memory by performing each group separately
    if N != 1 and group_policy == split_group_policy.separate:
        for i in range(N):
            unsplit([first[q * N + i] for q in range(Q)], [second[i]], cache, group_policy)
        return

    split_grid = second[0].grid
    sranks = split_grid.sranks
    srank = split_grid.srank

    lcoor = second[0].split_lcoor
    gcoor = second[0].split_gcoor

    src_data = second
    dst_data = first

    if cache is None:
        cache = {}

    cache_key = f"unsplit_plan_{first[0].grid.obj}_{second[0].grid.obj}_{first[0].otype.__name__}_{second[0].otype.__name__}_{n}_{N}"
    if cache_key not in cache:
        plan = gpt.copy_plan(dst_data, src_data, embed_in_communicator=first[0].grid)
        i = srank // (sranks // Q)
        for x in first[i * N : (i + 1) * N]:
            plan.destination += x.view[gcoor]
        for x in second:
            plan.source += x.view[lcoor]
        cache[cache_key] = plan()

    cache[cache_key](dst_data, src_data)


def split_by_rank(first, group_policy=split_group_policy.separate):
    if type(first) != list:
        return split_by_rank([first])[0]

    assert len(first) > 0

    # TODO: split types
    lattices = first
    grid = lattices[0].grid
    mpi_split = [1, 1, 1, 1]
    fdimensions = [grid.fdimensions[i] // grid.mpi[i] for i in range(grid.nd)]
    split_grid = grid.split(mpi_split, fdimensions)
    gcoor = gpt.coordinates(lattices[0])
    lcoor = gpt.coordinates((split_grid, lattices[0].checkerboard()))
    return split_lattices(lattices, lcoor, gcoor, split_grid, len(lattices), group_policy)


def split(first, split_grid, cache=None, group_policy=split_group_policy.separate):
    assert len(first) > 0
    lattices = first
    gcoor = gpt.coordinates((split_grid, lattices[0].checkerboard()))
    lcoor = gpt.coordinates((split_grid, lattices[0].checkerboard()))
    assert len(lattices) % split_grid.sranks == 0
    return split_lattices(
        lattices,
        lcoor,
        gcoor,
        split_grid,
        len(lattices) // split_grid.sranks,
        cache,
        group_policy,
    )


class split_map:
    def __init__(self, grid, functions, mpi_split):
        self.cache = {}
        self.grid = grid
        self.grid_split = grid.split(mpi_split, grid.fdimensions)
        self.functions = functions

    def __call__(self, outputs, inputs=None):

        call_one_argument = inputs is None
        if inputs is None:
            inputs = [[]] * len(outputs)

        # for now this only works if all fields live on same grid!
        assert all([o.grid is self.grid for ls in outputs + inputs for o in ls])
        srank = self.grid_split.srank
        sranks = self.grid_split.sranks
        n_jobs = len(outputs)

        cache = self.cache
        grid_split = self.grid_split
        functions = self.functions

        assert len(inputs) == n_jobs

        assert n_jobs % sranks == 0
        n_jobs_per_rank = n_jobs // sranks
        n_inputs_per_job = len(inputs[0])
        n_outputs_per_job = len(outputs[0])

        flat_inputs = [f for function_inputs in inputs for f in function_inputs]
        flat_outputs = [f for function_outputs in outputs for f in function_outputs]

        if len(flat_inputs) > 0:
            inputs_split = split(flat_inputs, grid_split, cache)
        else:
            inputs_split = []
        outputs_split = split(flat_outputs, grid_split, cache)

        results = numpy.zeros(shape=(n_jobs,), dtype=numpy.complex128)

        for i in range(n_jobs_per_rank):
            this_job_index = srank * n_jobs_per_rank + i
            this_job_inputs = [
                inputs_split[i * n_inputs_per_job + j] for j in range(n_inputs_per_job)
            ]
            this_job_outputs = [
                outputs_split[i * n_outputs_per_job + j] for j in range(n_outputs_per_job)
            ]

            if call_one_argument:
                r = functions[this_job_index](this_job_outputs)
            else:
                r = functions[this_job_index](this_job_outputs, this_job_inputs)
            if gpt.util.is_num(r) and grid_split.processor == 0:
                results[this_job_index] = r

        unsplit(flat_outputs, outputs_split, cache)

        self.grid.globalsum(results)

        return results
