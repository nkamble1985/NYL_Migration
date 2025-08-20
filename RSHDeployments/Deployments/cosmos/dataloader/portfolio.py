#
# portfolio loaders
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
import functools as ft
import numpy as np
import pandas as pd
import warnings
import classes.root as root
import os
from util.intersect import *
import util.utilities as util
import util.routines as rt
from util.utilities import display
import numbers
import dataloader.market_data as md
import sys
import dataloader.ma as ma


cache = {}
weights = {}


def get_positions(start_date, end_date, portfolio, calendar_str='US',
                  forward_fill_days=0, recurse=False):
    """
    get positions
    :param start_date:
    :param end_date:
    :param portfolio:
    :param calendar_str:
    :param forward_fill_days:
    :param recurse:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 1, 2021

    """
    if start_date is None:
        display(f"start date is invalid")
        return False

    if end_date is None:
        display(f"start date is invalid")
        return False

    if forward_fill_days is None:
        forward_fill_days = 0

    if calendar_str is None or not isinstance(calendar_str, str):
        calendar_str = 'US'
    if len(calendar_str) == 0:
        calendar_str = 'US'

    bus_days = util.load_business_days(calendar_str, start_date, end_date)
    if len(bus_days) == 0:
        display(f"No valid business days: {calendar_str} calendar")
        return None
    if forward_fill_days > 0:
        all_days = util.load_business_days(calendar_str, [], end_date)
        idx = np.where(all_days == bus_days[0])[0][0]
        position_days = all_days[idx - forward_fill_days:]
    else:
        position_days = bus_days
    if isinstance(portfolio, numbers.Number):
        df = md.get_positions(bus_days[0], bus_days[-1], portfolio, calendar_str=calendar_str,
                              forward_fill_days=forward_fill_days)
        return df
    cashes = md.get_cash_securities()
    if portfolio.upper().strip() in cashes:
        df = pd.DataFrame(1.0, index=bus_days, columns=[portfolio.upper().strip()])
        return df
    por = root.load_object(portfolio)
    location = por.descriptor_location
    if len(location) == 0 or not util.exists(location) or not por.position_file:
        if hasattr(por, 'get_positions'):
            df = por.get_positions(position_days[0], position_days[-1])
            return df
        else:
            warnings.warn(f"Position Location Not Found")
        return None
    # check if the portfolio has differential position files, if it does exist use that
    file = os.path.join(location, f"POSITIONS.qd")
    if util.exists(file):
        try:
            data = util.load_data(file)
            index = np.where(np.logical_and(data['from_dt'] <= position_days[-1], data['to_dt'] >= position_days[0]))[0]
            data = data.iloc[index, :]
            del index
            df = pd.DataFrame(0.0, index=position_days, columns=np.unique(data['sec_ids']))
            for d in position_days:
                index = np.where(np.logical_and(data['from_dt'] <= d, data['to_dt'] >=d))[0]
                if len(index) == 0:
                    continue
                c, i1, i2 = intersect(df.columns, data['sec_ids'].iloc[index])
                df.loc[d, c] = data['values'].iloc[i2].to_numpy()
            return df
        except ValueError as e:
            display(e)
    # if no differential position file, load day by day
    df = pd.DataFrame()
    for i, d in enumerate(position_days):
        file = os.path.join(location, f"{d.strftime( util.yyyymmdd_format)}.qd")
        if not util.exists(file):
            display(f"{d.strftime(util.MM_DD_YY_format)}: {por.name} position file missing")
            tf = pd.DataFrame(index=[d])
        else:
            data = util.load_data(file)
            g_index = np.where(pd.notnull(data['values']))[0]
            data = data.iloc[g_index]
            tf = pd.DataFrame(data[['values']].to_numpy().T, index=[d], columns=data['sec_ids'].to_list())
        df = pd.concat([df, tf], axis=0)
    if forward_fill_days is not None and forward_fill_days > 0:
        df.fillna(method='pad', limit=forward_fill_days, inplace=True)
        df = df.loc[bus_days]
    df[pd.isnull(df)] = 0
    return df


def get_portfolio_weights(start_date, end_date, portfolio, calendar_str='US',
                          weight_flag=None, forward_fill_days=0,
                          recurse=False, composite_flag=False, deep=False):
    """
    get positions
    :param start_date:
    :param end_date:
    :param portfolio:
    :param calendar_str:
    :param weight_flag=None
    :param forward_fill_days: 0
    :param recurse: False
    :param composite_flag: False
    :param deep: False
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 1, 2021
    """

    if start_date is None:
        display(f"start date is invalid")
        return False

    if end_date is None:
        display(f"start date is invalid")
        return False

    if calendar_str is None or not isinstance(calendar_str, str):
        calendar_str = 'US'
    if len(calendar_str) == 0:
        calendar_str = 'US'

    wt_type = get_weight_type(portfolio)
    if weight_flag is None or not isinstance(weight_flag, str):
        weight_flag = get_default_weighting_method(portfolio)
        unspecified = True
    else:
        if wt_type.upper() in ('WEIGHT', 'WEIGHTS', 'WTS', 'WT'):
            unspecified = True   # if weight type is 'WEIGHT', ignore weight_flag
        else:
            unspecified = False
    weight_flag = weight_flag.strip()

    bus_days = util.load_business_days(calendar_str, start_date, end_date)
    if len(bus_days) == 0:
        display(f"No valid business days: {calendar_str} calendar")
        return None
    if not composite_flag and isinstance(portfolio, str):
        cashes = md.get_cash_securities()
        if portfolio.upper().strip() in cashes:
            df = pd.DataFrame(1.0, index=bus_days, columns=[portfolio.upper().strip()])
            return df
        p_obj = root.load_object(portfolio)
        if p_obj is not None:
            if hasattr(p_obj, 'security_type'):
                if p_obj.security_type.upper().strip() == 'PORTFOLIO':
                    composite_flag = True
    positions = get_positions(bus_days[0], bus_days[-1], portfolio,
                              calendar_str, forward_fill_days=forward_fill_days,
                              recurse=recurse)
    if unspecified and wt_type.upper() in ('WEIGHT', 'WEIGHTS', 'WTS', 'WT'):
        weights = positions
    else:
        if weight_flag.upper() not in util.WEIGHTING_SCHEMES and weight_flag not in util.WEIGHT_FACTORS:
            warnings.warn(f'Unsupported weighting scheme: {weight_flag}')
            return None
        weights = calculate_weights(positions, weight_flag, composite_flag=composite_flag)

    if recurse:
        if composite_flag:
            portfolios = weights.columns.to_numpy()
            sec_ids = np.array([])
            wts = {}
            for ix, p in enumerate(portfolios):
                wt = get_portfolio_weights(weights.index[0], weights.index[-1], p,
                                           calendar_str=calendar_str, recurse=deep)
                sec_ids = np.union1d(sec_ids, wt.columns.to_numpy())
                wts[p] = wt
            expanded = {}
            for ix, p in enumerate(portfolios):
                df = pd.DataFrame(0.0, index=weights.index, columns=sec_ids)
                w = wts[p]
                c = df.columns.intersection(w.columns)
                df.loc[df.index, c] = w.loc[df.index, c]
                df[pd.isnull(df)] = 0.0
                expanded[p] = df
            full = pd.DataFrame(0.0, index=weights.index, columns=sec_ids)
            for d in full.index:
                for c in weights.columns:
                    w = weights.loc[d, c]
                    if w == 0:
                        continue
                    full.loc[d] = full.loc[d] + w * expanded[c].loc[d]
            full[pd.isnull(full)] = 0.0
            weights = full
    return weights


