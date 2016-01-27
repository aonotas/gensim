#!/usr/bin/env python
# -*- coding: utf-8 -*-

#!/usr/bin/env cython
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# coding: utf-8
#
# Copyright (C) 2013 Radim Rehurek <me@radimrehurek.com>
# Licensed under the GNU LGPL v2.1 - http://www.gnu.org/licenses/lgpl.html

import cython
import numpy as np
from numpy import zeros, float32 as REAL
cimport numpy as np

from libc.math cimport exp
from libc.math cimport sqrt, pow, isnan
from libc.string cimport memset, memcpy

# scipy <= 0.15
try:
     from scipy.linalg.blas import fblas
except ImportError:
     # in scipy > 0.15, fblas function has been removed
     import scipy.linalg.blas as fblas

from word2vec_inner cimport bisect_left, random_int32, \
     scopy, saxpy, sdot, dsdot, snrm2, sscal, \
     REAL_t, EXP_TABLE, \
     our_dot, our_saxpy, \
     our_dot_double, our_dot_float, our_dot_noblas, our_saxpy_noblas

from word2vec import FAST_VERSION

DEF MAX_DOCUMENT_LEN = 10000

cdef int ONE = 1
cdef REAL_t ONEF = <REAL_t>1.0
cdef REAL_t ONEFM = <REAL_t> -1.0
cdef REAL_t ZERO = <REAL_t>0.0

DEF EXP_TABLE_SIZE = 1000
DEF MAX_EXP = 6

