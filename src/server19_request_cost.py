"""Inclusive phase timings for slow server requests / 服务端分段计时。"""
def install_cost_observer(stage, gacha, policy, server):
    """Attribute the next hardware spike without changing request behavior.

Phase times are inclusive/nested and must not be added together.
"""
    from functools import wraps
    import threading
    import time
    local = threading.local()
    original_event = server.event
    targets = ('GachaReq', 'GetClearStageActivityReq', 'GetOpenworldReq',
               'GetCollectCabinReq', 'GetGachaDisplayReq', 'GetMissionDataReq',
               'GetMasterPupilApplyReq', 'GetStageDropDisplayReq')

    def event(kind, **values):
        if kind == 'game_request':
            request = values.get('command')
            local.cost = {'request': request, 'phases': {}} if request in targets else None
        if kind == 'game_gacha_wire' and getattr(local, 'cost', None):
            decoded = server.proto.decode_message(values['command'], bytes.fromhex(values['body_hex']))
            local.cost.update(pool_type=decoded.get('type'), pull_num=decoded.get('num'))
        result = original_event(kind, **values)
        cost = getattr(local, 'cost', None)
        if cost and (kind in ('game_error', 'game_disconnected') or
                     (kind == 'game_response' and values.get('command') == cost['request'][:-3] + 'Rsp')):
            local.cost = None
            original_event('server_request_cost', **cost, inclusive=True,
                           elapsed_ms=values.get('elapsed_ms'))
        return result

    def wrap(module, name, label):
        original = getattr(module, name)

        @wraps(original)
        def measured(*args, **kwargs):
            cost = getattr(local, 'cost', None)
            if cost is None:
                return original(*args, **kwargs)
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                phase = cost['phases'].setdefault(label, {'calls': 0, 'ms': 0.0})
                phase['calls'] += 1
                phase['ms'] += (time.perf_counter() - started) * 1000
        setattr(module, name, measured)

    for name in ('refresh_account', '_read', '_save', '_sync', 'copy_account'):
        wrap(stage, name, name)
    wrap(server, 'response', 'business_response')
    wrap(gacha, 'deepcopy', 'gacha_copy')
    wrap(policy, 'deepcopy', 'draw_copy')
    for name in ('response', '_draw', '_roll', '_table_for', '_grant', 'notification_snapshot'):
        wrap(gacha, name, 'gacha' + name)
    for name in ('catalog', 'choices', 'select', 'commit', 'draw'):
        wrap(policy, name, 'policy_' + name)
    server.event = event