def is_weight_type(data):
    if 'type' in data:
        if isinstance(data['type'], (list, np.ndarray)) and len(data['type']) == 1:
            if 'Weight' in data['type'][0]:
                return True
            else:
                return False
        else:
            if isinstance(data['type'], str):
                if 'Weight' in data['type']:
                    return True
                else:
                    return False


def get_position_dates(acct):
    """
    get list of dates for internal portfolios, others it will be empty
    :param acct:
    :return:

    Example:
        Input:
            get_position_dates('US100')
        Output:
            ([datetime.date(2018, 12, 31),...., dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if isinstance(acct, int):
        return np.array([])

    acct = root.load_object(acct)
    directory = acct.descriptor_location
    days = util.parse_date(util.get_files(directory, '.qd', strip_extension=True))
    return days[pd.notnull(days)]


# deprecated
def get_weights(wt_type, start_date=None, end_date=None, sec_ids=None, universe=None, calendar_str=None,
                wt_low=None, wt_high=None, alt_universe=None, month_end_flag=None, fwd_fill_days=None):
    """

    :param wt_type: [optional] string, default 'equal'
    :param start_date: start_date: datetime object or integer
    :param end_date: start_date: datetime object or integer
    :param sec_ids:  ndarray, strings
    :param universe: string, universe identifider
    :param alt_universe: string, universe identifider
    :param calendar_str: string, default 'GL'
    :param wt_low: [optional] double, default 0.0
    :param wt_high: [optional] double, default 100.0
    :param month_end_flag: [optional] logical, default False;
                            if True, return only
    :param fwd_fill_days: [optional] integer
    :return: structure:
            .dates
            .ccyymmdd
            .sec_ids
            .values: list of objects, each element is a structure with fields:
                                .dates
                                .ccyymmdd
                                .sec_ids
                                .values: array of security weights
            .wt_type: string
    """

    # weights on each day need to be winsorized using wt_low and wt_high as the lower/uppre bounds
    # one of sec_ids and universe can be None; if both are not None, use get_positions
    # to get the securities in universe, and merge them with sec_ids
    # forward filling will be performed on the data frequency

    if not isinstance(wt_type, str):
        wt_type = 'EQUAL'
    wt_type = wt_type.strip()

    weight_object = root.load_object(wt_type)
    if weight_object is None:
        raise Exception('Cannot find corresponding weight object %s' % wt_type)

    if sec_ids is None:
        sec_ids = np.array([])
    elif isinstance(sec_ids, (numbers.Number, str)):
        sec_ids = np.array([sec_ids])
    elif isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    else:
        sec_ids = np.array([])

    if not isinstance(universe, str):
        universe = None
    if not isinstance(alt_universe, str):
        alt_universe = None

    if np.size(sec_ids) == 0 and (universe is None and alt_universe is None):
        warnings.warn('No sec_ids or universe')
        return

    if calendar_str is None or not isinstance(calendar_str, str):
        calendar_str = 'GL'
    if wt_low is None or not isinstance(wt_low, numbers.Number):
        wt_low = 0
    if wt_high is None or not isinstance(wt_high, numbers.Number):
        wt_high = 100
    if wt_low > wt_high:
        raise Exception('Lower bound for weight winsorization is higher than'
                        + 'upper bound')
    if wt_high < 0 or wt_low > 100:
        raise Exception('no valid weight winsorization bounds')
    if month_end_flag is None or not isinstance(month_end_flag, bool):
        month_end_flag = False
    if fwd_fill_days is None or not isinstance(fwd_fill_days, numbers.Number):
        fwd_fill_days = 0
        if hasattr(weight_object, 'fwd_fill_days'):
            fwd_fill_days = weight_object.forward_fill_days

    # calendar
    all_bus_days = util.load_business_days(calendar_str)
    discrete_dates_flag = False

    if start_date is not None and end_date is not None:
        if month_end_flag:
            bus_days = util.load_business_days(calendar_str, start_date, end_date, 'MONTHEND')
            discrete_dates_flag = True
        else:
            bus_days = util.load_business_days(calendar_str, start_date, end_date)
    else:
        if start_date is None and end_date is not None:
            bus_days = np.intersect1d(end_date, all_bus_days)
        else:
            bus_days = np.intersect1d(start_date, all_bus_days)
        discrete_dates_flag = True

    if len(bus_days) == 0:
        warnings.warn('No valid business days according to %s calendar' % calendar_str)
        return None
    # universe
    all_sec_ids = sec_ids
    if universe is not None:
        try:
            if discrete_dates_flag:
                univ = get_positions(bus_days, None, universe, calendar_str)
            else:
                # univ = get_positions(bus_days[0], bus_days[-1], universe, calendar_str)
                univ = get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
            all_sec_ids = np.union1d(all_sec_ids, univ.columns)
        except ValueError:
            raise Exception('Unable to load universe %s in weight generation' % universe)
    else:
        univ = None

    if alt_universe is not None:
        try:
            if discrete_dates_flag:
                alt_univ = get_positions(bus_days, None, alt_universe, calendar_str)
            else:
                alt_univ = get_cached_positions(bus_days[0], bus_days[-1], alt_universe, calendar_str)
            all_sec_ids = np.union1d(all_sec_ids, alt_univ.columns)
        except ValueError:
            raise Exception('Unable to load universe %s' % alt_universe)

    if len(all_sec_ids) == 0:
        warnings.warn('No valid securities')
        return None

    try:
        if discrete_dates_flag:
            wts = weight_object.load_values('DESCRIPTOR', bus_days, None, all_sec_ids, None, calendar_str)
        else:
            wts = weight_object.load_values('DESCRIPTOR', bus_days[0], bus_days[-1], all_sec_ids, None,
                                            calendar_str, None, fwd_fill_days)
    except ValueError:
        raise Exception('Unable to load market cap: %s')

    for i, d in enumerate(bus_days):

        if univ is not None:
            univ_ids = univ.columns[np.where(univ.loc[d] > 0)[0]]
        else:
            univ_ids = wts.columns
        univ_vec = wts.loc[d].iloc[np.where(wts.columns.isin(univ_ids))[0]].to_numpy()
        all_vec = wts.loc[d].to_numpy()
        univ_vec_w, all_vec_w = rt.winsorize(univ_vec, wt_low, wt_high, all_vec)
        wts.loc[d] = all_vec_w

    num_of_complex = np.iscomplex(wts).sum().sum()
    if num_of_complex > 0:
        warnings.warn(f'between {wts.index[0].strftime(util.MM_DD_YY_format)}'
                      f' and {wts.index[-1].strftime(util.MM_DD_YY_format)}'
                      f' for {wt_type}: {num_of_complex} '
                      f'securities have complex weights: setting NaN')
        ufa = wts.to_numpy()
        ufa[np.iscomplex(ufa)] = np.nan
        wts = pd.DataFrame(np.real(ufa), index=wts.index, columns=wts.columns)
        del ufa
    return wts


def calculate_weights(por, wt_flag=None, calendar_str=None, forward_fill_days=None, composite_flag=False):
    """
    calculate weights based on position history
    :param por: dataframe, dates as index, securities as columns
    :param wt_flag:
    :param calendar_str:
    :param forward_fill_days:
    :param composite_flag: False
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if wt_flag is None or not isinstance(wt_flag, str):
        wt_flag = 'NAV'

    wt_flag = wt_flag.strip()
    if wt_flag.upper() not in util.WEIGHTING_SCHEMES and wt_flag not in util.WEIGHT_FACTORS:
        raise Exception('Unsupported weighting scheme %s' % wt_flag)

    if calendar_str is None or not isinstance(calendar_str, str):
        calendar_str = 'GL'

    if forward_fill_days is None or not isinstance(forward_fill_days, (int, float)):
        forward_fill_days = 0

    result = pd.DataFrame(np.zeros_like(por.to_numpy()), index=por.index, columns=por.columns)

    if por.empty:
        display(f'Emtpy holdings returned: {wt_flag}')
        return result
    if wt_flag == 'EQUAL':
        result[por != 0] = 1
        # normalizing
        multiplier = pd.concat([1/result.sum(axis=1)] * por.shape[1], axis=1)
        result = pd.DataFrame(result.to_numpy() * multiplier.to_numpy(), index=result.index, columns=result.columns)
        return result
    elif wt_flag in util.WEIGHT_FACTORS:
        obj = root.load_object(wt_flag)
        mkt_cap = obj.load_values('DESCRIPTOR', por.index[0], por.index[-1],
                                  por.columns.to_numpy(), calendar_str=calendar_str,
                                  fwd_fill_days=forward_fill_days, composite_flag=composite_flag)
        result.update(mkt_cap.astype('float64'))
        result[por == 0] = 0
        result[pd.isnull(result)] = 0
        multiplier = pd.concat([1/result.sum(axis=1)] * por.shape[1], axis=1)
        result = pd.DataFrame(result.to_numpy() * multiplier.to_numpy(), index=result.index, columns=result.columns)
    elif wt_flag in ('MARKETCAP', 'MARKET_CAP', 'MARKET_CAPITALIZATION'):
        mkt_cap, m_local, exc, ccy = md.get_market_cap(por.index[0], por.index[-1], por.columns.to_numpy(),
                                                       calendar_str=calendar_str, base_currency='USD')
        result.update(mkt_cap.astype('float64'))
        result[por == 0] = 0
        result[pd.isnull(result)] = 0
        multiplier = pd.concat([1 / result.sum(axis=1)] * por.shape[1], axis=1)
        result = pd.DataFrame(result.to_numpy() * multiplier.to_numpy(), index=result.index, columns=result.columns)
    else:
        prices = md.get_prices(por.index[0], por.index[-1], por.columns.to_numpy(), calendar_str=calendar_str,
                               fwd_fill_days=forward_fill_days)
        # skip leverage multipliers for derivatives
        result.update(prices)
        result = result * por
        result = generate_weights(result, wt_flag)

    display(f'Finished computing weights {wt_flag} '
            f'from {por.index[0].strftime(util.YY_MM_DD_format)} '
            f'to {por.index[-1].strftime(util.YY_MM_DD_format)}')
    return result


