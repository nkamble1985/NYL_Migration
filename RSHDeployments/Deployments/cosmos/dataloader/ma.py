#
# Merger Acquisitions
#
#
# Author : Yun Chen
# Indigo Dao, LLC
# Date: January 30, 2023
#
import numbers
import functools as ft
import dataloader.market_data as md
import pandas as pd
import numpy as np
import pyodbc as db
from util.utilities import display
import util.utilities as util
import os
import sys

deal_types = None
deal_type_map = None
info = None
terms = None
relationships = None
roles = None
entity_transactions = None
status_map = None
purpose_map = None
attitude_map = None
entities = None
ma_cache = None


def get_deal_types(deal_id=None, type_id=None, primary_type_id=None):
    global deal_types
    if deal_types is None:
        query = 'select * from FactSetDataFeed.ma_v1.ma_deal_types'
        try:
            conn = md.get_connection()
            cursor = md.get_cursor(conn)
            cursor.execute(query)
            records = cursor.fetchall()
            deal_types = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
            dm = get_deal_type_map()
            deal_types['description'] = 'NA'
            for m in dm.index:
                ix = np.where(deal_types['deal_type_id'] == dm.loc[m, 'deal_type_code'])[0]
                deal_types.loc[deal_types.index[ix], 'description'] = dm.loc[m, 'deal_type_desc']
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to load deal types due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal types due to exception")
            raise ee

    if deal_types is None:
        return None
    if not isinstance(deal_types, pd.DataFrame):
        display(f"Deal Types should be in DataFrame format")
        raise ValueError(f"Deal Types should be in DataFrame format")
    ix = list(range(len(deal_types.index)))
    if deal_id is not None:
        if isinstance(deal_id, numbers.Number):
            ids = int(deal_id)
        elif isinstance(deal_id, str):
            ids = int(deal_id)
        else:
            ids = np.array(deal_id)
        iv = np.vectorize(int)
        ids = iv(ids)
        iy = np.where(np.isin(deal_types['deal_id'], ids))[0]
        ix = np.intersect1d(ix, iy)
    if type_id is not None:
        if isinstance(type_id, numbers.Number):
            ids = int(type_id)
        elif isinstance(type_id, str):
            ids = int(type_id)
        else:
            ids = np.array(type_id)
        iv = np.vectorize(int)
        ids = iv(ids)
        iy = np.where(np.isin(deal_types['deal_type_id'], ids))[0]
        ix = np.intersect1d(ix, iy)
    if primary_type_id is not None:
        if isinstance(primary_type_id, numbers.Number):
            ids = int(primary_type_id)
        elif isinstance(primary_type_id, str):
            ids = int(primary_type_id)
        else:
            ids = np.array(primary_type_id)
        iv = np.vectorize(int)
        ids = iv(ids)
        iy = np.where(np.isin(deal_types['primary_deal_type'], ids))[0]
        ix = np.intersect1d(ix, iy)
    return deal_types.iloc[ix]


def get_deal_type_map(desc=None):
    global deal_type_map
    if deal_type_map is None:
        query = 'select * from FactSetDataFeed.ref_v2.ma_deal_type_map'
        try:
            conn = md.get_connection()
            cursor = md.get_cursor(conn)
            cursor.execute(query)
            records = cursor.fetchall()
            deal_type_map = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to load deal type map due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal types due to exception")
            raise ee
    if desc is not None and isinstance(desc, str):
        ix = np.where(deal_type_map['deal_type_desc'].str.upper() == desc.upper().strip())[0]
    else:
        ix = list(range(len(deal_type_map.index)))
    return deal_type_map.iloc[ix]


