#
#  Utilities
#     -- calendar / date logic
#     -- time logic
#     -- CPU / Memory
#     -- save / retrieve data
#     -- stock dividend/corporate actions
#     -- return compounding
#
#  Author : Yun Chen
#  Indigo Dao LLC, copyright
#  July 5, 2022
#
# --------------------------------------------------------
import datetime
import os
import pathlib
import functools as ft
import time

import dateutil.parser
import numpy as np
import pandas as pd
import datetime as dt
from dateutil import parser
from dateutil.rrule import *
from dateutil.relativedelta import relativedelta
import numbers
import warnings
import errno
from collections.abc import Iterable
import dill as pickle
from shutil import copyfile
import psutil
import operator
from inspect import stack

import util.utilities
from util.intersect import *

DATA_TYPES = ('objects', 'descriptors', 'exposures', 'regressions', 'risks', 'alphas',
              'portfolios', 'market', 'classifications', 'reports', 'util', 'macro', 'fx')
yyyymmdd_format = '%Y%m%d'
yyyy_mm_dd_format = '%Y-%m-%d'
MM_DD_YY_format = '%m-%d-%Y'
YMDHMS_format = '%Y-%m-%d: %H:%M:%S'
YY_MM_DD_format = '%Y-%m-%d'
YMDHMS_INT_FORMAT = '%Y%m%d%H%M%S'
PRICE_TYPES = ('CLOSE', 'OPEN', 'HIGH', 'LOW')
FREQUENCIES = ['DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY',
               'ANNUALLY', 'MONTHEND', 'QUARTEREND',
               'YEAREND', 'MONDAY', 'TUESDAY', 'WEDNESDAY',
               'THURSDAY', 'FRIDAY', 'SEMIANNUAL']
PERIODS = [1, 5, 21, 63, 252, 21, 63, 252, 5, 5, 5, 5, 5, 126]
WEIGHTING_SCHEMES = ['NAV', 'NAV_EQUITY_ONLY', 'LONG_ONLY', 'SHORT_ONLY',
                     'LONG_SHORT', 'EQUAL', 'MARKETCAP', 'OPPORTUNITY_WEIGHT', 'LONG_SHORT_EQUITY_ONLY',
                     'NAV_CASH_EQUITY_ONLY', 'CASH', 'LONG_SHORT_EQUITY_ONLY_EX_CASH',
                     'NAV_EQUITY_ONLY_EX_CASH', 'LONG_ONLY_EX_CASH', 'NAV_EX_CASH']
WEIGHT_FACTORS = ['OPPORTUNITY_WEIGHT', 'SIZE', 'ResidualRisk', 'InverseResidualRisk',
                  'MARKETCAP_MONTHEND', 'OPPORTUNITY_WEIGHT_MONTHEND', 'LOGARITHMIC_WEIGHT',
                  'LOGARITHMIC_WEIGHT_MONTHEND', 'ASSETS_CACHE', 'LOG_WEIGHT']
FUNDAMENTAL_DATA_FREQUENCIES = ['ARQ', 'ARY', 'ART', 'MRQ', 'MRY', 'MRT']
log_file = None
# --------------------------------------------
#
# files, locations
#
# --------------------------------------------


def default_output_location(data_type=None, env=None):
    """
    get default output location; can be updated with
    :param data_type: string
    :param env: string, default None for production
    :return:
        string
    Example:
        Input:
            default_output_location('reports')
        Output:
            C:\\Users\\<my_id>\\data\\cosmos\\dev\\reports'

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    directory = root_directory(env)
    if not exists(directory):
        path_dir = pathlib.Path(directory)
        path_dir.mkdir(parents=True)
        print(f"Successfully created:\n{path_dir}")
    if data_type is not None and isinstance(data_type, str):
        d_type = data_type.strip().lower()
        if d_type in DATA_TYPES:
            directory = os.path.join(directory, DATA_TYPES[DATA_TYPES.index(d_type)])
            if not exists(directory):
                p_dir = pathlib.Path(directory)
                p_dir.mkdir(parents=True)
                print(f"Successfully created:\n{p_dir}")
        else:
            print(f"Requested type: {d_type} is not part of cosmos data types")
            directory = os.path.join(directory, d_type)
            if not exists(directory):
                p_dir = pathlib.Path(directory)
                p_dir.mkdir(parents=True)
                print(f"Successfully created\n{p_dir}")
    return directory


def root_directory(env=None):
    """
    base directory for all outputs/inputs
    :param env: Default None ('PROD')
    :return:
        path string
    Example:
        Input:
            root_directory()
        Output:
            C:\\Users\\<my_id>\\data\\cosmos\\dev

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date : August 29, 2022
    """
    if env is None or not isinstance(env, str):
        env = 'PROD'
    if env.upper().strip() == 'PROD':
        directory = os.path.join('C:\\RiskModel\\')
        return directory
    s = os.getenv(env)
    home = os.getenv('HOME')
    if not home:
        home = os.getenv('USERPROFILE')
    if s and isinstance(s, str) and s.strip().upper() == 'TRUE':
        directory = os.path.join(home, 'data', 'cosmos', 'prod')
    else:
        directory = os.path.join(home, 'data', 'cosmos', 'dev')
    return directory


def exists(file):
    """
    check if a file is in existence
    :param file: full path or relative path (relative to root_directory)
    :return:
        Input:
            exists('C:\\Users\\<my_id>\\data\\cosmos\\dev\\reports\\risk\\unrecognized.qd')
        Output:
            True
        Input:
            exists('reports\\risk\\unrecognized.qd')
        Output:
            True

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if os.path.exists(file):
        return True
    else:
        path = root_directory()
        if path not in file:
            f = os.path.join(path, file)
            return os.path.exists(f)
        else:
            return False


def is_file(file):
    """
    check if a file is a file in existence
    :param file: full path or relative path (relative to root_directory)
    :return:
        Input:
            is_file('C:\\Users\\<my_id>\\data\\cosmos\\dev\\reports\\risk\\unrecognized.qd')
        Output:
            True
        Input:
            is_file('reports\\risk\\unrecognized.qd')
        Output:
            True

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if os.path.isfile(file):
        return True
    path = root_directory()
    if path not in file:
        f = os.path.join(path, file)
        return os.path.isfile(f)
    else:
        return False


def isfile(file):
    """
    check if a file is a file in existence
    :param file: full path or relative path (relative to root_directory)
    :return:
        Input:
            is_file('C:\\Users\\<my_id>\\data\\cosmos\\dev\\reports\\risk\\unrecognized.qd')
        Output:
            True
        Input:
            is_file('reports\\risk\\unrecognized.qd')
        Output:
            True

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """

    return is_file(file)


def makedirs(location, mode=0o777, exist_ok=True):
    """
    create directory
    pre-pend default location to all relative paths
    :param location: full path or relative path (relative to default location)
    :param mode: default 0o777
    :param exist_ok: default True, to over-ride if set True
    :return: bool for success/failure

    Example:
        Input:
            makedirs(my_path)
        Output:
            True

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if location is None:
        return False
    path = root_directory()
    if path in location:
        os.makedirs(location, mode, exist_ok)
        return True
    else:
        os.makedirs(os.path.join(path, location), mode, exist_ok)
        return True