def generate_weights(market_values, wt_flag=None, sec_ids=None, bus_day=None):
    """
    given market value, weight flag, create weight matrix
    :param market_values:
    :param wt_flag:
    :param sec_ids:
    :param bus_day:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if wt_flag is None or not isinstance(wt_flag, str):
        wt_flag = 'NAV'
    wt_flag = wt_flag.strip()
    if wt_flag.upper() not in util.WEIGHTING_SCHEMES and wt_flag not in util.WEIGHT_FACTORS:
        raise Exception('Unsupported weighting scheme %s' % wt_flag)

    # skip levered products
    result = market_values.copy(deep=True)
    result[pd.isnull(result)] = 0

    if wt_flag in ['NAV', 'NAV_EX_CASH']:
        # normalizing
        multiplier = pd.concat([1/result.sum(axis=1)] * market_values.shape[1], axis=1)
    elif wt_flag in ['LONG_ONLY']:
        multiplier = pd.concat([1 / result[result>0].sum(axis=1)] * market_values.shape[1], axis=1)
        multiplier[result < 0] = 0
    elif wt_flag in ['EQUAL']:
        multiplier = pd.concat([1 / result[result!=0].sum(axis=1)] * market_values.shape[1], axis=1)
    elif wt_flag in ['LONG_SHORT']:
        multiplier = pd.concat([1 / result[result > 0].sum(axis=1)] * market_values.shape[1], axis=1)
    else:
        raise Exception(f"Unsupported weight flag {wt_flag}")
    result = pd.DataFrame(result.to_numpy() * multiplier.to_numpy(), index=result.index, columns=result.columns)
    return result


def compute_returns(start_date, end_date, portfolio, wt_flag='NAV', calendar_str='US',
                    weight_forward_fill_days=0):
    """
    compute daily returns for a portfolio
    :param start_date:
    :param end_date:
    :param portfolio:
    :param wt_flag:
    :param calendar_str:
    :param weight_forward_fill_days:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    bus_days = util.load_business_days(calendar_str, start_date, end_date)
    por_days = util.previous_business_days(bus_days, calendar_code=calendar_str)
    por = get_portfolio_weights(por_days[0], por_days[-1], portfolio, calendar_str=calendar_str,
                                weight_flag=wt_flag, forward_fill_days=weight_forward_fill_days)
    ret = md.get_returns(bus_days[0], bus_days[-1], por.columns.to_numpy(), calendar_str=calendar_str)
    result = w_prime_r(por, ret, calendar_str)
    return result.to_frame(portfolio)


def w_prime_r(por, ret, calendar_str='GL', normalize=True):
    """
    weight times return, contribution calculator
    :param por:
    :param ret:
    :param calendar_str:
    :param normalize:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if normalize is None:
        normalize = True
    ret = align_portfolio_and_return(por, ret, calendar_str)
    w = por.reset_index(drop=True)
    r = ret.reset_index(drop=True)
    w_x_r = w * r
    w_ = pd.DataFrame(np.zeros_like(w_x_r), columns=w_x_r.columns)
    w_.update(w)
    w_[pd.isnull(w_x_r)] = 0
    w_[pd.isnull(w_)] = 0
    w_x_r_mat = w_x_r.to_numpy()
    w_mat = w_.to_numpy()
    if normalize:
        multiplier = 1 / w_mat.sum(axis=1)
        multiplier = multiplier.reshape((len(multiplier), 1))
    else:
        multiplier = np.ones((w_x_r_mat.shape[0], 1))
    multiplier = np.repeat(multiplier, w_x_r_mat.shape[1], axis=1)
    result = w_x_r_mat * multiplier
    result = pd.Series(np.nansum(result, axis=1), index=ret.index)
    return result


def active_portfolio(managed, benchmark):
    """
    from managed and benchmark holdings (data frames) output active portfolio
    :param managed:
    :param benchmark:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    index = np.union1d(managed.index, benchmark.index)
    sec_ids = np.union1d(managed.columns, benchmark.columns)
    mf = pd.DataFrame(0, index=index, columns=sec_ids)
    mf.update(managed)
    bf = pd.DataFrame(0, index=index, columns=sec_ids)
    bf.update(benchmark)
    df = mf - bf
    df[pd.isnull(df)] = 0
    return df