def get_spinoffs(canceled_only=False, completed_only=True, start_date=None, end_date=None):
    """

    Parameters
    ----------
    canceled_only: default False
    completed_only: default True, only completed return
    start_date: default None
    end_date: default None

    Returns
    -------

    """
    deals = get_deals_by_type('Spinoff', canceled_only, completed_only, start_date, end_date)
    rel = get_deal_relationships(deals['deal_id'])
    deals.loc[deals.index, 'parent'] = ''
    deals.loc[deals.index, 'target'] = ''
    deals.loc[deals.index, 'purchaser'] = ''
    deals.loc[deals.index, 'new'] = ''
    for idx in deals.index:
        d = deals.loc[idx, 'deal_id']
        ix = np.where(rel['deal_id'] == d)[0]
        if len(ix) == 0:
            continue
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 3)[0]
        if len(iy) > 0:
            deals.loc[idx, 'purchaser'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 4)[0]
        if len(iy) > 0:
            deals.loc[idx, 'parent'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 2)[0]
        if len(iy) > 0:
            deals.loc[idx, 'target'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 14)[0]
        if len(iy) > 0:
            deals.loc[idx, 'new'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
    return deals


# def get_completed_merger_acquisitions(start_date=None, end_date=None):
#     """
#     get completed merger and acquisitions
#     Parameters
#     ----------
#     start_date: default None
#     end_date: default None
#
#     Returns
#     -------
#
#     """
#     deals = get_deals_by_type('Acquisition / Merger', False, True, start_date, end_date)
#     rel = get_deal_relationships(deals['deal_id'])
#     deals.loc[deals.index, 'parent'] = ''
#     deals.loc[deals.index, 'target'] = ''
#     deals.loc[deals.index, 'purchaser'] = ''
#     deals.loc[deals.index, 'new'] = ''
#     for idx in deals.index:
#         d = deals.loc[idx, 'deal_id']
#         ix = np.where(rel['deal_id'] == d)[0]
#         if len(ix) == 0:
#             continue
#         iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 3)[0]
#         if len(iy) > 0:
#             deals.loc[idx, 'purchaser'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
#         iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 4)[0]
#         if len(iy) > 0:
#             deals.loc[idx, 'parent'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
#         iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 2)[0]
#         if len(iy) > 0:
#             deals.loc[idx, 'target'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
#         iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 14)[0]
#         if len(iy) > 0:
#             deals.loc[idx, 'new'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
#     return deals


def get_merger_acquisitions(start_date=None, end_date=None, status='close', include_regional_ids=True,
                            public_target=False, public_buyer=False, types=None):
    """
    get merger and acquisitions: further filter with close/announce/cancel
    Parameters
    ----------
    start_date: default None
    end_date: default None
    status: default None
    include_regional_ids: default False
    public_target: default False
    public_buyer: default False
    types: default 'Acquisition / Merger'

    Returns
    -------

    """
    if types is None:
        types = 'Acquisition / Merger'
    deals = get_deals_by_type(types, False, False, start_date, end_date, status)
    if deals.empty:
        display(f"no deals found")
        return None
    rel = get_deal_relationships(deals['deal_id'])
    deals.loc[deals.index, 'parent'] = ''
    deals.loc[deals.index, 'target'] = ''
    deals.loc[deals.index, 'purchaser'] = ''
    deals.loc[deals.index, 'new'] = ''
    deals.loc[deals.index, 'target_type'] = 'private'
    deals.loc[deals.index, 'purchaser_type'] = 'private'
    for idx in deals.index:
        d = deals.loc[idx, 'deal_id']
        ix = np.where(rel['deal_id'] == d)[0]
        if len(ix) == 0:
            continue
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 3)[0]
        if len(iy) > 0:
            deals.loc[idx, 'purchaser'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 4)[0]
        if len(iy) > 0:
            deals.loc[idx, 'parent'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 2)[0]
        if len(iy) > 0:
            deals.loc[idx, 'target'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
        iy = np.where(rel.loc[rel.index[ix], 'co_role_id'] == 14)[0]
        if len(iy) > 0:
            deals.loc[idx, 'new'] = rel.loc[rel.index[ix[iy[0]]], 'factset_entity_id']
    if not include_regional_ids:
        return deals
    names = np.append(deals.columns, ['sec_id', 'role'])
    targets = pd.DataFrame(columns=names)
    buyers = pd.DataFrame(columns=names)
    parents = pd.DataFrame(columns=names)
    news = pd.DataFrame(columns=names)
    display(f"{len(deals.index)} deals between {deals.loc[deals.index[0], 'announce_date']} "
            f"- {deals.loc[deals.index[-1], 'announce_date']}")
    if include_regional_ids:
        # deals['target_sec_id'] = None
        # deals['purchaser_sec_id'] = None
        # deals['parent_sec_id'] = None
        # deals['new_sec_id'] = None
        ent = np.union1d(deals['target'], deals['purchaser'])
        ent = np.union1d(ent, deals['parent'])
        ent = np.union1d(ent, deals['new'])
        ent = np.setdiff1d(ent, [''])
        if len(ent) > 0:
            display(f"Getting {len(ent)} entities equity securities ...")
            primaries = md.get_primary_equity_by_entities(ent, True)
            display(f"Obtained {len(primaries.index)} securities for {len(np.unique(primaries['factset_entity_id']))} "
                    f"out of {len(ent)} requested entities")
            # ix = np.where(pd.notnull(primaries['fsym_regional_id']))[0]
            # primaries = primaries.iloc[ix]
            t1 = util.clock()
            if not primaries.empty:
                p_ent = primaries['factset_entity_id'].to_numpy()
                if public_buyer and public_target:
                    ib = np.where(np.isin(deals['purchaser'].to_numpy(), p_ent))[0]
                    it = np.where(np.isin(deals['target'].to_numpy(), p_ent))[0]
                    ig = np.intersect1d(ib, it)
                    n_original = len(deals.index)
                    deals = deals.iloc[ig]
                    display(f"{len(ig)} out of {n_original} are public/public deals")
                elif public_target:
                    it = np.where(np.isin(deals['target'].to_numpy(), p_ent))[0]
                    n_original = len(deals.index)
                    deals = deals.iloc[it]
                    display(f"{len(it)} out of {n_original} deals involved public target")

                for i1, x in enumerate(deals.index):
                    t2 = util.clock()
                    sd = deals.loc[x, 'announce_date']
                    ad = util.previous_business_days(deals.loc[x, 'announce_date'], 'GL', 5)
                    iy = np.where(np.logical_and(primaries['start_date'] <= ad, primaries['end_date'] > ad))[0]
                    t_type = 'Private'
                    b_type = 'Private'
                    p_type = 'Private'
                    n_type = 'Private'
                    te = deals.loc[x, 'target']
                    be = deals.loc[x, 'purchaser']
                    pe = deals.loc[x, 'parent']
                    if pd.notnull(te) and len(te) > 0:
                        ix = np.intersect1d(iy, np.where(p_ent == te)[0])
                        if len(ix) > 0:
                            # deals.loc[x, 'target_sec_id'] = primaries.loc[primaries.index[ix[0]], 'fsym_regional_id']
                            zf = pd.concat([deals.loc[[x]]] * len(ix), ignore_index=True)
                            zf['sec_id'] = primaries.loc[primaries.index[ix], 'fsym_regional_id'].to_numpy()
                            zf['target_type'] = 'public'
                            if targets.empty:
                                targets = zf.copy(deep=True)
                            else:
                                targets = pd.concat((targets, zf), axis=0, ignore_index=True)
                            t_type = 'Public'
                            deals.loc[x, 'target_type'] = 'public'
                    if pd.notnull(be) and len(be) > 0:
                        ix = np.intersect1d(iy, np.where(p_ent == be)[0])
                        if len(ix) > 0:
                            # deals.loc[x, 'purchaser_sec_id'] =
                            # primaries.loc[primaries.index[ix[0]], 'fsym_regional_id']
                            zf = pd.concat([deals.loc[[x]]] * len(ix), ignore_index=True)
                            zf['sec_id'] = primaries.loc[primaries.index[ix], 'fsym_regional_id'].to_numpy()
                            zf['purchaser_type'] = 'public'
                            if buyers.empty:
                                buyers = zf.copy(deep=True)
                            else:
                                buyers = pd.concat((buyers, zf), axis=0, ignore_index=True)
                            b_type = 'Public'
                            deals.loc[x, 'purchaser_type'] = 'public'
                    if pd.notnull(pe) and len(pe) > 0:
                        ix = np.intersect1d(iy, np.where(p_ent == pe)[0])
                        if len(ix) > 0:
                            # deals.loc[x, 'parent_sec_id'] = primaries.loc[primaries.index[ix[0]], 'fsym_regional_id']
                            zf = pd.concat([deals.loc[[x]]] * len(ix), ignore_index=True)
                            zf['sec_id'] = primaries.loc[primaries.index[ix], 'fsym_regional_id'].to_numpy()
                            parents = pd.concat((parents, zf), axis=0, ignore_index=True)
                            p_type = 'Public'
                    ne = deals.loc[x, 'new']
                    if pd.notnull(ne) and len(ne) > 0:
                        ix = np.intersect1d(iy, np.where(primaries['factset_entity_id'] == ne)[0])
                        if len(ix) > 0:
                            # deals.loc[x, 'new_sec_id'] = primaries.loc[primaries.index[ix[0]], 'fsym_regional_id']
                            zf = pd.concat([deals.loc[[x]]] * len(ix), ignore_index=True)
                            zf['sec_id'] = primaries.loc[primaries.index[ix], 'fsym_regional_id'].to_numpy()
                            news = pd.concat((news, zf), axis=0, ignore_index=True)
                            n_type = 'Public'
                    t3 = util.clock()
                    display(f"Processed deal: {i1} of {len(deals.index)}: {t3-t2:.1f} sec (total {t3-t1:.1f} sec) "
                            f": {deals.loc[x, 'deal_id']}: announced "
                            f"{sd}: target {te} - {t_type}, buyer {be} - {b_type}, "
                            f"parent {pe} - {p_type}, new {ne} - {n_type}")
    targets.loc[targets.index, 'role'] = 'target'
    buyers.loc[buyers.index, 'role'] = 'buyer'
    parents.loc[parents.index, 'role'] = 'parent'
    news.loc[news.index, 'role'] = 'new'

    if not buyers.empty:
        result = pd.concat((targets, buyers), axis=0, ignore_index=True)
    else:
        result = targets
    if not parents.empty:
        result = pd.concat((result, parents), axis=0, ignore_index=True)
    if not news.empty:
        result = pd.concat((result, news), axis=0, ignore_index=True)

    if public_target:
        pt = np.unique(targets['deal_id'])
        ix = np.where(np.isin(result['deal_id'], pt))[0]
        result = result.iloc[ix]
    if public_buyer:
        pb = np.unique(buyers['deal_id'])
        ix = np.where(np.isin(result['deal_id'], pb))[0]
        result = result.iloc[ix]
    # get sectors/industries
    try:
        ref = md.get_classification(result['sec_id'], 'sector', vector_flag=True)
        ref.rename(columns={ref.columns[0]: 'sector'}, inplace=True)
        result = result.merge(ref, left_on='sec_id', right_index=True)
    except ValueError as ve:
        util.display(f"Due to value error: {ve}")
        util.display(f"Unable to get sectors")
    try:
        ref = md.get_classification(result['sec_id'], 'industry', vector_flag=True)
        ref.rename(columns={ref.columns[0]: 'industry'}, inplace=True)
        result = result.merge(ref, left_on='sec_id', right_index=True)
    except ValueError as ve:
        util.display(f"Due to value error: {ve}")
        util.display(f"Unable to get industries")
    try:
        ref = md.get_rbics_classification(result['sec_id'], 'l1_name', vector_flag=True)
        ref.rename(columns={ref.columns[0]: 'rbics sector'}, inplace=True)
        result = result.merge(ref, left_on='sec_id', right_index=True)
    except ValueError as ve:
        util.display(f"Due to value error: {ve}")
        util.display(f"Unable to get rbics sectors")
    try:
        ref = md.get_rbics_classification(result['sec_id'], 'l2_name', vector_flag=True)
        ref.rename(columns={ref.columns[0]: 'rbics industry group'}, inplace=True)
        result = result.merge(ref, left_on='sec_id', right_index=True)
    except ValueError as ve:
        util.display(f"Due to value error: {ve}")
        util.display(f"Unable to get rbics industry group")
    try:
        ref = md.get_rbics_classification(result['sec_id'], 'l3_name', vector_flag=True)
        ref.rename(columns={ref.columns[0]: 'rbics industry'}, inplace=True)
        result = result.merge(ref, left_on='sec_id', right_index=True)
    except ValueError as ve:
        util.display(f"Due to value error: {ve}")
        util.display(f"Unable to get rbics industries")
    return result


# def process_merger_acquisitions(start_date, end_date, save_flag=False):
#     """
#     only process 100% ought
#     Parameters
#     ----------
#     start_date
#     end_date
#     save_flag: default False
#
#     Returns
#     -------
#
#     """
#     sd = util.parse_date(start_date)
#     ed = util.parse_date(end_date)
#     days = util.load_business_days('GL', sd, ed)
#     display(f"Processing Merger & Acquisition for period {sd} - {ed}")
#     deals = get_merger_acquisitions(start_date, end_date)
#     if deals is None or isinstance(deals, pd.DataFrame) and deals.empty:
#         display(f"No completed berger and acquisition deals between {sd} and {ed}")
#         return True
#     t = get_deal_terms(np.unique(deals['deal_id'].to_numpy()), 1)  # take into
#     ent = np.union1d(deals['target'].to_numpy(), deals['purchaser'].to_numpy())
#     ent = np.union1d(ent, np.setdiff1d(np.unique(deals['new'].to_numpy()), ['']))
#     ent = np.union1d(ent, np.setdiff1d(np.unique(deals['parent'].to_numpy()), ['']))
#     display(f"{len(deals['deal_id'])} merger & acquisition deals found; {len(ent)} entities involved")
#     primary = md.get_primary_equity_by_entities(ent)
#     df = pd.DataFrame(columns=['from_entity', 'from_security', 'from_regional',
#                                'to_entity', 'to_security', 'to_regional',
#                                'buyer_entity', 'buyer_security', 'buyer_regional',
#                                'date', 'value',
#                                'deal', 'type', 'role', 'sought', 'owned', 'deal_type'])
#     count_cash = 0
#     count_stock = 0
#     count_combo = 0
#     count_error = 0
#     count_other = 0
#     incomplete = pd.DataFrame(columns=['deal', 'seller', 'buyer', 'date', 'comment'])
#     for ix, d in enumerate(deals['deal_id'].to_numpy()):
#         try:
#             close_date = deals.loc[deals.index[ix], 'close_date']
#             if close_date not in days:
#                 nd = util.next_business_days(close_date, 'GL')
#             else:
#                 nd = close_date
#             seller = deals.loc[deals.index[ix], 'target']
#             buyer = deals.loc[deals.index[ix], 'purchaser']
#             final = deals.loc[deals.index[ix], 'new']
#             parent = deals.loc[deals.index[ix], 'parent']
#             if len(parent) > 0:
#                 if parent != seller:
#                     display(f"deal {d}: {nd}: parent {parent} --> target {seller}: spinoff")
#             merged = buyer
#             if len(final) > 0:
#                 merged = final
#             else:
#                 if len(parent) > 0:
#                     if parent != seller:
#                         merged = seller  # ??
#             tx = np.where(t['deal_id'] == d)[0]
#             if len(tx) == 0:
#                 display(f"deal {d} {close_date}: no term found")
#                 ef = pd.DataFrame([[d, seller, buyer, close_date, 'no deal term']],
#                                   columns=['deal', 'seller', 'buyer', 'date', 'comment'])
#                 incomplete = pd.concat((incomplete, ef), axis=0)
#                 continue
#             if len(tx) > 1:
#                 display(f"deal{d} {close_date}: have more than 1 latest version")
#                 display(f"picking the fist one")
#
#             # security IDs, regional IDs
#             bx = np.where(np.logical_and(primary['factset_entity_id'] == buyer, primary['start_date'] <= close_date,
#                                          primary['end_date'] > close_date))[0]
#             if len(bx) == 0:
#                 bx = np.where(np.logical_and(primary['factset_entity_id'] == buyer, primary['start_date'] <= nd,
#                                              primary['end_date'] > nd))[0]
#             buyer_sec = None
#             buyer_reg = None
#             buyer_ccy = None
#             if len(bx) > 0:
#                 if len(bx) > 1:
#                     display(f"{d}: {buyer}: {len(tx)} securities")
#                 buyer_sec = primary.loc[primary.index[bx], 'fsym_primary_equity_id']
#                 buyer_reg = primary.loc[primary.index[bx], 'fsym_primary_listing_id']
#                 buyer_ccy = primary.loc[primary.index[bx], 'currency']
#             sx = np.where(np.logical_and(primary['factset_entity_id'] == seller, primary['start_date'] <= close_date,
#                                          primary['end_date'] > close_date))[0]
#             if len(sx) == 0:
#                 sx = np.where(np.logical_and(primary['factset_entity_id'] == seller, primary['start_date'] <= nd,
#                                              primary['end_date'] > nd))[0]
#             seller_sec = None
#             seller_reg = None
#             if len(sx) > 0:
#                 seller_sec = primary.loc[primary.index[sx[0]], 'fsym_primary_equity_id']
#                 seller_reg = primary.loc[primary.index[sx[0]], 'fsym_primary_listing_id']
#             parent_sec = None
#             parent_reg = None
#             if len(parent) > 0:
#                 px = np.where(np.logical_and(primary['factset_entity_id'] == parent, primary['start_date'] <= close_date,
#                                              primary['end_date'] > close_date))[0]
#                 if len(px) == 0:
#                     px = np.where(np.logical_and(primary['factset_entity_id'] == parent, primary['start_date'] <= nd,
#                                                  primary['end_date'] > nd))[0]
#                 if len(px) > 0:
#                     parent_sec = primary.loc[primary.index[px[0]], 'fsym_primary_equity_id']
#                     parent_reg = primary.loc[primary.index[px[0]], 'fsym_primary_listing_id']
#             merged_sec = None
#             merged_reg = None
#             if merged == buyer:
#                 merged_sec = buyer_sec
#                 merged_reg = buyer_reg
#             else:
#                 mx = np.where(np.logical_and(primary['factset_entity_id'] == merged, primary['start_date'] <= close_date,
#                                              primary['end_date'] > close_date))[0]
#                 if len(mx) > 0:
#                     merged_sec = primary.loc[primary.index[mx[0]], 'fsym_primary_equity_id']
#                     merged_reg = primary.loc[primary.index[mx[0]], 'fsym_primary_listing_id']
#
#             term = t.iloc[tx[0]]
#             sought = term['percent_sought']
#             owned = term['percent_owned']
#             mop = term['mop']
#             if mop is None:
#                 count_error = count_error + 1
#                 display(f"{d} ({close_date}: deal type is missing; skipping")
#                 ef = pd.DataFrame([[d, seller, buyer, close_date, 'no payment terms']],
#                                   columns=['deal', 'seller', 'buyer', 'date', 'comment'])
#                 incomplete = pd.concat((incomplete, ef), axis=0)
#                 continue
#             if mop == 'CASH':
#                 count_cash = count_cash + 1
#             elif mop == 'STOCK':
#                 count_stock = count_stock + 1
#             elif mop == 'COMBO':
#                 count_combo = count_combo + 1
#             else:
#                 count_other = count_other + 1
#             s_ratio = term['b_mid_exg_ratio']
#             b_ratio = term['s_mid_exg_ratio']
#             if mop != 'CASH':
#                 if s_ratio is None and b_ratio is None:
#                     display(f"{d} {close_date}: no valid buyer or seller ratio; skipping")
#                     ef = pd.DataFrame([[d, seller, buyer, close_date, 'exchange ratio missing']],
#                                       columns=['deal', 'seller', 'buyer', 'date', 'comment'])
#                     incomplete = pd.concat((incomplete, ef), axis=0)
#                     count_error = count_error + 1
#                     continue
#                 if np.isnan(s_ratio) and np.isnan(b_ratio):
#                     display(f"{d} {close_date}: no valid buyer or seller ratio; skipping")
#                     ef = pd.DataFrame([[d, seller, buyer, close_date, 'exchange ratio missing']],
#                                       columns=['deal', 'seller', 'buyer', 'date', 'comment'])
#                     incomplete = pd.concat((incomplete, ef), axis=0)
#                     count_error = count_error + 1
#                     continue
#             cash = term['cash']
#             currency = term['deal_currency']
#             if sought < 100:
#                 display(f"{d} {close_date}: already owned {owned} %, sought {sought} %")
#             cash_row = None
#             if cash is not None and not np.isnan(cash):
#                 cash_sec = md.get_cash_securities(currency)
#                 if len(cash_sec) == 0:
#                     display(f"WARNING! {d} {close_date}: deal currency {currency} "
#                             f"not recognized/mapped! please investigate")
#                 else:
#                     cash_row = pd.DataFrame([[seller, seller_sec, seller_reg, cash_sec[0], cash_sec[0], cash_sec[0],
#                                               buyer, buyer_sec, buyer_reg,
#                                               close_date, cash, d, 'cash', 'seller', sought, owned, mop]],
#                                             columns=['from_entity', 'from_security', 'from_regional',
#                                                      'to_entity', 'to_security', 'to_regional',
#                                                      'buyer_entity', 'buyer_security', 'buyer_regional',
#                                                      'date', 'value', 'deal', 'type', 'role',
#                                                      'sought', 'owned', 'deal_type'])
#
#             seller_row = pd.DataFrame([[seller, seller_sec, seller_reg, merged, merged_sec, merged_reg,
#                                         buyer, buyer_sec, buyer_reg,
#                                         close_date, s_ratio, d, 'stock', 'buyer', sought, owned, mop]],
#                                       columns=['from_entity', 'from_security', 'from_regional',
#                                                'to_entity', 'to_security', 'to_regional',
#                                                'buyer_entity', 'buyer_security', 'buyer_regional',
#                                                'date', 'value', 'deal', 'type', 'role',
#                                                'sought', 'owned', 'deal_type'])
#             buyer_row = pd.DataFrame([[buyer, buyer_sec, buyer_reg, merged, merged_sec, merged_reg,
#                                        buyer, buyer_sec, buyer_reg,
#                                        close_date, b_ratio, d, 'stock', 'buyer', sought, owned, mop]],
#                                      columns=['from_entity', 'from_security', 'from_regional',
#                                               'to_entity', 'to_security', 'to_regional',
#                                               'buyer_entity', 'buyer_security', 'buyer_regional',
#                                               'date', 'value', 'deal', 'type', 'role',
#                                               'sought', 'owned', 'deal_type'])
#
#             if cash_row is not None:
#                 df = pd.concat((df, cash_row), axis=0, ignore_index=True)
#             if mop != 'CASH':
#                 df = pd.concat((df, seller_row), axis=0, ignore_index=True)
#                 df = pd.concat((df, buyer_row), axis=0, ignore_index=True)
#             if np.isnan(cash):
#                 cash = 0
#             display(f"{d} {close_date}: seller: {seller} (x {s_ratio} stock, cash {cash:.2f}); "
#                     f"buyer: {buyer} (x {b_ratio}); "
#                     f"merged {merged}  |  {mop}")
#         except ValueError as ve:
#             display(f"{ve}")
#             display(f"Unable to process deal {d} due to value error")
#         except Exception as ee:
#             display(f"{ee}")
#             display(f"Unable to process deal {d} due to exception")
#
#     df.loc[df.index[ix], 'owned'] = 0
#     print('*' * 100)
#     display(f"{sd} - {ed}: {len(deals.index)} deals: {count_cash:,} Cash, "
#             f"{count_stock:,} Stock, {count_combo:,} Combo, {count_other:,} Other, {count_error:,} errors")
#     print('*' * 100)
#     if save_flag:
#         location = os.path.join(util.default_output_location('market'), 'ma')
#         if not util.exists(location):
#             util.makedirs(location)
#             display(f"Successfully created : {location}")
#         file = os.path.join(location, f"merger.qd")
#         if util.exists(file):
#             data = util.load_data(file)
#             orig_rows = len(data.index)
#             ix = np.where(np.logical_and(data['date'] >= sd, data['date'] <= ed))[0]
#             if len(ix) > 0:
#                 data.drop(data.index[ix], axis=0, inplace=True)
#                 display(f"Dropped {len(ix)} rows for prior data between {sd} and {ed}")
#             data = pd.concat((data, df), axis=0, ignore_index=True)
#             data.sort_values(by='date', inplace=True, ignore_index=True)
#             util.save_data(data, file)
#             new_rows = len(df.index)
#             display(f"Total {len(np.unique(data['deal']))} ({orig_rows}: +{new_rows}) deals between "
#                     f"{data.loc[data.index[0], 'date']} and "
#                     f"{data.loc[data.index[-1], 'date']}")
#             display(f"{file}")
#         else:
#             util.save_data(df, file)
#             display(f"Total {len(np.unique(df['deal']))} deals between {df.loc[df.index[0], 'date']} and "
#                     f"{df.loc[df.index[-1], 'date']}")
#             display(f"{file}")
#         if not incomplete.empty:
#             dates = np.unique(incomplete['date'].to_numpy())
#             err_location = os.path.join(location, 'error_logs')
#             if not util.exists(err_location):
#                 util.makedirs(err_location)
#                 display(f"Successfully created error log location: {err_location}")
#             for d in dates:
#                 ix = np.where(incomplete['date'] == d)[0]
#                 if len(ix) == 0:
#                     continue
#                 efile = os.path.join(err_location, f"error.{d.strftime(util.yyyymmdd_format)}.xlsx")
#                 incomplete.iloc[ix].to_excel(efile)
#                 display(f"{d}: {len(ix)} deals omitted")
#                 display(f"{efile}")
#             display(f"{sd} - {ed}: {len(dates)}-days with merger deals (total {len(deals['deal_id'])}):"
#                     f" total {len(incomplete.index)} deals omitted")
#     return df, incomplete


def process_merger_acquisitions3(start_date, end_date, save_flag=False):
    """
    only process 100% ought
    Parameters
    ----------
    start_date
    end_date
    save_flag: default False

    Returns
    -------

    """
    sd = util.parse_date(start_date)
    ed = util.parse_date(end_date)
    days = util.load_business_days('GL', sd, ed)
    display(f"Processing Merger & Acquisition for period {days[0]} - {days[-1]}")
    deals = get_merger_acquisitions(start_date, end_date)
    if deals is None or isinstance(deals, pd.DataFrame) and deals.empty:
        display(f"No completed merger and acquisition deals between {sd} and {ed}")
        return True
    total_d = len(np.unique(deals['deal_id']))
    errors = pd.DataFrame(columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date', 'comment'])
    error_template = errors.copy()
    t = get_deal_terms(np.unique(deals['deal_id'].to_numpy()), 1)  # take into
    ix = np.where(pd.notnull(t['mop']))[0]
    iz = np.where(pd.isnull(t['mop']))[0]
    ic = np.where(t['mop'] == 'CASH')[0]
    ie = np.where(np.logical_and(pd.isnull(t['s_mid_exg_ratio']), pd.isnull(t['b_mid_exg_ratio'])))[0]
    ie = np.intersect1d(ix, ie)
    ie = np.setdiff1d(ie, ic)
    display(f"{len(iz)} out of {len(t.index)} deal terms missing 'methods of payments'")
    display(f"{len(ic)} out of {len(t.index)} deal pure CASH deals'")
    display(f"{len(ie)} out of {len(np.setdiff1d(ix, ic))} deal STOCK/COMBO deals: missing exchange ratios ignored'")
    count_mop_missing = len(iz)
    count_cash = len(ic)
    if len(ie) > 0:
        ef = error_template.copy()
        eids = t['deal_id'].iloc[ie].to_numpy()
        ex = np.where(np.isin(deals['deal_id'].to_numpy(), eids))[0]
        ef['deal'] = deals.loc[deals.index[ex], 'deal_id']
        ef['target'] = deals.loc[deals.index[ex], 'target']
        ef['buyer'] = deals.loc[deals.index[ex], 'purchaser']
        ef['date'] = deals.loc[deals.index[ex], 'close_date']
        ef['comment'] = 'stock/combo deals missing exchange ratios'
        errors = pd.concat((errors, ef), axis=0, ignore_index=True)
        display(f"Out of all {len(deals.index)} deals: {len(ef.index)} stock/combo deals are missing exchange ratios")
    if len(iz) > 0:
        ef = error_template.copy()
        eids = t['deal_id'].iloc[iz].to_numpy()
        ex = np.where(np.isin(deals['deal_id'].to_numpy(), eids))[0]
        ef['deal'] = deals.loc[deals.index[ex], 'deal_id']
        ef['target'] = deals.loc[deals.index[ex], 'target']
        ef['buyer'] = deals.loc[deals.index[ex], 'purchaser']
        ef['date'] = deals.loc[deals.index[ex], 'close_date']
        ef['comment'] = 'no payment option'
        errors = pd.concat((errors, ef), axis=0, ignore_index=True)
        display(f"Out of all {len(deals.index)} deals: {len(ef.index)} deals are missing payment options")
    # ix = np.setdiff1d(ix, ic)
    ix = np.setdiff1d(ix, ie)
    t = t.iloc[ix]
    ix = np.where(np.isin(deals['deal_id'], t['deal_id']))[0]
    original = len(deals.index)
    deals = deals.iloc[ix]
    display(f"{len(deals.index)} out of {original} deals have minimal deal terms information")
    if deals.empty:
        display(f"No valid completed berger and acquisition deals between {sd} and {ed}")
        return True
    ent = np.union1d(deals['target'].to_numpy(), deals['purchaser'].to_numpy())
    ent = np.union1d(ent, np.setdiff1d(np.unique(deals['new'].to_numpy()), ['']))
    ent = np.union1d(ent, np.setdiff1d(np.unique(deals['parent'].to_numpy()), ['']))
    display(f"{len(deals['deal_id'])} merger & acquisition deals found; {len(ent)} entities involved")
    if len(ent) == 0:
        display(f"No valid entities found; returning")
        return False
    eh = md.get_entity_structure_history(ent)
    if eh is None or eh.empty:
        display(f"No valid entity structure history; returning")
        return False
    # add in parent entities if they have equities
    ix = np.where(pd.notnull(eh['factset_parent_entity_id']))[0]
    ent = np.union1d(ent, eh.loc[eh.index[ix], 'factset_parent_entity_id'])
    # add in ultimate parent entities if they have equities
    ix = np.where(pd.notnull(eh['factset_ult_parent_entity_id']))[0]
    ent = np.union1d(ent, eh.loc[eh.index[ix], 'factset_ult_parent_entity_id'])
    primary = md.get_primary_equity_by_entities(ent, True)
    p_ent = np.unique(primary['factset_entity_id'].to_numpy())
    df = pd.DataFrame(columns=['from_entity', 'from_security', 'from_regional', 'from_name', 'from_type',
                               'to_entity', 'to_security', 'to_regional', 'to_name', 'to_type',
                               'date', 'value', 'stock', 'cash', 'currency', 'deal', 'role',
                               'sought', 'owned', 'payment_type'])
    count_stock = 0
    count_combo = 0
    count_spinoff = 0
    count_error = 0
    count_other = 0

    counted = np.array([])
    num_d = len(deals.index)
    for ix, d in enumerate(deals['deal_id'].to_numpy()):
        try:
            # ----------------------------------------------------------------------------
            # figure out dates
            # ----------------------------------------------------------------------------
            close_date = deals.loc[deals.index[ix], 'close_date']
            nd = util.next_business_days(close_date, 'GL', 5)
            prev = util.previous_business_days(close_date, 'GL', 5)
            # ----------------------------------------------------------------------------
            # figure out who is selling what to whom
            # ----------------------------------------------------------------------------
            target = deals.loc[deals.index[ix], 'target']
            target_to = None   # the entity the target is turning into
            target_from_type = None
            target_to_type = None
            count_target = 0
            buyer = deals.loc[deals.index[ix], 'purchaser']
            buyer_to = None
            buyer_from_type = None
            buyer_to_type = None
            count_buyer = 0
            parent = deals.loc[deals.index[ix], 'parent']
            if len(parent) > 0:
                if parent != target:
                    display(f"{d}: {close_date}: parent {parent} --> target {target}: spinoff")
                    count_spinoff += 1
            if target not in p_ent and buyer not in p_ent:
                display(f"{ix} of {num_d} deal: {d}; no security info for both target {target} or buyer {buyer}")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date, 'target/buyer entities not recognized']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',  'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
                count_error += 1
                continue
            # ----------------------------------------------------------------------------
            # figure out terms
            # ----------------------------------------------------------------------------
            tx = np.where(t['deal_id'] == d)[0]
            if len(tx) == 0:
                display(f"{d}: {close_date} no valid deal term found, skipping")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date, 'no deal term']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
                counted = np.union1d(counted, d)
                continue
            if len(tx) > 1:
                display(f"{d}: {close_date}: {len(tx)} terms found, taking the first term")
            term = t.iloc[tx[0]]
            sought = term['percent_sought']
            owned = term['percent_owned']
            if np.isnan(owned):
                owned = 0.0
            mop = term['mop']
            cash = term['cash_price_share']
            stock = term['stock_price_share']
            currency = term['deal_currency']
            if currency is not None:
                cash_sec = md.get_cash_securities(currency)
                if isinstance(cash_sec, np.ndarray):
                    cash_sec = cash_sec[0]
            else:
                cash_sec = None
            s_ratio = term['s_mid_exg_ratio']
            b_ratio = term['b_mid_exg_ratio']
            if sought < 100:
                display(f"{d} {close_date}: already owned {owned:.2f} %, sought {sought:.2f} %")
            if mop == 'CASH':
                count_cash = count_cash + 1
                # display(f"No. {ix} ({num_d}): {d}: all cash deal, detail in sym_v1 corporate action table; skipping")
                display(f"No. {ix} ({num_d}): {d}: all cash deal")
            elif mop == 'STOCK':
                count_stock = count_stock + 1
            elif mop == 'COMBO':
                count_combo = count_combo + 1
            else:
                count_other = count_other + 1
            display(f"No. {ix} ({num_d}) deal {d}: {close_date}: {mop}: {cash_sec} {cash} + "
                    f"stock(Seller {b_ratio} X, Buyer {s_ratio} X)")
            if mop in ('STOCK', 'COMBO'):
                if pd.isnull(s_ratio) and pd.isnull(b_ratio):
                    display(f"No. {ix} ({num_d}): {d}: {mop} deal: exchange ratios for buyer and seller missing:"
                            f" skipping")
                    ef = pd.DataFrame([[d, target, buyer, None, None, close_date, 'both exchange ratios missing']],
                                      columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                               'date', 'comment'])
                    errors = pd.concat((errors, ef), axis=0, ignore_index=True)
                    continue
            # -----------------------------------------------------
            # entity types and securities
            # -----------------------------------------------------
            # ---------------------
            # target
            tx = np.where(np.logical_and(eh['factset_entity_id'] == target,
                                         np.logical_and(eh['start_date'] <= prev,
                                         eh['end_date'] > prev)))[0]
            px = np.where(np.logical_and(eh['factset_entity_id'] == target,
                                         np.logical_and(eh['start_date'] <= nd,
                                         eh['end_date'] > nd)))[0]
            if len(tx) == 0 and len(px) == 0:
                display(f"{d} {close_date} Cannot find before and after target {target} information")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date,
                                    'target entity security information missing']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                           'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            elif len(tx) > 0 and len(px) == 0:
                display(f"{d} {close_date} Cannot find after target {target} information")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date,
                                    'target entity after security information missing']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                           'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            elif len(tx) == 0 and len(px) > 0:
                display(f"{d} {close_date} Cannot find before target {target} information")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date,
                                    'target entity before security information missing']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                           'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            else:
                if len(tx) > 1:
                    display(f"{d} {close_date} target {target}: {len(tx)} entities found: pre-closing: first used")
                tx = tx[0]
                if len(px) > 1:
                    display(f"{d} {close_date} target {target}: {len(px)} entities found: post-closing: first used")
                px = px[0]
                if tx == px:
                    display(f"{d} {close_date} found target {target} remains unchanged after transaction")
                    target_to = target
                    if mop == 'CASH':
                        target_to = cash_sec
                else:
                    if mop == 'CASH':
                        target_to = cash_sec
                    else:
                        target_to = eh.loc[eh.index[px], 'factset_parent_entity_id']
                        if target_to is None:
                            target_to = eh.loc[eh.index[px], 'factset_ult_parent_entity_id']
                    display(f"{d} ({num_d}) {close_date}: target {target} turn into "
                            f"{target_to}")
                target_from_type = eh.loc[eh.index[tx], 'entity_type']
                target_to_type = eh.loc[eh.index[px], 'entity_type']
                if mop == 'CASH':
                    target_to_type = 'CASH'
            if target_to is not None:
                tx = np.where(np.logical_and(primary['factset_entity_id'] == target,
                                             np.logical_and(primary['start_date'] <= prev,
                                                            primary['end_date'] > prev)))[0]
                px = np.where(np.logical_and(primary['factset_entity_id'] == target_to,
                                             np.logical_and(primary['start_date'] <= nd,
                                                            primary['end_date'] > nd)))[0]
                if len(tx) == 0:
                    display(f"{d}: target {target}: no corresponding securities found")
                if len(px) == 0:
                    if mop == 'CASH':
                        display(f"{d}: {mop} deal: target {target} turning into {target_to}")
                    else:
                        display(f"{d}: {mop} deal: target {target} turning into {target_to} which has zero securities")
                if len(tx) > 0 and len(px) > 0 or mop != 'STOCK' and len(tx) > 0:
                    display(f"{d}: target {target} {len(tx)} securities turning into {target_to} {len(px)} securities")
                    from_ref = pd.DataFrame(primary.loc[primary.index[tx], ['fsym_security_id', 'fsym_regional_id',
                                                                            'currency', 'fref_listing_exchange',
                                                                            'proper_name']].to_numpy(),
                                            columns=['security_id', 'regional_id', 'currency', 'exchange', 'name'])
                    from_ref['entity_id'] = target
                    from_ref['entity_type'] = target_from_type
                    to_ref = pd.DataFrame(primary.loc[primary.index[px], ['fsym_security_id', 'fsym_regional_id',
                                                                          'currency', 'fref_listing_exchange',
                                                                          'proper_name']].to_numpy(),
                                          columns=['security_id', 'regional_id', 'currency', 'exchange', 'name'])
                    to_ref['entity_id'] = target
                    to_ref['entity_type'] = target_to_type
                    for x in from_ref.index:
                        ccy = from_ref.loc[x, 'currency']
                        sid = from_ref.loc[x, 'security_id']
                        rid = from_ref.loc[x, 'regional_id']
                        exc = from_ref.loc[x, 'exchange']
                        f_name = from_ref.loc[x, 'name']
                        if rid is None:
                            display(f"{d}: {close_date}: target {target} from security {sid} ({rid}) "
                                    f"missing regional ID")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date, 'target regional id missing']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        if sid is None:
                            display(f"{d}: {close_date}: target {target} from security {sid} ({rid}) missing currency")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date, 'target security id missing']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        if ccy is None:
                            display(f"{d}: {close_date}: target {target} from security {sid} ({rid}) missing currency")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date,
                                                'target security currency missing']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        kx = np.where(to_ref['regional_id'] == rid)[0]
                        if len(kx) == 0:
                            kx = np.where(np.logical_and(to_ref['currency'] == ccy, to_ref['exchange'] == exc))[0]
                        if len(kx) == 0:
                            kx = np.where(to_ref['currency'] == ccy)[0]
                        if len(kx) == 0:
                            if mop == 'CASH':
                                rf = pd.DataFrame([[target, sid, rid, f_name, target_from_type,
                                                   target_to, target_to, target_to, target_to, target_to_type,
                                                   close_date, b_ratio, stock, cash, currency, d, 'target', sought,
                                                   owned, mop]],
                                                  columns=['from_entity', 'from_security', 'from_regional', 'from_name',
                                                           'from_type', 'to_entity', 'to_security', 'to_regional',
                                                           'to_name', 'to_type', 'date', 'value', 'stock', 'cash',
                                                           'currency', 'deal', 'role', 'sought', 'owned', 'payment_type'])
                                df = pd.concat((df, rf), axis=0, ignore_index=True)
                                count_target += 1
                            else:
                                display(f"{d}: {mop} deal: {close_date}: target {target} "
                                        f"from security {sid} ({rid}, {ccy}) "
                                        f" no destination security with the same currency {ccy}")
                                ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date,
                                                    'target security ccy not found among successors']],
                                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                           'comment'])
                                errors = pd.concat((errors, ef), axis=0)
                                continue
                        else:
                            if len(kx) > 1:
                                display(f"{d}: {mop} deal: {close_date}: target {target} "
                                        f"from security {sid} ({rid}, {ccy}) "
                                        f"has {len(kx)} (>1) destination security with the same currency; picking 1st")
                            kx = kx[0]
                            y = to_ref.index[kx]
                            tsid = to_ref.loc[y, 'security_id']
                            trid = to_ref.loc[y, 'regional_id']
                            t_name = to_ref.loc[y, 'name']
                            if tsid == sid and trid == rid and b_ratio == 1.0:
                                if target == target_to:
                                    display(f"{d}: {close_date} target entity id {target} and "
                                            f"regional id {rid} continues and exchange ratio is 1.0; skipping")
                                else:
                                    display(f"{d}: {close_date} target entity id {target} changed to {target_to} and "
                                            f"regional id {rid} continues and exchange ratio is 1.0; skipping")
                                continue
                            rf = pd.DataFrame([[target, sid, rid, f_name, target_from_type,
                                               target_to, tsid, trid, t_name, target_to_type, close_date,
                                               b_ratio, stock, cash, currency, d, 'target', sought, owned, mop]],
                                              columns=['from_entity', 'from_security', 'from_regional', 'from_name',
                                                       'from_type',
                                                       'to_entity', 'to_security', 'to_regional', 'to_name', 'to_type',
                                                       'date', 'value', 'stock', 'cash', 'currency', 'deal', 'role',
                                                       'sought', 'owned', 'payment_type'])
                            df = pd.concat((df, rf), axis=0, ignore_index=True)
                            count_target += 1
                else:
                    if len(tx) == 0:
                        display(f"No. {ix} ({num_d}): {d}: {mop} deal: target missing corresponding securities")
                    else:
                        display(f"No. {ix} ({num_d}): {d}: {mop} deal: target's successor missing securities")
                    ef = pd.DataFrame([[d, target, buyer, None, None, close_date,
                                        'target/successor missing securities']],
                                      columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                               'date', 'comment'])
                    errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            else:
                if b_ratio != 1:
                    display(f"{d}: target after {close_date} not found: but exchange rate is not 1.0: skipping target")
                else:
                    display(f"{d}: target after {close_date} not found: exchange rate is 1.0: skipping target")
            # ---------------------
            # buyer
            bx = np.where(np.logical_and(eh['factset_entity_id'] == buyer,
                                         np.logical_and(eh['start_date'] <= prev,
                                                        eh['end_date'] > prev)))[0]
            qx = np.where(np.logical_and(eh['factset_entity_id'] == buyer,
                                         np.logical_and(eh['start_date'] <= nd,
                                                        eh['end_date'] > nd)))[0]
            if len(bx) == 0 and len(qx) == 0:
                display(f"{d} {close_date} Cannot find before and after buyer {buyer} information")
                display(f"No. {ix} ({num_d}): {d}: {mop} deal: buyer and successor entities missing:"
                        f" skipping")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date, 'buyer/successor missing entities']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                           'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            elif len(bx) > 0 and len(qx) == 0:
                display(f"{d} {close_date} Cannot find after buyer {buyer} information")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date,
                                    'buyer/successor missing after information']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                           'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            elif len(bx) == 0 and len(qx) > 0:
                display(f"{d} {close_date} Cannot find before buyer {buyer} information")
                ef = pd.DataFrame([[d, target, buyer, None, None, close_date,
                                    'target entity before security information missing']],
                                  columns=['deal', 'target', 'buyer', 'security_id', 'regional_id',
                                           'date', 'comment'])
                errors = pd.concat((errors, ef), axis=0, ignore_index=True)
            else:
                if len(bx) > 1:
                    display(f"{d} {close_date} buyer {buyer} found {len(bx)} entities: pre-closing")
                bx = bx[0]
                if len(qx) > 1:
                    display(f"{d} {close_date} buyer {buyer} found {len(qx)} entities: post-closing")
                qx = qx[0]
                if bx == qx:
                    display(f"{d} {close_date} buyer {buyer} survives merger")
                    buyer_to = buyer
                else:
                    buyer_to = eh.loc[eh.index[qx], 'factset_parent_entity_id']
                    if buyer_to is None:
                        buyer_to = eh.loc[eh.index[qx], 'factset_ult_parent_entity_id']
                    display(f"{d} {close_date}: buyer {buyer} turn into "
                            f"{buyer_to}")
                buyer_from_type = eh.loc[eh.index[bx], 'entity_type']
                buyer_to_type = eh.loc[eh.index[qx], 'entity_type']
            if buyer_to is not None:
                bx = np.where(np.logical_and(primary['factset_entity_id'] == buyer,
                                             np.logical_and(primary['start_date'] <= prev,
                                                            primary['end_date'] > prev)))[0]
                qx = np.where(np.logical_and(primary['factset_entity_id'] == buyer_to,
                                             np.logical_and(primary['start_date'] <= nd,
                                                            primary['end_date'] > nd)))[0]
                if len(bx) == 0:
                    display(f"{d}: buyer {buyer} zero securities")
                if len(qx) == 0:
                    display(f"{d}: buyer {buyer} turning into {buyer_to} which has zero securities")
                if len(bx) > 0 and len(qx) > 0:
                    display(f"{d}: buyer {buyer} {len(bx)} securities turning into {buyer_to} {len(qx)} securities")
                    from_ref = pd.DataFrame(primary.loc[primary.index[bx], ['fsym_security_id', 'fsym_regional_id',
                                                                            'currency', 'fref_listing_exchange',
                                                                            'proper_name']].to_numpy(),
                                            columns=['security_id', 'regional_id', 'currency', 'exchange', 'name'])
                    from_ref['entity_id'] = buyer
                    from_ref['entity_type'] = buyer_from_type
                    to_ref = pd.DataFrame(primary.loc[primary.index[qx], ['fsym_security_id', 'fsym_regional_id',
                                                                          'currency', 'fref_listing_exchange',
                                                                          'proper_name']].to_numpy(),
                                          columns=['security_id', 'regional_id', 'currency', 'exchange', 'name'])
                    to_ref['entity_id'] = buyer_to
                    to_ref['entity_type'] = buyer_to_type
                    for x in from_ref.index:
                        ccy = from_ref.loc[x, 'currency']
                        sid = from_ref.loc[x, 'security_id']
                        rid = from_ref.loc[x, 'regional_id']
                        exc = from_ref.loc[x, 'exchange']
                        f_name = from_ref.loc[x, 'name']
                        if rid is None:
                            display(f"{d}: {close_date}: buyer {buyer} from security {sid} ({rid}) "
                                    f"missing regional ID")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date, 'buyer regional id missing']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        if sid is None:
                            display(f"{d}: {close_date}: buyer {buyer} from security {sid} ({rid}) missing currency")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date, 'buyer security id missing']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        if ccy is None:
                            display(f"{d}: {close_date}: buyer {buyer} from security {sid} ({rid}) missing currency")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date,
                                                'buyer security currency missing']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        kx = np.where(to_ref['regional_id'] == rid)[0]
                        if len(kx) == 0:
                            kx = np.where(np.logical_and(to_ref['currency'] == ccy, to_ref['exchange'] == exc))[0]
                        if len(kx) == 0:
                            kx = np.where(to_ref['currency'] == ccy)[0]
                        if len(kx) == 0:
                            display(f"{d}: {close_date}: buyer {buyer} from security {sid} ({rid}, {ccy}) "
                                    f" no destination security with the same currency {ccy}")
                            ef = pd.DataFrame([[d, target, buyer, sid, rid, close_date,
                                                'successor security ccy not found']],
                                              columns=['deal', 'target', 'buyer', 'security_id', 'regional_id', 'date',
                                                       'comment'])
                            errors = pd.concat((errors, ef), axis=0)
                            continue
                        else:
                            if len(kx) > 1:
                                display(f"{d}: {mop} deal: {close_date}: buyer {buyer} from security "
                                        f"{sid} ({rid}, {ccy}) "
                                        f"has {len(kx)} (>1) successor security with the same currency; picking 1st")
                            kx = kx[0]
                            y = to_ref.index[kx]
                            tsid = to_ref.loc[y, 'security_id']
                            trid = to_ref.loc[y, 'regional_id']
                            t_name = to_ref.loc[y, 'name']
                            if tsid == sid and rid == trid and s_ratio == 1.0:
                                if buyer != buyer_to:
                                    display(f"{d}: {close_date} buyer entity id changed from {buyer} to {buyer_to} "
                                            f"but regional id {rid} continued: skipping")
                                else:
                                    display(f"{d}: {close_date} buyer entity id {buyer} and regional id {rid} "
                                            f"continued: skipping")
                                continue
                            rf = pd.DataFrame([[target, sid, rid, f_name, target_from_type,
                                               target_to, tsid, trid, t_name, target_to_type, close_date,
                                               s_ratio, stock, cash, currency, d, 'buyer', sought, owned, mop]],
                                              columns=['from_entity', 'from_security', 'from_regional', 'from_name',
                                                       'from_type', 'to_entity', 'to_security', 'to_regional',
                                                       'to_name', 'to_type', 'date', 'value', 'stock', 'cash',
                                                       'currency', 'deal', 'role', 'sought', 'owned', 'payment_type'])
                            df = pd.concat((df, rf), axis=0, ignore_index=True)
                            count_buyer += 1
            else:
                if s_ratio != 1:
                    display(f"{d}: buyer continues beyond {close_date}: but exchange rage is not 1.0: skipping buyer")
                else:
                    display(f"{d}: buyer continues beyond {close_date}: exchange rage is 1.0: skipping buyer")
            print('-' * 100)
            display(f"{ix} of {num_d}: {d}: {close_date}: {target} acquired by {buyer} ({mop}): "
                    f"+{count_target} target rows, +{count_buyer} buyer rows")
            display(f"{ix} of {num_d}: total {len(np.unique(df['deal']))} deals, "
                    f"{(df['role'] == 'target').sum()} target rows, {(df['role'] == 'buyer').sum()} buyer rows")
            print('-' * 100)
        except ValueError as ve:
            display(f"{ve}")
            display(f"Unable to process deal {d} due to value error")
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to process deal {d} due to exception")
    df.drop_duplicates(keep='last', inplace=True)
    errors.drop_duplicates(keep='last', inplace=True)
    count_cash = len(np.where(df['payment_type'] == 'CASH')[0])
    count_stock = len(np.where(df['payment_type'] == 'STOCK')[0])
    count_combo = len(np.where(df['payment_type'] == 'COMBO')[0])
    count_other = len(df.index) - (count_stock + count_cash + count_combo)
    display(f"{total_d} deals: between {np.min(deals['close_date'])} and {np.max(deals['close_date'])}\n"
            f"    Cash Deals: {count_cash}\n"
            f"    Stock Deals: {count_stock}\n"
            f"    Combo Deals: {count_combo}\n"
            f"Securities Transformed\n"
            f"    Total deals: {len(np.unique(df['deal']))}\n"
            f"    Target securities: {(df['role'] == 'target').sum()}\n"
            f"    Buyer securities: {(df['role'] == 'buyer').sum()}\n"
            f"Errors: {len(errors.index)}\n"
            f"    mop missing: {count_mop_missing}")
    display(f"======== {len(df.index)} rows ========")
    # ix = np.where(pd.isnull(df['owned']))[0]
    # df.loc[df.index[ix], 'owned'] = 0
    print('*' * 100)
    display(f"{sd} - {ed}: {num_d} deals: {count_cash:,} Cash, "
            f"{count_stock:,} Stock, {count_combo:,} Combo, {count_other:,} Other, "
            f"{len(np.unique(errors['deal'])):,} errors")
    print('*' * 100)
    if save_flag:
        location = os.path.join(util.default_output_location('market'), 'ma')
        if not util.exists(location):
            util.makedirs(location)
            display(f"Successfully created : {location}")
        file = os.path.join(location, f"mergers.qd")
        if util.exists(file):
            data = util.load_data(file)
            orig_rows = len(data.index)
            ix = np.where(np.logical_and(data['date'] >= sd, data['date'] <= ed))[0]
            if len(ix) > 0:
                data.drop(data.index[ix], axis=0, inplace=True)
                display(f"Dropped {len(ix)} rows for prior data between {sd} and {ed}")
            data = pd.concat((data, df), axis=0, ignore_index=True)
            data.sort_values(by='date', inplace=True, ignore_index=True)
            data.drop_duplicates(inplace=True)
            util.save_data(data, file)
            new_rows = len(df.index)
            display(f"Total {len(np.unique(data['deal']))} ({orig_rows}: +{new_rows}) deals between "
                    f"{data.loc[data.index[0], 'date']} and "
                    f"{data.loc[data.index[-1], 'date']}")
            display(f"{file}")
        else:
            df.drop_duplicates(inplace=True)
            util.save_data(df, file)
            display(f"Total {len(np.unique(df['deal']))} deals between {df.loc[df.index[0], 'date']} and "
                    f"{df.loc[df.index[-1], 'date']}")
            display(f"{file}")
        if not errors.empty:
            dates = np.unique(errors['date'].to_numpy())
            err_location = os.path.join(location, 'error_logs')
            if not util.exists(err_location):
                util.makedirs(err_location)
                display(f"Successfully created error log location: {err_location}")
            for d in dates:
                ix = np.where(errors['date'] == d)[0]
                if len(ix) == 0:
                    continue
                efile = os.path.join(err_location, f"error.{d.strftime(util.yyyymmdd_format)}.xlsx")
                errors.iloc[ix].to_excel(efile)
                display(f"{d}: {len(ix)} deals omitted")
                display(f"{efile}")
            display(f"{sd} - {ed}: {len(dates)}-days with merger deals (total {total_d}):"
                    f" total {len(errors.index)} deals omitted, {len(np.unique(df['deal']))} processed")
    return df, errors


