#
# basic factors
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#
import numbers
import time

import numpy as np
import functools as ft

# import root
from util.intersect import *
import util.utilities as util
import util.routines as rt
from util.utilities import display
import warnings
import os
import dataloader.market_data as md
import dataloader.portfolio as port
import pandas as pd


class Life:
    __slots__ = ("from_dt", 'thru_dt')

    def __init__(self,
                 from_dates=None,
                 to_dates=None
                 ):
        if from_dates is None and to_dates is not None:
            raise Exception("Incompatible From and Through Dates")
        if to_dates is None and from_dates is not None:
            raise Exception("Incompatible From and Through Dates")
        self.from_dt = util.parse_date(from_dates)
        self.thru_dt = util.parse_date(to_dates)

    def within_range(self, d):
        d_date = util.parse_date(d)
        if isinstance(self.from_dt, list):
            return any([x <= d_date <= y for (x, y) in zip(self.from_dt, self.thru_dt)])
        else:
            return self.from_dt <= d_date <= self.thru_dt


class Root(object):
    __slots__ = ('name', 'description', 'author', 'calendar', 'life')

    def __init__(self,
                 name=None,
                 description=None,
                 author=None,
                 calendar='GL',
                 life=Life(19000101, 99991231)):

        if name is not None and isinstance(name, str):
            self.name = name

        if description is not None and isinstance(description, str):
            self.description = description
        else:
            self.description = 'Generic Factor'

        if author is not None and isinstance(author, str):
            self.author = author
        else:
            self.author = 'anonymous'

        if calendar is not None and isinstance(calendar, str):
            self.calendar = calendar
        else:
            self.calendar = 'GL'

        if life is not None and isinstance(life, Life):
            self.life = life


# -----------------------------
# saving/loading/removing objects

def save_object(obj, overwrite=False, as_prod=False):
    """

    :param obj: an instance of ROOT or subclass of ROOT
    :param overwrite: default False
    :param as_prod: default False, if set True, can attempt to save object to production if permission is given
    :return: True or False

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    Modified: October 6, 2022
    """
    if not isinstance(obj, Root):
        print("Saving an object not of class Root: Failed")
        return False
    po = load_all_objects('PROD')  # production objects
    lo = load_all_objects('DEV')  # local objects
    pc = obj.name in po
    lc = obj.name in lo
    if pc and not as_prod:
        raise ValueError(f"{obj.name} conflicting production object of the same name: either login as production or "
                         f"set as_prod=True if you have write permission")
    if not lc and as_prod:
        env = 'PROD'
    else:
        if lc and as_prod:
            raise ValueError(f"saving {obj.name} to prod as prod: already in local object map, "
                             f"if you want to promote it to production, change it to a different name;\n "
                             f"if you want to save to local, do so NOT as prod by setting as_prod=False")
        env = 'DEV'
    directory = util.default_output_location('objects', env)
    file = os.path.join(directory, f"{obj.name}.qd")
    if util.exists(file):
        if not overwrite:
            print("{0:s} existent; set overwrite=True if you want to replace".format(obj.name))
            return False
        else:
            print(f"{obj.name} existent: overwriting")
    util.save_data(obj, file, False, env)
    print(f"Successfully saved object {obj.name} to {file}")
    return True


def load_object(name):
    """
    load a previously defined object: production object first, then local objects
    :param name: string or array of strings
    :return: object or array of objects

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    prod_objects = load_all_objects('PROD')
    directory = util.default_output_location('objects')
    local = util.default_output_location('objects', 'DEV')
    if not isinstance(name, list):
        env = 'PROD'
        if isinstance(name, str):
            if name not in prod_objects:
                file = os.path.join(local, f"{name}.qd")
                env = 'DEV'
            else:
                file = os.path.join(directory, f"{name}.qd")
        elif isinstance(name, Root):
            if name.name not in prod_objects:
                file = os.path.join(local, f"{name.name}.qd")
                env = 'DEV'
            else:
                file = os.path.join(directory, f"{name.name}.qd")
        else:
            file = ''
        if len(file) == 0:
            raise Exception('Unsupported object type')
        if not util.exists(file):
            print(f"Unable to find object file:{file}")
            return None
        return util.load_data(file, False, env)
    else:
        result = [None]*len(name)
        i = 0
        for s in name:
            try:
                env = 'PROD'
                if isinstance(s, str):
                    if s not in prod_objects:
                        file = os.path.join(local, f"{s}.qd")
                        env = 'DEV'
                    else:
                        file = os.path.join(directory, f"{s}.qd")
                elif isinstance(s, Root):
                    if s.name not in prod_objects:
                        file = os.path.join(local, f"{s.name}.qd")
                        env = 'DEV'
                    else:
                        file = os.path.join(directory, f"{s.name}.qd")
                else:
                    file = ''
                if len(file) == 0:
                    print("Unsupported type: No.{0:d} object requested".format(i))
                    i += 1
                    continue
                if not util.exists(file):
                    print("Unable to find No.{0:d} object file: {1:s}".format(i, file))
                    i += 1
                    continue
                else:
                    result[i] = util.load_data(file, False, env)
                i += 1
            except Exception as E:
                print(E)
                raise E
        return result


def remove_object(name, obj_type, confirm=False):
    """
    remove a previously defined object
    :param name:
    :param obj_type:
    :param confirm: default False
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    if not confirm:
        return False
    try:
        data = load_object(name)
        if data is None:
            return False
        if isinstance(data, obj_type) and hasattr(data, 'name'):
            file = os.path.join(util.default_output_location('objects'), f"{data.name}.qd")
            os.remove(file)
            print(f"{data.name} successfully removed:{file}")
            return True
        else:
            print("Object type not matched: not removed {0:s}".format(data.name))
    except Exception as e:
        print(e)
        print("Unable to remove object")
        return False


def load_all_objects(env=None):
    """
    load all objects
    :param env: default None, production
    :return:

    Author: Yun Chen
    Copyright: Indigo Dao, LLC
    Date: May 1, 2022
    """
    path = util.default_output_location('objects', env)
    return util.get_files(path, extensions=['.qd'], strip_extension=True)


def is_internal(symbols):
    if isinstance(symbols, str):
        symbols = np.array([symbols])
    df = pd.DataFrame(False, index=symbols, columns=['values'])
    internals = load_all_objects()
    ix = np.where(np.isin(symbols, internals))
    df.loc[df.index[ix], 'values'] = True
    return df

# ----------------------------
# factors