def split_ls_portfolio(por):
    """
    split a long short portfolios into two parts: long and short portfolios
    :param por:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    result = {'long': None, 'short': None}
    long = por.copy(deep=True)
    short = por.copy(deep=True)
    long[long < 0] = 0
    # exclude zeros for longs
    index = np.where(long.sum(axis=0) > 0)[0]
    long = long.iloc[:, index]

    short[short > 0] = 0
    short = -short
    # exclude zeros for shorts
    index = np.where(short.sum(axis=0) > 0)[0]
    short = short.iloc[:, index]

    result['long'] = long
    result['short'] = short
    return result


def align_portfolio_and_return(por, ret, calendar_str='GL', sec_ids=None):
    if sec_ids is not None:
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        m = np.setdiff1d(sec_ids, por.columns)
        tp = pd.DataFrame(0.0, index=por.index, columns=m)
        por = por.combine_first(tp)
        por = por[sec_ids]
    r_days = util.next_business_days(por.index.to_numpy(), calendar_code=calendar_str)
    missing = np.setdiff1d(por.columns, ret.columns)
    if len(missing) > 0:
        ret[missing] = np.nan
    missing_days = np.setdiff1d(r_days, ret.index)
    if len(missing_days) > 0:
        df = pd.DataFrame(index=r_days, columns=ret.columns)
        common, i1, i2 = intersect(r_days, ret.index)
        df.loc[common] = ret.loc[common]
        ret = df.copy(deep=True)
        del df
    r = ret.loc[r_days, por.columns]
    if sec_ids is not None:
        return r, por
    else:
        return r


def cache_yearly_positions(year, portfolio, calendar_str='US', update_flag=False):
    """
    cache self-defined portfolio by year
    :param year:
    :param portfolio:
    :param calendar_str: default 'US'
    :param update_flag: default False
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    obj = root.load_object(portfolio)
    if obj is None:
        display(f"{portfolio} not self-defined; cannot be file-cached; returning")
        return False
    else:
        output_location = obj.descriptor_location
    file = os.path.join(output_location, f"{year}.qd")
    days = util.load_business_days_by_year(year, calendar_str)
    days = days[days <= util.today()]
    if util.exists(file) and not update_flag:
        por = util.load_data(file)
        missing = np.setdiff1d(days, por.index.to_numpy())
        if len(missing) > 0:
            display(f"{portfolio}: year {year} file cache missing: {missing[0]} - {missing[-1]} loading")
            df = get_positions(missing[0], missing[-1], portfolio, calendar_str)
            df = df.iloc[np.where(np.abs(df).sum(axis=1) > 0)[0], :]
            display(f"loaded {portfolio} : {df.index[0]} - {df.index[-1]}")
            all_sec_ids = np.union1d(por.columns, df.columns)
            dates = np.union1d(por.index, df.index)
            zf = pd.DataFrame(0.0, index=dates, columns=all_sec_ids)
            zf.update(por)
            zf.update(df)
            por = zf
            por[pd.isnull(por)] = 0.0
            if por.index[-1] == util.today():
                por = por.iloc[np.where(np.abs(por).sum(axis=1) > 0)[0], :]
            util.save_data(por, file)
            display(f"Expanded file cache year {year}: {portfolio}: {por.index[0]} - {por.index[-1]}")
    else:
        display(f"{portfolio} cache year {year} doesn't exist: caching...")
        por = get_positions(days[0], days[-1], portfolio, calendar_str)
        por = por.iloc[np.where(np.abs(por).sum(axis=1) > 0)[0], :]
        util.save_data(por, file)
        display(f"{portfolio}: year {year} holdings cached to {file}")
    return por


def get_default_weighting_method(por=None):
    """
    get default weighting method; all fails, 'NAV' is chosen
    :param por:
    :return:
    """
    if por is None or isinstance(por, numbers.Number):
        return 'NAV'
    cashes = md.get_cash_securities()
    if isinstance(por, str):
        if por.upper().strip() in cashes:
            return 'NAV'

    p_obj = root.load_object(por)
    if p_obj is None:
        return 'NAV'
    if hasattr(p_obj, 'weighting_method'):
        return p_obj.weighting_method
    else:
        return 'NAV'


def get_weight_type(por=None):
    if por is None:
        return 'SHARE'
    if isinstance(por, numbers.Number):
        return 'WEIGHT'
    if md.is_cash(por):
        return 'WEIGHT'
    p_obj = root.load_object(por)
    if p_obj is None:
        return 'SHARE'
    if hasattr(p_obj, 'weight_type'):
        return p_obj.weight_type
    else:
        return 'SHARE'


def get_cached_positions(start_date, end_date, portfolio, calendar_str='US',
                         forward_fill_days=0, recurse=False):
    """
    cache positions into memory for faster retrieval
    :param start_date:
    :param end_date:
    :param portfolio:
    :param calendar_str:
    :param forward_fill_days:
    :param recurse:
    :return:

    Author:
    """
    bus_days = util.load_business_days(calendar_str, start_date, end_date)
    if portfolio not in cache:
        missing_days = bus_days
        df = pd.DataFrame()
    else:
        df = cache[portfolio]
        missing_days = np.setdiff1d(bus_days, df.index.to_numpy())
    if len(missing_days) <= 0:
        display(f"{portfolio}: loaded from cache: {bus_days[0]} - {bus_days[-1]}")
    else:
        if isinstance(portfolio, str):
            years = np.unique(util.year(missing_days))
            p_obj = root.load_object(portfolio)
            clock1 = util.clock()
            for y in years:
                file = os.path.join(p_obj.descriptor_location, f"{y}.qd")
                if util.exists(file):
                    data = util.load_data(file)
                    # all_sec_ids = np.union1d(df.columns, data.columns)
                    # all_days = np.union1d(df.index, data.index)
                    # mf = pd.DataFrame(0.0, index=all_days, columns=all_sec_ids)
                    # mf.update(df)
                    # mf.update(data)
                    # df = mf
                    # sanity check
                    overlap = np.intersect1d(df.index, data.index)
                    if len(overlap) > 0:
                        gd = np.setdiff1d(df.index, data.index)
                    else:
                        gd = df.index
                    df = pd.concat((df.loc[gd], data), axis=0)
                    df[pd.isnull(df)] = 0.0
                    cache[portfolio] = df
                    display(f"{portfolio} cache expanded by year: {data.index[0]} - {data.index[-1]}")
                else:
                    display(f"{portfolio}: year {y} not yet cached")
                    continue
            clock2 = util.clock()
            display(f"{p_obj.name}: file cache loaded: {clock2 - clock1: .1} seconds")
            missing_days = np.setdiff1d(bus_days, df.index.to_numpy())
        if len(missing_days) > 0:
            segments = util.day_segments(missing_days, calendar_str)
            for i in segments.index:
                tf = get_positions(segments.loc[i, 'from'], segments.loc[i, 'to'], portfolio, calendar_str,
                                   forward_fill_days, recurse)
                overlap = np.intersect1d(df.index, tf.index)
                if len(overlap) > 0:
                    gd = np.setdiff1d(df.index, tf.index)
                else:
                    gd = df.index
                df = pd.concat((df.loc[gd], tf), axis=0)
                df[pd.isnull(df)] = 0.0
                df.sort_index(ascending=True, inplace=True)
                display(f"Portfolio {portfolio} position loaded for segment: "
                        f"{segments.loc[i, 'from']} - {segments.loc[i, 'to']}")
                cache[portfolio] = df
    result = df.loc[bus_days]
    good_index = np.where(np.sum(np.abs(result.to_numpy()), axis=0) > 0)[0]
    result = result.iloc[:, good_index]
    del good_index
    return result