def get_processed_merger_acquisitions(start_date=None, end_date=None, sec_ids=None, role=None):
    location = os.path.join(util.default_output_location('market'), 'ma')
    if not util.exists(location):
        util.makedirs(location)
        display(f"Successfully created : {location}")
    file = os.path.join(location, f"mergers.qd")
    if not util.exists(file):
        display(f"No previously cached processed merger and acquisitions found; returning None")
        return None
    df = util.load_data(file)
    df.drop_duplicates(inplace=True)
    if start_date is not None or end_date is not None:
        days = util.load_business_days('GL', start_date, end_date)
        if len(days) == 0:
            display(f"No valid business days; returning None")
            return None
        ix = np.where(np.logical_and(df['date'] >= days[0], df['date'] <= days[-1]))[0]
        df = df.iloc[ix]
    if sec_ids is not None:
        if hasattr(sec_ids, 'to_numpy'):
            sec_ids = sec_ids.to_numpy()
        if isinstance(sec_ids, str):
            sec_ids = np.array([sec_ids])
        ix = np.where(np.isin(df['from_regional'].to_numpy(), sec_ids))[0]
        df = df.iloc[ix]
    if role is not None:
        if isinstance(role, str):
            role = role.lower().strip()
            if role not in ('buyer', 'target'):
                display(f"{role} not accepted: either buyer or target")
            else:
                ix = np.where(df['role'] == role)[0]
                df = df.iloc[ix]
    return df


