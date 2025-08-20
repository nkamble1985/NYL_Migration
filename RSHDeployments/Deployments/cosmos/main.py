# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import os.path

import test_db
import util.utilities as util

def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.

import dataloader.market_data as md
import dataloader.qaimera as qa
import numpy as np
import os
import util.routines as rt
import dataloader.portfolio as port
import classes.root as root
import analytics.ra.risk_analysis as ra
import analytics.va.variance_analysis as va
import analytics.ea.factor_performance as fp
import analytics.fa.factor_attribution as fa

# Press the green button in the gutter to run the script.
if __name__ == '__main__':

    fa.factor_attribution(20220801,20220831,14,34,'COSMOS_US_FACTOR_GROUP',print_report=True)
    md.get_sec_id_by_tickers('EYEG-US')

    qa.process_us_model(20181011, 20201230)
    ra.risk_analysis(20220729,13,33,'COSMOS_US_RISK_MODEL','US',True,market=33)
    md.get_sec_id_by_tickers('HDG-US')
    obj = root.load_object('COSMOS_US_FACTOR_GROUP')
    r = obj.load_factor_returns(20110715,20120112)
    file = os.path.join(util.default_output_location('reports'), 'tmp', 'ret.qd')
    ret = util.load_data(file)
    r = r['values'][0]['values']
    result = fp.regression_ts(ret.iloc[:126].to_numpy(),r.to_numpy().astype('float64'))
    va.variance_analysis(20220201, 20220731, 14, 34, ["COSMOS_INDGRP"], 'US', print_report=True)
    sec_ids = 'JLJ0VZ-R'
    obj = root.load_object('COSMOS_US_RISK_MODEL')
    obj.load_related_residual_correlation(20220818, sec_ids)
    obj.load_covariance(20220818, 'JLJ0VZ-R')

    md.get_classification('CTYNJ1-R', vector_flag=False, level='sector')
    obj = root.load_object('COSMOS_US_RISK_MODEL')
    obj.load_residual_covariance(20220818, 'JLJ0VZ-R')
    tickers = ['CAEJ', 'GSas']
    cusips = ['169364106', '38141G104']
    tc = np.array([['CAEJ', '169364106'], ['GSas', '38141G104']])
    qa.map_to_sec_ids(tc)
    b = md.get_identifiers(['P8R3C2-R'], day=19860331)
    b = md.get_identifiers(['JLJ0VZ-R'])
    b = md.get_identifiers(['Q8D48N-R', 'P8R3C2-R'], day=19860331)
    p = md.get_positions(20220816, 20220816, 11)

    md.get_sec_ids('GOOG-US')
    qa.process_related(20220818)

    a, b = md.get_positions(20220811, 20220816, 11, calendar_str='US')
    md.get_sec_id_by_tickers('AXON-US')
    md.get_prices(20220701,20220705,'WFJYTJ-R','GL','CLOSE','JPY')
    md.get_sec_id_by_entity_ids('002615-E')
    md.get_stock_references('HTM0LK-R')
    # test_db.test_returns(20040330,20040430)
    md.get_sec_id_by_exchanges('NAS')
    md.get_sec_id_by_exchanges('NAS')
    md.get_sec_id_by_security_ids('N138TY-S', id_type='listing')
    md.get_returns(20220713,20220714,['B3LWD0-R','HL264M-R'],'US','USD')
    b = md.get_shares_outstanding(20200801, 20200819, ['B3LWD0-R', 'HL264M-R'])
    md.get_sec_id_by_bloomberg_ids('BBG000BS3BJ7')
    md.get_market_cap(20220707, 20220711, ['B3LWD0-R', 'HL264M-R', 'VLHKF9-R'])
    md.get_market_cap(20210707, 20210711, ['HL264M-R', 'VLHKF9-R'])
    md.get_exchange_rates(20220701,20220702,'USD','EUR')
    md.get_exchange_rates(20220701, 20220702, 'GBP', 'JPY')
    a = md.get_prices(20220701, 20220703, ['VLHKF9-R', 'HL264M-R'], 'GL', base_currency='EUR')
# See PyCharm help at https://www.jetbrains.com/help/pycharm/