def clear_cache(portfolio):
    global cache
    if portfolio is None:
        cache = {}
        display('Removed all position cache')
    else:
        if portfolio in cache:
            cache.pop(portfolio)
            display(f'Cleared cache for {portfolio}')
        else:
            display(f'{portfolio} not in cache')
    return True


def get_multiple_portfolios(bus_day, portfolios, wt_flags=None, calendar_str='US', recurse=None, deep=None,
                            benchmark=None, bench_wt_flag=None):
    if isinstance(portfolios, (int, str)):
        portfolios = np.array([portfolios])
    sec_ids = np.array([])
    pf = pd.DataFrame(0.0, index=portfolios, columns=sec_ids)
    if wt_flags is None:
        wt_flags = np.full((len(portfolios), 1), 'NONE')
    else:
        if isinstance(wt_flags, str):
            wt_flags = np.array([wt_flags])
        if len(wt_flags) == 1:
            wt_flags = np.tile(wt_flags, len(portfolios))
        if len(wt_flags) != len(portfolios):
            display(f"get_multiple_portfolios: Weight Flag and Portfolios should match in length")
            raise ValueError
    if benchmark is not None:
        ben = get_portfolio_weights(bus_day, bus_day, benchmark, weight_flag=bench_wt_flag,
                                    calendar_str=calendar_str, recurse=recurse, deep=deep)
        display(f"loaded benchmark: {benchmark}: {len(ben.columns)} securities for {bus_day}")
    else:
        ben = None
    pf = pd.DataFrame(index=portfolios)
    for ix, por in enumerate(portfolios):
        if isinstance(por, str) and root.load_object(por) is None:
            display(f"---> {por} not properly setup, skipping <---")
            continue
        if wt_flags[ix] == 'NONE':
            wt_flag = None
        else:
            wt_flag = wt_flags[ix]
        p = get_portfolio_weights(bus_day, bus_day, por, weight_flag=wt_flag, calendar_str=calendar_str,
                                  recurse=recurse, deep=deep)
        if ben is not None:
            p = active_portfolio(p, ben)
        p.index = np.array([por])
        pf = pf.combine_first(p)
    pf[pd.isnull(pf)] = 0.0
    return pf


def get_turnover(start_date, end_date, portfolio, calendar_str='US', propagate=True, security_type='EQUITY',
                 recurse=False, deep=False):
    por = root.load_object(portfolio)
    if calendar_str is None:
        calendar_str = por.calendar
    bus_days = util.load_business_days(calendar_str, start_date, end_date)
    if len(bus_days) == 0:
        display(f"No valid business days: {calendar_str}")
        return None
    if not isinstance(propagate, bool):
        propagate = False
    if security_type.upper().strip() in ('PORTFOLIO', 'QSR', 'POR'):
        composite_flag = True
    else:
        composite_flag = False
    if hasattr(por, 'rebalance_frequency'):
        reb_days = util.load_business_days(calendar_str, None, end_date, por.rebalance_frequency)
    else:
        reb_days = util.load_business_days(calendar_str, None, end_date, por.descriptor_frequency)
    ix = np.argmax(reb_days > bus_days[0]) - 1
    reb_days = reb_days[ix :]
    old = get_portfolio_weights(reb_days[0], reb_days[0], portfolio, composite_flag=composite_flag,
                                recurse=recurse, deep=deep)
    turnovers = pd.DataFrame(index=reb_days[1:], columns=['values'])
    for i in range(1, len(reb_days), 1):
        new = get_portfolio_weights(reb_days[i], reb_days[i], portfolio, composite_flag=composite_flag,
                                    recurse=recurse, deep=deep)
        if not propagate:
            propagated = old
            propagated.index = new.index
        else:
            ret = md.get_returns(util.next_business_days(reb_days[i-1]), reb_days[i], old.columns.to_numpy(),
                                 calendar_str=calendar_str, security_type=security_type)
            period_returns = np.prod(ret.to_numpy() + 1, axis=0)
            c, i1, i2 = intersect(old.columns, ret.columns)
            multipliers = np.ones((1, len(old.columns)))
            multipliers[0, i1] = period_returns[i2]
            del (c, i1, i2)
            propagated = pd.DataFrame(old.to_numpy() * multipliers, index=new.index, columns=old.columns)
            display(f"{portfolio}: holdings propagated from {reb_days[i-1]} to {reb_days[i]}")
        act = active_portfolio(new, propagated)
        # exclude cash
        turnovers.loc[reb_days[i], 'values'] = max(np.nansum(act[act > 0]), np.nansum(act[act < 0])).sum()
        display(f"{portfolio}: {reb_days[i]} turnover {turnovers.loc[reb_days[i], 'values']*100:.1f} %")
        old = new.copy(deep=True)
    return turnovers


# def propagate_positions(por, dates, weight_type='WEIGHT', security_type='EQUITY', calendar_str='US', normalize=True):
#     """
#
#     :param por:
#     :param dates:
#     :param weight_type:
#     :param security_type:
#     :param calendar_str:
#     :param normalize:
#     :return:
#     """
#     if not isinstance(dates, np.ndarray):
#         dates = np.array([dates])
#     if weight_type not in ['WEIGHT', 'WT', 'WTS', 'WEIGHTS']:
#         display(f"No implemented yet")
#         return None
#     p_day = por.index[0]
#     dates = util.parse_date(dates)
#     dates = np.unique(dates)
#     dates = np.sort(dates)
#     dates = dates[dates > p_day]
#     if len(dates) == 0:
#         display('Nothing to propagate into future')
#         return None
#     s_day = min(util.next_business_days(p_day,calendar_str), dates[0])
#     e_day = dates[-1]
#     sids = por.columns.to_numpy()
#     ret = md.get_returns(s_day, e_day, sids, calendar_str, security_type=security_type)
#     cr = np.nancumprod(1+ret, axis=0)
#     c, i1, i2 = intersect(dates, ret.index)
#     d, i3, i4 = intersect(sids, ret.columns.to_numpy())
#     f_mat = np.zeros((len(dates), len(sids)))
#     f_mat[np.ix_(i1, i3)] = cr[np.ix_(i2, i4)]
#     p0_mat = np.tile(por.iloc[0, :].to_numpy().T, (len(dates), 1))
#     p_mat = p0_mat * f_mat
#     if normalize:
#         p_sums = np.nansum(p_mat, axis=1)
#         for i in range(p_mat.shape[0]):
#             p_mat[i, :] = p_mat[i, :] / p_sums[i]
#     df = pd.DataFrame(p_mat, index=dates, columns=sids)
#     return df

def propagate_weights(por, as_of, start_date, end_date, calendar_str='US', normalize=True):
    """

    Parameters
    ----------
    por: dataframe, 1 x N shape, columns are security regional IDs
    as_of: the date for which the por is valid
    start_date: request start date
    end_date: request end date
    calendar_str: default 'US
    normalize: default True

    Returns
    -------

    """
    days = util.load_business_days(calendar_str, as_of, end_date)
    dates = util.load_business_days(calendar_str, start_date, end_date)
    if len(dates) == 0:
        display(f"No valid business dates requested: {calendar_str}: returning None")
        return None
    df = pd.DataFrame()
    prev_d = util.parse_date(as_of)
    prev_p = por.copy()
    for d in days:
        if d <= prev_d:
            continue
        pf = propagate_weights_1_day(prev_p, prev_d, calendar_str, normalize)
        df = pd.concat((df, pf), axis=0)
        nd = pf.index[0]
        display(f"===========> Propagated from {prev_d} to {nd} <=============")
        prev_p = pf.copy()
        prev_d = nd
    common = np.intersect1d(dates, df.index)
    return df.loc[common]


