# Scenario analysis
#
#
# Author : Yun CHen
# Copyright: Indigo Dao, LLC
# Date : January 20, 2022
# ---------------------------------------
import numbers
import os
import pandas as pd
import numpy as np
import dataloader.market_data as md
import analytics.ea.factor_performance as fp
import util.utilities as util
from util.utilities import display
import classes.root as root


def historical_simulation_ts(exposure_date, hist_start, hist_end, sec_ids, factor_group=None, assets=None,
                             look_back=126, calendar_str='US', factors=None, print_report=True, prod=False):
    if factor_group is None and assets is None:
        display(f"No valid factor group or explanatory assets: nothing to do; returning None")
        return None
    exp_date = util.most_recent_business_day(exposure_date, calendar_str)
    ret_days = util.load_business_days(calendar_str, hist_start, hist_end)
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f"No valid securities/portfolios requested")
    if look_back is None or not isinstance(look_back, numbers.Number) or look_back <= 0:
        look_back = 126
    exp_days = util.load_business_days(calendar_str, None, exp_date)
    exp_days = exp_days[-look_back:]
    sec_ids = np.unique(sec_ids)
    ret = md.get_returns(exp_days[0], exp_days[-1], sec_ids, calendar_str)
    fr = get_returns(ret.index[0], ret.index[-1], factor_group, assets, calendar_str, factors)
    exposures = fp.factor_exposure_ts(ret, fr, True, None, calendar_str, look_back)
    hr = get_returns(ret_days[0], ret_days[-1], factor_group, assets, calendar_str, factors)  # historical factor return
    tr = md.get_returns(ret_days[0], ret_days[-1], sec_ids, calendar_str)  # historical target returns to assess vol
    sr = pd.DataFrame(np.nan, index=hr.index, columns=ret.columns)
    snapshot = pd.DataFrame(0.0, index=ret.columns, columns=exposures[0].columns)
    for ix, s in enumerate(sr.columns):
        es = np.tile(exposures[ix], (len(hr.index), 1))
        sr.loc[sr.index, s] = np.nansum(hr.to_numpy() * es, axis=1)
        v = np.nanstd(tr[s])
        e = np.nanstd(sr[s])
        sr.loc[sr.index, s] = sr.loc[sr.index, s] * v / e
    for ix in range(len(exposures)):
        col = np.intersect1d(snapshot.columns, exposures[ix].columns)
        snapshot.loc[s, col] = exposures[ix].loc[exposures[ix].index[0], col].to_numpy()
    if print_report:
        if prod:
            env = 'PROD'
        else:
            env = 'DEV'
        output_location = os.path.join(util.default_output_location('reports', env), 'ea')
        if not util.exists(output_location):
            util.makedirs(output_location)
            display(f"Successfully created {output_location}")
        ref = md.get_stock_references(np.union1d(sec_ids, assets))
        file = os.path.join(output_location, f"scenario")
        for s in sec_ids:
            if s not in ref.index:
                continue
            file = f"{file}.{ref.loc[s, 'ticker']}"
            if s in sr:
                sr.rename(columns={s: f"Simulated {ref.loc[s, 'name']}"}, inplace=True)
            if s in tr:
                tr.rename(columns={s: f"Actual {ref.loc[s, 'name']}"}, inplace=True)
            if s in snapshot.index:
                snapshot.rename(index={s: ref.loc[s, 'name']}, inplace=True)
        for s in assets:
            if s not in ref.index:
                continue
            if s not in hr:
                continue
            hr.rename(columns={s: ref.loc[s, 'name']}, inplace=True)
            snapshot.rename(columns={s: ref.loc[s, 'name']}, inplace=True)
        file = f"{file}.xlsx"
        with pd.ExcelWriter(file) as writer:
            snapshot.to_excel(writer, sheet_name='Exposures')
            hr.to_excel(writer, sheet_name='Factor Returns')
            sr.to_excel(writer, sheet_name='Simulated')
            tr.to_excel(writer, sheet_name='Actual')
        print(f"Successfully output simulated returns to {file}")

    return exposures, sr, hr, tr


def get_returns(start_date, end_date, factor_group=None, assets=None, calendar_str='US', factors=None):
    dates = util.load_business_days(calendar_str, start_date, end_date)
    if factor_group is not None:
        fg = root.load_object(factor_group)
        fr = fg.load_factor_returns(dates[0], dates[-1], calendar_str=calendar_str)
        fr = fr['values'][0]['values']
        if factors is not None:
            if isinstance(factors, str):
                factors = np.array([factors])
            if isinstance(factors, list):
                factors = np.array(factors)
            factors = np.unique(factors)
        ix = np.where(np.isin(fr.columns, factors))[0]
        fr = fr.iloc[:, ix]
    else:
        fr = None
    if assets is not None:
        ar = md.get_returns(dates[0], dates[-1], assets, calendar_str)
    else:
        ar = None
    if fr is None and ar is None:
        display(f"No valid explanatory returns; nothing to do, returning None")
        return None
    if fr is None:
        fr = ar
    if fr is not None:
        if ar is not None:
            fr = fr.join(ar)
    return fr