class Factor(Root):
    __slots__ = ('universe', 'model_universe', 'descriptor_location',
                 'descriptor_frequency', 'descriptor_value_type',
                 'descriptor_forward_fill', 'exposure_location',
                 'exposure_frequency', 'exposure_forward_fill', 'factors', 'factor_types',
                 'factor_themes', 'factor_lives', 'exposure_object', 'regression_object', 'regression_location',
                 'group_flag', 'caching_frequency', 'base_currency', 'source',
                 'composite_universe', 'model_composite_universe', 'residual_cache_days')

    def __init__(self,
                 name=None,
                 author=None,
                 description=None,
                 source='cosmos',
                 universe=None,
                 model_universe=None,
                 descriptor_location=None,
                 descriptor_frequency='Daily',
                 descriptor_forward_fill=None,
                 descriptor_value_type='values',
                 exposure_location=None,
                 exposure_frequency='Daily',
                 exposure_forward_fill=None,
                 factors=None,
                 factor_types=None,
                 factor_themes=None,
                 factor_lives=None,
                 exposure_object=None,
                 regression_object=None,
                 regression_location=None,
                 group_flag=False,
                 caching_frequency=None,
                 base_currency='USD'
                 ):

        super(Factor, self).__init__(name=name, author=author, description=description)
        self.composite_universe = None
        self.model_composite_universe = None
        self.residual_cache_days = None

        if source is not None and isinstance(source, (str, numbers.Number)):
            self.source = source
        else:
            self.source = 'cosmos'

        if universe is not None and isinstance(universe, (str, numbers.Number)):
            self.universe = universe
        else:
            self.universe = None

        if model_universe is not None and isinstance(model_universe, (str, numbers.Number)):
            self.model_universe = model_universe
        else:
            self.model_universe = None

        if descriptor_location is not None and isinstance(descriptor_location, str):
            self.descriptor_location = descriptor_location
        else:
            self.descriptor_location = None

        if descriptor_frequency is not None and isinstance(descriptor_frequency, str):
            self.descriptor_frequency = descriptor_frequency
        else:
            self.descriptor_frequency = 'DAILY'

        if descriptor_value_type is not None and isinstance(descriptor_value_type, str):
            self.descriptor_value_type = descriptor_value_type
        else:
            self.descriptor_value_type = 'values'

        if descriptor_forward_fill is None:
            self.descriptor_forward_fill = 'DAILY'
        else:
            self.descriptor_forward_fill = descriptor_forward_fill

        if exposure_location is not None and isinstance(exposure_location, str):
            self.exposure_location = exposure_location
        else:
            self.exposure_location = None

        if exposure_frequency is not None and isinstance(exposure_frequency, str):
            self.exposure_frequency = exposure_frequency
        else:
            self.exposure_frequency = 'DAILY'

        if exposure_forward_fill is None:
            self.exposure_forward_fill = 'DAILY'
        else:
            self.exposure_forward_fill = exposure_forward_fill

        if exposure_object is not None and isinstance(exposure_object, str):
            self.exposure_object = exposure_object
        else:
            self.exposure_object = None

        if regression_location is not None and isinstance(regression_location, str):
            self.regression_location = regression_location
        else:
            self.regression_location = None

        if regression_object is not None and isinstance(regression_object, str):
            self.regression_object = regression_object
        else:
            self.regression_object = None

        if group_flag is not None and isinstance(group_flag, bool):
            self.group_flag = group_flag
        else:
            self.group_flag = False

        if base_currency is not None and isinstance(base_currency, str):
            self.base_currency = base_currency
        else:
            self.base_currency = 'USD'

        if factors is None:
            self.factors = []

        if factor_themes is None:
            self.factor_themes = []

        if factor_lives is None:
            self.factor_lives = []

        if factor_types is None:
            self.factor_types = []

    def snapshot(self, bus_day=None, expand_flag=False,
                 include_or_exclude=None, types=None):

        result = {'factors': [], 'factor_lives': [], 'factor_types': [], 'factor_groups': [],
                  'factor_themes': []}

        # if include_or_exclude is None or not isinstance(include_or_exclude, str):
        if types is not None and isinstance(types, str):
            types = [types]

        if include_or_exclude is not None and isinstance(include_or_exclude, str):
            include_or_exclude = include_or_exclude.upper()

        index = np.where(rt.within_range(bus_day, self.factor_lives))[0]
        for i in index:
            try:
                factor_object = load_object(self.factors[i])
                if include_or_exclude is not None:
                    if 'INCLUDE' in include_or_exclude:
                        if not isinstance(factor_object, types):
                            continue
                    elif 'EXCLUDE' in include_or_exclude:
                        if isinstance(factor_object, types):
                            continue
                    else:
                        raise Exception('Not supported type: %s' % include_or_exclude)

                if factor_object.group_flag and expand_flag:
                    rslt = factor_object.snapshot(bus_day, expand_flag)
                    if rslt is None or rslt['factors'] is None or np.size(rslt['factors']) == 0:
                        factors = [factor_object.name]
                        lives = [factor_object.life]
                    else:
                        factors = rslt['factors']
                        lives = rslt['factor_lives']
                else:
                    factors = [factor_object.name]
                    lives = [factor_object.life]
            except ValueError:
                raise Exception('Cannot load factor.')
            result['factors'] = np.concatenate((result['factors'], factors))
            result['factor_lives'] = np.concatenate((result['factor_lives'], factors))
            result['factor_types'] = np.concatenate((result['factor_types'], [self.factor_types[i]] * len(lives)))
            if np.size(self.factor_themes) == 0:
                result['factor_themes'] = np.concatenate((result['factor_themes'], ['NA'] * len(lives)))
            else:
                result['factor_themes'] = np.concatenate((result['factor_themes'],
                                                          [self.factor_themes[i]] * len(lives)))
        result['factor_groups'] = np.array([self.name] * len(result['factors']))
        return result

    def load_values(self, value_type='EXPOSURE', start_date=None, end_date=None,
                    sec_ids=None, universe=None, calendar_str=None, freq_type=None,
                    fwd_fill_days=None, alt_directory=None, data_freq_type=None,
                    composite_flag=False, exposure_value_type=None, exposure_fill_value=0):
        if not isinstance(value_type, str):
            value_type = 'EXPOSURE'
        if value_type.strip().upper() == 'DESCRIPTOR' and isinstance(self.descriptor_value_type, str):
            value_type = self.descriptor_value_type
        if isinstance(sec_ids, pd.Index):
            sec_ids = sec_ids.to_numpy()
        if isinstance(sec_ids, (pd.Series, pd.DataFrame)):
            sec_ids = sec_ids.to_numpy()
        if isinstance(sec_ids, (numbers.Number, str)):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None or not isinstance(sec_ids, np.ndarray):
            sec_ids = np.array([])
        if exposure_value_type is None and not isinstance(exposure_value_type, str):
            exposure_value_type = 'values'

        if not isinstance(universe, (int, str)):
            universe = None

        if np.size(sec_ids) == 0 and universe is None:
            warnings.warn('No sec_ids or universe')
            return None

        if fwd_fill_days is None or not isinstance(fwd_fill_days, numbers.Number):
            fwd_fill_days = 0

        value_type = value_type.strip()
        exposure_flag = 'EXPOSURE' in value_type

        # requested freq
        if freq_type is None or not isinstance(freq_type, str):
            freq_type = 'DAILY'
        freq_type = freq_type.upper()
        if freq_type not in util.FREQUENCIES:
            raise Exception('unsupported date frequency')

        # data freq
        if data_freq_type is None or not isinstance(data_freq_type, str):
            if exposure_flag:
                data_freq_type = self.exposure_frequency
            else:
                data_freq_type = self.descriptor_frequency

        if data_freq_type is None or not isinstance(data_freq_type, str):
            data_freq_type = 'DAILY'

        data_freq_type = data_freq_type.upper()
        if data_freq_type not in util.FREQUENCIES:
            raise Exception('unsupported date frequency')

        # location
        if exposure_flag:
            directory = self.exposure_location
            if composite_flag:
                directory = os.path.join(directory, 'composites')
        else:
            directory = self.descriptor_location
            if composite_flag:
                directory = os.path.join(directory, 'composites')
        if alt_directory is not None and isinstance(alt_directory, str):
            directory = alt_directory

        if directory is None:
            raise Exception('directory unspecified')

        # calendar
        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        discrete_dates_flag = False
        if start_date is not None and end_date is not None:
            bus_days = util.load_business_days(calendar_str, start_date, end_date, freq_type)
            if 'DAILY' not in freq_type:
                discrete_dates_flag = True
        else:
            if start_date is None and end_date is not None:
                bus_days = end_date
            elif start_date is not None and end_date is None:
                bus_days = start_date

        if len(bus_days) == 0:
            warnings.warn(f'No valid business days according to {calendar_str} calendar')
            return False

        data_dates = util.load_business_days(calendar_str, bus_days[0], bus_days[-1], data_freq_type)
        k = fwd_fill_days
        if np.size(data_dates) == 0 or data_dates[0] > bus_days[0]:
            k = k + 1
        if k > 0:  # append one data date if first data date was behind first business day
            p_days = util.load_business_days(calendar_str, None, bus_days[0], data_freq_type)
            d_index = np.where(p_days < bus_days[0])[0][-k:]
            data_dates = np.concatenate((p_days[d_index], data_dates))

        # security IDs
        all_sec_ids = sec_ids
        if universe is not None:
            try:
                univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns)
            except ValueError:
                raise Exception('Unable to load universe %s' % universe)

        if len(all_sec_ids) == 0:
            warnings.warn('No valid securities')
            return None

        if exposure_flag:
            fwd_fill_freq = self.exposure_forward_fill
        else:
            fwd_fill_freq = self.descriptor_forward_fill
        if isinstance(fwd_fill_freq, str):
            fwd_fill_freq = np.array([fwd_fill_freq])

        df = pd.DataFrame(np.nan, index=bus_days, columns=all_sec_ids)

        for i, d in enumerate(data_dates):
            valid_days = bus_days[bus_days >= d]
            if i < len(data_dates) - 1:
                valid_days = valid_days[valid_days < data_dates[i+1]]
            c, valid_index, i2 = intersect(df.index, valid_days)
            file = os.path.join(directory, f"{d.strftime(util.yyyymmdd_format)}.qd")

            if not util.isfile(file):
                file_exist = False
                prev_d = d
                for j in range(len(fwd_fill_freq)):
                    prev_d = util.previous_day(prev_d, calendar_str, fwd_fill_freq[j])
                    file = os.path.join(directory, f"{prev_d.strftime(util.yyyymmdd_format)}.qd")

                    if util.isfile(file):
                        file_exist = True
                        print(f'{self.name}: {d.strftime(util.MM_DD_YY_format)} '
                              f'forwarded from {prev_d.strftime(util.MM_DD_YY_format)}')
                        break
                if not file_exist:
                    print(f"{self.name} : {value_type} not found for {d.strftime(util.MM_DD_YY_format)}")
                    warnings.warn(f'For {d.strftime(util.MM_DD_YY_format)}: '
                                  f'cannot find any {self.name} data ({value_type})')
                    continue

            try:
                if self.name in load_all_objects('PROD'):
                    env = 'PROD'
                else:
                    env = 'DEV'
                # data = util.load_data(file, env=env)
                data = util.cache_and_load_data(file, env=env)
                tf = pd.DataFrame(columns=['sec_ids', 'values', 'source'])
                tf['sec_ids'] = all_sec_ids
                tf['values'] = np.nan
                if exposure_flag:
                    tf['source'] = 'cosmos'
                else:
                    tf['source'] = self.source
                if composite_flag: # composite values are all internally computed
                    tf['source'] = 'cosmos'

                if exposure_flag:
                    tf = util.update_data(tf, data, keys=['sec_ids', 'source'],
                                          source_items=[exposure_value_type], target_items=['values'])
                elif 'DESCRIPTOR' in value_type:
                    tf = util.update_data(tf, data, keys=['sec_ids', 'source'],
                                          source_items=['values'], target_items=['values'])
                else:
                    if value_type not in data.columns:
                        warnings.warn(f'{self.name}: {d.strftime(util.MM_DD_YY_format)}:'
                                      f' data does not contain field {value_type}')
                        continue
                    tf = util.update_data(tf, data, keys=['sec_ids', 'source'],
                                          source_items=[value_type], target_items=['values'])
                if tf['values'].dtype == object:
                    df.iloc[valid_index, :] = tf['values'].to_numpy().transpose().astype('float64')
                else:
                    df.iloc[valid_index, :] = tf['values'].to_numpy().transpose()
            except ValueError as ve:
                print(ve)
                raise Exception(f'Failed to load on {d} for value error {ve}')
            except Exception as ee:
                print(ee)
                display(f"Unable to load values for {self.name} on {d} for exception {ee}")
        # omit load from cache and special handling for composites and ADRs
        if fwd_fill_days > 0:
            df.fillna(method='pad', limit=fwd_fill_days, inplace=True)
        if exposure_flag:
            df.fillna(exposure_fill_value, inplace=True)
        return df

    def get_values(self, bus_day, sec_id=None,
                   calendar_str=None, freq_type=None, fwd_fill_days=None,
                   value_type='DESCRIPTOR'):
        df = self.load_values(value_type, start_date=bus_day, end_date=bus_day,
                              sec_ids=sec_id, calendar_str=None,
                              freq_type=None, fwd_fill_days=None)
        if df is not None:
            df['values'] = df[sec_id]
        return df

    def compute_descriptors(self, start_date=None, end_date=None,
                            sec_ids=None, overwrite_flag=False, universe=None, calendar_str=None, freq_type=None,
                            fwd_fill_days=None, alt_directory=None, data_freq_type=None):
        return 'Not Implemented'

    def compute_exposures(self, start_date=None, end_date=None, save_flag=None):
        if self.exposure_object is None:
            warnings.warn(f"{self.name} : no exposure object specified; returning")
            return None
        exp_obj = load_object(self.exposure_object)
        if exp_obj is None:
            result = []
            warnings.warn('No exposure object defined for %s; skip exposure computation' % self.name)
            return result
        if save_flag is None or not isinstance(save_flag, bool):
            save_flag = False
        result = exp_obj.compute_exposures(start_date, end_date, self, save_flag)
        return result

    def load_exposures(self, bus_day, sec_ids=None, universe=None,
                       calendar_str=None, freq_type=None, fwd_fill_days=None,
                       constituent_flag=False, value_type=None, exposure_fill_value=0,
                       composite_flag=False):
        """

        :param bus_day:
        :param sec_ids:
        :param universe:
        :param calendar_str:
        :param freq_type:
        :param fwd_fill_days:
        :param constituent_flag:
        :param value_type:
        :param exposure_fill_value:
        :param composite_flag: False
        :return:
        """
        if bus_day is None:
            warnings.warn('No valid business day')
            raise Exception("No valid business day")
        sec_ids = util.to_numpy(sec_ids)
        if not isinstance(universe, (int, str)):
            universe = None

        if np.size(sec_ids) == 0 and universe is None:
            warnings.warn('No sec_ids or universe')
            return None

        if fwd_fill_days is None or not isinstance(fwd_fill_days, numbers.Number):
            fwd_fill_days = 0

        if value_type is None or not isinstance(value_type, str):
            value_type = 'values'

        bus_days = util.load_business_days(calendar_str, [], bus_day)
        bus_day = bus_days[-1]
        # security IDs
        all_sec_ids = sec_ids
        if universe is not None:
            try:
                univ = port.get_cached_positions(bus_day, bus_day, universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns)
            except ValueError:
                raise Exception('Unable to load universe %s' % universe)

        if len(all_sec_ids) == 0:
            warnings.warn('No valid securities')
            return None

        df = pd.DataFrame(index=all_sec_ids)

        if self.group_flag:
            snapshots = self.snapshot(bus_day)
            fac = snapshots['factors']
            if util.exists(self.exposure_location):  # load from factor group exposure cache instead of individual
                file = os.path.join(self.exposure_location, f"{bus_day.strftime(util.yyyymmdd_format)}.qd")
                if util.exists(file):
                    tf = util.load_data(file)
                    df = pd.merge(df, tf, left_index=True, right_index=True)
                    fac = np.setdiff1d(fac, df.columns)
                del tf
            for f in fac:
                try:
                    f_obj = load_object(f)
                    if f_obj is None:
                        continue
                    tf = f_obj.load_exposures(bus_day, all_sec_ids,
                                              fwd_fill_days=fwd_fill_days)
                    df = pd.merge(df, tf, left_index=True, right_index=True)
                    del tf
                except Exception as e:
                    print(e)
                    print(f)
                    raise ValueError
        else:
            kf = self.load_values('EXPOSURE', bus_day, bus_day, all_sec_ids,
                                  fwd_fill_days=fwd_fill_days, exposure_value_type=value_type,
                                  exposure_fill_value=exposure_fill_value, composite_flag=composite_flag)
            if isinstance(kf, bool):
                print(f"No exposure found for {self.name}")
            tf = pd.DataFrame(kf.to_numpy().transpose(),
                              index=kf.columns, columns=[self.name])

            df = df.merge(tf, left_index=True, right_index=True)
            # treat composites
            ce = self.load_composite_exposures(bus_day, all_sec_ids)
            if ce is not None:
                df = df.combine_first(ce)
                df.update(ce)
            del tf
        if self.group_flag:
            # treat composites
            ce = self.load_composite_exposures(bus_day, all_sec_ids)
            if ce is not None:
                df = df.combine_first(ce)
                df.update(ce)
                df.fillna(0.0)
        return df

    def load_composite_exposures(self, bus_day, sec_ids, calendar_str=None,
                                 freq_type=None, fwd_fill_days=None):
        if sec_ids is None and sec_ids is None:
            display(f"Warning: No valid securities")
            return None
        if calendar_str is None:
            calendar_str = self.calendar
        if not isinstance(calendar_str, str):
            calendar_str = self.calendar
        if self.name in load_all_objects('PROD'):
            env = 'PROD'
        else:
            env = 'DEV'
        if self.exposure_location is not None:
            location = os.path.join(util.default_output_location(env=env), self.exposure_location, 'composites')
        else:
            display(f"No composite exposure computed and location not set up")
            return None
        comp = md.get_composites(sec_ids)
        if comp.empty:
            return None
        days = util.load_business_days(calendar_str, None, bus_day)
        bus_day = days[-1]
        file = os.path.join(location, f"{bus_day.strftime(util.yyyymmdd_format)}.json")
        if not util.exists(file):
            portfolios = np.unique(comp['PortfolioID'])
            display(f"{self.name}: {bus_day} pre-computed composite exposure file not found. compute on the fly")
            por = port.get_cached_multiple_portfolios(bus_day, portfolios, calendar_str=calendar_str, recurse=True,
                                                      deep=True)
            display(f"{self.name}: load exposures: {bus_day}: loaded {len(por.index)} ({len(por.columns)} "
                    f"securities) composite holdings")
            secs = por.columns.to_numpy()
            if len(secs) == 0:
                display(f'{self.name} on {bus_day} no valid stocks found for all composites')
                return None
            exposures = self.load_exposures(bus_day, secs, fwd_fill_days=fwd_fill_days)
            ids = por.columns.intersection(exposures.index)
            values = np.matmul(por[ids].to_numpy(), exposures.loc[ids].to_numpy())
            data = pd.DataFrame(values, index=por.index, columns=exposures.columns)
            if len(data.index) > 0:
                display(f"{self.name}: {bus_day} computed {len(data.index)} (x {len(data.columns)} exposures")
            df = pd.DataFrame(0.0, index=np.unique(comp['sec_id']), columns=data.columns)
            for sid in df.index:
                ix = np.where(comp['sec_id'] == sid)[0]
                if len(ix) == 0:
                    continue
                p = comp['PortfolioID'].iloc[ix[0]]
                m = comp['Multiplier'].iloc[ix[0]]
                iy = np.where(data.index == p)[0]
                if len(iy) == 0:
                    continue
                df.loc[sid, df.columns] = m * data.loc[data.index[iy], df.columns].to_numpy()
            return df
        data = pd.read_json(file)
        df = pd.DataFrame(0.0, index=comp['sec_id'].to_numpy(), columns=data.columns)
        for sid in df.index:
            ix = np.where(comp['sec_id'] == sid)[0]
            if len(ix) == 0:
                continue
            p = comp['PortfolioID'].iloc[ix[0]]
            m = comp['Multiplier'].iloc[ix[0]]
            iy = np.where(data.index == p)[0]
            if len(iy) == 0:
                continue
            df.loc[sid, df.columns] = m * data.loc[data.index[iy], df.columns].to_numpy()
        return df

    def load_portfolio_exposures(self, bus_day, portfolios=None, portfolio_universe=None,
                                 wt_flags=None, calendar_str=None,
                                 freq_type=None, fwd_fill_days=None):
        if portfolios is None and portfolio_universe is None:
            print(f"Warning: No valid portfolios")
        if calendar_str is None:
            calendar_str = self.calendar
        if not isinstance(calendar_str, str):
            calendar_str = self.calendar
        if self.exposure_location is not None:
            location = os.path.join(self.exposure_location, 'portfolios')
        else:
            location = None
        if location is not None:
            if util.exists(location):
                print(f"Unimplemented!")
                raise NotImplementedError
        days = util.load_business_days(calendar_str, None, bus_day)
        bus_day = days[-1]
        pf = port.get_multiple_portfolios(bus_day, portfolios, wt_flags,)
        all_sec_ids = pf.columns.to_numpy()
        b = self.load_exposures(bus_day, all_sec_ids)
        mat = b.to_numpy()
        df = pd.DataFrame(np.matmul(pf.to_numpy(), mat), index=pf.index, columns=b.columns)
        return df

    def compute_composite_descriptors(self,  start_date=None, end_date=None, save_flag=False,
                                      sec_ids=None,  universe=None, model_universe=None,
                                      calendar_str=None, freq_type=None, fwd_fill_days=None,
                                      alt_directory=None, value_type=None):
        if calendar_str is None:
            calendar_str = self.calendar
        if alt_directory is not None:
            location = alt_directory
        else:
            location = os.path.join(self.descriptor_location, 'composites')
        if freq_type is None:
            freq_type = self.descriptor_frequency
        if not isinstance(freq_type, str):
            freq_type = self.descriptor_frequency
        if not util.exists(location):
            util.makedirs(location)
        bus_days = util.load_business_days(calendar_str, start_date, end_date, freq_type)
        if len(bus_days) == 0 :
            print(f"No valid business days: {calendar_str}")
            return None
        if sec_ids is None:
            sec_ids = np.array([])
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if len(sec_ids) == 0 and universe is None:
            universe = self.composite_universe
        if len(sec_ids) == 0 and model_universe is None:
            model_universe = self.model_composite_universe
        if value_type is None:
            value_type = self.descriptor_value_type
        if universe is not None:
            univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if model_universe is not None:
            model_univ = port.get_cached_positions(bus_days[0], bus_days[-1], model_universe, calendar_str)
            sec_ids = np.union1d(sec_ids, model_univ.columns.to_numpy())
        if len(sec_ids) == 0:
            print(f"No valid securities: {self.name}")

        for d in bus_days:
            try:
                por = {}
                secs = np.array([])
                tic = time.time()
                for s in sec_ids:
                    try:
                        p = port.get_cached_weights(d, d, s, calendar_str, recurse=True, deep=True)
                        por[s] = p
                        secs = np.union1d(p.columns.to_numpy(), secs)
                    except Exception as e:
                        p[s] = None
                        print(e)
                        print(f"{util.current_time()}: {self.name} on {d} unable to load holdings for {s}; skipping")
                toc = time.time()
                if len(secs) == 0:
                    print(f'{util.current_time()}: {self.name} on {d} no valid stocks found for all composites')
                    continue
                print(f"{util.current_time()}: {self.name}: loading {len(sec_ids)} portfolios: {toc-tic:.1f} seconds")
                data = self.load_values(value_type, d, d, secs, fwd_fill_days=fwd_fill_days)
                df = pd.DataFrame(index=sec_ids, columns=['sec_ids', 'source', 'values', 'median', 'mean', 'max',
                                                          'min', 'valid', 'valid %', 'invalid', 'invalid %',
                                                          'count', 'zeros', 'positive', 'negative', 'inf', '10%',
                                                          '20%', '25%', '50%', '75%', '80%', '90%', 'std', 'std raw',
                                                          'positive median', 'positive mean'])
                df['sec_ids'] = sec_ids
                df['source'] = 'cosmos'
                for k in por.keys():
                    try:
                        if por[k] is None:
                            continue
                        k_sec_ids = por[k].columns[np.where(por[k].iloc[0, :] != 0)[0]].to_numpy()
                        k_index = np.where(np.isin(data.columns, k_sec_ids))[0]
                        if len(k_index) == 0:
                            print(f"{util.current_time()}: {self.name}: {d}: {k} no data found")
                            continue
                        values = data.iloc[0, k_index].to_numpy().astype('float64')
                        v_vec = data.loc[data.index[0], data.columns[k_index]].to_numpy()
                        w_vec = por[k].loc[por[k].index[0], data.columns[k_index]].to_numpy()
                        weighted_average = np.nansum(v_vec * w_vec)
                        df.loc[k, 'count'] = len(values)
                        df.loc[k, 'valid'] = pd.notnull(values).sum()
                        if df.loc[k, 'valid'] == 0:
                            print(f"{self.name}: {d}: {k} all NaNs")
                            continue
                        df.loc[k, 'invalid'] = df.loc[k, 'count'] - df.loc[k, 'valid']
                        df.loc[k, 'valid %'] = df.loc[k, 'valid'] / df.loc[k, 'count']
                        df.loc[k, 'invalid %'] = df.loc[k, 'invalid'] / df.loc[k, 'count']
                        df.loc[k, 'max'] = np.nanmax(values)
                        df.loc[k, 'min'] = np.nanmin(values)
                        df.loc[k, 'mean'] = np.nanmean(values)
                        df.loc[k, 'median'] = np.nanmedian(values)
                        df.loc[k, 'values'] = weighted_average
                        df.loc[k, '50%'] = df.loc[k, 'median']
                        df.loc[k, 'inf'] = np.isinf(values).sum()
                        df.loc[k, 'positive'] = (values > 0).sum()
                        df.loc[k, 'negative'] = (values < 0).sum()
                        df.loc[k, 'zeros'] = (values == 0).sum()
                        df.loc[k, '25%'] = np.nanpercentile(values, 25)
                        df.loc[k, '75%'] = np.nanpercentile(values, 75)
                        df.loc[k, '10%'] = np.nanpercentile(values, 10)
                        df.loc[k, '20%'] = np.nanpercentile(values, 20)
                        df.loc[k, '80%'] = np.nanpercentile(values, 80)
                        df.loc[k, '90%'] = np.nanpercentile(values, 90)
                        df.loc[k, 'std'] = np.nanstd(rt.winsorize(values.copy(), 10, 90))
                        df.loc[k, 'std raw'] = np.nanstd(values)
                        df.loc[k, 'sum'] = np.nansum(values)
                        df.loc[k, 'positive median'] = np.nanmedian(values[values > 0])
                        idx = np.where(values > 0)[0]
                        wv_vec = w_vec * v_vec
                        df.loc[k, 'positive mean'] = np.nansum(wv_vec[idx]) / np.nansum(w_vec[idx])
                    except ValueError as e:
                        print(e)
                        print(f"{self.name} on {d} unable to process statistics on portfolio {k}")
                if save_flag:
                    value_keys = np.setdiff1d(df.columns, ['sec_ids', 'source'])
                    file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    df.reset_index(drop=True, inplace=True)
                    env = 'DEV'
                    if self.name in load_all_objects('PROD'):
                        env = 'PROD'
                    util.merge_and_save_data(file, df, keys=['sec_ids', 'source'], value_keys=value_keys,
                                             overwrite=True, env=env)
                    print(f"{util.current_time()}: {self.name} on {d}: {len(df.index)} composites statistics saved to "
                          f"{file}")
            except ValueError as e:
                print(e)
                print(f"{util.current_time()}: Unable to compute portfolio statistics on {d} for {self.name}")
                continue

    def compute_composite_exposures(self, start_date=None, end_date=None, save_flag=False,
                                    sec_ids=None, universe=None, model_universe=None, overwrite_flag=False,
                                    additional=None, calendar_str=None, freq_type=None, fwd_fill_days=0):
        """
        compute underlying portfolios for composite securities such as ETFs
        Parameters
        ----------
        start_date
        end_date
        save_flag
        sec_ids : composite securities
        universe
        model_universe
        overwrite_flag
        additional: additional portfolios (integer or array of integer of portfolio IDs)
        calendar_str
        freq_type
        fwd_fill_days

        Returns
        -------

        """
        if calendar_str is None:
            calendar_str = self.calendar
        location = os.path.join(self.exposure_location, 'composites')
        if freq_type is None:
            freq_type = self.exposure_frequency
        if not isinstance(freq_type, str):
            freq_type = self.exposure_frequency
        if not util.exists(location):
            util.makedirs(location)
        bus_days = util.load_business_days(calendar_str, start_date, end_date, freq_type)
        if len(bus_days) == 0:
            print(f"{self.name}: composite exposures: No valid business days: {calendar_str}")
            return None
        if sec_ids is None:
            sec_ids = np.array([])
        sec_ids = util.to_numpy(sec_ids)
        if len(sec_ids) == 0 and universe is None:
            universe = self.composite_universe
        if len(sec_ids) == 0 and model_universe is None:
            model_universe = self.model_composite_universe
        if universe is not None:
            univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if model_universe is not None:
            model_univ = port.get_cached_positions(bus_days[0], bus_days[-1], model_universe, calendar_str)
            sec_ids = np.union1d(sec_ids, model_univ.columns.to_numpy())
        if len(sec_ids) == 0:
            print(f"{self.name}: composite exposures: No valid securities: {self.name}")

        if self.name in load_all_objects('PROD'):
            env = 'PROD'
        else:
            env = 'DEV'
        location = os.path.join(util.default_output_location(env=env), self.exposure_location, 'composites')
        if not util.exists(location):
            util.makedirs(location)
            display(f"Successfully created for {self.name}: composite exposure location\n{location}")
        # obtain security to composite mapping
        comp = md.get_composites(sec_ids)
        portfolios = np.unique(comp['PortfolioID'].to_numpy())
        if additional is not None:
            additional = util.to_numpy(additional)
            portfolios = np.union1d(portfolios, additional)
        for d in bus_days:
            try:
                file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.json")
                if overwrite_flag:
                    missing = portfolios
                    data = None
                else:
                    if not util.exists(file):
                        missing = portfolios
                        data = None
                    else:
                        data = pd.read_json(file)
                        missing = np.setdiff1d(portfolios, data.index)
                if len(missing) == 0:
                    display(f"{self.name}: {d} no valid portfolio to run")
                    continue
                display(f"{self.name}: composite exposures: {d}: loading {len(missing)} composite holdings")
                por = port.get_cached_multiple_portfolios(d, missing, calendar_str=calendar_str, recurse=True, deep=True)
                display(f"{self.name}: composite exposures: {d}: loaded {len(por.index)} ({len(por.columns)} "
                        f"securities) composite holdings")
                secs = por.columns.to_numpy()
                if len(secs) == 0:
                    display(f'{util.current_time()}: {self.name} on {d} no valid stocks found for all composites')
                    continue
                exposures = self.load_exposures(d, secs, fwd_fill_days=fwd_fill_days)
                ids = por.columns.intersection(exposures.index)
                values = np.matmul(por[ids].to_numpy(), exposures.loc[ids].to_numpy())
                df = pd.DataFrame(values, index=por.index, columns=exposures.columns)
                if len(df.index) > 0:
                    display(f"{self.name}: {d} computed {len(df.index)} (x {len(df.columns)} exposures")
                if data is not None:
                    df = data.combine_first(df)

                if save_flag:
                    df.to_json(file)
                    display(f"{self.name} on {d}: {len(df.index)} composites statistics saved to \n"
                            f"{file}")
            except ValueError as e:
                display(e)
                display(f"{self.name}: Unable to compute portfolio statistics on {d} due to value error")
                continue
            except Exception as ee:
                display(ee)
                display(f"{self.name}: Unable to compute portfolio statistics on {d} due to exception")
        return True

    def add_factor(self, fac, fac_life, fac_type, fac_theme):
        idx = np.where(self.factors == fac)[0]
        if self.factors is None or not isinstance(self.factors, np.ndarray):
            self.factors = np.array([])
        if len(idx) > 0:
            self.factor_lives[idx] = fac_life
            self.factor_types[idx] = fac_type
            self.factor_themes[idx] = fac_theme
        else:
            self.factors = np.append(self.factors, fac)
            self.factor_lives = np.append(self.factor_lives, fac_life)
            self.factor_types = np.append(self.factor_types, fac_type)
            self.factor_themes = np.append(self.factor_themes, fac_theme)

    def remove_factor(self, fac):
        idx = np.where(self.factors == fac)[0]
        if len(idx) == 0:
            return False
        idx = np.where(self.factors != fac)[0]
        self.factors = self.factors[idx]
        self.factor_lives = self.factor_lives[idx]
        self.factor_types = self.factor_types[idx]
        self.factor_themes = self.factor_themes[idx]
        return True

    def load_factor_returns(self, start_date, end_date, horizons=None,
                            calendar_str=None, factors=None, directory=None, month_end_flag=None):

        result = {'dates': [None], 'factors': [None], 'factor_types': [None], 'factor_themes': [None],
                  'factor_groups': [None], 'horizons': [None], 'values': [None], 'r_square': [None],
                  'r_square_adjusted': [None]}

        if horizons is None:
            horizons = 1

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if directory is None or not isinstance(directory, str):
            directory = self.regression_location

        # if not util.exists(directory):
        if not util.exists(directory):
            raise Exception('Cannot find location: %s' % directory)

        if month_end_flag is None or not isinstance(month_end_flag, bool):
            month_end_flag = False

        if start_date is not None and end_date is not None:
            if month_end_flag:
                bus_days = util.load_business_days(calendar_str, start_date, end_date, 'MONTHEND')
            else:
                bus_days = util.load_business_days(calendar_str, start_date, end_date)
        else:
            if start_date is None and end_date is not None:
                bus_days = end_date
            else:
                bus_days = start_date

        num_of_days = len(bus_days)
        if num_of_days == 0:
            warnings.warn(f'No valid business days according to {calendar_str} calendar')

        if factors is None:
            factors = []
        if isinstance(factors, str):
            factors = [factors]

        if isinstance(horizons, list):
            horizons = np.array(horizons)
        horizons = np.unique(horizons)
        num_of_horizons = len(horizons)
        all_bus_days = util.load_business_days(calendar_str, None, bus_days[-1])

        result['dates'] = bus_days
        result['horizons'] = horizons
        result['values'] = [None] * num_of_horizons
        if np.size(factors) > 0:
            num_of_factors = len(factors)
            temp_val = {'dates': result['dates'], 'factors': factors,
                        'factor_types': np.array(['NA'] * num_of_factors),
                        'factor_themes': np.array(['NA'] * num_of_factors)}
            snapshots = self.snapshot(None, expand_flag=True)
            cc, ft1, ft2 = intersect(factors, snapshots['factors'])
            temp_val['factor_types'][ft1] = snapshots['factor_types'][ft2]
            temp_val['factor_themes'][ft1] = snapshots['factor_themes'][ft2]
            del (cc, ft1, ft2, snapshots)
            temp_val['factor_groups'] = np.array([self.name] * num_of_factors)
            temp_val['values'] = np.full((num_of_days, num_of_factors), np.nan)
            temp_val['intercept'] = np.full((num_of_days, 1), np.nan)
            result['values'] = [temp_val] * num_of_horizons
            result['factors'] = factors
            del (num_of_factors, temp_val)
        else:
            for j in range(num_of_horizons):
                hia = np.where(all_bus_days <= bus_days[-1])[0][-1] - horizons[j]
                try:
                    snapshots = self.snapshot(all_bus_days[hia], expand_flag=True)
                    num_of_factors = len(snapshots['factors'])
                    temp_val = {'dates': result['dates'], 'factors': snapshots['factors'],
                                'factor_types': snapshots['factor_types'], 'factor_themes': snapshots['factor_themes'],
                                'factor_groups': np.array([self.name] * num_of_factors),
                                # 'values': np.full((num_of_days, num_of_factors), np.nan),
                                'values': pd.DataFrame(index=result['dates'], columns=snapshots['factors']),
                                'intercept': np.array([np.nan] * num_of_days)}
                    result['values'][j] = temp_val
                    result['factors'] = np.union1d(factors, temp_val['factors'])
                    del (num_of_factors, snapshots, temp_val)
                except ValueError:
                    warnings.warn('No valid snapshots of factor group')
                    continue

        result['r_square'] = np.full((num_of_days, num_of_horizons), np.nan)
        result['r_square_adjusted'] = np.full((num_of_days, num_of_horizons), np.nan)
        for i in range(num_of_days):
            d = bus_days[num_of_days - i - 1]
            file = os.path.join(directory, f"factor_returns.{d.strftime('%Y%m%d')}.qd")
            if not util.isfile(file):
                holidays = util.load_holidays(self.calendar, None, end_date=d)
                if d in holidays:
                    print('%s is a holiday on calendar %s' % (d.strftime('%Y%m%d'), self.calendar))
                else:
                    if rt.within_range(d, self.life):
                        warnings.warn('%s missing regression: within life of %s' % (d.strftime('%Y%m%d'), self.name))
                continue
            try:
                if self.name in load_all_objects('PROD'):
                    env = 'PROD'
                else:
                    env = 'DEV'
                data = util.load_data(file, env=env)
                c, ia, ib = intersect(result['values'][j]['factors'], data.index)
                for j in range(num_of_horizons):
                    ix = np.where(data.columns == horizons[j])[0]
                    if len(ix) == 0:
                        display(f"{d}: {self.name}: factor returns missing horizon {horizons[j]}-day")
                        continue
                    result['values'][j]['values'].iloc[num_of_days-i-1, ia] = data.iloc[ib, ix[0]]
                    del ix
                del (c, ia, ib)
                if np.mod(i, 252) == 0:
                    display(f"{self.name}: No. {i} factor returns: {d}")
            except ValueError as ve:
                display(ve)
                raise Exception(f'Cannot load factor returns on {d}: Value Error')
            except Exception as e:
                display(e)
                display(f"Unable to load factor returns on {d}")

        result['factor_groups'] = [self.name] * len(result['factors'])
        try:
            result['factor_types'] = np.array(['NA'] * len(result['factors']))
            result['factor_themes'] = np.array(['NA'] * len(result['factors']))
            snapshots = self.snapshot()
            cc, ft1, ft2 = intersect(result['factors'], snapshots['factors'])
            result['factor_types'][ft1] = np.array(snapshots['factor_types'])[ft2]
            result['factor_themes'][ft1] = np.array(snapshots['factor_themes'])[ft2]
            del (cc, ft1, ft2, snapshots)
        except ValueError:
            warnings.warn('Unable to get factor types')
        return result

    def load_residuals(self, start_date, end_date, sec_ids, universe=None, horizons=None,
                       calendar_str=None, directory=None, month_end_flag=None):

        result = {'dates': [None], 'sec_ids': [None], 'values': [None], 'factor': [None], 'horizons': [None],
                  'r_square': [None], 'r_square_adjusted': [None]}

        if horizons is None:
            horizons = 1

        if not isinstance(horizons, (list, np.ndarray)):
            horizons = [horizons]

        if isinstance(sec_ids, (numbers.Number, str)):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None or not isinstance(sec_ids, np.ndarray):
            sec_ids = np.array([])

        if not isinstance(universe, (int, str)):
            universe = None

        if np.size(sec_ids) == 0 and universe is None:
            warnings.warn('No sec_ids or universe')
            return result

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if directory is None or not isinstance(directory, str):
            directory = self.regression_location

        if not util.exists(directory):
            raise Exception('Cannot find location: %s' % directory)

        if month_end_flag is None or not isinstance(month_end_flag, bool):
            month_end_flag = False

        discrete_date_flag = False
        if start_date is not None and end_date is not None:
            if month_end_flag:
                bus_days = util.load_business_days(calendar_str, start_date, end_date, 'MONTHEND')
                discrete_date_flag = True
            else:
                bus_days = util.load_business_days(calendar_str, start_date, end_date)
        else:
            if start_date is None and end_date is not None:
                bus_days = end_date
            else:
                bus_days = start_date
            discrete_date_flag = True

        num_of_days = len(bus_days)
        if num_of_days == 0:
            warnings.warn('No valid business days according to %s calendar' % calendar_str)

        master_sec_ids = sec_ids
        if universe is not None:
            try:
                if discrete_date_flag:
                    univ = port.get_positions(bus_days, None, universe, calendar_str)
                else:
                    univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
                master_sec_ids = np.union1d(master_sec_ids, univ.columns.to_numpy())
            except ValueError:
                raise Exception('Unable to load universe between %s and %s' %
                                (bus_days[0].strftime("%B %d, %Y"), bus_days[-1].strftime("%B %d, %Y")))
        num_of_secs = len(master_sec_ids)
        if num_of_secs == 0:
            warnings.warn('No valid securities. returning')
            return result

        if isinstance(horizons, list):
            horizons = np.array(horizons)
        horizons = np.unique(horizons)
        num_of_horizons = len(horizons)
        result['dates'] = bus_days
        result['sec_ids'] = master_sec_ids
        df = pd.DataFrame(index=bus_days, columns=master_sec_ids)
        result['values'] = [df] * num_of_horizons
        result['factor'] = self.name
        result['horizons'] = horizons
        result['r_square'] = np.full((num_of_days, num_of_horizons), np.nan)
        result['r_square_adjusted'] = np.full((num_of_days, num_of_horizons), np.nan)

        for i, d in enumerate(bus_days):
            file = os.path.join(directory, f"residuals.{d.strftime(util.yyyymmdd_format)}.qd")
            if not util.isfile(file):
                display(f'Cannot load residual returns from {file}')
                continue
            try:
                if self.name in load_all_objects('PROD'):
                    env = 'PROD'
                else:
                    env = 'DEV'
                data = util.load_data(file, env=env)
                c, ia, ib = intersect(result['sec_ids'], data.index)
                for j in range(num_of_horizons):
                    h_index = np.where(data.columns == horizons[j])[0]
                    if np.size(h_index) > 0:
                        h_index = h_index[0]
                        result['values'][j].iloc[i, ia] = data.iloc[ib, h_index]
                if np.mod(i, 63) == 0 and len(master_sec_ids) > 100:
                    print(f"{util.current_time()}:{self.name} residuals loaded for {d}")
            except ValueError:
                warnings.warn(f'Cannot load residual returns from {file}')
                continue

        return result

    def cache_factor_returns(self, start_date, end_date, save_flag=True):
        days = util.load_business_days(self.calendar, start_date, end_date)
        days = days[days <= util.today()]
        years = util.year(days)
        uy = np.unique(years)
        r = pd.DataFrame()
        display(f"{self.name}: caching factor returns: {days[0]} - {days[-1]}: {len(days)} days, {len(uy)} years")
        for y in uy:
            ix = np.where(years == y)[0]
            if len(ix) == 0:
                continue
            dates = days[ix]
            sd = np.min(dates)
            ed = np.max(dates)
            fr = self.load_factor_returns(sd, ed)
            fr = fr['values'][0]['values']
            r = r.combine_first(fr)
            file = os.path.join(self.regression_location, f"{y}.qd")
            if util.exists(file):
                df = util.load_data(file)
                df = df.combine_first(fr)
                df.update(fr)
                if save_flag:
                    util.save_data(df, file)
                    display(f"{self.name} factor returns: {y} added {len(fr.index)} to total {len(df.index)}")
            else:
                df = fr
                if save_flag:
                    util.save_data(df, file)
                    display(f"{self.name} factor returns: {y} cached {len(df.index)}")
        return r

    def load_factor_returns_from_cache(self, start_date, end_date):
        days = util.load_business_days(self.calendar, start_date, end_date)
        days = days[days <= util.today()]
        years = util.year(days)
        uy = np.unique(years)
        r = pd.DataFrame()
        display(f"{self.name}: loading cached factor returns: {days[0]} - {days[-1]}: "
                f"{len(days)} days, {len(uy)} years")
        for y in uy:
            ix = np.where(years == y)[0]
            if len(ix) == 0:
                continue
            dates = days[ix]
            sd = np.min(dates)
            ed = np.max(dates)

            file = os.path.join(self.regression_location, f"{y}.qd")
            if util.exists(file):
                df = util.load_data(file)
                missing = np.setdiff1d(dates, df.index)
                if len(missing) > 0:
                    zf = self.cache_factor_returns(missing[0], missing[-1], True)
                    df = df.combine_first(zf)
            else:
                df = self.cache_factor_returns(sd, ed, True)
            r = r.combine_first(df)
        ss = self.snapshot(expand_flag=True)
        fr = {'dates': days, 'factors': ss['factors'], 'factor_types': ss['factor_types'],
              'factor_themes': ss['factor_themes'], 'factor_groups': ss['factor_groups'], 'values': r,
              'intercept': None}
        result = {'dates': days, 'factors': ss['factors'], 'factor_types': ss['factor_types'],
                  'factor_themes': ss['factor_themes'], 'factor_groups': ss['factor_groups'], 'horizons': [1],
                  'values': [fr]}
        return result