cdef void fast_document_dbow_hs(
    const np.uint32_t *word_point, const np.uint8_t *word_code, const int codelen,
    REAL_t *context_vectors, REAL_t *syn1, const int size,
    const np.uint32_t context_index, const REAL_t alpha, REAL_t *work, int learn_context, int learn_hidden,
    REAL_t *context_locks, const REAL_t adam_lr, const REAL_t adam_beta1, const REAL_t adam_beta2, const REAL_t adam_eps, REAL_t *adam_m, REAL_t *adam_v, REAL_t *adam_m2, REAL_t *adam_v2, REAL_t *adam_grad, REAL_t *adam_grad_syn1, REAL_t *adam_grad_context, REAL_t *update_work) nogil:

    cdef long long a, b
    cdef long long row1 = context_index * size, row2
    cdef REAL_t f, g
    cdef np.uint32_t row_index
    cdef np.uint32_t row_index2
    # Adam
    cdef REAL_t adam_grad_base
    cdef REAL_t adam_grad_element
    cdef REAL_t update_element


    for i in range(size):
        our_saxpy(&ONE, &ZERO, &ZERO, &ONE, &adam_grad[i], &ONE)
        # our_saxpy(&ONE, &ZERO, &ZERO, &ONE, &update_work[i], &ONE)
        # our_saxpy(&ONE, &ZERO, &ZERO, &ONE, &adam_grad_syn1[i], &ONE)
        # our_saxpy(&ONE, &ZERO, &ZERO, &ONE, &adam_grad_context[i], &ONE)

    memset(work, 0, size * cython.sizeof(REAL_t))
    for b in range(codelen):
        row2 = word_point[b] * size
        f = our_dot(&size, &context_vectors[row1], &ONE, &syn1[row2], &ONE)
        if f <= -MAX_EXP or f >= MAX_EXP:
            continue
        f = EXP_TABLE[<int>((f + MAX_EXP) * (EXP_TABLE_SIZE / MAX_EXP / 2))]
        g = (1 - word_code[b] - f) * alpha


        # Adam
        adam_grad_base = -(1 - word_code[b] - f)
        # adam_grad_base = f - 1 + word_code[b] # comment out
        memset(adam_grad, 0, ONE * cython.sizeof(REAL_t) * size)
        # # memset(adam_grad_syn1, 0, ONE * cython.sizeof(REAL_t) * size)
        # # memset(adam_grad_context, 0, ONE * cython.sizeof(REAL_t) * size)
        our_saxpy(&size, &adam_grad_base, &syn1[row2], &ONE, adam_grad, &ONE) 
        # our_saxpy(&size, &g, &syn1[row2], &ONE, adam_grad, &ONE) 


        # AdaGrad
        for i in range(size):
            # h += grad * grad
            row_index = <np.uint32_t> i + row2
            update_element = <REAL_t> adam_grad[i] * adam_grad[i]
            if not isnan(update_element):
                our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_m[row_index], &ONE)
            
            # param.data -= self.lr * grad / (numpy.sqrt(h) + self.eps)
            update_element = <REAL_t> ((adam_lr * adam_grad[i]) / (sqrt(adam_m[row_index]) + adam_eps))
            if not isnan(update_element):
                our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &work[i], &ONE)

        # # Adam
        # for i in range(size):
        #     # m += (1 - self.beta1) * (grad - m)
        #     # self.m = self.beta1*self.m_old + (1 - self.beta1)*grad
        #     row_index = <np.uint32_t> i + row2
        #     # row_index = row_index + i
        #     update_element = <REAL_t> (ONEF - adam_beta1) * (adam_grad[i] - adam_m[row_index])
        #     if not isnan(update_element):
        #         # our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_grad_syn1[i], &ONE)
        #         our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_m[row_index], &ONE)
        #     # adam_grad_syn1[i] = update_element
        #     # v += (1 - self.beta2) * (grad * grad - v)
        #     update_element = <REAL_t> (ONEF - adam_beta2) * ((adam_grad[i] * adam_grad[i]) - adam_v[row_index])
        #     if not isnan(update_element):
        #         # our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_grad_context[i], &ONE)
        #         our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_v[row_index], &ONE)
        #     # adam_grad_context[i] = update_element
        # # our_saxpy(&size, &ONEF, adam_grad_syn1, &ONE, &adam_m[row2], &ONE)
        # # our_saxpy(&size, &ONEF, adam_grad_context, &ONE, &adam_v[row2], &ONE)

        # # Adam update
        # for i in range(size):
        #     # param.data -= self.lr * m / (numpy.sqrt(v) + self.eps)
        #     row_index = <np.uint32_t> i + row2
        #     # if isnan(adam_m[row_index]):
        #     #     adam_m[row_index] = <REAL_t> 0.0
        #     #     # continue
        #     # if isnan(adam_v[row_index]):
        #     #     adam_v[row_index] = <REAL_t> 0.0
        #     #     # continue
        #     update_element = <REAL_t> ((adam_lr * adam_m[row_index]) / (sqrt(adam_v[row_index]) + adam_eps))
        #     # update_element = <REAL_t> adam_grad_base * alpha * syn1[row_index]
        #     # update_element = <REAL_t> adam_grad[i] * alpha
        #     if isnan(update_element):
        #         # update_element = <REAL_t> 0.0
        #         # continue
        #         our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &work[i], &ONE)
        #     # print update_element
        #     # print adam_grad[i] * alpha
        #     # print ''
        #     # work[i] += -update_element
        #     # our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &work[i], &ONE) # Comment out
        #     # our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &work[i], &ONE)
        #     # print work[i]

        #     # work[i] += g * syn1[row2+i]
        #     # work[i] += adam_grad[i]


        # SGD
        # our_saxpy(&size, &g, &syn1[row2], &ONE, work, &ONE)
        if learn_hidden:
            # AdaGrad
            memset(adam_grad, 0, ONE * cython.sizeof(REAL_t) * size)
            our_saxpy(&size, &adam_grad_base, &context_vectors[row1], &ONE, adam_grad, &ONE)
            for i in range(size):
                # h += grad * grad
                row_index = <np.uint32_t> i + row2
                row_index2 = <np.uint32_t> i + row2
                update_element = <REAL_t> adam_grad[i] * adam_grad[i]
                if not isnan(update_element):
                    our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_m2[row_index], &ONE)
                
                # param.data -= self.lr * grad / (numpy.sqrt(h) + self.eps)
                update_element = <REAL_t> ((adam_lr * adam_grad[i]) / (sqrt(adam_m2[row_index]) + adam_eps))
                if not isnan(update_element):
                    our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &syn1[row_index2], &ONE)

            # # # Adam
            # memset(adam_grad, 0, ONE * cython.sizeof(REAL_t) * size)
            # # # memset(adam_grad_syn1, 0, ONE * cython.sizeof(REAL_t) * size)
            # # # memset(adam_grad_context, 0, ONE * cython.sizeof(REAL_t) * size)
            # # # memset(update_work, 0, ONE * cython.sizeof(REAL_t) * size)
            # our_saxpy(&size, &adam_grad_base, &context_vectors[row1], &ONE, adam_grad, &ONE)
            # # # our_saxpy(&size, &g, &context_vectors[row1], &ONE, adam_grad, &ONE)

            # for i in range(size):
            #     row_index = <np.uint32_t> i + row1
            #     # m += (1 - self.beta1) * (grad - m)
            #     update_element = <REAL_t> (ONEF - adam_beta1) * (adam_grad[i] - adam_m2[row_index])
            #     # our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_grad_syn1[i], &ONE)
            #     if not isnan(update_element):
            #         our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_m2[row_index], &ONE)
            #     # adam_grad_syn1[i] = update_element

            #     # v += (1 - self.beta2) * (grad * grad - v)
            #     update_element = <REAL_t> (ONEF - adam_beta2) * ((adam_grad[i] * adam_grad[i]) - adam_v2[row_index])
            #     # our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_grad_context[i], &ONE)
            #     if not isnan(update_element):
            #         our_saxpy(&ONE, &ONEF, &update_element, &ONE, &adam_v2[row_index], &ONE)
            #     # adam_grad_context[i] = update_element

            # # # our_saxpy(&size, &ONEF, adam_grad_syn1, &ONE, &adam_m2[row1], &ONE)
            # # # our_saxpy(&size, &ONEF, adam_grad_context, &ONE, &adam_v2[row1], &ONE)

            # for i in range(size):
            #     # # param.data -= self.lr * m / (numpy.sqrt(v) + self.eps)
            #     row_index = <np.uint32_t> i + row1
            #     row_index2 = <np.uint32_t> i + row2
            #     # if isnan(adam_m2[row_index]):
            #     #     adam_m2[row_index] = <REAL_t> 0.0
            #     # #     # continue
            #     # if isnan(adam_v2[row_index]):
            #     #     adam_v2[row_index] = <REAL_t> 0.0
            #     # #     # continue
            #     update_element = <REAL_t> ((adam_lr * adam_m2[row_index]) / (sqrt(adam_v2[row_index]) + adam_eps))
            #     # update_element = <REAL_t> adam_grad[i] * alpha
            #     # # CHECK TODO: -=じゃなくていいのか
            #     if not isnan(update_element):
            #         # update_element = <REAL_t> 0.0
            #         # continue
            #         our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &syn1[row_index2], &ONE)
            #     # print update_element
            #     # print adam_grad[i] * alpha
            #     # print ''
            #     # update_work[i] = -update_element
            #     # print update_element
            #     # our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &update_work[i], &ONE)
            #     # our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &syn1[row_index2], &ONE) # comment out
            #     # our_saxpy(&ONE, &ONEFM, &update_element, &ONE, &syn1[row_index2], &ONE)
            #     # our_saxpy(&ONE, &update_element, &ONEF, &ONE, &update_work[i], &ONE)

            #     # update_element = <REAL_t> g * context_vectors[row1+i]
            #     # update_element = <REAL_t> adam_grad[i]
            #     # our_saxpy(&ONE, &ONEF, &update_element, &ONE, &update_work[i], &ONE)

            # # our_saxpy(&size, &ONEF, update_work, &ONE, &syn1[row2], &ONE)




            # SGD
            # our_saxpy(&size, &g, &context_vectors[row1], &ONE, &syn1[row2], &ONE)
    if learn_context:
        our_saxpy(&size, &context_locks[context_index], work, &ONE, &context_vectors[row1], &ONE)


