#
#
#
#
#
#
###################################################
import pandas as pd
import pyodbc as db
import functools as ft
import numbers
import dataloader.market_data as md
import numpy as np
import util.utilities as util
from util.utilities import display
from util.routines import intersect


@ft.lru_cache()
def get_reporting_frequencies(freq=None):
    """

    """
    frequencies = np.array(['LTM', 'QF', 'AF'])
    if freq is None or not isinstance(freq, str):
        return frequencies
    else:
        z = freq.lower().strip()
        if z in ('quarter', 'quarterly', 'qtr', 'qf'):
            return 'QF'
        elif z in ('ltm', 'lagged_12_months', 'lagged twelve months', 'last 12 months', 'last_12_months'):
            return 'LTM'
        elif z in ('af', 'annual', 'yearly', 'year', 'annually', 'ann'):
            return 'AF'
        else:
            raise ValueError(f"{freq} not recognized or supported")


def get_fiscal_periods(fp, num=1, freq='QF'):
    """

    Parameters
    ----------
    fp
    num
    freq

    Returns
    -------

    """
    code = get_reporting_frequencies(freq)
    periods = np.array([np.nan] * num)
    periods[0] = fp
    if code == 'AF':
        for i in range(1, num):
            periods[i] = periods[i - 1] - 100
    else:
        for i in range(1, num):
            m = int(periods[i - 1] % 100)
            y = periods[i - 1] - m
            m = m - 3
            if m <= 0:
                m = 12 + m
                y = y - 100
            periods[i] = y + m
    return periods.astype('int64')


def align_fiscal_periods(periods, ff_fpnc):
    result = periods
    for ix, p in enumerate(periods):
        if p in ff_fpnc:
            continue
        if p + 1 in ff_fpnc:
            result[ix] = p + 1
        elif p - 1 in ff_fpnc:
            result[ix] = p - 1
    return result


def get_fundamentals(bus_day, sec_ids, items, freq='qtr', num=1, lag=0, base_currency=None, calendar_str='US',
                     sandbox='PROD'):
    """

    Parameters
    ----------
    bus_day
    sec_ids
    items
    freq
    num
    lag
    base_currency
    calendar_str
    sandbox

    Returns
    -------

    """
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid fundamental item(s) requested")
        return None
    if num is None or not isinstance(num, numbers.Number) or num < 1:
        num = 1
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f"Fundamental loader: required string or list / array of strings for security identifiers")
        raise ValueError(f"Input required: sec_ids cannot be empty")
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1-lag]
    num = int(np.floor(num))
    freq_code = get_reporting_frequencies(freq)
    if freq_code == 'QF':
        earliest = util.previous_business_days(day, calendar_str, (num + 2) * 90)
    else:
        earliest = util.previous_business_days(day, calendar_str, (num + 1) * 260)
    available = is_available(items, freq_code)
    fields = available.index[np.where(available['values'])[0]].to_numpy()
    not_availables = available.index[np.where(~available['values'])[0]].to_numpy()
    if len(fields) == 0:
        display(f"Out of {len(items)}: no field is available from Database for frequency {freq_code}; returning None")
        return None
    if len(not_availables) > 0:
        display(f"{len(not_availables)} of {len(items)} requested fields are not available for frequency {freq_code}")
    sql_base = f"select fsym_id, date, currency, cast(ff_fpnc AS integer) as ff_fpnc, " \
               f"ff_fyr, ff_eps_rpt_date, ff_restate_ind "
    for item in fields:
        sql_base = sql_base + f", {item}"
    sql_base = f"{sql_base} from FF.ff_basic where " \
               f"ff_eps_rpt_date <= '{day.strftime(util.YY_MM_DD_format)}' and " \
               f"ff_eps_rpt_date >= '{earliest.strftime(util.YY_MM_DD_format)}' and " \
               f"ff_FrequencyCode = '{freq_code}' and " \
               f"IsActive = 1 " \
               f"and fsym_id in "
    sql_suffix = f"ORDER BY fsym_id, date DESC"
    conn = md.get_connection(sandbox=sandbox)
    try:
        ac = util.clock()
        data = md.execute_batch(conn, sql_base, sec_ids, batch_size=20, drop_duplicate=True, sql_suffix=sql_suffix)
        rc = util.clock()
        data.loc[data.index, 'date'] = util.parse_date(data['date'].to_numpy())
        data.drop_duplicates(keep='last', inplace=True)
        fc = util.clock()
        display(f" {len(data.index)} rows of record: as of {bus_day}")
        display(f"executing query took {rc - ac: .1f} Seconds: as of {bus_day}")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds: as of {bus_day}")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        display(sql_base)
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        display(sql_base)
        conn.close()
        raise IOError(f'database exception: ')
    if data.empty:
        display(f"No fundamental data found; returning None")
        return data
    data = filter_fundamental(data, num, freq_code)
    if len(not_availables) > 0:
        data[not_availables] = np.nan
    # restated
    ix = np.where(data['ff_restate_ind'])[0]
    updates = None
    if len(ix) > 0:
        restated = np.unique(data.loc[data.index[ix], 'fsym_id'])
        periods = np.unique(data.loc[data.index[ix], 'date'])
        try:
            fp_start = np.min(periods)
            fp_end = np.max(periods)
            updates = get_restated_fundamentals(bus_day, fp_start, fp_end, restated, fields,
                                                freq_code, lag, calendar_str, sandbox)
            data = update_fundamentals(bus_day, data, updates, items, lag, calendar_str)
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load from database: restated due to exception")
            raise IOError(f'database exception: ')

    return data


