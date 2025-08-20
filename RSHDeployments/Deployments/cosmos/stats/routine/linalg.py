#
# linear algebra functions
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#

import numpy as np
import warnings

import pandas as pd


def woodbury_inverse(A, U, C, V=None):
    """
        Sherman-Morrison-Woodbury matrix identity
        A faster matrix inversion of quadratic form as follows
        ( A + UCV)^(-1)
    """
    if not (isinstance(A, np.ndarray)):
        M_A = np.array(A)
    else:
        M_A = A

    if not (isinstance(U, np.ndarray)):
        M_U = np.array(U)
    else:
        M_U = U
    if not (isinstance(C, np.ndarray)):
        M_C = np.array(C)
    else:
        M_C = C
    if V is None:
        M_V = M_U.T
    else:
        if not (isinstance(V, np.ndarray)):
            M_V = np.array(V)
        else:
            M_V = V

    if not (is_square(M_A)):
        raise Exception("A not a square matrix")
    if not (is_square(M_C)):
        raise Exception("C is not a square matrix")
    # inverse of A
    if is_diagonal(M_A):
        M_A_INV = np.diag(1 / np.diagonal(M_A))
    else:
        M_A_INV = np.linalg.inv(M_A)
    # inverse of C
    if is_diagonal(M_C):
        M_C_INV = np.diag(1 / np.diagonal(M_C))
    else:
        M_C_INV = np.linalg.inv(M_C)
    M_K = M_C_INV + np.matmul(M_V, np.matmul(M_A_INV, M_U))
    M_K_INV = np.linalg.inv(M_K)
    M = M_A_INV - np.matmul(M_A_INV, np.matmul(M_U, np.matmul(M_K_INV, np.matmul(M_V, M_A_INV))))
    return M


def wls_project(B, W=None, delta=None):
    """
    Weighted Least Square Projector
    :param B: N x K
    :param W: [ optional ] N x 1, if empty or a scalar, it becomes equal weight
    :param delta: [ optional ] scalar, ridge perturbation
    :return:

    F = Projector x R
    """

    if not (isinstance(B, np.ndarray)):
        B_ = np.array(B)
    else:
        B_ = B
    N = B_.shape[0]
    K = B_.shape[1]
    if W is None:
        W_ = np.ones((N, 1))
    else:
        if not (isinstance(W, np.ndarray)):
            W_ = np.array(W)
        else:
            W_ = np.copy(W)

    if W_.ndim > 2:
        raise Exception('Weighted Least Square Weight Vector Dimension Larger Than 2')
    elif W_.ndim == 0:
        W_ = np.ones((N, 1))
    elif W_.ndim == 2:
        if 1 in W_.shape:
            W_ = W_.reshape((W_.size, 1))
        else:
            raise Exception('Weighted Least Square Weight Vector Dimension Incorrect: vector expected')
    elif W_.ndim == 1:
        W_ = W_.reshape((W_.size, 1))
    else:
        raise Exception('Dimension Error')

    if W_.size != N:
        raise Exception('Weight vector length dismatches exposure matrix')

    if delta is None:
        delta = 0
    if delta > 0:
        print('Ridge perturbation by %f' % delta)
    M_W = to_diagonal_matrix(W_)
    cov_cond = np.linalg.cond(M_W)
    bcovb = np.matmul(B_.T, np.matmul(M_W, B_))
    bcovb_cond = np.linalg.cond(bcovb)
    p = np.linalg.inv(bcovb + delta * to_diagonal_matrix(np.ones((K, 1))))
    p = np.matmul(p, np.matmul(B_.T, M_W))
    result = {'projector': p, 'cov_inv': M_W, 'cov_cond': cov_cond, 'bcovb': bcovb,
              'bcovb_cond': bcovb_cond}
    return result


