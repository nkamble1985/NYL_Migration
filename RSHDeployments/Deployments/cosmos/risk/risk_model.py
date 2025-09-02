#
# Risk Models
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#
import distutils.cygwinccompiler
import scipy.stats as stats
import pandas as pd
# import stats.routine.optimizer as op
import classes.root as root
import analytics.ra.risk_analysis as ra
import util.utilities
from classes.root import *
# from risk.ts_risk import *
from dataloader.portfolio import *
import util.routines as rt
import numpy as np
import warnings
import numbers
import os
import util.routines as rt
import stats.routine.linalg as lin
from util.utilities import display
# import stats.routine.linear_regress as lr


class RiskModel(Model):
    """
    Generic risk model
    """

    __slots__ = ('base_currency', 'default_horizon', 'data_forward_fill')

    def __init__(self, name=None,
                 base_currency=None,
                 default_horizon=1,
                 data_forward_fill='MONTHEND'):

        super(RiskModel, self).__init__(name=name)
        self.data_forward_fill = 'MONTHEND'
        if base_currency is not None and isinstance(base_currency, str):
            self.base_currency = base_currency
        else:
            self.base_currency = 'USD'

        if default_horizon is not None and isinstance(default_horizon, numbers.Number):
            self.default_horizon = default_horizon
        else:
            self.default_horizon = 1
        if data_forward_fill is not None and isinstance(data_forward_fill, str):
            self.data_forward_fill = data_forward_fill

    def load_covariance(self, bus_day, sec_ids):
        raise Exception('Unimplemented method!')

    def load_correlation(self, bus_day, sec_ids):
        covariance = self.load_covariance(bus_day, sec_ids)
        return lin.cov_to_corr(covariance)

    def load_values(self, value_type, bus_day, sec_ids=None, universe=None,
                    composite_flag=False, forward_fill_days=0, calendar_str=None, matrix_flag=False):
        if calendar_str is None:
            calendar_str = self.calendar
        if not isinstance(calendar_str, str):
            calendar_str = self.calendar
        if value_type is None:
            value_type = 'volatility'
        if not isinstance(value_type, str):
            value_type = 'volatility'
        if sec_ids is None:
            sec_ids = np.array([])
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if len(sec_ids) == 0 and universe is None:
            if composite_flag:
                universe = self.composite_universe
            else:
                universe = self.universe
        if forward_fill_days is None:
            forward_fill_days = 0
        value_type = value_type.strip().lower()
        if value_type in ['vol', 'volatility', 'volatilities']:
            data_type = 'values'
        elif value_type in ['covariance', 'variance', 'value', 'values', 'variances', 'covariances']:
            data_type = 'values'
        elif value_type in ['correlation', 'correlations', 'corr']:
            data_type = 'correlations'
        else:
            data_type = value_type
        days = util.load_business_days(calendar_str, None, bus_day)
        bus_day = days[-1]
        if universe is not None:
            univ = get_cached_positions(bus_day, bus_day, universe, calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        df = pd.DataFrame(index=sec_ids, columns=['values'], dtype='float64')
        if composite_flag:
            location = os.path.join(util.default_output_location('risks'), self.name, 'composites')
            for i in range(forward_fill_days+1):
                d = days[-(i+1)]
                file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                if not util.exists(file):
                    continue
                try:
                    data = util.load_data(file)
                    if data_type not in data.columns:
                        display(f"{self.name}: {data_type} ({value_type}) "
                                f"not part to of output on {d}")
                        continue
                    c, i1, i2 = intersect(df.index, data['sec_ids'])
                    df.loc[c] = data[[data_type]].iloc[i2].to_numpy()
                    if value_type in ['vol', 'volatilities', 'vols', 'volatility']:
                        df[['values']] = np.sqrt(df[['values']].to_numpy().astype('float64'))
                except ValueError as e:
                    display(e)
                    display(f"Unable to load for {self.name} ({value_type}) on {d}: ValueError")
                    continue
                except IOError as ie:
                    display(ie)
                    display(f"Unable to load for {self.name} ({value_type}) on {d}: IOError")
                    continue
        else:
            if value_type in ['variance', 'covariance', 'volatility', 'vol', 'volatilities', 'variances', 'covariances']:
                cov = self.load_covariance(bus_day, sec_ids)
                c, i1, i2 = intersect(sec_ids, cov.index)
                if matrix_flag:
                    df = pd.DataFrame(index=sec_ids, columns=sec_ids)
                    df.loc[c, c] = cov.loc[c, c]
                else:
                    df.loc[c] = np.diag(cov.loc[c, c].to_numpy()).reshape((len(c), 1))
                    if value_type in ['volatility', 'vol', 'volatilities']:
                        df.loc[c] = np.sqrt(df.loc[c].to_numpy())
            else:
                if not hasattr(self, 'location'):
                    print(f'no valid location for data {value_type}')
                    return None
                for i in range(forward_fill_days + 1):
                    d = days[-(i + 1)]
                    file = os.path.join(self.location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    if not util.exists(file):
                        continue
                    try:
                        data = util.load_data(file)
                        if data_type not in data.columns:
                            display(f"{self.name}: {data_type} ({value_type}) "
                                    f"not par to of output on {d}")
                            continue
                        c, i1, i2 = intersect(df.index, data['sec_ids'])
                        df.loc[c] = data[[data_type]].iloc[i2].to_numpy()
                        del (c, i1, i2)
                    except ValueError as e:
                        print(e)
                        print(f"Unable to load for {self.name} ({value_type}) on {d}")
                        continue
        return df

    def snapshot(self, bus_day=None):
        raise NotImplementedError


class FactorRiskModel(RiskModel):
    __slots__ = ('max_factor_ret_obs', 'min_factor_ret_obs',
                 'max_residual_ret_obs', 'min_residual_ret_obs',
                 'factor_risk_model', 'residual_risk_model',
                 'factor_cov_location', 'residual_cov_location',
                 'factor_ret_low_bound', 'factor_ret_high_bound',
                 'residual_ret_low_bound', 'residual_ret_high_bound',
                 'exclude_missing_industry_observation')

    def __init__(self, name=None,
                 max_factor_ret_obs=None,
                 min_factor_ret_obs=None,
                 max_residual_ret_obs=None,
                 min_residual_ret_obs=None,
                 factor_risk_model=None,
                 residual_risk_model=None,
                 factor_cov_location=None,
                 residual_cov_location=None,
                 factor_ret_low_bound=None,
                 factor_ret_high_bound=None,
                 residual_ret_low_bound=None,
                 residual_ret_high_bound=None,
                 exclude_missing_industry_observation=True):

        super(FactorRiskModel, self).__init__(name=name)
        self.exclude_missing_industry_observation = True
        self.residual_ret_low_bound = 5
        self.residual_ret_high_bound = 95
        self.factor_ret_low_bound = 5
        self.factor_ret_high_bound = 95
        if max_factor_ret_obs is not None and max_factor_ret_obs > 0:
            self.max_factor_ret_obs = max_factor_ret_obs
        else:
            self.max_factor_ret_obs = 1000

        if min_factor_ret_obs is not None and min_factor_ret_obs > 0:
            self.min_factor_ret_obs = min_factor_ret_obs
        else:
            self.min_factor_ret_obs = 5

        if max_residual_ret_obs is not None and max_residual_ret_obs > 0:
            self.max_residual_ret_obs = max_residual_ret_obs
        else:
            self.max_residual_ret_obs = 1000

        if min_residual_ret_obs is not None and min_residual_ret_obs > 0:
            self.min_residual_ret_obs = min_residual_ret_obs
        else:
            self.min_residual_ret_obs = 5

        if factor_risk_model is not None and isinstance(factor_risk_model, str):
            self.factor_risk_model = factor_risk_model
        else:
            self.factor_risk_model = None

        if residual_risk_model is not None and isinstance(residual_risk_model, str):
            self.residual_risk_model = residual_risk_model
        else:
            self.residual_risk_model = None

        if factor_cov_location is not None and isinstance(factor_cov_location, str):
            self.factor_cov_location = factor_cov_location
        else:
            self.factor_cov_location = None

        if residual_cov_location is not None and isinstance(residual_cov_location, str):
            self.residual_cov_location = residual_cov_location
        else:
            self.residual_cov_location = None
        if exclude_missing_industry_observation is not None and isinstance(exclude_missing_industry_observation, bool):
            self.exclude_missing_industry_observation = exclude_missing_industry_observation
        if residual_ret_high_bound is not None and isinstance(residual_ret_high_bound, numbers.Number):
            self.residual_ret_high_bound = residual_ret_high_bound
        else:
            self.residual_ret_high_bound = 100
        if residual_ret_low_bound is not None and isinstance(residual_ret_low_bound, numbers.Number):
            self.residual_ret_low_bound = residual_ret_low_bound
        else:
            self.residual_ret_low_bound = 0
        if factor_ret_high_bound is not None and isinstance(factor_ret_high_bound, numbers.Number):
            self.factor_ret_high_bound = factor_ret_high_bound
        else:
            self.factor_ret_high_bound = 100
        if factor_ret_low_bound is not None and isinstance(factor_ret_low_bound, numbers.Number):
            self.factor_ret_low_bound = factor_ret_low_bound
        else:
            self.factor_ret_low_bound = 0

    def load_factor_covariance(self, bus_day, factors=None, horizon=None, calendar_str=None,
                               forward_fill_days=None, location=None, exclude_nan=False):
        result = {'dates': [None], 'data_date': [None], 'factors': [None], 'models': [None],
                  'values': [None], 'risk_model': self.name}
        if bus_day is None:
            raise Exception('Must specify a date')

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if horizon is None:
            horizon = self.default_horizon

        if forward_fill_days is None or forward_fill_days < 0:
            forward_fill_days = 0

        if location is None or not isinstance(location, str):
            location = self.factor_cov_location
        if not util.exists(location):
            raise Exception('No valid input location')

        if factors is None or not isinstance(factors, (Factor, str, np.ndarray)):
            factors = []
        if isinstance(factors, Factor):
            factors = factors.name
        elif isinstance(factors, str):
            factors = np.array([factors])

        bus_days = util.load_business_days(calendar_str, None, bus_day)
        bus_days = bus_days[-1 - forward_fill_days:]
        num_of_days = len(bus_days)

        for i in range(num_of_days):
            d = bus_days[num_of_days - i - 1]
            d_str = d.strftime("%B %d, %Y")

            file = os.path.join(location, f"{d.strftime('%Y%m%d')}.qd")
            if not util.isfile(file):
                raise Exception('For %s: Unable to find file: %s' % (d_str, file))
            else:
                try:
                    data = util.load_data(file)
                    index = np.where(data['horizons'] == horizon)[0]
                    if np.size(index) == 0:
                        warnings.warn('For %s: no factor covariance for %d-day horizon' %
                                      (d_str, horizon))
                        continue
                    index = index[0]
                    result['dates'] = bus_days[-1]
                    result['data_date'] = d
                    result['factors'] = data['values'][index]['factors']
                    result['factor_groups'] = np.repeat(self.factor_groups, len(result['factors']))
                    result['models'] = np.array([self.name] * len(result['factors']))
                    result['values'] = data['values'][index]['values']
                    break
                except ValueError:
                    warnings.warn('%s: Unable to load %s' % (d_str, file))
            if i < num_of_days - 1:
                warnings.warn('Trying from previous day %s' % bus_days[-i - 1].strftime("%B %d, %Y"))
                continue
        if np.size(factors) > 0:
            K = len(factors)
            c, ia, ib = intersect(factors, result['factors'])
            values = np.full((K, K), np.nan)
            values[np.ix_(ia, ia)] = result['values'][np.ix_(ib, ib)]
            result['factors'] = factors
            result['factor_groups'] = np.repeat(self.factor_groups, len(result['factors']))
            result['models'] = np.array([self.name] * len(result['factors']))
            result['values'] = values
            del (c, ia, ib, values)
        if exclude_nan:
            n_index = np.where(pd.isnull(np.diag(result['values'])))[0]
            if len(n_index) > 0:
                display(f"{self.name}: {bus_day}: {len(n_index)} factor covariance is NaN, excluded")
                for ni in n_index:
                    display(f"    {result['factors'][ni]}")
                g_index = np.where(pd.notnull(np.diag(result['values'])))[0]
                result['factors'] = result['factors'][g_index]
                result['factor_groups'] = result['factor_groups'][g_index]
                result['models'] = result['models'][g_index]
                result['values'] = result['values'][np.ix_(g_index, g_index)]
        return result

    def load_residual_covariance(self, bus_day, sec_ids=None, universe=None, calendar_str=None,
                                 horizon=None, forward_fill_days=None, matrix_flag=False, location=None,
                                 fill_na=False):
        if bus_day is None:
            raise Exception('Must specify a date')

        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, (pd.Series, pd.DataFrame, pd.Index)):
            sec_ids = sec_ids.to_numpy()
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None or not isinstance(sec_ids, (str, list, np.ndarray)):
            sec_ids = np.array([])

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if forward_fill_days is None or forward_fill_days < 0:
            forward_fill_days = 0

        if location is None or not isinstance(location, str):
            location = self.residual_cov_location
        if not util.exists(location):
            raise Exception('No valid input location')
        if horizon is None:
            horizon = self.default_horizon
        bus_days = util.load_business_days(calendar_str, None, bus_day)
        bus_days = bus_days[-1 - forward_fill_days:]

        if universe is not None and isinstance(universe, str):
            try:
                univ = get_positions(bus_days[-1], bus_days[-1], universe, calendar_str)
                sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
            except ValueError as ve:
                display(ve)
                raise Exception(f'Unable to load universe {universe} positions: value error')
            except IOError as ie:
                display(ie)
                raise Exception(f'Unable to load universe {universe} positions: IO error')

        if np.size(sec_ids) == 0:
            warnings.warn('No sec_ids or universe')
            return
        sec_ids = np.unique(sec_ids)
        cashes = md.get_cash_securities()

        # skip treating composites and ADRs
        result = pd.DataFrame(index=sec_ids, columns=['values'])
        cash_sec = np.intersect1d(cashes, sec_ids)
        missing = sec_ids
        for i in range(len(bus_days)):
            d = bus_days[len(bus_days) - i - 1]
            d_str = d.strftime('%Y%m%d')

            file = os.path.join(location, f"{d.strftime('%Y%m%d')}.qd")
            if not util.exists(file):
                warnings.warn('For %s: Unable to find file: %s' % (d_str, file))
            else:
                try:
                    data = util.load_data(file)
                    idx = np.where(data['horizons'] == horizon)[0]
                    if len(idx) == 0:
                        print(f"{d_str}: {self.name}: can't find horizon: {horizon} in file\n{file}")
                        continue
                    data = data['values'][idx[0]]
                    found, i1, i2 = intersect(missing, data.index)
                    if len(found) > 0:
                        result.loc[missing[i1]] = data.loc[data.index[i2]]
                    if len(cash_sec) > 0:
                        n_index = np.where(pd.isnull(result.loc[cash_sec]))[0]
                        if len(n_index) > 0:
                            result.loc[cash_sec[n_index]] = 0.0
                    missing = result.index[np.where(pd.isnull(result['values']))[0]].to_numpy()
                    if len(missing) == 0:
                        break
                except ValueError as ve:
                    print(ve)
                    warnings.warn(f'{d_str}: Unable to load {file}')
            if i < len(bus_days) - 1:
                warnings.warn('Trying from previous day %s' % bus_days[-i - 1].strftime("%B %d, %Y"))
                continue
        if fill_na and len(missing) > 0 and self.universe is not None:
            try:
                univ = get_positions(bus_days[-1], bus_days[-1], self.universe)
                univ_sec_ids = np.setdiff1d(univ.columns.to_numpy(), missing)
                univ_d = self.load_residual_covariance(bus_days[-1], univ_sec_ids)
                group_stats = rt.group_stats(univ_d.index.to_numpy(), univ_d['values'].to_numpy(),
                                             'COSMOS_SECTOR', bus_days[-1])
                group = root.load_object('COSMOS_SECTOR')
                ind = group.load_exposures(bus_days[-1], missing)
                univ_median = group_stats.loc['80%', 'universe']
                m_df = pd.DataFrame(index=missing, columns=['values'])
                for m in missing:
                    idx = np.where(ind.index == m)[0]
                    if len(idx) == 0:
                        val = univ_median
                    else:
                        sx = np.where(ind.loc[m] > 0)[0]
                        if len(sx) == 0:
                            val = univ_median
                        else:
                            sector = ind.columns[sx[0]]
                            val = group_stats.loc['80%', sector]
                            if val is None:
                                val = univ_median
                    if val is None:
                        val = univ_median
                    m_df.loc[m] = val
                print(f"{self.name}: {bus_days[-1]}: {pd.notnull(m_df).sum().sum()} of "
                      f"{len(missing)} filled with sector/universe median")
                result.update(m_df)
            except ValueError:
                print(ValueError)
                print(f"Unable to fill NA on {d} for risk model: {self.name}")
        # turn vector to matrix
        if matrix_flag:
            vec = result.to_numpy()
            vec = vec.reshape((len(vec),))
            result = pd.DataFrame(np.diag(vec), index=sec_ids, columns=sec_ids)
            related = self.load_related(bus_day)
            if related is not None:
                corr = self.load_related_residual_correlation(bus_day, sec_ids, forward_fill_days, calendar_str)
                vol_sqrt = np.diag(np.sqrt(vec.astype('float64')))
                cov_mat = np.matmul(vol_sqrt, np.matmul(corr.to_numpy(), vol_sqrt))
                result = pd.DataFrame(cov_mat, index=sec_ids, columns=sec_ids)
                del cov_mat
        # skip special treatments to composites, base currency assets, and accrued income
        return result

    def load_exposures(self, bus_day=None, sec_ids=None, universe=None,
                      calendar_str=None, freq_type=None, fwd_fill_days=None):
        if bus_day is None:
            print(f"No valid business day requested")
            return None
        if isinstance(sec_ids, (numbers.Number, str)):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None or not isinstance(sec_ids, np.ndarray):
            sec_ids = np.array([])
        if freq_type is None or not isinstance(freq_type, str):
            freq_type = 'DAILY'
        freq_type = freq_type.strip().upper()
        if not isinstance(universe, str):
            universe = None
        if np.size(sec_ids) == 0 and universe is None:
            warnings.warn('No sec_ids or universe')
            return None

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
                univ = get_positions(b_day, b_day, universe, calendar_str)
                all_sec_ids = np.union1d(all_sec_ids, univ.columns.to_numpy())
            except ValueError as ve:
                display(ve)
                raise Exception(f'Unable to load universe {universe}')

        if len(all_sec_ids) == 0:
            warnings.warn(f'{self.name}: No securities to load exposures on {b_day}; returning')
            raise ValueError

        if isinstance(self.factor_groups, (np.ndarray, list)):
            if len(self.factor_groups) == 0:
                display(f"No underlying factor groups for model: {self.name}")
                raise ValueError
            elif len(self.factor_groups) > 1:
                display(f"{len(self.factor_groups)} factor groups referenced by model {self.name}: loading the first one")
            fg = load_object(self.factor_groups[0])
        elif isinstance(self.factor_groups, str):
            fg = load_object(self.factor_groups)
        else:
            warnings.warn(f"{type(self.factor_groups)} not accepted: model {self.name} on {b_day}")
            raise ValueError

        exposures = fg.load_exposures(b_day, all_sec_ids, fwd_fill_days=fwd_fill_days)
        if exposures.empty:
            print(f"Model {self.name}: {b_day} exposures returning empty for factor group: {fg.name}")
        return exposures

    def load_covariance(self, bus_day, sec_ids=None, universe=None, calendar_str=None,
                        horizon=None, forward_fill_days=None, factor_covariance_location=None,
                        residual_covariance_location=None, month_end_flag=None, exposures=None,
                        fill_na=True, correlation_flag=False):

        result = {'dates': [None], 'sec_ids': [None], 'values': [None], 'risk_model': self.name}

        if bus_day is None:
            raise Exception('Must specify a date')

        if sec_ids is None or not isinstance(sec_ids, (str, list, np.ndarray)):
            sec_ids = np.array([])

        if horizon is None:
            horizon = self.default_horizon

        if not isinstance(fill_na, bool):
            fill_na = True

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar
        bus_day = util.parse_date(bus_day)

        if forward_fill_days is None or forward_fill_days < 0:
            forward_fill_days = 0

        if factor_covariance_location is None or not isinstance(factor_covariance_location, str):
            factor_covariance_location = self.factor_cov_location
        if not util.exists(factor_covariance_location):
            raise Exception('No valid input factor_covariance_location')

        if residual_covariance_location is None or not isinstance(residual_covariance_location, str):
            residual_covariance_location = self.residual_cov_location
        if not util.exists(residual_covariance_location):
            raise Exception('No valid input residual_covariance_location')

        if month_end_flag is None or not isinstance(month_end_flag, bool):
            month_end_flag = False

        bus_days = util.load_business_days(calendar_str, [], bus_day)
        b_day = bus_days[-1]
        if b_day < bus_day:
            display(f"{self.name}: Requested {bus_day}: using {b_day}")
        if universe is not None:
            try:
                univ = get_positions(b_day, b_day, universe, calendar_str)
                sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
            except ValueError:
                raise Exception('Unable to load universe %s positions' % universe)

        matrix_flag = False
        related = md.get_related_security_map(sec_ids)
        if not related.empty:
            matrix_flag = True
        if np.size(sec_ids) == 0:
            warnings.warn('No sec_ids or universe')
            return result
        sec_ids = np.unique(sec_ids)

        if exposures is None:
            try:
                if month_end_flag:
                    freq = 'MONTHEND'
                else:
                    freq = 'DAILY'
                exposures = self.load_exposures(b_day, sec_ids, None, calendar_str, freq,
                                                fwd_fill_days=forward_fill_days)
            except ValueError:
                raise Exception(f'model {self.name}: Unable to load factor exposures: {b_day}')

        try:
            factor_covariance = self.load_factor_covariance(b_day, None, horizon, calendar_str, forward_fill_days,
                                                            factor_covariance_location)
        except ValueError as ve:
            display(ve)
            raise Exception(f'Model {self.name}: Unable to load factor covariance for: {b_day}')

        good_index = np.where(~np.isnan(np.diag(factor_covariance['values'])))[0]
        if np.size(good_index) == 0:
            raise Exception('No valid factor covariance')
        if len(good_index) < len(factor_covariance['factors']):
            factor_covariance['factors'] = factor_covariance['factors'][good_index]
            factor_covariance['values'] = factor_covariance['values'][np.ix_(good_index, good_index)]

        try:
            residual_covariance = self.load_residual_covariance(b_day, sec_ids, None, calendar_str,
                                                                forward_fill_days=forward_fill_days,
                                                                location=residual_covariance_location,
                                                                fill_na=fill_na, matrix_flag=matrix_flag)
        except ValueError as ve:
            display(ve)
            raise Exception(f'{self.name}: Unable to load residual covariance: {b_day}')

        exposures_mat = exposures.to_numpy()
        num_of_sec = len(sec_ids)
        factor_contrib = np.full((num_of_sec, num_of_sec), np.nan)
        residual_contrib = np.full((num_of_sec, num_of_sec), np.nan)

        c, ia, ib = intersect(sec_ids, exposures.index.to_numpy())
        c, ig, ih = intersect(exposures.columns.to_numpy(), factor_covariance['factors'])
        if np.size(c) == 0:
            raise Exception('No valid common factors between exposures and factor covariance')
        f_cov = factor_covariance['values']
        factor_contrib[np.ix_(ia, ia)] = np.matmul(np.matmul(exposures_mat[np.ix_(ib, ig)], f_cov[np.ix_(ih, ih)]),
                                                   exposures_mat[np.ix_(ib, ig)].T)
        del (c, ia, ib, ig, ih)

        c, ie, ig = intersect(sec_ids, residual_covariance.index.to_numpy())
        missing = np.setdiff1d(sec_ids, residual_covariance.index.to_numpy())
        if np.size(missing) > 0:
            warnings.warn('POTENTIALLY VERY DANGEROUS: These sec_ids are missing residual risk!')
            for i in range(len(missing)):
                print('%s\n' % missing[i])

        residual_mat = residual_covariance.to_numpy()
        if residual_mat.ndim == 1 or (1 in residual_mat.shape):
            r_array = residual_mat.reshape((len(residual_mat),))
            residual_contrib[np.ix_(ie, ie)] = np.diag(r_array[ig])
            del r_array
        else:
            if residual_mat.shape[0] == residual_mat.shape[1]:
                residual_contrib[np.ix_(ie, ie)] = residual_mat[np.ix_(ig, ig)]
            else:
                raise Exception('Unsupported dimension from residual covariance')
        df = pd.DataFrame(factor_contrib + residual_contrib, index=sec_ids, columns=sec_ids)
        if correlation_flag:
            df = lin.cov_to_corr(df)
        return df

    def load_related_residual_correlation(self, bus_day, sec_ids, forward_fill_days=None,
                                          calendar_str=None, location=None):
        if forward_fill_days is None:
            forward_fill_days = 0
        if calendar_str is None:
            calendar_str = self.calendar
        if location is None:
            location = self.residual_cov_location
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        days = util.load_business_days(calendar_str, None, bus_day)
        bus_days = days[-(forward_fill_days+1): ]
        df = pd.DataFrame(0.0, index=sec_ids, columns=sec_ids, dtype='float64')
        for i in range(len(bus_days)):
            d = bus_days[len(bus_days) - i - 1]
            file = os.path.join(location, f"related.{d.strftime('%Y%m%d')}.qd")
            if util.exists(file):
                try:
                    data = util.load_data(file)
                    data = util.sparse_to_dense(data)
                    data = data.astype('float64')
                    df.update(data)
                except ValueError as voe:
                    print(voe)
                    print(f"Unable to load due to Value Error")
                except IOError as ioe:
                    print(ioe)
                    print(f"Unable to load due to IO Error")
                except Exception as exe:
                    print(exe)
                    print(f"Unable to load due to exception")
        np.fill_diagonal(df.values, 1)
        return df

    def load_portfolio_volatility(self, bus_day, portfolios, wt_flags=None, forward_fill_days=None,
                                  calendar_str=None):
        cov = self.load_portfolio_covariance(bus_day, portfolios, wt_flags, forward_fill_days=forward_fill_days,
                                             calendar_str=calendar_str, correlation_flag=False)
        df = pd.DataFrame(np.sqrt(np.diag(cov.astype('float64'))), index=cov.index, columns=['values'])
        return df

    def load_portfolio_covariance(self, bus_day, portfolios, wt_flags=None,
                                  correlation_flag=False, forward_fill_days=None, calendar_str=None,
                                  benchmark=None, bench_wt_flag=None):
        """

        :param bus_day:
        :param portfolios:
        :param wt_flags:
        :param correlation_flag:
        :param forward_fill_days:
        :param calendar_str:
        :param benchmark:
        :param bench_wt_flag:
        :return:
        """
        if forward_fill_days is None:
            forward_fill_days = 0
        if calendar_str is None:
            calendar_str = self.calendar
        pf = get_multiple_portfolios(bus_day, portfolios, wt_flags, recurse=True, deep=True,
                                     benchmark=benchmark, bench_wt_flag=bench_wt_flag)
        s_cov = self.load_covariance(bus_day, pf.columns.to_numpy(), forward_fill_days=forward_fill_days,
                                     calendar_str=calendar_str)
        cov = pd.DataFrame(index=pf.index, columns=pf.index, dtype='float64')

        for ix, x in enumerate(pf.index):
            for iy, y in enumerate(pf.index):
                if iy < ix:
                    continue
                wx = pf.loc[x].to_numpy()
                wy = pf.loc[y].to_numpy()
                cov.iloc[ix, iy] = np.matmul(wx, np.matmul(s_cov, wy.T))
                if ix != iy:
                    cov.iloc[iy, ix] = cov.iloc[ix, iy]
        if correlation_flag:
            return lin.cov_to_corr(cov.astype('float64'))
        return cov

    def load_portfolio_residual_covariance(self, bus_day, portfolios, wt_flags=None,
                                           correlation_flag=False, forward_fill_days=None, calendar_str=None):
        if forward_fill_days is None:
            forward_fill_days = 0
        if calendar_str is None:
            calendar_str = self.calendar
        pf = get_multiple_portfolios(bus_day, portfolios, wt_flags)
        s_cov = self.load_residual_covariance(bus_day, pf.columns.to_numpy(), forward_fill_days=forward_fill_days,
                                              calendar_str=calendar_str, matrix_flag=True)
        ix = np.where(pd.notnull(np.diag(s_cov)))[0]
        cov_mat = np.matmul(pf.iloc[:, ix].to_numpy(), np.matmul(s_cov.iloc[ix, ix].to_numpy(),
                                                                 pf.iloc[:, ix].T.to_numpy()))
        cov = pd.DataFrame(cov_mat, index=pf.index, columns=pf.index)
        if correlation_flag:
            return lin.cov_to_corr(cov.astype('float64'))
        return cov

    def load_stock_portfolio_covariance(self, bus_day, sec_ids, por, wt_flag=None,
                                        correlation_flag=False, forward_fill_days=None, calendar_str=None):
        if wt_flag is None:
            wt_flag = get_default_weighting_method(por)
        if forward_fill_days is None:
            forward_fill_days = 0
        if calendar_str is None:
            calendar_str = self.calendar
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if isinstance(sec_ids, pd.Series):
            sec_ids = sec_ids.to_numpy()
        cov = np.full((len(sec_ids), 1), np.nan)
        pa = get_portfolio_weights(bus_day, bus_day, por, wt_flag)
        all_sec = np.union1d(sec_ids, pa.columns.to_numpy())
        c, i1, i2 = intersect(all_sec, pa.columns.to_numpy())
        wa = np.zeros((len(all_sec), 1))
        wa[i1, 0] = pa[c].to_numpy()

        s_cov = self.load_covariance(bus_day, all_sec)
        for ix, s in enumerate(sec_ids):
            cov[ix] = np.matmul(s_cov.loc[s].to_numpy(), wa)[0]
        if correlation_flag:
            p_vol = np.sqrt(np.matmul(wa.T, np.matmul(s_cov.to_numpy(), wa))[0])
            for ix, s in enumerate(sec_ids):
                s_vol = np.sqrt(s_cov.loc[s, s])
                cov[ix] = cov[ix] / p_vol / s_vol
        return cov

    def load_composite_correlation(self, bus_day, portfolios, wt_flags=None, por_universe=None, forward_fill_days=None,
                                   calendar_str=None):
        if forward_fill_days is None:
            forward_fill_days = 0
        if calendar_str is None:
            calendar_str = self.calendar
        if isinstance(portfolios, str):
            portfolios = np.array([portfolios])
        if portfolios is None:
            portfolios = np.array([])
        if len(portfolios) == 0 and por_universe is not None:
            univ = get_cached_positions(bus_day, bus_day, por_universe, calendar_str)
            portfolios = np.union1d(portfolios, univ.columns.to_numpy())
        pf = get_cached_multiple_portfolios(bus_day, portfolios, wt_flags, recurse=True, deep=True)
        s_cov = self.load_covariance(bus_day, pf.columns.to_numpy(), forward_fill_days=forward_fill_days,
                                     calendar_str=calendar_str)
        corr = pd.DataFrame(index=pf.index, columns=['values', 'volatilities'])
        s_var = np.diag(s_cov)
        s_vol = np.sqrt(s_var)
        for p in pf.index:
            wa = pf.loc[p].to_numpy()
            p_var = np.matmul(wa, np.matmul(s_cov, wa.T))
            s_ws_vol = np.nansum(wa * s_vol)
            s_ws_var = np.nansum(wa * wa * s_var)
            numerator = s_ws_vol * s_ws_vol - s_ws_var
            if numerator != 0:
                corr.loc[p, 'values'] = (p_var - s_ws_var) / numerator
            else:
                print(f"{p}: {bus_day}: {self.name}: correlation numerator equals to zero <--")
            corr.loc[p, 'volatilities'] = np.sqrt(p_var)
        return corr

    def compute_composite_covariance(self, start_date, end_date, save_flag, sec_ids=None,
                                     universe=None, calendar_str=None, forward_fill_days=0):
        if calendar_str is None:
            calendar_str = self.calendar
        bus_days = util.load_business_days(calendar_str, start_date, end_date)
        if len(bus_days) == 0:
            display(f"No valid business days: {self.name} computing covariance: {calendar_str} calendar")
            return None
        location = os.path.join(util.default_output_location('risks'), self.name, 'composites')
        if not util.exists(location):
            util.makedirs(location)
        if sec_ids is None:
            sec_ids = np.array([])
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if len(sec_ids) == 0 and universe is None:
            universe = self.composite_universe
        if universe is not None:
            univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str=calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        wt_flags = None
        zf = pd.DataFrame(index=bus_days, columns=sec_ids)
        for ix, d in enumerate(bus_days):
            try:
                pf = get_cached_multiple_portfolios(d, sec_ids, wt_flags, recurse=True, deep=True)
                s_cov = self.load_covariance(d, pf.columns.to_numpy(), forward_fill_days=forward_fill_days,
                                             calendar_str=calendar_str)
                corr = pd.DataFrame(index=pf.index, columns=['values', 'correlations', 'count', 'valid', 'valid %',
                                                             'invalid', 'invalid %', 'mean', 'median', '10%',
                                                             '20%', '25%', '50%', '75%', '80%', 'min', 'max',
                                                             'std', 'std raw'])
                for p in pf.index:
                    wa = pf.loc[p].to_numpy()
                    p_var = np.matmul(wa, np.matmul(s_cov, wa.T))
                    s_var = np.diag(s_cov)
                    s_vol = np.sqrt(s_var)
                    s_ws_vol = np.nansum(wa * s_vol)
                    s_ws_var = np.nansum(wa * wa * s_var)
                    corr.loc[p, 'correlations'] = (p_var - s_ws_var) / (s_ws_vol * s_ws_vol - s_ws_var)
                    corr.loc[p, 'values'] = p_var
                    corr.loc[p, 'count'] = len(s_vol)
                    corr.loc[p, 'valid'] = pd.notnull(s_vol).sum()
                    corr.loc[p, 'invalid'] = corr.loc[p, 'count'] - corr.loc[p, 'valid']
                    corr.loc[p, 'valid %'] = corr.loc[p, 'valid'] / corr.loc[p, 'count']
                    corr.loc[p, 'invalid %'] = corr.loc[p, 'invalid'] / corr.loc[p, 'count']
                    corr.loc[p, 'median'] = np.nanmedian(s_vol)
                    corr.loc[p, 'mean'] = np.nanmean(s_vol)
                    corr.loc[p, 'min'] = np.nanmin(s_vol)
                    corr.loc[p, 'max'] = np.nanmax(s_vol)
                    corr.loc[p, '10%'] = np.nanpercentile(s_vol, 10)
                    corr.loc[p, '20%'] = np.nanpercentile(s_vol, 20)
                    corr.loc[p, '25%'] = np.nanpercentile(s_vol, 25)
                    corr.loc[p, '50%'] = np.nanpercentile(s_vol, 50)
                    corr.loc[p, '75%'] = np.nanpercentile(s_vol, 75)
                    corr.loc[p, '80%'] = np.nanpercentile(s_vol, 80)
                    corr.loc[p, '90%'] = np.nanpercentile(s_vol, 90)
                    corr.loc[p, 'std'] = np.nanstd(rt.winsorize(s_vol, 10, 90))
                    corr.loc[p, 'std raw'] = np.nanstd(s_vol)

                    zf.loc[d, p] = p_var
                    display(f"{self.name}: {d}: {p}: predicted vol {np.sqrt(corr.loc[p, 'values']):.1%}, correlation "
                            f"{corr.loc[p, 'correlations']:.1%}")
                if save_flag:
                    file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    corr.reset_index(inplace=True)
                    corr.rename(columns={'index': 'sec_ids'}, inplace=True)
                    corr['source'] = 'cosmos'
                    value_keys = np.setdiff1d(corr.columns, ['sec_ids', 'source'])
                    util.merge_and_save_data(file, corr, keys=['sec_ids', 'source'],
                                             value_keys=value_keys, overwrite=True)
                    display(f"{self.name}: {d}: {len(corr.index)} predicted volatilities"
                            f" saved to \n{file}")
            except ValueError as e:
                display(e)
                display(f"{self.name}: {d}: unable to compute covariance")

        return zf

    def load_values(self, value_type, bus_day, sec_ids=None, universe=None,
                    composite_flag=False, forward_fill_days=0, calendar_str=None, matrix_flag=False):
        if calendar_str is None:
            calendar_str = self.calendar
        if not isinstance(calendar_str, str):
            calendar_str = self.calendar
        if value_type is None:
            value_type = 'volatility'
        if not isinstance(value_type, str):
            value_type = 'volatility'
        if sec_ids is None:
            sec_ids = np.array([])
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if len(sec_ids) == 0 and universe is None:
            if composite_flag:
                universe = self.composite_universe
            else:
                universe = self.universe
        if forward_fill_days is None:
            forward_fill_days = 0
        value_type = value_type.strip().lower()
        if value_type in ['vol', 'volatility', 'volatilities']:
            data_type = 'values'
        elif value_type in ['covariance', 'variance', 'value', 'values', 'variances', 'covariances']:
            data_type = 'values'
        elif value_type in ['residual', 'residuals', 'residual risk', 'residual risks',
                            'idiosyncratic', 'idiosyncratic risk']:
            data_type = 'residual'
        elif value_type in ['correlation', 'correlations', 'corr']:
            data_type = 'correlations'
        else:
            data_type = value_type
        days = util.load_business_days(calendar_str, None, bus_day)
        bus_day = days[-1]
        if universe is not None:
            univ = get_cached_positions(bus_day, bus_day, universe, calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        df = pd.DataFrame(index=sec_ids, columns=['values'])
        if composite_flag:
            location = os.path.join(util.default_output_location('risks'), self.name, 'composites')
            for i in range(forward_fill_days+1):
                d = days[-(i+1)]
                file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                if not util.exists(file):
                    continue
                try:
                    data = util.load_data(file)
                    if data_type not in data.columns:
                        display(f"{self.name}: {data_type} ({value_type}) "
                              f"not part to of output on {d}")
                        continue
                    c, i1, i2 = intersect(df.index, data['sec_ids'])
                    df.loc[c] = data[[data_type]].iloc[i2].to_numpy()
                    if value_type in ['vol', 'volatilities', 'vols', 'volatility']:
                        df[['values']] = np.sqrt(df[['values']].to_numpy().astype('float64'))
                except ValueError as e:
                    display(e)
                    display(f"Unable to load {value_type} for {self.name} on {d}")
                    continue
        else:
            if value_type in ['variance', 'covariance', 'volatility', 'vol', 'volatilities', 'variances', 'covariances']:
                cov = self.load_covariance(bus_day, sec_ids)
                c, i1, i2 = intersect(sec_ids, cov.index)
                if matrix_flag:
                    df = pd.DataFrame(index=sec_ids, columns=sec_ids)
                    df.loc[c, c] = cov.loc[c, c]
                else:
                    df.loc[c] = np.diag(cov.loc[c, c].to_numpy()).reshape((len(c), 1))
                    if value_type in ['volatility', 'vol', 'volatilities']:
                        df.loc[c] = np.sqrt(df.loc[c].to_numpy())
            elif value_type in ['residual', 'residuals', 'residual risk', 'residual risks',
                                'idiosyncratic', 'idiosyncratic risk', 'residual volatility',
                                'spec risk', 'specific risk', 'spec risks', 'specific risks',
                                'specific volatility', 'residual volatilities']:
                cov = self.load_residual_covariance(bus_day, sec_ids, matrix_flag=matrix_flag)
                c, i1, i2 = intersect(sec_ids, cov.index)
                if matrix_flag:
                    df = pd.DataFrame(index=sec_ids, columns=sec_ids)
                    df.loc[c, c] = cov.loc[c, c]
                else:
                    df.loc[c] = cov.loc[c].to_numpy()
                    df.loc[c] = np.sqrt(df.loc[c].to_numpy().astype('float64'))
            else:
                if not hasattr(self, 'location'):
                    display(f'no valid location for data {value_type}')
                    return None
                for i in range(forward_fill_days + 1):
                    d = days[-(i + 1)]
                    file = os.path.join(self.location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    if not util.exists(file):
                        continue
                    try:
                        data = util.load_data(file)
                        if data_type not in data.columns:
                            print(f"{util.current_time()}: {self.name}: {data_type} ({value_type}) "
                                  f"not par to of output on {d}")
                            continue
                        c, i1, i2 = intersect(df.index, data['sec_ids'])
                        df.loc[c] = data[[data_type]].iloc[i2].to_numpy()
                        del (c, i1, i2)
                    except ValueError as e:
                        display(e)
                        display(f"Unable to load {value_type} for {self.name} on {d}")
                        continue
        return df

    def snapshot(self, bus_day=None):
        bus_day = util.most_recent_business_day(bus_day, self.calendar)
        fg = root.load_object(self.factor_groups)
        ss = fg.snapshot(bus_day, expand_flag=True)
        ss['models'] = np.repeat(self.name, len(ss['factors']))
        return ss

    def load_related(self, bus_day):
        bus_day = util.most_recent_business_day(bus_day, self.calendar)
        location = self.residual_cov_location
        file = os.path.join(location, f"related.{bus_day.strftime(util.yyyymmdd_format)}.qd")
        if not util.exists(file):
            display(f"{bus_day}: no related residual covariance files; returning None")
            return None
        df = util.load_data(file)
        return df


class Dispersion(root.Factor):
    __slots__ = 'risk_model'

    def __init__(self, name=None,
                 risk_model=None
                 ):
        super().__init__(name)
        self.risk_model = None
        if risk_model is not None:
            if isinstance(risk_model, str):
                self.risk_model = risk_model
            elif isinstance(risk_model, root.Root):
                self.risk_model = risk_model.name

    def compute_descriptors(self, start_date=None, end_date=None, save_flag=False,
                            sec_ids=None, universe=None,
                            calendar_str=None, freq_type=None,
                            fwd_fill_days=None, alt_directory=None, data_freq_type=None):
        if calendar_str is None:
            calendar_str = self.calendar
        if isinstance(sec_ids, (numbers.Number, str)):
            sec_ids = np.array([sec_ids])
        elif isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if isinstance(sec_ids, pd.Series):
            sec_ids = sec_ids.to_numpy()
        if sec_ids is None or not isinstance(sec_ids, np.ndarray):
            sec_ids = np.array([])
        bus_days = util.load_business_days(calendar_str, start_date, end_date, freq_type)
        if len(bus_days) == 0:
            display(f"No valid business days: {self.name}: calendar {calendar_str}")
            return None
        location = self.descriptor_location
        if alt_directory is not None:
            if isinstance(alt_directory, str):
                location = alt_directory
        if not util.exists(location):
            util.makedirs(location)
        risk = root.load_object(self.risk_model)
        if risk is None:
            display(f"No valid risk model configured: {self.name}")
            return None
        if len(sec_ids) == 0 and universe is None:
            universe = self.universe
        if universe is not None:
            univ = get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if len(sec_ids) == 0:
            display(f"No valid portfolios: {self.name}")
            return None
        data = pd.DataFrame(index=bus_days, columns=sec_ids)
        for d in bus_days:
            df = risk.load_composite_correlation(d, sec_ids)
            data.loc[d, df.index] = df['values'].to_numpy().transpose()
            display(f"{self.name}: {d}: max {np.nanmax(df['values']):.1%}  "
                    f"min {np.nanmin(df['values']): .1%}")
            if save_flag:
                file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                ef = df.copy(deep=True)
                ef.reset_index(inplace=True)
                ef.rename(columns={'index' : 'sec_ids'}, inplace=True)
                ef['source'] = 'cosmos'
                util.merge_and_save_data(file, ef, keys=['sec_ids', 'source'],
                                         value_keys=['values', 'volatilities'], overwrite=True)
                display(f"{d}: {self.name}: {len(df.index)} "
                        f"portfolios dispersions saved to \n{file}")
        return data


def dispersion(p_vol, s_vol, wts=None):
    """
    compute dispersion given portfolio level volatility, stock volatility vector and weights
    :param p_vol:
    :param s_vol:
    :param wts:
    :return:
    """
    if isinstance(s_vol, numbers.Number):
        s_vol = np.array([s_vol])
    if isinstance(s_vol, list):
        s_vol = np.array(s_vol)
    if wts is None:
        wts = np.ones((len(s_vol), 1))
    if isinstance(wts, list):
        wts = np.array(wts)
    wts = wts.reshape((len(wts), 1))
    wts = wts / np.nansum(wts)
    s_vol = s_vol.reshape((len(s_vol), 1))
    p_var = p_vol * p_vol
    s_var = s_vol * s_vol
    s_ws_vol = np.nansum(wts * s_vol)
    s_ws_var = np.nansum(wts * wts * s_var)
    d = (p_var - s_ws_var) / (s_ws_vol * s_ws_vol - s_ws_var)
    return d


class DenseRiskModel(RiskModel):
    __slots__ = ('return_loader', 'composite_universe', 'location', 'ts_risk_model',
                 'max_ts_window', 'min_ts_window', 'return_low_bound', 'return_high_bound',
                 'ignore_off_diagonal', 'security_type')

    def __init__(self, name=None,
                 ts_risk_model=None,
                 max_ts_window=None,
                 min_ts_window=None,
                 return_loader=None,
                 location=None,
                 return_low_bound=None,
                 return_high_bound=None,
                 ignore_off_diagonal=True,
                 security_type='EQUITY'
                 ):
        super().__init__(name)
        self.return_loader = md.get_returns
        self.ts_risk_model = 'IG_63_2'
        self.min_ts_window = 21
        self.max_ts_window = 126
        self.composite_universe = None
        self.return_high_bound = 100
        self.return_high_bound = 0
        self.ignore_off_diagonal = True
        self.security_type = 'EQUITY'
        if ts_risk_model is not None:
            self.ts_risk_model = ts_risk_model
        if min_ts_window is not None:
            self.min_ts_window = min_ts_window
        if max_ts_window is not None:
            self.max_ts_window = max_ts_window
        if return_loader is not None:
            self.return_loader = return_loader
        if location is not None:
            self.location = location
        else:
            self.location = os.path.join(util.default_output_location('risks'), self.name, self.ts_risk_model)
        if not util.exists(self.location):
            util.makedirs(self.location)
        if return_high_bound is not None:
            self.return_high_bound = return_high_bound
        if return_low_bound is not None:
            self.return_low_bound = return_low_bound
        if ignore_off_diagonal is not None:
            if isinstance(ignore_off_diagonal, bool):
                self.ignore_off_diagonal = ignore_off_diagonal
        if security_type is not None:
            if isinstance(security_type, str):
                self.security_type = security_type

    def compute_composite_covariance(self, start_date, end_date, save_flag, sec_ids=None,
                                     universe=None, calendar_str=None):
        if calendar_str is None:
            calendar_str = self.calendar
        ts = root.load_object(self.ts_risk_model)
        if ts is None:
            display(f"{self.name}: time series risk model not set")
            return None
        bus_days = util.load_business_days(calendar_str, start_date, end_date)
        if len(bus_days) == 0:
            display(f"No valid business days: {self.name} computing covariance: {calendar_str} calendar")
            return None
        location = os.path.join(util.default_output_location('risks'), self.name, 'composites')
        if not util.exists(location):
            util.makedirs(location)
        if sec_ids is None:
            sec_ids = np.array([])
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if len(sec_ids) == 0 and universe is None:
            universe = self.composite_universe
        if universe is not None:
            univ = port.get_cached_positions(bus_days[0], bus_days[-1], universe, calendar_str=calendar_str)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        all_days = util.load_business_days(calendar_str, None, bus_days[-1])
        ix = np.argmax(all_days >= bus_days[0])
        ret_days = all_days[ix - self.max_ts_window:]
        del ix
        ret = self.return_loader(ret_days[0], ret_days[-1], sec_ids, calendar_str)
        horizon = 1
        zf = pd.DataFrame(index=bus_days, columns=sec_ids)
        ds = pd.DataFrame(index=bus_days, columns=sec_ids)
        sk = pd.DataFrame(index=bus_days, columns=sec_ids)
        kt = pd.DataFrame(index=bus_days, columns=sec_ids)
        for ix, d in enumerate(bus_days):
            try:
                i1 = np.argmax(ret_days >= d)
                index = range(max(0, i1 - self.max_ts_window), i1)
                matrix = ret.iloc[index, :].to_numpy()
                corr = pd.DataFrame(index=sec_ids, columns=['values', 'correlations', 'count', 'valid', 'valid %',
                                                            'invalid', 'invalid %', 'mean', 'median', '10%',
                                                            '20%', '25%', '50%', '75%', '80%', 'min', 'max',
                                                            'std', 'std raw', 'skewness', 'kurtosis', 'source'])
                corr['source'] = 'cosmos'
                for si, s in enumerate(sec_ids):
                    if pd.notnull(matrix[:, si]).sum() < self.min_ts_window:
                        continue
                    so = root.load_object(s)
                    if so.security_type.upper().strip() not in ('EQUITY', 'CURRENCY', 'PORTFOLIO'):
                        continue
                    dev = ts.compute_covariance(rt.winsorize(matrix[:, si], self.return_low_bound,
                                                             self.return_high_bound),
                                                time_horizon=horizon,
                                                min_obs=self.min_ts_window,
                                                overlapping=True)
                    if dev is None:
                        continue
                    zf.loc[d, s] = dev[0, 0]
                    # skewness and kurtosis
                    sk.loc[d, s] = stats.skew(matrix[:, si])
                    kt.loc[d, s] = stats.kurtosis(matrix[:, si])
                    # compute dispersions:
                    wt_flag = get_default_weighting_method(s)
                    try:
                        por = port.get_cached_weights(d, d, s, calendar_str, wt_flag)
                        if por.empty:
                            continue
                    except ValueError as vee:
                        print(vee)
                        print(f"{s}: {d}: holdings failure <===")
                        continue
                    except Exception as xee:
                        print(xee)
                        print(f"{s}: {d}: holdings exception <===")
                        continue
                    p_index = np.where(por.iloc[0, :] != 0)[0]
                    wts = por.iloc[0, p_index].to_numpy()
                    p_sec_ids = por.columns[p_index].to_numpy()
                    var = self.load_covariance(d, p_sec_ids, diagonal_flag=True)
                    s_vol = np.full((len(p_sec_ids), 1), np.nan)
                    cc, k1, k2 = intersect(p_sec_ids, var.index)
                    s_vol[k1] = np.sqrt(var.loc[cc].to_numpy())
                    del (cc, k1, k2)
                    if pd.notnull(s_vol).sum() < 1:
                        print(f"{s}: not sufficient realized vol data")
                        continue
                    ds.loc[d, s] = dispersion(np.sqrt(zf.loc[d, s]), rt.winsorize(s_vol, 0, 95), wts)
                    corr.loc[s, 'correlations'] = ds.loc[d, s]
                    corr.loc[s, 'values'] = zf.loc[d, s]
                    corr.loc[s, 'count'] = len(s_vol)
                    corr.loc[s, 'valid'] = pd.notnull(s_vol).sum()
                    corr.loc[s, 'invalid'] = corr.loc[s, 'count'] - corr.loc[s, 'valid']
                    corr.loc[s, 'valid %'] = corr.loc[s, 'valid'] / corr.loc[s, 'count']
                    corr.loc[s, 'invalid %'] = corr.loc[s, 'invalid'] / corr.loc[s, 'count']
                    corr.loc[s, 'median'] = np.nanmedian(s_vol)
                    corr.loc[s, 'mean'] = np.nanmean(s_vol)
                    corr.loc[s, 'min'] = np.nanmin(s_vol)
                    corr.loc[s, 'max'] = np.nanmax(s_vol)
                    corr.loc[s, '10%'] = np.nanpercentile(s_vol, 10)
                    corr.loc[s, '20%'] = np.nanpercentile(s_vol, 20)
                    corr.loc[s, '25%'] = np.nanpercentile(s_vol, 25)
                    corr.loc[s, '50%'] = np.nanpercentile(s_vol, 50)
                    corr.loc[s, '75%'] = np.nanpercentile(s_vol, 75)
                    corr.loc[s, '80%'] = np.nanpercentile(s_vol, 80)
                    corr.loc[s, '90%'] = np.nanpercentile(s_vol, 90)
                    corr.loc[s, 'std'] = np.nanstd(rt.winsorize(s_vol, 10, 90))
                    corr.loc[s, 'std raw'] = np.nanstd(s_vol)
                    corr.loc[s, 'skewness'] = sk.loc[d, s]
                    corr.loc[s, 'kurtosis'] = kt.loc[d, s]

                    display(f"{self.name}: {d}: {s}: realized vol {np.sqrt(zf.loc[d, s]):.1%}, correlation "
                            f"{ds.loc[d, s]: .1%}, skewness {sk.loc[d, s]:.1f}, kurtosis {kt.loc[d, s]:.1f}")
                if save_flag:
                    file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    corr.reset_index(inplace=True)
                    corr.rename(columns={'index': 'sec_ids'}, inplace=True)
                    value_keys = np.setdiff1d(corr.columns, ['se_ids', 'source'])
                    util.merge_and_save_data(file, corr, keys=['sec_ids', 'source'],
                                             value_keys=value_keys, overwrite=True)
                    display(f"{self.name}: {d}: {len(corr.index)} realized volatilities"
                          f" saved to \n{file}")
            except ValueError as e:
                display(e)
                display(f"{self.name}: {d}: unable to compute covariance")
        return zf

    def load_covariance(self, bus_day, sec_ids, calendar_str=None, fwd_fill_days=2,
                        composite_flag=False, diagonal_flag=False):
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if calendar_str is None:
            calendar_str = self.calendar
        if fwd_fill_days is None:
            fwd_fill_days = 2
        if fwd_fill_days < 0:
            fwd_fill_days = 0
        location = self.location
        if composite_flag:
            location = os.path.join(util.default_output_location('risks'), self.name, 'composites')
        days = util.load_business_days(calendar_str, None, bus_day)
        if not self.ignore_off_diagonal:
            df = pd.DataFrame(index=sec_ids, columns=sec_ids)
            for i in range(fwd_fill_days+1):
                day = days[-(i+1)]
                file = os.path.join(location, f"{day.strftime(util.yyyymmdd_format)}.qd")
                if not util.exists(file):
                    continue
                data = util.load_data(file)
                sids, i1, i2=intersect(data.index, sec_ids)
                df.loc[sids, sids] = data.loc[sids, sids]
                return df
            return None
        vec = np.full((len(sec_ids), 1), np.nan)
        for i in range(fwd_fill_days+1):
            n_index = np.where(pd.isnull(vec))[0]
            n_sec_ids = sec_ids[n_index]
            if len(n_sec_ids) == 0:
                break
            day = days[-(i+1)]
            file = os.path.join(location, f"{day.strftime(util.yyyymmdd_format)}.qd")
            if not util.exists(file):
                display(f"{day}: {file} not found")
                continue
            data = util.load_data(file)
            c, i1, i2 = intersect(n_sec_ids, data['sec_ids'])
            if len(c) == 0:
                continue
            vec[n_index[i1], 0] = data['values'].iloc[i2].to_numpy()
            if pd.isnull(vec).sum() == 0:
                break
        if diagonal_flag:
            return pd.DataFrame(vec, index=sec_ids, columns=['values'])
        else:
            return pd.DataFrame(np.diag(vec[:, 0]), index=sec_ids, columns=sec_ids)

    def load_composite_correlation(self, bus_day, sec_ids, calendar_str=None, fwd_fill_days=2):
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if calendar_str is None:
            calendar_str = self.calendar
        if fwd_fill_days is None:
            fwd_fill_days = 2
        if fwd_fill_days < 0:
            fwd_fill_days = 0
        location = os.path.join(self.location, 'composites')
        days = util.load_business_days(calendar_str, None, bus_day)
        vec = np.full((len(sec_ids), 1), np.nan)
        vol = np.full((len(sec_ids), 1), np.nan)
        for i in range(fwd_fill_days+1):
            n_index = np.where(pd.isnull(vec))[0]
            n_sec_ids = sec_ids[n_index]
            if len(n_sec_ids) == 0:
                break
            day = days[-(i+1)]
            file = os.path.join(location, f"{day.strftime(util.yyyymmdd_format)}.qd")
            if not util.exists(file):
                display(f"{day}: {file} not found")
                continue
            data = util.load_data(file)
            c, i1, i2 = intersect(n_sec_ids, data['sec_ids'])
            if len(c) == 0:
                continue
            vec[n_index[i1], 0] = data['correlations'].iloc[i2].to_numpy()
            vol[n_index[i1], 0] = data['values'].iloc[i2].to_numpy()
            if pd.isnull(vec).sum() == 0:
                break
        df = pd.DataFrame(vec, index=sec_ids, columns=['values'])
        df['volatilities'] = vol
        return df