def get_restated_fundamentals(bus_day, fp_start, fp_end, sec_ids, items, freq='qtr', lag=0,
                              calendar_str='US', sandbox='PROD'):
    """

    Parameters
    ----------
    bus_day
    fp_start
    fp_end
    sec_ids
    items
    freq
    lag
    calendar_str
    sandbox

    Returns
    -------

    """
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid restated fundamental item(s) requested")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f"Fundamental loader: required string or list / array of strings for security identifiers")
        raise ValueError(f"Input required: sec_ids cannot be empty")
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1 - lag]
    start = util.parse_date(fp_start)
    fin = util.parse_date(fp_end)
    freq_code = get_reporting_frequencies(freq)
    sql_base = f"select fsym_id, date, currency, cast(ff_fpnc AS integer) as ff_fpnc, ff_fyr, ff_eps_rpt_date," \
               f"ff_source_bs_date, ff_source_is_date, ff_source_cf_date "
    for item in items:
        sql_base = sql_base + f", {item}"
    sql_base = f"{sql_base} from FF.ff_basic_r where " \
               f"date >= '{start.strftime(util.YY_MM_DD_format)}' and " \
               f"date <= '{fin.strftime(util.YY_MM_DD_format)}' and " \
               f"ff_FrequencyCode = '{freq_code}' and " \
               f"IsActive = 1 " \
               f"and fsym_id in "
    sql_suffix = f"ORDER BY fsym_id, date DESC"
    conn = md.get_connection(sandbox=sandbox)
    try:
        ac = util.clock()
        data = md.execute_batch(conn, sql_base, sec_ids, batch_size=20, drop_duplicate=True, sql_suffix=sql_suffix)
        rc = util.clock()
        data.loc[data.index, 'date'] = util.parse_date(data['date'].to_numpy())
        data.drop_duplicates(keep='last', inplace=True)
        fc = util.clock()
        display(f" {len(data.index)} rows of restated record: as of {bus_day}")
        display(f"executing query took {rc - ac: .1f} Seconds: as of {bus_day}")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds: as of {bus_day}")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        display(sql_base)
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        display(sql_base)
        conn.close()
        raise IOError(f'database exception: ')
    return data


