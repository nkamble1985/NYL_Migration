#
# filtering factors
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#
import numpy as np
import numbers


def percentile_filter(x, low=0, high=100, left_include=True, right_include=False):
    """

    :param x:
    :param low:
    :param high:
    :param left_include:
    :param right_include:
    :return:
    """
    if low < 0:
        low = 0
    if high > 100:
        high = 100
    if np.any(np.isinf(x)):
        x[np.isinf(x)] = np.nan
    x_low = np.nanpercentile(x, low)
    x_high = np.nanpercentile(x, high)
    if isinstance(x, list):
        x = np.array(x)
    mask = np.full(x.shape, False)
    if low >= 0:
        if left_include:
            mask[x >= x_low] = True
        else:
            mask[x > x_low] = True

    if high <= 100:
        if right_include:
            mask[x > x_high] = False
        else:
            mask[x >= x_high] = False
    return mask


def smoothstep(x, cutoff=1, width=1, smooth_type='cubic', high_pass=True):
    """
    smoothstep(x, left=0, right=1, left_width=1, right_width=1, smooth_type='quintic')

    returns a high(left edge) or low(right edge) pass filter with 1 between left and right, smooth edges with left edge
    width and right edge specifiable. Smooth types are cubic, quintic and exponential

    Example:
        smoothstep(x, cutoff=2, width=1, smooth_type='quintic')
        This creates a high pass filter at 2 extend to left width 1

    """
    if high_pass:
        L = cutoff - width
        R = cutoff
    else:
        L = cutoff
        R = cutoff + width
    xc = clamp((x - L) / (R - L))
    if not high_pass:
        xc = -(xc - 1)
    if not isinstance(smooth_type, str):
        raise Exception("smoothing type must be a string")
    smooth_type = smooth_type.lower().strip()
    if smooth_type == 'cubic':
        y = cubic_hermitian(xc, 0, 1)
    elif smooth_type == 'quintic':
        y = quintic_hermitian(xc, 0, 1)
    else:
        y = quintic_hermitian(xc, 0, 1)

    return y


def smoothbox(x, left=0, right=1, left_width=1, right_width=1, smooth_type='quintic'):
    """
    smoothbox(x, left=0, right=1, left_width=1, right_width=1, smooth_type='quintic')

    returns a box filter with 1 between left and right, smooth edges with left edge
    width and right edge width specifiable. Smooth types are cubic, quintic and exponential

    Example:
        smoothbox(x, left=2, right = 5, left_width=1, right_width=0.5, smooth_type='quintic')
        This creates a box filter between 2 and 5, left width 1, and right width 0.5. Value falls to
        zero left of 1 (2-1) and right of 5.5 (5 + 0.5)

    """

    L = min(left, right)
    R = max(left, right)
    if left_width is None or left_width <= 0:
        left_width = 1
    if right_width is None or right_width <= 0:
        right_width = 1
    if x < R:
        return smoothstep(x, L, left_width, smooth_type)
    else:
        return smoothstep(x, R, right_width, smooth_type, high_pass=False)


def clamp(x, left=0, right=1):
    L = min(left, right)
    R = max(left, right)
    if x < L:
        x = L
    elif x > R:
        x = R
    return x


def cubic_hermitian(x, left=0, right=1):
    L = min(left, right)
    R = max(left, right)
    xc = clamp((x - L) / (R - L), 0, 1)
    return xc * xc * (3 - 2 * xc)


def quintic_hermitian(x, left=0, right=1):
    L = min(left, right)
    R = max(left, right)
    xc = clamp((x - L) / (R - L), 0, 1)
    return xc * xc * xc * (xc * (xc * 6 - 15) + 10)


def exponential_smoothing(x, k=1):
    return 1 / (np.exp(-k * x) + 1)