class Exposure(Root):
    __slots__ = ('universe', 'value_type')

    def __init__(self,
                 name=None,
                 author=None,
                 description=None,
                 universe=None):
        super(Exposure, self).__init__(name=name)

        if author is not None and isinstance(author, str):
            self.author = author

        if description is not None and isinstance(description, str):
            self.description = description

        if universe is not None and isinstance(universe, (str, numbers.Number)):
            self.universe = universe

    def compute_exposures(self, start_date, end_date, factor, save_flag,
                          exposure_directory, calendar_str, grouping_factor, universe,
                          model_universe, wt_type, wt_low, wt_high, value_low, value_high,
                          cut_off_low, cut_off_high, des_freq, exp_freq, sign_flip, group_minimum,
                          exclusion_group_factor, excluded_groups, excluded_levels):
        raise Exception('Unimplemented method!')


class StandardizeExposure(Exposure):
    __slots__ = ('grouping_factor', 'group_minimum', 'exclusion_group_factor',
                 'excluded_groups', 'excluded_levels', 'excluded_universe',
                 'weight_type', 'weight_low_bound', 'weight_high_bound',
                 'value_low_bound', 'value_high_bound', 'cut_off_low', 'cut_off_high',
                 'sign_flip', 'median_adjust')

    def __init__(self,
                 name=None,
                 grouping_factor=None,
                 group_minimum=5,
                 exclusion_group_factor=None,
                 excluded_groups=None,
                 excluded_levels=None,
                 excluded_universe=None,
                 weight_type=None,
                 weight_low_bound=0,
                 weight_high_bound=100,
                 value_low_bound=0,
                 value_high_bound=100,
                 cut_off_low=0,
                 cut_off_high=100,
                 sign_flip=False,
                 median_adjust=False):

        super().__init__(name=name)

        if grouping_factor is not None and isinstance(grouping_factor, str):
            self.grouping_factor = grouping_factor
        else:
            self.grouping_factor = None

        if weight_type is not None and isinstance(weight_type, str):
            self.weight_type = weight_type
        else:
            self.weight_type = None

        if exclusion_group_factor is not None and isinstance(exclusion_group_factor, str):
            self.exclusion_group_factor = exclusion_group_factor
        else:
            self.exclusion_group_factor = None

        if excluded_groups is not None and isinstance(excluded_groups, str):
            self.excluded_groups = excluded_groups
        else:
            self.excluded_groups = None

        if excluded_levels is not None and isinstance(excluded_levels, str):
            self.excluded_levels = excluded_levels
        else:
            self.excluded_levels = None

        if excluded_universe is not None and isinstance(excluded_universe, str):
            self.excluded_universe = excluded_universe
        else:
            self.excluded_universe = None

        if group_minimum is not None and isinstance(group_minimum, numbers.Number):
            self.group_minimum = group_minimum
        else:
            self.group_minimum = 5

        if weight_low_bound is not None and isinstance(weight_low_bound, numbers.Number):
            self.weight_low_bound = weight_low_bound
        else:
            self.weight_low_bound = 0

        if weight_high_bound is not None and isinstance(weight_high_bound, numbers.Number):
            self.weight_high_bound = weight_high_bound
        else:
            self.weight_high_bound = 100

        if value_low_bound is not None and isinstance(value_low_bound, numbers.Number):
            self.value_low_bound = value_low_bound
        else:
            self.value_low_bound = 0

        if value_high_bound is not None and isinstance(value_high_bound, numbers.Number):
            self.value_high_bound = value_high_bound
        else:
            self.value_high_bound = 100

        if cut_off_low is not None and isinstance(cut_off_low, numbers.Number):
            self.cut_off_low = cut_off_low
        else:
            self.cut_off_low = -10

        if cut_off_high is not None and isinstance(cut_off_high, numbers.Number):
            self.cut_off_high = cut_off_high
        else:
            self.cut_off_high = 10

        if sign_flip is not None and isinstance(sign_flip, bool):
            self.sign_flip = sign_flip
        else:
            self.sign_flip = False
        if median_adjust is not None and isinstance(median_adjust, bool):
            self.median_adjust = median_adjust
        else:
            self.median_adjust = False

    def compute_exposures(self, start_date, end_date, factor, save_flag=None,
                          exposure_directory=None, calendar_str=None,
                          grouping_factor=None, universe=None,
                          model_universe=None, wt_type=None, wt_low=None,
                          wt_high=None, value_low=None, value_high=None,
                          cut_off_low=None, cut_off_high=None, des_freq=None,
                          exp_freq=None, sign_flip=None,
                          group_minimum=None, exclusion_group_factor=None,
                          excluded_groups=None, excluded_levels=None):

        if start_date is None:
            raise Exception('No valid start dates')
        if end_date is None:
            raise Exception('No valid end dates')

        if factor is None or not isinstance(factor, (Factor, str)):
            raise Exception('Must specify a factor')
        factor = load_object(factor)

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = factor.calendar

        if des_freq is None or not isinstance(des_freq, str):
            des_freq = factor.descriptor_frequency
        des_freq = des_freq.strip().upper()

        if exp_freq is None or not isinstance(exp_freq, str):
            exp_freq = factor.exposure_frequency
        exp_freq = exp_freq.strip().upper()

        if start_date is not None and end_date is not None:
            bus_days = util.load_business_days(calendar_str, start_date, end_date, exp_freq)
        else:
            if start_date is None and end_date is not None:
                bus_days = end_date
            elif start_date is not None and end_date is None:
                bus_days = start_date

        if len(bus_days) == 0:
            warnings.warn('No valid business days according to %s calendar; returning' % calendar_str)
            return None

        descriptor_days = util.load_business_days(calendar_str, None, bus_days[-1], des_freq)
        index = np.where(descriptor_days <= bus_days[0])[0][-1]
        descriptor_days = descriptor_days[index:]

        if universe is None or not isinstance(universe, (int, str)):
            universe = factor.universe

        if model_universe is None or not isinstance(model_universe, str):
            model_universe = factor.model_universe

        if grouping_factor is None or not isinstance(grouping_factor, str):
            grouping_factor = self.grouping_factor
        if grouping_factor is not None:
            grouping_factor = load_object(grouping_factor)

        if wt_type is None or not isinstance(wt_type, str):
            wt_type = self.weight_type

        if wt_low is None or not isinstance(wt_low, numbers.Number):
            wt_low = self.weight_low_bound

        if wt_high is None or not isinstance(wt_high, numbers.Number):
            wt_high = self.weight_high_bound

        if value_low is None or not isinstance(value_low, numbers.Number):
            value_low = self.value_low_bound

        if value_high is None or not isinstance(value_high, numbers.Number):
            value_high = self.value_high_bound

        if cut_off_low is None or not isinstance(cut_off_low, numbers.Number):
            cut_off_low = self.cut_off_low

        if cut_off_high is None or not isinstance(cut_off_high, numbers.Number):
            cut_off_high = self.cut_off_high

        if save_flag is None or not isinstance(save_flag, bool):
            save_flag = False

        if sign_flip is None or not isinstance(sign_flip, bool):
            sign_flip = self.sign_flip

        if group_minimum is None or not isinstance(group_minimum, numbers.Number):
            group_minimum = self.group_minimum

        if exposure_directory is None or not isinstance(exposure_directory, str):
            exposure_directory = factor.exposure_location

        if exclusion_group_factor is None or not isinstance(exclusion_group_factor, (str, list)):
            exclusion_group_factor = self.exclusion_group_factor

        if excluded_groups is None or not isinstance(excluded_groups, (str, list)):
            excluded_groups = self.excluded_groups

        if isinstance(excluded_groups, str):
            excluded_groups = [excluded_groups]
        elif exclusion_group_factor is None and excluded_groups is not None:
            exclusion_group_factor = grouping_factor

        if excluded_levels is None or not isinstance(excluded_levels, (str, list)):
            excluded_levels = self.excluded_levels
        if isinstance(excluded_levels, str):
            excluded_levels = [excluded_levels]
        if excluded_groups is not None:
            if excluded_levels is None and grouping_factor is not None:
                excluded_levels = [grouping_factor.level]

        if excluded_groups is not None and excluded_levels is not None:
            if len(excluded_groups) != len(excluded_levels):
                if len(excluded_levels) == 1:
                    excluded_levels = excluded_levels * len(excluded_groups)
                else:
                    raise Exception('Number of exclusion levels does not match number of excluded groups')
        excluded_universe = self.excluded_universe
        if isinstance(excluded_universe, str):
            excluded_universe = [excluded_universe]

        if save_flag and not util.exists(exposure_directory):
            util.makedirs(exposure_directory, exist_ok=True)

        # ------- weights -------
        if wt_type is not None and isinstance(wt_type, str):
            try:
                weights = port.get_weights(wt_type, bus_days[0], bus_days[-1], None,
                                           universe, calendar_str, wt_low, wt_high)
            except ValueError:
                raise Exception('Unable to compute weights in exposure generation')
        else:
            weights = None

        all_sec_ids = np.array([])
        if universe is not None:
            try:
                univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns)
            except ValueError:
                raise Exception('Unable to load universe %s' % universe)
        else:
            univ = None
        if model_universe is not None:
            try:
                model_univ = port.get_cached_positions(bus_days[0], bus_days[-1], model_universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, model_univ.columns)
            except ValueError:
                raise Exception('Unable to load model_universe %s' % model_universe)
        else:
            model_univ = None

        ex_univ = None
        if excluded_universe is not None:
            for exu in excluded_universe:
                try:
                    t_univ = port.get_cached_positions(bus_days[0], bus_days[-1], exu, calendar_str)
                    ex_univ = ex_univ.append(t_univ)
                    del t_univ
                except ValueError:
                    warnings.warn('Unable to load exclusion universe')

        rf = pd.DataFrame(0, index=bus_days, columns=all_sec_ids)

        for i, d in enumerate(bus_days):
            sec_ids = np.array([])
            if univ is not None:
                universe_sec_ids = univ.columns[univ.loc[d].to_numpy().nonzero()[0]]
            else:
                universe_sec_ids = sec_ids
            if len(universe_sec_ids) == 0:
                warnings.warn(f'No estimation universe found on {d.strftime(util.MM_DD_YY_format)}')
                continue
            sec_ids = np.union1d(sec_ids, universe_sec_ids)

            if model_univ is not None:
                sec_ids = np.union1d(sec_ids, model_univ.columns[model_univ.loc[d].to_numpy().nonzero()[0]])

            des_index = np.where(descriptor_days <= d)[0]
            if np.size(des_index) == 0:
                warnings.warn(f'Cannot find descriptor date for exposure date {d}')
            des_day = descriptor_days[des_index[-1]]
            del des_index

            # load descriptors
            try:
                des = factor.load_values('DESCRIPTOR', des_day, des_day,
                                         sec_ids, None, calendar_str)
            except ValueError:
                warnings.warn(f'Trouble loading descriptor {factor.name} '
                              f'on {des_day.strftime(util.MM_DD_YY_format)}; skipping')
                continue
            sec_ids = des.columns

            # copy data and filter for estimation universe
            vf = pd.DataFrame(des.transpose().to_numpy(), index=sec_ids, columns=['values'], dtype='float64')
            uf = pd.DataFrame(np.nan, index=universe_sec_ids, columns=['values'], dtype='float64')
            uf.update(vf)
            if uf.notnull().sum().sum() == 0:
                warnings.warn(f'No valid values found for securities within '
                              f'estimation universe; skipping {d.strftime(util.MM_DD_YY_format)}')
                continue
            # ----------------------------------------------
            # data scrubbing begins
            # check for infinite values
            num_of_inf = np.isinf(uf).sum().sum()
            if num_of_inf > 0:
                warnings.warn(f'On {d.strftime(util.MM_DD_YY_format)}'
                              f' for {factor.name}: {num_of_inf} '
                              f'securities have infinite values')
                uf.replace([np.inf, -np.inf], np.nan, inplace=True)
                vf.replace([np.inf, -np.inf], np.nan, inplace=True)

            # check for complex values
            num_of_complex = np.iscomplex(uf).sum().sum()
            if num_of_complex > 0:
                warnings.warn(f'On {d.strftime(util.MM_DD_YY_format)}'
                              f' for {factor.name}: {num_of_complex} '
                              f'securities have complex values')
                uf[np.iscomplex(uf)] = np.nan
                vf[np.iscomplex(vf)] = np.nan

            if exclusion_group_factor is not None and excluded_groups is not None:
                vf = rt.exclude_values_from_groups(d, vf, sec_ids, exclusion_group_factor, excluded_groups,
                                                   excluded_levels, calendar_str)
            if ex_univ is not None:
                for ui in ex_univ:
                    try:
                        if ui is None:
                            continue
                        ex_sec_ids = ui.columns[np.where(ui.loc[d] > 0)[0]]
                        uf[uf.index.isin(ex_sec_ids)] = np.NAN
                        vf[vf.index.isin(ex_sec_ids)] = np.NAN
                    except ValueError:
                        warnings.warn(f'{d.strftime(util.MM_DD_YY_format)}: Unable to exclude values from universe')

            u_vec, v_vec = rt.winsorize(uf.to_numpy(), low=value_low,
                                        high=value_high, alt_vector=vf.to_numpy())
            uf['values'] = u_vec
            vf['values'] = v_vec

            # ---------------------------------------------
            # compute adjustments
            # universe mean and std
            univ_weights = pd.DataFrame(np.ones_like(u_vec), index=uf.index, columns=['values'], dtype='float64')
            if weights is not None:
                wf = pd.DataFrame(weights.loc[d].transpose().to_numpy(), index=weights.columns, columns=['values'])
                univ_weights.update(wf)
                del wf
            wuf = uf * univ_weights
            univ_weights[pd.isnull(wuf)] = 0
            if self.median_adjust:
                univ_adj = np.nanmedian(uf.to_numpy())
            else:
                univ_adj = np.nansum(wuf.to_numpy()) / np.nansum(univ_weights.to_numpy())

            # group adjustments
            adj = pd.DataFrame(index=vf.index, columns=['values'])
            if grouping_factor is not None:
                adjustments = rt.group_adjustments(vf, univ_weights, grouping_factor,
                                                     d, group_minimum, self.median_adjust)
                adj['values'] = adjustments['adjustment'].to_numpy()
            else:
                adj['values'] = np.ones_like(vf) * univ_adj

            df = vf - adj

            # update those value in universe frame
            uf.update(df)
            # remove universe mean/median again, this time un-weighted
            if self.median_adjust:
                univ_adj = np.nanmedian(uf)
            else:
                univ_adj = np.nanmean(uf)
            univ_std = np.nanstd(uf)

            df = (df - univ_adj)/univ_std
            df = np.clip(df, cut_off_low, cut_off_high)

            # set NaN to zero
            df[pd.isnull(df)] = 0

            # sign lip
            if sign_flip:
                print(f'{factor.name}: {self.name}: Sign Flipped')
                df = -df
            df = np.clip(df, cut_off_low, cut_off_high)

            if save_flag:
                file = os.path.join(exposure_directory, f"{d.strftime(util.yyyymmdd_format)}.qd")
                zf = pd.DataFrame()
                zf['sec_ids'] = df.index.to_numpy()
                zf['values'] = df.to_numpy()
                zf['source'] = 'cosmos'

                if factor.name in load_all_objects('PROD'):
                    env = 'PROD'
                else:
                    env = 'DEV'
                util.save_data(zf, file, env=env)
                print(f'{util.current_time()}:{factor.name}:{self.name}:{d}: {len(df.index)} '
                      f'exposures successfully saved to \n{file}')
                del zf
        return rf


