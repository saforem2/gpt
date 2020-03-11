#
# GPT
#
# Authors: Christoph Lehner 2020
#
import gpt as g

def cg(mat,src,psi,tol,maxit,verbose=True):
    p,mmp,r=g.copy(src),g.copy(src),g.copy(src)
    guess=g.norm2(psi)
    mat(psi,mmp) # in, out
    d=g.innerProduct(psi,mmp).real
    b=g.norm2(mmp)
    g.eval(r,src - mmp)
    g.copy(p,r)
    a = g.norm2(p)
    cp = a
    ssq = g.norm2(src)
    rsq = tol * tol * ssq
    for k in range(1,maxit+1):
        c=cp
        mat(p, mmp)
        dc=g.innerProduct(p,mmp)
        d=dc.real
        a = c / d
        cp=g.axpy_norm(r, -a, mmp, r)
        b = cp / c
        g.eval(psi,a*p+psi)
        g.eval(p,b*p+r)
        # TODO: expose multiple simultaneous evals as g.eval([psi,p],[a*p+psi,b*p+r])
        if verbose:
            g.message("Iter %d -> %g" % (k,cp))
        if cp <= rsq:
            if verbose:
                g.message("Converged")
            break