def get_advanced_fundamentals(bus_day, sec_ids, items, freq='qtr', num=1, lag=0, base_currency=None, calendar_str='US',
                              sandbox='PROD'):
    """

    Parameters3
    ----------
    bus_day
    sec_ids
    items
    freq
    num
    lag
    base_currency
    calendar_str
    sandbox

    Returns
    -------

    """
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid fundamental item(s) requested")
        return None
    if num is None or not isinstance(num, numbers.Number) or num < 1:
        num = 1
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f"Fundamental loader: required string or list / array of strings for security identifiers")
        raise ValueError(f"Input required: sec_ids cannot be empty")
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1-lag]
    num = int(np.floor(num))
    freq_code = get_reporting_frequencies(freq)
    if freq_code == 'QF':
        table = 'ff_advanced_qf'
        earliest = util.previous_business_days(day, calendar_str, (num + 2) * 90)
    else:
        table = 'ff_advanced_af'
        earliest = util.previous_business_days(day, calendar_str, (num + 1) * 260)
    available = is_available(items, freq_code)
    fields = available.index[np.where(available['values'])[0]].to_numpy()
    not_availables = available.index[np.where(~available['values'])[0]].to_numpy()
    if len(fields) == 0:
        display(f"Out of {len(items)}: no field is available from Database for frequency {freq_code}; returning None")
        return None
    if len(not_availables) > 0:
        display(f"{len(not_availables)} of {len(items)} requested fields are not available for frequency {freq_code}")
    sql_base = f"select fsym_id, date, currency, ff_restate_ind "
    for item in fields:
        sql_base = sql_base + f", {item}"
    sql_base = f"{sql_base} from ff_v3.{table} where " \
               f"date <= '{day.strftime(util.YY_MM_DD_format)}' and " \
               f"date >= '{earliest.strftime(util.YY_MM_DD_format)}' and " \
               f"fsym_id in "
    sql_suffix = f"ORDER BY fsym_id, date DESC"
    conn = md.get_connection(database='FactSetDataFeed', sandbox=sandbox)
    try:
        ac = util.clock()
        data = md.execute_batch(conn, sql_base, sec_ids, batch_size=20, drop_duplicate=True, sql_suffix=sql_suffix)
        rc = util.clock()
        data.loc[data.index, 'date'] = util.parse_date(data['date'].to_numpy())
        data.drop_duplicates(keep='last', inplace=True)
        fc = util.clock()
        display(f" {len(data.index)} rows of record: as of {bus_day}")
        display(f"executing query took {rc - ac: .1f} Seconds: as of {bus_day}")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds: as of {bus_day}")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        display(sql_base)
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        display(sql_base)
        conn.close()
        raise IOError(f'database exception: ')
    if data.empty:
        display(f"No fundamental data found; returning None")
        return data
    data['ff_fpnc'] = (util.year(data['date']) * 100 + util.month(data['date'])).astype('int64')
    data = filter_fundamental(data, num, freq_code)
    if len(not_availables) > 0:
        data[not_availables] = np.nan
    # # restated
    # ix = np.where(data['ff_restate_ind'])[0]
    # updates = None
    # if len(ix) > 0:
    #     restated = np.unique(data.loc[data.index[ix], 'fsym_id'])
    #     periods = np.unique(data.loc[data.index[ix], 'date'])
    #     try:
    #         fp_start = np.min(periods)
    #         fp_end = np.max(periods)
    #         updates = get_restated_fundamentals(bus_day, fp_start, fp_end, restated, fields,
    #                                             freq_code, lag, calendar_str, sandbox)
    #         data = update_fundamentals(bus_day, data, updates, items, lag, calendar_str)
    #     except Exception as ee:
    #         display(f"{ee}")
    #         display(f"Unable to load from database: restated due to exception")
    #         raise IOError(f'database exception: ')

    return data