# -------------------------
# GROUP Factor
# -------------------------
class GROUP(Factor):
    __slots__ = ('classification', 'level', 'levels')

    def __init__(self,
                 name=None,
                 classification='COSMOS',
                 level='sector',
                 levels=['sector'],
                 description=None):
        super(GROUP, self).__init__(name=name)

        if name is not None and isinstance(name, str):
            self.name = name

        if classification is not None and isinstance(classification, str):
            self.classification = classification
        else:
            self.classification = 'QSR'
        self.classification = self.classification.strip()

        if level is not None and isinstance(level, str):
            self.level = level
        else:
            self.level = 'SECTOR'
        self.level = self.level.strip()
        if description is not None and isinstance(description, str):
            self.description = description
        else:
            self.description = f'classification: {self.classification} | level: {self.level}'
        if levels is not None and isinstance(levels, (np.ndarray, list)):
            self.levels = levels
        else:
            self.levels = self.level

    def load_exposures(self, bus_day, sec_ids=None, fwd_fill_days=None, alt_level=None,
                       calendar_str=None, universe=None, exposure_value_type=None, exposure_fill_value=0):

        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None:
            sec_ids = np.array([])
        sec_ids = np.array(np.unique(sec_ids))
        if len(sec_ids) == 0 and universe is None:
            print(f"No valid input universe or securities")
            return None
        if universe is not None:
            univ = port.get_cached_positions(bus_day, bus_day, universe)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if alt_level is not None:
            level = alt_level
        else:
            level = self.level
        level = level.strip().lower()
        meta_map = md.get_classification_meta_map(source=self.classification.strip(), bus_day=bus_day, levels=level)
        if level not in meta_map.columns:
            warnings.warn(f"{level} not in hierarchy in classification: {self.classification}")
            return None
        groups = np.unique(meta_map[level.lower()])
        factors = self.snapshot(bus_day, expand_flag=True, levels=level)
        if len(factors['factors']) > 0:
            groups = np.intersect1d(groups, factors['factors'])
        df = pd.DataFrame(0, index=sec_ids, columns=groups)

        if self.classification.upper() == 'RBICS':
            classification = md.get_rbics_classification(sec_ids, level=level, as_of=bus_day)
        else:
            classification = md.get_classification(sec_ids, level=level, source=self.classification,
                                                   as_of=bus_day)
        df.update(classification)
        # composites
        ce = self.load_composite_exposures(bus_day, sec_ids)
        if ce is not None:
            df = df.combine_first(ce)
            df.update(ce)
        return df

    def load_composite_exposures(self, bus_day, sec_ids, calendar_str=None,
                                 freq_type=None, fwd_fill_days=None):
        if sec_ids is None and sec_ids is None:
            display(f"Warning: No valid securities")
            return None
        if calendar_str is None:
            calendar_str = self.calendar
        if not isinstance(calendar_str, str):
            calendar_str = self.calendar
        comp = md.get_composites(sec_ids)
        if comp.empty:
            return None
        portfolios = np.unique(comp['PortfolioID'])
        days = util.load_business_days(calendar_str, None, bus_day)
        bus_day = days[-1]
        por = port.get_cached_multiple_portfolios(bus_day, portfolios, calendar_str=calendar_str, recurse=True, deep=True)
        display(f"{self.name}: load exposures: {bus_day}: loaded {len(por.index)} ({len(por.columns)} "
                f"securities) composite holdings")
        secs = por.columns.to_numpy()
        if len(secs) == 0:
            display(f'{self.name} on {bus_day} no valid stocks found for all composites')
            return None
        exposures = self.load_exposures(bus_day, secs, fwd_fill_days=fwd_fill_days)
        ids = por.columns.intersection(exposures.index)
        values = np.matmul(por[ids].to_numpy(), exposures.loc[ids].to_numpy())
        data = pd.DataFrame(values, index=por.index, columns=exposures.columns)
        if len(data.index) > 0:
            display(f"{self.name}: {bus_day} computed {len(data.index)} (x {len(data.columns)} exposures")
        df = pd.DataFrame(0.0, index=np.unique(comp['sec_id']), columns=data.columns)
        for sid in df.index:
            ix = np.where(comp['sec_id'] == sid)[0]
            if len(ix) == 0:
                continue
            p = comp['PortfolioID'].iloc[ix[0]]
            m = comp['Multiplier'].iloc[ix[0]]
            iy = np.where(data.index == p)[0]
            if len(iy) == 0:
                continue
            df.loc[sid, df.columns] = m * data.loc[data.index[iy], df.columns].to_numpy()
        return df

    def snapshot(self, bus_day=None, expand_flag=False,
                 include_or_exclude=None, types=None, levels=None):

        result = {'factors': [], 'factor_lives': [], 'factor_types': [], 'factor_groups': [],
                  'factor_themes': []}
        if not expand_flag:
            result['factors'] = np.array([self.name])
            result['factor_lives'] = np.array([self.life])
            result['factor_types'] = np.array([self.level])
            result['factor_groups'] = np.array([self.name])
            result['factor_themes'] = np.array(['INDUSTRY'])
            return result
        meta_map = md.get_classification_meta_map(self.classification, bus_day=bus_day, levels=levels)
        groups = set(pd.unique(meta_map[self.level.lower()]))
        if bus_day is None:
            bus_day = util.today()
        if len(self.factors) > 0:
            valid = self.factors[np.where(rt.within_range(bus_day, self.factor_lives))[0]]
            groups = groups.intersection(set(valid))
        result['factors'] = np.array(list(groups))
        result['factor_lives'] = np.full((len(result['factors']), 1), Life(19000101, 99991231))
        result['factor_types'] = np.full((len(result['factors']), 1), "INDUSTRY")
        result['factor_groups'] = np.full((len(result['factors']), 1), self.name)
        result['factor_themes'] = np.full((len(result['factors']), 1), "INDUSTRY")

        return result

    def filter(self, sec_ids, bus_day=None):
        if bus_day is None:
            bus_day = util.prior_day(self.calendar)
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        b = self.load_exposures(bus_day, sec_ids)
        sec_list = b.index[b.sum(axis=1) > 0].to_numpy()
        s = pd.Series(sec_ids)
        vec = np.full(sec_ids.shape, False)
        vec[s.isin(sec_list)] = True
        vec = vec.reshape((len(vec), 1))
        return vec
