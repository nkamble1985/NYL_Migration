#
# routines
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#
import numbers
import pandas as pd
import numpy as np
import classes.root as root
import dataloader.market_data as md
import dataloader.portfolio as port
import util.utilities as util
import warnings
from util.intersect import *
import scipy.stats.mstats as mstats
import scipy.stats as ss
import os


def group_adjustments(df, univ_weights=None, grouping_factor=None,
                      bus_day=None, min_count=5, median_adjust=False):
    """

    :param df: columns are securities, one row of data
    :param univ_weights: columns are securities that belong to a universe, one row of weights
    :param grouping_factor:
    :param bus_day:
    :param min_count:
    :param median_adjust:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if min_count is None or not isinstance(min_count, numbers.Number) or min_count < 0:
        min_count = 5

    if grouping_factor is not None and not isinstance(grouping_factor, (str, root.GROUP)):
        grouping_factor = None

    if grouping_factor is not None and bus_day is None:
        raise Exception('Must provide a valid business date')

    if univ_weights is None:
        univ_weights = pd.DataFrame(1, index=df.index, columns=['values'])
    univ_sec_ids = univ_weights.index
    all_sec_ids = df.index
    # all data
    vf = pd.DataFrame(np.nan, columns=['values'], index=df.index)
    vf.update(df)
    # universe data
    uf = pd.DataFrame(index=univ_sec_ids)
    uf['values'] = np.nan
    uf['weights'] = univ_weights['values'].to_numpy()
    uf.update(vf)
    uf['wv'] = uf['values'] * uf['weights']
    uf.loc[pd.isnull(uf['wv']), 'weights'] = np.nan
    uf['count'] = 1
    adjustments = np.ones((len(all_sec_ids), 1)) * np.nan
    if grouping_factor is not None:
        group = root.load_object(grouping_factor)
        classification = group.classification
        levels = group.levels
        for level in levels:
            level = level.strip().lower()
            try:
                mapping = md.get_classification(all_sec_ids, level,
                                                source=classification,
                                                as_of=bus_day, vector_flag=True)
                mapping.drop(columns=['value'], inplace=True)
                vf[level] = np.nan
                vf.update(mapping)
                uf[level] = np.nan
                uf.update(mapping)

                g = uf.groupby(level)
                if median_adjust:
                    g_adj = g.median()
                    g_adj['adjustment'] = g_adj['values']
                else:
                    g_adj = g.sum()
                    g_adj['adjustment'] = g_adj['wv'] / g_adj['weights']

                zf = pd.DataFrame(index=vf.index, columns=[level])
                zf[level] = vf[level]
                zf = zf.merge(g_adj, how='left', left_on=level, right_index=True)
                index = np.where((zf[['count']].to_numpy() >= min_count) & (np.isnan(adjustments)))[0]
                if len(index) > 0:
                    adjustments[index] = zf[['adjustment']].iloc[index].to_numpy()
            except Exception as e:
                print(e)
                warnings.warn(f"Unable to adjust at level: {level.strip().lower()}")

    # universe adjustments
    if median_adjust:
        universe_adj = np.nanmedian(uf['values'])
    else:
        universe_adj = np.nansum(uf['wv'].to_numpy()) / np.nansum(uf['weights'].to_numpy())
    if np.isnan(adjustments).sum() > 0:
        adjustments[np.isnan(adjustments)] = universe_adj
    vf['adjustment'] = adjustments
    vf['universe_adjustment'] = universe_adj
    vf['weights'] = np.NAN
    vf['in_universe'] = False
    vf.loc[vf.index.isin(univ_sec_ids), 'in_universe'] = True
    vf.loc[vf.index.isin(univ_weights.index), 'weights'] = univ_weights['values']
    return vf


def winsorize(primary_vector, low=0, high=100, alt_vector=None):
    """

    :param primary_vector:
    :param low: default 0
    :param high: default 100
    :param alt_vector:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if not isinstance(primary_vector, np.ndarray):
        primary_vector = np.array(primary_vector)
    vec = mstats.winsorize(primary_vector[~np.isnan(primary_vector)],
                           limits=(low/100, 1-high/100)).data
    max_val = np.max(vec)
    min_val = np.min(vec)
    vector = primary_vector
    vector[vector >= max_val] = max_val
    vector[vector <= min_val] = min_val
    if alt_vector is not None:
        if not isinstance(alt_vector, np.ndarray):
            alt_vector = np.array(alt_vector)
        alt_vector[alt_vector >= max_val] = max_val
        alt_vector[alt_vector <= min_val] = min_val
        return vector, alt_vector
    else:
        return vector