def filter_fundamental(data, num=1, freq='QF'):
    sec_ids = np.unique(data['fsym_id'].to_numpy())
    code = get_reporting_frequencies(freq)
    df = pd.DataFrame()
    for s in sec_ids:
        ix = np.where(data['fsym_id'] == s)[0]
        if len(ix) == 0:
            continue
        rows = data.loc[data.index[ix]]
        if num == 1:
            df = pd.concat((df, rows.iloc[[0]]), axis=0, ignore_index=True)
            continue
        last = rows.loc[rows.index[0], 'ff_fpnc']
        ccy = rows.loc[rows.index[0], 'currency']
        periods = get_fiscal_periods(last, num, code)
        if code == 'QF':
            periods = align_fiscal_periods(periods, rows['ff_fpnc'].to_numpy())
        iy = np.where(np.isin(rows['ff_fpnc'].to_numpy(), periods))[0]
        rows = rows.iloc[iy]
        missing = np.setdiff1d(periods, rows['ff_fpnc'].to_numpy())
        if len(missing) > 0:
            print(f"{s}: missing {len(missing)} fiscal periods, filling with NaN")
            years, months, dates = fiscal_dates(missing)
            lines = pd.DataFrame(columns=rows.columns)
            lines['ff_fpnc'] = missing
            lines.loc[lines.index, 'fsym_id'] = s
            lines.loc[lines.index, 'date'] = dates
            lines.loc[lines.index, 'currency'] = ccy
            lines.loc[lines.index, 'ff_fyr'] = years
            rows = pd.concat((rows, lines), axis=0, ignore_index=True)
            rows.sort_values(by='ff_fpnc', axis=0, ascending=False, ignore_index=True, inplace=True)
        df = pd.concat((df, rows), axis=0, ignore_index=True)
    return df


def update_fundamentals(bus_day, data, updates, items, lag=0, calendar_str='US'):
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid fundamental item(s) requested")
        return None
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1-lag]
    fields = np.intersect1d(data.columns, updates.columns)
    fields = np.intersect1d(fields, items)
    if len(fields) == 0:
        display(f"Nothing to update with restated")
        return data
    fields = fields.astype(str)
    ref = get_item_references(fields)
    ref['date_field'] = 'ff_eps_rpt_date'
    ix = np.where(ref['statement'] == 'IS')[0]
    ref.loc[ref.index[ix], 'date_field'] = 'ff_source_is_date'
    ix = np.where(ref['statement'] == 'BS')[0]
    ref.loc[ref.index[ix], 'date_field'] = 'ff_source_bs_date'
    ix = np.where(ref['statement'] == 'CF')[0]
    ref.loc[ref.index[ix], 'date_field'] = 'ff_source_cf_date'
    updated = np.unique(updates['fsym_id'].to_numpy())
    for s in updated:
        ix = np.where(data['fsym_id'] == s)[0]
        if len(ix) == 0:
            display(f"{s} not found in original dataset")
            continue
        iz = np.where(updates['fsym_id'] == s)[0]
        if len(iz) == 0:
            display(f"{s} not found in restated dataset")
            continue
        tu = updates.iloc[iz]
        del iz
        for r in tu.index:
            fp = tu.loc[r, 'date']
            iz = np.where(data.loc[data.index[ix], 'date'] == fp)[0]
            if len(iz) == 0:
                # display(f"{s}: {fp} not among original dataset; skipping")
                continue
            iz = iz[0]
            for f in fields:
                if tu.loc[r, f] is None:
                    continue
                d = tu.loc[r, ref.loc[f, 'date_field']]
                if d is None:
                    continue
                if d > day:
                    # display(f"{s}: {f}: {day} earlier than restatement date: {d}; skipping")
                    continue
                if tu.loc[r, f] == data.loc[data.index[ix[iz]], f]:
                    continue
                display(f"{s}: {f}: {bus_day} {lag}-lag: {fp}: original {data.loc[data.index[ix[iz]], f]}"
                        f" - restated {tu.loc[r, f]}")
                data.loc[data.index[ix[iz]], f] = tu.loc[r, f]
    return data


def fiscal_dates(fp):
    periods = np.array(fp)
    years = (periods/100).astype('int64')
    months = (periods % 100).astype('int64')
    dates = util.get_month_end_dates(years, months)
    return years, months, dates