def get_deals_by_type(deal_type, canceled_only=False, completed_only=False, start_date=None, end_date=None,
                      status='close'):
    """
        get list of deals by type historically
    Parameters
    ----------
    deal_type
    canceled_only: default False
    completed_only: default False (meaning both completed and canceled)
    start_date: default None
    end_date: default None
    status: default 'close', also option 'announce', 'cancel'
    Returns
    -------

    """

    dm = get_deal_type_map(deal_type)
    if dm.empty:
        raise ValueError(f"Unable to find Spinoff code")
    code = dm.loc[dm.index[0], 'deal_type_code']
    deals = get_deal_types(type_id=code)
    if end_date is not None and start_date is not None:
        dls = get_deals_between(start_date, end_date, status)
        ix = np.where(np.isin(deals['deal_id'].to_numpy(), dls['deal_id'].to_numpy()))[0]
        deals = deals.iloc[ix]
    di = get_deal_info(deals['deal_id'].to_numpy(), start_date, end_date, status)
    deals = deals.merge(di, how='left', on='deal_id')
    iz = list(range(len(deals.index)))
    if len(iz) > 0:
        if canceled_only:
            ix = np.where(pd.notnull(deals['cancel_date']))[0]
            iz = np.intersect1d(iz, ix)
        if completed_only:
            ix = np.where(pd.notnull(deals['close_date']))[0]
            iz = np.intersect1d(iz, ix)
        # if start_date is not None:
        #     ix = np.where(deals['close_date'] >= util.parse_date(start_date))
        #     iz = np.intersect1d(iz, ix)
        # if end_date is not None:
        #     ix = np.where(deals['close_date'] <= util.parse_date(end_date))
        #     iz = np.intersect1d(iz, ix)
    display(f"Found {len(iz)} deals of type {dm.loc[dm.index[0], 'deal_type_desc']}")
    return deals.iloc[iz]