cdef unsigned long long fast_document_dbow_neg(
    const int negative, np.uint32_t *cum_table, unsigned long long cum_table_len,
    REAL_t *context_vectors, REAL_t *syn1neg, const int size, const np.uint32_t word_index,
    const np.uint32_t context_index, const REAL_t alpha, REAL_t *work,
    unsigned long long next_random, int learn_context, int learn_hidden, REAL_t *context_locks) nogil:

    cdef long long a
    cdef long long row1 = context_index * size, row2
    cdef unsigned long long modulo = 281474976710655ULL
    cdef REAL_t f, g, label
    cdef np.uint32_t target_index
    cdef int d

    memset(work, 0, size * cython.sizeof(REAL_t))

    for d in range(negative+1):
        if d == 0:
            target_index = word_index
            label = ONEF
        else:
            target_index = bisect_left(cum_table, (next_random >> 16) % cum_table[cum_table_len-1], 0, cum_table_len)
            next_random = (next_random * <unsigned long long>25214903917ULL + 11) & modulo
            if target_index == word_index:
                continue
            label = <REAL_t>0.0
        row2 = target_index * size
        f = our_dot(&size, &context_vectors[row1], &ONE, &syn1neg[row2], &ONE)
        if f <= -MAX_EXP or f >= MAX_EXP:
            continue
        f = EXP_TABLE[<int>((f + MAX_EXP) * (EXP_TABLE_SIZE / MAX_EXP / 2))]
        g = (label - f) * alpha
        our_saxpy(&size, &g, &syn1neg[row2], &ONE, work, &ONE)
        if learn_hidden:
            our_saxpy(&size, &g, &context_vectors[row1], &ONE, &syn1neg[row2], &ONE)
    if learn_context:
        our_saxpy(&size, &context_locks[context_index], work, &ONE, &context_vectors[row1], &ONE)

    return next_random


cdef void fast_document_dm_hs(
    const np.uint32_t *word_point, const np.uint8_t *word_code, int word_code_len,
    REAL_t *neu1, REAL_t *syn1, const REAL_t alpha, REAL_t *work,
    const int size, int learn_hidden) nogil:

    cdef long long b
    cdef long long row2
    cdef REAL_t f, g

    # l1 already composed by caller, passed in as neu1
    # work (also passed in)  will accumulate l1 error
    for b in range(word_code_len):
        row2 = word_point[b] * size
        f = our_dot(&size, neu1, &ONE, &syn1[row2], &ONE)
        if f <= -MAX_EXP or f >= MAX_EXP:
            continue
        f = EXP_TABLE[<int>((f + MAX_EXP) * (EXP_TABLE_SIZE / MAX_EXP / 2))]
        g = (1 - word_code[b] - f) * alpha
        our_saxpy(&size, &g, &syn1[row2], &ONE, work, &ONE)
        if learn_hidden:
            our_saxpy(&size, &g, neu1, &ONE, &syn1[row2], &ONE)


cdef unsigned long long fast_document_dm_neg(
    const int negative, np.uint32_t *cum_table, unsigned long long cum_table_len, unsigned long long next_random,
    REAL_t *neu1, REAL_t *syn1neg, const int predict_word_index, const REAL_t alpha, REAL_t *work,
    const int size, int learn_hidden) nogil:

    cdef long long row2
    cdef unsigned long long modulo = 281474976710655ULL
    cdef REAL_t f, g, label
    cdef np.uint32_t target_index
    cdef int d

    # l1 already composed by caller, passed in as neu1
    # work (also passsed in) will accumulate l1 error for outside application
    for d in range(negative+1):
        if d == 0:
            target_index = predict_word_index
            label = ONEF
        else:
            target_index = bisect_left(cum_table, (next_random >> 16) % cum_table[cum_table_len-1], 0, cum_table_len)
            next_random = (next_random * <unsigned long long>25214903917ULL + 11) & modulo
            if target_index == predict_word_index:
                continue
            label = <REAL_t>0.0

        row2 = target_index * size
        f = our_dot(&size, neu1, &ONE, &syn1neg[row2], &ONE)
        if f <= -MAX_EXP or f >= MAX_EXP:
            continue
        f = EXP_TABLE[<int>((f + MAX_EXP) * (EXP_TABLE_SIZE / MAX_EXP / 2))]
        g = (label - f) * alpha
        our_saxpy(&size, &g, &syn1neg[row2], &ONE, work, &ONE)
        if learn_hidden:
            our_saxpy(&size, &g, neu1, &ONE, &syn1neg[row2], &ONE)

    return next_random