def get_derived(bus_day, sec_ids, items, freq='qtr', num=1, lag=0, base_currency=None, calendar_str='US',
                sandbox='FactSetDataFeed'):
    """

    Parameters
    ----------
    bus_day
    sec_ids
    items
    freq
    num
    lag
    base_currency
    calendar_str
    sandbox : default FactSetDataFeed

    Returns
    -------

    """
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid fundamental derived item(s) requested")
        return None
    if num is None or not isinstance(num, numbers.Number) or num < 1:
        num = 1
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f"Fundamental derived loader: required string or list / array of strings for security identifiers")
        raise ValueError(f"Input required: sec_ids cannot be empty")
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    if sandbox is None or not isinstance(sandbox, str):
        sandbox = 'FactSetDataFeed'
    sandbox = sandbox.upper().strip()
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1-lag]
    num = int(np.floor(num))
    freq_code = get_reporting_frequencies(freq)
    if sandbox == 'FACTSETDATAFEED':
        table = f'FactSetDataFeed.ff_v3.ff_basic_der_{freq_code.lower()}'
    else:
        table = 'FF.ff_basic_der'
    if freq_code == 'QF':
        earliest = util.previous_business_days(day, calendar_str, (num + 2) * 90)
    else:
        earliest = util.previous_business_days(day, calendar_str, (num + 1) * 260)
    sql_base = f"select fsym_id, date, currency, ff_fyr"
    for item in items:
        sql_base = sql_base + f", {item}"
    # sql_base = f"{sql_base} from FF.ff_basic_der where " \
    sql_base = f"{sql_base} from {table} where " \
               f"date <= '{day.strftime(util.YY_MM_DD_format)}' and " \
               f"date >= '{earliest.strftime(util.YY_MM_DD_format)}' "
    if sandbox != 'FACTSETDATAFEED':
        sql_base = f"{sql_base} and ff_FrequencyCode = '{freq_code}' " \
                   f" and IsActive = 1 "
    sql_base = f"{sql_base} and fsym_id in "
    sql_suffix = f"ORDER BY fsym_id, date DESC"
    conn = md.get_connection(sandbox=sandbox)
    try:
        ac = util.clock()
        data = md.execute_batch(conn, sql_base, sec_ids, batch_size=20, drop_duplicate=True, sql_suffix=sql_suffix)
        rc = util.clock()
        data.loc[data.index, 'date'] = util.parse_date(data['date'].to_numpy())
        data.drop_duplicates(keep='last', inplace=True)
        fc = util.clock()
        display(f" {len(data.index)} rows of record")
        display(f"executing query took {rc - ac: .1f} Seconds")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        display(sql_base)
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        display(sql_base)
        conn.close()
        raise IOError(f'database exception: ')
    data['ff_fpnc'] = (util.year(data['date'])*100+util.month(data['date'])).astype('int64')
    data = filter_fundamental(data, num, freq_code)
    # restated
    ix = np.array(list(range(len(data.index))))
    if len(ix) > 0:
        restated = np.unique(data.loc[data.index[ix], 'fsym_id'])
        periods = np.unique(data.loc[data.index[ix], 'date'])
        try:
            fp_start = np.min(periods)
            fp_end = np.max(periods)
            updates = get_restated_derived(bus_day, fp_start, fp_end, restated, items,
                                           freq_code, lag, calendar_str, sandbox)
            data = update_derived(bus_day, data, updates, items, lag, calendar_str)
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load from database: restated due to exception")
            raise IOError(f'database exception: ')

    return data