def gls_project(B_alpha, B_risk, FCov, RCov, delta=None, COV=None, confine_flag=None):
    """
        Generalized Least Square Projector

        Arguments:

            B_alpha : N x K, alpha factor exposures
            B_risk  : N x L, risk factor exposures
            FCov    : L x L, risk factor covariance
            RCov    : N x 1 or N x N, residual covariance
            delta   : scalar, ridge perturbation

        Output:
            P       : K x N, portfolio weights

        F = Projector x R
    """

    if not (isinstance(B_alpha, np.ndarray)):
        B_a = np.array(B_alpha)
    else:
        B_a = B_alpha
    N = B_a.shape[0]
    K = B_a.shape[1]
    if not (isinstance(B_risk, np.ndarray)):
        B_r = np.array(B_risk)
    else:
        B_r = B_risk
    if B_r.shape[0] != N:
        raise Exception('B_risk shape incompatible with B_alpha ')
    L = B_r.shape[1]
    if not (isinstance(FCov, np.ndarray)):
        fcov = np.array(FCov)
    else:
        fcov = FCov
    if not (is_square(fcov)):
        raise Exception('Factor Covariance Matrix Not A Square Matrix')
    if fcov.shape[0] != L:
        raise Exception('Factor Covariance Matrix  shape '
                        'Incompatile with Exposure Matrix shape ')
    if not (isinstance(RCov, np.ndarray)):
        rcov = np.array(RCov)
    else:
        rcov = RCov
    dcov = to_diagonal_matrix(rcov)
    if dcov.shape[1] != N:
        raise Exception('Residual Covariance Dimension Does not match Exposures')

    if delta is None:
        delta = 0
    if delta > 0:
        print('Ridge perturbation by %f' % delta)

    if COV is None:
        sigma_inv = woodbury_inverse(dcov, B_r, fcov)
        COV = np.matmul(B_r, np.matmul(fcov, B_r.T)) + dcov
        COV_cond = np.linalg.cond(COV)
    else:
        sigma_inv = np.linalg.inv(COV)
        COV_cond = np.linalg.cond(COV)

    if confine_flag is None or not isinstance(confine_flag, bool):
        confine_flag = False

    BCOVB = np.matmul(B_a.T, np.matmul(sigma_inv, B_a))
    p = np.linalg.inv(BCOVB + delta * to_diagonal_matrix(np.ones((K, 1))))
    p = np.matmul(p, B_a.T)
    p = np.matmul(p, sigma_inv)
    result = {'projector': p, 'cov_inv': sigma_inv, 'cov_cond': COV_cond, 'bcovb': BCOVB,
              'bcovb_cond': np.linalg.cond(BCOVB)}
    if confine_flag:
        try:
            proj_confined = np.zeros(result['projector'].shape)
            good_index = np.where(np.sum(B_r != 0, axis=0) > 3)[0]
            if np.size(good_index) > 0:
                C = B_r[:, good_index]
                # A = C.dot(np.linalg.inv(C.T.dot(C)).dot(C.T))
                A = C @ np.linalg.inv(C.T @ C) @ C.T
                proj_confined = result['projector'].dot(A)
                del A
            del good_index
            result['projector_confined'] = proj_confined
            del proj_confined
        except ValueError:
            warnings.warn('Unable to confine projector onto the risk model')
    return result


def to_diagonal_matrix(A):
    """
        Turn a vector into a diagonal matrix

        Arguments:
            A : matrix
        Output
            B: matrix
            if A is one dimensional array, or N x 1 (or 1 X N) array, it will be
            a diagonal matrix with A on the diagonal
            if A is a 2 dimenstional array, the diagonal elements will remain
            if A is of any other diemsion, the diagonal elements will remain
    """
    if not (isinstance(A, np.ndarray)):
        M_A = np.array(A)
    else:
        M_A = A

    if M_A.ndim == 1:
        return np.diag(M_A)
    elif M_A.ndim == 2:
        if 1 in M_A.shape:
            return np.diag(M_A.reshape(M_A.size, ))
        else:
            return np.diag(np.diagonal(M_A))
    else:
        return np.diag(np.diagonal(M_A))


def is_diagonal(A):
    """
        Testing for diagonal matrix

        is_diagonal( A )
    """
    if not (isinstance(A, np.ndarray)):
        M_A = np.array(A)
    else:
        M_A = A
    if M_A.ndim < 2:
        return False
    if len(set(M_A.shape)) != 1:
        return False
    else:
        return np.count_nonzero(M_A - np.diag(np.diagonal(M_A))) == 0


def is_square(A):
    """
        Testing for square matrix

        is_square_matrix( A )
    """
    if not (isinstance(A, np.ndarray)):
        M_A = np.array(A)
    else:
        M_A = A
    if M_A.ndim < 2:
        return False
    if len(set(M_A.shape)) == 1:
        return True
    else:
        return False


def is_symmetric(A):
    if not (isinstance(A, np.ndarray)):
        M_A = np.array(A)
    else:
        M_A = A
    if np.count_nonzero(M_A - M_A.T) > 0:
        return False
    else:
        return True


def cov_to_corr(m):
    if isinstance(m, list):
        m = np.array(m)
    if m.ndim != 2:
        print(f"Unable to convert a matrix of dimension other than 2 to correlation")
        raise ValueError
    if m.shape[0] != m.shape[1]:
        print(f"Unable to convert a non-square matrix to correlation")
        raise ValueError
    var = np.diag(m)

    if (var <= 0).sum() > 0:
        print(f"Matrix contains negative diagonal elements")
        raise ValueError
    vol = np.sqrt(var)
    outer_vol = np.outer(vol, vol)
    corr = m / outer_vol
    if isinstance(m, pd.DataFrame):
        corr.index = m.index
        corr.columns = m.columns
    return corr


def projector_symmetric(e, j=None):
    k = e.shape[1]
    projectors = [None] * k
    for i in range(k):
        v = e[:, [i]]
        projectors[i] = np.matmul(v, v.T)
    if j is None:
        return projectors
    else:
        if 0 <= j < k:
            return projectors[j]
        else:
            raise ValueError('Requested index out of bounds for eigen vectors')


def projector_asymmetric(e, i, j):
    v1 = e[:, [int(i)]]
    v2 = e[:, [int(j)]]
    return 0.5 * (np.matmul(v1, v2.T) + np.matmul(v2, v1.T))


def matrix_sum(matrices, weights=None):
    """

    :param matrices: list of matrices of identical shape
    :param weights:
    :return:
    """
    if weights is None:
        weights = np.ones(len(matrices))
    if len(weights) != len(matrices):
        print(f"Not matching in dimension when combining spectral projectors and their weights")
        return None
    m = np.zeros((matrices[0].shape[0], matrices[0].shape[1]))
    for ix, s in enumerate(matrices):
        m = weights[ix] * s + m
    return m

