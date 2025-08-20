import numbers
import os.path

import numpy as np
import pandas as pd
import util.utilities as util
import dataloader.market_data as md
import dataloader.portfolio as port
import dataloader.fundamental as fd
import dataloader.ma as ma
from util.utilities import display


def test_price(start_date, end_date, calendar_str='US'):

    dates = util.load_business_days(calendar_str, start_date, end_date, 'MONTHEND')
    sql_base = f"select top 5000 p.fsym_id, p.p_date as date, p.p_price, " \
               f"p.p_price_open, p.p_price_high, p.p_price_low, p.p_volume " \
               f"from fp_v2.fp_basic_prices p inner join sym_v1.sym_coverage sm on " \
               f"sm.fsym_id = p.fsym_id where sm.fref_security_type = 'SHARE' and p.p_volume > 0 and " \
               f"p_date = "
    ret_base = f"select p.fsym_id, p.p_date as date, p.one_day_pct as ret from fp_v2.fp_total_returns_daily p " \
               f"where p.p_date = "

    # keys = ['close', 'low', 'high', 'open', 'volume', 'return']
    keys = ['close', 'low', 'high', 'open', 'volume']
    result = dict.fromkeys(keys)
    for key in result.keys():
        result[key] = pd.DataFrame(index=dates, columns=['correlation', 'max_diff', 'count', 'f_missing', 'i_missing'])
    for d in dates:
        try:
            conn = md.get_connection(sandbox='FactSet')
            cursor = conn.cursor()
            sql = sql_base + f"'{d.strftime(util.yyyy_mm_dd_format)}' order by p.p_volume DESC"
            at = util.clock()
            cursor.execute(sql)
            records = cursor.fetchall()
            zf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            zf.drop_duplicates(keep='last', inplace=True)
            et = util.clock()
            print(f"{d}: {len(records)} rows: {et - at: .1f} seconds | prices")
            # close
            df = zf.pivot(index='date', columns='fsym_id', values='p_price')
            p = md.get_prices(d, d, df.columns.to_numpy(), calendar_str, 'CLOSE')
            ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            pf = pd.concat([df[ids], p[ids]], axis=0)
            result['close'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            result['close'].loc[d, 'count'] = len(df.columns)
            result['close'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            result['close'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            result['close'].loc[d, 'max_diff'] = np.nanmax(np.abs(df[ids].to_numpy() - p[ids].to_numpy()), 1)[0]
            print(f"{d}: close complete  <====")
            # low
            df = zf.pivot(index='date', columns='fsym_id', values='p_price_low')
            p = md.get_prices(d, d, df.columns.to_numpy(), calendar_str, 'LOW')
            ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            pf = pd.concat([df[ids], p[ids]], axis=0)
            result['low'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            result['low'].loc[d, 'count'] = len(df.columns)
            result['low'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            result['low'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            result['low'].loc[d, 'max_diff'] = np.nanmax(np.abs(df[ids].to_numpy() - p[ids].to_numpy()), 1)[0]
            print(f"{d}: low complete  <====")
            # high
            df = zf.pivot(index='date', columns='fsym_id', values='p_price_high')
            p = md.get_prices(d, d, df.columns.to_numpy(), calendar_str, 'HIGH')
            ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            pf = pd.concat([df[ids], p[ids]], axis=0)
            result['high'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            result['high'].loc[d, 'count'] = len(df.columns)
            result['high'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            result['high'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            result['high'].loc[d, 'max_diff'] = np.nanmax(np.abs(df[ids].to_numpy() - p[ids].to_numpy()), 1)[0]
            print(f"{d}: high complete  <====")
            # open
            df = zf.pivot(index='date', columns='fsym_id', values='p_price_open')
            p = md.get_prices(d, d, df.columns.to_numpy(), calendar_str, 'OPEN')
            ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            pf = pd.concat([df[ids], p[ids]], axis=0)
            result['open'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            result['open'].loc[d, 'count'] = len(df.columns)
            result['open'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            result['open'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            result['open'].loc[d, 'max_diff'] = np.nanmax(np.abs(df[ids].to_numpy() - p[ids].to_numpy()), 1)[0]
            print(f"{d}: open complete  <====")
            # vol
            df = zf.pivot(index='date', columns='fsym_id', values='p_volume')
            p = md.get_volume(d, d, df.columns.to_numpy(), calendar_str)
            ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            pf = pd.concat([df[ids], p[ids]], axis=0)
            result['volume'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            result['volume'].loc[d, 'count'] = len(df.columns)
            result['volume'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            result['volume'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            result['volume'].loc[d, 'max_diff'] = np.nanmax(np.abs(df[ids].to_numpy() - p[ids].to_numpy()), 1)[0]
            print(f"{d}: volume complete  <====")
            # return
            # rql = ret_base + f"'{d.strftime(util.yyyy_mm_dd_format)}'"
            # rql = rql + f" and p.fsym_id in ('{ids[0]}'"
            # for ix, s in enumerate(ids):
            #     if ix == 0:
            #         continue
            #     rql = rql + f", '{s}'"
            # rql = rql + ")"
            # at = util.clock()
            # cursor.execute(rql)
            # records = cursor.fetchall()
            # rf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            # rf.drop_duplicates(keep='last', inplace=True)
            # et = util.clock()
            # print(f"{d}: {len(records)} rows: {et - at: .1f} seconds | returns")
            # df = rf.pivot(index='date', columns='fsym_id', values='ret')
            # p = md.get_returns(d, d, df.columns.to_numpy(), calendar_str)
            # ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            # pf = pd.concat([df[ids], p[ids]], axis=0)
            # result['return'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            # result['return'].loc[d, 'count'] = len(df.columns)
            # result['return'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            # result['return'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            # result['return'].loc[d, 'max_diff'] = np.nanmax(np.abs(df[ids].to_numpy() - p[ids].to_numpy()), 1)[0]
            # print(f"{d}: return complete  <====")
            cursor.close()
            conn.close()
        except ValueError as ve:
            print(ve)
            print(f"{util.clock()}: failed on {d}")
            cursor.close()
            conn.close()
        except Exception as ee:
            print(ee)
            print(f"{util.clock()}: failed on {d}")
            cursor.close()
            conn.close()

    file = os.path.join(util.default_output_location('reports'), 'tmp', f'test_price.xlsx')
    with pd.ExcelWriter(file) as writer:
        for key in result.keys():
            result[key].to_excel(writer, sheet_name=key)
            print(f"{key} :    {file}")
    return result


def test_returns(start_date, end_date, suffix=0, calendar_str='US'):

    dates = util.load_business_days(calendar_str, start_date, end_date, 'MONTHEND')
    sql_base = f"select top 5000 p.fsym_id, p.p_date as date, p.one_day_pct as ret " \
               f"from fp_v2.fp_total_returns_daily p inner join fp_v2.fp_basic_prices prices on " \
               f"prices.fsym_id = p.fsym_id and prices.p_date = p.p_date " \
               f"where prices.p_volume > 0 and p.p_date = "

    keys = ['return']
    result = dict.fromkeys(keys)
    for key in result.keys():
        result[key] = pd.DataFrame(index=dates, columns=['correlation', 'max_diff', 'count', 'f_missing',
                                                         'i_missing', 'max_sec'])
    for d in dates:
        try:
            conn = md.get_connection(sandbox='FactSet')
            cursor = conn.cursor()
            sql = sql_base + f"'{d.strftime(util.yyyy_mm_dd_format)}' order by prices.p_volume DESC"
            at = util.clock()
            cursor.execute(sql)
            records = cursor.fetchall()
            zf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            zf.drop_duplicates(keep='last', inplace=True)
            et = util.clock()
            print(f"{d}: {len(records)} rows: {et - at: .1f} seconds | returns")
            df = zf.pivot(index='date', columns='fsym_id', values='ret')
            p = md.get_returns(d, d, df.columns.to_numpy(), calendar_str)
            ids = np.intersect1d(df.columns.to_numpy(), p.columns.to_numpy())
            pf = pd.concat([df[ids], p[ids]], axis=0)
            abs_diff = np.abs(df[ids].to_numpy()/100.0 - p[ids].to_numpy())
            result['return'].loc[d, 'correlation'] = pf.T.corr().iloc[0,1]
            result['return'].loc[d, 'count'] = len(df.columns)
            result['return'].loc[d, 'i_missing'] = pd.isnull(p).sum(axis=1).sum()
            result['return'].loc[d, 'f_missing'] = pd.isnull(df).sum(axis=1).sum()
            result['return'].loc[d, 'max_diff'] = np.nanmax(abs_diff, 1)[0]
            result['return'].loc[d, 'max_sec'] = ids[np.nanargmax(abs_diff)]
            print(f"{d}: return complete  <====")
            cursor.close()
            conn.close()
        except ValueError as ve:
            print(ve)
            print(f"{util.clock()}: failed on {d}")
            cursor.close()
            conn.close()
        except Exception as ee:
            print(ee)
            print(f"{util.clock()}: failed on {d}")
            cursor.close()
            conn.close()

    file = os.path.join(util.default_output_location('reports'), 'tmp', f'test_returns_{suffix}.xlsx')
    with pd.ExcelWriter(file) as writer:
        for key in result.keys():
            result[key].to_excel(writer, sheet_name=key)
            print(f"{key} :    {file}")
    return result


def test_fundamentals(start_date, end_date, benchmark=30, fields=['ff_sales', 'ff_assets', 'ff_net_inc_cf'],
                      calendar_str='US', freq='MONTHEND', frequencies=['qtr', 'ltm', 'ann'], nums=[4, 1, 1],
                      save_flag=True):
    days = util.load_business_days(calendar_str, start_date, end_date, freq)
    output_location = os.path.join(util.default_output_location('reports'), 'tmp', 'test',
                                   'fundamental', f"{benchmark}")
    if not util.exists(output_location):
        util.makedirs(output_location)
        display(f"generated {output_location}")
    if isinstance(frequencies, str):
        frequencies = np.array([frequencies])
    if isinstance(nums, numbers.Number):
        nums = np.array([nums])
    result = dict.fromkeys(frequencies)
    for f in result.keys():
        result[f] = pd.DataFrame(0, index=days, columns=np.concatenate((['count'], fields)))
    for d in days:
        prev_d = util.previous_business_days(d, 'US', 1)
        p = port.get_positions(prev_d, d, benchmark)
        sids = p.columns.to_numpy()
        count = len(sids)
        dc = dict.fromkeys(frequencies)
        for ix, fq in enumerate(frequencies):
            result[fq].loc[d, 'count'] = count
            try:
                data = fd.get_fundamentals(d, sids, fields, fq, nums[ix])
                for f in fields:
                    td = data.pivot(index='fsym_id', columns='date', values=f)
                    valid = (td.notnull().sum(axis=1) == nums[ix]).sum()
                    result[fq].loc[d, f] = valid
                    display(f"{d}: {fq}: {f}: {valid} out of {count} <=====")
                dc[fq] = result[fq].loc[[d]]
            except Exception as ee:
                display(f"{ee}")
                display(f"{d}: Unable to load ")
        file = os.path.join(output_location, f"{d.strftime(util.yyyymmdd_format)}.qd")
        if util.exists(file):
            qd = util.load_data(file)
            for k in dc.keys():
                if k not in qd:
                    qd[k] = dc[k]
                    continue
                if qd[k] is None:
                    qd[k] = pd.DataFrame()
                if dc[k] is None:
                    dc[k] = pd.DataFrame()
                    continue
                qd[k] = qd[k].combine_first(dc[k])
                qd[k].update(dc[k])
            dc = qd
        util.save_data(dc, file)
        print(f"Cached {d} to {file}")
    if save_flag:
        file = os.path.join(output_location, f"{benchmark}")
        for f in fields:
            file = os.path.join(f"{file}.{f}")
        file = os.path.join(f"{file}.{days[0].strftime(util.yyyymmdd_format)}.{days[-1].strftime(util.yyyymmdd_format)}")
        file = os.path.join(f"{file}.xlsx")
        with pd.ExcelWriter(file) as writer:
            for f in frequencies:
                result[f].to_excel(writer, sheet_name=f)
        print(f"Successfully output Fundamental test files to {file}")
    return result


def print_fundamentals(start_date, end_date, benchmark=30, fields=['ff_sales', 'ff_assets', 'ff_net_inc_cf'],
                       calendar_str='US', freq='MONTHEND', frequencies=['qtr', 'ltm', 'ann']):
    output_location = os.path.join(util.default_output_location('reports'), 'tmp', 'test',
                                   'fundamental', f"{benchmark}")
    days = util.load_business_days(calendar_str, start_date, end_date, freq)
    file = os.path.join(output_location, f"{benchmark}")
    for f in fields:
        file = os.path.join(f"{file}.{f}")
    result = dict.fromkeys(frequencies)
    for f in result.keys():
        result[f] = pd.DataFrame(0, index=days, columns=np.concatenate((['count'], fields)))
    for d in days:
        file = os.path.join(output_location, f"{d.strftime(util.yyyymmdd_format)}.qd")
        if not util.exists(file):
            display(f"{d}: not found: {file} <======")
            continue
        try:
            data = util.load_data(file)
            for f in result.keys():
                if f not in data:
                    display(f"{d}: {f} not computed")
                    continue
                if data[f] is None:
                    display(f"{d}: {f} NaN; skipping")
                    continue
                if data[f].empty:
                    display(f"{d}: {f} empty; skipping")
                    continue
                result[f].update(data[f])
                print(f"{d}: {f}: {data[f].loc[data[f].index[0], 'count']}")
        except Exception as ee:
            display(ee)
            display(f"{d}: error loading prior computed data")
    file = os.path.join(output_location, f"{benchmark}")
    for f in fields:
        file = os.path.join(f"{file}.{f}")
    file = os.path.join(f"{file}.{days[0].strftime(util.yyyymmdd_format)}.{days[-1].strftime(util.yyyymmdd_format)}")
    file = os.path.join(f"{file}.xlsx")

    with pd.ExcelWriter(file) as writer:
        for f in frequencies:
            result[f] = result[f].astype('int64')
            result[f].to_excel(writer, sheet_name=f)
    print(f"Successfully output Fundamental test files to {file}")
    return result


def deal_statistics(start_date=None, end_date=None, deals=None, date_type='announce', status='closed',
                    target_domiciles=None, buyer_domiciles=None):

    if deals is None:
        dls = ma.get_merger_acquisitions(start_date, end_date, date_type, True, True, True)
    else:
        dls = ma.get_deal_info(deals)
    if dls is None or dls.empty:
        display(f"No valid deals found; returning None")
        return False
    if status in ('close', 'closed', 'completed'):
        ix = np.where(pd.notnull(dls['close_date']))[0]
        dls = dls.iloc[ix]
    elif status in ('cancel', 'cancelled', 'cancellation', 'fail', 'failed'):
        ix = np.where(pd.notnull(dls['close_date']))[0]
        dls = dls.iloc[ix]
    if target_domiciles is not None:
        if isinstance(target_domiciles, str):
            target_domiciles = np.array([target_domiciles])
        elif isinstance(target_domiciles, list):
            target_domiciles = np.array(target_domiciles)
        dom = md.get_domiciles(dls['target_sec_id'].to_numpy())
        ids = dom.index[np.where(np.isin(dom['domicile'].to_numpy(), target_domiciles))[0]].to_numpy()
        ix = np.where(np.isin(dls['target_sec_id'].to_numpy(), ids))[0]
        dls = dls.iloc[ix]
    if buyer_domiciles is not None:
        if isinstance(buyer_domiciles, str):
            buyer_domiciles = np.array([buyer_domiciles])
        elif isinstance(buyer_domiciles, list):
            buyer_domiciles = np.array(buyer_domiciles)
        dom = md.get_domiciles(dls['purchaser_sec_id'].to_numpy())
        ids = dom.index[np.where(np.isin(dom['domicile'].to_numpy(), buyer_domiciles))[0]].to_numpy()
        ix = np.where(np.isin(dls['purchaser_sec_id'].to_numpy(), ids))[0]
        dls = dls.iloc[ix]
    if dls.empty:
        display(f"No deals to run")
    announce_min = np.min(dls['announce_date'].to_numpy())
    announce_max = np.max(dls['announce_date'].to_numpy())
    close_min = np.min(dls['close_date'].to_numpy())
    close_max = np.max(dls['close_date'].to_numpy())


def test_cached_public_mergers(start_y, end_y, domicile='US', save_flag=False):
    years = list(range(start_y, end_y+1))
    data = dict.fromkeys(years)
    for y in years:
        s = util.parse_date(f"{y}0101")
        e = util.parse_date(f"{y}1231")
        data[y] = pd.DataFrame()
        try:
            df = ma.get_cached_public_mergers(s, e, domiciles=domicile)
            if df is None:
                display(f"No deals found for {y}")
                continue
            if df.empty:
                display(f"No deals found for {y}")
                continue
            sids = np.unique(df['sec_id'])
            cap, cu, xrates, ccys = md.get_market_cap(s, e, sids, 'GL', base_currency='USD')
            df['market_cap'] = np.nan
            for j in df.index:
                deal = df.loc[j, 'deal_id']
                sid = df.loc[j, 'sec_id']
                d = df.loc[j, 'announce_date']
                i1 = np.where(cap.index <= d)[0]
                i2 = np.where(cap.columns == sid)[0]
                if len(i1) == 0 or len(i2) == 0:
                    display(f"{y}: sec_id (deal {deal}) no market cap on announcement date {d}")
                    continue
                try:
                    df.loc[j, 'market_cap'] = cap.iloc[i1[-1], i2[0]]
                except ValueError as ee:
                    display(f"{ee}")
                    display(f"{j}: {deal}")
                except Exception as eex:
                    display(f"{eex}")
                    display(f"{j}: {deal}")

            ix = np.where(df['role'] == 'target')[0]
            t_min = np.nanmin(df.loc[df.index[ix], 'market_cap'])
            t_max = np.nanmax(df.loc[df.index[ix], 'market_cap'])
            iy = np.where(df['role'] == 'buyer')[0]
            b_min = np.nanmin(df.loc[df.index[iy], 'market_cap'])
            b_max = np.nanmax(df.loc[df.index[iy], 'market_cap'])
            display(f"Processed year {y}: {len(np.unique(df['deal_id'].iloc[ix]))} deals, {len(sids)} securities")
            display(f"{len(np.unique(df.loc[df.index[ix], 'deal_id']))} targets: max cap ${t_max:,.1f} mln, "
                    f"min cap ${t_min:,.1f} mln")
            display(f"{len(np.unique(df.loc[df.index[iy], 'deal_id']))} buyers: max cap ${b_max:,.1f} mln, "
                    f"min cap ${b_min:,.1f} mln")
            data[y] = df
        except ValueError as ve:
            display(f"{ve}")
            display(f"{y}: unable to load cached public mergers")

    if save_flag:
        file = os.path.join(util.default_output_location('reports'), 'tmp',
                            f'cached_ma_{domicile}_{years[0]}_{years[-1]}.xlsx')
        for y in data.keys():

            exist = util.exists(file)
            if exist:
                with pd.ExcelWriter(file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    data[y].to_excel(writer, sheet_name=f"{y}")
            else:
                with pd.ExcelWriter(file, engine='openpyxl', mode='w') as writer:
                    data[y].to_excel(writer, sheet_name=f"{y}")
    return data