def get_restated_derived(bus_day, fp_start, fp_end, sec_ids, items, freq='qtr', lag=0,
                         calendar_str='US', sandbox='PROD'):
    """

    Parameters
    ----------
    bus_day
    fp_start
    fp_end
    sec_ids
    items
    freq
    lag
    calendar_str
    sandbox

    Returns
    -------

    """
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid restated fundamental item(s) requested")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f"Fundamental loader: required string or list / array of strings for security identifiers")
        raise ValueError(f"Input required: sec_ids cannot be empty")
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    if sandbox is None or not isinstance(sandbox, str):
        sandbox = 'DEV'
    sandbox = sandbox.upper().strip()
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1 - lag]
    start = util.parse_date(fp_start)
    fin = util.parse_date(fp_end)
    freq_code = get_reporting_frequencies(freq)
    sql_base = f"select fsym_id, date, currency, ff_fyr "
    for item in items:
        sql_base = sql_base + f", {item}"
    sql_base = f"{sql_base} from FF.ff_basic_der_r where " \
               f"date >= '{start.strftime(util.YY_MM_DD_format)}' and " \
               f"date <= '{fin.strftime(util.YY_MM_DD_format)}' and " \
               f"ff_FrequencyCode = '{freq_code}' and " \
               f"IsActive = 1 " \
               f"and fsym_id in "
    sql_suffix = f"ORDER BY fsym_id, date DESC"
    conn = md.get_connection(sandbox=sandbox)
    try:
        ac = util.clock()
        data = md.execute_batch(conn, sql_base, sec_ids, batch_size=20, drop_duplicate=True, sql_suffix=sql_suffix)
        rc = util.clock()
        data.loc[data.index, 'date'] = util.parse_date(data['date'].to_numpy())
        data.drop_duplicates(keep='last', inplace=True)
        fc = util.clock()
        display(f" {len(data.index)} rows of restated record")
        display(f"executing query took {rc - ac: .1f} Seconds")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        display(sql_base)
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        display(sql_base)
        conn.close()
        raise IOError(f'database exception: ')
    return data


def update_derived(bus_day, data, updates, items, lag=0, calendar_str='US'):
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid fundamental item(s) requested")
        return None
    if lag is None or not isinstance(lag, numbers.Number) or lag < 0:
        lag = 0
    lag = int(np.floor(lag))
    days = util.load_business_days(calendar_str, None, bus_day)
    # lag logic
    day = days[-1-lag]
    fields = np.intersect1d(data.columns, updates.columns)
    fields = np.intersect1d(fields, items)
    if len(fields) == 0:
        display(f"Nothing to update with restated")
        return data
    fields = fields.astype(str)
    ref = get_item_references(fields)
    ref['date_field'] = 'date'
    updated = np.unique(updates['fsym_id'].to_numpy())
    for s in updated:
        ix = np.where(data['fsym_id'] == s)[0]
        if len(ix) == 0:
            display(f"{s} not found in original dataset")
            continue
        iz = np.where(updates['fsym_id'] == s)[0]
        if len(iz) == 0:
            display(f"{s} not found in restated dataset")
            continue
        tu = updates.iloc[iz]
        del iz
        for r in tu.index:
            fp = tu.loc[r, 'date']
            iz = np.where(data.loc[data.index[ix], 'date'] == fp)[0]
            if len(iz) == 0:
                # display(f"{s}: {fp} not among original dataset; skipping")
                continue
            iz = iz[0]
            for f in fields:
                if tu.loc[r, f] is None:
                    continue
                d = tu.loc[r, ref.loc[f, 'date_field']]
                if d is None:
                    print(f"{s}: field {f}, date missing; skipping")
                    continue
                if d > day:
                    # display(f"{s}: {f}: {day} earlier than restatement date: {d}; skipping")
                    continue
                if tu.loc[r, f] == data.loc[data.index[ix[iz]], f]:
                    continue
                display(f"{s}: {f}: {bus_day} {lag}-lag: {fp}: original {data.loc[data.index[ix[iz]], f]}"
                        f" - restated {tu.loc[r, f]}")
                data.loc[data.index[ix[iz]], f] = tu.loc[r, f]
    return data


def is_available(fields, freq='qtr'):
    if isinstance(fields, str):
        fields = np.array([fields])
    if isinstance(fields, list):
        fields = np.array(fields)
    fields = np.unique(fields)
    smap = get_all_item_statement_codes()
    df = pd.DataFrame(False, index=fields, columns=['ann', 'qtr', 'semi', 'ltm'])
    for f in df.columns:
        ix = np.where(np.isin(fields, smap.loc[smap.index[np.where(smap[f])[0]], 'field_name']))[0]
        df.loc[df.index[ix], f] = True
    if freq is not None:
        if freq.lower().strip() in ('qtr', 'qf', 'quarter'):
            df['values'] = df['qtr']
        if freq.lower().strip() in ('ann', 'annual', 'year', 'yearly', 'annually', 'af'):
            df['values'] = df['ann']
        if freq.lower().strip() in ('semi', 'half', 'semiannual', 'semi-annual', 'saf'):
            df['values'] = df['semi']
        if freq.lower().strip() in ('ltm', 'l12m'):
            df['values'] = df['ltm']
    else:
        df['values'] = df['qtr']
    return df