cdef void fast_document_dmc_hs(
    const np.uint32_t *word_point, const np.uint8_t *word_code, int word_code_len,
    REAL_t *neu1, REAL_t *syn1, const REAL_t alpha, REAL_t *work,
    const int layer1_size, const int vector_size, int learn_hidden) nogil:

    cdef long long a, b
    cdef long long row2
    cdef REAL_t f, g
    cdef int m

    # l1 already composed by caller, passed in as neu1
    # work accumulates net l1 error; eventually applied by caller
    for b in range(word_code_len):
        row2 = word_point[b] * layer1_size
        f = our_dot(&layer1_size, neu1, &ONE, &syn1[row2], &ONE)
        if f <= -MAX_EXP or f >= MAX_EXP:
            continue
        f = EXP_TABLE[<int>((f + MAX_EXP) * (EXP_TABLE_SIZE / MAX_EXP / 2))]
        g = (1 - word_code[b] - f) * alpha
        our_saxpy(&layer1_size, &g, &syn1[row2], &ONE, work, &ONE)
        if learn_hidden:
            our_saxpy(&layer1_size, &g, neu1, &ONE, &syn1[row2], &ONE)


cdef unsigned long long fast_document_dmc_neg(
    const int negative, np.uint32_t *cum_table, unsigned long long cum_table_len, unsigned long long next_random,
    REAL_t *neu1, REAL_t *syn1neg, const int predict_word_index, const REAL_t alpha, REAL_t *work,
    const int layer1_size, const int vector_size, int learn_hidden) nogil:

    cdef long long a
    cdef long long row2
    cdef unsigned long long modulo = 281474976710655ULL
    cdef REAL_t f, g, label
    cdef np.uint32_t target_index
    cdef int d, m

    # l1 already composed by caller, passed in as neu1
    # work accumulates net l1 error; eventually applied by caller
    for d in range(negative+1):
        if d == 0:
            target_index = predict_word_index
            label = ONEF
        else:
            target_index = bisect_left(cum_table, (next_random >> 16) % cum_table[cum_table_len-1], 0, cum_table_len)
            next_random = (next_random * <unsigned long long>25214903917ULL + 11) & modulo
            if target_index == predict_word_index:
                continue
            label = <REAL_t>0.0

        row2 = target_index * layer1_size
        f = our_dot(&layer1_size, neu1, &ONE, &syn1neg[row2], &ONE)
        if f <= -MAX_EXP or f >= MAX_EXP:
            continue
        f = EXP_TABLE[<int>((f + MAX_EXP) * (EXP_TABLE_SIZE / MAX_EXP / 2))]
        g = (label - f) * alpha
        our_saxpy(&layer1_size, &g, &syn1neg[row2], &ONE, work, &ONE)
        if learn_hidden:
            our_saxpy(&layer1_size, &g, neu1, &ONE, &syn1neg[row2], &ONE)

    return next_random