def get_deal_info(deal_ids, start_date=None, end_date=None, date_type='close'):
    """
    get basic deal information by deal id
    Parameters
    ----------
    deal_ids
    start_date: default None
    end_date: default None
    date_type: default 'close'

    Returns
    -------

    """
    if isinstance(deal_ids, numbers.Number):
        deal_ids = np.array([deal_ids])
    elif isinstance(deal_ids, list):
        deal_ids = np.array(deal_ids)
    elif isinstance(deal_ids, pd.Series) or isinstance(deal_ids, pd.DataFrame):
        deal_ids = deal_ids.to_numpy()
    if not isinstance(deal_ids, np.ndarray):
        raise ValueError(f"Deal IDs must be integer, array, or list")
    deal_ids = np.unique(deal_ids)
    missing = deal_ids
    global info
    if info is not None:
        if isinstance(info, pd.DataFrame):
            ix = np.where(np.isin(deal_ids, info['deal_id']))[0]
            missing = np.setdiff1d(missing, deal_ids[ix])
    date_str = 'close_date'
    if isinstance(date_type, str):
        date_type = date_type.strip().lower()
        if date_type in ('close', 'closed', 'complete', 'completed', 'finished'):
            date_str = 'close_date'
        elif date_type in ('announce', 'announced', 'announcement', 'declared'):
            date_str = 'announce_date'
        elif date_type in ('cancel', 'cancelled', 'cancellation'):
            date_str = 'cancel_date'
        else:
            date_str = 'close_date'
    if len(missing) > 0:
        conn = md.get_connection()
        try:
            query = f"select * from FactSetDataFeed.ma_v1.ma_deal_info where deal_id in "
            ids = missing.astype(str)
            suffix = f""
            if start_date is not None or end_date is not None:
                if start_date is not None:
                    cs = util.parse_date(start_date)
                    suffix = suffix + f"and {date_str} >= '{cs.strftime(util.YY_MM_DD_format)}'"
                if end_date is not None:
                    ce = util.parse_date(end_date)
                    suffix = suffix + f"and {date_str} <= '{ce.strftime(util.YY_MM_DD_format)}'"
            data = md.execute_batch(conn, query, ids, sql_suffix=suffix)
            data.loc[data.index, 'announce_date'] = util.parse_date(data.loc[data.index, 'announce_date'])
            data.loc[data.index, 'cancel_date'] = util.parse_date(data.loc[data.index, 'cancel_date'])
            data.loc[data.index, 'expected_close_date'] = util.parse_date(data.loc[data.index, 'expected_close_date'])
            data.loc[data.index, 'close_date'] = util.parse_date(data.loc[data.index, 'close_date'])
            data.loc[data.index, 'rumor_date'] = util.parse_date(data.loc[data.index, 'rumor_date'])
            if info is None or not isinstance(info, pd.DataFrame):
                info = data.copy()
            else:
                if info.empty:
                    info = data.copy()
                else:
                    info = pd.concat([info, data], axis=0, ignore_index=True)
                    info.drop_duplicates(subset=['deal_id'], keep='last', inplace=True)
                info.loc[info.index, 'deal_id'] = info.loc[info.index, 'deal_id'].astype('int64')
                info.loc[info.index, 'status_id'] = info.loc[info.index, 'status_id'].astype('int64')
                info.loc[info.index, 'purpose_id'] = info.loc[info.index, 'purpose_id'].astype('int64')
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get deal info due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal info due to exception")
            raise ee
    if info is None:
        display(f"No deal info found")
        return None
    ix = np.where(np.isin(info['deal_id'], deal_ids))[0]
    return info.iloc[ix].copy(deep=True)