def get_item_references(items):
    """

    Parameters
    ----------
    items: string, list of strings, or numpy array of strings

    Returns
    -------
    data frame with items as index, and corresponding statements: BS, IS, CF
    """
    if isinstance(items, str):
        items = np.array([items])
    if isinstance(items, list):
        items = np.array(items)
    if len(items) == 0:
        display(f"No valid items provided: string, list or numpy array of strings are accepted")
        raise ValueError(f"Non-empty financial statement items are required")
    items = np.unique(items)
    items = np.char.strip(np.char.lower(items))
    df = pd.DataFrame('NA', index=items, columns=['statement', 'description'])
    bs = get_all_items('BS')
    ins = get_all_items('IS')
    cf = get_all_items('CF')
    pen = get_all_items('PEN')
    c, ix, iy = intersect(items, bs['field_name'])
    if len(c) > 0:
        df.loc[c, 'statement'] = 'BS'
        df.loc[c, 'description'] = bs['description'].iloc[iy].to_numpy()
    c, ix, iy = intersect(items, ins['field_name'])
    if len(c) > 0:
        df.loc[c, 'statement'] = 'IS'
        df.loc[c, 'description'] = ins['description'].iloc[iy].to_numpy()
    c, ix, iy = intersect(items, cf['field_name'])
    if len(c) > 0:
        df.loc[c, 'statement'] = 'CF'
        df.loc[c, 'description'] = cf['description'].iloc[iy].to_numpy()
    c, ix, iy = intersect(items, pen['field_name'])
    if len(c) > 0:
        df.loc[c, 'statement'] = 'PEN'
        df.loc[c, 'description'] = pen['description'].iloc[iy].to_numpy()
    return df


@ft.lru_cache()
def get_all_item_statement_codes():
    query = f"select * from FactSetDataFeed.ff_v3.ff_balance_model"
    conn = md.get_connection()
    try:
        cursor = md.get_cursor(conn)
        cursor.execute(query)
        records = cursor.fetchall()
        rf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        rf['code'] = rf['report_code'].str[:2]
        rf['BS'] = False
        rf['IS'] = False
        rf['CF'] = False
        rf['PEN'] = False
        ix = np.where(rf['code'] == 'BS')
        rf.loc[rf.index[ix], 'BS'] = True
        ix = np.where(rf['code'] == 'IS')
        rf.loc[rf.index[ix], 'IS'] = True
        ix = np.where(rf['code'] == 'CF')
        rf.loc[rf.index[ix], 'CF'] = True
        ix = np.where(rf['code'] == 'PE')
        rf.loc[rf.index[ix], 'PEN'] = True
        return rf
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to get FactSet fundamental balance model meta map: database error")
        conn.close()
        raise dbe
    except Exception as ee:
        display(f"{ee}")
        display(f"Unable to get FactSet fundamental balance model meta map: exception")
        conn.close()
        raise ee


@ft.lru_cache()
def get_all_items(statement=None):
    smap = get_all_item_statement_codes()
    if statement is None:
        return smap[['field_name', 'description']]
    if not isinstance(statement, str):
        raise ValueError(f"statement must be string")
    if statement.upper() == 'BS':
        return smap[smap['BS']].loc[:, ['field_name', 'description']]
    if statement.upper() == 'BS':
        return smap[smap['BS']].loc[:, ['field_name', 'description']]
    if statement.upper() == 'IS':
        return smap[smap['IS']].loc[:, ['field_name', 'description']]
    if statement.upper() == 'CF':
        return smap[smap['CF']].loc[:, ['field_name', 'description']]
    if statement.upper() == 'PEN':
        return smap[smap['PEN']].loc[:, ['field_name', 'description']]
