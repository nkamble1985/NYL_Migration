#
#  data loaders
#     -- establish connection to default database server
#     -- execute arbitrary query
#     -- stock reference query
#     -- stock price/returns/volume/shares outstanding
#     -- stock dividend/corporate actions
#
#
#  Author : Yun Chen
#  Indigo Dao LLC, copyright
#  July 5, 2022
#
# --------------------------------------------------------
import pyodbc as db
import functools as ft
import os
import pandas as pd
import numpy as np
import numbers
import util.utilities as util
from util.utilities import display
from util.intersect import *
from dataloader.portfolio import filter_portfolios
from dataloader.portfolio import get_portfolio_returns

cache = {}
related_map = None
econ_series = None
entity_types = None
merged_entities = None
merged_securities = None
references = None
exchange_securities = None
region_securities = None
exchanges = None
rbics = None
exchange_country = None
primary_share_classes=None


def get_default_db_parameters(sandbox='PROD'):
    """
    return default database parameters; prod is default
    :param sandbox:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 21, 2022

    """
    file = os.path.join(util.default_output_location('util'), 'database_parameters.xlsx')
    if not util.exists(file):
        display(f"Cannot find database parameters: file missing: \n{file}")
        raise FileNotFoundError(file)
    data = pd.read_excel(file)
    data.set_index('Context', inplace=True)
    sandbox = sandbox.upper().strip()
    if sandbox == 'DEV':
        return data.loc['DEV']
    elif sandbox == 'PROD':
        return data.loc['PROD']
    elif sandbox == 'FACTSET':
        return data.loc['FactSet']
    else:
        return data.loc['DEV']


def get_connection(driver=None, server=None, database=None, user=None, password=None, sandbox='PROD'):
    """

    :param driver:
    :param server:
    :param database:
    :param user:
    :param password:
    :param sandbox:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 21, 2022

    """
    param = get_default_db_parameters(sandbox)
    if driver is None:
        driver = param.loc['Driver']
    if server is None:
        server = param.loc['Server']
    if database is None:
        database = param.loc['Database']
    if user is None:
        user = param.loc['User']
    if password is None:
        password = param.loc['Password']
    p_str = f"Driver={{{driver}}};Server={server};Database={database};UID={user};PWD={password};"
    # UID={user};PWD={password}" Trusted_Connection=yes;
    conn = db.connect(p_str)
    return conn


def get_cursor(connection):
    return connection.cursor()


def run_query(conn, sql):
    """

    :param conn:
    :param sql:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 21, 2022
"""
    cursor = get_cursor(conn)
    return cursor.execute(sql)


def execute_batch(conn, sql_base, sec_ids, batch_size=500, drop_duplicate=True, sql_suffix=None):
    """

    :param conn:
    :param sql_base: end in 'where xxxx in'
    :param sec_ids:
    :param batch_size: number of securities per batch
    :param drop_duplicate: default True
    :param sql_suffix: default None
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 21, 2022
    """
    cursor = conn.cursor()
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if hasattr(sec_ids, 'to_numpy'):
        sec_ids = sec_ids.to_numpy()
    sec_ids = np.unique(sec_ids)
    sec_ids = sec_ids[np.where(pd.notnull(sec_ids))[0]]
    if len(sec_ids) == 0:
        return pd.DataFrame()
    num = int(np.ceil(len(sec_ids) / batch_size))
    df = pd.DataFrame()
    st = util.clock()
    row = 0
    sec = 0
    for i in range(num):
        try:
            ids = sec_ids[i * batch_size:(i + 1) * batch_size]
            sql = sql_base + f" ('{ids[0].strip()}'"
            for ix, s in enumerate(ids):
                if ix == 0:
                    continue
                sql = sql + f", '{s.strip()}'"
            sql = sql + f")"
            if sql_suffix is not None and isinstance(sql_suffix, str):
                sql = sql + f" {sql_suffix}"
            at = util.clock()
            cursor.execute(sql)
            et = util.clock()
            records = cursor.fetchall()
            zt = util.clock()
            sf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            df = pd.concat([df, sf], axis=0)
            row = row + len(df.index)
            sec = sec + len(ids)
            display(f"{i:,}-th batch: securities: total {sec:,} (+{len(ids):,}): rows {row:,} (+{len(records):,}): "
                    f"elapsed: {zt - st: .1f} sec (execute: {et - at: .1f}; fetch: {zt - et: .1f}) ")
        except db.DatabaseError as dbe:
            display(dbe)
            display(f"{i}-th batch loading error ")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f"{i}-th batch loading error ")
            raise ee
    qt = util.clock()
    if drop_duplicate:
        df.drop_duplicates(keep='last', inplace=True)
    df.reset_index(inplace=True)
    df.drop(df.columns[0], axis=1, inplace=True)
    display(f"Total {num:,} batches, {len(sec_ids):,} securities, {len(df.index):,} rows: {qt - st: .1f} seconds")
    return df


# -----------------------------------------------------------
#
# Time series loaders
#
# -----------------------------------------------------------

def get_prices(start_date, end_date, sec_ids, calendar_str='US', price_type='CLOSE', fwd_fill_days=None,
               base_currency=None, adjusted=False):
    """
    load local prices or in a given base currency
    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str: default 'US'
    :param price_type:  default 'CLOSE'
    :param fwd_fill_days: default None
    :param base_currency: default None (local prices)
    :param adjusted: default False
    :return:

    Example:
        Input:   local prices
            get_prices(20220701,20220705,'NNKD2Y-R')
        Output:
                        NNKD2Y-R
            2022-07-01    114.05
            2022-07-05    112.62

        Input:   total prices
            get_prices(20220701,20220705,'WFJYTJ-R','GL','CLOSE', None, 'JPY')
        Output:
                prices in JPY
                             WFJYTJ-R
            2022-07-01  295172.662830
            2022-07-04  295285.553515
            2022-07-05  309387.482799

                local prices (which happens to be USD)
                        WFJYTJ-R
            2022-07-01   2181.62
            2022-07-04   2181.62
            2022-07-05   2277.74

                FX rates (USD/JPY)
                          WFJYTJ-R
            2022-07-01  135.299760
            2022-07-04  135.351506
            2022-07-05  135.830904

                security base currency
                                 currency                   name
            WFJYTJ-R      USD  Alphabet Inc. Class C

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: June 1, 2022
    """
    # calendar and dates
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) <= 0:
        display(f" calendar {calendar_str}: no valid business days")
        return None
    p_days = days
    if fwd_fill_days is not None and isinstance(fwd_fill_days, (int, float)):
        fwd_fill_days = int(fwd_fill_days)
        if fwd_fill_days > 0:
            all_days = util.load_business_days(calendar_str, None, end_date)
            ix = np.where(all_days == days[0])[0][0]
            p_days = all_days[ix - fwd_fill_days:]
    # securities
    if sec_ids is None:
        display(f" no valid securities")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if hasattr(sec_ids, 'to_numpy'):
        sec_ids = sec_ids.to_numpy()
    if len(sec_ids) == 0:
        display(f" at least one security ID is needed")
        return None
    sec_ids = np.unique(sec_ids)
    df = pd.DataFrame(np.nan, index=days, columns=sec_ids)  # local prices
    # check price type
    if price_type is None or not isinstance(price_type, str):
        price_type = 'CLOSE'
    price_type = price_type.upper().strip()
    if price_type not in util.PRICE_TYPES:
        display(f" price type: {price_type} not supported: close/open/high/low are accepted")
        raise ValueError('Unsupported price type')
    if price_type == 'LOW':
        v_type = 'PriceLow'
    elif price_type == 'OPEN':
        v_type = 'PriceOpen'
    elif price_type == 'HIGH':
        v_type = 'PriceHigh'
    else:
        v_type = 'PriceClose'
    # check currency
    local = True
    if base_currency is not None:
        if not isinstance(base_currency, str):
            display(f"get_prices: no valid string-type base currency provided; assuming local prices desired")
        else:
            local = False
    # query

    query = f"select Date, SecCode, AliasCode, {v_type} from mkt.Price where " \
            f"Date between '{p_days[0].strftime(util.yyyy_mm_dd_format)}'" \
            f" and '{p_days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f"AliasCode in "
    conn = get_connection()
    try:
        ac = util.clock()
        data = execute_batch(conn, query, sec_ids)
        rc = util.clock()
        data['Date'] = util.parse_date(data['Date'])
        data.drop_duplicates(keep='last', inplace=True)
        zf = data.pivot(index='Date', columns='AliasCode', values=v_type)
        if fwd_fill_days is not None and isinstance(fwd_fill_days, (int, float)):
            if fwd_fill_days > 0:
                zf = pd.DataFrame(util.forward_fill(zf.to_numpy(), fwd_fill_days), index=zf.index, columns=zf.columns)
        df.update(zf)
        fc = util.clock()
        display(f" {len(data.index)} rows of record")
        display(f"executing query took {rc - ac: .1f} Seconds")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        conn.close()
        raise IOError(f'database exception: ')
    if adjusted:
        af = get_adjustment_factors(p_days[0], p_days[-1], sec_ids, calendar_str, ts_flag=True)
        df = df * af
    if local:
        return df
    else:
        cf = get_currencies(sec_ids)
        ccys = np.unique(cf['currency'].to_numpy())
        x_rates = get_exchange_rates(days[0], days[-1], ccys, base_currency, calendar_str)
        xf = pd.DataFrame(1.0, index=days, columns=sec_ids)
        for ccy in x_rates.columns:
            index = np.where(cf['currency'] == ccy)[0]
            if len(index) == 0:
                continue
            sids = cf['sec_id'].iloc[index].to_numpy()
            xf[sids] = np.tile(x_rates[[ccy]].to_numpy(), (1, len(sids)))
        tf = xf * df
        return tf, df, xf, cf


def get_returns(start_date, end_date, sec_ids, calendar_str='GL', base_currency=None):
    """
    get local or total returns in a given currency
    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str: [optional] default 'GL'
    :param base_currency: [optional] None
    :return:

    Example:
        Input:
            get_returns(20220701,20220705,'NNKD2Y-R')
        Output:
                        NNKD2Y-R
            2022-07-01  0.012788
            2022-07-04  0.000000
            2022-07-05 -0.003770

        Input:
            get_returns(20220701,20220705,'WFJYTJ-R','GL','JPY')
        Output:
                        Total returns
                        WFJYTJ-R
            2022-07-01 -0.009741
            2022-07-04  0.000382
            2022-07-05  0.047757
                        Local returns
                        WFJYTJ-R
            2022-07-01 -0.002665
            2022-07-04  0.000000
            2022-07-05  0.044059
                        FX rate of returns
                        WFJYTJ-R
            2022-07-01 -0.007094
            2022-07-04  0.000382
            2022-07-05  0.003542

        Input:
            get_returns(20220701,20220705,['US100', 'WFJYTJ-R'],'GL','JPY')
        Output:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: June 15, 2022
    """
    # calendar and dates
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) <= 0:
        display(f"get_prices: calendar {calendar_str}: no valid business days")
        return None
    # securities
    if sec_ids is None:
        display(f"get_prices: no valid securities")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if hasattr(sec_ids, 'to_numpy'):
        sec_ids = sec_ids.to_numpy()
    if len(sec_ids) == 0:
        display(f"get_prices: at least one security ID is needed")
        return None
    sec_ids = np.unique(sec_ids)
    df = pd.DataFrame(np.nan, index=days, columns=sec_ids)  # local returns
    xf = df.copy(deep=True) # x rates
    portfolios = filter_portfolios(sec_ids)
    kids = np.setdiff1d(sec_ids, portfolios)
    # check currency
    local = True
    if base_currency is not None:
        if not isinstance(base_currency, str):
            display(f"get_returns: no valid string-type base currency provided; assuming local returns desired")
        else:
            local = False

    # portfolio returns
    if len(portfolios) > 0:
        if local:
            pf = get_portfolio_returns(days[0], days[-1], portfolios, calendar_str, base_currency)
            df.update(pf)
        else:
            pf, pl, px = get_portfolio_returns(days[0], days[-1], portfolios, calendar_str, base_currency)
            xf.update(px)
            df.update(pl)

    if len(kids) > 0:
        # query = f"select SecCode, AliasCode, Date, DTD, Currency from mkt.TotalReturns where " \
        #         f"Date between '{days[0].strftime(util.yyyy_mm_dd_format)}' " \
        #         f"AND '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
        #         f"AliasCode in "
        query = f"select fsym_id as AliasCode, p_date as Date, one_day_pct as DTD, currency as Currency " \
                f"from fp_v2.fp_total_returns_daily where " \
                f"p_date between '{days[0].strftime(util.yyyy_mm_dd_format)}' " \
                f"AND '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
                f"fsym_id in "
        # connect to db
        conn = get_connection(database='FactSetDataFeed')
        try:
            ac = util.clock()
            data = execute_batch(conn, query, kids)
            rc = util.clock()
            data['Date'] = util.parse_date(data['Date'])
            mf = data.pivot(index='Date', columns='AliasCode', values='DTD')
            mf = mf / 100
            df.update(mf)
            cf = data[['AliasCode', 'Currency']].copy(deep=True)
            cf.drop_duplicates(subset=['AliasCode'], keep='last', inplace=True)
            cf['Name'] = 1
            currencies = cf.pivot(index='AliasCode', columns='Name', values='Currency')
            fc = util.clock()
            display(f" {len(data.index)} rows of record")
            display(f"executing query took {rc - ac: .1f} Seconds")
            display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds")
            conn.close()
            del cf, data
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to  from database")
            conn.close()
            raise IOError(f'database error: ')
        except Exception as ee:
            display(f"{ee}")
            conn.close()
            raise IOError(f'database exception: ')
        if not local:
            ccys = np.unique(currencies.to_numpy())
            x_rates = get_exchange_rate_returns(days[0], days[-1], ccys, base_currency, calendar_str)
            if x_rates is None:
                display(f"No valid FX rates for {len(ccys)} currencies")
            else:
                for ccy in x_rates.columns:
                    index = np.where(currencies == ccy)[0]
                    if len(index) == 0:
                        continue
                    sids = currencies.index[index].to_numpy()
                    xf[sids] = np.tile(x_rates[[ccy]].to_numpy(), (1, len(sids)))
    if local:
        return df
    else:
        tf = (1 + xf) * (1 + df) - 1
        return tf, df, xf


def get_exchange_rates(start_date, end_date, currencies, base_currency='USD', calendar_str='GL'):
    """
    get daily exchange rates: get_exchange_rates(20220701,20220707, ['EUR','CNY'], 'JPY', 'GL')
    :param start_date:
    :param end_date:
    :param currencies:
    :param base_currency: [ optional ] default 'USD'
    :param calendar_str: [ optional ] default 'GL'
    :return:

    Example:
        Input:
            get_exchange_rats(20220801,20220803,'JPY','USD')
        Output:
                             JPY
            2022-08-01  0.007559
            2022-08-02  0.007636
            2022-08-03  0.007486

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: June 1, 2022

    """
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        display(f"get_exchange_rates: no valid business days: {calendar_str} calendar")
        return None
    if currencies is None:
        display(f"No valid currencies")
        return
    if isinstance(currencies, str):
        currencies = np.array([currencies])
    if isinstance(currencies, list):
        currencies = np.array(currencies)
    if hasattr(currencies, 'to_numpy'):
        currencies = currencies.to_numpy()
    if len(currencies) == 0:
        display(f"get_exchange_rates: no valid currencies")
        return None
    cache_name = 'exchange rates'
    if cache_name not in cache:
        rates = pd.DataFrame()
    else:
        rates = cache[cache_name]
    base_currency = base_currency.strip().upper()
    currencies = np.unique(currencies)
    ccys = np.setdiff1d(currencies, base_currency)
    if len(ccys) == 0:
        df = pd.DataFrame(1.0, index=days, columns=currencies)
        return df
    else:
        df = pd.DataFrame(np.nan, index=days, columns=currencies)
        if 'USD' in currencies:
            df['USD'] = 1.0
    if base_currency != 'USD':
        non_usd = True
    else:
        non_usd = False

    if rates.empty:
        missing = days
    else:
        missing = np.setdiff1d(days, rates['Date'])
    missing.sort(axis=0,)
    if len(missing) > 0:

        if not rates.empty:
            s_date = missing[0]
            e_date = missing[-1]
        else:
            s_date = util.previous_business_days(days[0], calendar_str, 252)
            e_date = util.previous_business_days(days[-1], calendar_str, -252)
            if e_date > util.today():
                e_date = util.most_recent_business_day(calendar_str=calendar_str)
        query = f"select * from mkt.FxRatesUSD x where x.Date between " \
                f"'{s_date.strftime(util.yyyy_mm_dd_format)}' AND " \
                f"'{e_date.strftime(util.yyyy_mm_dd_format)}' AND " \
                f"x.CreatedOn = (select max(CreatedOn) from " \
                f"mkt.FxRatesUsd where Currency=x.Currency and Date = x.Date)"
        display(f"loading exchange rates between {s_date} and {e_date}")
        conn = get_connection()
        cursor = conn.cursor()
        try:
            ct = util.clock()
            cursor.execute(query)
            rt = util.clock()
            records = cursor.fetchall()
            et = util.clock()
            rf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            rf['Date'] = util.parse_date(rf['Date'])
            rf.drop_duplicates(keep='last', inplace=True)
            kt = util.clock()
            rates = rates.combine_first(rf)
            rates.update(rf)
            cache[cache_name] = rates
            display(f"get_exchange_rates: {rt - ct: .1f} sec to execute query; {et - rt: .1f} sec to fetch results; "
                    f"{kt - et: .1f} sec to format into data frame")
            display(f"Added {len(rf.index)}: "
                    f"{len(np.unique(rf['Date']))} days x {len(np.unique(rf['Currency']))} currencies (USD)")
            display(f"Total {len(rates.index)} records: "
                    f"{len(np.unique(rates['Date']))} days x "
                    f"{len(np.unique(rates['Currency']))} currencies (USD)")
            cursor.close()
            conn.close()
        except db.DatabaseError as dbe:
            display(dbe)
            cursor.close()
            conn.close()
        except Exception as ee:
            display(ee)
            cursor.close()
            conn.close()

    index = np.where(np.logical_and(rates['Date'] >= days[0], rates['Date'] <= days[-1]))[0]
    if len(index) == 0:
        display(f"get_exchange_rates: no data found between {days[0]} and {days[-1]}")
        return df
    for ccy in df.columns:
        if ccy == 'USD':
            df[ccy] = 1.0
            continue
        ix = np.intersect1d(index, np.where(rates['Currency'] == ccy)[0])
        if len(ix) == 0:
            display(f"{ccy} not found")
            continue
        # cf = pd.DataFrame(rates['ExchRateUsd'].iloc[ix].to_numpy(), index=rates['Date'].iloc[ix].to_numpy(),
        #                   columns=[ccy])
        cf = rates.iloc[ix].pivot_table('ExchRateUsd', 'Date', 'Currency')
        df.update(cf)
    if non_usd:
        base = get_exchange_rates(days[0], days[-1], base_currency, 'USD', calendar_str)
        bf = pd.DataFrame(np.tile(base.to_numpy(), (1, len(df.columns))), index=base.index, columns=df.columns)
        df = df / bf
    return df


def get_exchange_rate_returns(start_date, end_date, currencies, base_currency='USD', calendar_str='GL'):
    """
    get daily exchange rate returns: get_exchange_rate_returns(20220701,20220707, ['EUR','CNY'], 'JPY', 'GL')
    :param start_date:
    :param end_date:
    :param currencies:
    :param base_currency: [ optional ] default 'USD'
    :param calendar_str:
    :return:

    Example:
        Input:
            get_exchange_rate_returns(20220801,20220803,'EUR','GBP')
        Output:
                             EUR
            2022-08-01 -0.003453
            2022-08-02 -0.000418
            2022-08-03 -0.000430

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: June 15, 2022
    """
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        display(f"get_exchange_rate_returns: no valid business days: {calendar_str} calendar")
        return None
    if currencies is None:
        display(f"No valid currencies")
        return
    if isinstance(currencies, str):
        currencies = np.array([currencies])
    if isinstance(currencies, list):
        currencies = np.array(currencies)
    if hasattr(currencies, 'to_numpy'):
        currencies = currencies.to_numpy()
    if len(currencies) == 0:
        display(f"get_exchange_rates: no valid currencies")
        return None
    base_currency = base_currency.strip().upper()
    currencies = np.unique(currencies)
    p_day = util.previous_business_days(days[0], calendar_str)
    x = get_exchange_rates(p_day, days[-1], currencies, base_currency, calendar_str)
    df = pd.DataFrame(np.exp(np.diff(np.log(x), axis=0)) - 1, index=days, columns=x.columns)
    return df


@ft.lru_cache()
def get_currency_list():
    file = os.path.join(util.default_output_location(), 'macro', 'currencies.xlsx')
    df = pd.read_excel(file)
    return df


@ft.lru_cache()
def get_cash_securities(ccy=None):
    df = get_currency_list()
    if ccy is not None and isinstance(ccy, str):
        index = np.where(df['Currency'] == ccy.upper().strip())[0]
        if len(index) > 0:
            df = df.iloc[index]
    cashes = np.unique(df['SEC_IDS'])
    return cashes.astype('str')


def get_cash_references(cashes=None):
    all_cashes = get_cash_securities()
    if cashes is None:
        cashes = all_cashes
    cashes = util.to_numpy(cashes)
    cashes = np.char.strip(np.char.upper(cashes))
    ix = np.where(np.isin(cashes, all_cashes))[0]
    cashes = cashes[ix]
    df = pd.DataFrame(columns=['sec_id', 'is_active', 'security_id', 'id_type', 'currency', 'region',
                               'region_code', 'listing_id', 'primary_equity_id', 'exchange',
                               'entity_id', 'entity_name', 'entity_type', 'domicile', 'security_type',
                               'universe', 'name', 'is_listing', 'is_regional', 'is_security',
                               'start_date', 'end_date'])
    df['sec_id'] = cashes
    df['entity_id'] = cashes
    df['security_id'] = cashes
    df['is_active'] = 1
    df['entity_type'] = 'SOVEREIGN'
    df['id_type'] = 'CASH'
    df['region'] = 'CASH'
    df['region_code'] = 'CASH'
    df['is_regional'] = 0
    df['is_listing'] = 0
    df['is_security'] = 0
    df['security_type'] = 'CASH'
    df['universe'] = 'CASH'
    df['start_date'] = util.parse_date(19000101)
    df['end_date'] = util.parse_date(99991231)
    for c in df.index:
        cc = df.loc[c, 'sec_id']
        df.loc[c, 'currency'] = cc[-3:]
        df.loc[c, 'name'] = f"{cc[-3:]} CASH"
        df.loc[c, 'entity_name'] = f"{cc[-3:]} CASH"
    return df


def get_cash_tickers(cashes=None):
    all_cashes = get_cash_securities()
    if cashes is None:
        cashes = all_cashes
    cashes = util.to_numpy(cashes)
    cashes = np.char.strip(np.char.upper(cashes))
    ix = np.where(np.isin(cashes, all_cashes))[0]
    cashes = cashes[ix]
    df = pd.DataFrame(columns=['sec_id', 'ticker_region', 'start_date', 'end_date', 'most_recent'])
    df['sec_id'] = cashes
    df['ticker_region'] = cashes
    df['most_recent'] = True
    df['start_date'] = util.parse_date(19000101)
    df['end_date'] = util.parse_date(99991231)
    return df


def is_cash(ccy=None):
    if ccy is None:
        return None
    cf = get_currency_list()
    if isinstance(ccy, str):
        ccy = ccy.strip().upper()
        return ccy in cf['Currency'].to_list() or ccy in cf['SEC_IDS'].to_list()
    else:
        ccy = util.to_numpy(ccy)
        result = np.array([False]*len(ccy))
        currencies = cf['Currency'].to_list()
        sids = cf['SEC_IDS'].to_list()
        for ix, c in enumerate(ccy):
            cy = c.strip().upper()
            result[ix] = cy in currencies or cy in sids
        return result