def get_deal_terms(deal_ids, ver=None):
    """
    get basic deal terms by deal id
    Parameters
    ----------
    deal_ids
    ver: default None

    Returns
    -------

    """
    if isinstance(deal_ids, numbers.Number):
        deal_ids = np.array([deal_ids])
    elif isinstance(deal_ids, list):
        deal_ids = np.array(deal_ids)
    elif isinstance(deal_ids, pd.DataFrame) or isinstance(deal_ids, pd.Series):
        deal_ids = deal_ids.to_numpy()
    if not isinstance(deal_ids, np.ndarray):
        raise ValueError(f"Deal IDs must be integer, array, or list")
    deal_ids = np.unique(deal_ids)
    missing = deal_ids
    global terms
    if terms is not None:
        if isinstance(terms, pd.DataFrame):
            ix = np.where(np.isin(deal_ids, terms['deal_id']))[0]
            missing = np.setdiff1d(missing, deal_ids[ix])
    if len(missing) > 0:
        conn = md.get_connection()
        try:
            query = f"select * from FactSetDataFeed.ma_v1.ma_deal_terms where deal_id in "
            ids = missing.astype(str)
            data = md.execute_batch(conn, query, ids)
            if terms is None or not isinstance(terms, pd.DataFrame):
                terms = data.copy()
            else:
                terms = terms.combine_first(data)
                terms.update(data)
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get deal info due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal info due to exception")
            raise ee
    if terms is None:
        display(f"No deal terms found")
        return None
    ix = np.where(np.isin(terms['deal_id'], deal_ids))[0]
    if ver is not None:
        if isinstance(ver, numbers.Number):
            iz = np.where(terms['ver'] == ver)[0]
            ix = np.intersect1d(ix, iz)
    return terms.iloc[ix]


def get_deal_relationships(deal_ids):
    """

    Parameters
    ----------
    deal_ids

    Returns
    -------

    """
    if isinstance(deal_ids, numbers.Number):
        deal_ids = np.array([deal_ids])
    elif isinstance(deal_ids, list):
        deal_ids = np.array(deal_ids)
    elif isinstance(deal_ids, pd.DataFrame) or isinstance(deal_ids, pd.Series):
        deal_ids = deal_ids.to_numpy()
    if not isinstance(deal_ids, np.ndarray):
        raise ValueError(f"Deal IDs must be integer, array, or list")
    deal_ids = np.unique(deal_ids)
    missing = deal_ids
    global relationships
    if relationships is not None:
        if isinstance(relationships, pd.DataFrame):
            ix = np.where(np.isin(deal_ids, relationships['deal_id']))[0]
            missing = np.setdiff1d(missing, deal_ids[ix])
    if len(missing) > 0:
        conn = md.get_connection()
        try:
            query = f"select * from FactSetDataFeed.ma_v1.ma_deal_relationship where deal_id in "
            ids = missing.astype(str)
            data = md.execute_batch(conn, query, ids, 10000)
            r = get_roles()
            if relationships is None or not isinstance(relationships, pd.DataFrame):
                relationships = data.copy()
                relationships = relationships.merge(r, how='left', left_on='co_role_id', right_on='co_role_code')
                relationships.drop(columns='co_role_code', inplace=True)
            else:
                cols = relationships.columns
                relationships = relationships.combine_first(data)
                relationships.update(data)
                relationships.loc[relationships.index, 'co_role_id'] = relationships.loc[
                    relationships.index, 'co_role_id'].astype('int64')
                relationships.loc[relationships.index, 'deal_id'] = relationships.loc[
                    relationships.index, 'deal_id'].astype('int64')
                relationships = relationships[cols]
                roles.set_index('co_role_code', inplace=True)
                relationships.set_index('co_role_id', inplace=True)
                relationships.update(roles)
                relationships.reset_index(inplace=True)
                roles.reset_index(inplace=True)

        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get deal relationships due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal relationships due to exception")
            raise ee
    if relationships is None:
        display(f"No deal relationships found")
        return None
    ix = np.where(np.isin(relationships['deal_id'], deal_ids))[0]
    return relationships.iloc[ix]