# -------------------------
# IDENTITY
# -------------------------


class IDENTITY(Factor):
    __slots__ = 'value'

    def __init__(self,
                 name=None,
                 author=None,
                 description=None,
                 value=1):
        super(Factor, self).__init__(name=name, author=author, description=description)
        if name is not None and isinstance(name, str):
            self.name = name
        else:
            self.name = f"Ad_Hoc_Idenity"
        if value is not None:
            self.value = value
        else:
            self.value = value

    def load_values(self, value_type='EXPOSURE', start_date=None, end_date=None,
                    sec_ids=None, universe=None, calendar_str=None, freq_type=None,
                    fwd_fill_days=None, alt_directory=None, data_freq_type=None):
        if isinstance(sec_ids, (numbers.Number, str)):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None or not isinstance(sec_ids, np.ndarray):
            sec_ids = np.array([])

        if not isinstance(universe, (int, str)):
            universe = None

        if np.size(sec_ids) == 0 and universe is None:
            warnings.warn('No sec_ids or universe')
            return None

        if fwd_fill_days is None or not isinstance(fwd_fill_days, numbers.Number):
            fwd_fill_days = 0

        # requested freq
        if freq_type is None or not isinstance(freq_type, str):
            freq_type = 'DAILY'
        freq_type = freq_type.upper()
        if freq_type not in util.FREQUENCIES:
            raise Exception('unsupported date frequency')

        # calendar
        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        discrete_dates_flag = False
        if start_date is not None and end_date is not None:
            bus_days = util.load_business_days(calendar_str, start_date, end_date, freq_type)
            if 'DAILY' not in freq_type:
                discrete_dates_flag = True
        else:
            if start_date is None and end_date is not None:
                bus_days = end_date
            elif start_date is not None and end_date is None:
                bus_days = start_date
            discrete_dates_flag = True

        if len(bus_days) == 0:
            warnings.warn(f'No valid business days according to {calendar_str} calendar')
            return False

        # security IDs
        all_sec_ids = sec_ids
        if universe is not None:
            try:
                univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns)
            except ValueError:
                raise Exception('Unable to load universe %s' % universe)
        df = pd.DataFrame(self.value, index=bus_days, columns=all_sec_ids)
        return df