def exclude_values_from_groups(bus_day, values, sec_ids, exclusion_factors,
                               excluded_groups, excluded_levels, calendar_str):
    """

    :param bus_day:
    :param values:
    :param sec_ids:
    :param exclusion_factors:
    :param excluded_groups:
    :param excluded_levels:
    :param calendar_str:
    :return:
    """
    if values is None or exclusion_factors is None or excluded_groups is None:
        return None
    if calendar_str is None or not isinstance(calendar_str, str):
        calendar_str = 'GL'
    if len(sec_ids) != len(values):
        raise Exception('values and sec_ids lengths mismatch')
    ex_days = util.load_business_days(calendar_str, [], bus_day)
    ex_day = ex_days[-1]
    del ex_days
    if isinstance(exclusion_factors, str):
        exclusion_factors = np.array([exclusion_factors])
    exf = exclusion_factors
    exclusion_factors = np.array([])
    for exg in exf:
        exclusion_factors = np.append(exclusion_factors, root.load_object(exg))
    if exclusion_factors is None:
        return None
    if not isinstance(exclusion_factors, (list, np.ndarray)):
        exclusion_factors = np.array([exclusion_factors])
    if not isinstance(excluded_groups, (list, np.ndarray)):
        excluded_groups = np.array([excluded_groups])
    if len(exclusion_factors) != len(excluded_groups):
        if len(exclusion_factors) == 1:
            exclusion_factors = exclusion_factors * len(excluded_groups)
        else:
            raise Exception('Exclusion factors and excluded groups lengths mismatch')

    if excluded_levels is None or not isinstance(excluded_levels, (str, list)):
        excluded_levels = [x.level for x in exclusion_factors]
    if isinstance(excluded_levels, str):
        excluded_levels = np.array([excluded_levels])
    if len(excluded_levels) != len(excluded_groups):
        if len(excluded_levels) == 1:
            excluded_levels = excluded_levels * len(excluded_groups)
        else:
            raise Exception('Excluded levels and excluded groups lengths mismatch')

    for j, exg in enumerate(excluded_groups):
        if exclusion_factors[j] is None:
            continue
        try:
            exposures = exclusion_factors[j].load_exposures(ex_day, sec_ids, calendar_str=calendar_str,
                                                            alt_level=excluded_levels[j])
            c, ia, ib = intersect(exposures.columns.to_numpy(), excluded_groups[j])
            if np.size(ia) > 0:
                index = np.where(np.sum(abs(exposures.iloc[:,ia]), axis=1) >= 1)[0]
                if np.size(index) == 0:
                    continue
                c, i1, i2 = intersect(exposures.index[index], sec_ids)
                if np.size(i2) > 0:
                    values.loc[c] = np.nan
                    print(f"Excluding {len(i2)} stocks from {exclusion_factors[j].name}: {excluded_groups[j]} ")
        except ValueError:
            warnings.warn('Unable to load or exclude groups: %s: level %s : %s' \
                          % (exclusion_factors[j].name, excluded_levels[j], excluded_groups[j]))
    return values