def train_document_dbow(model, doc_words, doctag_indexes, alpha, work=None,
                        train_words=False, learn_doctags=True, learn_words=True, learn_hidden=True,
                        word_vectors=None, word_locks=None, doctag_vectors=None, doctag_locks=None):
    cdef int hs = model.hs
    cdef int negative = model.negative
    cdef int sample = (model.sample != 0)
    cdef int _train_words = train_words
    cdef int _learn_words = learn_words
    cdef int _learn_hidden = learn_hidden
    cdef int _learn_doctags = learn_doctags

    cdef REAL_t *_word_vectors
    cdef REAL_t *_doctag_vectors
    cdef REAL_t *_word_locks
    cdef REAL_t *_doctag_locks
    cdef REAL_t *_work
    cdef REAL_t _alpha = alpha
    cdef int size = model.layer1_size

    cdef int codelens[MAX_DOCUMENT_LEN]
    cdef np.uint32_t indexes[MAX_DOCUMENT_LEN]
    cdef np.uint32_t _doctag_indexes[MAX_DOCUMENT_LEN]
    cdef np.uint32_t reduced_windows[MAX_DOCUMENT_LEN]
    cdef np.uint32_t reduced_windows_r[MAX_DOCUMENT_LEN]
    cdef int document_len
    cdef int doctag_len
    cdef int window = model.window
    cdef int window_r = model.window_r

    cdef int i, j
    cdef unsigned long long r
    cdef long result = 0

    # For hierarchical softmax
    cdef REAL_t *syn1
    cdef np.uint32_t *points[MAX_DOCUMENT_LEN]
    cdef np.uint8_t *codes[MAX_DOCUMENT_LEN]

    # For negative sampling
    cdef REAL_t *syn1neg
    cdef np.uint32_t *cum_table
    cdef unsigned long long cum_table_len
    cdef unsigned long long next_random

    # Adam
    cdef REAL_t adam_t  = model.adam_t
    cdef REAL_t adam_alpha_init  = model.adam_alpha_init
    cdef REAL_t adam_fix1 = ONEF - (model.adam_beta1 ** model.adam_t)
    cdef REAL_t adam_fix2 = ONEF - (model.adam_beta2 ** model.adam_t)
    # cdef REAL_t adam_lr = adam_alpha_init * sqrt(adam_fix2) / adam_fix1
    cdef REAL_t adam_lr = adam_alpha_init
    cdef REAL_t adam_beta1 = model.adam_beta1
    cdef REAL_t adam_beta2 = model.adam_beta2
    cdef REAL_t adam_eps = model.adam_eps
    # model.alpha = adam_lr
    cdef REAL_t *adam_m
    cdef REAL_t *adam_v
    cdef REAL_t *adam_m2
    cdef REAL_t *adam_v2
    

    cdef REAL_t *adam_word_m
    cdef REAL_t *adam_word_v
    cdef REAL_t *adam_doc_m
    cdef REAL_t *adam_doc_v
    cdef REAL_t *adam_syn1_m
    cdef REAL_t *adam_syn1_v
    cdef REAL_t *adam_syn1neg_m
    cdef REAL_t *adam_syn1neg_v

    adam_word_m = <REAL_t *>(np.PyArray_DATA(model.adam_word_m))
    adam_word_v = <REAL_t *>(np.PyArray_DATA(model.adam_word_v))
    adam_doc_m = <REAL_t *>(np.PyArray_DATA(model.adam_doc_m))
    adam_doc_v = <REAL_t *>(np.PyArray_DATA(model.adam_doc_v))

    cdef REAL_t *adam_grad
    cdef REAL_t *adam_grad_syn1
    cdef REAL_t *adam_grad_context
    cdef REAL_t *update_work
    adam_grad = <REAL_t *>np.PyArray_DATA(zeros(model.layer1_size, dtype=REAL))
    adam_grad_syn1 = <REAL_t *>np.PyArray_DATA(zeros(model.layer1_size, dtype=REAL))
    adam_grad_context = <REAL_t *>np.PyArray_DATA(zeros(model.layer1_size, dtype=REAL))
    update_work = <REAL_t *>np.PyArray_DATA(zeros(model.layer1_size, dtype=REAL))

    # print 'adam_lr:', adam_lr
    # print 'adam_m :', model.adam_m, model.adam_m2
    # print 'adam_v :', model.adam_v, model.adam_v2

    # default vectors, locks from syn0/doctag_syn0
    if word_vectors is None:
       word_vectors = model.syn0
    _word_vectors = <REAL_t *>(np.PyArray_DATA(word_vectors))
    if doctag_vectors is None:
       doctag_vectors = model.docvecs.doctag_syn0
    _doctag_vectors = <REAL_t *>(np.PyArray_DATA(doctag_vectors))
    if word_locks is None:
       word_locks = model.syn0_lockf
    _word_locks = <REAL_t *>(np.PyArray_DATA(word_locks))
    if doctag_locks is None:
       doctag_locks = model.docvecs.doctag_syn0_lockf
    _doctag_locks = <REAL_t *>(np.PyArray_DATA(doctag_locks))

    if hs:
        syn1 = <REAL_t *>(np.PyArray_DATA(model.syn1))
        adam_syn1_m = <REAL_t *>(np.PyArray_DATA(model.adam_syn1_m))
        adam_syn1_v = <REAL_t *>(np.PyArray_DATA(model.adam_syn1_v))

    if negative:
        syn1neg = <REAL_t *>(np.PyArray_DATA(model.syn1neg))
        cum_table = <np.uint32_t *>(np.PyArray_DATA(model.cum_table))
        cum_table_len = len(model.cum_table)
        
        adam_syn1neg_m = <REAL_t *>(np.PyArray_DATA(model.adam_syn1neg_m))
        adam_syn1neg_v = <REAL_t *>(np.PyArray_DATA(model.adam_syn1neg_v))

    if negative or sample:
        next_random = (2**24) * model.random.randint(0, 2**24) + model.random.randint(0, 2**24)

    # convert Python structures to primitive types, so we can release the GIL
    if work is None:
       work = zeros(model.layer1_size, dtype=REAL)
    _work = <REAL_t *>np.PyArray_DATA(work)



    vlookup = model.vocab
    i = 0
    for token in doc_words:
        predict_word = vlookup[token] if token in vlookup else None
        if predict_word is None:  # shrink document to leave out word
            continue  # leaving i unchanged
        if sample and predict_word.sample_int < random_int32(&next_random):
            continue
        indexes[i] = predict_word.index
        if hs:
            codelens[i] = <int>len(predict_word.code)
            codes[i] = <np.uint8_t *>np.PyArray_DATA(predict_word.code)
            points[i] = <np.uint32_t *>np.PyArray_DATA(predict_word.point)
        result += 1
        i += 1
        if i == MAX_DOCUMENT_LEN:
            break  # TODO: log warning, tally overflow?
    document_len = i

    if _train_words:
        # single randint() call avoids a big thread-synchronization slowdown

        if window == 0:
            for i, item in enumerate(range(document_len)):
                reduced_windows[i] = 0
        else:
            for i, item in enumerate(model.random.randint(0, window, document_len)):
                reduced_windows[i] = item

        if window_r == 0:
            for i, item in enumerate(range(document_len)):
                reduced_windows_r[i] = 0
        else:  
            for i, item in enumerate(model.random.randint(0, window_r, document_len)):
                reduced_windows_r[i] = item

        

    doctag_len = <int>min(MAX_DOCUMENT_LEN, len(doctag_indexes))
    for i in range(doctag_len):
        _doctag_indexes[i] = doctag_indexes[i]
        result += 1

    # release GIL & train on the document
    with nogil:
        for i in range(document_len):
            if _train_words:  # simultaneous skip-gram wordvec-training
                j = i - window + reduced_windows[i]
                if j < 0:
                    j = 0
                k = i + window_r + 1 - reduced_windows_r[i]
                if k > document_len:
                    k = document_len
                for j in range(j, k):
                    if j == i:
                        continue
                    if hs:
                        # we reuse the DBOW function, as it is equivalent to skip-gram for this purpose
                        fast_document_dbow_hs(points[i], codes[i], codelens[i], _word_vectors, syn1, size, indexes[j],
                                              _alpha, _work, _learn_words, _learn_hidden, _word_locks, adam_lr, adam_beta1, adam_beta2, adam_eps, adam_word_m, adam_word_v, adam_syn1_m, adam_syn1_v, adam_grad, adam_grad_syn1, adam_grad_context, update_work)
                    if negative:
                        # we reuse the DBOW function, as it is equivalent to skip-gram for this purpose
                        next_random = fast_document_dbow_neg(negative, cum_table, cum_table_len, _word_vectors, syn1neg, size,
                                                             indexes[i], indexes[j], _alpha, _work, next_random,
                                                             _learn_words, _learn_hidden, _word_locks)

            # docvec-training
            for j in range(doctag_len):
                if hs:
                    fast_document_dbow_hs(points[i], codes[i], codelens[i], _doctag_vectors, syn1, size, _doctag_indexes[j],
                                          _alpha, _work, _learn_doctags, _learn_hidden, _doctag_locks, adam_lr, adam_beta1, adam_beta2, adam_eps, adam_doc_m, adam_doc_v, adam_syn1_m, adam_syn1_v, adam_grad, adam_grad_syn1, adam_grad_context, update_work)
                if negative:
                    next_random = fast_document_dbow_neg(negative, cum_table, cum_table_len, _doctag_vectors, syn1neg, size,
                                                             indexes[i], _doctag_indexes[j], _alpha, _work, next_random,
                                                             _learn_doctags, _learn_hidden, _doctag_locks)

    return result