def propagate_weights_1_day(por, as_of, calendar_str='US', normalize=True):
    """

    Parameters
    ----------
    por
    as_of
    calendar_str: default 'US'
    normalize: default True

    Returns
    -------

    """
    sec_ids = por.columns.to_numpy()
    nd = util.next_business_days(as_of, calendar_str)
    ret = md.get_returns(nd, nd, sec_ids, calendar_str)
    ret.fillna(0, inplace=True)
    ff = pd.DataFrame(0, index=[nd], columns=sec_ids)
    ff.update(ret)
    ff = 1 + ff
    df = pd.DataFrame(por.iloc[[0]].to_numpy(), index=[nd], columns=sec_ids)
    df = df * ff

    # cash and non-cash distributions
    div = md.get_dividends(nd, nd, sec_ids, calendar_str)
    if not div.empty:
        c_sec_id = md.get_cash_securities('USD')  # FactSet quotes all dividend in USD
        c_sec_id = c_sec_id[0]
        if c_sec_id not in df.columns:
            cf = pd.DataFrame(0.0, index=[nd], columns=[c_sec_id])
            df = pd.concat((df, cf), axis=1)
        cash = np.where(div['Spinoff'] == 0)[0]
        spin = np.where(div['Spinoff'] == 1)[0]
        display(f"{as_of} -> {nd}: {len(div.index)} distributions: {len(cash)} cash, {len(spin)} spinoffs")
        bp, lp, exc, cref = md.get_prices(nd, nd, div['sec_ids'], calendar_str, base_currency='USD')
        for ix in cash:
            try:
                s = div.loc[div.index[ix], 'sec_ids']
                d = div.loc[div.index[ix], 'DividendPaid']
                iy = np.where(bp.columns == s)[0]
                if len(iy) == 0:
                    display(f"Error processing cash dividend: {s} on {nd}: missing price")
                    continue
                p = bp.iloc[0, iy[0]]
                tw = df.loc[nd, s]  # total weight that includes cash distribution and issuing stock
                rw = tw * (1 - d/(d + p))
                cw = tw * d / (d + p)
                df.loc[nd, s] = rw
                df.loc[nd, c_sec_id] += cw
                tc = df.loc[nd, c_sec_id]
                display(f"{as_of} -> {nd}: {s} cash dividend USD ${d} (price USD ${p}): "
                        f"{tw:.2%} = {rw: .2%} stock + {cw: .2%} cash; total cash {tc: .2%}")
            except ValueError as ve:
                display(f"{ve}")
                display(f"Due to value error: cannot process {ix}-th cash dividend: {as_of} -> {nd}")
            except Exception as ee:
                display(f"{ee}")
                display(f"Due to exception: cannot process {ix}-th cash dividend: {as_of} -> {nd}")
        parents = div.loc[div.index[spin], 'sec_ids'].to_numpy()
        if len(parents) > 0:
            spun_offs = md.get_spun_offs(nd, parents)
            for ix in spin:
                try:
                    s = div.loc[div.index[ix], 'sec_ids']
                    d = div.loc[div.index[ix], 'DividendPaid']
                    iy = np.where(bp.columns == s)[0]
                    if len(iy) == 0:
                        display(f"Error processing cash dividend: {s} on {nd}: missing price")
                        continue
                    p = bp.iloc[0, iy[0]]
                    tw = df.loc[nd, s]  # total weight that includes cash distribution and issuing stock
                    rw = tw * (1 - d/(d + p))
                    cw = tw * d / (d + p)
                    df.loc[nd, s] = rw
                    iz = np.where(spun_offs['fsym_id'] == s)[0]
                    if len(iz) == 0:
                        df.loc[nd, c_sec_id] += cw
                        tc = df.loc[nd, c_sec_id]
                        display(f"{as_of} -> {nd}: {s} spun_offs non-equity entity, treated as cash USD ${d} "
                                f"(price USD ${p}): {tw:.3%} = {rw: .3%} stock + {cw: .3%} spunoff; "
                                f"total cash {tc: .3%}")
                    else:
                        s_sec_id = spun_offs.loc[spun_offs.index[iz[0]], 'fsym_regional_id']
                        s_name = spun_offs.loc[spun_offs.index[iz[0]], 'spun_off_entity']
                        if s_sec_id in df.columns:
                            df.loc[nd, s_sec_id] += cw
                        else:
                            zf = pd.DataFrame(cw, index=[nd], columns=[s_sec_id])
                            df = pd.concat((df, zf), axis=1)
                        display(f"{as_of} -> {nd}: {s} spun-off {s_sec_id} ({s_name})"
                                f"USD ${d} (price USD ${p}): "
                                f"{tw:.3%} = {rw: .3%} stock + {cw: .3%} spun-off;")
                except ValueError as ve:
                    display(f"{ve}")
                    display(f"Due to value error: cannot process {ix}-th spin off: {as_of} -> {nd}")
                except Exception as ee:
                    display(f"{ee}")
                    display(f"Due to exception: cannot process {ix}-th spin off: {as_of} -> {nd}")
    # M&A
    act = ma.get_processed_merger_acquisitions(nd, nd, df.columns.to_numpy())
    if not act.empty:
        for i in act.index:
            f_sec = act.loc[i, 'from_regional']
            t_sec = act.loc[i, 'to_regional']
            f_name = act.loc[i, 'from_name']
            t_name = act.loc[i, 'to_name']
            role = act.loc[i, 'role']
            ptype = act.loc[i, 'payment_type']
            ptype = ptype.lower().strip()
            deal = act.loc[i, 'deal']
            ccy = act.loc[i, 'currency']
            c_sec = md.get_cash_securities(ccy)
            c_sec = c_sec[0]
            if role == 'buyer':
                if f_sec == t_sec:
                    continue
                else:
                    ws = df.loc[nd, f_sec]
                    if t_sec in df.columns:
                        df.loc[nd, t_sec] += ws
                    else:
                        zf = pd.DataFrame(ws, index=[nd], columns=[t_sec])
                        df = pd.concat((df, zf), axis=1)
                    df.drop(f_sec, axis=1, inplace=True)
                    display(f"{nd}: {deal} ({ptype} deal): buyer {f_sec} --> {t_sec} ({ws: .3%})")
            else:
                if ptype == 'stock':
                    if f_sec == t_sec:
                        continue
                    else:
                        ws = df.loc[nd, f_sec]
                        if t_sec in df.columns:
                            df.loc[nd, t_sec] += ws
                        else:
                            zf = pd.DataFrame(ws, index=[nd], columns=[t_sec])
                            df = pd.concat((df, zf), axis=1)
                        df.drop(f_sec, axis=1, inplace=True)
                        display(f"{nd}: {deal} ({ptype} deal): target {f_sec} --> {t_sec} ({ws: .3%})")
                        display(f"{f_name} --> {t_name}")
                elif ptype == 'cash':
                    wc = df.loc[nd, f_sec]
                    if c_sec in df.columns:
                        df.loc[nd, c_sec] += wc
                    else:
                        zf = pd.DataFrame(wc, index=[nd], columns=[c_sec])
                        df = pd.concat((df, zf), axis=1)
                    df.drop(f_sec, axis=1, inplace=True)
                    display(f"{nd}: {deal} ({ptype} deal): target {f_sec} --> {c_sec} ({wc:.3%})")
                    display(f"{f_name} --> {c_sec}")
                else:
                    cc = act.loc[i, 'cash']
                    ss = act.loc[i, 'stock']
                    pc = cc / (cc + ss)
                    ps = ss / (cc + ss)
                    wc = pc * df.loc[nd, f_sec]
                    ws = ps * df.loc[nd, f_sec]
                    if c_sec in df.columns:
                        df.loc[nd, c_sec] += wc
                    else:
                        zf = pd.DataFrame(wc, index=[nd], columns=[c_sec])
                        df = pd.concat((df, zf), axis=1)
                    if t_sec in df.columns:
                        df.loc[nd, t_sec] += ws
                    else:
                        zf = pd.DataFrame(ws, index=[nd], columns=[t_sec])
                        df = pd.concat((df, zf), axis=1)
                    df.drop(f_sec, axis=1, inplace=True)
                    display(f"{nd}: {deal} ({ptype} deal): target {f_sec} --> {c_sec} ({pc:.1%}: {wc: .3%s}) "
                            f"and {t_sec} ({ps:.1%}: {ws:.3%})")
                    display(f"{f_name} --> {c_sec} + {t_name}")
    df.fillna(0, inplace=True)
    if normalize:
        df = df / np.nansum(df.sum(axis=1))
        display(f"Weights {nd} normalized")
    return df