# -------------------------
# Derived Factor
# -------------------------

class DerivedFactor(Factor):
    __slots__ = 'filter'

    def __init__(self,
                 name=None,
                 func_str=None
                 ):

        super(DerivedFactor, self).__init__(name=name)
        self.filter = None
        if isinstance(func_str, str):
            self.filter = func_str

    def load_values(self, value_type='DESCRIPTOR', start_date=None, end_date=None,
                    sec_ids=None, universe=None, calendar_str=None, freq_type=None,
                    fwd_fill_days=None, alt_directory=None, data_freq_type=None,
                    composite_flag=False, exposure_value_type=None, exposure_fill_value=None):
        if value_type.strip().upper() == 'EXPOSURE':
            df = Factor.load_values(self, value_type, start_date, end_date, sec_ids, universe, calendar_str,
                                    freq_type, fwd_fill_days, alt_directory, data_freq_type,
                                    exposure_value_type=exposure_value_type, exposure_fill_value=exposure_fill_value,
                                    composite_flag=composite_flag)
            return df
        if composite_flag and self.descriptor_location is not None:
            if util.exists(self.descriptor_location):
                df = Factor.load_values(self, value_type, start_date, end_date, sec_ids, universe, calendar_str,
                                        freq_type, fwd_fill_days, alt_directory, data_freq_type,
                                        composite_flag=composite_flag)
                return df
        if len(self.factors) == 0:
            warnings.warn(f'No underlying factor found for : {self.name}')
            return None
        fac = load_object(self.factors[0])
        df = fac.load_values(value_type, start_date, end_date, sec_ids, universe, calendar_str,
                             freq_type, fwd_fill_days, alt_directory, data_freq_type,
                             composite_flag=composite_flag)
        df = df.apply(eval(self.filter))
        return df