def group_stats(sec_ids, vector, group='COSMOS_SECTOR', bus_day=None):
    """
    compute statistics by groups
    :param sec_ids:
    :param vector:
    :param group: default 'COSMOS_SECTOR'
    :param bus_day:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    obj = root.load_object(group)
    if bus_day is None:
        bus_day = util.today()
    group = obj.load_exposures(bus_day, sec_ids)
    groups = group.columns.to_numpy()
    index = ['count', 'missing', 'inf', 'positive', 'negative',
             'mean', 'median', '0%', '10%', '20%', '25%', '30%',
             '40%', '50%', '60%', '70%', '75%', '80%', '90%', '100%']
    df = pd.DataFrame(index=index, columns=groups)
    vector = np.array(vector.reshape(len(vector), 1), dtype=float)
    for g in groups:
        g_sec = group.index[np.where(group[g] == 1)[0]]
        if g_sec is None or len(g_sec) == 0:
            continue
        vec = vector[np.isin(sec_ids, g_sec)]
        df.loc['count', g] = len(vec)
        df.loc['missing', g] = pd.isnull(vec).sum()
        df.loc['mean', g] = np.nanmean(vec)
        df.loc['max', g] = np.nanmax(vec)
        df.loc['100%', g] = df.loc['max', g]
        df.loc['min', g] = np.nanmin(vec)
        df.loc['0%', g] = df.loc['min', g]
        df.loc['inf', g] = np.isinf(vec).sum()
        df.loc['positive', g] = len(vec[vec > 0])
        df.loc['negative', g] = len(vec[vec < 0])
        df.loc['median', g] = np.nanmedian(vec)
        df.loc['50%', g] = df.loc['median', g]
        df.loc['10%', g] = np.nanpercentile(vec, 10)
        df.loc['20%', g] = np.nanpercentile(vec, 20)
        df.loc['25%', g] = np.nanpercentile(vec, 25)
        df.loc['30%', g] = np.nanpercentile(vec, 30)
        df.loc['40%', g] = np.nanpercentile(vec, 40)
        df.loc['60%', g] = np.nanpercentile(vec, 60)
        df.loc['70%', g] = np.nanpercentile(vec, 70)
        df.loc['75%', g] = np.nanpercentile(vec, 75)
        df.loc['80%', g] = np.nanpercentile(vec, 80)
        df.loc['90%', g] = np.nanpercentile(vec, 90)
        df.loc['100%', g] = np.nanpercentile(vec, 100)

    # universe
    g = 'universe'
    vec = vector
    df.loc['count', g] = len(vec)
    df.loc['missing', g] = np.isnan(vec).sum()
    df.loc['mean', g] = np.nanmean(vec)
    df.loc['max', g] = np.nanmax(vec)
    df.loc['100%', g] = df.loc['max', g]
    df.loc['min', g] = np.nanmin(vec)
    df.loc['0%', g] = df.loc['min', g]
    df.loc['inf', g] = np.isinf(vec).sum()
    df.loc['positive', g] = len(vec[vec > 0])
    df.loc['negative', g] = len(vec[vec < 0])
    df.loc['median', g] = np.nanmedian(vec)
    df.loc['50%', g] = df.loc['median', g]
    df.loc['10%', g] = np.nanpercentile(vec, 10)
    df.loc['20%', g] = np.nanpercentile(vec, 20)
    df.loc['25%', g] = np.nanpercentile(vec, 25)
    df.loc['30%', g] = np.nanpercentile(vec, 30)
    df.loc['40%', g] = np.nanpercentile(vec, 40)
    df.loc['60%', g] = np.nanpercentile(vec, 60)
    df.loc['70%', g] = np.nanpercentile(vec, 70)
    df.loc['75%', g] = np.nanpercentile(vec, 75)
    df.loc['80%', g] = np.nanpercentile(vec, 80)
    df.loc['90%', g] = np.nanpercentile(vec, 90)
    df.loc['100%', g] = np.nanpercentile(vec, 100)

    # missing
    missing_index = np.where(group.sum(axis=1) == 0)[0]
    df['missing'] = np.nan
    if len(missing_index) > 0:
        g = 'missing'
        missing = group.index[missing_index].to_numpy()
        vec = vector[np.isin(sec_ids, missing)]
        df.loc['count', g] = len(vec)
        if len(vec) == 1:
            return df
        df.loc['missing', g] = np.isnan(vec).sum()
        df.loc['mean', g] = np.nanmean(vec)
        df.loc['max', g] = np.nanmax(vec)
        df.loc['100%', g] = df.loc['max', g]
        df.loc['min', g] = np.nanmin(vec)
        df.loc['0%', g] = df.loc['min', g]
        df.loc['inf', g] = np.isinf(vec).sum()
        df.loc['positive', g] = len(vec[vec > 0])
        df.loc['negative', g] = len(vec[vec < 0])
        df.loc['median', g] = np.nanmedian(vec)
        df.loc['50%', g] = df.loc['median', g]
        df.loc['10%', g] = np.nanpercentile(vec, 10)
        df.loc['20%', g] = np.nanpercentile(vec, 20)
        df.loc['25%', g] = np.nanpercentile(vec, 25)
        df.loc['30%', g] = np.nanpercentile(vec, 30)
        df.loc['40%', g] = np.nanpercentile(vec, 40)
        df.loc['60%', g] = np.nanpercentile(vec, 60)
        df.loc['70%', g] = np.nanpercentile(vec, 70)
        df.loc['75%', g] = np.nanpercentile(vec, 75)
        df.loc['80%', g] = np.nanpercentile(vec, 80)
        df.loc['90%', g] = np.nanpercentile(vec, 90)
        df.loc['100%', g] = np.nanpercentile(vec, 100)

    return df


def coverage(start_date, end_date, fac, value_type='DESCRIPTOR', freq='MONTHEND', univ=None):
    """

    :param start_date:
    :param end_date:
    :param fac:
    :param value_type:
    :param freq:
    :param univ:
    :return:
    """
    fac = root.load_object(fac)
    bus_days = util.load_business_days(fac.calendar, start_date, end_date, freq)
    value_type = value_type.strip()
    if univ is None:
        univ = fac.universe
    df = pd.DataFrame(np.nan, index=bus_days, columns=[value_type, 'count', 'missing',
                                                       'valid', 'valid %', 'mean',
                                                       'median', 'min', 'max', 'positive',
                                                       'negative', 'zero', 'std', 'inf',
                                                       '10pct', '20pct', '25pct', '75pct',
                                                       '80pct', '90pct'])

    for idx, d in enumerate(bus_days):
        try:
            p = port.get_cached_positions(d, d, univ)
            sec_ids = p.columns.to_numpy()
            df.loc[d, 'count'] = len(sec_ids)
            df.loc[d, 'missing'] = len(sec_ids)
            b = fac.load_values(value_type, d, d, sec_ids)
            v = b.to_numpy()
            df.loc[d, 'missing'] = np.isnan(v).sum()
            df.loc[d, 'valid'] = df.loc[d, 'count'] - df.loc[d, 'missing']
            df.loc[d, 'valid %'] = df.loc[d, 'valid'] / df.loc[d, 'count']
            df.loc[d, 'mean'] = np.nanmean(v)
            df.loc[d, 'median'] = np.nanmean(v)
            df.loc[d, 'std'] = np.nanstd(v)
            df.loc[d, 'max'] = np.nanmax(v)
            df.loc[d, 'min'] = np.nanmin(v)
            df.loc[d, 'inf'] = np.isinf(v).sum()
            df.loc[d, 'positive'] = (v > 0).sum()
            df.loc[d, 'negative'] = (v < 0).sum()
            df.loc[d, 'zero'] = (v == 0).sum()
            df.loc[d, '25pct'] = np.percentile(v, 25)
            df.loc[d, '75pct'] = np.percentile(v, 75)
            df.loc[d, '10pct'] = np.percentile(v, 10)
            df.loc[d, '20pct'] = np.percentile(v, 20)
            df.loc[d, '80pct'] = np.percentile(v, 80)
            df.loc[d, '90pct'] = np.percentile(v, 90)
            if freq.upper() != 'DAILY' or np.mod(idx, 21) == 0:
                print(f"{d.strftime(util.YY_MM_DD_format)}: {fac.name}, {value_type}: "
                      f"{df.loc[d, 'valid']:.0f} valid ({df.loc[d, 'valid %']*100:.0f} %), max "
                      f"{df.loc[d, 'max']:.2f}, min {df.loc[d, 'min']:.2f}, mean "
                      f"{df.loc[d, 'mean']:.2f}, median {df.loc[d, 'median']:.2f}, positive "
                      f"{df.loc[d, 'positive']:.0f}, negative {df.loc[d, 'negative']:.0f}, zero "
                      f"{df.loc[d, 'zero']:.0f}, ")
        except Exception as e:
            print(e)
            continue
    return df


def within_range(day, lives):
    """

    :param day: int or datetime string
    :param lives: util.life object, or list of objects
    :return: True/False or list of True or False

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """

    if day is None:
        return [True] * len(lives)
    d = util.parse_date(day)
    if isinstance(lives, (list, np.ndarray)):
        return list(map(lambda x: x.within_range(d), lives))
    elif isinstance(lives, root.Life):
        return lives.within_range(d)
    else:
        print("Warning: Not util.life type")
        return False


def exponential_weights(t,
                        half_life=None,
                        reverse_flag=True):
    """
    Exponential weight sequence
    :param t: integer, length of values
    :param half_life: [ optional ] K-by-1 double, half lives
    :param reverse_flag: [ optional ] logical, default true
    :return: T-by-K double, normalized weights

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """

    if (not isinstance(t, numbers.Number)) or t <= 0:
        warnings.warn('you must specify positive length of the weights.')

    if half_life is None:
        weights = np.ones((t, 1))
    else:
        if not isinstance(half_life, np.ndarray):
            half_life = np.array(half_life)
            if not np.all(half_life > 0):
                raise Exception('You must specify positive half lives of the weights.')

        k = half_life.size
        half_life = half_life.reshape((1, k))
        weights = np.arange(t).reshape((t, 1)) + 1
        weights = weights.repeat(k, axis=1)
        weights = weights / half_life.repeat(t, axis=0)
        weights = 2 ** (-weights)

    weights = weights / np.atleast_2d(sum(weights)).repeat(t, axis=0)

    if reverse_flag:
        weights = weights[::-1]

    return weights


def russell_linking_factors(ret):
    """
    compute russell linking factor to link daily contributions to period
    :param ret:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if isinstance(ret, pd.DataFrame) or isinstance(ret, pd.Series):
        ret = ret.to_numpy()
    if ret.dtype == 'object':
        ret = ret.astype('float64')
    T, N = ret.shape
    epsilon = 1e-12
    percent_period_returns = np.prod(1 + ret, axis=0) - 1
    null_index = np.where(percent_period_returns == 0)[0]
    if np.size(null_index) > 0:
        percent_period_returns[null_index] = epsilon
    log_period_returns = np.log(1 + percent_period_returns)
    # f_period = percent_period_returns / log_period_returns
    f_period = log_period_returns / percent_period_returns

    null_index = np.where(ret == 0)[0]
    if np.size(null_index) > 0:
        ret[null_index] = epsilon
    log_ts = np.log(1 + ret)
    f_ts = log_ts / ret

    factors = f_ts / (np.tile(f_period, (T, 1)))
    if isinstance(factors, pd.DataFrame):
        factors = factors.to_numpy()
    return factors