def get_market_cap(start_date, end_date, sec_ids, calendar_str='US', cap_type=None, base_currency=None):
    """

    Parameters
    ----------
    start_date
    end_date
    sec_ids
    calendar_str
    cap_type
    base_currency

    Returns
    -------
    cap_rebased: T x N in a given base currency
    cap_local:   T x N in local currencies
    exchange_rates: T x N exchanged rates
    currency: dataframe N x 1, currencies

    """
    if cap_type is None or not isinstance(cap_type, str):
        ct = 'sharesout'
    else:
        if cap_type.lower().strip() in ('shares', 'share', 'sharesout', 'sharesoutstanding', 'market'):
            ct = 'sharesout'
        else:
            ct = None
    if ct is None:
        return get_entity_market_cap(start_date, end_date, sec_ids, calendar_str, cap_type, base_currency)
    if base_currency is None:
        base_currency = 'USD'
    sec_ids = util.to_numpy(sec_ids)
    if len(sec_ids) == 0:
        display(f"No valid sec_ids are provided")
        return None
    days = util.load_business_days(calendar_str, start_date, end_date)
    ref = get_references(sec_ids, start_date=days[0], end_date=days[-1])
    missing = np.setdiff1d(sec_ids, ref['sec_id'])
    primaries = get_primary_equity_share_classes(sec_ids, start_date=days[0], end_date=days[-1])
    sids = np.union1d(missing, primaries['sec_id'])
    tf, df, xf, currencies = get_shares_x_price_market_cap(start_date, end_date, sids, calendar_str, base_currency)
    rf = pd.DataFrame(index=tf.index, columns=sec_ids)
    if len(missing) > 0 :
        x = np.intersect1d(missing, tf.columns)
        rf.loc[rf.index, x] = tf.loc[rf.index, x]
    for i in ref.index:
        s = ref.loc[i, 'sec_id']
        e = ref.loc[i, 'entity_id']
        ix = np.where(primaries['entity_id'] == e)[0]
        if len(ix) == 0:
            continue
        ids = primaries.loc[primaries.index[ix], 'sec_id'].to_numpy()
        x = np.intersect1d(tf.columns, ids)
        if len(x) == 0:
            continue
        rf.loc[rf.index, s] = tf.loc[rf.index, x].sum(axis=1).to_numpy()
        all_null = np.where(pd.notnull(tf.loc[rf.index, x]).sum(axis=1) == 0)[0]
        if len(all_null) > 0 :
            rf.loc[rf.index[all_null], s] = np.nan
    return rf


def get_entity_market_cap(start_date, end_date, sec_ids, calendar_str='US', cap_type=None, base_currency=None):
    """
    get market capitalization

    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str:
    :param cap_type: 'MV', 'MVExNonTraded', 'MVExNonTradedTreasury', 'MVExTreasury', default 'MV'
    :param base_currency: default USD
    :return:
        :cap_rebased: T x N in a given base currency
        :cap_local:   T x N in local currencies
        :exchange_rates: T x N exchanged rates
        :currency: dataframe N x 1, currencies

    Example:
        Input: get Citi Bank's entity market cap in GBP
            get_entity_market_cap(20220701, 20220701, 'RK3DL5-R', 'US', 'MV', 'GBP')
        Output:
                    RK3DL5-R
        2022-07-01  119101.221148,
                    RK3DL5-R
        2022-07-01  143295.890323,
                    RK3DL5-R
        2022-07-01  0.831156
                    Currency
        RK3DL5-R  'USD'


    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 12, 2022
    """
    # calendar and dates
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) <= 0:
        display(f" calendar {calendar_str}: no valid business days")
        return None
    # securities
    if sec_ids is None:
        display(f" no valid securities")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" at least one security ID is needed")
        return None
    sec_ids = np.unique(sec_ids)
    df = pd.DataFrame(np.nan, index=days, columns=sec_ids)  # local market cap
    # check price type
    if cap_type is None or not isinstance(cap_type, str):
        cap_type = 'MV'
    cap_type = cap_type.upper().strip()
    if cap_type not in ('MV', 'MVExNonTraded', 'MVExNonTradedTreasury', 'MVExTreasury'):
        raise ValueError(f" {cap_type}: not supported")
    if base_currency is None or not isinstance(base_currency, str):
        base_currency = 'USD'

    query = f"select mv.SecCode, sa.AliasCode as AliasCode, mv.{cap_type}, mv.Date, mv.Currency as Currency from " \
            f"mkt.MarketValue as mv inner join sec.SecAlias as sa on sa.SecCode = mv.SecCode where " \
            f"mv.Date between '{days[0].strftime(util.yyyy_mm_dd_format)}'" \
            f" and '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f" sa.AliasCode in "
    # connect to db
    conn = get_connection()
    try:
        ac = util.clock()
        mf = execute_batch(conn, query, sec_ids)
        mf['Date'] = util.parse_date(util.parse_date(mf['Date']))
        ec = util.clock()
        zf = mf.pivot(index='Date', columns='AliasCode', values=cap_type)
        df.update(zf)
        cf = mf[['AliasCode', 'Currency']].copy(deep=True)
        cf.drop_duplicates(inplace=True)
        cf['Name'] = 'Currency'
        currencies = cf.pivot(index='AliasCode', columns='Name', values='Currency')
        fc = util.clock()
        df = df * 1e6
        display(f" {len(mf.index)} rows of record")
        display(f"executing query took {ec - ac: .1f} Seconds")
        display(f"reformatting to DataFrame took {fc - ec: .1f} Seconds")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        conn.close()
        raise IOError(f'database exception: ')

    ccys = np.unique(currencies.to_numpy())
    if len(ccys) == 1 and ccys[0] == 'USD' and ccys == 'USD' and base_currency == 'USD':
        xf = pd.DataFrame(1.0, index=df.index, columns=df.columns)
        display(f"All in USD")
        return df, df, xf, currencies
    else:
        x_rates = get_exchange_rates(days[0], days[-1], ccys, base_currency, calendar_str)
        xf = pd.DataFrame(1.0, index=days, columns=sec_ids)
        for ccy in x_rates.columns:
            index = np.where(currencies == ccy)[0]
            if len(index) == 0:
                continue
            sids = currencies.index[index].to_numpy()
            xf[sids] = np.tile(x_rates[[ccy]].to_numpy(), (1, len(sids)))
        tf = xf * df
        return tf, df, xf, currencies


def get_shares_x_price_market_cap(start_date, end_date, sec_ids, calendar_str='US', base_currency=None):
    """

    Parameters
    ----------
    start_date
    end_date
    sec_ids
    calendar_str
    base_currency

    Returns
    -------
    cap_rebased: T x N in a given base currency
    cap_local:   T x N in local currencies
    exchange_rates: T x N exchanged rates
    currency: dataframe N x 1, currencies

    """
    if base_currency is None:
        base_currency = 'USD'
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    elif isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    shares = get_shares_outstanding(start_date, end_date, sec_ids, calendar_str)
    prices = get_prices(start_date, end_date, sec_ids, calendar_str)
    sids = np.intersect1d(shares.columns, prices.columns)
    days = np.intersect1d(shares.index, prices.index)
    df = prices.loc[days, sids] * shares.loc[days, sids]
    currencies = get_currencies(sids)
    currencies = currencies[['sec_id', 'currency']]
    currencies.set_index('sec_id', inplace=True)
    ccys = np.unique(currencies.to_numpy())
    if len(ccys) == 1 and ccys[0] == 'USD' and ccys == 'USD' and base_currency == 'USD':
        xf = pd.DataFrame(1.0, index=df.index, columns=df.columns)
        display(f"All in USD")
        return df, df, xf, currencies
    else:
        x_rates = get_exchange_rates(days[0], days[-1], ccys, base_currency, calendar_str)
        xf = pd.DataFrame(1.0, index=days, columns=df.columns)
        for ccy in x_rates.columns:
            index = np.where(currencies == ccy)[0]
            if len(index) == 0:
                continue
            ids = currencies.index[index].to_numpy()
            xf[ids] = np.tile(x_rates[[ccy]].to_numpy(), (1, len(ids)))
        tf = xf * df
        return tf, df, xf, currencies


def get_shares_outstanding(start_date, end_date, sec_ids, calendar_str='GL'):
    """
    get shares outstanding

    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str: [optional] default 'GL'
    :return:

    Example:
        Input:
            get_shares_outstanding(20220801,20220804, 'RK3DL5-R')
        Output:
                        RK3DL5-R
            2022-08-01  109829000.0
            2022-08-02  109829000.0
            2022-08-03  109829000.0
            2022-08-04  109829000.0

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 12, 2022

    """
    # calendar and dates
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) <= 0:
        display(f" calendar {calendar_str}: no valid business days")
        return None
    # securities
    if sec_ids is None:
        display(f" no valid securities")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if hasattr(sec_ids, 'to_numpy'):
        sec_ids = sec_ids.to_numpy()
    if len(sec_ids) == 0:
        display(f" at least one security ID is needed")
        return None
    sec_ids = np.unique(sec_ids)
    df = pd.DataFrame(np.nan, index=days, columns=sec_ids)  # local prices
    # query
    query = f"select * from mkt.ShareOutstanding where " \
            f"Date <= '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f"AliasCode in "
    suffix = 'ORDER by AliasCode, Date'
    # connect to db
    conn = get_connection()
    try:
        ac = util.clock()
        data = execute_batch(conn, query, sec_ids, sql_suffix=suffix)
        rc = util.clock()
        data['Date'] = util.parse_date(data['Date'])
        data['Shares'] = data['Shares'] * 1000
        fc = util.clock()
        display(f" {len(data.index)} rows of record")
        display(f"executing query took {rc - ac: .1f} Seconds")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        conn.close()
        raise IOError(f'database exception: ')
    sids = np.unique(data['AliasCode'])
    for s in sids:
        ix = np.where(data['AliasCode'] == s)[0]
        if len(ix) == 0:
            continue
        s_dates = data['Date'].iloc[ix].to_numpy()
        s_values = data['Shares'].iloc[ix].to_numpy()
        for iz, sd in enumerate(s_dates):
            index = np.where(days >= sd)[0]
            if iz < len(s_dates) - 1:
                index = np.intersect1d(index, np.where(days < s_dates[iz+1])[0])
            if len(index) == 0:
                continue
            df.loc[df.index[index], s] = np.array([s_values[iz]] * len(index))
    return df


def get_volume(start_date, end_date, sec_ids, calendar_str='US'):
    """
    get trading volume

    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str:
    :return:
        :volume: T x N in a given base currency

    Example:
        Input:
            get_volume(20220801,20220804, 'RK3DL5-R')
        Output:
                         RK3DL5-R
            2022-08-01  13051.780
            2022-08-02  17378.471
            2022-08-03  13570.580
            2022-08-04  10152.190

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 2, 2022

    """
    # calendar and dates
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) <= 0:
        display(f" calendar {calendar_str}: no valid business days")
        return None
    # securities
    if sec_ids is None:
        display(f" no valid securities")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if hasattr(sec_ids, 'to_numpy'):
        sec_ids = sec_ids.to_numpy()
    if len(sec_ids) == 0:
        display(f" at least one security ID is needed")
        return None
    sec_ids = np.unique(sec_ids)
    df = pd.DataFrame(np.nan, index=days, columns=sec_ids)  # volume
    query = f"select Date, SecCode, AliasCode, Volume from mkt.Price where " \
            f"Date between '{days[0].strftime(util.yyyy_mm_dd_format)}'" \
            f" and '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f"AliasCode in "
    # connect to db
    conn = get_connection()
    try:
        ac = util.clock()
        mf = execute_batch(conn, query, sec_ids)
        rc = util.clock()
        mf['Date'] = util.parse_date(mf['Date'])
        zf = mf.pivot(index='Date', columns='AliasCode', values='Volume')
        df.update(zf)
        fc = util.clock()
        df = df * 1000
        display(f" {len(mf.index)} rows of record")
        display(f"executing query took {rc - ac: .1f} Seconds")
        display(f"reformatting to DataFrame took {fc - rc: .1f} Seconds")
        conn.close()
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to get_prices from database")
        conn.close()
        raise IOError(f'database error: get_prices')
    except Exception as ee:
        display(f"{ee}")
        conn.close()
        raise IOError(f'database exception: ')
    return df

# -----------------------------------------------------------
#
# corporate actions: dividend, splits
#
# -----------------------------------------------------------


def get_splits(start_date, end_date, sec_ids, calendar_str='GL'):
    """
    get split adjustment factors by dates between dates for a list of securities

    :param start_date: inclusive
    :param end_date: inclusive
    :param sec_ids: security identifiers such as 'VLHKF9-R'
    :param calendar_str: default 'GL'
    :return:

    Example:
        Input:
            get_splits(20110101, 20110731, 'RK3DL5-R')
        Output:
              security_id   sec_ids        Date  SplitFactor
            0    T6BMPP-S  RK3DL5-R  2011-05-09         10.0

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 2, 2022
    """
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        display(f" calendar {calendar_str} no valid business days")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" no valid securities")
        return None
    query = f"select SecCode, AliasCode, Date, SplitFactor from ca.StockSplit where Date between " \
            f"'{days[0].strftime(util.yyyy_mm_dd_format)}' and '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f"AliasCode in "
    conn = get_connection()
    try:
        at = util.clock()
        df = execute_batch(conn, query, sec_ids)
        et = util.clock()
        display(f" {et - at: .1f} seconds to execute query: {len(df.index)} rows")
        conn.close()
        df['Date'] = util.parse_date(df['Date'].to_numpy())
        df.rename(columns={'AliasCode': 'sec_ids', 'SecCode': 'security_id'}, inplace=True)
    except db.DatabaseError as dbe:
        display(dbe)
        display(f" Cannot retrieve due to database error")
        conn.close()
        raise dbe
    except Exception as ee:
        display(ee)
        display(f" Cannot retrieve due to exception")
        conn.close()
        raise ee
    return df


def get_adjustment_factors(start_date, end_date, sec_ids, calendar_str='GL', ts_flag=False):
    """
    get cumulative adjustment factors between two dates, inclusive of both end points

    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str:
    :param ts_flag: default False
    :return:

    Example:
        Input:
            get_adjustment_factors(20220101, 20220731, 'NNKD2Y-R')
        Output:
                      values
            NNKD2Y-R     1.0

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 1, 2022
    """
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        display(f" calendar {calendar_str} no valid business days")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" no valid securities")
        return None
    sec_ids = np.unique(sec_ids)
    df = pd.DataFrame(1.0, index=sec_ids, columns=['values'])
    splits = get_splits(days[0], days[-1], sec_ids, calendar_str)
    if splits is None:
        return df
    if splits.empty:
        return df
    sids = np.unique(splits['sec_ids'].to_numpy())
    if not ts_flag:
        for s in sids:
            ix = np.where(splits['sec_ids'] == s)[0]
            f = np.prod(splits['SplitFactor'].iloc[ix].to_numpy())
            df.loc[s] = f
        return df
    else:
        tf = pd.DataFrame(1.0, index=days, columns=sec_ids)
        for s in sids:
            ix = np.where(splits['sec_ids'] == s)[0]
            f = splits['SplitFactor'].iloc[ix].to_numpy()
            t = splits['Date'].iloc[ix].to_numpy()
            for i1, d in enumerate(t):
                zx = np.where(tf.index < d)[0]
                if len(zx) == 0:
                    continue
                tf.loc[tf.index[zx], s] *= f[i1]
        return tf


def get_dividends(start_date, end_date, sec_ids, calendar_str='GL'):
    """
    get cash dividends between two dates for a list of securities

    :param start_date:
    :param end_date:
    :param sec_ids:
    :param calendar_str:
    :return:
        data: dict, sec_id as key
    Example:
        Input:
            get_dividends(20220101,20220731, 'NNKD2Y-R')
        Output:
                    Id security_id  ... ModifiedBy              ModifiedOn
            0  3033038    N5N6M6-S  ...         sa 2022-07-14 07:48:54.827
            1  3033039    N5N6M6-S  ...         sa 2022-07-14 07:48:54.827
            2  3033040    N5N6M6-S  ...         sa 2022-07-14 07:48:54.827
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: June 1, 2022
    """
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        display(f" calendar {calendar_str} no valid business days")
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" no valid securities")
        return None
    sec_ids = np.unique(sec_ids)
    query = f"select * from ca.Dividend where ExDate between " \
            f"'{days[0].strftime(util.yyyy_mm_dd_format)}' and '{days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f"AliasCode in "
    conn = get_connection()
    try:
        at = util.clock()
        df = execute_batch(conn, query, sec_ids)
        et = util.clock()
        display(f"{et - at: .1f} seconds to execute query: {len(df.index)} rows")
        conn.close()
        df['ExDate'] = util.parse_date(df['ExDate'].to_numpy())
        df['PayDate'] = util.parse_date(df['PayDate'].to_numpy())
        df['RecDate'] = util.parse_date(df['RecDate'].to_numpy())
    except db.DatabaseError as dbe:
        display(dbe)
        display(f" Cannot retrieve due to database error")
        conn.close()
        raise dbe
    except Exception as ee:
        display(ee)
        display(f" Cannot retrieve due to exception")
        conn.close()
        raise ee
    df.rename(columns={'SecCode': 'security_id', 'AliasCode': 'sec_ids'}, inplace=True)
    return df


def get_spun_offs(ex_date, sec_ids, database="FactSetDataFeed"):
    """
    get spun-offs by a given date and a list of parent companies
    Parameters
    ----------
    ex_date
    sec_ids
    database

    Returns
    -------

    """
    exd = util.parse_date(ex_date)
    query = f"SELECT div.fsym_id, div.p_divs_exdate, div.p_divs_pd_id, div.p_divs_pd,\n"
    query += f"div.currency, div.p_divs_paydatec, dsym.factset_entity_id, dchg.factset_entity_id "
    query += f"as spun_off_entity_id, scov.fref_security_type, scov.fsym_regional_id, \n"
    query += f"spun1.fsym_id as security_id, tent.entity_proper_name as spun_off_entity \n"
    query += f"FROM fp_v2.fp_basic_dividends div \n"
    query += f"LEFT JOIN sym_v1.sym_coverage dcov on dcov.fsym_id = div.fsym_id \n"
    query += f"LEFT JOIN sym_v1.sym_sec_entity dsym on dsym.fsym_id = dcov.fsym_security_id \n"
    query += f"LEFT JOIN ent_v1.ent_entity_changes dchg on dchg.old_value = dsym.factset_entity_id \n"
    query += f"LEFT JOIN sym_v1.sym_entity tent on dchg.factset_entity_id = tent.factset_entity_id \n"
    query += f"LEFT JOIN sym_v1.sym_sec_entity spun1 on dchg.factset_entity_id = spun1.factset_entity_id \n"
    query += f"LEFT JOIN ent_v1.ent_entity_changes tchg on tchg.factset_entity_id = dchg.factset_entity_id \n"
    query += f"LEFT JOIN ent_v1.ent_entity_changes tchg2 on tchg2.factset_entity_id = dchg.new_value \n"
    query += f"LEFT JOIN sym_v1.sym_coverage scov on scov.fsym_security_id = spun1.fsym_id \n"
    query += f"where div.p_divs_s_spinoff = '1' and tchg.change_type = 'entity_type' \n"
    query += f"and spun1.fsym_id is not NULL and scov.fref_security_type = 'SHARE' \n"
    query += f"and scov.fsym_regional_id is not NULL \n"
    query += f"and div.p_divs_exdate = '{exd.strftime(util.YY_MM_DD_format)}' \n"
    query += f"and (tchg2.change_type is NULL or tchg2.change_type = 'entity_type') and div.fsym_id in "

    suffix = f"order by p_divs_exdate"
    try:
        conn = get_connection(database=database)
        df = execute_batch(conn, query, sec_ids, sql_suffix=suffix)
    except ValueError as ve:
        display(f"Unable to get spun off entities due to value error {ve}")
        raise ve
    except db.DatabaseError as dbe:
        display(f"Unable to get spun off entities due to database error {dbe}")
        raise dbe
    return df

# -----------------------------------------------------------
#
# security reference loaders
#
# -----------------------------------------------------------


def get_references(sec_ids=None, fields=None, active_only=False, dates=None, database='FactSetDataFeed',
                   start_date=None, end_date=None, keep_latest=False):
    """
    get domicile of the firms
    :param sec_ids:
    :param fields: None
    :param active_only: False
    :param dates: default NOne
    :param database: default 'FactSetDataFeed'
    :param start_date: default None
    :param end_date: default None
    :param keep_latest: default False
    :return:
        is_active:      0 or 1, 1 for active securities
        security_id:    such as 'N5N6M6-S'
        id_type:        Regional, Security, Listing
        currency:       ISO currency code such as USD
        ticker:         ticker-region combination such as JPM-US
        region:         such as 'AMER
        region_code:    such as 'AMER'
        listing_id:     primary listing ID, such as DPZZHX-L
        exchange:       primary exchange, such as NYS or NAS
        entity_name:    such as 'JPMorgan Chase & Co.'
        entity_type:    such as 'PUB'
        domicile:       such as 'US
        security_type:  such as 'SHARE'
        universe:       string for asset class, such as 'EQ' for equity
        name:           issue name such as 'JPMorgan Chase & Co.'
        is_listing:     default 0
        is_regional:    default 0
        is_security:    default 0
        start_date:     datetime object
        end_date:       datetime object

    examples:
        Input:
            ref = get_references('NNKD2Y-R')
        output:
            ref
                    is_active security_id  ... universe                  name
            NNKD2Y-R         1    N5N6M6-S  ...       EQ  JPMorgan Chase & Co.

    Examples:
        Input:
            get_references('HTM0LK-R')
        Output:
                     domicile                    name
            HTM0LK-R       US   Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: IndigoDao LLC
    Date: July 29, 2022
    Modified: April 25, 2023
    """
    global references
    if sec_ids is None:
        return references
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if hasattr(sec_ids, 'to_numpy'):
        sec_ids = sec_ids.to_numpy()
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    cash_ref = get_cash_references()
    if references is None:
        references = cash_ref
    if references is None or len(references) == 0:
        missing = sec_ids
    else:
        ix = np.where(pd.notnull(references['sec_id']))[0]
        missing = np.setdiff1d(sec_ids, references['sec_id'].iloc[ix])
    if len(missing) > 0:
        missing = np.unique(missing)
        query = f"select sc.fsym_regional_id as sec_id, sc.active_flag as is_active, "
        query += f"sc.fsym_security_id as security_id, 'Regional' as id_type, sc.currency, sr.region as region, "
        query += f"'NA' as region_code, sc.fsym_primary_listing_id as listing_id, "
        query += f"sc.fsym_primary_equity_id as primary_equity_id,"
        query += f"sc.fref_listing_exchange as exchange, se.factset_entity_id as entity_id, "
        query += f"se.entity_proper_name as entity_name, se.entity_type, se.iso_country as domicile, "
        query += f"sc.fref_security_type as security_type, sc.universe_type as universe, "
        query += f"se.entity_proper_name as name, "
        query += f"sc.listing_flag as is_listing, sc.regional_flag as is_regional, sc.security_flag as is_security, "
        query += f"sh.start_date, sh.end_date "
        query += f"from sym_v1.sym_entity se inner join sym_v1.sym_sec_entity_hist sh "
        query += f"on se.factset_entity_id = sh.factset_entity_id inner join "
        query += f"sym_v1.sym_coverage sc on sh.fsym_id = sc.fsym_primary_equity_id join "
        query += f"sym_v1.sym_region sr on sr.fsym_id = sc.fsym_id "
        query += f"where sc.currency is not NULL and sc.fsym_primary_listing_id is not NULL "
        query += f"and sc.fsym_regional_id is not NULL and sc.fref_listing_exchange is not NULL "
        query += f"and sc.fsym_security_id in (select ssc.fsym_security_id from sym_v1.sym_coverage ssc "
        query += f"where ssc.fsym_id in "
        suffix = f")"
        try:
            conn = get_connection(database=database)
            df = execute_batch(conn, query, missing, 5000, True, suffix)
            conn.close()
            if not df.empty:
                df['name'] = df['entity_name']
                df['region_code'] = df['region']
                df.loc[df.index, 'start_date'] = util.parse_date(df['start_date'].to_numpy())
                df.loc[df.index, 'end_date'] = util.parse_date(df['end_date'].to_numpy())
                ix = np.where(pd.isnull(df['end_date']))[0]
                if len(ix) > 0 :
                    df.loc[df.index[ix], 'end_date'] = util.parse_date(99991231)
                df['id_type'] = None
                ix = np.where(df['is_listing'] == 1)[0]
                if len(ix) > 0:
                    df.loc[df.index[ix], 'id_type'] = 'Listing'
                ix = np.where(df['is_regional'] == 1)[0]
                if len(ix) > 0:
                    df.loc[df.index[ix], 'id_type'] = 'Regional'
                ix = np.where(df['is_security'] == 1)[0]
                if len(ix) > 0:
                    df.loc[df.index[ix], 'id_type'] = 'Security'
                ix = np.where(df['end_date'] < util.parse_date(99991231))[0]
                if len(ix) > 0:
                    df.loc[df.index[ix], 'is_active'] = 0
                df.reset_index(drop=True, inplace=True)
                if references is None:
                    references = df
                else:
                    references = pd.concat((references, df), axis=0, ignore_index=True)
                    references.drop_duplicates(keep='last', inplace=True, ignore_index=True)
                references.drop_duplicates(keep='last', inplace=True)
                references.reset_index(drop=True, inplace=True)
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get references")
            if not conn.closed:
                conn.close()
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get references")
            if not conn.closed:
                conn.close()
            raise ee
    if references is None:
        return references
    ix = np.where(np.isin(references['sec_id'].to_numpy(), sec_ids))[0]
    if dates is not None:
        days = util.parse_date(dates)
        if not isinstance(days, np.ndarray):
            iy = np.where(np.logical_and(references['start_date'] <= days, references['end_date'] > days))[0]
        else:
            if len(dates) != len(sec_ids):
                raise ValueError(f"get_domiciles: dates and sec_ids are not identical in length")
            iy = np.array([])
            for dx, d in enumerate(days):
                iz = np.where(np.logical_and(references['start_date'] <= d, references['end_date'] > d))[0]
                jz = np.where(references['sec_id'] == sec_ids[dx])[0]
                iz = np.intersect1d(iz, jz)
                if len(iz) > 0:
                    iy = np.union1d(iy, iz)
        ix = np.intersect1d(ix, iy)
    if active_only is not None:
        if isinstance(active_only, bool):
            if active_only:
                iy = np.where(references['is_active'] == 1)[0]
                ix = np.intersect1d(ix, iy)
    if start_date is not None:
        sd = util.parse_date(start_date)
        iz = np.where(~(references['end_date'] <= sd))[0]
        ix = np.intersect1d(ix, iz)
    if end_date is not None:
        sd = util.parse_date(end_date)
        iz = np.where(~(references['start_date'] > sd))[0]
        ix = np.intersect1d(ix, iz)
    ref = references.iloc[ix].copy()
    if fields is not None:
        if isinstance(fields, str):
            fields = np.array([fields])
        elif isinstance(fields, list):
            fields = np.array(fields)
        missing = np.setdiff1d(fields, references.columns)
        f = np.intersect1d(fields, references.columns)
        if 'sec_id' not in f:
            f = np.append(['sec_id'], f)
        ref = ref[f]
        if len(missing) > 0:
            display(f"Requested {len(fields)} fields: {len(missing)} missing")
    if keep_latest:
        ref.sort_values(by=['sec_id', 'end_date'], inplace=True)
        ref.drop_duplicates(subset=['sec_id'], keep='last', inplace=True)
    return ref.reset_index(drop=True)