def caller(level=1):
    """
    return name of function from which caller() is embedded
    :param level: default 1
    :return: string
        Input:
            caller()
        Output:
            my_function()

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    return stack()[level].function


def preserve_file(file):
    """
    check if file exists, if it does, save it by a name with original name plus a timestring
    :param file: full path
    :return: bool for success/failure

    Example:
        Input:
            preserve_file(my_file_name)
        Output:
            True

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if not exists(file):
        return False
    f, e = os.path.splitext(file)
    current = dt.datetime.now()
    c_str = current.strftime('%Y%m%d%I%p%M%S')
    old_file = f"{f}.{c_str}.{e}"
    copyfile(file, old_file)
    print(f"copy existing file: {file} to\n{old_file}")
    return True


def get_files(path, extensions=None, strip_extension=False):
    """
    get file names from a location, optionally filter through extensions, optionally strip off extensions
    :param path:
    :param extensions: default None
    :param strip_extension: default False
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    files = []
    base_path = default_output_location()
    if base_path not in path and not os.path.exists(path):
        path = os.path.join(base_path, path)
    if not exists(path):
        print(f"Not found:\n{path}")
        return files
    if isinstance(extensions, str):
        extensions = [extensions]
    if not isinstance(strip_extension, bool):
        strip_extension = False

    fs = os.listdir(path)
    if extensions is not None or strip_extension:
        for f in fs:
            name, ext = os.path.splitext(f)
            if extensions is not None:
                if ext not in extensions:
                    continue
            if strip_extension:
                files.append(name)
            else:
                files.append(f)
    else:
        files = fs

    return files


def return_location():
    """
    return location to returns of internal composites
    :return: path
    """
    s = os.path.join(default_output_location('portfolios'), 'return')
    if not exists(s):
        makedirs(s)
        print(f"{current_time()}: {caller()}: created : {s}")
    return s


# --------------------------------------------
#
# time, clock, date, calendars
#
# --------------------------------------------


def clock():
    """
    get current clock time in serial number
    :return: float

    Example:
        Input:
            clock()
        Output:
            1661785581.6744351

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    return time.time()


def current_time(ts_format=None):
    """
    get current clock time in string, default 'yyyy-mm-d: hh:mm:ss' format
    :param ts_format: string, default 'yyyy-mm-d: hh:mm:ss'
    :return: string

    Example:
        Input:
            current_time()
        Output:
            '2022-08-29: 11:08:15'

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """

    t = dt.datetime.now()
    if ts_format is None:
        return t.strftime(YMDHMS_format)
    else:
        if isinstance(ts_format, str):
            return t.strftime(ts_format)
        else:
            return t.strftime(YMDHMS_format)


def parse_date(d):
    """
    convert integer or date string into internal numerical date
    :param d: date string or integer, or list of date string/integer
    :return: date object or numpy array of them

    Example:
        Input:
            parse_date([20220301, 20220829])
        Output:
            array([datetime.date(2022, 3, 1), datetime.date(2022, 8, 29)],
                  dtype=object)
        Input:
            parse_date(19991231)
        Output:
            datetime.date(1999, 12, 31)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if isinstance(d, list) or isinstance(d, set) or isinstance(d, np.ndarray):
        return np.asarray(list(map(parse_single_date, d)))
    elif isinstance(d, pd.Series) or isinstance(d, pd.DataFrame):
        return d.apply(parse_single_date)
    else:
        return parse_single_date(d)


def parse_single_date(d):
    """
    convert integer or date string into internal numerical date
    :param d: date string or integer
    :return: date object

    Example:
        Input:
            parse_single_date(19991231)
        Output:
            datetime.date(1999, 12, 31)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if d is None:
        return None
    if isinstance(d, dt.datetime):
        return d.date()
    try:
        if not (isinstance(d, str)):
            e = parser.parse(str(d)).date()
        else:
            e = parser.parse(d).date()
    except dateutil.parser.ParserError:
        e = None
    return e


def date2int_single_day(d):
    if d is None:
        return d
    dd = parse_single_date(d)
    if dd is None:
        return dd
    return int(dd.strftime('%Y%m%d'))


def date2int(d):
    """
    convert integer or date string or date object into internal numerical date
    :param d: date string or integer, or list of date string/integer
    :return: integer or numpy array of them

    Example:
        Input:
            date2int([20220301, 20220829])
        Output:
            array([20220301, 220829,
                  dtype=int)
        Input:
            date2int('19991231')
        Output:
            19991231

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: April 28, 2023
    """
    if isinstance(d, list) or isinstance(d, set) or isinstance(d, np.ndarray):
        return np.asarray(list(map(date2int_single_day, d)))
    elif isinstance(d, pd.Series) or isinstance(d, pd.DataFrame):
        return d.apply(date2int_single_day)
    else:
        return date2int_single_day(d)


def date_to_datetime(d, t=dt.datetime.min.time()):
    return dt.datetime.combine(d, t)