def daily_to_period(ret, period='MONTHEND', calendar_str=None):
    """
    compound daily to period returns
    :param ret: data frame, T x N
    :param period: default 'MONTHEND'
    :param calendar_str: default None (or 'GL')
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if calendar_str is None:
        calendar_str = 'GL'
    if period is None:
        print(f'No right periodicity required: unable to turn daily to period returns')
        return None
    if not isinstance(period, str):
        print(f'No right periodicity required: unable to turn daily to period returns')
        return None
    period = period.strip().upper()
    if period in ['MONTHLY', 'MONTH', 'MONTHS']:
        period = 'MONTHEND'
    elif period in ['QUARTER', 'QUARTERS', 'QUARTERLY']:
        period = 'QUARTEREND'
    elif period in ['YEAR', 'YEARS', 'YEARLY', 'ANNUAL', 'ANNUALLY']:
        period = 'YEAREND'

    periods = util.load_business_days(calendar_str, freq=period)
    periods = periods[periods >= ret.index[0]]
    ix = np.argmax(periods >= ret.index[-1])
    periods = periods[:ix+1]
    del ix
    df = pd.DataFrame(np.nan, index=periods, columns=ret.columns)
    for idx, d in enumerate(periods):
        if idx == 0:
            index = np.where(ret.index <= periods[idx])[0]
        else:
            index = np.where(np.logical_and(ret.index > periods[idx - 1], ret.index <= periods[idx]))[0]
        if len(index) == 0:
            continue
        mat = ret.iloc[index, :].to_numpy()
        mat[pd.isnull(mat)] = 0.0
        df.loc[d] = np.prod(1+mat,axis=0)-1

    return df


def multi_day_return(mat, max_multi_day, value=None):
    """
    compound daily to period returns

    :param mat:
    :param max_multi_day:
    :param value:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if mat.shape[0] <= max_multi_day:
        return mat
    null_mat = np.isnan(mat)
    nvec = np.sum(null_mat, axis=0)
    null_index = np.where(nvec)[0]
    if np.size(null_index) == 0:
        return mat

    if value is None or not isinstance(value, numbers.Number):
        value = 0

    ia = np.where(null_mat[0, ])[0]
    null_index = np.setdiff1d(null_index, ia)
    if np.size(null_index) == 0:
        return mat

    ia = np.where(null_mat[-1, ])[0]
    null_index = np.setdiff1d(null_index, ia)
    if np.size(null_index) == 0:
        return mat
    del ia

    tmat = null_mat[:, null_index]
    smat = np.cumsum(tmat, axis=0) * tmat
    nmat = np.diff(smat, n=1, axis=0)

    ic = np.argwhere(nmat < 0)
    ia, ib = ic[:, 0], ic[:, 1]
    uib = np.unique(ib)

    good_index = np.array([])
    for i in range(len(uib)):
        vec = smat[ia[ib == uib[i]], uib[i]]
        tmpmax = np.max(np.concatenate(([vec[0]], np.diff(vec, axis=0)), axis=0))
        if tmpmax <= max_multi_day:
            good_index = np.append(good_index, null_index[uib[i]])
    if np.size(good_index) > 0:
        bad_index = np.setdiff1d(np.arange(mat.shape[1]), good_index)
        null_mat[:, bad_index] = 0
        mat[null_mat == 1] = value
    return mat


