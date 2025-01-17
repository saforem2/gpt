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
import gpt as g


def transformed(obj, V):
    if isinstance(obj, g.matrix_operator):

        M = obj

        def _mat(dst, src):
            dst @= V * M * g.adj(V) * src

        return g.matrix_operator(_mat, vector_space=M.vector_space)

    else:

        U = obj

        return [g(V * U[mu] * g.cshift(g.adj(V), mu, 1)) for mu in range(len(U))]