def train_document_dm(model, doc_words, doctag_indexes, alpha, work=None, neu1=None,
                      learn_doctags=True, learn_words=True, learn_hidden=True,
                      word_vectors=None, word_locks=None, doctag_vectors=None, doctag_locks=None):
    cdef int hs = model.hs
    cdef int negative = model.negative
    cdef int sample = (model.sample != 0)
    cdef int _learn_doctags = learn_doctags
    cdef int _learn_words = learn_words
    cdef int _learn_hidden = learn_hidden
    cdef int cbow_mean = model.cbow_mean
    cdef REAL_t count, inv_count = 1.0

    cdef REAL_t *_word_vectors
    cdef REAL_t *_doctag_vectors
    cdef REAL_t *_word_locks
    cdef REAL_t *_doctag_locks
    cdef REAL_t *_work
    cdef REAL_t *_neu1
    cdef REAL_t _alpha = alpha
    cdef int size = model.layer1_size

    cdef int codelens[MAX_DOCUMENT_LEN]
    cdef np.uint32_t indexes[MAX_DOCUMENT_LEN]
    cdef np.uint32_t _doctag_indexes[MAX_DOCUMENT_LEN]
    cdef np.uint32_t reduced_windows[MAX_DOCUMENT_LEN]
    cdef np.uint32_t reduced_windows_r[MAX_DOCUMENT_LEN]
    cdef int document_len
    cdef int doctag_len
    cdef int window = model.window
    cdef int window_r = model.window_r

    cdef int i, j, k, m
    cdef long result = 0

    # For hierarchical softmax
    cdef REAL_t *syn1
    cdef np.uint32_t *points[MAX_DOCUMENT_LEN]
    cdef np.uint8_t *codes[MAX_DOCUMENT_LEN]

    # For negative sampling
    cdef REAL_t *syn1neg
    cdef np.uint32_t *cum_table
    cdef unsigned long long cum_table_len
    cdef unsigned long long next_random

    # default vectors, locks from syn0/doctag_syn0
    if word_vectors is None:
       word_vectors = model.syn0
    _word_vectors = <REAL_t *>(np.PyArray_DATA(word_vectors))
    if doctag_vectors is None:
       doctag_vectors = model.docvecs.doctag_syn0
    _doctag_vectors = <REAL_t *>(np.PyArray_DATA(doctag_vectors))
    if word_locks is None:
       word_locks = model.syn0_lockf
    _word_locks = <REAL_t *>(np.PyArray_DATA(word_locks))
    if doctag_locks is None:
       doctag_locks = model.docvecs.doctag_syn0_lockf
    _doctag_locks = <REAL_t *>(np.PyArray_DATA(doctag_locks))

    if hs:
        syn1 = <REAL_t *>(np.PyArray_DATA(model.syn1))

    if negative:
        syn1neg = <REAL_t *>(np.PyArray_DATA(model.syn1neg))
        cum_table = <np.uint32_t *>(np.PyArray_DATA(model.cum_table))
        cum_table_len = len(model.cum_table)
    if negative or sample:
        next_random = (2**24) * model.random.randint(0, 2**24) + model.random.randint(0, 2**24)

    # convert Python structures to primitive types, so we can release the GIL
    if work is None:
       work = zeros(model.layer1_size, dtype=REAL)
    _work = <REAL_t *>np.PyArray_DATA(work)
    if neu1 is None:
       neu1 = zeros(model.layer1_size, dtype=REAL)
    _neu1 = <REAL_t *>np.PyArray_DATA(neu1)

    vlookup = model.vocab
    i = 0
    for token in doc_words:
        predict_word = vlookup[token] if token in vlookup else None
        if predict_word is None:  # shrink document to leave out word
            continue  # leaving i unchanged
        if sample and predict_word.sample_int < random_int32(&next_random):
            continue
        indexes[i] = predict_word.index
        if hs:
            codelens[i] = <int>len(predict_word.code)
            codes[i] = <np.uint8_t *>np.PyArray_DATA(predict_word.code)
            points[i] = <np.uint32_t *>np.PyArray_DATA(predict_word.point)
        result += 1
        i += 1
        if i == MAX_DOCUMENT_LEN:
            break  # TODO: log warning, tally overflow?
    document_len = i

    # single randint() call avoids a big thread-sync slowdown
    if window == 0:
        for i, item in enumerate(range(document_len)):
            reduced_windows[i] = 0
    else:
        for i, item in enumerate(model.random.randint(0, window, document_len)):
            reduced_windows[i] = item

    if window_r == 0:
        for i, item in enumerate(range(document_len)):
            reduced_windows_r[i] = 0
    else:  
        for i, item in enumerate(model.random.randint(0, window_r, document_len)):
            reduced_windows_r[i] = item

    doctag_len = <int>min(MAX_DOCUMENT_LEN, len(doctag_indexes))
    for i in range(doctag_len):
        _doctag_indexes[i] = doctag_indexes[i]
        result += 1

    # release GIL & train on the document
    with nogil:
        for i in range(document_len):
            j = i - window + reduced_windows[i]
            if j < 0:
                j = 0
            k = i + window_r + 1 - reduced_windows_r[i]
            if k > document_len:
                k = document_len

            # compose l1 (in _neu1) & clear _work
            memset(_neu1, 0, size * cython.sizeof(REAL_t))
            count = <REAL_t>0.0
            for m in range(j, k):
                if m == i:
                    continue
                else:
                    count += ONEF
                    our_saxpy(&size, &ONEF, &_word_vectors[indexes[m] * size], &ONE, _neu1, &ONE)
            for m in range(doctag_len):
                count += ONEF
                our_saxpy(&size, &ONEF, &_doctag_vectors[_doctag_indexes[m] * size], &ONE, _neu1, &ONE)
            if count > (<REAL_t>0.5):
                inv_count = ONEF/count
            if cbow_mean:
                sscal(&size, &inv_count, _neu1, &ONE)  # (does this need BLAS-variants like saxpy?)
            memset(_work, 0, size * cython.sizeof(REAL_t))  # work to accumulate l1 error
            if hs:
                fast_document_dm_hs(points[i], codes[i], codelens[i],
                                    _neu1, syn1, _alpha, _work,
                                    size, _learn_hidden)
            if negative:
                next_random = fast_document_dm_neg(negative, cum_table, cum_table_len, next_random,
                                                   _neu1, syn1neg, indexes[i], _alpha, _work,
                                                   size, _learn_hidden)

            if not cbow_mean:
                sscal(&size, &inv_count, _work, &ONE)  # (does this need BLAS-variants like saxpy?)
            # apply accumulated error in work
            if _learn_doctags:
                for m in range(doctag_len):
                    our_saxpy(&size, &_doctag_locks[_doctag_indexes[m]], _work,
                              &ONE, &_doctag_vectors[_doctag_indexes[m] * size], &ONE)
            if _learn_words:
                for m in range(j, k):
                    if m == i:
                        continue
                    else:
                         our_saxpy(&size, &_word_locks[indexes[m]], _work, &ONE,
                                   &_word_vectors[indexes[m] * size], &ONE)

    return result


