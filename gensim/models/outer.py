#!/usr/bin/env python
# -*- coding: utf-8 -*-

%%cython
import cython
from cython cimport view
import numpy as np
cimport numpy as np

from cpython cimport PyCapsule_GetPointer # PyCObject_AsVoidPtr
from scipy.linalg.blas import fblas

REAL = np.float32
ctypedef np.float32_t REAL_t
 
cdef int ONE = 1
cdef REAL_t ONEF = <REAL_t>1.0
 
ctypedef void (*sger_ptr) (const int *M, const int *N, const float *alpha, const float *X, const int *incX, float *Y, const int *incY, float *A, const int * LDA) nogil
cdef sger_ptr sger=<sger_ptr>PyCapsule_GetPointer(fblas.sger._cpointer , NULL)  # A := alpha*x*y.T + A

cdef void outer_prod(REAL_t*  x, REAL_t* y, REAL_t * out, int x_len, int y_len):
    sger(&y_len, &x_len, &ONEF, y, &ONE, x, &ONE, out, &y_len)

def vector_outer_product(np.ndarray[REAL_t, ndim=2] _x, np.ndarray[REAL_t, ndim=2] _y):
    
    cdef int i, length = _x.shape[0], x_len = _x.shape[1], y_len = _y.shape[1]
    cdef int box_size = x_len * y_len
    cdef np.ndarray[REAL_t, ndim=3] result
    result = np.zeros([length, x_len, y_len], dtype = REAL)
    
    
    #cdef REAL_t* _result = <REAL_t *>(np.PyArray_DATA(result))
                                        
    cdef REAL_t*  x = <REAL_t *>(np.PyArray_DATA(_x))
    cdef REAL_t* y = <REAL_t *>(np.PyArray_DATA(_y))
    
    cdef REAL_t[:,:] x_view = _x
    cdef REAL_t[:,:] y_view = _y
    #cdef REAL_t[:,:,:] result_view = result
    
    
    for i in range(length):
        outer_prod(&x_view[i,0], &y_view[i,0], &result[i,0,0], x_len, y_len)
    
    return result.transpose((1,2,0))
    
def numpy_vector_outer_product(a,b):
    return np.dstack([np.outer(a[i,:], b[i,:]) for i in range(a.shape[0])])

a = np.random.randn(20,3).astype(np.float32)
b = np.random.randn(20,4).astype(np.float32)

np.allclose(vector_outer_product(a,b),numpy_vector_outer_product(a,b))
# => True

%timeit vector_outer_product(a, b)
# => 100000 loops, best of 3: 9.01 µs per loop

%timeit numpy_vector_outer_product(a,b)
# => 1000 loops, best of 3: 267 µs per loop