# def get_stock_references(sec_ids=None, fields=None, active_only=True, dates=None, database='FactSetDataFeed'):
#     """
#     get reference information for securities
#
#     :param sec_ids: regional ID or listing ID
#     :param fields: [ optional ]: any combination of the output fields
#     :param active_only: [ optional ]: default True
#     :param dates: [optional]
#     :param database: [optional] default FactSetDataFeed
#     :return:
#         is_active:      0 or 1, 1 for active securities
#         security_id:    such as 'N5N6M6-S'
#         id_type:        Regional, Security, Listing
#         currency:       ISO currency code such as USD
#         ticker:         ticker-region combination such as JPM-US
#         region:         such as 'AMER
#         region_code:    such as 'AMER'
#         listing_id:     primary listing ID, such as DPZZHX-L
#         exchange:       primary exchange, such as NYS or NAS
#         sedol:          SEDOL string such as 2190385
#         cusip:          CUSIP string such as 46625H100
#         ISIN:           ISIN string such as US56625H1005
#         bloomberg_id:   bloomberg unique ID, such as BBG001S8CRC3
#         bloomberg_ticker:   bloomberg ticker, such as GOOGL US
#         entity_name:    such as 'JPMorgan Chase & Co.'
#         entity_type:    such as 'PUB'
#         domicile:       such as 'US
#         security_type:  such as 'SHARE'
#         universe:       string for asset class, such as 'EQ' for equity
#         name:           issue name such as 'JPMorgan Chase & Co.'
#
#     examples:
#         Input:
#             ref = get_stock_references('NNKD2Y-R')
#         output:
#             ref
#                     is_active security_id  ... universe                  name
#             NNKD2Y-R         1    N5N6M6-S  ...       EQ  JPMorgan Chase & Co.
#
#     Author: Yun Chen
#     Copyright: Indigo Dao, LLC
#     Date: July 29, 2022
#     """
#     if sec_ids is None:
#         if 'stock reference' in cache:
#             return cache['stock reference']
#         else:
#             return None
#     if isinstance(sec_ids, str):
#         sec_ids = np.array([sec_ids])
#     if isinstance(sec_ids, list):
#         sec_ids = np.array(sec_ids)
#     if len(sec_ids) == 0:
#         if 'stock reference' in cache:
#             return cache['stock reference']
#         else:
#             return None
#     if not isinstance(active_only, bool):
#         active_only = True
#     sec_ids = np.unique(sec_ids)
#     ref = get_references(sec_ids, None, False, dates, database)
#     # tickers
#     df = get_tickers(sec_ids, table_flag=True)
#     ix = np.where(df['most_recent'])[0]
#     df = df.loc[df.index[ix], ['sec_id', 'ticker_region']]
#     df.rename(columns={'ticker_region': 'ticker'}, inplace=True)
#     df.set_index('sec_id', inplace=True)
#     ref = ref.merge(df, how='left', left_index=True, right_index=True)
#     del df
#     # cusips
#     df = get_cusips(sec_ids, table_flag=True)
#     ix = np.where(df['most_recent'])[0]
#     df = df.loc[df.index[ix], ['sec_id', 'cusip']]
#     df.set_index('sec_id', inplace=True)
#     ref = ref.merge(df, how='left', left_index=True, right_index=True)
#     del df
#     # sedols
#     df = get_sedols(sec_ids, table_flag=True)
#     ix = np.where(df['most_recent'])[0]
#     df = df.loc[df.index[ix], ['sec_id', 'sedol']]
#     df.set_index('sec_id', inplace=True)
#     ref = ref.merge(df, how='left', left_index=True, right_index=True)
#     del df
#     # bbg
#     df = get_bloomberg_ids(sec_ids, True, table_flag=True)
#     ix = np.where(df['most_recent'])[0]
#     df = df.loc[df.index[ix], ['sec_id', 'bbg_id']]
#     df.set_index('sec_id', inplace=True)
#     ref = ref.merge(df, how='left', left_index=True, right_index=True)
#     del df
#     df = get_bloomberg_tickers(sec_ids, True, table_flag=True)
#     ix = np.where(df['most_recent'])[0]
#     df = df.loc[df.index[ix], ['sec_id', 'bbg_ticker']]
#     df.set_index('sec_id', inplace=True)
#     ref = ref.merge(df, how='left', left_index=True, right_index=True)
#     del df
#     # isins
#     df = get_isins(sec_ids, table_flag=True)
#     ix = np.where(df['most_recent'])[0]
#     df = df.loc[df.index[ix], ['sec_id', 'isin']]
#     df.set_index('sec_id', inplace=True)
#     ref = ref.merge(df, how='left', left_index=True, right_index=True)
#     del df
#
#     ref.drop_duplicates(keep='last', inplace=True)
#     ids = np.intersect1d(sec_ids, ref.index)
#     if fields is None:
#         return ref.loc[ids]
#     else:
#         if isinstance(fields, str):
#             fields = np.array([fields])
#         if isinstance(fields, list):
#             fields = np.array(fields)
#         ref = ref.loc[ids, fields]
#         ref.drop_duplicates(keep='last', inplace=True)
#         return ref