def daily_to_rolling_returns(ret, horizon):
    result = ret

    if not isinstance(horizon, (int, float)):
        return result
    result['values'] = multi_day_return(ret['values'], 5)
    log_returns = np.log(1 + result['values'])
    period_log_returns = moving_sum(log_returns, horizon)
    result['values'] = np.exp(period_log_returns) - 1
    return result


def moving_sum(mat, window=None, exclude_nan=None):
    result = np.full(mat.shape, np.nan)

    if window is None or not isinstance(window, (int, float)):
        window = 1

    if exclude_nan is None or not isinstance(exclude_nan, bool):
        exclude_nan = False

    if exclude_nan:
        mat[np.isnan(mat)] = 0

    if window == 1 or mat.shape[0] < window:
        result = mat
        return result

    for i in range(mat.shape[0]):
        result[i, ] = np.sum(mat[max(0, i - window):i, ], axis=0)

    return result


def maximum_drawdown(ret):
    """
    compute maximum drawdowns
    :param ret:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    r = ret.to_numpy()
    cr = np.nancumprod(1+r)
    cm = np.maximum.accumulate(cr)
    dd = (cr - cm) / cm
    max_dd = np.min(dd)
    e_index = np.argmin(dd)
    if e_index == 0:
        periods = np.array([None, None])
        duration = None
        return max_dd, periods, duration
    s_index = np.argmax(cr[:e_index])
    periods = np.array([ret.index[s_index], ret.index[e_index]])
    duration = e_index - s_index + 1
    return max_dd, periods, duration


def maximum_drawdown_relative(ret, ben=None):
    """
    compute maximum drawdowns
    :param ret:
    :param ben: [optional] None
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: January 13, 2023
    """
    if ben is None:
        ben = pd.DataFrame(0.0, index=ret.index)
    r = ret.to_numpy()
    b = ben.to_numpy()
    cr = np.nancumprod(1+r)
    cb = np.nancumprod(1+b)
    cc = cr / cb
    cm = np.maximum.accumulate(cc)
    dd = (cc - cm) / cm
    max_dd = np.min(dd)
    e_index = np.argmin(dd)
    if e_index == 0:
        periods = np.array([None, None])
        duration = None
        return max_dd, periods, duration
    s_index = np.argmax(cc[:e_index])
    periods = np.array([ret.index[s_index], ret.index[e_index]])
    duration = e_index - s_index + 1
    max_dd = np.prod(1+r[s_index:e_index + 1]) - np.nanprod(1+b[s_index:e_index + 1])
    return max_dd, periods, duration


def group_ranks(df, univ_weights=None, grouping_factor=None,
                bus_day=None, min_count=5):
    """

    :param df: columns are securities, one row of data
    :param univ_weights: columns are securities that belong to a universe, one row of weights
    :param grouping_factor: string, such as 'COSMOS_SECTOR'
    :param bus_day:
    :param min_count:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if min_count is None or not isinstance(min_count, numbers.Number) or min_count < 0:
        min_count = 5

    if grouping_factor is not None and not isinstance(grouping_factor, (str, root.GROUP)):
        grouping_factor = None

    if grouping_factor is not None and bus_day is None:
        raise Exception('Must provide a valid business date')

    if univ_weights is None:
        univ_weights = pd.DataFrame(1, index=df.index, columns=['values'])
    univ_sec_ids = univ_weights.index
    all_sec_ids = df.index
    # all data
    vf = pd.DataFrame(np.nan, columns=['values'], index=df.index)
    vf.update(df)
    # universe data
    uf = pd.DataFrame(index=univ_sec_ids)
    uf['values'] = np.nan
    uf['weights'] = univ_weights['values'].to_numpy()
    uf.update(vf)
    uf['wv'] = uf['values'] * uf['weights']
    uf.loc[pd.isnull(uf['wv']), 'weights'] = np.nan
    uf['count'] = 1
    ranks = pd.DataFrame(index=df.index, columns=['universe'])
    vr = np.vectorize(lambda x: ss.percentileofscore(uf['values'][pd.notnull(uf['values'])], x))(vf['values'])
    ranks.loc[df.index, 'universe'] = vr
    del vr
    if grouping_factor is not None:
        group = root.load_object(grouping_factor)
        classification = group.classification
        levels = group.levels
        for level in levels:
            level = level.strip().lower()
            ranks[level] = np.nan
            try:
                mapping = md.get_classification(all_sec_ids, level,
                                                source=classification,
                                                as_of=bus_day, vector_flag=True)
                mapping.drop(columns=['value'], inplace=True)
                vf[level] = np.nan
                vf.update(mapping)
                uf[level] = np.nan
                uf.update(mapping)

                vg = vf.groupby(level)
                ug = uf.groupby(level)
                groups = ug.groups
                # iterate through groups
                for g in groups:
                    vv = vg.get_group(g)
                    uv = ug.get_group(g)
                    vr = np.vectorize(lambda x: ss.percentileofscore(uv['values'][pd.notnull(uv['values'])], x))\
                        (vv['values'])
                    ranks.loc[vv.index, level] = vr
                    del (vv, uv, vr)
            except Exception as e:
                print(e)
                warnings.warn(f"Unable to adjust at level: {level.strip().lower()}")

    return ranks