def train_document_dm_concat(model, doc_words, doctag_indexes, alpha, work=None, neu1=None,
                             learn_doctags=True, learn_words=True, learn_hidden=True,
                             word_vectors=None, word_locks=None, doctag_vectors=None, doctag_locks=None):
    cdef int hs = model.hs
    cdef int negative = model.negative
    cdef int sample = (model.sample != 0)
    cdef int _learn_doctags = learn_doctags
    cdef int _learn_words = learn_words
    cdef int _learn_hidden = learn_hidden

    cdef REAL_t *_word_vectors
    cdef REAL_t *_doctag_vectors
    cdef REAL_t *_word_locks
    cdef REAL_t *_doctag_locks
    cdef REAL_t *_work
    cdef REAL_t *_neu1
    cdef REAL_t _alpha = alpha
    cdef int layer1_size = model.layer1_size
    cdef int vector_size = model.vector_size

    cdef int codelens[MAX_DOCUMENT_LEN]
    cdef np.uint32_t indexes[MAX_DOCUMENT_LEN]
    cdef np.uint32_t _doctag_indexes[MAX_DOCUMENT_LEN]
    cdef np.uint32_t window_indexes[MAX_DOCUMENT_LEN]
    cdef int document_len
    cdef int doctag_len
    cdef int window = model.window
    cdef int window_r = model.window_r
    cdef int expected_doctag_len = model.dm_tag_count

    cdef int i, j, k, m, n
    cdef long result = 0
    cdef int null_word_index = model.vocab['\0'].index

    # For hierarchical softmax
    cdef REAL_t *syn1
    cdef np.uint32_t *points[MAX_DOCUMENT_LEN]
    cdef np.uint8_t *codes[MAX_DOCUMENT_LEN]

    # For negative sampling
    cdef REAL_t *syn1neg
    cdef np.uint32_t *cum_table
    cdef unsigned long long cum_table_len
    cdef unsigned long long next_random

    doctag_len = <int>min(MAX_DOCUMENT_LEN, len(doctag_indexes))
    if doctag_len != expected_doctag_len:
        return 0  # skip doc without expected number of tags

    # default vectors, locks from syn0/doctag_syn0
    if word_vectors is None:
       word_vectors = model.syn0
    _word_vectors = <REAL_t *>(np.PyArray_DATA(word_vectors))
    if doctag_vectors is None:
       doctag_vectors = model.docvecs.doctag_syn0
    _doctag_vectors = <REAL_t *>(np.PyArray_DATA(doctag_vectors))
    if word_locks is None:
       word_locks = model.syn0_lockf
    _word_locks = <REAL_t *>(np.PyArray_DATA(word_locks))
    if doctag_locks is None:
       doctag_locks = model.docvecs.doctag_syn0_lockf
    _doctag_locks = <REAL_t *>(np.PyArray_DATA(doctag_locks))

    if hs:
        syn1 = <REAL_t *>(np.PyArray_DATA(model.syn1))

    if negative:
        syn1neg = <REAL_t *>(np.PyArray_DATA(model.syn1neg))
        cum_table = <np.uint32_t *>(np.PyArray_DATA(model.cum_table))
        cum_table_len = len(model.cum_table)
    if negative or sample:
        next_random = (2**24) * model.random.randint(0, 2**24) + model.random.randint(0, 2**24)

    # convert Python structures to primitive types, so we can release the GIL
    if work is None:
       work = zeros(model.layer1_size, dtype=REAL)
    _work = <REAL_t *>np.PyArray_DATA(work)
    if neu1 is None:
       neu1 = zeros(model.layer1_size, dtype=REAL)
    _neu1 = <REAL_t *>np.PyArray_DATA(neu1)

    vlookup = model.vocab
    i = 0
    for token in doc_words:
        predict_word = vlookup[token] if token in vlookup else None
        if predict_word is None:  # shrink document to leave out word
            continue  # leaving i unchanged
        if sample and predict_word.sample_int < random_int32(&next_random):
            continue
        indexes[i] = predict_word.index
        if hs:
            codelens[i] = <int>len(predict_word.code)
            codes[i] = <np.uint8_t *>np.PyArray_DATA(predict_word.code)
            points[i] = <np.uint32_t *>np.PyArray_DATA(predict_word.point)
        result += 1
        i += 1
        if i == MAX_DOCUMENT_LEN:
            break  # TODO: log warning, tally overflow?
    document_len = i

    for i in range(doctag_len):
        _doctag_indexes[i] = doctag_indexes[i]
        result += 1

    # release GIL & train on the document
    with nogil:
        for i in range(document_len):
            j = i - window      # negative OK: will pad with null word
            k = i + window_r + 1  # past document end OK: will pad with null word

            # compose l1 & clear work
            for m in range(doctag_len):
                # doc vector(s)
                memcpy(&_neu1[m * vector_size], &_doctag_vectors[_doctag_indexes[m] * vector_size],
                       vector_size * cython.sizeof(REAL_t))
            n = 0
            for m in range(j, k):
                # word vectors in window
                if m == i:
                    continue
                if m < 0 or m >= document_len:
                    window_indexes[n] = null_word_index
                else:
                    window_indexes[n] = indexes[m]
                n = n + 1
            for m in range(window + window_r):
                memcpy(&_neu1[(doctag_len + m) * vector_size], &_word_vectors[window_indexes[m] * vector_size],
                       vector_size * cython.sizeof(REAL_t))
            memset(_work, 0, layer1_size * cython.sizeof(REAL_t))  # work to accumulate l1 error

            if hs:
                fast_document_dmc_hs(points[i], codes[i], codelens[i],
                                     _neu1, syn1, _alpha, _work,
                                     layer1_size, vector_size, _learn_hidden)
            if negative:
                next_random = fast_document_dmc_neg(negative, cum_table, cum_table_len, next_random,
                                                    _neu1, syn1neg, indexes[i], _alpha, _work,
                                                   layer1_size, vector_size, _learn_hidden)

            if _learn_doctags:
                for m in range(doctag_len):
                    our_saxpy(&vector_size, &_doctag_locks[_doctag_indexes[m]], &_work[m * vector_size],
                              &ONE, &_doctag_vectors[_doctag_indexes[m] * vector_size], &ONE)
            if _learn_words:
                for m in range(window + window_r):
                    our_saxpy(&vector_size, &_word_locks[window_indexes[m]], &_work[(doctag_len + m) * vector_size],
                              &ONE, &_word_vectors[window_indexes[m] * vector_size], &ONE)

    return result