def get_currencies(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get base currencies for a regional ID
    :param sec_ids:
    :param dates:
    :param database: FactSetDataFeed
    :return:

    Example:
        Input:
            get_currencies('HTM0LK-R')
        Output:
                     currency                   name
            HTM0LK-R      USD  Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 1, 2022
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    currencies = ref[['sec_id', 'currency', 'name', 'start_date', 'end_date']]
    return currencies


def get_domiciles(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get domicile of the firms
    :param sec_ids:
    :param dates: default NOne
    :param database: default 'FactSetDataFeed'
    :return: dict of strings

    Examples:
        Input:
            get_domiciles('HTM0LK-R')
        Output:
                     domicile                    name
            HTM0LK-R       US   Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: IndigoDao LLC
    Date: July 29, 2022
    Modified: April 25, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    return ref[['sec_id', 'domicile', 'name', 'start_date', 'end_date']]
    # global domiciles
    # if domiciles is None:
    #     missing = sec_ids
    # else:
    #     missing = np.setdiff1d(sec_ids, domiciles['sec_id'])
    # if len(missing) > 0:
    #     missing = np.unique(missing)
    #     query = f"select sc.fsym_regional_id as sec_id, sc.active_flag as is_active, "
    #     query += f"sc.fsym_security_id as security_id, 'Regional' as id_type, sc.currency, sr.region as region, "
    #     query += f"'NA' as region_code, sc.fsym_primary_listing_id as listing_id, "
    #     query += f"sc.fref_listing_exchange as exchange, se.factset_entity_id as entity_id, "
    #     query += f"se.entity_proper_name as entity_name, se.entity_type, se.iso_country as domicile, "
    #     query += f"sc.fref_security_type as security_type, sc.universe_type as universe, "
    #     query += f"se.entity_proper_name as name, "
    #     query += f"sc.listing_flag as is_listing, sc.regional_flag as is_regional, sc.security_flag as is_security, "
    #     query += f"sh.start_date, sh.end_date "
    #     query += f"from sym_v1.sym_entity se inner join sym_v1.sym_sec_entity_hist sh "
    #     query += f"on se.factset_entity_id = sh.factset_entity_id inner join "
    #     query += f"sym_v1.sym_coverage sc on sh.fsym_id = sc.fsym_primary_equity_id join "
    #     query += f"sym_v1.sym_region sr on sr.fsym_id = sc.fsym_id "
    #     query += f"where sc.fsym_id in "
    #     try:
    #         conn = get_connection(database=database)
    #         df = execute_batch(conn, query, missing)
    #         conn.close()
    #         if not df.empty:
    #             df['name'] = df['entity_name']
    #             df['region_code'] = df['region']
    #             df.loc[df.index, 'start_date'] = util.parse_date(df['start_date'].to_numpy())
    #             df.loc[df.index, 'end_date'] = util.parse_date(df['end_date'].to_numpy())
    #             ix = np.where(pd.isnull(df['end_date']))[0]
    #             if len(ix) > 0 :
    #                 df.loc[df.index[ix], 'end_date'] = util.parse_date(99991231)
    #             df['id_type'] = None
    #             ix = np.where(df['is_listing'] == 1)[0]
    #             if len(ix) > 0:
    #                 df.loc[df.index[ix], 'id_type'] = 'Listing'
    #             ix = np.where(df['is_regional'] == 1)[0]
    #             if len(ix) > 0:
    #                 df.loc[df.index[ix], 'id_type'] = 'Regional'
    #             ix = np.where(df['is_security'] == 1)[0]
    #             if len(ix) > 0:
    #                 df.loc[df.index[ix], 'id_type'] = 'Security'
    #             if domiciles is None:
    #                 domiciles = df
    #             else:
    #                 domiciles = pd.concat((domiciles, df), axis=0, ignore_index=True)
    #     except db.DatabaseError as dbe:
    #         display(dbe)
    #         display(f" Unable to get domiciles")
    #         if not conn.closed:
    #             conn.close()
    #         raise dbe
    #     except Exception as ee:
    #         display(ee)
    #         display(f" Unable to get domiciles")
    #         if not conn.closed:
    #             conn.close()
    #         raise ee
    # if domiciles is None:
    #     return domiciles
    # ix = np.where(np.isin(domiciles['sec_id'].to_numpy(), sec_ids))[0]
    # if dates is not None:
    #     days = util.parse_date(dates)
    #     if not isinstance(days, np.ndarray):
    #         iy = np.where(np.logical_and(domiciles['start_date'] <= days, domiciles['end_date'] > days))[0]
    #     else:
    #         if len(dates) != len(sec_ids):
    #             raise ValueError(f"get_domiciles: dates and sec_ids are not identical in length")
    #         iy = np.array([])
    #         for d in days:
    #             iz = np.where(np.logical_and(domiciles['start_date'] <= d, domiciles['end_date'] > d))[0]
    #             if len(iz) > 0:
    #                 iy = np.union1d(iy, iz)
    #     ix = np.intersect1d(ix, iy)
    # return domiciles.iloc[ix].copy()


def get_names(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get names of the firms
    :param sec_ids:
    :param dates: default NOne
    :param database: default 'FactSetDataFeed'

    :return:

    Example:
        Input:
            get_names('HTM0LK-R')
        Output:
                                       name
            sec_id
            HTM0LK-R  Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 29, 2022
    Modified: April 25, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    names = get_references(sec_ids, None, False, dates, database)
    if names is None:
        return names
    return names[['sec_id', 'name', 'start_date', 'end_date']]


def get_security_ids(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    not to be confused with get_sec_ids, the latter gives regional/listing IDs,
    here 'security id' is the company ID
    get security id of the firms
    :param sec_ids:
    :param dates:
    :param database
    :return:
        Input:
            get_security_ids('HTM0LK-R')
        Output:
                     security_id                   name
            sec_id
            HTM0LK-R    XF9TK6-S  Alphabet Inc. Class A
    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 29, 2022
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    return ref[['sec_id', 'security_id', 'name', 'start_date', 'end_date']]


def get_entity_ids(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
        get entity IDs
    :param sec_ids:
    :param dates:
    :param database:
    :return: dataframe with 'entity_id', and 'entity_name' as columns and sec_ids as index

    Example:
            input:
                get_entity_ids('JLJ0VZ-R')
            output:
                     entity_id                    entity_name
            JLJ0VZ-R  002615-E  The Goldman Sachs Group, Inc.

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    Modified: April 26, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    return ref[['sec_id', 'entity_id', 'name', 'start_date', 'end_date']]


def get_id_types(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get id types of the firms
    :param sec_ids:
    :param dates:
    :param database: FactSetDataFeed
    :return:

    Example:
        Input:
            get_id_types('HTM0LK-R')
        Output:
                       id_type                   name
            sec_id
            HTM0LK-R  Regional  Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    Modified: April 26, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return None
    s = ref[['sec_id', 'id_type', 'name', 'start_date', 'end_date']]
    return s


def get_exchange_country_map(exch=None, countries=None, exchange_only=True, database='FactSetDataFeed'):
    global exchange_country
    if exchange_country is None:
        query = f"select * from ref_v2.fref_sec_exchange_map"
        conn = get_connection(database=database)
        cursor = get_cursor(conn)
        try:
            at = util.clock()
            cursor.execute(query)
            et = util.clock()
            records = cursor.fetchall()
            zt = util.clock()
            display(f" {len(records)} rows; "
                    f"{et - at: .1f} seconds to execute; {zt - et: .1f} seconds to fetch")
            exchange_country = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to load exchange to country map due to database error")
            raise dbe
        except ValueError as ve:
            display(f"Unable to load exchange to country map due to value error: {ve}")
            raise ve
        except Exception as ee:
            display(f"Unable to load exchange to country map due to exception: {ee}")
            raise ee
    if exchange_country is None:
        display(f"No valid exchange to country map found")
        raise ValueError(f"No valid exchange to country map found")
    if exchange_country.empty:
        display(f"Empty exchange to country map")
    df = exchange_country.copy(deep=True)
    if exchange_only:
        ix = np.where(df['fref_exchange_market_type'] == 'EXCH')[0]
        df = df.iloc[ix]
    if countries is not None:
        if isinstance(countries, str):
            countries = np.array([countries])
        elif isinstance(countries, list):
            countries = np.array(countries)
        countries = np.char.strip(np.char.upper(countries))
        ix = np.where(np.isin(df['fref_exchange_location_code'], countries))[0]
        df = df.iloc[ix]
    if exch is not None:
        if isinstance(exch, str):
            exch = np.array([exch])
        elif isinstance(exch, list):
            exch = np.array(exch)
        exch = np.char.strip(np.char.upper(exch))
        ix = np.where(np.isin(df['fref_exchange_code'], exch))[0]
        df = df.iloc[ix]
    return df


def get_exchanges(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get exchanges of the firms
    :param sec_ids:
    :param dates: None
    :param database: FactSetDataFeed
    :return:

    Example:
        Input:
            get_exchanges('HTM0LK-R')
        Output:
                      exchange                 name
            sec_id
            HTM0LK-R  NAS     Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 29, 2022
    Modified: April 26, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    names = ref[['sec_id', 'exchange', 'name', 'start_date', 'end_date']]
    return names


def get_regions(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get regions of the firms
    :param sec_ids:
    :param dates: None
    :param database: FactSetDataFeed
    :return:

    Example:
        Input:
            get_regions('HTM0LK-R')
        Output:
                      region                    name
            sec_id
            HTM0LK-R  AMER     Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 29, 2022
    Modified: April 26, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    # ref = get_references(sec_ids)
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    regions = ref[['sec_id', 'region', 'name', 'start_date', 'end_date']]
    return regions


def get_universes(sec_ids=None, dates=None, database='FactSetDataFeed'):
    """
    get universes of the firms
    :param sec_ids:
    :param dates: None
    :param database: FactSetDataFeed
    :return:

    Example:
        Input:
            get_universes('HTM0LK-R')
        Output:
                      universe                    name
            sec_id
            HTM0LK-R  EQ         Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 29, 2022
    Modified: April 26, 2023
    """
    if sec_ids is None:
        return None
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if len(sec_ids) == 0:
        display(f" not sufficient securities")
        return None
    ref = get_references(sec_ids, None, False, dates, database)
    if ref is None:
        return ref
    names = ref[['sec_id', 'universe', 'name', 'start_date', 'end_date']]
    return names


# inverse look up: symbol to sec_id

def get_sec_ids(symbols, s_type='ticker', currency=None, id_type=None, active_only=False, region=None, exchange=None,
                day=None):
    """
    get security id by symbol
    :param symbols:
    :param s_type:
    :param currency:
    :param id_type: default None or regional, also accepted security or listing
    :param active_only: default False
    :param region: default None
    :param exchange: default None, string or list of strings such as 'NAS', ['NYS', 'NAS']
    :param day: default None, the day for which the queries is based on
    :return:
            Input:
                get_sec_ids('GS-US')
            Output:
                          currency domicile entity_id  ... universe  start_date    end_date
              USD       US  002615-E  ...       EQ  1999-05-04  9999-12-31


            Input:
                get_sec_ids('002615-E', 'entity')
            Output:
                  sec_id  is_active security_id  ... is_security  start_date    end_date
                HL1ZRF-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                JLJ0VZ-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                J0BVSG-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                LC1YHJ-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                CLYS7W-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                CX5Q6V-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                CB0K4B-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                HR20K1-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                HS0FNN-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31
                WMM7Y7-R          1    HG5HFV-S  ...           0  1999-05-04  9999-12-31

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022

    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if hasattr(symbols, 'to_numpy'):
        symbols = symbols.to_numpy()
    if len(symbols) == 0:
        display(f" empty symbols")
    s_type = s_type.lower().strip()
    if s_type == 'ticker':
        return get_sec_id_by_tickers(symbols, currency, id_type, active_only, region, exchange, day=day)
    elif s_type == 'cusip':
        return get_sec_id_by_cusips(symbols, currency, id_type, active_only, region, exchange, day=day)
    elif s_type == 'sedol':
        return get_sec_id_by_sedols(symbols, currency, id_type, active_only, region, exchange, day=day)
    elif s_type == 'isin':
        return get_sec_id_by_isins(symbols, currency, id_type, active_only, region, exchange, day=day)
    elif s_type in ('bbg_id', 'bloomberg_id', 'bloomberg', 'bbg'):
        return get_sec_id_by_bloomberg_ids(symbols, currency, id_type, active_only, region, exchange)
    elif s_type in ('bbg_ticker', 'bloomberg_ticker', 'bloombergticker'):
        return get_sec_id_by_bloomberg_tickers(symbols, currency, id_type, active_only, region, exchange)
    elif s_type in ('entity', 'entity_id', 'entity_ids', 'entityid', 'entityids'):
        return get_sec_id_by_entity_ids(symbols, currency, id_type, active_only, region, exchange, day=day)
    elif s_type == 'security_id':
        return get_sec_id_by_security_ids(symbols, currency, id_type, active_only, region, exchange, day=day)
    elif s_type == 'primary_equity_id':
        return get_sec_id_by_primary_equity_ids(symbols, currency, id_type, active_only, region, exchange, day=day)
    else:
        display(f" {s_type} not recognized: assuming 'ticker'")
        return get_sec_id_by_tickers(symbols, currency, id_type, active_only, region, exchange, day=day)


def is_active(sec_ids):
    """
    find out if security is a currently active security
    :param sec_ids:
    :return:

    Example:
            Input:
                is_active('CTYNJ1-R')
            Output:
                          is_active
                CTYNJ1-R       True

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    """
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    sec_ids = np.unique(sec_ids)
    ref = get_references(sec_ids)
    df = ref[['is_active', 'name']].copy(deep=True)
    active = np.array([False] * len(df.index))
    ix = np.where(df['is_active'] == 1)[0]
    active[ix] = True
    df.loc[df.index, 'is_active'] = active
    return df


def get_tickers(sec_ids=None, day=util.today(), table_flag=True):
    """
    get security tickers by sec id (regional ID)
    :param sec_ids:
    :param day: default today
    :param table_flag: default False
    :return:

    Example:
        Input:
            get_tickers(['JLJ0VZ-R', 'J3QHBN-R', 'QLGSL2-R'], 20220608)
        Output:
            {'J3QHBN-R': array(['AAAB.XX1-US'], dtype=object), 'JLJ0VZ-R': array(['GS-US'], dtype=object),
            'QLGSL2-R': array(['FB-US'], dtype=object)}

    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 22, 2022
    """
    if sec_ids is None:
        sec_ids = np.array([])
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if not isinstance(table_flag, bool):
        table_flag = True
    d = util.parse_date(day)

    field = 'ticker_region'
    cache_name = 'ticker region'
    if len(sec_ids) == 0:
        if cache_name in cache:
            return cache[cache_name]
        else:
            display(f"Empty sec_ids: returning None")
            return None
    sec_ids = np.unique(sec_ids)
    cash_tickers = get_cash_tickers()
    if cache_name not in cache:
        cache[cache_name] = cash_tickers
    if cache_name not in cache:
        ref = pd.DataFrame()
        missing = sec_ids
    else:
        ref = cache[cache_name]
        missing = np.setdiff1d(sec_ids, ref['sec_id'])
    if len(missing) > 0:
        query = f"select * from dbo.vw_Get_ticker_region_hist where fsym_id in "
        try:
            conn = get_connection()
            data = execute_batch(conn, query, missing)
            conn.close()
            if not data.empty:
                data.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
                data['start_date'] = util.parse_date(data['start_date'])
                data['end_date'] = util.parse_date(data['end_date'])
                most_recent = np.array([False] * len(data.index))
                ix = np.where(data['most_recent'] == 1.0)[0]
                most_recent[ix] = True
                data['most_recent'] = most_recent
                # convert end date for those most recent to 9999/12/31
                ix = np.where(np.logical_and(pd.notnull(data['start_date']), pd.isnull(data['end_date'])))[0]
                data.loc[data.index[ix], 'end_date'] = util.parse_date(99991231)
                data.sort_values(by=['sec_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                # convert rows of None for both start and end date
                ix = np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0]
                bad = np.array([], dtype='int64')
                first = util.parse_date(19000101)
                last = util.parse_date(99991231)
                for kx in ix:
                    s = data['sec_id'].iloc[kx]
                    iz = np.where(data['sec_id'] == s)[0]
                    if len(iz) == 1:
                        data.loc[data.index[kx], 'most_recent'] = True
                        data.loc[data.index[kx], 'start_date'] = first
                        data.loc[data.index[kx], 'end_date'] = last
                    else:
                        max_end = data.loc[data.index[iz[-1]], 'end_date']
                        if max_end < last:
                            if data.loc[data.index[kx], field] == data.loc[data.index[iz[-1]], field]:
                                data.loc[data.index[iz[-1]], 'end_date'] = last
                                data.loc[data.index[iz[-1]], 'most_recent'] = True
                            else:
                                data.loc[data.index[kx], 'start_date'] = max_end
                                data.loc[data.index[kx], 'end_date'] = last
                                data.loc[data.index[kx], 'most_recent'] = True
                                data.loc[data.index[iz[-1]], 'most_recent'] = False
                        else:
                            bad = np.union1d(bad, [kx])

                data.drop_duplicates(keep='first', inplace=True)
                bad = np.union1d(bad, np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0])
                if len(bad) > 0:
                    good = np.setdiff1d(data.index, data.index[bad])
                    data = data.loc[good]
                    display(f"{len(bad)} rows of bad data expunged")
                data.sort_values(by=['sec_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                if not data.empty:
                    ref = pd.concat([ref, data], axis=0, ignore_index=True)
                    ref.drop_duplicates(keep='last', inplace=True)
                    ref.reset_index(drop=True, inplace=True)
                    if not ref.empty:
                        cache[cache_name] = ref
        except IOError as ioe:
            display(ioe)
            display(f"Due to IO Error: unable to get {cache_name}")
            conn.close()
            raise ioe
        except Exception as eee:
            display(eee)
            display(f"Due to Exception: unable to get {cache_name}")
            conn.close()
            raise eee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref['sec_id'], sec_ids))[0]
    if d is not None:
        iz = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    if table_flag:
        return ref.reset_index(drop=True)
    else:
        df = dict.fromkeys(sec_ids)
        for s in sec_ids:
            ix = np.where(ref['sec_id'] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[field].iloc[ix].to_numpy())
        return df.reset_index(drop=True)


def get_cusips(sec_ids=None, day=util.today(), table_flag=True):
    """
    get cusips, optionally returning table
    :param sec_ids:
    :param day: default today
    :param table_flag: default True
    :return:

    Example:
        Input:
            get_cusips(['JLJ0VZ-R', 'J3QHBN-R', 'QLGSL2-R'], 20220608)
        Output:
            {'J3QHBN-R': array(['007231103'], dtype=object), 'JLJ0VZ-R': array(['38141G104'], dtype=object),
            'QLGSL2-R': array(['30303M102'], dtype=object)}


    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 22, 2022
    Modified: April 28, 2023
    """
    if sec_ids is None:
        sec_ids = np.array([])
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if not isinstance(table_flag, bool):
        table_flag = True
    d = util.parse_date(day)

    field = 'cusip'
    cache_name = 'cusip'
    if len(sec_ids) == 0:
        if cache_name in cache:
            return cache[cache_name]
        else:
            display(f"Empty sec_ids: returning None")
            return None
    sec_ids = np.unique(sec_ids)
    if cache_name not in cache:
        ref = pd.DataFrame()
        missing = sec_ids
    else:
        ref = cache[cache_name]
        missing = np.setdiff1d(sec_ids, ref['sec_id'])
    if len(missing) > 0:
        ids = get_security_ids(missing)
        # ids.reset_index(inplace=True)
        # ids.rename(columns={ids.columns[0]: 'sec_id'}, inplace=True)
        query = f"select * from dbo.vw_Get_cusip_hist where fsym_id in "
        try:
            conn = get_connection()
            data = execute_batch(conn, query, ids['security_id'])
            conn.close()
            if not data.empty:
                data.rename(columns={'fsym_id': 'security_id'}, inplace=True)
                data['start_date'] = util.parse_date(data['start_date'])
                data['end_date'] = util.parse_date(data['end_date'])
                most_recent = np.array([False] * len(data.index))
                ix = np.where(data['most_recent'] == 1.0)[0]
                most_recent[ix] = True
                data['most_recent'] = most_recent
                # convert end date for those most recent to 9999/12/31
                ix = np.where(np.logical_and(pd.notnull(data['start_date']), pd.isnull(data['end_date'])))[0]
                data.loc[data.index[ix], 'end_date'] = util.parse_date(99991231)
                data.sort_values(by=['security_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                # convert rows of None for both start and end date
                ix = np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0]
                bad = np.array([], dtype='int64')
                first = util.parse_date(19000101)
                last = util.parse_date(99991231)
                for kx in ix:
                    s = data['security_id'].iloc[kx]
                    iz = np.where(data['security_id'] == s)[0]
                    if len(iz) == 1:
                        data.loc[data.index[kx], 'most_recent'] = True
                        data.loc[data.index[kx], 'start_date'] = first
                        data.loc[data.index[kx], 'end_date'] = last
                    else:
                        max_end = data.loc[data.index[iz[-1]], 'end_date']
                        if max_end < last:
                            if data.loc[data.index[kx], field] == data.loc[data.index[iz[-1]], field]:
                                data.loc[data.index[iz[-1]], 'end_date'] = last
                                data.loc[data.index[iz[-1]], 'most_recent'] = True
                            else:
                                data.loc[data.index[kx], 'start_date'] = max_end
                                data.loc[data.index[kx], 'end_date'] = last
                                data.loc[data.index[kx], 'most_recent'] = True
                                data.loc[data.index[iz[-1]], 'most_recent'] = False
                        else:
                            bad = np.union1d(bad, [kx])

                data.drop_duplicates(keep='first', inplace=True)
                bad = np.union1d(bad, np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0])
                if len(bad) > 0:
                    good = np.setdiff1d(data.index, data.index[bad])
                    data = data.loc[good]
                    display(f"{len(bad)} rows of bad data expunged")
                data.sort_values(by=['security_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                sids = np.unique(data['security_id'])
                sf = pd.DataFrame()
                for s in sids:
                    ix = np.where(ids['security_id'] == s)[0]
                    iy = np.where(data['security_id'] == s)[0]
                    if len(ix) == 0 or len(iy) == 0:
                        continue
                    r1 = ids.iloc[ix]
                    d1 = data.iloc[iy]
                    for r in r1['sec_id'].to_numpy():
                        iz = np.where(r1['sec_id'] == r)[0]
                        r2 = r1.iloc[iz]
                        tf = util.merge_multiple_by_date_range(r2, d1, 'security_id')
                        sf = pd.concat((sf, tf), axis=0, ignore_index=True)
                ix = np.where(pd.notnull(sf['cusip']))[0]
                data = sf.iloc[ix]

                # data = util.merge_multiple_by_date_range(data, ids, 'security_id',
                #                                          'start_date', 'end_date', 'start_date', 'end_date')
                names = np.setdiff1d(data.columns, np.array(['start_date', 'end_date']))
                names = np.setdiff1d(names, ['sec_id', 'security_id', 'cusip'])
                names = np.append(np.array(['sec_id', 'security_id', 'cusip']), names)
                names = np.append(names, np.array(['start_date', 'end_date']))
                data = data[names]
                gx = np.where(pd.notnull(data['sec_id']))[0]
                data = data.iloc[gx]
                if not data.empty:
                    ref = pd.concat([ref, data], axis=0, ignore_index=True)
                    ref.drop_duplicates(keep='last', inplace=True)
                    if not ref.empty:
                        cache[cache_name] = ref
        except IOError as ioe:
            display(ioe)
            display(f"Due to IO Error: unable to get {cache_name}")
            conn.close()
            raise ioe
        except Exception as eee:
            display(eee)
            display(f"Due to Exception: unable to get {cache_name}")
            conn.close()
            raise eee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref['sec_id'], sec_ids))[0]
    if d is not None:
        iz = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(sec_ids)
        for s in sec_ids:
            ix = np.where(ref['sec_id'] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[field].iloc[ix].to_numpy())
        return df


def get_sedols(sec_ids=None, day=util.today(), table_flag=True):
    """

    :param sec_ids:
    :param day: default today
    :param table_flag: default False
    :return:

    Example:
        Input:
            get_sedols(['JLJ0VZ-R', 'J3QHBN-R', 'QLGSL2-R'], 20220608)
        Output:
            {'J3QHBN-R': array(['2302566'], dtype=object), 'JLJ0VZ-R': array(['2407966'], dtype=object),
            'QLGSL2-R': array(['B7TL820'], dtype=object)}


    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 22, 2022
    """
    if sec_ids is None:
        sec_ids = np.array([])
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if not isinstance(table_flag, bool):
        table_flag = True
    d = util.parse_date(day)

    field = 'sedol'
    cache_name = 'sedols'
    if len(sec_ids) == 0:
        if cache_name in cache:
            return cache[cache_name]
        else:
            display(f"Empty sec_ids: returning None")
            return None
    sec_ids = np.unique(sec_ids)
    if cache_name not in cache:
        ref = pd.DataFrame()
        missing = sec_ids
    else:
        ref = cache[cache_name]
        missing = np.setdiff1d(sec_ids, ref['sec_id'])
    if len(missing) > 0:
        query = f"select * from dbo.vw_Get_sedol_hist where fsym_id in "
        try:
            conn = get_connection()
            data = execute_batch(conn, query, missing)
            conn.close()
            if not data.empty:
                data.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
                data['start_date'] = util.parse_date(data['start_date'])
                data['end_date'] = util.parse_date(data['end_date'])
                most_recent = np.array([False] * len(data.index))
                ix = np.where(data['most_recent'] == 1.0)[0]
                most_recent[ix] = True
                data['most_recent'] = most_recent
                # convert end date for those most recent to 9999/12/31
                ix = np.where(np.logical_and(pd.notnull(data['start_date']), pd.isnull(data['end_date'])))[0]
                data.loc[data.index[ix], 'end_date'] = util.parse_date(99991231)
                data.sort_values(by=['sec_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                # convert rows of None for both start and end date
                ix = np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0]
                bad = np.array([], dtype='int64')
                first = util.parse_date(19000101)
                last = util.parse_date(99991231)
                for kx in ix:
                    s = data['sec_id'].iloc[kx]
                    iz = np.where(data['sec_id'] == s)[0]
                    if len(iz) == 1:
                        data.loc[data.index[kx], 'most_recent'] = True
                        data.loc[data.index[kx], 'start_date'] = first
                        data.loc[data.index[kx], 'end_date'] = last
                    else:
                        max_end = data.loc[data.index[iz[-1]], 'end_date']
                        if max_end < last:
                            if data.loc[data.index[kx], field] == data.loc[data.index[iz[-1]], field]:
                                data.loc[data.index[iz[-1]], 'end_date'] = last
                                data.loc[data.index[iz[-1]], 'most_recent'] = True
                            else:
                                data.loc[data.index[kx], 'start_date'] = max_end
                                data.loc[data.index[kx], 'end_date'] = last
                                data.loc[data.index[kx], 'most_recent'] = True
                                data.loc[data.index[iz[-1]], 'most_recent'] = False
                        else:
                            bad = np.union1d(bad, [kx])

                data.drop_duplicates(keep='first', inplace=True)
                bad = np.union1d(bad, np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0])
                if len(bad) > 0:
                    good = np.setdiff1d(data.index, data.index[bad])
                    data = data.loc[good]
                    display(f"{len(bad)} rows of bad data expunged")
                data.sort_values(by=['sec_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                if not data.empty:
                    ref = pd.concat([ref, data], axis=0, ignore_index=True)
                    ref.drop_duplicates(keep='last', inplace=True)
                    if not ref.empty:
                        cache[cache_name] = ref
        except IOError as ioe:
            display(ioe)
            display(f"Due to IO Error: unable to get {cache_name}")
            conn.close()
            raise ioe
        except Exception as eee:
            display(eee)
            display(f"Due to Exception: unable to get {cache_name}")
            conn.close()
            raise eee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref['sec_id'], sec_ids))[0]
    if d is not None:
        iz = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(sec_ids)
        for s in sec_ids:
            ix = np.where(ref['sec_id'] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[field].iloc[ix].to_numpy())
        return df


def get_isins(sec_ids=None, day=util.today(), table_flag=True):
    """
    get isins, optionally returning table
    :param sec_ids:
    :param day: default today
    :param table_flag: default False
    :return:

    Example:
        Input:
            get_isins(['JLJ0VZ-R', 'J3QHBN-R', 'QLGSL2-R'], 20220608)
        Output:
            {'J3QHBN-R': array(['US0072311030'], dtype=object), 'JLJ0VZ-R': array(['US38141G1040'], dtype=object),
            'QLGSL2-R': array(['US30303M1027'], dtype=object)}

    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 26, 2022
    """
    if sec_ids is None:
        sec_ids = np.array([])
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if not isinstance(table_flag, bool):
        table_flag = False
    d = util.parse_date(day)

    field = 'isin'
    cache_name = 'isins'
    if len(sec_ids) == 0:
        if cache_name in cache:
            return cache[cache_name]
        else:
            display(f"Empty sec_ids: returning None")
            return None
    sec_ids = np.unique(sec_ids)
    if cache_name not in cache:
        ref = pd.DataFrame()
        missing = sec_ids
    else:
        ref = cache[cache_name]
        missing = np.setdiff1d(sec_ids, ref['sec_id'])
    if len(missing) > 0:
        ids = get_security_ids(missing)
        # ids.reset_index(inplace=True)
        # ids.rename(columns={ids.columns[0]: 'sec_id'}, inplace=True)
        query = f"select * from dbo.vw_Get_isin_hist where fsym_id in "
        try:
            conn = get_connection()
            data = execute_batch(conn, query, ids['security_id'])
            conn.close()
            if not data.empty:
                data.rename(columns={'fsym_id': 'security_id'}, inplace=True)
                data['start_date'] = util.parse_date(data['start_date'])
                data['end_date'] = util.parse_date(data['end_date'])
                most_recent = np.array([False] * len(data.index))
                ix = np.where(data['most_recent'] == 1.0)[0]
                most_recent[ix] = True
                data['most_recent'] = most_recent
                # convert end date for those most recent to 9999/12/31
                ix = np.where(np.logical_and(pd.notnull(data['start_date']), pd.isnull(data['end_date'])))[0]
                data.loc[data.index[ix], 'end_date'] = util.parse_date(99991231)
                data.sort_values(by=['security_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                # convert rows of None for both start and end date
                ix = np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0]
                bad = np.array([], dtype='int64')
                first = util.parse_date(19000101)
                last = util.parse_date(99991231)
                for kx in ix:
                    s = data['security_id'].iloc[kx]
                    iz = np.where(data['security_id'] == s)[0]
                    if len(iz) == 1:
                        data.loc[data.index[kx], 'most_recent'] = True
                        data.loc[data.index[kx], 'start_date'] = first
                        data.loc[data.index[kx], 'end_date'] = last
                    else:
                        max_end = data.loc[data.index[iz[-1]], 'end_date']
                        if max_end < last:
                            if data.loc[data.index[kx], field] == data.loc[data.index[iz[-1]], field]:
                                data.loc[data.index[iz[-1]], 'end_date'] = last
                                data.loc[data.index[iz[-1]], 'most_recent'] = True
                            else:
                                data.loc[data.index[kx], 'start_date'] = max_end
                                data.loc[data.index[kx], 'end_date'] = last
                                data.loc[data.index[kx], 'most_recent'] = True
                                data.loc[data.index[iz[-1]], 'most_recent'] = False
                        else:
                            bad = np.union1d(bad, [kx])

                data.drop_duplicates(keep='first', inplace=True)
                bad = np.union1d(bad, np.where(pd.isnull(data[['start_date', 'end_date']]).sum(axis=1) == 2)[0])
                if len(bad) > 0:
                    good = np.setdiff1d(data.index, data.index[bad])
                    data = data.loc[good]
                    display(f"{len(bad)} rows of bad data expunged")
                data.sort_values(by=['security_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
                # data = data.merge(ids, how='left', left_on='security_id', right_on='security_id')
                # data = util.merge_multiple_by_date_range(data, ids, 'security_id', 'start_date', 'end_date',
                #                                          'start_date', 'end_date')
                sids = np.unique(data['security_id'])
                sf = pd.DataFrame()
                for s in sids:
                    ix = np.where(ids['security_id'] == s)[0]
                    iy = np.where(data['security_id'] == s)[0]
                    if len(ix) == 0 or len(iy) == 0:
                        continue
                    r1 = ids.iloc[ix]
                    d1 = data.iloc[iy]
                    for r in r1['sec_id'].to_numpy():
                        iz = np.where(r1['sec_id'] == r)[0]
                        r2 = r1.iloc[iz]
                        tf = util.merge_multiple_by_date_range(r2, d1, 'security_id')
                        sf = pd.concat((sf, tf), axis=0, ignore_index=True)
                ix = np.where(pd.notnull(sf['isin']))[0]
                data = sf.iloc[ix]

                names = np.setdiff1d(data.columns, np.array(['start_date', 'end_date']))
                names = np.setdiff1d(names, ['sec_id', 'security_id', 'isin'])
                names = np.append(np.array(['sec_id', 'security_id', 'isin']), names)
                names = np.append(names, np.array(['start_date', 'end_date']))
                data = data[names]
                gx = np.where(pd.notnull(data['sec_id']))[0]
                data = data.iloc[gx]
                if not data.empty:
                    ref = pd.concat([ref, data], axis=0, ignore_index=True)
                    ref.drop_duplicates(keep='last', inplace=True)
                    if not ref.empty:
                        cache[cache_name] = ref
        except IOError as ioe:
            display(ioe)
            display(f"Due to IO Error: unable to get {cache_name}")
            conn.close()
            raise ioe
        except Exception as eee:
            display(eee)
            display(f"Due to Exception: unable to get {cache_name}")
            conn.close()
            raise eee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref['sec_id'], sec_ids))[0]
    if d is not None:
        iz = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(sec_ids)
        for s in sec_ids:
            ix = np.where(ref['sec_id'] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[field].iloc[ix].to_numpy())
        return df


def get_bloomberg_ids(sec_ids=None, recent=True, table_flag=True, field='bbg_id'):
    """
    get bloomberg ID or optionally bloomberg ticker
    :param sec_ids:
    :param recent: default True
    :param table_flag: default False
    :param field: default 'bbg_id', alternative 'bbg_ticker'
    :return:

    Example:
        Input:
            get_bloomberg_ids(['JLJ0VZ-R', 'J3QHBN-R', 'QLGSL2-R'])
        Output:
            {'J3QHBN-R': array(['BBG000C4GMX5'], dtype=object), 'JLJ0VZ-R': array(['BBG000C6CFJ5'], dtype=object),
            'QLGSL2-R': array(['BBG000MM2P62'], dtype=object)}

    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 22, 2022
    """
    if sec_ids is None:
        sec_ids = np.array([])
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    if isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    if not isinstance(table_flag, bool):
        table_flag = False
    if not isinstance(field, str):
        field = 'bbg_id'
    field = field.lower().strip()
    if field not in ['bbg_id', 'bbg_ticker']:
        display(f"Requested field: {field} not accepted; has to be bbg_id or bbg_ticker")
        raise ValueError(f"Wrong field: has to be either bbg_id or bbg_ticker")
    cache_name = 'bloomberg'
    if len(sec_ids) == 0:
        if cache_name in cache:
            return cache[cache_name]
        else:
            display(f"Empty sec_ids: returning None")
            return None
    sec_ids = np.unique(sec_ids)
    if cache_name not in cache:
        ref = pd.DataFrame()
        missing = sec_ids
    else:
        ref = cache[cache_name]
        missing = np.setdiff1d(sec_ids, ref['sec_id'])
    if len(missing) > 0:
        query = f"select * from sym_v1.sym_bbg where fsym_id in "
        try:
            conn = get_connection()
            data = execute_batch(conn, query, missing)
            conn.close()
            if not data.empty:
                data.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
                most_recent = np.array([False] * len(data.index))
                ix = np.where(data['most_recent'] == 1.0)[0]
                most_recent[ix] = True
                data['most_recent'] = most_recent
                data.sort_values(by=['sec_id', 'most_recent'], inplace=True, ignore_index=True, na_position='first')
                data.drop_duplicates(keep='first', inplace=True)
                if not data.empty:
                    ref = pd.concat([ref, data], axis=0, ignore_index=True)
                    ref.drop_duplicates(keep='last', inplace=True)
                    if not ref.empty:
                        cache[cache_name] = ref
        except IOError as ioe:
            display(ioe)
            display(f"Due to IO Error: unable to get {cache_name}")
            conn.close()
            raise ioe
        except Exception as eee:
            display(eee)
            display(f"Due to Exception: unable to get {cache_name}")
            conn.close()
            raise eee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref['sec_id'], sec_ids))[0]
    if recent:
        iz = np.where(ref['most_recent'])[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(sec_ids)
        for s in sec_ids:
            ix = np.where(ref['sec_id'] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[field].iloc[ix].to_numpy())
        return df


def get_bloomberg_tickers(sec_ids=None, recent=True, table_flag=True):
    """
    get bloomberg ID or optionally bloomberg ticker
    :param sec_ids:
    :param recent: default True
    :param table_flag: default False
    :return:

    Example:
        Input:
            get_bloomberg_tickers(['JLJ0VZ-R', 'J3QHBN-R', 'QLGSL2-R'])
        Output:
            {'J3QHBN-R': array([None], dtype=object), 'JLJ0VZ-R': array(['GS US'], dtype=object),
            'QLGSL2-R': array(['META US'], dtype=object)}

    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 22, 2022
    """
    return get_bloomberg_ids(sec_ids, recent, table_flag, 'bbg_ticker')


def get_sec_id_by_tickers(symbols, currency=None, id_type=None,  active_only=True, region=None, exchange=None,
                          day=None, exclude_nan=True):
    """
    get sec unique identifier by ticker: ticker-region format
    :param symbols: such as 'HSBA-LN'
    :param currency: default None
    :param id_type: default None, accepted 'security', 'regional', 'listing'
    :param region: default None
    :param exchange: default None
    :param active_only: default True
    :param exchange: default None, string or list of strings
    :param day: default None : search all histories
    :param exclude_nan: default True
    :return:
            Input:
                get_sec_id_by_tickers('GE-US')
            Output:
                {'GE-US': array(['CTYNJ1-R'], dtype=object)}

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    Modified: May 1, 2023
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()

    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange.upper().strip()])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    if len(exchange) > 0:
        for i, s in enumerate(exchange):
            exchange[i] = s.upper().strip()
    v_type = 'sec_id'
    if id_type is not None:
        if not isinstance(id_type, str):
            id_type = None
        else:
            id_type = id_type.lower().strip()
            if id_type == 'listing':
                v_type = 'listing_id'
            elif id_type == 'security':
                v_type = 'security_id'

    if day is not None:
        d = util.parse_date(day)
    else:
        d = None
    field = 'ticker_region'
    ref = pd.DataFrame()
    missing = symbols
    if len(missing) > 0:
        query = f"select * from dbo.vw_Get_ticker_region_hist where ticker_region in "
        conn = get_connection()
        try:
            data = execute_batch(conn, query, symbols)
            conn.close()
            data.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
            if data.empty:
                return data
            ix = np.where(~np.logical_and(pd.isnull(data['start_date']), pd.isnull(data['end_date'])))[0]
            data = data.iloc[ix]
            if data.empty:
                return data
            ref = get_tickers(np.unique(data['sec_id'].to_numpy()), None, True)
        except db.DatabaseError as dbe:
            display(dbe)
            display(f"Database Error: Unable to get sec_id by ticker")
            if not conn.closed:
                conn.close()
            raise dbe
        except Exception as ee:
            display(ee)
            display(f"Exception: Unable to get sec_id by ticker")
            if not conn.closed:
                conn.close()
            raise ee
    if ref.empty:
        return None
    if exclude_nan:
        ix = np.where(pd.notnull(ref['sec_id']))[0]
        ref = ref.iloc[ix]
    meta = get_references(ref['sec_id'])
    # ref = ref.merge(meta, how='left', left_on='sec_id', right_on='sec_id')
    ref = util.merge_multiple_by_date_range(ref, meta, 'sec_id')
    ix = np.where(ref['end_date'] < util.parse_date(99991231))[0]
    ref['is_active'].iloc[ix] = 0
    ix = np.where(pd.isnull(ref['most_recent']))[0]
    ref['most_recent'].iloc[ix] = False
    ix = np.where(np.isin(ref[field], symbols))[0]
    if d is not None:
        iz = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    if exclude_nan:
        ix = np.where(~np.logical_and(pd.isnull(ref['security_id']), pd.isnull(ref['entity_id'])))[0]
        ref = ref.iloc[ix]
    return ref


def get_sec_id_by_sedols(symbols, currency=None, id_type=None,  active_only=False, region=None, exchange=None,
                         day=None, exclude_nan=True):
    """
    get sec unique identifier by sedol:
    :param symbols: such as '2407966'
    :param currency: default None
    :param id_type: default None, accepted 'security', 'regional', 'listing'
    :param active_only: default True
    :param region: default None
    :param exchange: default None
    :param day: default None : search all histories
    :param exclude_nan: default True
    :return:
            Input:
                get_sec_id_by_sedols('BMD3QK1')
            Output:
                  currency domicile entity_id  ... universe  start_date    end_date
                      USD       US  06YV42-E  ...       EQ  2020-10-05  2022-10-11
                      NaN      NaN       NaN  ...      NaN  2022-10-11  9999-12-31

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    Modified: May 1, 2023
    Modified: May 27, 2023
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if hasattr(symbols, 'to_numpy'):
        symbols = symbols.to_numpy()
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange.upper().strip()])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    v_type = 'sec_id'
    if id_type is not None:
        if not isinstance(id_type, str):
            id_type = None
        else:
            id_type = id_type.lower().strip()
            if id_type == 'listing':
                v_type = 'listing_id'
            elif id_type == 'security':
                v_type = 'security_id'

    if day is not None:
        d = util.parse_date(day)
    else:
        d = None
    field = 'sedol'
    ref = pd.DataFrame()
    missing = symbols
    if len(missing) > 0:
        query = f"select * from dbo.vw_Get_sedol_hist where {field} in "
        conn = get_connection()
        try:
            data = execute_batch(conn, query, symbols)
            conn.close()
            data.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
            ref = get_sedols(np.unique(data['sec_id'].to_numpy()), d, True)
        except db.DatabaseError as dbe:
            display(dbe)
            display(f"Database Error: Unable to get sec_id by {field}")
            if not conn.closed:
                conn.close()
            raise dbe
        except Exception as ee:
            display(ee)
            display(f"Exception: Unable to get sec_id by {field}")
            if not conn.closed:
                conn.close()
            raise ee
    if ref is None:
        return None
    if ref.empty:
        return None
    if exclude_nan:
        ix = np.where(pd.notnull(ref['sec_id']))[0]
        ref = ref.iloc[ix]
    ix = np.where(np.isin(ref[field], symbols))[0]
    if d is not None:
        iz = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ix = np.intersect1d(ix, iz)
    ref = ref.iloc[ix]
    meta = get_references(ref['sec_id'])
    # ref = ref.merge(meta, how='left', left_on='sec_id', right_on='sec_id')
    ref = util.merge_multiple_by_date_range(ref, meta, 'sec_id')
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    ix = np.where(np.isin(ref['sedol'].to_numpy(), symbols))[0]
    ref = ref.iloc[ix]
    return ref
    # if table_flag:
    #     return ref
    # else:
    #     df = dict.fromkeys(symbols)
    #     for s in symbols:
    #         ix = np.where(ref[field] == s)[0]
    #         df[s] = np.array([])
    #         if len(ix) == 0:
    #             continue
    #         df[s] = np.unique(ref[v_type].iloc[ix].to_numpy())
    #     return df


def get_sec_id_by_cusips(symbols, currency=None, id_type=None, active_only=False, region=None, exchange=None,
                         day=None, exclude_nan=True):
    """
    get sec unique identifier by cusip:
    :param symbols: such as '2407966'
    :param currency: default None
    :param id_type: default None, accepted 'security', 'regional', 'listing'
    :param active_only: default False
    :param region: default None
    :param exchange: default None, string or list of strings
    :param day: default None : search all histories
    # :param table_flag: default False
    :param exclude_nan: default True
    :return:
            Input:
                get_sec_id_by_cusip('007231103')
            Output:
                {'2407966': array(['J3QHBN-R'], dtype=object)}

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if hasattr(symbols, 'to_numpy'):
        symbols = symbols.to_numpy()
    if len(symbols) == 0:
        display(f" empty symbols")
    symbols = np.unique(symbols)
    symbols = symbols[np.where(pd.notnull(symbols))[0]]
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange.upper().strip()])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    if id_type is None or not isinstance(id_type, str):
        id_type = 'regional'
    id_type = id_type.lower().strip()
    # if not isinstance(table_flag, bool):
    #     table_flag = False
    if day is not None:
        d = util.parse_date(day)
    else:
        d = None
    field = 'cusip'

    query = f"select * from dbo.vw_Get_cusip_hist where cusip in "
    conn = get_connection()
    try:
        df = execute_batch(conn, query, symbols)
        conn.close()
        if not df.empty:
            df.rename(columns={'fsym_id': 'security_id'}, inplace=True)
            df.loc[df.index, 'start_date'] = util.parse_date(df['start_date'].to_numpy())
            df.loc[df.index, 'end_date'] = util.parse_date(df['end_date'].to_numpy())
            df.drop_duplicates(keep='last', inplace=True)
            most_recent = np.array([False] * len(df.index))
            ix = np.where(df['most_recent'])[0]
            most_recent[ix] = True
            df.loc[df.index, 'most_recent'] = most_recent
            df.sort_values(by=['security_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
            first = util.parse_date(19000101)
            last = util.parse_date(99991231)
            ix = np.where(np.logical_and(pd.notnull(df['start_date']), pd.isnull(df['end_date'])))[0]
            df.loc[df.index[ix], 'end_date'] = last
            ix = np.where(pd.isnull(df[['start_date', 'end_date']]).sum(axis=1) == 2)[0]
            bad = np.array([], dtype='int64')
            for kx in ix:
                s = df.loc[df.index[kx], field]
                iz = np.where(df[field] == s)[0]
                if len(iz) == 1:
                    df.loc[df.index[kx], 'start_date'] = first
                    df.loc[df.index[kx], 'end_date'] = last
                    df.loc[df.index[kx], 'most_recent'] = True
                    continue
                if df.loc[df.index[iz[-1]], 'end_date'] < last:
                    if df.loc[df.index[kx], field] == df.loc[df.index[iz[-1]], field]:
                        df.loc[df.index[iz[-1]], 'end_date'] = last
                        df.loc[df.index[iz[-1]], 'most_recent'] = True
                    else:
                        df.loc[df.index[kx], 'start_date'] = df.loc[df.index[iz[-1]], 'end_date']
                        df.loc[df.index[kx], 'end_date'] = last
                        df.loc[df.index[kx], 'most_recent'] = True
                        df.loc[df.index[iz[-1]], 'most_recent'] = False
                else:
                    bad = np.union1d(bad, [kx])
            bad = np.union1d(bad, np.where(pd.isnull(df[['start_date', 'end_date']]).sum(axis=1) == 2)[0])
            if len(bad) > 0:
                good = np.setdiff1d(df.index, df.index[bad])
                df = df.loc[good]
                display(f"{len(bad)} rows expunged")
            df.drop_duplicates(keep='last', inplace=True)
            if d is not None:
                ix = np.where(np.logical_and(df['start_date'] <= d, df['end_date'] > d))[0]
                display(f"No securities found for requested cusips on day: {d}")
                df = df.iloc[ix]
            if df.empty:
                display(f"No securities found for requested cusips")
                return None
            ref = get_sec_id_by_security_ids(np.unique(df['security_id'].to_numpy()),
                                             currency, id_type, active_only, region, exchange)
            # ids = dict.fromkeys(symbols)
            if ref is None:
                return pd.DataFrame()
            if exclude_nan:
                ix = np.where(pd.notnull(ref['sec_id']))[0]
                ref = ref.iloc[ix]
            zx = np.where(np.isin(ref['security_id'].to_numpy(), df['security_id'].to_numpy()))[0]
            ref = ref.iloc[zx].copy()
            ref.sort_values(by='sec_id', inplace=True)
            sids = np.unique(df['security_id'])
            sf = pd.DataFrame()
            for s in sids:
                ix = np.where(ref['security_id'] == s)[0]
                iy = np.where(df['security_id'] == s)[0]
                if len(ix) == 0 or len(iy) == 0:
                    continue
                r1 = ref.iloc[ix]
                d1 = df.iloc[iy]
                for r in r1['sec_id'].to_numpy():
                    iz = np.where(r1['sec_id'] == r)[0]
                    r2 = r1.iloc[iz]
                    tf = util.merge_multiple_by_date_range(r2, d1, 'security_id')
                    sf = pd.concat((sf, tf), axis=0, ignore_index=True)
            ix = np.where(pd.notnull(sf['cusip']))[0]
            sf = sf.iloc[ix]
            return sf
            # for s in symbols:
            #     sx = np.where(df[field] == s)[0]
            #     if len(sx) == 0:
            #         ids[s] = np.array([])
            #         continue
            #     sids = np.unique(df['security_id'].iloc[sx])
            #     rids = np.array([])
            #     for kid in sids:
            #         if kid in ref['security_id'].to_numpy():
            #             rids = np.union1d(rids, ref[kid])
            #     ids[s] = rids
            #     # sf = get_stock_references(rids)
            #     # rx = list(range(len(sf.index)))
            #     # if currency is not None:
            #     #     rx = np.intersect1d(rx, np.where(sf['currency'] == currency)[0])
            #     # if region is not None:
            #     #     rx = np.intersect1d(rx, np.where(sf['region'] == region)[0])
            #     # if id_type is not None:
            #     #     if id_type == 'security':
            #     #         ids[s] = sf['security_id'].iloc[rx].to_numpy()
            #     #     elif id_type == 'regional':
            #     #         rx = np.intersect1d(rx, np.where(sf['id_type'] == 'Regional')[0])
            #     #         ids[s] = sf.index[rx].to_numpy()
            #     #     elif id_type == 'listing':
            #     #         ids[s] = sf['listing_id'].iloc[rx].to_numpy()
            #     #     else:
            #     #         rx = np.intersect1d(rx, np.where(sf['id_type'] == 'Regional')[0])
            #     #         ids[s] = sf.index[rx].to_numpy()
            #     # else:
            #     #     ids[s] = sf.index[rx].to_numpy()
            #     # ids[s] = np.unique(ids[s])
            # return ids
    except db.DatabaseError as dbe:
        display(dbe)
        display(f"Database Error: Unable to get sec_id by {field}")
        if not conn.closed:
            conn.close()
        raise dbe
    except Exception as ee:
        display(ee)
        display(f"Exception: Unable to get sec_id by {field}")
        if not conn.closed:
            conn.close()
        raise ee


def get_sec_id_by_isins(symbols, currency=None, id_type=None, active_only=False, region=None, exchange=None,
                        day=None):
    """
    get sec unique identifier by isin:
    :param symbols: such as '2407966'
    :param currency: default None
    :param id_type: default None, accepted 'security', 'regional', 'listing'
    :param active_only: default False
    :param region: default None
    :param exchange: default None, string or list of strings
    :param day: default None : search all histories
    :return:
            Input:
                get_sec_id_by_isins('US38141G1040',exchange=['NAS','NYS'])
            Output:
                {'US38141G1040': array(['JLJ0VZ-R'], dtype=object)}

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    symbols = np.unique(symbols)
    symbols = symbols[np.where(pd.notnull(symbols))[0]]
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange.upper().strip()])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    if id_type is None or not isinstance(id_type, str):
        id_type = 'regional'
    id_type = id_type.lower().strip()
    if day is not None:
        d = util.parse_date(day)
    else:
        d = None
    field = 'isin'

    query = f"select * from dbo.vw_Get_isin_hist where {field} in "
    conn = get_connection()
    try:
        df = execute_batch(conn, query, symbols)
        conn.close()
        if not df.empty:
            df.rename(columns={'fsym_id': 'security_id'}, inplace=True)
            df.loc[df.index, 'start_date'] = util.parse_date(df['start_date'].to_numpy())
            df.loc[df.index, 'end_date'] = util.parse_date(df['end_date'].to_numpy())
            df.drop_duplicates(keep='last', inplace=True)
            most_recent = np.array([False] * len(df.index))
            ix = np.where(df['most_recent'])[0]
            most_recent[ix] = True
            df.loc[df.index, 'most_recent'] = most_recent
            df.sort_values(by=['security_id', 'end_date'], inplace=True, ignore_index=True, na_position='first')
            first = util.parse_date(19000101)
            last = util.parse_date(99991231)
            ix = np.where(np.logical_and(pd.notnull(df['start_date']), pd.isnull(df['end_date'])))[0]
            df.loc[df.index[ix], 'end_date'] = last
            ix = np.where(pd.isnull(df[['start_date', 'end_date']]).sum(axis=1) == 2)[0]
            bad = np.array([], dtype='int64')
            for kx in ix:
                s = df.loc[df.index[kx], field]
                iz = np.where(df[field] == s)[0]
                if len(iz) == 1:
                    df.loc[df.index[kx], 'start_date'] = first
                    df.loc[df.index[kx], 'end_date'] = last
                    df.loc[df.index[kx], 'most_recent'] = True
                    continue
                if df.loc[df.index[iz[-1]], 'end_date'] < last:
                    if df.loc[df.index[kx], field] == df.loc[df.index[iz[-1]], field]:
                        df.loc[df.index[iz[-1]], 'end_date'] = last
                        df.loc[df.index[iz[-1]], 'most_recent'] = True
                    else:
                        df.loc[df.index[kx], 'start_date'] = df.loc[df.index[iz[-1]], 'end_date']
                        df.loc[df.index[kx], 'end_date'] = last
                        df.loc[df.index[kx], 'most_recent'] = True
                        df.loc[df.index[iz[-1]], 'most_recent'] = False
                else:
                    bad = np.union1d(bad, [kx])
            bad = np.union1d(bad, np.where(pd.isnull(df[['start_date', 'end_date']]).sum(axis=1) == 2)[0])
            if len(bad) > 0:
                good = np.setdiff1d(df.index, df.index[bad])
                df = df.loc[good]
                display(f"{len(bad)} rows expunged")
            df.drop_duplicates(keep='last', inplace=True)
            if d is not None:
                ix = np.where(np.logical_and(df['start_date'] <= d, df['end_date'] > d))[0]
                display(f"No securities found for requested isins on day: {d}")
                df = df.iloc[ix]
            if df.empty:
                display(f"No securities found for requested isins")
                return None
            ref = get_sec_id_by_security_ids(np.unique(df['security_id'].to_numpy()),
                                             currency, id_type, active_only, region, exchange)
            if ref is None:
                return pd.DataFrame()
            zx = np.where(np.isin(ref['security_id'].to_numpy(), df['security_id'].to_numpy()))[0]
            ref = ref.iloc[zx].copy()
            ref.sort_values(by='sec_id', inplace=True)
            sids = np.unique(df['security_id'])
            sf = pd.DataFrame()
            for s in sids:
                ix = np.where(ref['security_id'] == s)[0]
                iy = np.where(df['security_id'] == s)[0]
                if len(ix) == 0 or len(iy) == 0:
                    continue
                r1 = ref.iloc[ix]
                d1 = df.iloc[iy]
                for r in r1['sec_id'].to_numpy():
                    iz = np.where(r1['sec_id'] == r)[0]
                    r2 = r1.iloc[iz]
                    tf = util.merge_multiple_by_date_range(r2, d1, 'security_id')
                    sf = pd.concat((sf, tf), axis=0, ignore_index=True)
            ix = np.where(pd.notnull(sf['isin']))[0]
            sf = sf.iloc[ix]
            return sf
            # ids = dict.fromkeys(symbols)
            # for s in symbols:
            #     sx = np.where(df[field] == s)[0]
            #     if len(sx) == 0:
            #         ids[s] = np.array([])
            #         continue
            #     sids = np.unique(df['security_id'].iloc[sx])
            #     rids = np.array([])
            #     for kid in sids:
            #         if kid in ref:
            #             rids = np.union1d(rids, ref[kid])
            #     ids[s] = rids
            # return ids
    except db.DatabaseError as dbe:
        display(dbe)
        display(f"Database Error: Unable to get sec_id by {field}")
        if not conn.closed:
            conn.close()
        raise dbe
    except Exception as ee:
        display(ee)
        display(f"Exception: Unable to get sec_id by {field}")
        if not conn.closed:
            conn.close()
        raise ee


def get_sec_id_by_security_ids(symbols, currency=None, id_type=None, active_only=False, region=None, exchange=None,
                               day=None, table_flag=True, exclude_nan=True, database='FactSetDataFeed'):
    """
    get sec unique identifier by security ID
    :param symbols:
    :param currency: default None
    :param id_type: default None or regional, also accepted security, or listing
    :param active_only: default False
    :param region: default None
    :param exchange: default None
    :param day: default None
    :param table_flag: default False
    :param exclude_nan: default True
    :param database: default FactSetDataFeed
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 15, 2022
    Modified: May 1, 2023
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    field = 'security_id'
    if id_type is None:
        id_type = 'regional'
    if not isinstance(id_type, str):
        id_type = 'regional'
    id_type = id_type.lower().strip()
    ref = get_references()
    symbols = np.unique(symbols[pd.notnull(symbols)])
    if ref is not None:
        if field not in ref.columns:
            display(f" {field} not recognized")
            raise ValueError(f" s_type: {field} not supported")
        else:
            found = np.isin(symbols, ref[field])
            missing = symbols[np.where(~found)[0]]
    else:
        missing = symbols
    if len(missing) > 0:

        # query = f"select * from ( select sa.SecCode as security_id, sa.AliasCode as sec_id " \
        #         f"from sec.SecAlias sa " \
        #         f"union " \
        #         f"select sah.SecCode as security_id, sah.AliasCode as sec_id " \
        #         f"from sec.SecAliasHistory sah " \
        #         f") T where T.security_id in "
        query = f"select * from sym_v1.sym_coverage where regional_flag = 1 and fsym_security_id in "
        try:
            conn = get_connection(database=database)
            df = execute_batch(conn, query, missing)
            conn.close()
            if not df.empty:
                df.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
                get_references(np.unique(df['sec_id'].to_numpy()))
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id")
            if not conn.closed:
                conn.close()
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id")
            if not conn.closed:
                conn.close()
            raise ee
    ref = get_references()
    if ref is None:
        return None
    if ref.empty:
        return None
    if exclude_nan:
        ix = np.where(pd.notnull(ref['sec_id']))[0]
        ref = ref.iloc[ix]
    ix = np.where(np.isin(ref[field], symbols))[0]
    ref = ref.iloc[ix]
    if day is not None:
        d = util.parse_date(day)
        ix = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ref = ref.iloc[ix]
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(id_type, str):
        if id_type == 'regional':
            ix = np.where(ref['id_type'] == 'Regional')[0]
        elif id_type == 'listing':
            ix = np.where(ref['id_type'] == 'Listing')[0]
        else:
            ix = np.where(ref['id_type'] == 'Regional')[0]
        ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(symbols)
        for s in symbols:
            ix = np.where(ref[field] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref.index[ix].to_numpy())
        return df


def get_sec_id_by_primary_equity_ids(symbols, currency=None, id_type=None, active_only=False, region=None,
                                     exchange=None, day=None, table_flag=True, exclude_nan=True,
                                     database='FactSetDataFeed'):
    """
    get sec unique identifier by security ID
    :param symbols:
    :param currency: default None
    :param id_type: default None or regional, also accepted security, or listing
    :param active_only: default False
    :param region: default None
    :param exchange: default None
    :param day: default None
    :param table_flag: default False
    :param exclude_nan: default True
    :param database: default FactSetDataFeed
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 24, 2023

    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    symbols = util.to_numpy(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    field = 'security_id'
    if id_type is None:
        id_type = 'regional'
    if not isinstance(id_type, str):
        id_type = 'regional'
    id_type = id_type.lower().strip()
    ref = get_references()
    symbols = np.unique(symbols[pd.notnull(symbols)])
    if ref is not None:
        if field not in ref.columns:
            display(f" {field} not recognized")
            raise ValueError(f" s_type: {field} not supported")
        else:
            found = np.isin(symbols, ref[field])
            missing = symbols[np.where(~found)[0]]
    else:
        missing = symbols
    if len(missing) > 0:

        query = f"select * from sym_v1.sym_coverage where regional_flag = 1 and fsym_primary_equity_id in "
        try:
            conn = get_connection(database=database)
            df = execute_batch(conn, query, missing)
            conn.close()
            if not df.empty:
                df.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
                get_references(np.unique(df['sec_id'].to_numpy()))
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id")
            if not conn.closed:
                conn.close()
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id")
            if not conn.closed:
                conn.close()
            raise ee
    ref = get_references()
    if ref is None:
        return None
    if ref.empty:
        return None
    if exclude_nan:
        ix = np.where(pd.notnull(ref['sec_id']))[0]
        ref = ref.iloc[ix]
    if day is not None:
        d = util.parse_date(day)
        ix = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ref = ref.iloc[ix]
    ix = np.where(np.isin(ref['primary_equity_id'].to_numpy(), symbols))[0]
    ref = ref.iloc[ix]
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(id_type, str):
        if id_type == 'regional':
            ix = np.where(ref['id_type'] == 'Regional')[0]
        elif id_type == 'listing':
            ix = np.where(ref['id_type'] == 'Listing')[0]
        else:
            ix = np.where(ref['id_type'] == 'Regional')[0]
        ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(symbols)
        for s in symbols:
            ix = np.where(ref[field] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref.index[ix].to_numpy())
        return df


def get_sec_id_by_bloomberg_ids(symbols, currency=None, id_type=None, active_only=False, region=None, exchange=None,
                                table_flag=True):
    """
    get sec id unique identifier by bloomberg id
    :param symbols:
    :param currency:
    :param id_type: default None, accepted: security, regional (default), and listing
    :param active_only: default False
    :param region: default None
    :param exchange: default None, string or list of strings
    :param table_flag: default False
    :return:

    Example:
        Input:
            get_sec_id_by_bloomberg_ids('BBG000MM2P62',exchange=['NAS'],table_flag=True)
        Output:
             sec_id        bbg_id  ... universe                         name
        0  QLGSL2-R  BBG000MM2P62  ...       EQ  Meta Platforms Inc. Class A


    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 29, 2022
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    v_type = 'sec_id'
    if id_type is not None:
        if isinstance(id_type, str):
            id_type = id_type.lower().strip()
            if id_type == 'listing':
                v_type = 'listing_id'
            elif id_type == 'security':
                v_type = 'security_id'
    field = 'bbg_id'
    ref = pd.DataFrame()
    symbols = np.unique(symbols[pd.notnull(symbols)])
    if len(symbols) > 0:
        query = f"select * from sym_v1.sym_bbg where bbg_id in "
        try:
            conn = get_connection()
            df = execute_batch(conn, query, symbols)
            conn.close()
            if df.empty:
                if table_flag:
                    return ref
                else:
                    return dict.fromkeys(symbols)
            df.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
            ref = get_bloomberg_ids(df['sec_id'].to_numpy(), True, True)
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id by {field}")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id by {field}")
            raise ee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref[field], symbols))[0]
    ref = ref.iloc[ix]
    meta = get_references(ref['sec_id'])
    ref = ref.merge(meta, how='left', left_on='sec_id', right_on='sec_id')
    # ref = util.merge_multiple_by_date_range(ref, meta)
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(symbols)
        for s in symbols:
            ix = np.where(ref[field] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[v_type].iloc[ix].to_numpy())
        return df


def get_sec_id_by_bloomberg_tickers(symbols, currency=None, id_type=None, active_only=False, region=None, exchange=None,
                                    table_flag=True):
    """
    get sec id unique identifier by bloomberg ticker
    :param symbols:
    :param currency:
    :param id_type: default None, accepted: security, regional (default), and listing
    :param active_only: default False
    :param region: default None
    :param exchange: default None, string or list of strings
    :param table_flag: default False
    :return:

    Example:
        Input:
            get_sec_id_by_bloomberg_tickers('IBM US',exchange=['NAS'],table_flag=True)
        Output:
             sec_id        bbg_id  ... universe                                         name
        0  SJY281-R  BBG000BLNNH6  ...       EQ  International Business Machines Corporation


    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: July 29, 2022
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    v_type = 'sec_id'
    if id_type is not None:
        if isinstance(id_type, str):
            id_type = id_type.lower().strip()
            if id_type == 'listing':
                v_type = 'listing_id'
            elif id_type == 'security':
                v_type = 'security_id'
    field = 'bbg_ticker'
    ref = pd.DataFrame()
    symbols = np.unique(symbols[pd.notnull(symbols)])
    if len(symbols) > 0:
        query = f"select * from sym_v1.sym_bbg where bbg_ticker in "
        try:
            conn = get_connection()
            df = execute_batch(conn, query, symbols)
            conn.close()
            if df.empty:
                if table_flag:
                    return ref
                else:
                    return dict.fromkeys(symbols)
            df.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
            ref = get_bloomberg_ids(df['sec_id'].to_numpy(), True, True)
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id by {field}")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id by {field}")
            raise ee
    if ref.empty:
        return None
    ix = np.where(np.isin(ref[field], symbols))[0]
    ref = ref.iloc[ix]
    meta = get_references(ref['sec_id'])
    ref = ref.merge(meta, how='left', left_on='sec_id', right_on='sec_id')
    # ref = util.merge_multiple_by_date_range(ref, meta)
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(symbols)
        for s in symbols:
            ix = np.where(ref[field] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref[v_type].iloc[ix].to_numpy())
        return df


def get_sec_id_by_exchanges(exch, currency=None, id_type=None, active_only=True, security_types=None,
                            day=None, database='FactSetDataFeed'):
    """
    get sec id unique identifier by exchanges
    :param exch:
    :param currency:
    :param id_type: default None, accepted: security, regional (default), and listing
    :param active_only: default True
    :param security_types: default SHARE
    :param day: default None
    :param database: 'FactSetDataFeed'
    :return:

    Example:
        get_sec_id_by_exchanges('NYS')

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 29, 2022
    Modified: May 1, 2023
    """
    if exch is None:
        display(f" no symbol provided")
        return None
    if isinstance(exch, str):
        exch = np.array([exch])
    if isinstance(exch, list):
        exch = np.array(exch)
    if len(exch) == 0:
        display(f" empty exchanges")
    if security_types is None:
        security_types = 'SHARE'
    if isinstance(security_types, str):
        security_types = np.array([security_types])
    if isinstance(security_types, list):
        security_types = np.array(security_types)
    if currency is not None and isinstance(currency, str):
        currency = np.array([currency.upper().strip()])
    if isinstance(currency, list):
        currency = np.array(currency)
    if id_type is not None:
        if isinstance(id_type, str):
            id_type = np.array([id_type.lower().strip()])
        if isinstance(id_type, list):
            id_type = np.array(id_type)
    # s_type = 'exchange'
    exch = np.unique(exch[pd.notnull(exch)])
    global exchange_securities
    if exchange_securities is None:
        missing = exch
    else:
        missing = np.setdiff1d(exch, exchange_securities['exchange'])
    if len(missing) > 0:
        # if active_only:
        #     query = f"select sa.SecCode as security_id, sa.AliasCode as sec_id, sa.AliasType as id_type, " \
        #             f"sa.RefListingExchange as exchange from sec.SecAlias sa inner join sec.SecMaster sm " \
        #             f"on sa.SecCode = sm.SecCode " \
        #             f"where sa.RefListingExchange in "
        # else:
        #     query = f"select * from ( select sa.SecCode as security_id, sa.AliasCode as sec_id, " \
        #             f"sa.AliasType as id_type, sa.RefListingExchange as exchange from sec.SecAlias sa " \
        #             f"union " \
        #             f"select sah.SecCode as security_id, sah.AliasCode as sec_id, sah.AliasType as id_type, " \
        #             f"sah.RefListingExchange as exchange from sec.SecAliasHistory sah" \
        #             f") T where T.exchange in "
        query = f"select * from sym_v1.sym_coverage where fref_listing_exchange in "
        query = query + f"('{missing[0]}'"
        for ix, s in enumerate(missing):
            if ix == 0:
                continue
            if len(s) == 0:
                continue
            query = query + f", '{s.upper().strip()}'"
        query = query + ")"
        if len(security_types) > 0:
            query = query + f" and fref_security_type in ('{security_types[0].upper().strip()}'"
            for ix, s in enumerate(security_types):
                if ix == 0:
                    continue
                query = query + f", '{s.strip().upper()}'"
            query = query + ")"
        conn = get_connection(database=database)
        cursor = conn.cursor()
        try:
            at = util.clock()
            cursor.execute(query)
            et = util.clock()
            records = cursor.fetchall()
            zt = util.clock()
            display(f" {len(records)} rows; "
                    f"{et - at: .1f} seconds to execute; {zt - et: .1f} seconds to fetch")
            df = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            df.rename(columns={'fsym_id': 'sec_id', 'fref_listing_exchange': 'exchange'}, inplace=True)
            if not df.empty:
                if exchange_securities is None:
                    exchange_securities = df
                else:
                    exchange_securities = pd.concat((exchange_securities, df), axis=0, ignore_index=True)
                get_references(df['sec_id'].to_numpy())
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id")
            raise ee
        cursor.close()
        conn.close()
    ref = get_references()
    # data = dict.fromkeys(exchanges)
    if ref is not None:
        if day is not None:
            d = util.parse_date(day)
            ix = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
            ref = ref.iloc[ix]
        iz = np.where(np.isin(ref['exchange'].to_numpy(), exch))[0]
        if active_only:
            ix = np.where(ref['is_active'] == 1)[0]
            iz = np.intersect1d(iz, ix)
        if isinstance(currency, np.ndarray):
            ix = np.where(np.isin(ref['currency'].to_numpy(), currency))[0]
            iz = np.intersect1d(iz, ix)
        if isinstance(id_type, np.ndarray):
            ix = np.where(np.isin(ref['id_type'].to_numpy(), id_type))[0]
            iz = np.intersect1d(iz, ix)
        if isinstance(security_types, np.ndarray):
            ix = np.where(np.isin(ref['security_type'].to_numpy(), security_types))[0]
            iz = np.intersect1d(iz, ix)
        # for s in exchanges:
        #     ix = np.where(ref[s_type] == s)[0]
        #     if isinstance(currency, str):
        #         ix = np.intersect1d(ix, np.where(ref['currency'] == currency)[0])
        #     if active_only:
        #         ix = np.intersect1d(ix, np.where(ref['is_active'])[0])
        #     if id_type is not None:
        #         if id_type == 'security':
        #             ids = ref['security_id'].iloc[ix].to_numpy()
        #         elif id_type == 'regional':
        #             ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
        #             ids = ref.index[ix].to_numpy()
        #         elif id_type == 'listing':
        #             ids = ref['listing_id'].iloc[ix].to_numpy()
        #         else:
        #             ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
        #             ids = ref.index[ix].to_numpy()
        #     else:
        #         ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
        #         ids = ref.index[ix].to_numpy()
        #     ids = np.unique(ids[pd.notnull(ids)])
        #     data[s] = ids
        data = ref.iloc[iz].copy()
        return data
    else:
        return None


def get_sec_id_by_regions(regions, currency=None, id_type=None, active_only=True, security_types=None,
                          day=None, database='FactSetDataFeed'):
    """
    get sec id unique identifier by regions
    :param regions:
    :param currency:
    :param id_type: default None, accepted: security, regional (default), and listing
    :param active_only: default True
    :param security_types: default SHARE
    :param day: default None
    :param database: default 'FactSetDataFeed'
    :return:

    Author: Yun Chen
    Copyright: IndigoDao LLC
    Date: August 15, 2022
    Modified: May 1, 2023
    """
    if regions is None:
        display(f" no region provided")
        return None
    if isinstance(regions, str):
        regions = np.array([regions])
    if isinstance(regions, list):
        regions = np.array(regions)
    if len(regions) == 0:
        display(f" empty regions")
    if security_types is None:
        security_types = 'SHARE'
    if isinstance(security_types, str):
        security_types = np.array([security_types])
    if isinstance(security_types, list):
        security_types = np.array(security_types)
    if currency is not None and isinstance(currency, str):
        currency = np.array([currency.upper().strip()])
    if isinstance(currency, list):
        currency = np.array(currency)
    if id_type is not None:
        if isinstance(id_type, str):
            id_type = np.array([id_type.lower().strip()])
        if isinstance(id_type, list):
            id_type = np.array(id_type)
    regions = np.unique(regions[pd.notnull(regions)])
    global region_securities
    if region_securities is None:
        missing = regions
    else:
        missing = np.setdiff1d(regions, region_securities['region'])
    if len(regions) > 0:
        # if active_only:
        #     query = f"select * from ( select sa.SecCode as security_id, sa.AliasCode as sec_id, " \
        #             f"sa.AliasType as id_type, sa.Region as region, sm.RefSecurityType as security_type  " \
        #             f"from sec.SecAlias sa inner join sec.SecMaster sm " \
        #             f"on sa.SecCode = sm.SecCode ) T " \
        #             f"where T.region in "
        # else:
        #     query = f"select * from ( select sa.SecCode as security_id, sa.AliasCode as sec_id, " \
        #             f"sa.AliasType as id_type, sa.Region as region, sm.RefSecurityType as security_type " \
        #             f"from sec.SecAlias sa inner join sec.SecMaster sm " \
        #             f"on sa.SecCode = sm.SecCode " \
        #             f"union " \
        #             f"select sah.SecCode as security_id, sah.AliasCode as sec_id, sah.AliasType as id_type, " \
        #             f"sah.Region as region, smh.RefSecurityType as security_type" \
        #             f"from sec.SecAliasHistory sah inner join sec.SecMasterHistory smh " \
        #             f"on sah.SecCode = smh.SecCode" \
        #             f") T where T.region in "
        query = f"select * from sym_v1.sym_region where region in "
        query = query + f"('{missing[0]}'"
        for ix, s in enumerate(missing):
            if ix == 0:
                continue
            if len(s) == 0:
                continue
            query = query + f", '{s.upper().strip()}'"
        query = query + ")"
        # query = query + f"('{regions[0]}'"
        # for ix, s in enumerate(regions):
        #     if ix == 0:
        #         continue
        #     query = query + f", '{s}'"
        # query = query + ")"
        # if len(security_types) > 0:
        #     query = query + f" and T.security_type in ('{security_types[0].upper().strip()}'"
        #     for ix, s in enumerate(security_types):
        #         if ix == 0:
        #             continue
        #         query = query + f", '{s.strip().upper()}'"
        #     query = query + ")"
        conn = get_connection(database=database)
        cursor = conn.cursor()
        try:
            at = util.clock()
            cursor.execute(query)
            et = util.clock()
            records = cursor.fetchall()
            zt = util.clock()
            display(f" {len(records)} rows; "
                    f"{et - at: .1f} seconds to execute; {zt - et: .1f} seconds to fetch")
            df = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            df.rename(columns={'fsym_id': 'sec_id'}, inplace=True)
            if not df.empty:
                if region_securities is None:
                    region_securities = df
                else:
                    region_securities = pd.concat((region_securities, df), axis=0, inplace=True)
                get_references(df['sec_id'].to_numpy())
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id")
            raise ee
        cursor.close()
        conn.close()
    ref = get_references()
    # data = dict.fromkeys(regions)
    # if ref is not None:
    #     for s in regions:
    #         ix = np.where(ref[s_type] == s)[0]
    #         if isinstance(currency, str):
    #             ix = np.intersect1d(ix, np.where(ref['currency'] == currency)[0])
    #         if active_only:
    #             ix = np.intersect1d(ix, np.where(ref['is_active'])[0])
    #         if id_type is not None:
    #             if id_type == 'security':
    #                 ids = ref['security_id'].iloc[ix].to_numpy()
    #             elif id_type == 'regional':
    #                 ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
    #                 ids = ref.index[ix].to_numpy()
    #             elif id_type == 'listing':
    #                 ids = ref['listing_id'].iloc[ix].to_numpy()
    #             else:
    #                 ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
    #                 ids = ref.index[ix].to_numpy()
    #         else:
    #             ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
    #             ids = ref.index[ix].to_numpy()
    #         ids = np.unique(ids[pd.notnull(ids)])
    #         data[s] = ids
    # return data
    if ref is not None:
        if day is not None:
            d = util.parse_date(day)
            ix = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
            ref = ref.iloc[ix]
        iz = np.where(np.isin(ref['region'].to_numpy(), regions))[0]
        if active_only:
            ix = np.where(ref['is_active'] == 1)[0]
            iz = np.intersect1d(iz, ix)
        if isinstance(currency, np.ndarray):
            ix = np.where(np.isin(ref['currency'].to_numpy(), currency))[0]
            iz = np.intersect1d(iz, ix)
        if isinstance(id_type, np.ndarray):
            ix = np.where(np.isin(ref['id_type'].to_numpy(), id_type))[0]
            iz = np.intersect1d(iz, ix)
        if isinstance(security_types, np.ndarray):
            ix = np.where(np.isin(ref['security_type'].to_numpy(), security_types))[0]
            iz = np.intersect1d(iz, ix)
        # for s in exchanges:
        #     ix = np.where(ref[s_type] == s)[0]
        #     if isinstance(currency, str):
        #         ix = np.intersect1d(ix, np.where(ref['currency'] == currency)[0])
        #     if active_only:
        #         ix = np.intersect1d(ix, np.where(ref['is_active'])[0])
        #     if id_type is not None:
        #         if id_type == 'security':
        #             ids = ref['security_id'].iloc[ix].to_numpy()
        #         elif id_type == 'regional':
        #             ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
        #             ids = ref.index[ix].to_numpy()
        #         elif id_type == 'listing':
        #             ids = ref['listing_id'].iloc[ix].to_numpy()
        #         else:
        #             ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
        #             ids = ref.index[ix].to_numpy()
        #     else:
        #         ix = np.intersect1d(ix, np.where(ref['id_type'] == 'Regional')[0])
        #         ids = ref.index[ix].to_numpy()
        #     ids = np.unique(ids[pd.notnull(ids)])
        #     data[s] = ids
        data = ref.iloc[iz].copy()
        return data
    else:
        return None


def get_sec_id_by_entity_ids(symbols, currency=None, id_type=None, active_only=False, region=None, exchange=None,
                             table_flag=True, universe_type='EQ', security_type='SHARE', day=None,
                             database='FactSetDataFeed', equity_only=True, exclude_nan=True):
    """
    get sec id unique identifier by entity ids
    :param symbols:
    :param currency:
    :param id_type: default None, accepted: security, regional, listing for output
    :param active_only: default False
    :param region: default None
    :param exchange: default None, string or list of strings
    :param table_flag: default False
    :param universe_type: default 'EQ' for equities
    :param security_type: default 'SHARE'
    :param day: default None
    :param database: default 'FactSetDataFeed'
    :param equity_only: default True
    :param exclude_nan: default True
    :return:

    Example:
            Input:
                get_sec_id_by_entity_ids('002615-E')
            Output:

    Author: Yun Chen
    Copyright: IndigoDao LLC
    Date: August 15, 2022
    Modified: May 1, 2023
    """
    if symbols is None:
        display(f" no symbol provided")
        return None
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    if len(symbols) == 0:
        display(f" empty symbols")
    if currency is not None and isinstance(currency, str):
        currency = currency.upper().strip()
    if region is not None and isinstance(region, str):
        region = region.upper().strip()
    if id_type is not None:
        if isinstance(id_type, str):
            id_type = id_type.lower().strip()
    if universe_type is None:
        universe_type = 'EQ'
    if isinstance(universe_type, str):
        universe_type = np.array([universe_type])
    if isinstance(universe_type, list):
        universe_type = np.array(universe_type)
    if security_type is None:
        security_type = 'SHARE'
    if isinstance(security_type, str):
        security_type = np.array([security_type])
    if isinstance(security_type, list):
        security_type = np.array(security_type)
    if exchange is None:
        exchange = np.array([])
    if isinstance(exchange, str):
        exchange = np.array([exchange.upper().strip()])
    if isinstance(exchange, list):
        exchange = np.array(exchange)
    if not isinstance(table_flag, bool):
        table_flag = False
    ref = get_references()
    field = 'entity_id'
    symbols = np.unique(symbols[pd.notnull(symbols)])
    if ref is not None:
        if field not in ref.columns:
            display(f" {field} not recognized")
            raise ValueError(f" s_type: {field} not supported")
        else:
            found = np.isin(symbols, ref[field])
            missing = symbols[np.where(~found)[0]]
    else:
        missing = symbols
    if len(missing) > 0:
        # query = f"select * from (select sm.SecCode as security_id, sa.AliasCode as sec_id, " \
        #         f"sm.EntityId as entity_id, " \
        #         f"sm.RefSecurityType as security_type, " \
        #         f"sa.AliasType as id_type, sm.UniverseType as universe_type from sec.SecMaster sm " \
        #         f"inner join sec.SecAlias sa on sa.SecCode = sm.SecCode " \
        #         f"union " \
        #         f"select smh.secCode as security_id, sah.AliasCode as sec_id, " \
        #         f"smh.EntityId as entity_id, " \
        #         f"smh.RefSecurityType as security_type, " \
        #         f"sah.AliasType as id_type, smh.UniverseType as universe_type from sec.SecMasterHistory smh " \
        #         f"inner join sec.SecAliasHistory sah on sah.SecCode = smh.SecCode " \
        #         f") T where T.entity_id in "
        query = f"select sh.* from sym_v1.sym_sec_entity_hist sh "
        if equity_only:
            query += "inner join sym_v1.sym_coverage sc on sc.fsym_id = sh.fsym_id "
        query += f" where "
        if equity_only:
            query += f" sc.universe_type = 'EQ' and "
        query += " sh.factset_entity_id in "
        conn = get_connection(database=database)
        try:
            df = execute_batch(conn, query, missing)
            conn.close()
            if not df.empty:
                security_ids = np.unique(df['fsym_id'])
                ids = get_sec_id_by_security_ids(security_ids)
                if not ids.empty:
                    get_references(ids['sec_id'].to_numpy())
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id")
            raise ee
    ref = get_references()
    if ref is None or ref.empty:
        return None
    if exclude_nan:
        ix = np.where(pd.notnull(ref['sec_id']))[0]
        ref = ref.iloc[ix]
    ix = np.where(np.isin(ref[field], symbols))[0]
    ref = ref.iloc[ix]
    if day is not None:
        d = util.parse_date(day)
        ix = np.where(np.logical_and(ref['start_date'] <= d, ref['end_date'] > d))[0]
        ref = ref.iloc[ix]
    if active_only:
        ix = np.where(ref['is_active'] == 1)[0]
        ref = ref.iloc[ix]
    if len(exchange) > 0:
        ix = np.where(np.isin(ref['exchange'], exchange))[0]
        ref = ref.iloc[ix]
    if len(universe_type) > 0:
        ix = np.where(np.isin(ref['universe'], universe_type))[0]
        ref = ref.iloc[ix]
    if len(security_type) > 0:
        ix = np.where(np.isin(ref['security_type'], security_type))[0]
        ref = ref.iloc[ix]

    if isinstance(currency, str):
        ix = np.where(ref['currency'] == currency.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(region, str):
        ix = np.where(ref['region'] == region.upper().strip())[0]
        ref = ref.iloc[ix]
    if isinstance(id_type, str):
        if id_type == 'regional':
            ix = np.where(ref['id_type'] == 'Regional')[0]
        elif id_type == 'listing':
            ix = np.where(ref['id_type'] == 'Listing')[0]
        else:
            ix = np.where(ref['id_type'] == 'Regional')[0]
        ref = ref.iloc[ix]
    if table_flag:
        return ref
    else:
        df = dict.fromkeys(symbols)
        for s in symbols:
            ix = np.where(ref[field] == s)[0]
            df[s] = np.array([])
            if len(ix) == 0:
                continue
            df[s] = np.unique(ref.index[ix].to_numpy())
        return df


def get_related_security_map(sec_ids=None):
    global related_map
    if related_map is None:
        file = os.path.join('market', 'reference', 'related_map.qd')
        related_map = util.load_data(file)
    rf = related_map.copy(deep=True)
    rf.reset_index(inplace=True)
    rf = rf.pivot(index='row', columns='column', values='value')
    if sec_ids is not None:
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        df = pd.DataFrame(0, index=sec_ids, columns=sec_ids)
        df.update(rf)
    else:
        df = rf.copy()
    df.fillna(0, inplace=True)
    return df


# -----------------------------------------------------------
#
# Portfolio loaders
#
# -----------------------------------------------------------
def get_portfolio_references(portfolio_ids=None):
    """
    portfolio reference information such as names
    :param portfolio_ids:
    :return:

    Example:
        Input:
            get_portfolio_references(12)
        Output:
            get_portfolio_references(12)
               ReferenceId   Source ReferenceCode  ... ModifiedBy ModifiedOn IsDeleted
            0           12  INDEXIQ       IQGLRND  ...       None       None     False

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 19, 2022
    """
    if 'portfolio reference' in cache:
        ref = cache['portfolio reference']
    else:
        ref = None

    if ref is None:
        sql = f"select * from ref.ReferenceMaster where IsDeleted = 0"
        conn = get_connection()
        cursor = conn.cursor()
        try:
            ac = util.clock()
            cursor.execute(sql)
            records = cursor.fetchall()
            ref = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            ec = util.clock()
            display(f"{ec - ac: .1f} seconds to load portfolio reference")
            cache['portfolio reference'] = ref
        except db.DatabaseError as dbe:
            display(dbe)
            display(f" Unable to get sec_id")
            raise dbe
        except Exception as ee:
            display(ee)
            display(f" Unable to get sec_id")
            raise ee
    if portfolio_ids is None:
        return ref
    ix = np.where(ref['ReferenceId'] == portfolio_ids)[0]
    return ref.iloc[ix]


def get_portfolio_ids(symbols):
    """
    by portfolio/index code, get index ID

    :param symbols:
    :return:

    Example:
        Input:
            get_portfolio_ids('IQGLRND')
        Output:
               ReferenceId   Source ReferenceCode  ... ModifiedBy ModifiedOn IsDeleted
            0           12  INDEXIQ       IQGLRND  ...       None       None     False
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 19, 2022
    """
    if symbols is None:
        display(f" no valid symbols")
        return None
    sql = f"select * from ref.ReferenceMaster where IsDeleted = 0"
    if isinstance(symbols, int) or isinstance(symbols, str):
        symbols = np.array([symbols])
    if isinstance(symbols, list):
        symbols = np.array(symbols)
    sql = sql + f" and ReferenceCode in ('{symbols[0]}'"
    for ix, p in enumerate(symbols):
        if ix == 0:
            continue
        sql = sql + f", '{p}'"
    sql = sql + ")"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        records = cursor.fetchall()
        df = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        return df
    except db.DatabaseError as dbe:
        display(dbe)
        display(f" Unable to get index ID")
        raise dbe
    except Exception as ee:
        display(ee)
        display(f" Unable to get sec_id")
        raise ee


def get_positions(start_date, end_date, portfolio_id, p_type='WEIGHT', calendar_str='US', forward_fill_days=0,
                  normalize=True):
    """
    get positions for official and benchmark holdings
    :param start_date:
    :param end_date:
    :param portfolio_id: integer
    :param p_type: default 'WEIGHT'
    :param calendar_str: default 'GL'
    :param forward_fill_days: default 0
    :param normalize: default True, if p_type is share, normalize is set to false
    :return:

    Example:
        Input:
            get_positions(20220729, 20220731, 14)
        Output:
                        B19ST9-R  B81TLL-R  BK6JKQ-R  ...  X643T6-R  XG4P3Q-R  XLV24X-R
            2022-07-29  0.017682   0.01097  0.003756  ...  0.003131   0.00261   0.01906
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    days = util.load_business_days(calendar_str, start_date, end_date)
    if len(days) == 0:
        display(f" calendar: {calendar_str} no valid business days")
        return None
    if forward_fill_days is None:
        forward_fill_days = 0
    if forward_fill_days == 0:
        p_days = days
    elif forward_fill_days > 0:
        all_days = util.load_business_days(calendar_str, None, end_date)
        ix = np.where(all_days == days[0])[0][0]
        p_days = all_days[ix - forward_fill_days:]
    if p_type is None or not isinstance(p_type, str):
        p_type = 'WEIGHT'
    p_type = p_type.upper().strip()
    if p_type in ('WEIGHT', 'WT', 'WTS', 'WEIGHTS'):
        p_type_id = 2
    else:
        p_type_id = 1
        normalize = False
    df = pd.DataFrame(index=p_days, dtype=np.float64)
    query = f"select AsOfDate as date, ReferenceId, SecCode as security_id," \
            f"AliasCode as sec_id, ReferenceValue as value " \
            f" from hold.Holdings where IsDeleted = 0 and " \
            f" ReferenceValueType = {p_type_id} and " \
            f" AsOfDate between '{p_days[0].strftime(util.yyyy_mm_dd_format)}' and " \
            f"'{p_days[-1].strftime(util.yyyy_mm_dd_format)}' and " \
            f"ReferenceId = {portfolio_id}" \
            f" and ReferenceValue IS NOT NULL and SecCode IS NOT NULL " \
            f" and AliasCode <> \'\'"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        ac = util.clock()
        cursor.execute(query)
        records = cursor.fetchall()
        ec = util.clock()
        display(f"{len(records)} rows: {ec - ac: .1f} seconds")
        pf = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        if pf.empty:
            display(f"{portfolio_id}: {p_type}: None found for period:"
                    f" {df.index[0]} - {df.index[-1]}")
            return df
        pf.drop_duplicates(keep='last', inplace=True)
        good_index = np.where(pf['value'] != 0)[0]
        pf = pf.iloc[good_index]
        zf = pf.pivot(index='date', columns='sec_id', values='value')
        zf.reset_index(inplace=True)
        zf['date'] = util.parse_date(zf['date'])
        zf.set_index('date', inplace=True)
        zf.index.name = None
        zf.columns.name = None
        df = df.combine_first(zf)
        missing = pd.isnull(df).sum(axis=1)
        mx = np.where(missing == len(df.columns))[0]
        df.fillna(0, inplace=True)
        if len(mx) > 0:
            df.loc[df.index[mx], df.columns] = np.nan
            display(f"{len(mx)} days missing holdings: {df.index[mx[0]]} ...")
            if forward_fill_days is not None and forward_fill_days > 0:
                df.fillna(method='pad', limit=forward_fill_days, inplace=True)
                still_missing = np.where(pd.isnull(df).sum(axis=1) == len(df.columns))[0]
                display(f"{len(mx) - len(still_missing)} out of {len(mx)} days forward-filled")
        df = df.loc[days]
        display(f"{portfolio_id}: {p_type}: {len(df.index)} dates x {len(df.columns)} securities"
                f" {df.index[0]} - {df.index[-1]}")
        good_index = np.where(pd.notnull(df).sum(axis=0) > 0)[0]
        df = df.iloc[:, good_index]
        good_index = np.where((df == 0).sum(axis=0) < len(df.index))[0]
        df = df.iloc[:, good_index]
        if normalize:
            multiplier = 1 / df.sum(axis=1).to_numpy()
            multiplier = multiplier.reshape((len(multiplier), 1))
            multiplier = np.repeat(multiplier, len(df.columns), axis=1)
            mf = pd.DataFrame(multiplier, index=df.index, columns=df.columns)
            df = df * mf
        return df
    except db.DatabaseError as dbe:
        display(dbe)
        display(query)
        display(f" Unable to get portfolio ({p_type}): {portfolio_id}")
        raise dbe
    except Exception as ee:
        display(ee)
        display(query)
        display(f" Unable to get portfolio ({p_type}): {portfolio_id}")
        raise ee

# ------------------------------------------------------------
#
#   Classifications
#
# ------------------------------------------------------------


@ft.lru_cache()
def get_classification_meta_map(source='COSMOS', bus_day=None, levels=3):
    source = source.strip().upper()
    if source == 'RBICS':
        return get_rbics_structure(bus_day, levels)
    file = os.path.join(util.default_output_location('classifications'), source, 'meta_map.qd')
    if not os.path.exists(file):
        display(f" {util.current_time()}: Classification ({source}) not found in\n{file}")
        return None
    return util.load_data(file)


@ft.lru_cache()
def get_all_classifications(source='COSMOS'):
    file = os.path.join('classifications', source, 'classification.qd')
    return util.load_data(file)


def get_classification(sec_ids=None, level='sector', source='COSMOS', as_of=util.today(), vector_flag=False):
    """
    get classification dataframe, index being security IDs, columns being groups
    :param sec_ids:
    :param level:
    :param source: default 'COSMOS'
    :param as_of: default today
    :param vector_flag: default False
    :return:
    """
    source = source.strip().upper()
    meta_map = get_classification_meta_map(source)
    if level is None or not isinstance(level, str):
        level = 'sector'
        display(f" {util.current_time()}: unrecognized classification level, assumed default {level}")
    levels = meta_map.columns
    level = level.strip().lower()
    if level not in levels:
        raise Exception(f"Requested level {level} not found in map ({source})")
    idx = np.where(levels == level)[0][0]
    groups = list(set(meta_map.iloc[:, idx]))
    ref = get_all_classifications(source)
    if as_of is not None:
        ad = util.parse_date(as_of)
        if ad is not None:
            ix = np.where(np.logical_and(ref['from_dt'] <= ad, ref['to_dt'] > ad))[0]
            ref = ref.iloc[ix]
    if sec_ids is None:
        ids = ref.index
        sec_ids = ref.index.to_numpy()
    else:
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        ids = np.intersect1d(sec_ids, ref.index)
    ref = ref.loc[ids]
    if vector_flag is None or not isinstance(vector_flag, bool):
        vector_flag = False
    if not vector_flag:
        df = pd.DataFrame(0, index=sec_ids, columns=groups)
        ref['value'] = 1
        ref.reset_index(inplace=True)
        ref.rename(columns={ref.columns[0]: 'sec_ids'}, inplace=True)
        ref = ref[['sec_ids', level, 'value']]
        ref.drop_duplicates(keep='last', inplace=True)
        zf = ref.pivot(index='sec_ids', columns=level, values='value')
        df.update(zf)
        df.fillna(0)
        return df
    else:
        df = pd.DataFrame(None, index=sec_ids, columns=['values'])
        ref.reset_index(inplace=True)
        ref.rename(columns={ref.columns[0]: 'sec_ids'}, inplace=True)
        ref = ref[['sec_ids', level]]
        ref.drop_duplicates(keep='last', inplace=True)
        ref.set_index('sec_ids', inplace=True)
        df.loc[ids, 'values'] = ref.loc[ids, level]
        return df


@ft.lru_cache()
def get_classification_hierarchy(source='COSMOS'):
    """
    get classification hierarchies
    :param source:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if source is None or not isinstance(source, str):
        source = 'COSMOS'
    source = source.strip().upper()
    if source == 'RBICS':
        return get_rbics_hierarchy()
    file = os.path.join(util.default_output_location('classifications'), source, 'hierarchy.qd')
    df = util.load_data(file)
    return df


# ------------------------------------------------------------
#
#   Leading Indicators
#
# ------------------------------------------------------------


def get_regimes(start_date=None, end_date=None, indicator='cosmos_us', calendar_str='US', freq='DAILY'):
    if not isinstance(indicator, str):
        display(f"No valid indicator, default 'cosmos_us'")
        return None
    ref = get_indicator_references()
    indicator = indicator.lower().strip()
    if indicator not in list(ref['indicators']):
        display(f"{indicator} not supported")
        return None
    dates = util.load_business_days(calendar_str, start_date, end_date, freq)
    history = get_regime_history()
    ix = np.where(history['indicators'] == indicator)[0]
    ts = history.iloc[ix]
    df = pd.DataFrame(index=dates, columns=['values', 'regimes'])
    if ts.empty:
        return df
    ix = np.where(~np.logical_or(ts['from_date'] > dates[-1], ts['to_date'] < dates[0]))[0]
    ts = ts.iloc[ix]
    if len(ix) == 0:
        return df
    for i in ts.index:
        f = ts.loc[i, 'from_date']
        t = ts.loc[i, 'to_date']
        v = ts.loc[i, 'values']
        r = ts.loc[i, 'regimes']
        ix = np.where(np.logical_and(dates >= f, dates < t))[0]
        if len(ix) == 0:
            continue
        df.loc[dates[ix], 'values'] = v
        df.loc[dates[ix], 'regimes'] = r
    return df


def get_regime_reference(indicator='cosmos_us'):
    meta_map = get_regime_meta_map()
    ix = np.where(meta_map['indicators'] == indicator.strip())[0]
    return meta_map.iloc[ix]


def get_regime_name(value, indicator='cosmos_us'):
    ref = get_regime_reference(indicator)
    ix = np.where(ref['values'] == value)[0]
    if len(ix) == 0:
        return None
    else:
        return ref.loc[ref.index[ix[0]], 'regimes']


@ft.lru_cache()
def get_indicator_references():
    file = os.path.join(util.default_output_location('macro'), f"indicator_references.qd")
    return util.load_data(file)


@ft.lru_cache()
def get_regime_meta_map():
    file = os.path.join(util.default_output_location('macro'), f"regime_meta_map.qd")
    return util.load_data(file)

#  ----------------------------------------------------------------------------
#


def get_entity_names(entities):
    if entities is None:
        display(f"No valid entities")
        return None
    if isinstance(entities, str):
        entities = np.array([entities])
    elif isinstance(entities, list):
        entities = np.array(entities)
    elif isinstance(entities, pd.DataFrame) or isinstance(entities, pd.Series):
        entities = entities.to_numpy()
    elif not isinstance(entities, np.ndarray):
        raise ValueError(f"Not accepted format for entities")
    entities = np.unique(entities)
    sql = f"select * from sym_v1.sym_entity where factset_entity_id in"
    try:
        conn = get_connection(database='FactSetDataFeed')
        cursor = get_cursor(conn)
        data = execute_batch(conn, sql, entities, 500, True)
        data.drop_duplicates(inplace=True, ignore_index=True)
        cursor.close()
        conn.close()
        return data
    except ValueError as ve:
        display(f"{ve}")
        display(f"Unable to get entity structure history due to value error")
        cursor.close()
        conn.close()
        raise ve
    except Exception as ee:
        display(f"{ee}")
        display(f"Unable to get entity structure history due to exception")
        cursor.close()
        conn.close()
        raise ee


def get_entity_types(types=None):
    global entity_types
    if entity_types is None:
        sql = f"select * from ref_v2.entity_type_map"
        try:
            conn = get_connection(database='FactSetDataFeed')
            cursor = get_cursor(conn)
            cursor.execute(sql)
            records = cursor.fetchall()
            entity_types = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get entity type map due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to get entity type map due to exception")
            raise ee
    if entity_types is None:
        return None
    if entity_types.empty:
        return None
    if types is not None:
        if isinstance(types, str):
            types = np.array([types])
        if isinstance(types, list):
            types = np.array(types)
        ix = np.where(np.isin(entity_types['entity_type_code'].to_numpy(), types))[0]
        return entity_types.iloc[ix]
    else:
        return entity_types


def get_entity_structure_history(entity_ids, start_date=None, end_date=None, ent_types=None):

    if entity_ids is None:
        display(f"No valid entity ids; returning None")
        return None
    if isinstance(entity_ids, str):
        entity_ids = np.array([entity_ids])
    if isinstance(entity_ids, list):
        entity_ids = np.array(entity_ids)
    entity_ids = np.unique(entity_ids)
    sql = f"select es.*, se.entity_proper_name as ult_parent_entity_proper_name, " \
          f"se.iso_country, se.entity_type from ent_v1.ent_entity_str_hist es " \
          f"join sym_v1.sym_entity se on es.factset_ult_parent_entity_id " \
          f"= se.factset_entity_id where es.factset_entity_id in "
    suffix = f"ORDER BY start_date"
    try:
        conn = get_connection(database='FactSetDataFeed')
        cursor = get_cursor(conn)
        data = execute_batch(conn, sql, entity_ids, 500, True, suffix)
        data.drop_duplicates(inplace=True, ignore_index=True)
        cursor.close()
        conn.close()
    except ValueError as ve:
        display(f"{ve}")
        display(f"Unable to get entity structure history due to value error")
        cursor.close()
        conn.close()
        raise ve
    except Exception as ee:
        display(f"{ee}")
        display(f"Unable to get entity structure history due to exception")
        cursor.close()
        conn.close()
        raise ee
    if data is None:
        return None
    if data.empty:
        return data
    nx = np.where(np.logical_and(pd.notnull(data['start_date']), pd.isnull(data['end_date'])))[0]
    if len(nx) > 0:
        data.loc[data.index[nx], 'end_date'] = util.parse_date(99991231)
    names = get_entity_names(data['factset_entity_id'].to_numpy())
    names.rename(columns={'factset_entity_id': 'entity_id'}, inplace=True)
    data = data.merge(names[['entity_id', 'entity_proper_name']], how='left', left_on='factset_entity_id',
                      right_on='entity_id')
    data.drop('entity_id', axis=1, inplace=True)
    ix = np.array(range(len(data.index)))
    if ent_types is not None:
        if isinstance(ent_types, str):
            ent_types = np.array([ent_types])
        if isinstance(ent_types, list):
            ent_types = np.array(ent_types)
        ent_types = np.unique(ent_types)
        ent_types = np.char.strip(np.char.upper(ent_types))
        iz = np.where(np.isin(data['entity_type'].to_numpy(), ent_types))[0]
        ix = np.intersect1d(ix, iz)
    if start_date is not None:
        sd = util.parse_date(start_date)
        iz = np.where(data['end_date'] < sd)[0]
        ix = np.setdiff1d(ix, iz)
    if end_date is not None:
        ed = util.parse_date(end_date)
        iz = np.where(data['start_date'] > ed)[0]
        ix = np.setdiff1d(ix, iz)
    return data.iloc[ix]


def get_primary_equity_by_entities(entity_ids, skip_missing=False, sec_type=None, currency=None):
    """
    get primary equity Security and Regional IDs for a given set of entity_ids
    Parameters
    ----------
    entity_ids
    skip_missing: default False
    sec_type: default None
    currency: default None

    Returns
    -------

    """
    if entity_ids is None:
        display(f"No valid entity ids; returning None")
        return None
    if isinstance(entity_ids, str):
        entity_ids = np.array([entity_ids])
    if isinstance(entity_ids, list):
        entity_ids = np.array(entity_ids)
    entity_ids = np.unique(entity_ids)
    ent = get_entity_names(entity_ids)

    sql = f"select ss.*, sc.fsym_id as sec_id, sc.currency, sc.proper_name, " \
          f"sc.fsym_primary_equity_id, sc.fsym_primary_listing_id, sc.active_flag, " \
          f"sc.fref_security_type, sc.fref_listing_exchange, sc.listing_flag, sc.regional_flag," \
          f"sc.security_flag, sc.fsym_regional_id, sc.fsym_security_id, sc.universe_type " \
          f"from sym_v1.sym_sec_entity_hist ss " \
          f"join sym_v1.sym_coverage sc on ss.fsym_id = sc.fsym_security_id " \
          f" where sc.fref_security_type in ('UNIT', 'SHARE', 'MF_C', 'ADR', 'GDR', 'DR', 'NVDR') and " \
          f"sc.currency IS NOT NULL and " \
          f"sc.fsym_primary_equity_id IS NOT NULL and " \
          f"sc.fsym_primary_listing_id IS NOT NULL and " \
          f"sc.regional_flag = 1 and " \
          f"ss.factset_entity_id in "
    # sql = f"select ss.*, sc.*, en.entity_type from sym_v1.sym_sec_entity_hist ss " \
    #       f"join sym_v1.sym_coverage sc on ss.fsym_id = sc.fsym_id " \
    #       f"join sym_v1.sym_entity en on ss.factset_entity_id = en.factset_entity_id " \
    #       f" where sc.fref_security_type = 'SHARE' and " \
    #       f"fsym_primary_equity_id IS NOT NULL and ss.factset_entity_id in "
    suffix = f""
    try:
        conn = get_connection(database='FactSetDataFeed')
        cursor = get_cursor(conn)
        data = execute_batch(conn, sql, entity_ids, 500, True, suffix)
        data.drop_duplicates(inplace=True, ignore_index=True)
        cursor.close()
        conn.close()
    except ValueError as ve:
        display(f"{ve}")
        display(f"Unable to get entity structure history due to value error")
        cursor.close()
        conn.close()
        raise ve
    except Exception as ee:
        display(f"{ee}")
        display(f"Unable to get entity structure history due to exception")
        cursor.close()
        conn.close()
        raise ee
    if data is None:
        return None
    data = data.merge(ent[['factset_entity_id', 'iso_country', 'entity_type']], how='outer', on='factset_entity_id')
    nx = np.intersect1d(np.where(pd.notnull(data['start_date']))[0], np.where(pd.isnull(data['end_date']))[0])
    if len(nx) > 0:
        data.loc[data.index[nx], 'end_date'] = util.parse_date(99991231)
    ix = np.array(range(len(data.index)))
    if skip_missing:
        good = np.where(pd.notnull(data['fsym_primary_equity_id']))[0]
        ix = np.intersect1d(ix, good)
        good = np.where(pd.notnull(data['fsym_regional_id']))[0]
        ix = np.intersect1d(ix, good)
    if sec_type is not None:
        if isinstance(sec_type, str):
            good = np.where(data['fref_security_type'] == sec_type.upper().strip())[0]
            ix = np.intersect1d(ix, good)
    if currency is not None:
        if isinstance(currency, str):
            good = np.where(data['currency'] == currency.upper().strip())[0]
            ix = np.intersect1d(ix, good)
    return data.iloc[ix]


def get_primary_equity_share_classes(sec_ids=None, entity_ids=None, start_date=None, end_date=None):
    """

    Parameters
    ----------
    sec_ids: default None
    entity_ids: default None
    start_date: default None
    end_date: default None

    Returns

            data frame, with columns: entity_id, sec_id, currency, name, exchange, primary_equity_id
    -------
    Examples:
        get_primary_equity_share_classes('JLJ0VZ-R', ['0FPWZZ-E', '003JLG-E'])

    Author : Yun Chen
    Indigo Dao, LLC
    July 25, 2023

    """

    if sec_ids is None and entity_ids is None:
        raise ValueError(f"No valid sec_id (regional IDs) or entity_ids")
    global primary_share_classes
    result = pd.DataFrame(columns=['entity_id', 'sec_id', 'currency', 'name', 'exchange', 'primary_equity_id',
                                   'start_date', 'end_date'])
    if primary_share_classes is None:
        primary_share_classes = result.copy()
    if entity_ids is not None:
        entities = util.to_numpy(entity_ids)
    else:
        entities = np.array([])
    if sec_ids is not None:
        sec_ids = np.unique(util.to_numpy(sec_ids))
        ref = get_references(sec_ids)
        entities = np.union1d(entities, np.unique(ref['entity_id']))
    missing = np.setdiff1d(entities, primary_share_classes['entity_id'].to_numpy())
    if len(missing) > 0:
        query = f"select a.factset_entity_id as entity_id, c.fsym_id as sec_id, c.currency, "
        query += f"c.proper_name as name, c.fref_listing_exchange as exchange, "
        query += "c.fsym_primary_equity_id as primary_equity_id "
        query += f"from sym_v1.sym_sec_entity_hist a "
        query += f"join sym_v1.sym_coverage b on a.fsym_id=b.fsym_id "
        query += f"join sym_v1.sym_coverage c on c.fsym_id=b.fsym_primary_listing_id "
        query += f"join sym_v1.sym_coverage d on c.fsym_primary_equity_id=d.fsym_id "
        query += f"join sym_v1.sym_coverage e on d.fsym_primary_listing_id=e.fsym_id "
        query += f"and e.fref_listing_exchange=c.fref_listing_exchange "
        query += f"where c.fref_security_type = 'SHARE' and a.factset_entity_id in "
        suffix = 'ORDER BY a.factset_entity_id'
        conn = get_connection(database='FactSetDataFeed')
        try:
            data = execute_batch(conn, query, missing, sql_suffix=suffix)
            if data is not None:
                if isinstance(data, pd.DataFrame) and not data.empty:
                    data['start_date'] = util.parse_date(19000101)
                    data['end_date'] = util.parse_date(99991231)
                    et = get_primary_equity_by_entities(np.unique(data['entity_id']), sec_type='SHARE')
                    for i in data.index:
                        e = data.loc[i, 'entity_id']
                        s = data.loc[i, 'sec_id']
                        ix = np.where(np.logical_and(et['factset_entity_id'] == e, et['sec_id'] == s))[0]
                        if len(ix) == 0:
                            continue
                        data.loc[i, 'start_date'] = et.loc[et.index[ix[0]], 'start_date']
                        data.loc[i, 'end_date'] = et.loc[et.index[ix[0]], 'end_date']
                    primary_share_classes = pd.concat((primary_share_classes, data), axis=0, ignore_index=True)
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get primary equity shares for {len(missing)} entities: database error")
            raise dbe
        except ValueError as ve:
            display(f"{ve}")
            display(f"Unable to get primary equity shares for {len(missing)} entities: value error")
            raise ve
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to get primary equity shares for {len(missing)} entities: other error")
            raise ee
    if primary_share_classes is None:
        return result
    if primary_share_classes.empty:
        return result
    ix = np.where(np.isin(primary_share_classes['entity_id'].to_numpy(), entities))[0]
    if start_date is not None:
        sd = util.parse_date(start_date)
        iz = np.where(~(primary_share_classes['end_date'] <= sd))[0]
        ix = np.intersect1d(ix, iz)
    if end_date is not None:
        sd = util.parse_date(end_date)
        iz = np.where(~(primary_share_classes['start_date'] > sd))[0]
        ix = np.intersect1d(ix, iz)
    return primary_share_classes.iloc[ix]


def get_merged_entities(start_date, end_date, from_entity_ids=None, to_entity_ids=None):
    """
    get merged entities history
    Parameters
    ----------
    start_date:
    end_date:
    from_entity_ids: default None
    to_entity_ids: default None

    Returns
    -------

    """
    global merged_entities
    days = util.load_business_days('GL', start_date, end_date)
    if len(days) == 0:
        display(f"No valid business days found: returning None")
        return None
    if merged_entities is not None:
        missing = np.setdiff1d(days, merged_entities['merge_date'])
    else:
        missing = days
    if len(missing) > 0:
        sql = f"select * from sym_v1.sym_merged_entity_id where merge_date >= " \
              f"'{missing[0].strftime(util.YY_MM_DD_format)}' and merge_date <= " \
              f"'{missing[-1].strftime(util.YY_MM_DD_format)}'"
        try:
            conn = get_connection(database='FactSetDataFeed')
            cursor = get_cursor(conn)
            cursor.execute(sql)
            records = cursor.fetchall()
            data = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            data.drop_duplicates(inplace=True, ignore_index=True)
            cursor.close()
            conn.close()
            if data is not None:
                display(f"Appended merging entities between {missing[0]} and {missing[-1]} ({len(missing)} days),"
                        f"{len(data.index)} rows")
            else:
                display(f"No merging entities found between {missing[0]} and {missing[-1]} ({len(missing)} days)")
            if merged_entities is None:
                merged_entities = data
            else:
                ix = np.where(np.isin(merged_entities['merge_date'], data['merge_date']))[0]
                merged_entities.drop(merged_entities.index[ix], axis=0)
                merged_entities = pd.concat((merged_entities, data), axis=0, ignore_index=True)
                merged_entities.drop_duplicates(keep='last', inplace=True)
        except ValueError as ve:
            display(f"{ve}")
            display(f"Unable to get entity structure history due to value error")
            cursor.close()
            conn.close()
            raise ve
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to get entity structure history due to exception")
            cursor.close()
            conn.close()
            raise ee

    if merged_entities is None:
        return None
    if merged_entities.empty:
        return None
    ix = np.where(np.logical_and(merged_entities['merge_date'] >= days[0],
                                 merged_entities['merge_date'] <= days[-1]))[0]
    if from_entity_ids is not None:
        if isinstance(from_entity_ids, str):
            from_entity_ids = np.array([from_entity_ids])
        if isinstance(from_entity_ids, list):
            from_entity_ids = np.array(from_entity_ids)
        from_entity_ids = np.unique(from_entity_ids)

        if len(from_entity_ids) > 0:
            good = ix = np.where(np.isin(merged_entities['merged_factset_entity_id'], from_entity_ids))[0]
            ix = np.intersect1d(ix, good)
    if to_entity_ids is not None:
        if isinstance(to_entity_ids, str):
            to_entity_ids = np.array([to_entity_ids])
        if isinstance(to_entity_ids, list):
            to_entity_ids = np.array(to_entity_ids)
        to_entity_ids = np.unique(to_entity_ids)

        if len(to_entity_ids) > 0:
            good = ix = np.where(np.isin(merged_entities['to_factset_entity_id'], to_entity_ids))[0]
            ix = np.intersect1d(ix, good)
    return merged_entities.iloc[ix]


def get_merged_security_ids(start_date, end_date, from_sec_ids=None, to_sec_ids=None):
    """
    get merged security IDs history
    Parameters
    ----------
    start_date:
    end_date:
    from_sec_ids: default None
    to_sec_ids: default None

    Returns
    -------

    """
    global merged_securities
    days = util.load_business_days('GL', start_date, end_date)
    if len(days) == 0:
        display(f"No valid business days found: returning None")
        return None
    if merged_securities is not None:
        missing = np.setdiff1d(days, merged_securities['merge_date'])
    else:
        missing = days
    if len(missing) > 0:
        sql = f"select * from sym_v1.sym_merged_fsym_id where merge_date >= " \
              f"'{missing[0].strftime(util.YY_MM_DD_format)}' and merge_date <= " \
              f"'{missing[-1].strftime(util.YY_MM_DD_format)}'"
        try:
            conn = get_connection(database='FactSetDataFeed')
            cursor = get_cursor(conn)
            cursor.execute(sql)
            records = cursor.fetchall()
            data = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            data.drop_duplicates(inplace=True, ignore_index=True)
            cursor.close()
            conn.close()
            if data is not None:
                display(f"Appended merging securites between {missing[0]} and {missing[-1]} ({len(missing)} days),"
                        f"{len(data.index)} rows")
            else:
                display(f"No merging securites found between {missing[0]} and {missing[-1]} ({len(missing)} days)")
            if merged_securities is None:
                merged_securities = data
            else:
                ix = np.where(np.isin(merged_securities['merge_date'], data['merge_date']))[0]
                merged_securities.drop(merged_securities.index[ix], axis=0)
                merged_securities = pd.concat((merged_securities, data), axis=0, ignore_index=True)
                merged_securities.drop_duplicates(keep='last', inplace=True)
        except ValueError as ve:
            display(f"{ve}")
            display(f"Unable to get merged securities history due to value error")
            cursor.close()
            conn.close()
            raise ve
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to get entity structure history due to exception")
            cursor.close()
            conn.close()
            raise ee

    if merged_securities is None:
        return None
    if merged_securities.empty:
        return None
    ix = np.where(np.logical_and(merged_securities['merge_date'] >= days[0],
                                 merged_securities['merge_date'] <= days[-1]))[0]
    if from_sec_ids is not None:
        if isinstance(from_sec_ids, str):
            from_sec_ids = np.array([from_sec_ids])
        if isinstance(from_sec_ids, list):
            from_sec_ids = np.array(from_sec_ids)
        from_sec_ids = np.unique(from_sec_ids)

        if len(from_sec_ids) > 0:
            good = ix = np.where(np.isin(merged_securities['merged_fsym_id'], from_sec_ids))[0]
            ix = np.intersect1d(ix, good)
    if to_sec_ids is not None:
        if isinstance(to_sec_ids, str):
            to_sec_ids = np.array([to_sec_ids])
        if isinstance(to_sec_ids, list):
            to_entity_ids = np.array(to_sec_ids)
        to_sec_ids = np.unique(to_sec_ids)

        if len(to_sec_ids) > 0:
            good = ix = np.where(np.isin(merged_securities['to_fsym_id'], to_sec_ids))[0]
            ix = np.intersect1d(ix, good)
    return merged_securities.iloc[ix]


@ft.lru_cache()
def get_exchange_map(database='FactSetDataFeed', sandbox='PROD'):
    """
    get all the security exchanges around the world
    Parameters
    ----------
    database
    sandbox

    Returns
    -------

    """
    sql = f"select * from ref_v2.fref_sec_exchange_map"
    try:
        conn = get_connection(database=database, sandbox=sandbox)
        cursor = get_cursor(conn)
        cursor.execute(sql)
        records = cursor.fetchall()
        data = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        return data
    except ValueError as ve:
        display(f"{ve}")
        display(f"Unable to load exchange map due to value error")
        raise ve
    except db.DatabaseError as dve:
        display(f"{dve}")
        display(f"Unable to load exchange map due to database error")
        raise dve
    except Exception as eve:
        display(f"{eve}")
        display(f"Unable to load exchange map due to exception")
        raise eve


def get_country_main_stock_exchanges(countries=None):
    global exchanges
    if exchanges is None:
        file = os.path.join(util.default_output_location('market'), 'reference', 'main_country_exchange_map.xlsx')
        exchanges = pd.read_excel(file)
    if countries is None:
        return exchanges
    if isinstance(countries, str):
        countries = np.array([countries])
    elif isinstance(countries, list):
        countries = np.array(countries)
    countries = np.char.upper(countries)
    countries = np.char.strip(countries)
    ix = np.where(np.isin(exchanges['iso_country'].to_numpy(), countries))[0]
    return exchanges.iloc[ix]


@ft.lru_cache()
def get_regime_history():
    file = os.path.join(util.default_output_location('macro'), 'all_regimes.qd')
    return util.load_data(file)


# economic indicators

def get_econ_reference(ids=None, series=None, concepts=None, currencies=None, frequencies=None, countries=None,
                       sandbox='PROD'):
    global econ_series
    if econ_series is None:
        sql = f"select * from econ.EconStandardizedAttributes"
        try:
            conn = get_connection(sandbox=sandbox)
            cursor = get_cursor(conn)
            cursor.execute(sql)
            records = cursor.fetchall()
            econ_series = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get econ series attributes due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to get econ series attributes due to exception")
            raise ee
    if econ_series is None or not isinstance(econ_series, pd.DataFrame):
        display(f"No valid economic reference")
        return None
    if econ_series.empty:
        display(f"Empty economic reference")
        return econ_series
    ix = np.array(range(len(econ_series.index)))
    if ids is not None:
        if isinstance(ids, numbers.Number):
            ids = np.array([ids])
        if isinstance(ids, list):
            ids = np.array(ids)
        iz = np.where(np.isin(econ_series['ID'].to_numpy(), ids))[0]
        ix = np.intersect1d(ix, iz)
    if series is not None:
        if isinstance(series, str):
            series = np.array([series])
        if isinstance(series, list):
            series = np.array(series)
        series = np.char.strip(np.char.upper(series))
        iz = np.where(np.isin(econ_series['series_id'].to_numpy(), series))[0]
        ix = np.intersect1d(ix, iz)
    if concepts is not None:
        if isinstance(concepts, str):
            concepts = np.array([concepts])
        if isinstance(concepts, list):
            concepts = np.array(concepts)
        concepts = np.char.strip(np.char.upper(concepts))
        iz = np.where(np.isin(econ_series['concept_code'].to_numpy(), concepts))[0]
        ix = np.intersect1d(ix, iz)
    if currencies is not None:
        if isinstance(currencies, str):
            currencies = np.array([currencies])
        if isinstance(currencies, list):
            currencies = np.array(currencies)
        currencies = np.char.strip(np.char.upper(currencies))
        iz = np.where(np.isin(econ_series['currency'].to_numpy(), currencies))[0]
        ix = np.intersect1d(ix, iz)
    if countries is not None:
        if isinstance(countries, str):
            countries = np.array([countries])
        if isinstance(countries, list):
            countries = np.array(countries)
        countries = np.char.strip(np.char.upper(countries))
        iz = np.where(np.isin(econ_series['iso_country'].to_numpy(), countries))[0]
        ix = np.intersect1d(ix, iz)
    if frequencies is not None:
        if isinstance(frequencies, str):
            frequencies = np.array([frequencies])
        if isinstance(frequencies, list):
            frequencies = np.array(frequencies)
        frequencies = np.char.strip(np.char.upper(frequencies))
        iz = np.where(np.isin(econ_series['frequency_code'].to_numpy(), np.char.upper(frequencies)))[0]
        ix = np.intersect1d(ix, iz)
    return econ_series.iloc[ix]


@ft.lru_cache()
def get_econ_concepts():
    ref = get_econ_reference()
    return np.unique(ref['concept_code'])


@ft.lru_cache()
def get_econ_countries():
    ref = get_econ_reference()
    ix = np.where(pd.notnull(ref['iso_country']))[0]
    return np.unique(ref['iso_country'].iloc[ix], equal_nan=True)


@ft.lru_cache()
def get_econ_country_desc():
    ref = get_econ_reference()
    ix = np.where(pd.notnull(ref['country_desc']))[0]
    return np.unique(ref['country_desc'].iloc[ix], equal_nan=True)


@ft.lru_cache()
def get_econ_currencies():
    ref = get_econ_reference()
    ix = np.where(pd.notnull(ref['currency']))[0]
    return np.unique(ref['currency'].iloc[ix], equal_nan=True)


@ft.lru_cache()
def get_econ_frequencies():
    ref = get_econ_reference()
    ix = np.where(pd.notnull(ref['frequency_code']))[0]
    return np.unique(ref['frequency_code'].iloc[ix], equal_nan=True)


@ft.lru_cache()
def get_econ_frequency_descriptions():
    ref = get_econ_reference()
    ix = np.where(pd.notnull(ref['frequency_desc']))[0]
    return np.unique(ref['frequency_desc'].iloc[ix], equal_nan=True)


def get_econ_series(start_date, end_date, series_id, sandbox='DEV'):
    sd = util.parse_date(start_date)
    ed = util.parse_date(end_date)
    if not isinstance(series_id, str):
        raise ValueError(f"{series_id} needs be string")
    series_id = series_id.strip().upper()
    sql = f"select * from econ.EconStandardized where series_date between '{sd.strftime(util.YY_MM_DD_format)}'" \
          f"and '{ed.strftime(util.YY_MM_DD_format)}' and series_id = '{series_id}'"
    try:
        conn = get_connection(sandbox=sandbox)
        cursor = get_cursor(conn)
        cursor.execute(sql)
        records = cursor.fetchall()
        df = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        df.loc[df.index, 'series_date'] = util.parse_date(df['series_date'])
        return df
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to get econ series due to database error")
        raise dbe
    except Exception as ee:
        display(f"{ee}")
        display(f"Unable to get econ series due to exception")
        raise ee


# -----------------------------------------------------------
#
#  RBICS classifications
#
# -----------------------------------------------------------

def get_rbics_structure(bus_day=None, levels=None, clean=True, database='FactSetDataFeed'):
    """

    Parameters
    ----------
    bus_day: default None, such as 20230714
    levels: default None, value 1 through 6
    clean: default True, if True, remove rows with Non-Corporate and Other
    database: default 'FactSetDataFeed'

    Returns
    -------

    Example:
        get_rbics_structure(20230714, 3)    # provide classification structure that includes sector/industry group
                                            # /industry, as of 20230714

    Author:  Yun Chen
    Indigo Dao, LLC
    Date: July 14, 2023
    """
    global rbics
    if rbics is None:
        sql = 'select * from rbics_v1.rbics_structure'
        conn = get_connection(database=database)
        cursor = get_cursor(conn)
        try:
            cursor.execute(sql)
            records = cursor.fetchall()
            df = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            df['start_date'] = util.parse_date(df['start_date'].to_numpy())
            df['end_date'] = util.parse_date(df['end_date'].to_numpy())
            ix = np.where(pd.isnull(df['end_date']))[0]
            df.loc[df.index[ix], 'end_date'] = util.parse_date(99991231)
            rbics = df.copy(deep=True)
        except ValueError as ve:
            display(f"{ve}")
            display(f"Unable to get RBICS classification structure: value error")
            raise ve
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get RBICS classification structure: database error")
            raise dbe
    else:
        df = rbics.copy(deep=True)
    if clean:
        ix = np.where(~np.isin(df['l1_name'].to_numpy(), ['Non-Corporate', 'Other']))[0]
        df = df.iloc[ix]
    if levels is not None:
        if isinstance(levels, str):
            levels = int(levels[1])
        if not isinstance(levels, numbers.Number):
            raise ValueError(f"RBICS structure: levels need be string such as l4_name or 4 (integer)")
        levels = int(levels)
        if 0 < levels < 6:
            columns = np.array(['start_date', 'end_date'])
            col = np.array([])
            for i in range(1, levels+1):
                col = np.append(col, f"l{i}_id")
                col = np.append(col, f"l{i}_name")
            columns = np.append(col, columns)
            df = df[columns]
            df.sort_values(by=list(columns), axis=0, ascending=True, inplace=True, ignore_index=True)
            df1 = df.drop_duplicates(subset=col, keep='first')
            df2 = df.drop_duplicates(subset=col, keep='last')
            df = df2.copy()
            df.loc[df.index, 'start_date'] = df1.loc[df1.index, 'start_date'].to_numpy()
    if bus_day is not None:
        d = util.parse_date(bus_day)
        if d is not None:
            ix = np.where(np.logical_and(df['start_date'] <= d, df['end_date'] > d))
            df = df.iloc[ix]

    return df


@ft.lru_cache()
def get_rbics_hierarchy():
    names = np.array([])
    for i in range(1, 7):
        names = np.append(names, f"l{i}_name")
    return pd.DataFrame(names, columns=['value'])


@ft.lru_cache()
def get_rbics_entity_classification(database='FactSetDataFeed'):
    sql = 'select * from rbics_v1.rbics_entity_focus'
    conn = get_connection(database=database)
    cursor = get_cursor(conn)
    try:
        cursor.execute(sql)
        records = cursor.fetchall()
        df = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        df['start_date'] = util.parse_date(df['start_date'].to_numpy())
        df['end_date'] = util.parse_date(df['end_date'].to_numpy())
        ix = np.where(pd.isnull(df['end_date']))[0]
        df.loc[df.index[ix], 'end_date'] = util.parse_date(99991231)
        display(f"Loaded {len(df.index):,} rows: {len(np.unique(df['factset_entity_id'])):,} "
                f"entities RBICS classification")
        return df
    except ValueError as ve:
        display(f"{ve}")
        display(f"Unable to get RBICS classification entity classification: value error")
        raise ve
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to get RBICS classification entity classification: database error")
        raise dbe


def get_rbics_classification(sec_ids, level=1, as_of=None, vector_flag=False, clean=True, ec=None):
    """

    Parameters
    ----------
    sec_ids: regional IDs
    level: default 1 (top level), the lowest level is 6, or 'l1_name' as default, available through 'l6_name'
    as_of: default one month prior to present day
    vector_flag: default False, if True, returns N x 1 matrix, otherwise N x K
    clean: default True, if True, exclude 'Other', 'Non-Corporate' from output
    ec: default None, if supplied, it bypasses loading entire mapping

    Returns
    -------

    Example:
        get_rbics_classification('JLJ0VZ-R', vector_flag=False, level=1)   # this returns a N x K matrix for level 1

                      Business Services  Consumer Services  ...  Telecommunications  Utilities
    JLJ0VZ-R                  0                  0  ...                   0          0

    """
    # if as_of is None:
    #     as_of = util.previous_business_days(util.today(), offset=20)
    bus_day = util.parse_date(as_of)
    if bus_day is not None:
        ref = get_references(sec_ids, dates=bus_day)
    else:
        ref = get_references(sec_ids, keep_latest=True)
    if ref is None or (isinstance(ref, pd.DataFrame) and ref.empty):
        display(f"No security reference found for securities;")
        return None
    ref = get_rbics_references(ref['sec_id'].to_numpy(), bus_day=bus_day, keep_latest=True)
    if ec is None:
        ec = get_rbics_entity_classification()
    iy = np.where(np.isin(ec['factset_entity_id'], ref['entity_id'].to_numpy()))[0]
    if bus_day is not None:
        ix = np.where(np.logical_and(ec['start_date'] <= bus_day, ec['end_date'] > bus_day))[0]
        iz = np.intersect1d(ix, iy)
    else:
        iz = iy
    cc = ec.iloc[iz].copy()
    cc.drop(columns=['start_date', 'end_date'], inplace=True)
    df = ref.merge(cc, how='left', left_on='entity_id', right_on='factset_entity_id')
    mm = get_rbics_structure()
    if bus_day is not None:
        ix = np.where(np.logical_and(mm['start_date'] <= bus_day, mm['end_date'] > bus_day))[0]
    else:
        if not vector_flag:
            sd = util.previous_business_days(util.today(), offset=20)
            ix = np.where(np.logical_and(mm['start_date'] <= sd, mm['end_date'] > sd))[0]
        else:
            ix = np.array(range(len(mm.index)))
    mm = mm.iloc[ix].copy()
    mm.drop(columns=['start_date', 'end_date'], inplace=True)
    if clean:
        excluded_names = ['Other', 'Non-Corporate']
        ix = np.where(~np.isin(mm['l1_name'].to_numpy(), excluded_names))[0]
        mm = mm.iloc[ix].copy()
    df = df.merge(mm, how='left', left_on='l6_id', right_on='l6_id')
    if level is None:
        lvl = 'l1_name'
    elif isinstance(level, numbers.Number):
        lvl = f"l{int(level)}_name"
    elif isinstance(level, str):
        lvl = level.lower().strip()
    else:
        raise ValueError(f"RBICS classification default level needs be integer or lXX_name string")
    if lvl not in mm.columns:
        display(f"RBICS has no {lvl} in its hierarchy")
        raise ValueError(f"RBICS has no {lvl} in its hierarchy")
    if not vector_flag:
        names = pd.unique(mm[lvl])
        zf = pd.DataFrame(0, index=df['sec_id'].to_numpy(), columns=names)
        df['values'] = 1
        kf = df.pivot_table(values='values', index='sec_id', columns=lvl, fill_value=0)
        zf.update(kf)
        return zf
    else:
        df = df[['sec_id', lvl]]
        df.rename(columns={lvl: 'values'}, inplace=True)
        df.drop_duplicates(subset=['sec_id'], keep='last', inplace=True)
        df.set_index('sec_id', inplace=True)
        df.index.name = None
        return df


def get_rbics_references(sec_ids, bus_day=None, database='FactSetDataFeed', keep_latest=False):
    # if bus_day is None:
    #     bus_day = util.previous_business_days(util.today(), offset=20)
    if sec_ids is None or len(sec_ids) == 0:
        display(f"No valid securities as input")
        return None
    bus_day = util.parse_date(bus_day)
    if bus_day is not None:
        ref = get_references(sec_ids, dates=bus_day, keep_latest=keep_latest)
    else:
        ref = get_references(sec_ids, keep_latest=keep_latest)
    conn = get_connection(database=database)
    try:
        sql_base = f"select fsym_id as security_id, start_date, end_date, factset_entity_id as rb_entity_id " \
                   f"from rbics_v1.rb_sec_entity_hist where "
        if bus_day is not None:
            dstr = bus_day.strftime(util.yyyy_mm_dd_format)
            sql_base += f"start_date <= '{dstr}' and end_date > '{dstr}' and fsym_id in "
        else:
            sql_base += f"fsym_id in "

        df = execute_batch(conn, sql_base, ref['security_id'].to_numpy())
        if keep_latest:
            df.sort_values(by=['security_id', 'rb_entity_id', 'end_date'], axis=0, inplace=True)
            df.drop_duplicates(subset=['security_id'], keep='last', inplace=True)
        df.drop(columns=['start_date', 'end_date'], inplace=True)
        ref = ref.merge(df, how='left', left_on='security_id', right_on='security_id')
        ix = np.where(pd.notnull(ref['rb_entity_id']))[0]
        if len(ix) > 0:
            ref.loc[ref.index[ix], 'entity_id'] = ref.loc[ref.index[ix], 'rb_entity_id']
        ref.drop(columns=['rb_entity_id'], inplace=True)
        return ref
    except db.DatabaseError as dbe:
        display(dbe)
        display(f"Unable to get RBICS references due to value error")
        raise dbe
    except Exception as ee:
        display(ee)
        display(f"Unable to get RBICS references due to exception")
        raise ee


def get_composites(sec_ids=None):
    """
    return mapping for stocks within sec_ids that are both composites and for which we have underlying holdings
    Parameters
    ----------
    sec_ids

    Returns
    -------

    """
    c_map = get_composite_mapping()
    if sec_ids is None:
        return c_map
    sec_ids = np.unique(util.to_numpy(sec_ids))
    ix = np.where(np.isin(c_map['sec_id'], sec_ids))[0]
    return c_map.iloc[ix]


@ft.lru_cache()
def get_composite_mapping(exclude_nan=True):
    file = os.path.join(util.default_output_location('market'), 'reference', 'composite_mapping.json')
    df = pd.read_json(file)
    if exclude_nan:
        ix = np.where(pd.notnull(df['sec_id']))[0]
        return df.iloc[ix]
    else:
        return df


def add_composite(ticker, portfolio_id, multiplier=1, active=True):
    ref = get_sec_ids(ticker, active_only=active)
    if ref.empty:
        display(f"Unable to find information on {ticker}")
        return False
    df = ref[['sec_id', 'name', 'ticker_region']]
    df.loc[:, ['Multiplier']] = multiplier
    df.loc[:, ['PortfolioID']] = int(portfolio_id)
    df = df.rename(columns={'name': 'Description', 'ticker_region': 'Tickers'})
    cf = get_composite_mapping(False)
    cf = pd.concat((cf, df), ignore_index=True)
    cf.drop_duplicates(subset=['PortfolioID', 'sec_id', 'Tickers'], keep='first', inplace=True, ignore_index=True)
    zf = cf.copy()
    zf['PortfolioID'] = zf['PortfolioID'].astype('int64')
    if not zf.empty:
        file = os.path.join(util.default_output_location('market'), 'reference', 'composite_mapping.json')
        zf.to_json(file)
        display(f"Updated composite mapping: {pd.notnull(zf['sec_id']).sum()} valid composites saved to :\n{file}")
    return zf

# ----------------------------------------------------------------------
#
#  I/B/E/S estimates
#
# ----------------------------------------------------------------------


def get_long_term_estimates(bus_day=None, sec_ids=None, item='EPS_LTG', universe=None, calendar_str='US',
                            database='FactSetDataFeed'):
    """
    get long term estimates for a regional ID
    :param bus_day: default today
    :param sec_ids:
    :param item: string, default EPS_LTG
    :param universe: default None
    :param calendar_str: default 'US'
    :param database: FactSetDataFeed
    :return:

    Example:
        Input:
            get_currencies('HTM0LK-R')
        Output:
                     currency                   name
            HTM0LK-R      USD  Alphabet Inc. Class A

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: July 1, 2022
    """
    if bus_day is None:
        bus_day = util.most_recent_business_day(calendar_str=calendar_str)
    bus_day = util.parse_date(bus_day)
    sec_ids = util.to_numpy(sec_ids)
    if universe is not None:
        univ = get_positions(bus_day, bus_day, universe, calendar_str=calendar_str)
        sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
    item = item.upper().strip()

    query = f"select fsym_id as sec_ids, estimate_value, factset_broker_id as broker_id, " \
            f"estimate_date as date, cons_start_date as trans_from_date, cons_end_date as trans_to_date " \
            f"from FactSetDataFeed.fe_v4.fe_basic_det_lt where estimate_value is NOT NULL and " \
            f"cons_start_date <= '{bus_day.strftime(util.yyyy_mm_dd_format)}' " \
            f"AND cons_end_date >= '{bus_day.strftime(util.yyyy_mm_dd_format)}' and fe_item = '{item}' and " \
            f"fsym_id in "
    # connect to db
    conn = get_connection(database=database)
    try:
        ac = util.clock()
        data = execute_batch(conn, query, sec_ids)
        rc = util.clock()
        conn.close()
        data.rename(columns={'estimate_value': 'values'}, inplace=True)
        data['date'] = util.parse_date(data['date'].to_numpy())
        data['trans_from_date'] = util.parse_date(data['trans_from_date'].to_numpy())
        data['trans_to_date'] = util.parse_date(data['trans_to_date'].to_numpy())
        return data
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to  from database")
        conn.close()
        raise IOError(f'database error: ')
    except Exception as ee:
        display(f"{ee}")
        conn.close()
        raise IOError(f'database exception: ')