def fill_na_by_group(mf, df, bus_day=None):
    if pd.isnull(mf).sum().sum() == 0:
        return mf
    sec_ids = df.index.to_numpy()
    vec = df.to_numpy()
    if bus_day is None:
        bus_day = util.today()
    obj = root.load_object('QSR_INDGRP')
    missing = mf.index.to_numpy()
    group = obj.load_exposures(bus_day, missing)
    g_stats = group_stats(sec_ids, vec, obj.name, bus_day)
    for s in group.index:
        ix = np.where(group.loc[s] == 1)[0]
        if len(ix) == 0:
            continue
        g = group.columns[ix]
        mf.loc[s] = g_stats.loc['median', g].to_numpy()
    if pd.isnull(mf).sum().sum() == 0:
        return mf
    # sector
    obj = root.load_object('QSR_SECTOR')
    missing = mf.index[np.where(pd.isnull(mf))[0]].to_numpy()
    group = obj.load_exposures(bus_day, missing)
    g_stats = group_stats(sec_ids, vec, obj.name, bus_day)
    for s in group.index:
        ix = np.where(group.loc[s] == 1)[0]
        if len(ix) == 0:
            continue
        g = group.columns[ix]
        mf.loc[s] = g_stats.loc['median', g].to_numpy()
    if pd.isnull(mf).sum().sum() == 0:
        return mf
    missing = mf.index[np.where(pd.isnull(mf))[0]].to_numpy()
    mf.loc[missing] = g_stats.loc['median', 'universe']
    return mf


