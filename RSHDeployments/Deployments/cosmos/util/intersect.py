#
# intersection
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#
import numpy as np


def intersect(x, y):
    """intersect(x, y) -> xm, ym
    x, y: 1-d arrays of unique values
    xm, ym: indices into x and y giving sorted intersection
    """
    # basic idea taken from numpy.lib.arraysetops.intersect1d
    if isinstance(x, list):
        x = np.array(x)
    if isinstance(y, list):
        y = np.array(y)

    u_x, u_idx_x = np.unique(x, return_index=True)
    u_y, u_idx_y = np.unique(y, return_index=True)
    i_xy = np.intersect1d(u_x, u_y, assume_unique=True)
    i_idx_x = u_idx_x[np.in1d(u_x, i_xy, assume_unique=True)]
    i_idx_y = u_idx_y[np.in1d(u_y, i_xy, assume_unique=True)]

    return x[i_idx_x], i_idx_x, i_idx_y

    # aux = np.concatenate((x, y))
    # sidx = aux.argsort()
    # # Note: intersect1d uses aux[:-1][aux[1:]==aux[:-1]] here - I don't know why the first [:-1] is necessary
    # inidx = aux[sidx[1:]] == aux[sidx[:-1]]
    #
    # # quicksort is not stable, so must do some work to extract indices
    # # (if stable, sidx[inidx.nonzero()]  would be for x)
    # # interlace the two sets of indices, and check against lengths
    # xym = np.vstack((sidx[inidx.nonzero()], sidx[1:][inidx.nonzero()])).T.flatten()
    #
    # xm = xym[xym < len(x)]
    # ym = xym[xym >= len(x)] - len(x)

    # return x[xm], xm, ym


def ismember(a, b):
    """Implement ismember in Matlab"""
    aa = a
    a = np.array(a)
    b = np.array(b)
    if a.ndim != b.ndim:
        a = np.array([aa])
    tf = np.in1d(a, b)
    u = np.unique(a[tf])
    index = np.array([(np.where(b == i))[0][-1] if t else 0 for i,t in zip(a, tf)])
    return tf, index


def union_by_rows(a, b):
    ranges = np.vstack((a, b))
    ranges = ranges[ranges[:, 0].argsort()]

    overlapping = np.all((ranges[1:, ] == ranges[:-1, ]), axis=1) + 1
    result = np.delete(ranges, overlapping, axis=0)
    return result


def intersect_by_rows(x, y):

    u_x, u_idx_x = np.unique(x, axis=0, return_index=True)
    u_y, u_idx_y = np.unique(y, axis=0, return_index=True)

    aux = np.vstack((u_x, u_y))
    sidx = aux[:, 0].argsort()
    inidx = np.all(aux[sidx[1:], ] == aux[sidx[:-1], ], axis=1)

    xym = np.vstack((sidx[inidx], sidx[1:][inidx])).T.flatten()
    xm = xym[xym < len(x)]
    ym = xym[xym >= len(x)] - len(x)

    i_idx_x = u_idx_x[xm]
    i_idx_y = u_idx_y[ym]

    return x[i_idx_x], i_idx_x, i_idx_y

    # return x[xm,], xm, ym
