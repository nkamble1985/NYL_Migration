#
# portfolio class
#
# Author: Yun Chen
# Copyright: Indigo Dao, LLC
# Date: 2022
#
import datetime
import numbers
import os
import time
import warnings

import numpy as np
import pandas as pd

import classes.root as root
import dataloader.market_data as md
import dataloader.portfolio as port
import util.routines as rt
import util.utilities as util
from util.utilities import display
from util.intersect import *
import analytics.ea.factor_performance as fp


# -------------------------
# portfolio
# -------------------------


class Portfolio(root.Factor):
    __slots__ = ('benchmark', 'weighting_method', 'forward_fill_days', 'frequency',
                 'security_type', 'benchmark_security_type', 'weight_type', 'position_file',
                 'regime_indicator', 'risk_model', 'ir')

    def __init__(self,
                 name=None,
                 benchmark=None,
                 forward_fill_days=0,
                 weighting_method=None):
        super(Portfolio, self).__init__(name=name)
        self.descriptor_location = os.path.join(util.default_output_location('descriptors'), self.name)
        self.weighting_method = 'EQUAL'
        self.benchmark = None
        self.forward_fill_days = 0
        self.frequency = 'DAILY'
        self.security_type = 'EQUITY'
        self.benchmark_security_type = 'FUND'
        self.weight_type = 'SHARE'
        self.position_file = False
        self.regime_indicator = 'ISM'
        self.ir = 2.0

        if benchmark is not None and isinstance(benchmark, str):
            self.benchmark = benchmark.strip()

        if forward_fill_days is not None:
            self.forward_fill_days = forward_fill_days

        if weighting_method is not None and isinstance(weighting_method, str):
            weighting_method = weighting_method.strip()
            if weighting_method.upper() in util.WEIGHTING_SCHEMES:
                self.weighting_method = weighting_method.upper()
            elif weighting_method in util.WEIGHT_FACTORS:
                self.weighting_method = weighting_method
            else:
                warnings.warn(f"{weighting_method} not supported; assuming EQUAL")

    def get_positions(self, start_date, end_date, calendar_str=None, forward_fill_days=None,
                      recurse=None):
        if calendar_str is None:
            calendar_str = self.calendar
        return port.get_cached_positions(start_date, end_date, self.name,
                                         calendar_str=calendar_str,
                                         forward_fill_days=forward_fill_days,
                                         recurse=recurse)

    def get_portfolio_weights(self, start_date, end_date, calendar_str=None, wt_flag=None,
                              forward_fill_days=0, recurse=None):
        if wt_flag is None or not isinstance(wt_flag, bool):
            wt_flag = self.weighting_method
        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar
        bus_days = util.load_business_days(calendar_str, start_date, end_date)
        if len(bus_days) == 0:
            display(f"No valid business day requested for {self.name}: calendar {calendar_str}")
            return None
        s_time = time.time()
        por = self.get_positions(start_date, end_date, calendar_str=calendar_str,
                                 forward_fill_days=forward_fill_days, recurse=recurse)
        r_time = time.time()
        display(f"portfolio {self.name} positions loaded for "
              f"{bus_days[0]} - {bus_days[-1]}: {len(por.index)} X {len(por.columns)} "
              f"in {r_time-s_time: .1f} seconds")
        if hasattr(self, 'weight_type'):
            if self.weight_type.upper().strip() in ['WEIGHT', 'WT', 'WTS', 'WEIGHTS']:
                return por
        if self.security_type in ('PORTFOLIO', 'QSR'):
            composite_flag=True
        else:
            composite_flag=False
        weights = port.calculate_weights(por, wt_flag=wt_flag, calendar_str=calendar_str, composite_flag=composite_flag)
        f_time = time.time()
        display(f"portfolio {self.name} weights computed: "
              f"{bus_days[0]} - {bus_days[-1]}: {len(weights.index)} X {len(weights.columns)} "
              f"in {f_time-r_time: .1f} seconds")
        return weights

    def compute_returns(self, start_date, end_date, save_flag=False, calendar_str=None, wt_flag=None,
                        weight_forward_fill_days=0, base_currency=None):
        """
        compute returns (in base currency) and report in any currency
        :param start_date:
        :param end_date:
        :param save_flag:
        :param calendar_str: default portfolio's calendar
        :param wt_flag:
        :param weight_forward_fill_days:
        :param base_currency: default portfolio's default base currency
        :return:
        """
        if wt_flag is None or not isinstance(wt_flag, str):
            wt_flag = self.weighting_method
        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar
        if base_currency is None or not isinstance(base_currency, str):
            base_currency = self.base_currency
            if base_currency is None:
                base_currency = 'USD'
                display(f" {self.name}: {util.caller()}: "
                        f" no default currency: {base_currency} assumed")
        normalize = True
        if hasattr(self, 'normalize') and isinstance(self.normalize, bool):
            normalize = self.normalize
        bus_days = util.load_business_days(calendar_str, start_date, end_date)
        por_days = util.previous_business_days(bus_days, calendar_code=calendar_str)
        por = self.get_portfolio_weights(por_days[0], por_days[-1], calendar_str=calendar_str,
                                         wt_flag=wt_flag, forward_fill_days=weight_forward_fill_days)
        r_time = time.time()
        ret, local, xf = md.get_returns(bus_days[0], bus_days[-1], por.columns.to_numpy(), calendar_str=calendar_str,
                                        base_currency=self.base_currency)
        s_time = time.time()
        display(f"{self.name} returns for {bus_days[0]} - {bus_days[-1]}: "
              f"{len(ret.index)} X {len(ret.columns)} returns loaded in"
              f" {s_time-r_time: .1f} seconds")
        result = port.w_prime_r(por, ret, calendar_str, normalize)
        result = result.to_frame(self.name)
        if hasattr(self, 'benchmark') and self.benchmark is not None:
            b_ret, local, xb = md.get_returns(bus_days[0], bus_days[-1], self.benchmark, calendar_str,
                                              base_currency=base_currency)
            result[self.benchmark] = b_ret.loc[result.index]
            result['active'] = result[self.name] - result[self.benchmark]
        if save_flag:
            directory = util.return_location()
            if not util.exists(directory):
                util.makedirs(directory)
            success = True
            for idx, d in enumerate(result.index):
                try:
                    df = pd.DataFrame(index=[d], columns=['sec_ids', 'values', 'currency', 'source'])
                    df['sec_ids'] = self.name.strip()
                    df['currency'] = self.base_currency
                    if isinstance(result, pd.DataFrame):
                        df['values'] = [result[self.name].iloc[idx]]
                    else:
                        success = False
                        display(f'{self.name}: failed to save on {d}: unrecognized result type')
                        continue
                    df['source'] = [self.source]
                    file = os.path.join(directory, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    util.merge_and_save_data(file, df, keys=['sec_ids', 'currency', 'source'], overwrite=True)
                    del df
                except ValueError:
                    display(ValueError)
                    success = False
                except Exception as e:
                    display(e)
                    display(f"Unable to save return results for {self.name} on {d}")
                    success = False
            if success:
                display(f"{self.name}: return results ({self.base_currency}) successfully saved between "
                      f"{bus_days[0]} and {bus_days[-1]}")
            else:
                display(f"{self.name}: partially or in whole saving return ({self.base_currency}) results between "
                      f"{bus_days[0]} and {bus_days[-1]} failed")
        if base_currency != self.base_currency:
            x = md.get_exchange_rate_returns(bus_days[0], bus_days[-1], self.base_currency, base_currency, calendar_str)
            xf = pd.DataFrame(x.to_numpy(), index=result.index, columns=[self.name])
            result[[self.name]] = (1 + result[[self.name]])*(1 + xf) - 1
            if 'active' in result.columns:
                result['active'] = result[self.name] - result[self.benchmark]
        return result

    def get_returns(self, start_date=None, end_date=None, calendar_str=None, source=None, active_flag=True,
                    base_currency=None):
        """

        :param start_date:
        :param end_date:
        :param calendar_str:
        :param source:
        :param active_flag: True
        :param base_currency: None
        :return:
        """
        if calendar_str is None:
            calendar_str = self.calendar
        if base_currency is None or not isinstance(base_currency, str):
            base_currency = self.base_currency
        bus_days = util.load_business_days(calendar_str, start_date, end_date)
        directory = util.return_location()
        df = pd.DataFrame(np.NAN, index=bus_days, columns=[self.name])
        if len(bus_days) == 0:
            return df
        if source is None:
            source = self.source
        for d in bus_days:
            d_str = d.strftime(util.YY_MM_DD_format)
            try:
                file = os.path.join(directory, f"{d.strftime(util.yyyymmdd_format)}.qd")
                if not util.exists(file):
                    display(f"Unable to find return file: {d_str}")
                    continue
                data = util.load_data(file)
                index = np.where(np.logical_and(data['sec_ids'] == self.name, data['source'] == source,
                                                data['currency'] == self.base_currency))[0]
                if len(index) == 0:
                    display(f"{d_str}: no returns found for {self.name}")
                    continue
                df.loc[d] = data['values'].iloc[index[0]]
            except ValueError:
                display(ValueError)
                display(f"{d_str}")
                continue
        if base_currency != self.base_currency:
            x = md.get_exchange_rate_returns(bus_days[0], bus_days[-1], self.base_currency, base_currency, calendar_str)
            xf = pd.DataFrame(x.to_numpy(), index=x.index, columns=df.columns)
            df = (1 + df)*(1 + xf) - 1

        if active_flag and self.benchmark is not None:
            b_ret, local, xb = md.get_returns(bus_days[0], bus_days[-1], self.benchmark,
                                              calendar_str, base_currency=base_currency)
            df[self.benchmark] = b_ret.loc[df.index].to_numpy()
            df['active'] = df[self.name] - df[self.benchmark]

        return df

    def propagate_positions(self, bus_day, start_date=None, end_date=None, save_flag=False, overwrite_flag=False,
                            normalize=None, calendar_str=None):
        if self.weight_type not in ['WEIGHT', 'WEIGHTS', 'WT', 'WTS']:
            display(f"Unsupported weight type: {self.weight_type} as of now")
            return None
        if hasattr(self, 'normalize') and isinstance(self.normalize, bool):
            normalize = self.normalize
        if normalize is None or not isinstance(self.normalize, bool):
            normalize = True
        if calendar_str is None:
            calendar_str = self.calendar
        bus_days = util.load_business_days(calendar_str, None, bus_day)
        bus_day = bus_days[-1]
        if start_date is None:
            start_date = bus_day
        if end_date is None:
            reb_days = util.load_business_days(calendar_str, bus_day, None, self.descriptor_frequency)
            reb_days = reb_days[reb_days > bus_day]
            end_date = util.load_business_days(calendar_str, None, reb_days[0])
            end_date = end_date[end_date<reb_days[0]]
            end_date = end_date[-1]
        dates = util.load_business_days(calendar_str, start_date, end_date)
        dates = dates[dates > bus_day]
        if len(dates) == 0:
            display(f"Not enough future date to propagate to")
            return None
        display(f"{self.name}: {bus_day} propagated to: {dates[0]} - {dates[-1]}")
        p = self.get_positions(bus_day, bus_day)
        por = port.propagate_positions(p, dates, self.weight_type, security_type=self.security_type,
                                       calendar_str=calendar_str, normalize=normalize)
        if por is None:
            return por
        if len(por.index) == 0:
            return por
        for ni, nd in enumerate(por.index):
            try:
                pos = pd.DataFrame(columns=['sec_ids', 'values', 'source'])
                pos['sec_ids'] = por.columns.to_numpy()
                pos['values'] = por.loc[nd].to_numpy()
                pos['source'] = 'QSR'
                pos_file = os.path.join(self.descriptor_location, f"{nd.strftime(util.yyyymmdd_format)}.qd")
                if util.exists(pos_file):
                    display(f"pre-existing: {pos_file}")
                    if overwrite_flag:
                        display(f"Overwriting...")
                    else:
                        display('skipping...')
                        continue
                util.save_data(pos, pos_file)
                display(f"{self.name}: {bus_day} propagated to {nd}")
            except ValueError as ve:
                display(ve)
        return por

    def compute_turnover(self, start_date, end_date, save_flag=False, calendar_str=None, recurse=False,
                         deep=False):
        """

        :param start_date:
        :param end_date:
        :param save_flag:
        :param calendar_str:
        :param recurse:
        :param deep:
        :return:
        """
        if calendar_str is None:
            calendar_str = self.calendar
        if hasattr(self, 'rebalance_frequency'):
            freq = self.rebalance_frequency
        else:
            freq = self.descriptor_frequency
        bus_days = util.load_business_days(calendar_str, start_date, end_date, freq)
        if len(bus_days) == 0:
            display(f"No rebalance dates in between: {self.name}: compute_turnover")
            return False
        if not util.exists(self.descriptor_location):
            util.makedirs(self.descriptor_location)
            display(f"Successfully created: {self.descriptor_location}")
        file = os.path.join(self.descriptor_location, 'turnover.qd')
        if not util.exists(file):
            df = pd.DataFrame(0.0, index=bus_days, columns=['values'])
        else:
            df = util.load_data(file)
        for d in bus_days:
            try:
                prev_d = util.previous_day(d, calendar_str, freq)
                to = port.get_turnover(prev_d, d, self.name, calendar_str, security_type=self.security_type,
                                       recurse=recurse, deep=deep)
                if to.empty:
                    display(f" {self.name}: {prev_d} - {d} failed to compute turnover; skipping ")
                    continue
                df.loc[d, 'values'] = to.loc[d, 'values']
                display(f" {self.name}: {prev_d} - {d} turnover {to.loc[d, 'values']*100: .1f} %")
            except Exception as ee:
                display(ee)
                display(f" {self.name}: {d}: cannot compute turnover")
        df.sort_index(inplace=True)
        if save_flag:
            util.save_data(df, file)
        c, i1, i2 = intersect(df.index.to_numpy(), bus_days)
        average = np.nanmean(df.loc[c, 'values'].to_numpy())
        total = np.nansum(df.loc[c, 'values'].to_numpy())
        display(f" {self.name}: {bus_days[0]} - "
              f"{bus_days[-1]} (round-trip turnover) average: {average*100: .1f} % ||"
              f"Total: {total*100: .1f} %"
              f"\n{file}")
        return df

    def load_turnover(self, start_date=None, end_date=None, calendar_str=None):
        if calendar_str is None:
            calendar_str = self.calendar
        if hasattr(self, 'rebalance_frequency'):
            freq = self.rebalance_frequency
        else:
            freq = self.descriptor_frequency
        bus_days = util.load_business_days(calendar_str, start_date, end_date, freq)
        file = os.path.join(self.descriptor_location, 'turnover.qd')
        if not util.exists(file):
            display(f"No Turnover found: NOT FOUND\n{file}")
            return None
        else:
            df = util.load_data(file)
        if len(bus_days) > 0:
            index = np.where(np.logical_and(df.index>= bus_days[0], df.index <= bus_days[-1]))[0]
            df = df.iloc[index]
        return df

    def get_regime_location(self, indicator=None):
        if indicator is None:
            indicator = self.regime_indicator
        return os.path.join(self.descriptor_location, 'regime', f"{indicator}")

    def compute_regime(self, start_date, end_date, save_flag=False, indicator=None):
        location = self.get_regime_location(indicator)
        if save_flag:
            if not util.exists(location):
                util.makedirs(location)
                display(f"{self.name}: regime location: {location}")
        bus_days = util.load_business_days(self.calendar, start_date, end_date)
        if len(bus_days) == 0:
            display(f"No valid business days: {self.calendar}: {self.name}: regime")
            return False
        all_days = util.load_business_days(self.calendar, self.life.from_dt, end_date)
        univ = port.get_cached_positions(bus_days[0], bus_days[-1], self.name)
        if hasattr(self, 'benchmark'):
            if self.benchmark is not None:
                display('-' * 70)
                display(f"{self.name}: loading {len(all_days)}-day {self.benchmark} returns from "
                      f"{all_days[0]} - {all_days[-1]}")
                br = md.get_returns(all_days[0], all_days[-1], self.benchmark, self.calendar,
                                    security_type=self.benchmark_security_type)
                display('-' * 70)
                display(f"{self.name}: loaded {len(all_days)} {self.benchmark} returns from "
                      f"{all_days[0]} - {all_days[-1]}")
                display('-' * 70)
            else:
                br = None
        else:
            br = None
        sec_ids = univ.columns.to_numpy()
        display('-'*70)
        display(f"{self.name}: loading {len(all_days)}-day {len(sec_ids)} assets returns from "
              f"{all_days[0]} - {all_days[-1]}")
        r = md.get_returns(all_days[0], all_days[-1], sec_ids, self.calendar, security_type=self.security_type)
        display('-'*70)
        display(f"{self.name}: loaded {len(all_days)} X {len(sec_ids)} returns from "
              f"{all_days[0]} - {all_days[-1]}")
        display('-'*70)
        for d in bus_days:
            ix = np.where(r.index == d)[0][0]
            p_days = r.index[:ix+1].to_numpy()
            ids = univ.columns[np.where(univ.loc[d] != 0)[0]].to_numpy()
            ids = r.columns.intersection(ids)
            if br is not None:
                ben = br.loc[p_days]
            else:
                ben = None
            try:
                stat = fp.return_statistics(r.loc[p_days, ids], ben, indicator=indicator)
                if save_flag:
                    file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    try:
                        util.save_data(stat, file)
                        display(f"{self.name}: regime: {d}: saved to\n{file}")
                    except IOError as ie:
                        display(ie)
                        display(f"{self.name}: {d}: unable to save")
            except ValueError as ve:
                display(ve)
                display(f"{self.name}: {d}: regime: unable to compute statistics")
            except Exception as ee:
                display(ee)
                display(f"{self.name}: {d}: regime: unable to compute statistics")

    def load_regimes(self, start_date, end_date, freq=None):
        if freq is None:
            freq = 'DAILY'
        all_regimes = md.get_ism_regimes(start_date, end_date, self.calendar, freq)
        return all_regimes

    def load_regime_stat(self, bus_day, portfolio=None, field=None):
        bus_day = util.most_recent_business_day(bus_day, self.calendar)
        file = os.path.join(self.get_regime_location(), f"{bus_day.strftime(util.yyyymmdd_format)}.qd")
        if not util.exists(file):
            display(f"{self.name}: regime statistics: {bus_day}: file not found: \n{file}")
            return None
        data = util.load_data(file)
        if portfolio is None:
            return data
        portfolio = portfolio.lower().strip()
        if portfolio not in ('managed', 'benchmark', 'active'):
            return data
        data = data[portfolio]
        if field is None:
            return data
        if field not in data.keys():
            return data
        return data[field]

    def load_regime_ir(self, bus_day, strategies=None):
        bus_day = util.most_recent_business_day(bus_day, self.calendar)
        data = self.load_regime_stat(bus_day, 'active', 'regime information ratios')
        regimes = self.load_regimes(bus_day, bus_day)
        rv = regimes.loc[bus_day, 'values']
        data = data.loc[int(rv)]
        if strategies is None:
            return data
        else:
            if isinstance(strategies, str):
                strategies = np.array([strategies])
            elif isinstance(strategies, list):
                strategies = np.array(strategies)
            df = pd.Series(np.nan, index=strategies)
            s = df.index.intersection(data.index)
            df.loc[s] = data.loc[s]
            return df

    def load_regime_vol(self, bus_day, strategies=None):
        bus_day = util.most_recent_business_day(bus_day, self.calendar)
        data = self.load_regime_stat(bus_day, 'active', 'regime volatilities')
        regimes = self.load_regimes(bus_day, bus_day)
        rv = regimes.loc[bus_day, 'values']
        data = data.loc[int(rv)]
        if strategies is None:
            return data
        else:
            if isinstance(strategies, str):
                strategies = np.array([strategies])
            elif isinstance(strategies, list):
                strategies = np.array(strategies)
            df = pd.Series(np.nan, index=strategies)
            s = df.index.intersection(data.index)
            df.loc[s] = data.loc[s]
            return df

    def load_regime_alpha(self, bus_day, strategies=None):
        bus_day = util.most_recent_business_day(bus_day, self.calendar)
        data = self.load_regime_stat(bus_day, 'active', 'regime returns')
        if data is None:
            return None
        regimes = self.load_regimes(bus_day, bus_day)
        rv = regimes.loc[bus_day, 'values']
        data = data.loc[int(rv)]
        if strategies is None:
            return data
        else:
            if isinstance(strategies, str):
                strategies = np.array([strategies])
            elif isinstance(strategies, list):
                strategies = np.array(strategies)
            df = pd.Series(np.nan, index=strategies)
            s = df.index.intersection(data.index)
            df.loc[s] = data.loc[s]
            return df

    def compute_alphas(self, start_date, end_date, save_flag=False, freq=None):
        if freq is None:
            freq = self.descriptor_frequency
        days = util.load_business_days(self.calendar, start_date, end_date, freq)
        rm = root.load_object(self.risk_model)
        location = os.path.join(self.descriptor_location, 'alphas')
        if save_flag:
            if not util.exists(location):
                util.makedirs(location)
                display(f"{self.name}: created {location}")
        vol_target = 0.01
        if hasattr(self, 'ir'):
            ir = self.ir
        else:
            ir = 2.0
        df = pd.DataFrame()
        for d in days:
            try:
                p = port.get_portfolio_weights(d, d, self.name, recurse=True, deep=True)
                sec_ids = p.columns.to_numpy()
                cov = rm.load_covariance(d, sec_ids)
                good_index = np.where(pd.notnull(np.diag(cov.to_numpy())))[0]
                cov = cov.iloc[good_index, good_index]
                ids = cov.index.intersection(sec_ids)
                sigma = np.matmul(p.loc[d, ids].to_numpy(), np.matmul(cov.loc[ids, ids].to_numpy(),
                                                                      p.loc[d, ids].to_numpy().T))
                sigma = np.sqrt(sigma)
                vf = vol_target / sigma
                w = p.loc[d, ids].to_numpy().T * vf
                alphas = np.matmul(cov.loc[ids, ids].to_numpy(), w)
                multiplier = ir / vol_target
                if multiplier is not None:
                    alphas = multiplier * alphas
                vols = np.sqrt(np.diag(cov.loc[ids, ids].to_numpy()))
                irs = alphas / vols
                af = pd.DataFrame(alphas, columns=[d], index=ids).T
                df = df.combine_first(af)
                if save_flag:
                    data = pd.DataFrame(alphas, columns=['values'])
                    data['ir'] = irs
                    data['vol'] = vols
                    data['sec_ids'] = ids
                    data['source'] = self.source
                    file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    try:
                        util.save_data(data, file)
                        display(f"{self.name}: {d}: {len(alphas)} alphas saved to \n{file}")
                    except ValueError as ve:
                        display(ve)
                        display(f"{self.name}: {d}: cannot save alphas")
                    except Exception as ee:
                        display(ee)
                        display(f"{self.name}: {d}: cannot save alphas")
            except ValueError as ve:
                display(ve)
                display(f"{self.name}: {d}: unable to compute alphas")
            except Exception as ee:
                display(ee)
                display(f"{self.name}: {d}: unable to compute alphas")
        return df

    def load_alphas(self, start_date, end_date, sec_ids=None, universe=None, freq=None):
        location = os.path.join(self.descriptor_location, 'alphas')
        if not util.exists(location):
            display(f"{self.name} No valid location found: {location}")
            return None
        if freq is None:
            freq = 'DAILY'
        bus_days = util.load_business_days(self.calendar, start_date, end_date, freq)
        if len(bus_days) == 0:
            display(f"{self.name}: {self.calendar} no valid business days")
            return None
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None:
            sec_ids = np.array([])
        if universe is not None:
            univ = port.get_cached_positions(start_date, end_date, universe)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if len(sec_ids) == 0:
            display(f"{self.name}: no valid securities or universe")
        df = pd.DataFrame(np.nan, index=bus_days, columns=sec_ids)
        for d in bus_days:
            file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
            try:
                data = util.load_data(file)
                data.set_index('sec_ids', inplace=True)
                ids = data.index.intersection(df.columns)
                tf = pd.DataFrame(data.loc[ids, 'values'].to_numpy(), columns=[d], index=ids).T
                df = df.combine_first(tf)
            except ValueError as ve:
                display(ve)
                display(f"{self.name}: {d}: value error")
            except Exception as ee:
                display(ee)
                display(f"{self.name}: {d}: exception: unable to load alpha")
        return df

    def load_irs(self, start_date, end_date, sec_ids=None, universe=None, freq=None):
        location = os.path.join(self.descriptor_location, 'alphas')
        if not util.exists(location):
            display(f"{self.name} No valid location found: {location}")
            return None
        if freq is None:
            freq = 'DAILY'
        bus_days = util.load_business_days(self.calendar, start_date, end_date, freq)
        if len(bus_days) == 0:
            display(f"{self.name}: {self.calendar} no valid business days")
            return None
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None:
            sec_ids = np.array([])
        if universe is not None:
            univ = port.get_cached_positions(start_date, end_date, universe)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if len(sec_ids) == 0:
            display(f"{self.name}: no valid securities or universe")
        df = pd.DataFrame(np.nan, index=bus_days, columns=sec_ids)
        for d in bus_days:
            file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
            try:
                data = util.load_data(file)
                data.set_index('sec_ids', inplace=True)
                ids = data.index.intersection(df.columns)
                tf = pd.DataFrame(data.loc[ids, 'ir'].to_numpy(), columns=[d], index=ids).T
                df = df.combine_first(tf)
            except ValueError as ve:
                display(ve)
                display(f"{self.name}: {d}: value error")
            except Exception as ee:
                display(ee)
                display(f"{self.name}: {d}: exception: unable to load alpha")
        return df

    def load_vols(self, start_date, end_date, sec_ids=None, universe=None, freq=None):
        location = os.path.join(self.descriptor_location, 'alphas')
        if not util.exists(location):
            display(f"{self.name} No valid location found: {location}")
            return None
        if freq is None:
            freq = 'DAILY'
        bus_days = util.load_business_days(self.calendar, start_date, end_date, freq)
        if len(bus_days) == 0:
            display(f"{self.name}: {self.calendar} no valid business days")
            return None
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        if isinstance(sec_ids, list):
            sec_ids = np.array(sec_ids)
        if sec_ids is None:
            sec_ids = np.array([])
        if universe is not None:
            univ = port.get_cached_positions(start_date, end_date, universe)
            sec_ids = np.union1d(sec_ids, univ.columns.to_numpy())
        if len(sec_ids) == 0:
            display(f"{self.name}: no valid securities or universe")
        df = pd.DataFrame(np.nan, index=bus_days, columns=sec_ids)
        for d in bus_days:
            file = os.path.join(location, f"{d.strftime(util.yyyymmdd_format)}.qd")
            try:
                data = util.load_data(file)
                data.set_index('sec_ids', inplace=True)
                ids = data.index.intersection(df.columns)
                tf = pd.DataFrame(data.loc[ids, 'vol'].to_numpy(), columns=[d], index=ids).T
                df = df.combine_first(tf)
            except ValueError as ve:
                display(ve)
                display(f"{self.name}: {d}: value error")
            except Exception as ee:
                display(ee)
                display(f"{self.name}: {d}: exception: unable to load alpha")
        return df

    def load_values(self, value_type='EXPOSURE', start_date=None, end_date=None,
                    sec_ids=None, universe=None, calendar_str=None, freq_type=None,
                    fwd_fill_days=None, alt_directory=None, data_freq_type=None,
                    composite_flag=False, exposure_value_type=None, exposure_fill_value=0):
        if value_type.lower().strip() in ('alpha', 'alphas'):
            return self.load_alphas(start_date, end_date, sec_ids, universe, freq_type)
        if value_type.lower().strip() in ('ir', 'irs', 'information ratio', 'information ratios'):
            return self.load_irs(start_date, end_date, sec_ids, universe, freq_type)
        if value_type.lower().strip() in ('vol', 'vols', 'volatility', 'volatilities'):
            return self.load_vols(start_date, end_date, sec_ids, universe, freq_type)
        return root.Factor.load_values(self, value_type, start_date, end_date, sec_ids, universe,
                                       calendar_str, freq_type, fwd_fill_days, alt_directory,
                                       data_freq_type, composite_flag, exposure_fill_value, exposure_fill_value)


class DerivedPortfolio(Portfolio):
    __slots__ = ('factor_frequencies', 'universe_include')

    def __init__(self,
                 name=None,
                 portfolios=None,
                 lives=None,
                 include=None,
                 weighting_method=None):
        super(DerivedPortfolio, self).__init__(name=name)
        self.descriptor_location = os.path.join(util.default_output_location('descriptors'), self.name)
        self.weighting_method = 'EQUAL'

        if portfolios is not None and isinstance(portfolios, (list, np.ndarray)):
            self.factors = portfolios
            self.factor_types = np.array(['PORTFOLIO'] * len(portfolios))
            self.factor_lives = np.array([root.Life(19000101, 99991231)] * len(portfolios))
            self.factor_include = [True] * len(portfolios)

        if lives is not None and isinstance(lives, (list, np.ndarray)):
            self.factor_lives = lives

        if include is not None and isinstance(include, (list, np.ndarray)):
            self.factor_include = include

        if weighting_method is not None and isinstance(weighting_method, str):
            weighting_method = weighting_method.strip()
            if weighting_method.upper() in util.WEIGHTING_SCHEMES:
                self.weighting_method = weighting_method.upper()
            elif weighting_method in util.WEIGHT_FACTORS:
                self.weighting_method = weighting_method
            else:
                warnings.warn(f"{weighting_method} not supported; assuming EQUAL")

    def compute_descriptors(self, start_date, end_date, calendar_str=None,
                            forward_fill_days=None, save_flag=False,
                            recurse=False):

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if forward_fill_days is None or not isinstance(forward_fill_days, bool):
            forward_fill_days = 0

        if recurse is None or not isinstance(recurse, bool):
            recurse = False
        days = util.load_business_days(calendar_str, start_date, end_date)

        if not days or np.size(days) == 0:
            warnings.warn('No business days found according to %s calendar' % calendar_str)
            return None

        num_of_por = len(self.factors)
        positions = np.array([None] * num_of_por)
        portfolios = self.factors
        include = self.universe_include
        lives = self.factor_lives
        frequencies = self.factor_frequencies
        for i in range(num_of_por):
            try:
                positions[i] = port.get_cached_positions(days[0], days[-1], portfolios[i], calendar_str, frequencies[i],
                                                  forward_fill_days, recurse)
            except ValueError:
                warnings.warn(f'Unable to load portfolio {portfolios[i]}')

        df = pd.DataFrame(index=days)
        for d in days:
            try:
                index = np.where(rt.within_range(d, lives))[0]
                if len(index) == 0:
                    warnings.warn('%s: no constituent universe' % d.strftime('%Y%m%d'))
                    continue
                sec_ids = np.array([])
                for k in range(len(index)):
                    v = positions[index[k]]
                    if v.empty:
                        continue
                    v_sec_ids = v.columns[np.where(v.loc[d] != 0)[0]].to_numpy()
                    if len(v_sec_ids) == 0:
                        warnings.warn('%s:%s missing positions' % (d.strftime('%Y%m%d'), positions[index[k]]))
                        continue
                    if include[index[k]]:
                        sec_ids = np.union1d(sec_ids, v_sec_ids)
                    else:
                        sec_ids = np.setdiff1d(sec_ids, v_sec_ids)
                new_sec = sec_ids[~np.isin(sec_ids, df.columns)]
                if len(new_sec) != 0:
                    df[new_sec] = 0
                all_sec_ids = df.columns.to_numpy()
                vec = np.zeros((len(all_sec_ids), 1))
                vec[np.isin(all_sec_ids, sec_ids)] = 1
                df.loc[d] = vec.transpose()
                if save_flag:
                    file = os.path.join(self.descriptor_location, f"{d.strftime(util.yyyymmdd_format)}.qd")
                    zf = pd.DataFrame()
                    zf['sec_ids'] = sec_ids
                    zf['values'] = 1
                    zf['source'] = 'QSR'
                    util.save_data(zf, file)
                    display(f"{self.name}: {d.strftime(util.MM_DD_YY_format)}: {len(sec_ids)} holdings saved")
            except ValueError:
                warnings.warn(f'Unable to join universes on {d.strftime(util.YY_MM_DD_format)}')
                continue
        return df


class FilteredPortfolio(Portfolio):
    __slots__ = ('factor_universes', 'filters', 'exclusion_universes', 'composite_flag')

    def __init__(self,
                 name=None,
                 factors=None,
                 lives=None):
        super(FilteredPortfolio, self).__init__(name=name)
        self.descriptor_location = os.path.join(util.default_output_location('descriptors'), self.name)
        self.factor_universes = None
        self.exclusion_universes = None
        self.composite_flag = False
        if factors is not None and isinstance(factors, (list, np.ndarray)):
            self.factors = factors
            self.factor_types = np.array(['DESCRIPTOR'] * len(factors))
            self.factor_lives = np.array([root.Life(19000101, 99991231)] * len(factors))
            self.factor_universes = [None] * len(factors)

        if lives is not None and isinstance(lives, (list, np.ndarray)):
            self.factor_lives = lives

    def get_positions(self, start_date, end_date, calendar_str=None, forward_fill_days=0,
                      recurse=None):

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if forward_fill_days is None or not isinstance(forward_fill_days, numbers.Number):
            forward_fill_days = self.forward_fill_days

        if recurse is None or not isinstance(recurse, bool):
            recurse = False

        days = util.load_business_days(calendar_str, start_date, end_date)
        if len(days) == 0:
            display(f"No valid business days: {self.name}")
            return None
        composite_flag = False
        if hasattr(self, 'composite_flag'):
            composite_flag = self.composite_flag
        factors = self.factors
        value_types = self.factor_types
        universes = self.factor_universes
        if universes is None:
            universes = [self.universe] * len(factors)
        filters = self.filters
        lives = self.factor_lives

        for i in range(len(value_types)):
            if value_types[i] is None:
                value_types[i] = 'DESCRIPTOR'
        for i in range(len(universes)):
            if universes[i] is None:
                universes[i] = self.universe
        data_dates = util.load_business_days(calendar_str, None, days[-1], self.descriptor_frequency)
        if days[0] in data_dates:
            data_dates = data_dates[data_dates >= days[0]]
        else:
            data_dates = data_dates[np.argmax(data_dates > days[0]) - 1:]

        # pre-load universes
        positions = [None] * len(factors)
        all_sec_ids = np.array([])
        exclusion_universes = self.exclusion_universes
        if isinstance(exclusion_universes, str):
            exclusion_universes = np.array([exclusion_universes])
        if isinstance(exclusion_universes, list):
            exclusion_universes = np.array(exclusion_universes)
        for i in range(len(universes)):
            if universes[i] is None:
                continue
            try:
                positions[i] = port.get_cached_positions(data_dates[0], data_dates[-1], universes[i],
                                                         calendar_str, forward_fill_days=forward_fill_days,
                                                         recurse=recurse)
                all_sec_ids = np.union1d(all_sec_ids, positions[i].columns.to_numpy())
            except ValueError:
                warnings.warn('Unable to load portfolio %s' % universes[i])
        df = pd.DataFrame(0, index=days, columns=all_sec_ids)
        for i, d in enumerate(data_dates):
            valid_days = days[days >= d]
            if i < len(data_dates) - 1:
                valid_days = valid_days[valid_days < data_dates[i + 1]]
            try:
                sec_ids = [None] * len(factors)
                # included = [False] * len(factors)
                included = np.array([])
                for k, fac in enumerate(factors):
                    try:
                        if not rt.within_range(d, lives[k]):
                            continue
                        por = positions[k]
                        k_sec_ids = por.columns[np.where(por.loc[d] != 0)[0]].to_numpy()
                        f_obj = root.load_object(fac)
                        if value_types[k].strip().upper() == 'EXPOSURE':
                            val = f_obj.load_exposures(d, k_sec_ids)
                            val = val.transpose()
                        elif value_types[k].strip().upper() in ['PORTFOLIO', 'UNIVERSE']:
                            val = port.get_cached_positions(d, d, fac, calendar_str)
                        else:
                            val = f_obj.load_values(value_types[k], d, d, k_sec_ids, composite_flag=composite_flag)
                        if val is None:
                            continue
                        if val.empty:
                            continue
                        val = val.astype('float64')
                        val = val[~np.isnan(val)]
                        try:
                            if callable(filters[k]):
                                sec_ids[k] = val.columns[np.where(filters[k](val))[1]].to_numpy()
                            elif isinstance(filters[k], str):
                                sec_ids[k] = val.columns[np.where(eval(filters[k]))[1]].to_numpy()
                            else:
                                sec_ids[k] = val.columns.to_numpy()
                            if k == 0:
                                included = sec_ids[k]
                            else:
                                included = np.intersect1d(included, sec_ids[k])
                            del (val, por, k_sec_ids)
                        except Exception as e:
                            display(e)
                            display(f"Unable to filter universe by {fac}")
                            continue
                    except ValueError as ve:
                        display(ve)
                        warnings.warn('Unable to filter %d on %s' % (k, d.strftime('%Y%m%d')))
                        continue
                if exclusion_universes is not None:
                    excluded = np.array([])
                    for eu in exclusion_universes:
                        try:
                            ex_u = port.get_cached_positions(d, d, eu, calendar_str)
                            if ex_u is not None:
                                if not ex_u.empty:
                                    excluded = np.union1d(excluded, ex_u.columns.to_numpy())
                        except ValueError as e:
                            display(e)
                            display(f" {self.name}: {d}: unable to exclude universe: {eu}")
                    if len(excluded) > 0:
                        included = np.setdiff1d(included, excluded)
                        display(f'{self.name}: {d}:{len(excluded)} stocks excluded: {len(included)} remained')
                df.loc[valid_days, df.columns.isin(included)] = 1
            except ValueError:
                warnings.warn('Unable to join universes on %s' % d.strftime('%Y%m%d'))
                continue
        # exclude zeros
        df = df[df.columns[np.where(df.sum(axis=0) > 0)]]
        return df


class UnionPortfolio(FilteredPortfolio):

    def __init__(self, name):
        super().__init__(name)

    def get_positions(self, start_date, end_date, calendar_str=None, forward_fill_days=0,
                      recurse=None):

        if calendar_str is None or not isinstance(calendar_str, str):
            calendar_str = self.calendar

        if forward_fill_days is None or not isinstance(forward_fill_days, numbers.Number):
            forward_fill_days = self.forward_fill_days

        if recurse is None or not isinstance(recurse, bool):
            recurse = False

        days = util.load_business_days(calendar_str, start_date, end_date)
        if len(days) == 0:
            display(f"No valid business days: {self.name}")
            return None
        factors = self.factors
        value_types = self.factor_types
        universes = self.factor_universes
        if universes is None:
            universes = [self.universe] * len(factors)
        filters = self.filters
        lives = self.factor_lives
        if filters is None:
            filters = np.repeat(None, len(lives))
        for i in range(len(value_types)):
            if value_types[i] is None:
                value_types[i] = 'DESCRIPTOR'
        for i in range(len(universes)):
            if universes[i] is None:
                universes[i] = self.universe
        data_dates = util.load_business_days(calendar_str, None, days[-1], self.descriptor_frequency)
        if days[0] in data_dates:
            data_dates = data_dates[data_dates >= days[0]]
        else:
            data_dates = data_dates[np.argmax(data_dates > days[0]) - 1:]

        # pre-load universes
        positions = [None] * len(factors)
        all_sec_ids = np.array([])
        exclusion_universes = self.exclusion_universes
        if isinstance(exclusion_universes, str):
            exclusion_universes = np.array([exclusion_universes])
        if isinstance(exclusion_universes, list):
            exclusion_universes = np.array(exclusion_universes)
        for i in range(len(universes)):
            if universes[i] is None:
                continue
            try:
                positions[i] = port.get_cached_positions(data_dates[0], data_dates[-1], universes[i],
                                                         calendar_str, forward_fill_days=forward_fill_days,
                                                         recurse=recurse)
                all_sec_ids = np.union1d(all_sec_ids, positions[i].columns.to_numpy())
            except ValueError:
                warnings.warn('Unable to load portfolio %s' % universes[i])
        df = pd.DataFrame(0, index=days, columns=all_sec_ids)
        for i, d in enumerate(data_dates):
            valid_days = days[days >= d]
            if i < len(data_dates) - 1:
                valid_days = valid_days[valid_days < data_dates[i + 1]]
            try:
                sec_ids = [None] * len(factors)
                # included = [False] * len(factors)
                included = np.array([])
                for k, fac in enumerate(factors):
                    try:
                        if not rt.within_range(d, lives[k]):
                            continue
                        por = positions[k]
                        k_sec_ids = por.columns[np.where(por.loc[d] != 0)[0]].to_numpy()
                        f_obj = root.load_object(fac)
                        if value_types[k].strip().upper() == 'EXPOSURE':
                            val = f_obj.load_exposures(d, k_sec_ids)
                            val = val.transpose()
                        elif value_types[k].strip().upper() in ['PORTFOLIO', 'UNIVERSE']:
                            val = port.get_cached_positions(d, d, fac, calendar_str)
                        else:
                            val = f_obj.load_values(value_types[k], d, d, k_sec_ids)
                        if val is None:
                            continue
                        if val.empty:
                            continue

                        val = val[~np.isnan(val)]
                        try:
                            if callable(filters[k]):
                                sec_ids[k] = val.columns[np.where(filters[k](val))[1]].to_numpy()
                            elif isinstance(filters[k], str):
                                sec_ids[k] = val.columns[np.where(eval(filters[k]))[1]].to_numpy()
                            else:
                                sec_ids[k] = val.columns.to_numpy()
                            if k == 0:
                                included = sec_ids[k]
                            else:
                                included = np.union1d(included, sec_ids[k])
                            del (val, por, k_sec_ids)
                        except Exception as e:
                            display(e)
                            display(f"Unable to filter universe by {fac}")
                            continue
                    except ValueError:
                        warnings.warn('Unable to filter %d on %s' % (k, d.strftime('%Y%m%d')))
                        continue
                if exclusion_universes is not None:
                    excluded = np.array([])
                    for eu in exclusion_universes:
                        try:
                            ex_u = port.get_cached_positions(d, d, eu, calendar_str)
                            if ex_u is not None:
                                if not ex_u.empty:
                                    excluded = np.union1d(excluded, ex_u.columns.to_numpy())
                        except ValueError as e:
                            display(e)
                            display(f" {self.name}: {d}: unable to exclude universe: {eu}")
                    if len(excluded) > 0:
                        included = np.setdiff1d(included, excluded)
                        display(f'{self.name}: {d}:{len(excluded)} stocks excluded: {len(included)} remained')
                df.loc[valid_days, df.columns.isin(included)] = 1
            except ValueError:
                warnings.warn('Unable to join universes on %s' % d.strftime('%Y%m%d'))
                continue
        # exclude zeros
        df = df[df.columns[np.where(df.sum(axis=0) > 0)]]
        return df