def get_deal_relationships_by_entities(entity_ids, role_ids=None):
    """

    Parameters
    ----------
    entity_ids
    role_ids: default None

    Returns
    -------

    """
    if isinstance(entity_ids, str):
        entity_ids = np.array([entity_ids])
    elif isinstance(entity_ids, list):
        entity_ids = np.array(entity_ids)
    if not isinstance(entity_ids, np.ndarray):
        raise ValueError(f"Entity IDs must be integer, array, or list")
    entity_ids = np.unique(entity_ids)
    missing = entity_ids
    global relationships
    if relationships is not None:
        if isinstance(relationships, pd.DataFrame):
            ix = np.where(np.isin(entity_ids, relationships['factset_entity_id']))[0]
            missing = np.setdiff1d(missing, entity_ids[ix])
    if len(missing) > 0:
        conn = md.get_connection()
        try:
            query = f"select * from FactSetDataFeed.ma_v1.ma_deal_relationship where factset_entity_id in "
            data = md.execute_batch(conn, query, missing)
            r = get_roles()
            if relationships is None or not isinstance(relationships, pd.DataFrame):
                relationships = data.copy()
                relationships = relationships.merge(r, how='left', left_on='co_role_id', right_on='co_role_code')
                relationships.drop(columns='co_role_code', inplace=True)
            else:
                cols = relationships.columns
                relationships = relationships.combine_first(data)
                relationships.update(data)
                relationships = relationships[cols]
                roles.set_index('co_role_code', inplace=True)
                relationships.set_index('co_role_id', inplace=True)
                relationships.update(roles)
                relationships.reset_index(inplace=True)
                roles.reset_index(inplace=True)
                relationships.loc[relationships.index, 'co_role_id'] = \
                    relationships.loc[relationships.index, 'co_role_id'].astype('int64')
                relationships.loc[relationships.index, 'deal_id'] = \
                    relationships.loc[relationships.index, 'deal_id'].astype('int64')
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get deal relationships due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal relationships due to exception")
            raise ee
    if relationships is None:
        display(f"No deal relationships found")
        return None
    ix = np.where(np.isin(relationships['factset_entity_id'], entity_ids))[0]
    if role_ids is not None:
        if isinstance(role_ids, numbers.Number):
            iz = np.where(relationships['co_role_id'] == role_ids)[0]
            ix = np.intersect1d(ix, iz)
        elif isinstance(role_ids, list) or isinstance(role_ids, np.ndarray):
            iz = np.where(np.isin(relationships['co_role_id'], role_ids))[0]
            ix = np.intersect1d(ix, iz)
    return relationships.iloc[ix]


def get_deals_between(start_date, end_date, date_type='close'):
    """
    get basic deal information by deal id
    Parameters
    ----------
    start_date
    end_date
    date_type: default 'close', also available 'announcement', and 'cancellation'

    Returns
    -------

    """
    date_str = 'close_date'
    status_type = 'closed'
    if isinstance(date_type, str):
        date_type = date_type.lower().strip()
        if date_type in ('close', 'closed', 'complete', 'completed', 'completion'):
            date_str = 'close_date'
        elif date_type in ('announce', 'announcement', 'announced', 'propose', 'proposal', 'proposed'):
            date_str = 'announce_date'
            status_type = 'announced'
        elif date_type in ('cancel', 'cancellation', 'fail', 'failure', 'abort', 'aborted'):
            date_str = 'cancel_date'
            status_type = 'cancelled'
        else:
            date_str = 'close_date'

    conn = md.get_connection()
    try:
        query = f"select * from FactSetDataFeed.ma_v1.ma_deal_info where "
        suffix = f""
        cs = util.parse_date(start_date)
        suffix = suffix + f"{date_str} >= '{cs.strftime(util.YY_MM_DD_format)}'"
        ce = util.parse_date(end_date)
        suffix = suffix + f"and {date_str} <= '{ce.strftime(util.YY_MM_DD_format)}'"
        query = query + suffix
        cursor = md.get_cursor(conn)
        cursor.execute(query)
        records = cursor.fetchall()
        data = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        data.loc[data.index, 'announce_date'] = util.parse_date(data.loc[data.index, 'announce_date'])
        data.loc[data.index, 'cancel_date'] = util.parse_date(data.loc[data.index, 'cancel_date'])
        data.loc[data.index, 'expected_close_date'] = util.parse_date(data.loc[data.index, 'expected_close_date'])
        data.loc[data.index, 'close_date'] = util.parse_date(data.loc[data.index, 'close_date'])
        data.loc[data.index, 'rumor_date'] = util.parse_date(data.loc[data.index, 'rumor_date'])
        global info
        if info is None or not isinstance(info, pd.DataFrame):
            info = data.copy()
        else:
            if info.empty:
                info = data.copy()
            else:
                info = pd.concat([info, data], axis=0, ignore_index=True)
                info.drop_duplicates(subset=['deal_id'], keep='last', inplace=True)
            info.loc[info.index, 'deal_id'] = info.loc[info.index, 'deal_id'].astype('int64')
            info.loc[info.index, 'status_id'] = info.loc[info.index, 'status_id'].astype('int64')
            info.loc[info.index, 'purpose_id'] = info.loc[info.index, 'purpose_id'].astype('int64')
        cursor.close()
        conn.close()
        display(f"found {len(data.index)} deals {status_type} between {cs} and {ce}")
        return data
    except db.DatabaseError as dbe:
        display(f"{dbe}")
        display(f"Unable to get deal info due to database error")
        raise dbe
    except Exception as ee:
        display(f"{ee}")
        display(f"Unable to load deal info due to exception")
        raise ee


def get_roles(role_id=None):
    global roles
    if roles is None:
        query = 'select * from FactSetDataFeed.ref_v2.ma_company_role_map'
        try:
            conn = md.get_connection()
            cursor = md.get_cursor(conn)
            cursor.execute(query)
            records = cursor.fetchall()
            roles = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to load deal company role map due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal company role map due to exception")
            raise ee
    if roles is None:
        return None
    if roles.empty:
        return roles
    if role_id is not None and isinstance(role_id, numbers.Number):
        ix = np.where(roles['co_role_id'] == int(role_id))[0]
    else:
        ix = list(range(len(roles.index)))
    return roles.iloc[ix]


def get_entity_transactions(entity_ids):
    """

    Parameters
    ----------
    entity_ids

    Returns
    -------

    """
    if isinstance(entity_ids, str):
        entity_ids = np.array([entity_ids])
    elif isinstance(entity_ids, list):
        entity_ids = np.array(entity_ids)
    elif isinstance(entity_ids, pd.DataFrame) or isinstance(entity_ids, pd.Series):
        entity_ids = entity_ids.to_numpy()
    if not isinstance(entity_ids, np.ndarray):
        raise ValueError(f"Entity IDs must be integer, array, or list")
    entity_ids = np.unique(entity_ids)
    missing = entity_ids
    global entity_transactions
    if entity_transactions is not None:
        if isinstance(entity_transactions, pd.DataFrame):
            ix = np.where(np.isin(entity_ids, entity_transactions['factset_entity_id']))[0]
            missing = np.setdiff1d(missing, entity_ids[ix])
    if len(missing) > 0:
        conn = md.get_connection()
        try:
            query = f"select * from FactSetDataFeed.ma_v1.ma_coverage where factset_entity_id in "
            data = md.execute_batch(conn, query, missing)
            if entity_transactions is None or not isinstance(entity_transactions, pd.DataFrame):
                entity_transactions = data.copy()
            else:
                cols = entity_transactions.columns
                entity_transactions = entity_transactions.combine_first(data)
                entity_transactions.update(data)
                entity_transactions = entity_transactions[cols]
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to get deal entity_transactions due to database error")
            raise dbe
        except Exception as ee:
            display(f"{ee}")
            display(f"Unable to load deal entity_transactions due to exception")
            raise ee
    if entity_transactions is None:
        display(f"No deal entity_transactions found")
        return None
    ix = np.where(np.isin(entity_transactions['factset_entity_id'], entity_ids))[0]
    return entity_transactions.iloc[ix]


@ft.lru_cache()
def get_status_map(code=None):
    global status_map
    if status_map is None:
        query = f"select * from FactSetDataFeed.ref_v2.ma_closing_status_map"
        conn = md.get_connection()
        cursor = md.get_cursor(conn)
        cursor.execute(query)
        records = cursor.fetchall()
        status_map = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
    if code is not None:
        if isinstance(code, numbers.Number):
            ix = np.where(status_map['status_code'] == code)[0]
        elif isinstance(code, str):
            ix = np.where(status_map['status_desc'] == code.title())
        else:
            return status_map
        return status_map.iloc[ix]
    else:
        return status_map


@ft.lru_cache()
def get_purpose_map(code=None):
    global purpose_map
    if purpose_map is None:
        query = f"select * from FactSetDataFeed.ref_v2.ma_acq_purpose_map"
        conn = md.get_connection()
        cursor = md.get_cursor(conn)
        cursor.execute(query)
        records = cursor.fetchall()
        purpose_map = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
    if code is not None:
        if isinstance(code, numbers.Number):
            ix = np.where(purpose_map['purpose_code'] == code)[0]
        elif isinstance(code, str):
            ix = np.where(purpose_map['purpose_desc'] == code.title())
        else:
            return purpose_map
        return purpose_map.iloc[ix]
    else:
        return purpose_map


@ft.lru_cache()
def get_attitude_map(code=None):
    global attitude_map
    if attitude_map is None:
        query = f"select * from FactSetDataFeed.ref_v2.ma_deal_attitude_map"
        conn = md.get_connection()
        cursor = md.get_cursor(conn)
        cursor.execute(query)
        records = cursor.fetchall()
        attitude_map = pd.DataFrame.from_records(records, columns=[col[0] for col in cursor.description])
    if code is not None:
        if isinstance(code, numbers.Number):
            ix = np.where(attitude_map['attitude_code'] == code)[0]
        elif isinstance(code, str):
            ix = np.where(attitude_map['attitude_desc'] == code.title())
        else:
            return attitude_map
        return attitude_map.iloc[ix]
    else:
        return attitude_map


def get_entities(sec_ids):
    """
    by regional IDs retrieve entities by which
    Parameters
    ----------
    sec_ids : regional IDs

    Returns
    -------
        regional_id as index, security_id, entity_id
    """
    if isinstance(sec_ids, str):
        sec_ids = np.array([sec_ids])
    elif isinstance(sec_ids, list):
        sec_ids = np.array(sec_ids)
    elif isinstance(sec_ids, pd.DataFrame) or isinstance(sec_ids, pd.Series) or isinstance(sec_ids, pd.Index):
        sec_ids = sec_ids.to_numpy()
    sec_ids = sec_ids.astype('str')
    sec_ids = np.char.strip(sec_ids)
    sec_ids = np.unique(sec_ids)
    ref = md.get_security_ids(sec_ids)
    if ref is None or ref.empty:
        display(f"No security ID found for sec_ids: returning None")
        return None
    global entities
    if entities is not None and not entities.empty:
        missing = np.setdiff1d(ref['security_id'], entities['security_id'])
        entities = entities.combine_first(ref)
    else:
        entities = ref.copy()
        entities['entity_id'] = None
        entities['start_date'] = None
        entities['end_date'] = None
        missing = np.unique(entities['security_id'].to_numpy())
    if len(missing):
        query = f"select * from FactSetDataFeed.ma_v1.ma_sec_entity_hist where fsym_id in "
        conn = md.get_connection()
        try:
            data = md.execute_batch(conn, query, missing)
            for ix, s in enumerate(data['fsym_id']):
                iy = np.where(entities['security_id'] == s)[0]
                if len(iy) == 0:
                    continue
                entities.loc[entities.index[iy], 'entity_id'] = data.loc[data.index[ix], 'factset_entity_id']
                entities.loc[entities.index[iy], 'start_date'] = data.loc[data.index[ix], 'start_date']
                entities.loc[entities.index[iy], 'end_date'] = data.loc[data.index[ix], 'end_date']
        except db.DatabaseError as dbe:
            display(f"{dbe}")
            display(f"Unable to load security/entity map due to database error")
        except Exception as ex:
            display(f"{ex}")
            display(f"Unable to load security/entity map due to exception")

    if entities is None or entities.empty:
        display(f"No entities found; returning None")
        return None
    ix = np.where(np.isin(entities.index, sec_ids))[0]
    return entities.iloc[ix]