def values_to_ordinals(values, delimiter_flag=True, delimiters=None, right_include=False):
    """
    convert actual values to ordinal numbers
    :param values:
    :param delimiter_flag:
    :param delimiters:
    :param right_include:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if isinstance(values, numbers.Number):
        values = np.array([values])
    if values.ndim == 1:
        values = values.reshape((len(values), 1))
    result = np.full(values.shape, np.nan)
    if delimiter_flag:
        if delimiters is None:
            print(f"No valid delimiters")
            return result
        if isinstance(delimiters, numbers.Number):
            delimiters = np.array([delimiters])
        if isinstance(delimiters, list):
            delimiters = np.array(delimiters)
        delimiters = np.unique(delimiters)
        delimiters.sort()
        for ix, d in enumerate(delimiters):
            for j in range(values.shape[1]):
                if right_include:
                    index = np.where(values[:, j] <= d)[0]
                else:
                    index = np.where(values[:, j] < d)[0]
                if len(index) == 0:
                    continue
                if ix > 0:
                    if right_include:
                        index = np.intersect1d(index, np.where(values[:, j] > delimiters[ix-1])[0])
                    else:
                        index = np.intersect1d(index, np.where(values[:, j] >= delimiters[ix-1])[0])
                if len(index) == 0:
                    continue
                result[index, j] = ix
                if ix == len(delimiters) - 1:
                    if right_include:
                        index = np.where(values[: j] > d)
                    else:
                        index = np.where(values[:, j] >= d)
                    result[index, j] = ix + 1
    else:
        if delimiters is None:
            buckets = 10
        else:
            if not isinstance(delimiters, numbers.Number):
                print(f"Number of buckets need be empty or an integer")
                return result
            if delimiters <= 0:
                print(f"number of buckets need be greater than zero")
                return result
            buckets = delimiters
        for ix in range(buckets):
            for j in range(values.shape[1]):
                left_demarcate = np.nanpercentile(values[:, j], ix / buckets * 100)
                right_demarcate = np.nanpercentile(values[:, j], (ix + 1)/buckets * 100)
                if ix == buckets - 1:
                    if right_include:
                        index = np.where(values[:, j] > left_demarcate)[0]
                    else:
                        index = np.where(values[:, j] >= left_demarcate)[0]
                elif ix == 0:
                    if right_include:
                        index = np.where(values[:, j] <= right_demarcate)[0]
                    else:
                        index = np.where(values[:, j] < right_demarcate)[0]
                else:
                    if right_include:
                        index = np.where(values[:, j] <= right_demarcate)[0]
                        index = np.intersect1d(index, np.where(values[:, j] > left_demarcate)[0])
                    else:
                        index = np.where(values[:, j] < right_demarcate)[0]
                        index = np.intersect1d(index, np.where(values[:, j] >= left_demarcate)[0])
                result[index, j] = ix
    return result


def remove_from_composites(portfolios, composite_universe='US_COMPOSITES', save_flag=False):
    obj = root.load_object(composite_universe)
    file = os.path.join(obj.descriptor_location, 'POSITIONS.qd')
    data = util.load_data(file)
    if isinstance(portfolios, str):
        portfolios = np.array([portfolios])
    ix = np.where(~np.isin(data['sec_ids'], portfolios))[0]
    iy = np.where(np.isin(data['sec_ids'], portfolios))[0]
    if len(iy) == 0:
        print(f"{portfolios[0]} etc not fond in {composite_universe}")
        return data
    original = len(data.index)
    data = data.iloc[ix, :]
    after = len(data.index)
    print(f"expunged: {original-after} from {after} records")
    if save_flag:
        util.save_data(data, file)
        print(f"Overwritten {composite_universe} with {after} records")
    return data


def add_composites(composites, lives=None, composite_universe=None, save_flag=False):
    """

    :param composites:
    :param lives:
    :param composite_universe:
    :param save_flag:
    :return:
    """
    if composites is None:
        return False
    if isinstance(composites, str):
        composites = np.array([composites])
    elif isinstance(composites, list):
        composites = np.array(composites)
    if len(composites) == 0:
        print(f"No valid composites provided")
        return False
    if composite_universe is None:
        composite_universe = 'US_COMPOSITES'
    obj = root.load_object(composite_universe)
    if obj is None:
        print(f"composite universe {composite_universe} not recognized")
        return False
    file = os.path.join(obj.descriptor_location, 'POSITIONS.qd')
    data = util.load_data(file)
    if lives is None:
        from_dt = 19000101
        to_dt = 99991231
    else:
        from_dt = lives[0]
        to_dt = lives[1]
    source = 'quasar'
    from_dt = util.parse_date(from_dt)
    to_dt = util.parse_date(to_dt)
    df = pd.DataFrame(columns=['sec_ids', 'values', 'from_dt', 'to_dt', 'source'])
    for comp in composites:
        o = root.load_object(comp)
        if o is None:
            print(f"{comp} is not recognized, skipping")
            continue
        if (data['sec_ids'] == comp).sum() > 0:
            print(f"{comp} pre-existing; skipping")
            continue
        cf = pd.DataFrame(index=[0],columns=df.columns)
        cf['sec_ids'] = comp
        cf['values'] = 1.0
        cf['from_dt'] = from_dt
        cf['to_dt'] = to_dt
        cf['source'] = source
        df = df.append(cf, ignore_index=True)
    if not data.empty:
        data = data.append(df)
    if save_flag:
        util.merge_and_save_data(file, df, ['sec_ids', 'source'], save_flag, value_keys=['values', 'from_dt', 'to_dt'])
        print(f"{util.current_time()}:  Appended {len(df.index)} to {composite_universe}")
    return data


def peak_to_trough(ret):
    """
    rolling peak to trough performance
    :param ret: data series/frame, numpy array
    :return: data series/frame or numpy

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    cr = np.cumprod(1+ret, axis=0)
    cm = np.maximum.accumulate(cr)
    df = cr / cm - 1
    return df


def exclude_high_low(x, high=0, low=0):
    if high == 0 & low == 0:
        return x
    if np.size(x) == 0 or np.sum(~np.isnan(x)) == 0:
        return x
    z = np.sort(x[~np.isnan(x)])
    if high > 0:
        z_high = z[-(min(len(z), high))]
        x[x >= z_high] = np.nan
    if low > 0:
        z_low = z[min(len(z), low) - 1]
        x[x <= z_low] = np.nan
    return x
