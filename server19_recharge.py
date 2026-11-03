"""User-authorized offline recharge; prices are presentation, never payments."""
from copy import deepcopy
from pathlib import Path
import time
import uuid

import server19_stage as stage

# Ordinary crystal denominations. The smallest pack hides the requested egg.
PACKS = tuple({'name': 'local_hcoin_' + str(n), 'desc': str(n) + '水晶',
               'type': 1, 'pay_hcoin': n, 'free_hcoin': 0,
               'price': rmb * 100, 'id': i + 1, 'is_add_hcoin': True}
              for i, (rmb, n) in enumerate(((6, 60), (30, 300), (98, 980),
                                            (198, 1980), (328, 3280), (648, 6480))))
BY_NAME = {p['name']: p for p in PACKS}


def response(name, account, request_values=None, *, account_path=None, enabled=False):
    if not enabled:
        return None
    import server19_recharge_welfare as welfare
    result=welfare.response(name,account,request_values,account_path=account_path)
    if result is not None:
        return result
    if name == 'GetProductListReq':
        return 'GetProductListRsp', {'retcode': 0, 'product_list': deepcopy(PACKS)}
    if name != 'ReportClickRechargeButtonNotify':
        return None
    req = request_values or {}
    pack = BY_NAME.get(req.get('product_name'))
    token = req.get('price', '')  # Local client replaces telemetry price with UUID.
    try:
        order = uuid.UUID(token)
        valid = str(order) == token and order.version == 4
    except (ValueError, AttributeError, TypeError):
        valid = False
    if not pack or not valid or req.get('currency_code') != 'CNY':
        return 'RechargeFinishNotify', {'retcode': 1}
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        runtime = current.setdefault('local_recharge_runtime', {'schema': 1, 'orders': {}})
        if runtime.get('schema') != 1 or not isinstance(runtime.get('orders'), dict):
            raise ValueError('Unsupported local recharge state')
        previous = runtime['orders'].get(token)
        if previous:
            stage._sync(account, before)
            if previous['product'] != pack['name']:
                return 'RechargeFinishNotify', {'retcode': 1}
            # Repeat delivery updates the wallet only: never a second reward popup.
            return 'GetMainDataRsp', {'retcode': 0, **deepcopy(before['main'])}
        amount = 10000 if pack['pay_hcoin'] == 60 else pack['pay_hcoin']
        balance = current['main']['hcoin']
        if type(balance) is not int or not 0 <= balance <= 0xffffffff - amount:
            return 'RechargeFinishNotify', {'retcode': 1}
        current['main']['hcoin'] = balance + amount
        runtime['orders'][token] = {'product': pack['name'], 'hcoin': amount,
                                    'time': int(time.time()), 'balance': balance + amount}
        stage._save(path, before, current)
        stage._sync(account, current)
    return 'RechargeFinishNotify', {
        'retcode': 0, 'product_name': pack['name'], 'product_desc': pack['desc'],
        'pay_hcoin': amount, 'free_hcoin': 0, 'is_add_hcoin': True,
        'channel_name': 'local', 'channel_order_no': token}


def notification_snapshot(account):
    return [('GetMainDataRsp', {'retcode': 0, **deepcopy(account['main'])})]