def get_mergers(start_date=None, end_date=None, deal_ids=None, from_regional=None, to_regional=None, from_security=None,
                to_security=None, from_entity=None, to_entity=None, buyer_regional=None, buyer_security=None,
                buyer_entity=None):
    """
    get transacted merger details from previously cached merger data
    Parameters
    ----------
    start_date
    end_date
    deal_ids
    from_regional
    to_regional
    from_security
    to_security
    from_entity
    to_entity
    buyer_regional
    buyer_security
    buyer_entity

    Returns
    -------

    """
    global ma_cache
    if ma_cache is None:
        location = os.path.join(util.default_output_location('market'), 'ma')
        file = os.path.join(location, 'mergers.qd')
        if not util.exists(file):
            display(f"Unable to find pre-cached merger data at {file}")
            raise FileNotFoundError(f"file: {file}")
        ma_cache = util.load_data(file)
    ix = np.array(range(len(ma_cache.index)))
    if start_date is not None:
        x = util.parse_date(start_date)
        ix = np.intersect1d(ix, np.where(ma_cache['date'] >= x)[0])
    if end_date is not None:
        x = util.parse_date(end_date)
        ix = np.intersect1d(ix, np.where(ma_cache['date'] <= x)[0])
    if deal_ids is not None:
        if isinstance(deal_ids, numbers.Number):
            deal_ids = np.array([deal_ids])
        elif isinstance(deal_ids, list):
            deal_ids = np.array(deal_ids)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['deal'], deal_ids))[0])
    if from_regional is not None:
        if isinstance(from_regional, str):
            from_regional = np.array([from_regional])
        elif isinstance(from_regional, list):
            from_regional = np.array(from_regional)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['from_regional'], from_regional))[0])
    if to_regional is not None:
        if isinstance(to_regional, str):
            to_regional = np.array([to_regional])
        elif isinstance(to_regional, list):
            to_regional = np.array(to_regional)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['from_regional'], to_regional))[0])
    if from_security is not None:
        if isinstance(from_security, str):
            from_security = np.array([from_security])
        elif isinstance(from_security, list):
            from_security = np.array(from_security)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['from_security'], from_security))[0])
    if to_security is not None:
        if isinstance(to_security, str):
            to_security = np.array([to_security])
        elif isinstance(to_security, list):
            to_security = np.array(to_security)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['to_security'], to_security))[0])
    if from_entity is not None:
        if isinstance(from_entity, str):
            from_entity = np.array([from_entity])
        elif isinstance(from_entity, list):
            from_entity = np.array(from_entity)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['from_entity'], from_entity))[0])
    if to_entity is not None:
        if isinstance(to_entity, str):
            to_entity = np.array([to_entity])
        elif isinstance(to_regional, list):
            to_entity = np.array(to_entity)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['to_entity'], to_entity))[0])
    if buyer_security is not None:
        if isinstance(buyer_security, str):
            buyer_security = np.array([buyer_security])
        elif isinstance(buyer_security, list):
            buyer_security = np.array(buyer_security)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['buyer_security'], buyer_security))[0])
    if buyer_entity is not None:
        if isinstance(buyer_entity, str):
            buyer_entity = np.array([buyer_entity])
        elif isinstance(buyer_entity, list):
            buyer_entity = np.array(buyer_entity)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['buyer_entity'], buyer_entity))[0])
    if buyer_regional is not None:
        if isinstance(to_entity, str):
            to_entity = np.array([to_entity])
        elif isinstance(to_regional, list):
            to_entity = np.array(to_entity)
        ix = np.intersect1d(ix, np.where(np.isin(ma_cache['to_entity'], to_entity))[0])

    return ma_cache.iloc[ix]


def cache_public_merger_acquisitions(start_date, end_date, save_flag=False, overwrite_flag=False, types=None):
    """

    Parameters
    ----------
    start_date
    end_date
    save_flag: default False
    overwrite_flag: default False
    types: default None

    Returns
    -------

    """
    if types is None:
        types = np.array(['Acquisition / Merger', 'Majority Stake'])
    if isinstance(types, str):
        types = np.array([types])
    elif isinstance(types, list):
        types = np.array(types)
    elif not isinstance(types, np.ndarray):
        raise ValueError(f"Wrong type of corporate action type")
    deals = pd.DataFrame()
    for t in types:
        dls = get_merger_acquisitions(start_date, end_date, 'announce', True, True, False, types=t)
        if deals.empty:
            deals = dls
        else:
            deals = pd.concat((deals, dls), axis=0, ignore_index=True)
        display(f"=====> {t} : {len(np.unique(dls['deal_id']))} deals <=====")
    if deals is None or deals.empty:
        display(f"No public merger acquisitions found")
        return None
    sids = deals['sec_id'].to_numpy()
    dom = md.get_domiciles(sids)
    deals['domicile'] = None
    deals['name'] = None
    for d in deals.index:
        ad = deals.loc[d, 'announce_date']
        ts = deals.loc[d, 'sec_id']
        ix = np.where(np.logical_and(dom['start_date'] <= ad, dom['end_date'] > ad))[0]
        iy = np.where(dom['sec_id'] == ts)[0]
        iz = np.intersect1d(ix, iy)
        if len(iz) > 0:
            deals.loc[d, 'domicile'] = dom.loc[dom.index[iz[0]], 'domicile']
            deals.loc[d, 'name'] = dom.loc[dom.index[iz[0]], 'name']
    if save_flag:
        location = os.path.join('market', 'ma', 'public', 'announce')
        if not util.exists(location):
            util.makedirs(location)
            display(f"Created {location}")
        file = os.path.join(location, "mergers.qd")
        if not util.exists(file):
            util.save_data(deals, file)
            display(f"Successfully saved {len(np.unique(deals['deal_id']))} deals between "
                    f"{np.min(deals['announce_date'])} and {np.max(deals['announce_date'])}")
            display(f"{file}")
        else:
            if overwrite_flag:
                util.save_data(deals, file)
                display(f"Successfully overwritten {len(np.unique(deals['deal_id']))} deals between "
                        f"{np.min(deals['announce_date'])} and {np.max(deals['announce_date'])}")
                display(f"{file}")
            else:
                data = util.load_data(file)
                dts = np.unique(deals['deal_type_id'])
                ix = np.where(np.isin(data['announce_date'].to_numpy(), deals['announce_date'].to_numpy()))[0]
                if len(ix) > 0:
                    old = np.array([], dtype='int64')
                    for p in dts:
                        iy = np.where(data['deal_type_id'] == p)[0]
                        iz = np.intersect1d(ix, iy)
                        display(f"Deal type id {p}: {len(iz)} found in file cache; to be removed")
                        old = np.union1d(old, iz)
                    if len(old) > 0:
                        data.drop(data.index[old], axis=0, inplace=True)
                        display(f"Dropped prior {len(old)} rows in {len(dts)} types between "
                                f"{np.min(deals['announce_date'])} and {np.max(deals['announce_date'])}")
                data = pd.concat((data, deals), axis=0, ignore_index=True)
                util.save_data(data, file)
                display(f"Successfully added additional {len(np.unique(deals['deal_id']))} deals in "
                        f"{len(dts)} types between {np.min(deals['announce_date'])} and "
                        f"{np.max(deals['announce_date'])}")
                display(f"{file}")
                display(f"Total {len(np.unique(data['deal_id']))} deals in {len(np.unique(data['deal_type_id']))} types"
                        f" between {np.min(data['announce_date'])} and {np.max(data['announce_date'])}")
    return deals


def get_cached_public_mergers(start_date=None, end_date=None, status='announce', domiciles=None, role=None, types=None):
    """

    Parameters
    ----------
    start_date: default None
    end_date: default None
    status: default 'announce'
    domiciles: default None
    role: default None
    types: default None, options include 1 for Acquisition / Merger, 39 for Majority Stake

    Returns
    -------

    """
    location = os.path.join('market', 'ma', 'public', 'announce')
    if not util.exists(location):
        util.makedirs(location)
        display(f"Created {location}")
    file = os.path.join(location, "mergers.qd")
    if not util.exists(file):
        display(f"caching directory not found: {location}")
        return None
    data = util.load_data(file)
    if start_date is None and end_date is None:
        return data
    if not isinstance(status, str):
        status = 'announce'
    if status in ('announce', 'announced', 'announcement'):
        dstr = 'announce_date'
    elif status in ('close', 'closed', 'completion', 'complete', 'closure'):
        dstr = 'close_date'
    elif status in ('cancel', 'cancelled', 'cancellation', 'fail', 'failure', 'failed'):
        dstr = 'cancel_date'
    else:
        raise ValueError(f"No valid status type: {status}")
    days = util.load_business_days('GL', start_date, end_date)
    ix = np.where(np.logical_and(data[dstr] >= days[0], data[dstr] <= days[-1]))[0]
    if domiciles is not None:
        if isinstance(domiciles, str):
            domiciles = np.array([domiciles])
        elif isinstance(domiciles, list):
            domiciles = np.array(domiciles)
        iy = np.where(np.isin(data['domicile'].to_numpy(), domiciles))[0]
        ix = np.intersect1d(ix, iy)
    if role is not None:
        if isinstance(role, str):
            role = np.array([role])
        elif isinstance(role, list):
            role = np.array(role)
        iy = np.where(np.isin(data['role'].to_numpy(), role))[0]
        ix = np.intersect1d(ix, iy)
    if types is not None:
        if isinstance(types, numbers.Number):
            types = np.array([types])
        elif isinstance(types, list):
            types = np.array(types)
        iy = np.where(np.isin(data['deal_type_id'].to_numpy(), types))[0]
        ix = np.intersect1d(ix, iy)
    dom = data.loc[data.index[ix], 'domicile'].to_numpy()
    dom = dom[np.where(pd.notnull(dom))[0]]
    display(f"Total {len(np.unique(data.loc[data.index[ix], 'deal_id']))} deals affecting {role} {len(ix)} securities "
            f"in {len(np.unique(dom))} domiciles {dstr} between {days[0]} and {days[-1]}")
    return data.iloc[ix]


if __name__ == "__main__":
    a = int(sys.argv[1])
    b = int(sys.argv[2])
    log_file = os.path.join(util.default_output_location('reports'), 'logs', 'ma',
                            f'merger_caching_{a}_{b}_{util.current_time("%Y-%m-%d-%H-%M-%S")}.txt')
    util.sink(log_file)
    util.display(f"Caching all mergers acquisitions")
    process_merger_acquisitions3(a, b, True)
    util.display(f"Caching mergers involving a public entity")
    cache_public_merger_acquisitions(a, b, True)