def upload_holdings(file, save_flag=False):
    """

    :param file:
    :param save_flag:
    :return:
    """
    if not util.exists(file):
        display(f"Not found: {file}")
        display(f"Returning...")
        return False
    df = pd.read_excel(file, header=0)
    for c in df.columns:
        df.rename(columns={c: c.upper().strip()}, inplace=True)
    if 'ACCOUNT' not in df.columns:
        if 'PORTFOLIO' in df.columns:
            df.rename(columns={'PORTFOLIO': 'ACCOUNT'})
        else:
            display(f"Cannot find either ACCOUNT or PORTFOLIO columns")
            return False
    if 'DATE' not in df.columns:
        display(f"Cannot find date column")
        return False
    accounts = np.unique(df['ACCOUNT'])
    data = {}
    for a in accounts:
        data[a] = None
    df['DATE'] = util.parse_date(df['DATE'].to_numpy())
    for p in accounts:
        index = np.where(df['ACCOUNT'] == p)[0]
        if len(index) == 0:
            display(f"{p}: no valid holdings; skipping")
            continue
        z = df.iloc[index]
        days = np.unique(z['DATE'])
        days = np.sort(days)
        sids = np.unique(z['SEC_ID'])
        zf = pd.DataFrame(0.0, index=days, columns=sids)
        for d in days:
            ix = np.where(z['DATE'] == d)[0]
            if len(ix) == 0:
                continue
            s = z.iloc[ix]
            kids = np.unique(s['SEC_ID'])
            for k in kids:
                ik = np.where(s['SEC_ID'] == k)[0]
                v = np.nansum(s['VALUE'].iloc[ik])
                zf.loc[d, k] = v
            display(f"{p}: {d}: {len(kids)} holdings")
        data[p] = zf
        if save_flag:
            obj = root.load_object(p)
            if obj is None:
                display(f"{p}: not defined; skipping")
                continue
            if not util.exists(obj.descriptor_location):
                util.makedirs(obj.descriptor_location)
                display(f"{p}: Created: {obj.descriptor_location}")
            for d in zf.index:
                try:
                    t = zf.loc[d].to_frame()
                    t.reset_index(inplace=True)
                    t.rename(columns={d:'values', 'index': 'sec_ids'}, inplace=True)
                    t['source'] = obj.source
                    t_file = os.path.join(obj.descriptor_location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    util.save_data(t, t_file)
                    display(f"{p}: {d}: {len(t.index)} holdings saved to {t_file}")
                except IOError as ie:
                    display(ie)
                    display(f"Unable to save holdings to {p}")
                except ValueError as ve:
                    display(ve)
                    display(f"Unable to save holdings to {p}")
                except Exception as ee:
                    display(ee)
                    display(f"Unable to save holdings to {p}")
    return data


@ft.lru_cache()
def get_portfolio_group_map():
    file = os.path.join('portfolios', 'portfolio_group_map.qd')
    data = util.load_data(file)
    return data


def map_portfolio_to_group(p):
    result = {'classification': None, 'level': None, 'group': None, 'portfolio': p}
    if p is not None:
        pgm = get_portfolio_group_map()
        index = np.where(pgm['Portfolios'] == p.strip())[0]
        if len(index) > 0:
            if len(index) > 1:
                display(f"{p} has more than one group mapped <====== potential error")
            result['classification'] = pgm['Classifications'].iloc[index[0]]
            result['level'] = pgm['Levels'].iloc[index[0]]
            result['group'] = pgm['Groups'].iloc[index[0]]
            result['portfolio'] = p.strip()
    return result


def split_long_short_portfolio(por, keep_short_sign=False, exclude_cash=False):
    """
    split a portfolio into long and short
    :param por:
    :param keep_short_sign: False
    :param exclude_cash: False
    :return:
    """

    if por is None:
        return None
    if exclude_cash:
        cash = md.get_cash_securities()
        non_cash = np.setdiff1d(por.columns, cash)
        por = por[non_cash]
    long = por.copy()
    short = por.copy()
    long[long < 0] = 0.0
    short[short > 0] = 0.0
    if not keep_short_sign:
        short = -short
    l_index = np.where(long.abs().sum(axis=0) > 0)[0]
    long = long.iloc[:, l_index]
    s_index = np.where(short.abs().sum(axis=0) > 0)[0]
    short = short.iloc[:, s_index]
    return long, short


def get_cached_weights(start_date, end_date, portfolio, calendar_str='US',
                       weight_flag=None, forward_fill_days=0,
                       recurse=False, composite_flag=False, deep=False):
    bus_days = util.load_business_days(calendar_str, start_date, end_date)
    if portfolio not in weights:
        missing_days = bus_days
        df = pd.DataFrame()
    else:
        df = weights[portfolio]
        missing_days = np.setdiff1d(bus_days, df.index.to_numpy())
    if len(missing_days) <= 0:
        display(f"{portfolio}: loaded from weights cache: {bus_days[0]} - {bus_days[-1]}")
    else:
        # years = np.unique(util.year(missing_days))
        # p_obj = root.load_object(portfolio)
        # for y in years:
        #     file = os.path.join(p_obj.descriptor_location, f"{y}.qd")
        #     if util.exists(file):
        #         data = util.load_data(file)
        #         all_sec_ids = np.union1d(df.columns, data.columns)
        #         all_days = np.union1d(df.index, data.index)
        #         mf = pd.DataFrame(0.0, index=all_days, columns=all_sec_ids)
        #         mf.update(df)
        #         mf.update(data)
        #         df = mf
        #         weights[portfolio] = df
        #         display(f"{portfolio} cache expanded by year: {data.index[0]} - {data.index[-1]}")
        #     else:
        #         display(f"{portfolio}: year {y} not yet cached")
        #         continue

        missing_days = np.setdiff1d(bus_days, df.index.to_numpy())
        if len(missing_days) > 0:
            segments = util.day_segments(missing_days, calendar_str)
            for i in segments.index:
                tf = get_portfolio_weights(segments.loc[i, 'from'], segments.loc[i, 'to'], portfolio, calendar_str,
                                           weight_flag, forward_fill_days, recurse, composite_flag, deep)
                all_sec_ids = np.union1d(df.columns, tf.columns)
                all_days = np.union1d(df.index, tf.index)
                mf = pd.DataFrame(0.0, index=all_days, columns=all_sec_ids)
                mf.update(df)
                mf.update(tf)
                df = mf
                display(f"Portfolio {portfolio} weights loaded for segment: "
                      f"{segments.loc[i, 'from']} - {segments.loc[i, 'to']}")
                weights[portfolio] = df
    result = df.loc[bus_days]
    good_index = np.where(np.sum(np.abs(result.to_numpy()), axis=0) > 0)[0]
    result = result.iloc[:, good_index]
    del good_index
    return result


def clear_weights(portfolio=None):
    global weights
    if portfolio is None:
        weights = {}
        display('Removed all weights cache')
    else:
        if portfolio in weights:
            weights.pop(portfolio)
            display(f'Cleared weight cache for {portfolio}')
        else:
            display(f'{portfolio} not in weight cache')
    return True


def get_cached_multiple_portfolios(bus_day, portfolios, wt_flags=None, calendar_str='US', recurse=True, deep=True,
                                   benchmark=None, bench_wt_flag=None):
    portfolios = util.to_numpy(portfolios)
    if wt_flags is None:
        wt_flags = np.full((len(portfolios), 1), 'NONE')
    else:
        if isinstance(wt_flags, str):
            wt_flags = np.array([wt_flags])
        if len(wt_flags) == 1:
            wt_flags = np.tile(wt_flags, len(portfolios))
        if len(wt_flags) != len(portfolios):
            display(f"get_multiple_portfolios: Weight Flag and Portfolios should match in length")
            raise ValueError
    if benchmark is not None:
        ben = get_cached_weights(bus_day, bus_day, benchmark, weight_flag=bench_wt_flag,
                                 calendar_str=calendar_str, recurse=recurse, deep=deep)
        display(f"loaded benchmark: {benchmark}: {len(ben.columns)} securities for {bus_day}")
    else:
        ben = None
    pf = pd.DataFrame(index=portfolios)
    for ix, por in enumerate(portfolios):
        if wt_flags[ix] == 'NONE':
            wt_flag = None
        else:
            wt_flag = wt_flags[ix]
        try:
            p = get_cached_weights(bus_day, bus_day, por, weight_flag=wt_flag, calendar_str=calendar_str,
                                   recurse=recurse, deep=deep)
            if ben is not None:
                p = active_portfolio(p, ben)
            p.index = np.array([por])
            pf = pf.combine_first(p)
        except ValueError as ve:
            display(ve)
            display(f"{por}: {bus_day}: holding failed at loading: value error")
        except Exception as ee:
            display(ee)
            display(f"{por}: {bus_day}: holding failed at loading: exception")
    pf[pd.isnull(pf)] = 0.0
    return pf


def get_portfolio_base_currencies(portfolios):
    currencies = pd.DataFrame('USD', index=portfolios, columns=['values'])
    for s in portfolios:
        so = root.load_object(s)
        currencies.loc[s, 'values'] = so.base_currency
    return currencies


def get_portfolio_returns(start_date, end_date, p, calendar_str='GL', base_currency=None):
    """
    get internal portfolio returns
    :param start_date:
    :param end_date:
    :param p:
    :param calendar_str: default 'GL'
    :param base_currency: default None for local returns
    :return:
            if base_currency not given, it is local return in portfolios' own base currency
            if base_currency is given, returns in that base currency, local returns in portfolio's own base currency,
                    and FX rate for each portfolio
    Example:
        Input:
            get_portfolio_returns(20220721, 20220731, ['US_LC_Dynamic_Edge', 'US100'], 'US', 'GBP')

        Output
            total_return_frame, local_return_frame, x_rate_frame

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 1, 2022
    """
    if isinstance(p, str):
        p = np.array([p])
    if isinstance(p, list):
        p = np.array(p)
    if p is None:
        display(f"{util.current_time()}: : no valid portfolios requested")
        return None
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        util.display(f"{calendar_str}: no valid business days")
        return None
    df = pd.DataFrame(None, index=days, columns=p)
    portfolios = filter_portfolios(p)
    if len(portfolios) == 0:
        display(f"{util.current_time()}: : No internal portfolios found")
        return df
    fx = get_portfolio_base_currencies(portfolios)
    fx.reset_index(inplace=True)
    fx.rename(columns={fx.columns[0]: 'sec_ids', 'values': 'currency'}, inplace=True)
    location = util.return_location()
    for d in days:
        file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
        if not util.exists(file):
            display(f"{d}: return file not found")
            continue
        try:
            data = util.load_data(file)
            z = fx.merge(data, left_on=['sec_ids', 'currency'], right_on=['sec_ids', 'currency'], how='inner')
            df.loc[d, z['sec_ids'].to_numpy()] = z['values'].to_numpy()
        except ValueError as ve:
            display(ve)
            display(f"{d}: Value Error: unable to load holdings")
        except IOError as ioe:
            display(ioe)
            display(f"{d}: I/O Error: unable to load holdings")
        except Exception as ee:
            display(ee)
            display(f"{d}: Exception: unable to load holdings")

    if base_currency is not None:
        currencies = np.unique(fx['currency'].to_numpy())
        foreign = np.setdiff1d(currencies, base_currency)
        lf = df.copy(deep=True)
        if len(foreign) == 0:
            xf = pd.DataFrame(1.0, index=df.index, columns=df.columns)
        else:
            x = md.get_exchange_rate_returns(days[0], days[-1], currencies, base_currency, calendar_str)
            xf = pd.DataFrame(np.nan, index=df.index, columns=df.columns)
            for f in x.columns:
                ix = np.where(fx['currency'] == f)[0]
                fp = fx['sec_ids'].iloc[ix].to_numpy()
                xf.loc[xf.index, fp] = x[[f]].to_numpy()
            df = (1 + lf)*(1 + xf) - 1
        display(f"{len(df.columns)} portfolios x {len(days)} days total returns loaded: {days[0]} - {days[-1]}")
        return df, lf, xf
    else:
        display(f"{len(df.columns)} portfolios x {len(days)} days local returns loaded: {days[0]} - {days[-1]}")
        return df


def filter_portfolios(sec_ids):
    internals = root.is_internal(sec_ids)
    portfolios = internals.index[np.where(internals)[0]].to_numpy()
    return portfolios


def propagate_shares(holdings, from_date, to_date, calendar_str='GL'):
    """
    propagate shares
    Parameters
    ----------
    holdings
    from_date
    to_date
    calendar_str

    Returns
    -------

    """

    days = util.load_business_days(calendar_str, from_date, to_date)
    if len(days) == 0:
        display(f"No business days")
        return holdings
    sec = holdings.columns.to_numpy()
    mergers = ma.get_completed_merger_acquisitions(days[0], days[-1])
    sd = days[0]
    position = pd.DataFrame()
    for d in days[1:]:
        # split adjustments
        ratios = md.get_adjustment_factors(sd, d, sec, calendar_str)
        # special/cash dividends
        div = md.get_dividends(d, d, sec, calendar_str)
        # ma
        sd = d
    return position