def exists(name):
    all_obj = load_all_objects()
    if name in all_obj:
        return True
    else:
        return False


class RankExposure(Exposure):
    __slots__ = ('grouping_factor', 'group_minimum', 'exclusion_group_factor',
                 'excluded_groups', 'excluded_levels', 'excluded_universe',
                 'sign_flip', 'normalize')

    def __init__(self,
                 name=None,
                 grouping_factor=None,
                 group_minimum=5,
                 exclusion_group_factor=None,
                 excluded_groups=None,
                 excluded_levels=None,
                 excluded_universe=None,
                 sign_flip=False):

        super().__init__(name=name)

        self.normalize = True
        if grouping_factor is not None and isinstance(grouping_factor, str):
            self.grouping_factor = grouping_factor
        else:
            self.grouping_factor = None
        if exclusion_group_factor is not None and isinstance(exclusion_group_factor, str):
            self.exclusion_group_factor = exclusion_group_factor
        else:
            self.exclusion_group_factor = None

        if excluded_groups is not None and isinstance(excluded_groups, str):
            self.excluded_groups = excluded_groups
        else:
            self.excluded_groups = None

        if excluded_levels is not None and isinstance(excluded_levels, str):
            self.excluded_levels = excluded_levels
        else:
            self.excluded_levels = None

        if excluded_universe is not None and isinstance(excluded_universe, str):
            self.excluded_universe = excluded_universe
        else:
            self.excluded_universe = None

        if group_minimum is not None and isinstance(group_minimum, numbers.Number):
            self.group_minimum = group_minimum
        else:
            self.group_minimum = 5

        if sign_flip is not None and isinstance(sign_flip, bool):
            self.sign_flip = sign_flip
        else:
            self.sign_flip = False

    def compute_exposures(self, start_date, end_date, factor, save_flag=None,
                          exposure_directory=None, calendar_str=None,
                          grouping_factor=None, universe=None,
                          model_universe=None, des_freq=None,
                          exp_freq=None, sign_flip=None,
                          group_minimum=None, exclusion_group_factor=None,
                          excluded_groups=None, excluded_levels=None):

        if start_date is None:
            raise Exception('No valid start dates')
        if end_date is None:
            raise Exception('No valid end dates')
        normalize = self.normalize
        if factor is None or not isinstance(factor, (Factor, str)):
            raise Exception('Must specify a factor')
        factor = load_object(factor)

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = factor.calendar

        if des_freq is None or not isinstance(des_freq, str):
            des_freq = factor.descriptor_frequency
        des_freq = des_freq.strip().upper()

        if exp_freq is None or not isinstance(exp_freq, str):
            exp_freq = factor.exposure_frequency
        exp_freq = exp_freq.strip().upper()

        discrete_dates_flag = False
        if start_date is not None and end_date is not None:
            bus_days = util.load_business_days(calendar_str, start_date, end_date, exp_freq)
            if 'DAILY' not in exp_freq:
                discrete_dates_flag = True
        else:
            if start_date is None and end_date is not None:
                bus_days = end_date
            elif start_date is not None and end_date is None:
                bus_days = start_date
            discrete_dates_flag = True

        if len(bus_days) == 0:
            warnings.warn('No valid business days according to %s calendar; returning' % calendar_str)
            return None

        descriptor_days = util.load_business_days(calendar_str, None, bus_days[-1], des_freq)
        index = np.where(descriptor_days <= bus_days[0])[0][-1]
        descriptor_days = descriptor_days[index:]

        if universe is None or not isinstance(universe, (int, str)):
            universe = factor.universe

        if model_universe is None or not isinstance(model_universe, str):
            model_universe = factor.model_universe

        if grouping_factor is None or not isinstance(grouping_factor, str):
            grouping_factor = self.grouping_factor
        if grouping_factor is not None:
            grouping_factor = load_object(grouping_factor)

        if save_flag is None or not isinstance(save_flag, bool):
            save_flag = False

        if sign_flip is None or not isinstance(sign_flip, bool):
            sign_flip = self.sign_flip

        if group_minimum is None or not isinstance(group_minimum, numbers.Number):
            group_minimum = self.group_minimum

        if exposure_directory is None or not isinstance(exposure_directory, str):
            exposure_directory = factor.exposure_location

        if exclusion_group_factor is None or not isinstance(exclusion_group_factor, (str, list)):
            exclusion_group_factor = self.exclusion_group_factor

        if excluded_groups is None or not isinstance(excluded_groups, (str, list)):
            excluded_groups = self.excluded_groups

        if isinstance(excluded_groups, str):
            excluded_groups = [excluded_groups]
        elif exclusion_group_factor is None and excluded_groups is not None:
            exclusion_group_factor = grouping_factor

        if excluded_levels is None or not isinstance(excluded_levels, (str, list)):
            excluded_levels = self.excluded_levels
        if isinstance(excluded_levels, str):
            excluded_levels = [excluded_levels]
        if excluded_groups is not None:
            if excluded_levels is None and grouping_factor is not None:
                excluded_levels = [grouping_factor.level]

        if excluded_groups is not None and excluded_levels is not None:
            if len(excluded_groups) != len(excluded_levels):
                if len(excluded_levels) == 1:
                    excluded_levels = excluded_levels * len(excluded_groups)
                else:
                    raise Exception('Number of exclusion levels does not match number of excluded groups')
        excluded_universe = self.excluded_universe
        if isinstance(excluded_universe, str):
            excluded_universe = [excluded_universe]

        if save_flag and not util.exists(exposure_directory):
            util.makedirs(exposure_directory, exist_ok=True)

        all_sec_ids = np.array([])
        if universe is not None:
            try:
                univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns)
            except ValueError:
                raise Exception('Unable to load universe %s' % universe)
        else:
            univ = None
        if model_universe is not None:
            try:
                model_univ = port.get_cached_positions(bus_days[0], bus_days[-1], model_universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, model_univ.columns)
            except ValueError:
                raise Exception('Unable to load model_universe %s' % model_universe)
        else:
            model_univ = None

        ex_univ = None
        if excluded_universe is not None:
            for exu in excluded_universe:
                try:
                    t_univ = port.get_cached_positions(bus_days[0], bus_days[-1], exu, calendar_str)
                    ex_univ = ex_univ.append(t_univ)
                    del t_univ
                except ValueError:
                    warnings.warn('Unable to load exclusion universe')

        rf = pd.DataFrame(0, index=bus_days, columns=all_sec_ids)

        for i, d in enumerate(bus_days):
            sec_ids = np.array([])
            if univ is not None:
                universe_sec_ids = univ.columns[univ.loc[d].to_numpy().nonzero()[0]]
            else:
                universe_sec_ids = sec_ids
            if len(universe_sec_ids) == 0:
                warnings.warn(f'No estimation universe found on {d.strftime(util.MM_DD_YY_format)}')
                continue
            sec_ids = np.union1d(sec_ids, universe_sec_ids)

            if model_univ is not None:
                sec_ids = np.union1d(sec_ids, model_univ.columns[model_univ.loc[d].to_numpy().nonzero()[0]])

            des_index = np.where(descriptor_days <= d)[0]
            if np.size(des_index) == 0:
                warnings.warn(f'Cannot find descriptor date for exposure date {d}')
            des_day = descriptor_days[des_index[-1]]
            del des_index

            # load descriptors
            try:
                des = factor.load_values(factor.descriptor_value_type, des_day, des_day,
                                         sec_ids, None, calendar_str)
            except ValueError:
                warnings.warn(f'Trouble loading descriptor {factor.name} '
                              f'on {des_day.strftime(util.MM_DD_YY_format)}; skipping')
                continue
            sec_ids = des.columns

            # copy data and filter for estimation universe
            vf = pd.DataFrame(des.transpose().to_numpy(), index=sec_ids, columns=['values'], dtype='float64')
            uf = pd.DataFrame(np.nan, index=universe_sec_ids, columns=['values'], dtype='float64')
            uf.update(vf)
            if uf.notnull().sum().sum() == 0:
                warnings.warn(f'No valid values found for securities within '
                              f'estimation universe; skipping {d.strftime(util.MM_DD_YY_format)}')
                continue
            univ_weights = pd.DataFrame(1, index=universe_sec_ids, columns=['values'])
            # ----------------------------------------------
            # data scrubbing begins
            # check for infinite values
            num_of_inf = np.isinf(uf).sum().sum()
            if num_of_inf > 0:
                warnings.warn(f'On {d.strftime(util.MM_DD_YY_format)}'
                              f' for {factor.name}: {num_of_inf} '
                              f'securities have infinite values')
                uf.replace([np.inf, -np.inf], np.nan, inplace=True)
                vf.replace([np.inf, -np.inf], np.nan, inplace=True)

            # check for complex values
            num_of_complex = np.iscomplex(uf).sum().sum()
            if num_of_complex > 0:
                warnings.warn(f'On {d.strftime(util.MM_DD_YY_format)}'
                              f' for {factor.name}: {num_of_complex} '
                              f'securities have complex values')
                uf[np.iscomplex(uf)] = np.nan
                vf[np.iscomplex(vf)] = np.nan

            if exclusion_group_factor is not None and excluded_groups is not None:
                vf = rt.exclude_values_from_groups(d, vf, sec_ids, exclusion_group_factor, excluded_groups,
                                                   excluded_levels, calendar_str)
            if ex_univ is not None:
                for ui in ex_univ:
                    try:
                        if ui is None:
                            continue
                        ex_sec_ids = ui.columns[np.where(ui.loc[d] > 0)[0]]
                        uf[uf.index.isin(ex_sec_ids)] = np.NAN
                        vf[vf.index.isin(ex_sec_ids)] = np.NAN
                    except ValueError:
                        warnings.warn(f'{d.strftime(util.MM_DD_YY_format)}: Unable to exclude values from universe')

            # ---------------------------------------------
            # compute ranks

            # group adjustments
            ranks = rt.group_ranks(vf, univ_weights, grouping_factor,
                                   d, group_minimum)

            if normalize:
                ranks = ranks / 100

            # sign lip
            if sign_flip:
                print(f'{factor.name}: {self.name}: Sign Flipped')
                ranks = -ranks + 2.0

            if save_flag:
                file = os.path.join(exposure_directory, f"{d.strftime(util.yyyymmdd_format)}.qd")
                zf = ranks.reset_index()
                zf.rename(columns={'index': 'sec_ids'}, inplace=True)
                zf['values'] = ranks['universe'].to_numpy()
                zf['source'] = 'cosmos'
                if factor.name in load_all_objects('PROD'):
                    env = 'PROD'
                else:
                    env = 'DEV'
                util.save_data(zf, file, env=env)
                print(f'{util.current_time()}:{factor.name}:{self.name}:{d}: {len(zf.index)} '
                      f'exposures successfully saved to \n{file}')
                del zf
        return rf