@ft.lru_cache()
def load_all_holidays():
    """
    load all holiday calendar dict, keyed by calendar codes such as GB, US
    :return:
        all_holidays, a dict

    Example:
        Input:
            load_all_holidays()
        Output:
            all_holidays

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    file = os.path.join(default_output_location('util'), 'ALL_HOLIDAYS.qd')
    all_holidays = load_data(file)
    return all_holidays


def load_business_days(calendar_code='GL', start_date=None, end_date=None, freq='DAILY'):
    """
    get numpy array of date objects for business days between start and end dates, according to a given frequency
    :param calendar_code: default 'GL'
    :param start_date: default None
    :param end_date: default None
    :param freq: default 'DAILY', or tuple/list to allow for compound frequency such as 7th day of a month
    :return: numpy array of objects

    Example:
        Input:
            load_business_days('US', 20030101, 20030105)  # daily days between 1/1/2003 and 1/05/2003
        Output:
            array([datetime.date(2003, 1, 2), datetime.date(2003, 1, 3)], dtype=object)

        Input:
            load_business_days('US', 20070101, 20070305, 'MONTHEND')  # month ends between 1/1/2007 and 3/05/2007
        Output:
            array([datetime.date(2007, 1, 31), datetime.date(2007, 2, 28)],
                  dtype=object)
        Input:
            load_business_days('US', 20220701, 20220715, 'FRIDAY')  # FRIDAY's between 7/1/2022 and 7/15/2022
        Output:
            array([datetime.date(2022, 7, 1), datetime.date(2022, 7, 8),
           datetime.date(2022, 7, 15)], dtype=object)

        Input:
            load_business_days('US', 20220701, 20220715, ('MONTHEND', 7))  # 7th business day between 7/1/2022 and 7/15/2022
        Output:
            array([datetime.date(2022, 7, 12)], dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    days = load_local_business_days(calendar_code)
    if freq is not None:
        if isinstance(freq, str):
            freq_str = freq.strip().upper()
            if freq_str in {'MONTHEND', 'MONTH END', 'MONTHLY', 'MONTH-END', 'MONTH_END'}:
                days = load_month_ends(calendar_code)
            elif freq_str in {'QUARTER END', 'QUARTEREND', 'QUARTERLY', 'QUARTER_END', 'QUARTER-END'}:
                days = load_month_ends(calendar_code)
                m = month(days)
                days = days[np.isin(m, [3, 6, 9, 12])]
            elif freq_str in {'SEMIANNUAL', 'SEMIANUALLY', 'SEMI-ANNUAL',
                              'HALFYEAR', 'HALF_YEAR', 'MIDYEAR', 'MID_YEAR', 'HALFYEARLY'}:
                days = load_month_ends(calendar_code)
                m = month(days)
                days = days[np.isin(m, [6, 12])]
            elif freq_str in {'ANNUAL', 'ANNUALLY', 'YEAR', 'YEAR_END', 'YEAREND', 'YEAR-END', 'YEARLY'}:
                days = load_month_ends(calendar_code)
                m = month(days)
                days = days[np.isin(m, [12])]
            elif freq_str in {'MON', 'MONDAY', 'MONDAYS'}:
                w = day_of_week(days)
                days = days[w == 0]
            elif freq_str in {'TUE', 'TUESDAY', 'TUESDAYS'}:
                w = day_of_week(days)
                days = days[w == 1]
            elif freq_str in {'WED', 'WEDS', 'WEDNESDAY', 'WEDNESDAYS'}:
                w = day_of_week(days)
                days = days[w == 2]
            elif freq_str in {'THU', 'THURSDAY', 'THURS', 'THURSDAYS'}:
                w = day_of_week(days)
                days = days[w == 3]
            elif freq_str in {'FRI', 'FRIDAY', 'FRIDAYS'}:
                w = day_of_week(days)
                days = days[w == 4]
            else:
                if freq_str != 'DAILY':
                    print(f"WARNING: frequency unrecognized: assuming {freq_str}")
        elif isinstance(freq, (tuple, list)):
            if len(freq) == 1:
                return load_business_days(calendar_code, start_date, end_date, freq[0])
            if len(freq) >= 3:
                first_or_last = freq[2].strip().upper()
            else:
                first_or_last = 'FIRST'
            ordinal = freq[1]
            freq_str = freq[0].strip().upper()
            if freq_str != 'DAILY':
                if first_or_last == 'FIRST':
                    return get_ordinal_business_day_of_period(ordinal, calendar_code, start_date, end_date, freq_str)
                else:
                    return get_ordinal_business_day_of_period(ordinal, calendar_code, start_date, end_date, freq_str,
                                                              True)
        else:
            raise Exception('Unsupported frequency type')
    days = np.array(days)
    if start_date and start_date is not None:
        days = days[days >= parse_date(start_date)]
    if end_date and end_date is not None:
        days = days[days <= parse_date(end_date)]
    days = np.sort(np.array(days))
    return days


def load_month_ends(calendar_code='GL', start_date=None, end_date=None):
    """
    load last business days of each month
    :param calendar_code:
    :param start_date:
    :param end_date:
    :return:

    Example:
        Input:
            load_month_ends('US', 20220701,20220831)
        Output:
            array([datetime.date(2022, 7, 29), datetime.date(2022, 8, 31)],
                  dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if calendar_code is None or not isinstance(calendar_code, str):
        calendar_code = 'GL'
    days = load_all_business_days()
    h_days = load_holidays(calendar_code)
    days = np.array(sorted(set(days) - set(h_days)))
    m = np.array(list(map(lambda x: x.month, days)))
    month_ends = days[np.where(np.diff(m) != 0)]
    if start_date is not None:
        month_ends = month_ends[month_ends >= parse_date(start_date)]
    if end_date is not None:
        month_ends = month_ends[month_ends <= parse_date(end_date)]
    return month_ends


def get_ordinal_business_day_of_period(n=1, calendar_code='GL', start_date=None, end_date=None,
                                       freq='MONTHEND', last=False):
    """
    get the n-th businee day within a month from first or last days of the month, between given date range
    :param n: default 1, No. N-th day of the month
    :param calendar_code: default 'GL'
    :param start_date: default None
    :param end_date: defualt None
    :param freq: default 'MONTHEND'
    :param last: default False, if True, will be counting from end
    :return: Numpy array of datetime.date objects

    Example:
        Input:
            util.get_ordinal_business_day_of_period(2,'US',20220701,20220731)
        Output:
            array([datetime.date(2022, 7, 5)], dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if calendar_code is None or not isinstance(calendar_code, str):
        calendar_code = 'GL'
    business_days = load_business_days(calendar_code, start_date, end_date)
    if len(business_days) == 0:
        result = np.empty(0,dtype=dt.date)
        return result
    if freq is None:
        freq = 'MONTHEND'
    period_ends = load_business_days(calendar_code, None, end_date, freq)
    if start_date is not None:
        ix = where_last(period_ends, parse_date(start_date))
        if ix is not None:
            period_ends = period_ends[ix:]
    if len(period_ends) == 0:
        result = np.empty(0,dtype=dt.date)
        return result
    expanded_business_days = load_business_days(calendar_code, period_ends[0], end_date)
    c,ia,ib=intersect(expanded_business_days, period_ends)
    if last:
        ia = ia - n + 1
        ia = ia[ia >= 0]
    else:
        ia = ia + n
        ia = ia[ia<expanded_business_days.shape]
    dates = expanded_business_days[ia]
    dates = intersect(dates, business_days)

    return dates[0]


def get_ordinal_day_of_month(n=1, start_date=None, end_date=None):
    """
    ordinal day of month, no calendar
    :param n: default 1, No. N-th day of the month
    :param start_date: default None
    :param end_date: default None
    :return: Numpy array of datetime.date objects

    Example:
        Input:
            util.get_ordinal_day_of_month(2,20220701,20220731)
        Output:
            array([datetime.date(2022, 7, 2)], dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """

    if not start_date or start_date is None:
        start_date = dt.date(1900, 1, 1)
    if not end_date or end_date is None:
        end_date = dt.date(2100, 1, 1)
    sdate = parse_date(start_date)
    edate = parse_date(end_date)
    years = range(sdate.year,edate.year+1)
    months = range(1, 13)
    dates = []
    for year in years:
        for month in months:
            dates.append(dt.date(year, month, n))
    dates=np.array(dates)
    dates=dates[(dates<=edate) & (dates>=sdate)]

    return dates


def day_segments(dates, calendar_str=None):
    """
    break a list of dates into chunks each of which is a continuous segment
    :param dates:
    :param calendar_str:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if isinstance(dates, dt.date):
        segments = pd.DataFrame(index=range(1), columns=['from', 'to'])
        segments.iloc[0, 0] = dates
        segments.iloc[0, 1] = dates
        return segments
    if calendar_str is None:
        calendar_str = 'GL'
    all_days = load_business_days(calendar_code=calendar_str)
    dates = np.sort(dates)
    c, i1, i2 = intersect(all_days, dates)
    segments = pd.DataFrame(columns=['from', 'to'])
    if len(c) == 0:
        return segments
    i3 = np.diff(i1)
    ix = np.where(i3 > 1)[0]
    segments = pd.DataFrame(index=range(len(ix)+1), columns=['from', 'to'])
    if len(ix) == 0:
        segments.iloc[0, 0] = dates[0]
        segments.iloc[0, 1] = dates[-1]
        return segments
    for i in range(len(ix) + 1):
        if i == 0:
            segments.iloc[i, 0] = dates[0]
        else:
            segments.iloc[i, 0] = dates[ix[i - 1]+1]
        if i == len(ix):
            segments.iloc[i, 1] = dates[-1]
        else:
            segments.iloc[i, 1] = dates[ix[i]]
    return segments


def load_business_days_by_year(yr, calendar_str='US', freq='DAILY'):
    """
    load all business days within a year by a calendar, and a frequency
    :param yr: integer
    :param calendar_str: default 'US'
    :param freq: default 'DAILY'
    :return: numpy array of date objects

    Example:
        Input:
            load_business_days_by_year(2022, 'US', 'WEDNESDAY')
        Output:
            array([datetime.date(2022, 1, 5), datetime.date(2022, 1, 12),
                   datetime.date(2022, 1, 19), datetime.date(2022, 1, 26),
                   datetime.date(2022, 2, 2), datetime.date(2022, 2, 9),
                   datetime.date(2022, 2, 16), datetime.date(2022, 2, 23),
                   datetime.date(2022, 3, 2), datetime.date(2022, 3, 9),
                   datetime.date(2022, 3, 16), datetime.date(2022, 3, 23),
                   datetime.date(2022, 3, 30), datetime.date(2022, 4, 6),
                   datetime.date(2022, 4, 13), datetime.date(2022, 4, 20),
                   datetime.date(2022, 4, 27), datetime.date(2022, 5, 4),
                   datetime.date(2022, 5, 11), datetime.date(2022, 5, 18),
                   datetime.date(2022, 5, 25), datetime.date(2022, 6, 1),
                   datetime.date(2022, 6, 8), datetime.date(2022, 6, 15),
                   datetime.date(2022, 6, 22), datetime.date(2022, 6, 29),
                   datetime.date(2022, 7, 6), datetime.date(2022, 7, 13),
                   datetime.date(2022, 7, 20), datetime.date(2022, 7, 27),
                   datetime.date(2022, 8, 3), datetime.date(2022, 8, 10),
                   datetime.date(2022, 8, 17), datetime.date(2022, 8, 24),
                   datetime.date(2022, 8, 31), datetime.date(2022, 9, 7),
                   datetime.date(2022, 9, 14), datetime.date(2022, 9, 21),
                   datetime.date(2022, 9, 28), datetime.date(2022, 10, 5),
                   datetime.date(2022, 10, 12), datetime.date(2022, 10, 19),
                   datetime.date(2022, 10, 26), datetime.date(2022, 11, 2),
                   datetime.date(2022, 11, 9), datetime.date(2022, 11, 16),
                   datetime.date(2022, 11, 23), datetime.date(2022, 11, 30),
                   datetime.date(2022, 12, 7), datetime.date(2022, 12, 14),
                   datetime.date(2022, 12, 21), datetime.date(2022, 12, 28)],
                  dtype=object)

    Author : Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if calendar_str is None:
        calendar_str = 'GL'
    if not isinstance(calendar_str, str):
        calendar_str = 'GL'
    s_date = dt.date(year=yr, month=1, day=1)
    e_date = dt.date(year=yr, month=12, day=31)
    return load_business_days(calendar_str, s_date, e_date, freq)


def get_period_start_end(start_date, end_date, freq='MONTHEND', calendar_str='GL'):
    """
    get pairs of first and last days given a freuqnecy between two dates
    :param start_date:
    :param end_date:
    :param freq:
    :param calendar_str:
    :return: P x 2 dataframes with from and to columns

    Example:
        Input:
            get_period_start_end(20220101, 20220731, 'MONTHEND', 'US')
        Output:
                     from          to
            0  2022-01-03  2022-01-31
            1  2022-02-01  2022-02-28
            2  2022-03-01  2022-03-31
            3  2022-04-01  2022-04-29
            4  2022-05-02  2022-05-31
            5  2022-06-01  2022-06-30
            6  2022-07-01  2022-07-29

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    bus_days = load_business_days(calendar_str, start_date, end_date)
    if len(bus_days) == 0:
        return np.array([])
    ends = load_business_days(calendar_str, None, None, freq)
    e_index = np.where(ends >= bus_days[-1])[0][0]
    b_index = np.where(ends >= bus_days[0])[0][0]
    a_index = np.where(ends < bus_days[0])[0][-1]

    df = pd.DataFrame(columns=['from', 'to'])
    shifted_ends = ends[a_index:e_index]
    df['to'] = ends[b_index:e_index+1]
    for idx, e in enumerate(shifted_ends):
        df['from'].iloc[idx] = next_business_days(e, calendar_str)
    return df


def previous_day(days, calendar_str=None, freq=None):
    if calendar_str is None or not isinstance(calendar_str, str):
        calendar_str = 'GL'

    if days is None:
        result = []
        return result

    if freq is None or not isinstance(freq, str):
        freq = 'DAILY'

    freq = freq.upper()
    if freq not in FREQUENCIES:
        raise Exception(f'Unsupported frequency type {freq}')
    all_bus_days = load_business_days(calendar_str, None, None, freq)
    dates = parse_date(days)
    if isinstance(dates, np.ndarray):
        n_days = np.empty(dates.shape, dtype=dt.date)
        for i, d in enumerate(dates):
            index = np.argmin(all_bus_days < d)
            if index:
                n_days[i] = all_bus_days[index - 1]
            else:
                continue
        return n_days
    else:
        index = np.argmin(all_bus_days < dates)
        if index:
            n_days = all_bus_days[index - 1]
        else:
            n_days = None
        return n_days


def previous_business_days(days, calendar_code=None, offset=1):
    """
    Prior N-th business day; If given day is a non-Business day, then it is the prior business day

    :param days: numpy array of date objects
    :param calendar_code: default None
    :param offset: default 1
    :return:
        Example:
        Input:
            previous_business_days([20220331, 20220905], 'US', 1)
        Output:
            array([datetime.date(2022, 3, 29), datetime.date(2022, 9, 1)], dtype=object)
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if calendar_code is None or not isinstance(calendar_code, str):
        calendar_code = 'GL'
    else:
        calendar_code = calendar_code.strip().upper()
    all_bus_days = load_business_days(calendar_code)
    dates = parse_date(days)
    if isinstance(dates, np.ndarray):
        n_days = np.empty(dates.shape, dtype=dt.date)
        for i, d in enumerate(dates):
            index = np.argmin(all_bus_days < d)
            if index:
                n_days[i] = all_bus_days[index - offset]
            else:
                continue
        return n_days
    else:
        index = np.argmin(all_bus_days < dates)
        if index:
            n_days = all_bus_days[index - offset]
        else:
            n_days = None
        return n_days


def next_business_days(days, calendar_code=None, offset=1):
    """
    Next N-th business day; If given day is a non-Business day, then it is the next business day
    and onwards; default is the next business day.
    :param days: date object or date int/string list or map or array
    :param calendar_code: default None ('GL')
    :param offset: default 1
    :return: numpy array of dates

    Example:
        Input:
            next_business_days([20220331, 20220905], 'US', 1)
        Output:
            array([datetime.date(2022, 4, 1), datetime.date(2022, 9, 6)], dtype=object)
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if calendar_code is None or not isinstance(calendar_code, str):
        cal_code = 'GL'
    else:
        cal_code = calendar_code.strip().upper()
    all_bus_days = load_business_days(cal_code)
    dates = parse_date(days)
    if isinstance(dates, np.ndarray):
        n_days = np.empty(dates.shape, dtype=dt.date)
        for i, d in enumerate(dates):
            index = np.argmin(all_bus_days <= d)
            if index:
                n_days[i] = all_bus_days[index + offset - 1]
            else:
                continue
        return n_days
    else:
        index = np.argmin(all_bus_days <= dates)
        if index:
            n_days = all_bus_days[index + offset - 1]
        else:
            n_days = None
        return n_days


@ft.lru_cache()
def load_all_business_days():
    """
    load all holiday calendars
    :return:
        dict

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    directory = default_output_location('util')
    file = os.path.join(directory, 'ALL_BUSINESS_DAYS.qd')
    if not exists(file):
        try:
            if not exists(directory):
                print(f"Directory not existent: {directory}")
                os.mkdir(directory)
                print(f"created: {directory}")
            # compute week days
            dates = create_week_days(print_time=True)
            save_data(dates, file)
        except IOError as ie:
            print(ie)
            print(f"Unable to save ALL_BUSINESS_DAYS: {file}")
            raise ie
        except Exception as ee:
            print(ee)
            raise ee
    else:
        dates = load_data(file)
    return np.array(dates)


@ft.lru_cache()
def load_local_business_days(calendar_code='GL'):
    days = load_all_business_days()
    holidays = load_holidays(calendar_code)
    days = np.array(sorted(set(days) - set(holidays)))
    return days


def load_holidays(calendar_code, start_date=None, end_date=None, exclude_global=False):
    """
    load a list of holidays by a calendar between two dates
    :param calendar_code: default 'GL'
    :param start_date: optional, default None
    :param end_date: optional, default None
    :param exclude_global: default False, if true, exclude global holidays
    :return: numpy array of date objects

    Example:
        Input:
            load_holidays('US', 20220901,20220930)
        Output:
            array([datetime.date(2022, 9, 5)], dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if not calendar_code or not(isinstance(calendar_code, str)):
        calendar_code = 'GL'
    else:
        calendar_code = calendar_code.strip().upper()
    file = os.path.join(default_output_location('util'), 'ALL_HOLIDAYS.qd')
    if exists(file):
        all_holidays = load_all_holidays()
        if isinstance(all_holidays, dict) and calendar_code in all_holidays.keys():
            holidays = all_holidays[calendar_code]
            if 'GL' in all_holidays.keys() and not exclude_global:
                holidays = np.union1d(holidays, all_holidays['GL'])
        else:
            holidays = np.array(([dt.date(y, 1, 1) for y in range(1, 10000)]))
    else:
        holidays = np.array([dt.date(y, 1, 1) for y in range(1, 10000)])

    if start_date and start_date is not None:
        holidays = holidays[holidays >= parse_date(start_date)]

    if end_date and end_date is not None:
        holidays = holidays[holidays <= parse_date(end_date)]

    return holidays


def add_holidays(calendar_code, holidays):
    """

    :param calendar_code:
    :param holidays:
    :return:

    Example:
        Input:
            add_holidays('US', 20220905)
        Output:
            True

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if not isinstance(calendar_code, str):
        raise ValueError('Calendar code needs be of type str')
    if not isinstance(holidays, Iterable):
        holidays = [holidays]
    h_days = parse_date(set(holidays))

    cal_code = calendar_code.strip().upper()
    h_set = {cal_code: h_days}
    directory = default_output_location('util')
    file = os.path.join(directory, 'ALL_HOLIDAYS.qd')
    if exists(file):
        gl_sets = load_data(file)
        if not isinstance(gl_sets, dict):
            print("Holiday sets should be a dict: tart anew from empty")
            gl_sets = {}
        if cal_code in gl_sets.keys():
            h_set[cal_code] = np.union1d(gl_sets[cal_code], h_set[cal_code])
            gl_sets.update(h_set)
        else:
            gl_sets.update(h_set)
    else:
        print("Creating holiday calendars for the first time")
        gl_sets = h_set
    if 'GL' not in gl_sets.keys():
        gl_sets.update({'GL':np.array([dt.date(y, 1, 1) for y in range(1, 10000)])})
    print(f"Saved {len(h_days)} unique holidays to {cal_code} calendar: {file}")
    save_data(gl_sets, file)
    return True


def remove_holidays(calendar_code, holidays):
    """
    remove holidays from a calendar
    :param calendar_code: string
    :param holidays: int or string arrays
    :return: True if successful otherwise False
    """
    if calendar_code is None or holidays is None or not isinstance(calendar_code, str):
        print("nothing to remove holidays: not in db")
        return False

    cal_code = calendar_code.strip().upper()
    h_days = parse_date(holidays)
    new_days = np.setdiff1d(load_holidays(cal_code, exclude_global=True), h_days)
    file = "{0:s}/ALL_HOLIDAYS.qd".format(default_output_location('util'))
    all_holidays = load_data(file)
    all_holidays.update({cal_code: new_days})
    save_data(all_holidays, file)
    return True


def create_week_days(start_date=None, end_date=None, print_time=False):
    """
    create weekdays
    :param start_date:
    :param end_date:
    :param print_time:
    :return:
    """
    if not start_date or start_date is None:
        start_date = dt.date(1900, 1, 1)
    if not end_date or end_date is None:
        end_date = max(dt.date(3000, 12, 31), dt.datetime.today().date() + dt.timedelta(days=365*100))
    s_date = parse_date(start_date)
    e_date = parse_date(end_date)
    a_time = time.time()
    d = list(rrule(DAILY, dtstart=s_date, until=e_date, byweekday=(0, 1, 2, 3, 4)))
    dates = list(map(lambda x: x.date(), d))
    b_time = time.time()
    if print_time:
        print(f"Took {b_time - a_time: .1f} Seconds to create {len(dates)} between {dates[0]} and {dates[-1]}")
    return dates


def month(days):
    """
    given a list of dates, return numpy array of corresponding months
    :param days:
    :return: numpy array

    Example:
        Input:
            month(util.parse_date([20030812, 20220831]))
        Output:
            array([8, 8])
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if isinstance(days, str):
        days = np.array([days])
    dates = util.utilities.parse_date(days)
    return np.array(list(map(operator.attrgetter("month"), dates)))


def year(days):
    """
    given a list of dates, return numpy array of corresponding years
    :param days:
    :return: numpy array

    Example:
        Input:
            year(util.parse_date([20030812, 20220831]))
        Output:
            array([2003, 2022])
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if isinstance(days, str):
        days = np.array([days])
    dates = util.utilities.parse_date(days)
    return np.array(list(map(operator.attrgetter("year"), dates)))


def day(days):
    """
    given a list of dates, return numpy array of corresponding days
    :param days:
    :return: numpy array

    Example:
        Input:
            day(util.parse_date([20030812, 20220831]))
        Output:
            array([12, 31])
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if isinstance(days, str):
        days = np.array([days])
    dates = util.utilities.parse_date(days)
    return np.array(list(map(operator.attrgetter("day"), dates)))


def day_of_week(days):
    """
    given a list of dates, return numpy array of corresponding day of week
    :param days:
    :return: numpy array

    Example:
        Input:
            day_of_week(util.parse_date([20030812, 20220831]))
        Output:
            array([1, 2])
    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    vf = np.vectorize(lambda x: x.weekday())
    return vf(parse_date(days))


def get_last_day_of_periods(start_date=None, end_date=None, freq='MONTHEND'):
    """
    last day of each period (month/quarter/semi-annual/year)
    :param start_date:
    :param end_date:
    :param freq: MONTHD, QUARTEREND, SEMIANNUAL, ANNUAL
    :return: numpy array of dates

    Example:
        Input:
            get_last_day_of_periods(20220101,20221230, 'SEMIANNUAL')
        Output:
            array([datetime.date(2022, 6, 30)], dtype=object)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if not start_date or start_date is None:
        start_date = dt.date(1900, 1, 1)
    if not end_date or end_date is None:
        end_date = dt.date(2100, 1, 1)
    s_date = parse_date(start_date)
    e_date = parse_date(end_date)+dt.timedelta(days=1)
    month_ends = get_ordinal_day_of_month(1,s_date, e_date)+dt.timedelta(days=-1)
    ends = month_ends[(month_ends <= e_date) & (month_ends >= s_date)]
    months = pd.to_datetime(ends).month
    freq = freq.upper().strip()
    if freq in ['MONTHEND', 'MONTHLY', 'MONTH', 'MONTHS']:
        return ends
    elif freq in ['QUARTEREND', 'QUARTERLY', 'QUARTER', 'QUARTERS']:
        index = np.where(months.isin([3, 6, 9, 12]))[0]
        return ends[index]
    elif freq in ['SEMIANNUAL', 'SEMI_ANNUAL', 'HALFYEAR', 'HALF-YEAR', 'HALF_YEAR', 'SEMI-ANNUAL']:
        index = np.where(months.isin([6, 12]))[0]
        return ends[index]
    elif freq in ['ANNUAL', 'YEAR', 'YEARLY', 'YEAREND', 'ANNUALLY']:
        index = np.where(months == 12)[0]
        return ends[index]
    else:
        return ends


def today():
    """
    today in datetime
    :return: datetime object

    Example:
        Input:
            today()
        Output:
            datetime.date(2022, 8, 29)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    return dt.date.today()


def prior_day(calendar_str=None):
    return previous_day(today(), calendar_str)


def most_recent_business_day(d=None, calendar_str='US', freq='DAILY', excluding_today=True):
    """
    Most recent business day, if requested on a holiday, the prior business day
    :param d:
    :param calendar_str: default 'US'
    :param freq:
    :param excluding_today: default True
    :return: datetime object

    Example:
        Input:
            most_recent_business_day(20220828)
        Output:
            datetime.date(2022, 8, 26)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    if calendar_str is None:
        calendar_str = 'GL'
    if freq is None:
        freq = 'DAILY'
    if d is None:
        d = today()
    days = load_business_days(calendar_str, None, d, freq)
    if excluding_today:
        days = days[days < today()]
    return days[-1]


def shift_date(d, num=0, calendar_str='US'):
    """
    :param d:
    :param num:
    :param calendar_str:
    :return:

    Example:
        Input:
            shift_date(20220331, 5)  # 5 business days AFTER requested date
        Output:
            datetime.date(2022, 4, 7)
        Input:
            shift_date(20220331, -5)  # 5 business days BEFORE requested date
        Output:
            datetime.date(2022, 3, 24)

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    d = most_recent_business_day(d, calendar_str)
    if num == 0:
        return d
    days = load_business_days(calendar_str)
    ix = np.where(days == d)[0]
    return days[ix + num][0]


def date_delta(num=0):
    return datetime.timedelta(days=num)


def get_month_end_dates(years, months):
    if isinstance(years, numbers.Number):
        return parse_date(datetime.datetime(years, months, 1) + relativedelta(day=31))
    if isinstance(years, list):
        years = np.array(years)
    if isinstance(months, list):
        months = np.array(months)
    dates = np.array([None]*len(years))
    for ix, y in enumerate(years):
        dates[ix] = datetime.datetime(y, months[ix], 1) + relativedelta(day=31)
    return parse_date(dates)

# --------------------------------------------
#
# memory
#
# --------------------------------------------


def cpu_count():
    """
    number of CPUs available
    :return: integer

    Example:
        Input:
            cpu_count()
        Output:
            8

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 29, 2022
    """
    return os.cpu_count()


def cpu_percent():
    """
    percent of CPUs utilised
    :return: float

    Example:
        Input:
            cpu_percent()
        Output:
            3.0

    Author: Yun Chen
    Copyright: Indigo Dao LLC
    Date: August 29, 2022
    """
    return psutil.cpu_percent()


def available_memory(percent=True):
    """
    available memory
    :param percent: default True
    :return: float

    Example:
        Input:
            available_memory()
        Output:
            17.799999999999997

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    mem = psutil.virtual_memory()
    if percent:
        return 100 - mem.percent
    else:
        return mem.available


def total_memory():
    """
    total memory
    :return: float

    Example:
        Input:
            total_memory()
        Output:
            8437760000

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    mem = psutil.virtual_memory()
    return mem.total

# --------------------------------------------
#
# save, load data
#
# --------------------------------------------


def load_data(file, print_time=False, env=None):
    """
    load data from file (pickled)
    :param file: string
    :param print_time: logical, default False
    :param env: default None, production
    :return:
        data

    Example:
        Input:
            load_data(my_file)
        Output:
            my_data

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 29, 2022
    """
    path = root_directory(env)
    if path not in file:
        file = os.path.join(path, file)
    try:
        fid = open(file, 'rb')
        a_time = time.time()
        if check_pandas_version():
            data = pd.read_pickle(fid)
        else:
            data = pickle.load(fid)
        b_time = time.time()
        fid.close()
        if print_time:
            display(f"Took {b_time - a_time: .1f} Seconds to open {file}")
        return data
    except IOError as ie:
        display(ie)
        display(f"Unable to load data from {file}")
        raise ie
    except Exception as ee:
        display(ee)
        display(f"Unable to load data from {file}")
        raise IOError('load_data')


def save_data(data, file, print_time=False, env=None):
    """
    save data to file (pickled)
    :param data:
    :param file:
    :param print_time: default False
    :param env: string, default None for PROD
    :return:

    Example:
        Input:
            save_data(df, my_file)
        Output:
            true

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    path = root_directory(env)
    if path not in file:
        file = os.path.join(path, file)
    try:
        fid = open(file, 'wb')
        a_time = time.time()
        pickle.dump(data, fid)
        b_time = time.time()
        if print_time:
            print(f"Took {b_time - a_time: .1f} Seconds to save to {file}")
        fid.close()
        return True
    except (OSError, IOError) as e:
        print(e)
        print('OS/IO Error')
        raise e


def merge_and_save_data(file, data, keys, overwrite=False, value_keys=None,
                        must_have_value_keys=None, env=None):
    """
    merge new with existing data frames from files
    :param file:
    :param data:
    :param keys:
    :param overwrite: default False
    :param value_keys: value column names
    :param must_have_value_keys: columns that must have values, default None
    :param env: param
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if not exists(file):
        save_data(data, file, env=env)
        return True
    if value_keys is None:
        value_keys = ['values']
    if must_have_value_keys is None:
        must_have_value_keys = value_keys

    # exclude null rows from updating data in column value if null exists
    # only those from must have value keys
    for val_key in must_have_value_keys:
        n_null = data[val_key].isnull().sum()
        if n_null > 0:
            data.dropna(inplace=True, subset=[val_key])
            data.reset_index(drop=True, inplace=True)
            print(f"{n_null} null value in '{val_key}' field of input data frame")
    # load old data
    old = load_data(file)
    old.set_index(keys, inplace=True)
    data.set_index(keys, inplace=True)
    df = old.combine_first(data)
    if overwrite:
        df.update(data)
    df.reset_index(drop=False, inplace=True)
    save_data(df, file, env)
    return True


def update_data(data, updates, keys=['sec_ids', 'source'],
                source_items=['values'], target_items=['values']):
    """
    update 'data' using infrom updates, matching on keys;
    source items ==> target items
    :param data:
    :param updates:
    :param keys:
    :param source_items:
    :param target_items:
    :return:
    """
    if keys is None:
        keys = ['sec_ids', 'source']
    if isinstance(keys, str):
        keys = [keys]
    if source_items is None:
        source_items = ['values']
    if isinstance(source_items, str):
        source_items = [source_items]
    if target_items is None:
        target_items = ['values']
    if isinstance(target_items, str):
        target_items = [target_items]
    if len(source_items) != len(target_items):
        warnings.warn(f"Source items and target items different in length")
        return False
    data = data.merge(updates, on=keys, how='left', suffixes=['', '_new'])
    for i, s in enumerate(source_items):
        t = target_items[i]
        if t == s:
            s_new = f"{s}_new"
            data[t] = np.where(pd.isnull(data[s_new]), data[t], data[s_new])
            data.drop(s_new, inplace=True, axis=1)
        else:
            data[t] = np.where(pd.isnull(data[s]), data[t], data[s])
            data.drop(s, inplace=True, axis=1)
    return data


@ft.lru_cache()
def cache_and_load_data(file, env=None):
    display(f"Caching: {file}")
    return load_data(file, env=env)


def clear_cache():
    cache_and_load_data.cache_clear()
    display(f"memory cache cleared")
    return True
# --------------------------------------------
#
# helper functions
#
# --------------------------------------------
def list_slice(lst, index=None):
    if index is None:
        return None
    val = []
    val = [lst[j] for j in index]
    return val


def where_last(array, value, less=True, include=True):
    try:
        if include:
            if less:
                return np.max(np.where(array <= value))
            else:
                return np.max(np.where(array >= value))
        else:
            if less:
                return np.max(np.where(array < value))
            else:
                return np.max(np.where(array > value))
    except ValueError:
        return None


def forward_fill(mat, fwd_fill_days):
    # use pandas forward fill is possible

    if fwd_fill_days is None or (not isinstance(fwd_fill_days, numbers.Number) or fwd_fill_days <= 0):
        return mat
    T = mat.shape[0]
    for i in range(T - 1):
        ia = T - 1 - i
        nindex = np.where(np.isnan(mat[ia,]))[0]
        if np.size(nindex) == 0:
            continue
        for j in range(fwd_fill_days):
            if ia - j < 0:
                continue
            mat[ia, nindex] = mat[ia - j - 1, nindex]
            nindex = np.where(np.isnan(mat[ia,]))
            if np.size(nindex) == 0:
                break
    return mat


def strmatch(strings, pattern, exact=True, case=False):
    """

    :param strings: a list of string
    :param pattern: string
    :param exact: default True
    :param case: default False
    :return: index
    """
    if isinstance(strings, str):
        strings = np.array([strings])
    if isinstance(strings, list):
        strings = np.array(strings)
    if exact:
        if case:
            index = [i for i, s in enumerate(strings) if s == pattern]
        else:
            index = [i for i, s in enumerate(strings) if s.upper() == pattern.upper()]
    else:
        if case:
            index = [i for i, s in enumerate(strings) if pattern in s]
        else:
            index = [i for i, s in enumerate(strings) if pattern.upper() in s.upper()]
    return index


def dense_to_sparse(mat, skip_nan=True, skip_diagonal=False):
    """
    transform [N x N] matrix to an array of [row, col, value]
    :param mat:
    :param skip_nan:
    :param skip_diagonal:
    :return:
                                            value
            Multi-Index: ('row', 'column')

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    if not isinstance(mat, pd.DataFrame):
        mf = pd.DataFrame(mat)
    else:
        mf = mat
    rows = mat.index.to_numpy()
    cols = mat.columns.to_numpy()
    condensed = pd.DataFrame(columns=['row', 'column', 'value'])
    for r in rows:
        ix = np.where(mf.loc[r] != 0)[0]
        if len(ix) == 0:
            continue
        for j in ix:
            c = cols[j]
            if skip_diagonal and c == r:
                continue
            v = mf.loc[r, c]
            if np.isnan(v) and skip_nan:
                continue
            jf = pd.DataFrame([[r, c, v]], columns=['row', 'column', 'value'])
            condensed = pd.concat([condensed, jf], axis=0, ignore_index=True)
    condensed.set_index(['row', 'column'], inplace=True)
    return condensed


def sparse_to_dense(mat, fill_zero=True):
    """
    turn rows of ['row', 'column', 'value'] into [N x N] matrix
    :param mat: ['row', 'column', 'value']
    :param fill_zero: default True
    :return:

    Example:
        Input:
            A  =         value
            row column
            0   0        1.20
                1       -0.30
            1   1        0.92

            sparse_to_dense(A)
        Output
            column    0     1
            row
            0       1.2 -0.30
            1       0.0  0.92

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: August 1, 2022
    """
    mat.reset_index(inplace=True)
    df = mat.pivot(index='row', columns='column', values='value')
    if fill_zero:
        df.fillna(0)
    return df


def display(string, screen_only=False):
    """
    display messages to screen and optionally to a log file
    :param string:
    :param screen_only:
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 1, 2022
    """
    print(f"{current_time()}: {caller(2)}: {string}")
    if not screen_only and log_file is not None:
        try:
            log_file.writelines(f"{current_time()}: {caller(2)}: {string}\n")
            log_file.flush()
        except IOError as ioe:
            display(ioe, True)
            display(f"IO Error: log file output error", True)
        except Exception as eee:
            display(eee, True)
            display(f"Exception: log file output error", True)
    return True


def sink(file=None):
    """
    set log file
    :param file: default None for a timestamp as file name
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: September 1, 2022
    """
    global log_file
    if file is None or not isinstance(file, str):
        file = f"{current_time('%Y%m%d%H%M%S')}.log"
    location = os.path.join(default_output_location('reports'), 'logs')
    if not exists(location):
        makedirs(location)
        print(f"{current_time()}: {caller()}: created {location}")
    output_file = os.path.join(location, file)
    try:
        fid = open(output_file, mode='a')
        fid.writelines(f"{'-' * 100}\n")
        fid.writelines(f"{output_file}\n")
        fid.writelines(f"{current_time()}: log begins\n")
        fid.flush()
        log_file = fid
        display(f"Writing to log file: {output_file}", True)
        return fid
    except IOError as ioe:
        display(ioe, True)
        display(f"IO Error: Unable to open log file: {log_file}", True)
    except Exception as eee:
        display(eee, True)
        display("Exception in closing log file", True)
    return None


def sunk():
    """
    close log file
    :return:
    Author : Yun Chen
    Copyright : Indigo Dao, LLC
    Date : September 1, 2022
    """
    global log_file
    if log_file is not None:
        try:
            log_file.writelines(f"{current_time()}: log ends\n")
            log_file.writelines(f"{log_file.name}\n")
            log_file.writelines(f"{'-' * 100}\n")
            display(f"Closing log file: {log_file.name}", True)
            log_file.close()
            log_file = None
        except IOError as ioe:
            display(ioe, True)
            display("IO Error in closing log file", True)
        except Exception as eee:
            display(eee, True)
            display("Exception in closing log file", True)


def trim_differential_frame(df, key_column=None, value_column=None, start_column=None, end_column=None):
    if key_column is not None:
        kc = key_column
    else:
        kc = 'sec_id'
    if value_column is not None:
        vc = value_column
    else:
        vc = 'value'
    if start_column is not None:
        sc = start_column
    else:
        sc = 'start_date'
    if end_column is not None:
        ec = end_column
    else:
        ec = 'end_date'
    df.sort_values(by=[kc, sc, ec], inplace=True)
    keys = np.unique(df[kc].to_numpy())
    zf = pd.DataFrame(columns=df.columns)
    for k in keys:
        ix = np.where(df[kc] == k)[0]
        if len(ix) == 0:
            continue
        if len(ix) == 1:
            zf = pd.concat((zf, df.iloc[ix]), axis=0, ignore_index=True)
            continue
        for i, j in enumerate(ix):
            if i == 0:
                zf = pd.concat((zf, df.iloc[[j]]), axis=0, ignore_index=True)
                continue
            if df.loc[df.index[ix[i]], vc] != df.loc[df.index[ix[i-1]], vc]:
                zf = pd.concat((zf, df.iloc[[j]]), axis=0, ignore_index=True)
                continue
            if df.loc[df.index[ix[i]], sc] == df.loc[df.index[ix[i-1]], ec]:
                zf.loc[zf.index[-1], ec] = df.loc[df.index[ix[i]], ec]
    return zf


def merge_by_date_range(f1, f2, start_column_1=None, end_column_1=None,
                        start_column_2=None, end_column_2=None):
    if start_column_1 is None:
        sc1 = 'start_date'
    else:
        sc1 = start_column_1
    if start_column_2 is None:
        sc2 = 'start_date'
    else:
        sc2 = start_column_2
    if end_column_1 is None:
        ec1 = 'end_date'
    else:
        ec1 = end_column_1
    if end_column_2 is None:
        ec2 = 'end_date'
    else:
        ec2 = end_column_2
    xs = date2int(f1[sc1])
    xe = date2int(f1[ec1])
    ys = date2int(f2[sc2])
    ye = date2int(f2[ec2])
    zs = np.union1d(xs, np.union1d(ys, np.union1d(ye, xe)))
    zs = np.setdiff1d(zs, np.max(np.union1d(xe, ye)))
    ze = np.union1d(xs, np.union1d(ys, np.union1d(ye, xe)))
    ze = np.setdiff1d(ze, np.min(ze))
    ix = pd.IntervalIndex.from_arrays(xs, xe, closed='left')
    iy = pd.IntervalIndex.from_arrays(ys, ye, closed='left')
    iz = pd.IntervalIndex.from_arrays(zs, ze, closed='left')

    c1 = np.setdiff1d(f1.columns, np.union1d(sc1, ec1))
    c2 = np.setdiff1d(f2.columns, np.union1d(sc2, ec2))
    columns = np.union1d(c1, c2)
    columns = np.append(columns, 'start_date')
    columns = np.append(columns, 'end_date')
    df = pd.DataFrame(index=range(len(iz)), columns=columns)
    df['start_date'] = parse_date(zs)
    df['end_date'] = parse_date(ze)
    for x in df.index:
        left = iz[x].left
        i1 = np.where(ix.contains(left))[0]
        if len(i1) > 0:
            df.loc[x, c1] = f1.loc[f1.index[i1[0]], c1]
        i2 = np.where(iy.contains(left))[0]
        if len(i2) > 0:
            df.loc[x, c2] = f2.loc[f2.index[i2[0]], c2]

    return df


def merge_multiple_by_date_range(df1, df2, key=None, start_column_1=None, end_column_1=None,
                                 start_column_2=None, end_column_2=None):
    if start_column_1 is None:
        sc1 = 'start_date'
    else:
        sc1 = start_column_1
    if start_column_2 is None:
        sc2 = 'start_date'
    else:
        sc2 = start_column_2
    if end_column_1 is None:
        ec1 = 'end_date'
    else:
        ec1 = end_column_1
    if end_column_2 is None:
        ec2 = 'end_date'
    else:
        ec2 = end_column_2
    if key is None or not isinstance(key, str):
        return merge_by_date_range(df1, df2, start_column_1, end_column_1, start_column_2, end_column_2)

    c1 = np.setdiff1d(df1.columns, np.union1d(sc1, ec1))
    c2 = np.setdiff1d(df2.columns, np.union1d(sc2, ec2))
    columns = np.union1d(c1, c2)
    columns = np.append(columns, 'start_date')
    columns = np.append(columns, 'end_date')
    df = pd.DataFrame(columns=columns)
    ids = np.intersect1d(df1[key], df2[key])
    missing = np.setdiff1d(df1[key], df2[key])
    if len(missing) > 0:
        ix = np.where(np.isin(df1[key], missing))[0]
        zf = pd.DataFrame(columns=columns)
        zf = pd.concat((zf, df1.loc[df1.index[ix], c1]), axis=0, ignore_index=True)
        zf['start_date'] = df1.loc[df1.index[ix], sc1]
        zf['end_date'] = df1.loc[df1.index[ix], ec1]
        df = pd.concat((df, zf), axis=0, ignore_index=True)
    for sid in ids:
        i1 = np.where(df1[key] == sid)[0]
        i2 = np.where(df2[key] == sid)[0]
        f1 = df1.iloc[i1]
        f2 = df2.iloc[i2]
        try:
            zf = merge_by_date_range(f1, f2, sc1, ec1, sc2, ec2)
            df = pd.concat((df, zf), axis=0, ignore_index=True)
        except ValueError as ve:
            display(f"{sid}: Unable to merge two differential dataset: Value Error")
            display(f"{ve}")
        except Exception as ee:
            display(f"{sid}: Unable to merge two differential dataset: Exception")
            display(f"{ee}")
    return df


@ft.lru_cache()
def check_pandas_version(version=1.5):
    versions = pd.__version__.split('.')
    vf = float(versions[0] + '.' + versions[1])
    return vf > version


def to_numpy(s):
    if s is None:
        return np.array([])
    if isinstance(s, np.ndarray):
        return s
    if isinstance(s, list):
        return np.array(s)
    if hasattr(s, 'to_numpy'):
        return s.to_numpy()
    return np.array([s])