class SubstitutionFactor(Factor):

    def __init__(self,
                 name):
        super().__init__(name=name)

    def load_values(self, value_type='EXPOSURE', start_date=None, end_date=None,
                    sec_ids=None, universe=None, calendar_str=None, freq_type=None,
                    fwd_fill_days=None, alt_directory=None, data_freq_type=None,
                    composite_flag=False, exposure_value_type=None, exposure_fill_value=0):
        factors = self.factors
        f_obj = load_object(factors[0])
        df = f_obj.load_values(value_type, start_date, end_date, sec_ids, universe, calendar_str,
                               freq_type, fwd_fill_days, alt_directory, data_freq_type,
                               composite_flag, exposure_value_type, exposure_fill_value)
        if len(factors) <= 1:
            return df
        factors = factors[1:]
        objects = np.full((len(factors), 1), None)
        for ix, f in enumerate(factors):
            objects[ix] = load_object(f)
        for d in df.index:
            index = np.where(pd.isnull(df.loc[d]))[0]
            if len(index) == 0:
                continue
            ids = df.columns[index].to_numpy()
            for o in objects:
                if o is None:
                    continue
                o = o[0]
                of = o.load_values(value_type, d, d, ids, None, calendar_str,
                                   freq_type, fwd_fill_days, alt_directory, data_freq_type,
                                   composite_flag, exposure_value_type, exposure_fill_value)
                not_null = pd.notnull(of).sum(axis=1).sum()
                if not_null == 0:
                    continue
                print(f"{self.name}: {d}: substituting in {o.name}: {not_null} assets")
                df.loc[d, of.columns] = of.loc[d, of.columns]
                index = np.where(pd.isnull(df.loc[d]))[0]
                if len(index) == 0:
                    break
                ids = df.columns[index].to_numpy()
        return df


class Model(Root):

    __slots__ = ('factor_groups', 'universe', 'model_universe', 'composite_universe')

    def __init__(self,
                 name=None,
                 factor_groups=None,
                 universe=None,
                 model_universe=None):

        super(Model, self).__init__(name=name)

        if factor_groups is not None and isinstance(factor_groups, Factor):
            self.factor_groups = factor_groups

        if universe is not None and isinstance(universe, (int, str)):
            self.universe = universe
        else:
            self.universe = None

        if model_universe is not None and isinstance(model_universe, str):
            self.model_universe = model_universe
        else:
            self.model_universe = None

    def load_exposures(self, bus_day=None, sec_ids=None, universe=None,
                       calendar_str=None, freq_type=None, fwd_fill_days=None):

        result = {'dates': [], 'name': [], 'sec_ids': [], 'factors': [], 'factor_types': [],
                  'factor_themes': [], 'factor_groups': [], 'values': [], 'class_names': [],
                  'models': []}

        if isinstance(sec_ids, (numbers.Number, str)):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None or not isinstance(sec_ids, np.ndarray):
            sec_ids = np.array([])
        if freq_type is None or not isinstance(freq_type, str):
            freq_type = 'DAILY'
        freq_type = freq_type.strip().upper()
        if not isinstance(universe, (int, str)):
            universe = None
        if np.size(sec_ids) == 0 and universe is None:
            warnings.warn('No sec_ids or universe')
            return result

        if fwd_fill_days is None or not isinstance(fwd_fill_days, numbers.Number):
            fwd_fill_days = 0

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar
        bus_day = util.parse_date(bus_day)
        bus_days = util.load_business_days(self.calendar, [], bus_day, freq_type)
        b_day = bus_days[-1]
        if b_day < bus_day:
            print(f"requested for {bus_day}: using {b_day}")
        all_sec_ids = sec_ids
        if universe is not None:
            try:
                univ = port.get_positions(b_day, b_day, universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns.to_numpy())
            except ValueError:
                raise Exception('Unable to load universe %s' % universe)

        if len(all_sec_ids) == 0:
            warnings.warn(f'{self.name}: No securities to load exposures on {b_day}; returning')
            return result
        N = len(all_sec_ids)
        if len(self.factor_groups) == 0:
            print(f"No underlying factor groups for model: {self.name}")
            raise ValueError
        factors = load_object(self.factor_groups)

        if isinstance(factors, list):
            for fac in factors:
                snapshots = fac.snapshot(b_day)
                result['factors'] = np.concatenate((result['factors'], snapshots['factors']))
                result['factor_groups'] = np.concatenate((result['factor_groups'],
                                                         np.array([fac.name] * len(snapshots['factors']))))
                result['factor_types'] = np.concatenate((result['factor_types'], snapshots['factor_types']))
                result['factor_themes'] = np.concatenate((result['factor_themes'], snapshots['factor_themes']))
        else:
            snapshots = factors.snapshot(b_day)
            result['factors'] = np.concatenate((result['factors'], snapshots['factors']))
            result['factor_groups'] = np.concatenate((result['factor_groups'],
                                                     np.array([factors.name] * len(snapshots['factors']))))
            result['factor_types'] = np.concatenate((result['factor_types'], snapshots['factor_types']))
            result['factor_themes'] = np.concatenate((result['factor_themes'], snapshots['factor_themes']))

        K = len(result['factors'])
        result['class_names'] = np.array([None] * K)
        result['models'] = np.array([self.name] * K)
        result['values'] = [None]
        result['name'] = [self.name]

        val = {'dates': result['dates'][j], 'sec_ids': result['sec_ids'], 'factors': result['factors'],
               'factor_types': result['factor_types'], 'factor_themes': result['factor_themes'],
               'factor_groups': result['factor_groups'], 'values': np.zeros((N, K)),
               'class_names': result['class_names'], 'name': result['name']}
        result['values'] = val

        if not isinstance(factors, (list, np.ndarray)):
            factors = [factors]
        for i, fac in enumerate(factors):
            B = fac.load_exposures(b_day, b_day, all_sec_ids, None, calendar_str,
                                   freq_type, fwd_fill_days)

            c, ia, ib = intersect(result['sec_ids'], B['sec_ids'])
            c, ic, id = intersect(result['factors'], B['factors'])
            for j, val in enumerate(B['values']):
                val = result['values'][j]
                val['values'][np.ix_(ia, ic)] = B['values'][j]['values'][np.ix_(ib, id)]
                val['factor_types'][ic] = B['factor_types'][id]
                val['factor_themes'][ic] = B['factor_themes'][id]
                val['factor_groups'][ic] = B['factor_groups'][id]
                val['class_names'][ic] = B['class_names'][id]
                result['values'][j] = val
            del (c, ia, ib, ic, id)

        return result

