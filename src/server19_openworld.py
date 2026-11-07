"""Opt-in first-cycle Sakura protocol service; native requests drive progress.

No account is enabled on import. Catalog configuration is separate from device
deployment. Original 1.9 serializer/retcode evidence is recorded in the audit.
"""
from copy import deepcopy
import json
from pathlib import Path
import time

import server19_stage as stage
import server19_commissions as commissions
import server19_cooking as cooking

_CATALOG = None
_COMMISSIONS = None
_COOKING = None
REQUESTS = frozenset({
    'GetOpenworldReq', 'GetOpenworldStageReq', 'OpenworldStageBeginReq',
    'OpenworldStageEndReq', 'ReportOpenworldSpawnPointReq',
    'AcceptOpenworldStoryReq', 'SetOpenworldStoryProgressReq',
    'TakeOpenworldStoryRewardReq',
    'TakeOpenworldCycleFinishRewardReq', 'AddServantExpReq', 'TakeServantCollectRewardReq',
}) | commissions.REQUESTS | cooking.REQUESTS


def configure_cooking(path):
    """Candidate only until explicitly enabled by the deployment launcher."""
    global _COOKING
    _COOKING = cooking.Cooking(path) if path else None


def configure_commissions(path):
    """Opt-in only; no live account writes or automatic activation."""
    global _COMMISSIONS
    _COMMISSIONS = commissions.Commissions(path) if path else None


def configure(path):
    """Explicitly select a reviewed catalog; never edit a saved account here."""
    global _CATALOG
    data = json.loads(Path(path).read_bytes())
    cycle = data['cycle']
    if (cycle['cycle'], cycle['level'], cycle['endstory'], cycle['finishreward']) != (1, 16, 111, 965022):
        raise ValueError('First-cycle configuration changed')
    expected_cycle_reward = dict(exp=0, scoin=0, hcoin=0, stamina=0,
        skill_point=0, friends_point=0, duty_point=0,
        item_list=[dict(id=20053, level=15, num=1), dict(id=30020, level=15, num=1), dict(id=7033, level=0, num=3)])
    if data['cycle_reward'] != expected_cycle_reward:
        raise ValueError('First-cycle reward changed; audit required')
    rows = data['stories']
    second = data.get('second_cycle')
    expected_ids = list(range(101, 112))
    if second:
        if (second['cycle'], second['level'], second['needstory'], second['endstory'], second['finishreward']) != (2, 30, 111, 207, 965023):
            raise ValueError('Second-cycle configuration changed')
        expected_ids += list(range(201, 208))
        expected = dict(exp=0, scoin=0, hcoin=0, stamina=0, skill_point=0,
                        friends_point=0, duty_point=0, item_list=[dict(id=10211, level=0, num=3),
                        dict(id=2005, level=0, num=50), dict(id=8003, level=0, num=1)])
        if data['second_cycle_reward'] != expected:
            raise ValueError('Second-cycle reward changed')
    third = data.get('third_cycle')
    if third:
        if not second or (third['cycle'], third['level'], third['needstory'], third['endstory'], third['finishreward']) != (3, 35, 207, 308, 965024):
            raise ValueError('Third-cycle configuration changed')
        expected_ids += list(range(301, 309))
        expected = dict(exp=0, scoin=0, hcoin=0, stamina=0, skill_point=0,
                        friends_point=0, duty_point=0, item_list=[dict(id=10211, level=0, num=3),
                        dict(id=5552, level=0, num=9), dict(id=8003, level=0, num=1)])
        if data['third_cycle_reward'] != expected:
            raise ValueError('Third-cycle reward changed')
    fourth = data.get('fourth_cycle')
    if fourth:
        if not third or (fourth['cycle'], fourth['level'], fourth['needstory'], fourth['endstory'], fourth['finishreward']) != (4, 42, 308, 411, 965050):
            raise ValueError('Fourth-cycle configuration changed')
        expected_ids += list(range(401, 412))
        expected = dict(exp=0, scoin=0, hcoin=0, stamina=0, skill_point=0,
                        friends_point=0, duty_point=0, item_list=[dict(id=5591, level=0, num=15),
                        dict(id=5552, level=0, num=9), dict(id=8003, level=0, num=1)])
        if data['fourth_cycle_reward'] != expected:
            raise ValueError('Fourth-cycle reward changed')
    if [r['StoryID'] for r in rows] != expected_ids:
        raise ValueError('Unsupported story catalog')
    for row in rows:
        identity = row['StoryID']
        if (row['Cycle'], row['StoryArea'], row['StoryType'], row['PreStory']) != (
                identity // 100, 102 if 408 <= identity <= 411 else 101, 1,
                [308 if identity == 401 else 207 if identity == 301 else 111 if identity == 201 else identity - 1 if identity > 101 else 0]):
            raise ValueError('Story ordering changed; audit required')
        if row['MaxCount'] not in ((2,) if identity == 308 else (1, 3, 5)) or row['HuntRewardEXp'] != 0:
            raise ValueError('Unsupported progress or hunt EXP')
        reward = data['rewards'][str(row['HuntRewardItem'])]
        # Source first-cycle rewards contain only coins and crystals.
        if any(reward[k] for k in ('exp', 'stamina', 'skill_point',
                                  'friends_point', 'duty_point')):
            raise ValueError('Additional reward business requires an audit')
        if reward['item_list'] and not (401 <= identity <= 411 and reward['item_list'] ==
                [dict(id=5591, level=0, num=4 if identity <= 404 else 5 if identity <= 407 else 6)]):
            raise ValueError('Additional story items require audit')
        for key in ('scoin', 'hcoin'):
            stage._u32(reward[key], key)
    _CATALOG = deepcopy(data)


def _cycle_configs():
    return {number: _CATALOG[key] for number, key in
            ((1, 'cycle'), (2, 'second_cycle'), (3, 'third_cycle'), (4, 'fourth_cycle')) if _CATALOG.get(key)}


def _world(account):
    world = account.setdefault('openworld_data', {})
    # Do not replace an existing later-cycle save with this bounded candidate.
    if world.get('cycle', 0) not in (0, 1, *_cycle_configs()):
        raise ValueError('Catalog cannot manage this later-cycle save')
    world['cycle'] = world.get('cycle') or 1
    for name in ('finish_story_id_list', 'cur_story_list', 'event_list',
                 'over_view_list', 'cook_list', 'event_stat_list'):
        world.setdefault(name, [])
    world.setdefault('quest_data', {'is_open': False, 'quest_list': []})
    # Native CurrentMissionCanAccept70249 compares UnlockQuestLv against this
    # even for main stories. Level1 is the source's initial tier, not an open
    # commission or a completed emergency quest.
    world['quest_data'].setdefault('level', 1)
    world.setdefault('servant_level', 0)
    world.setdefault('servant_exp', 0)
    world.setdefault('period_max_quest_num', 0)
    world.setdefault('period_finish_quest_num', 0)
    # Approved story progression: no calendar gate or cycle-reward prerequisite.
    # Old completed saves become eligible through a real client request as well.
    for number, config in _cycle_configs().items():
        if number > world['cycle'] and config['needstory'] in world['finish_story_id_list']:
            world['cycle'] = number
    if _CATALOG.get('fourth_cycle') and 405 in world['finish_story_id_list'] and not world['servant_level']:
        world['servant_level'] = 1
    return world


def _runtime(account):
    return account.setdefault('openworld_runtime', {
        'schema': 1, 'active': None, 'avatars': [], 'receipts': {},
    })


def _snapshot_avatars(runtime, values):
    rows = values.get('avatar_list', [])
    allowed = set(runtime['active']['avatar_ids']) if runtime['active'] else set()
    if not isinstance(rows, list):
        raise ValueError('Invalid avatar snapshot')
    seen = set()
    saved = {r['avatar_id']: deepcopy(r) for r in runtime['avatars']}
    for row in rows:
        identity = row.get('avatar_id')
        if identity not in allowed or identity in seen:
            raise ValueError('Avatar snapshot does not match the active team')
        seen.add(identity)
        result = saved.setdefault(identity, {'avatar_id': identity})
        for key in ('hp_percent', 'sp_percent', 'revive_time'):
            if key in row:
                value = stage._u32(row[key], key)
                if key.endswith('_percent') and value > 100:
                    raise ValueError('Invalid avatar percentage')
                result[key] = value
    runtime['avatars'] = list(saved.values())


def _handle(name, account, values):
    world, runtime = _world(account), _runtime(account)
    import server19_sakura_areas as areas
    area_teams = areas.state(account, _CATALOG, time.time())
    if _COMMISSIONS:
        _COMMISSIONS.state(account, time.time())
        if name in commissions.REQUESTS:
            return _COMMISSIONS.handle(name, account, values, time.time())
    if _COOKING:
        _COOKING.state(account, time.time())
        if name in cooking.REQUESTS:
            return _COOKING.handle(account, values, time.time())
    if name == 'TakeServantCollectRewardReq':
        # The historical passive collection reward schedule is not recovered.
        # Preserve this missing feature rather than acknowledge a fake claim.
        return {'retcode': 1}
    if name == 'AddServantExpReq':
        from server19_sakura_servant import add_exp
        return add_exp(account, values, _CATALOG)
    if name == 'GetOpenworldReq':
        return dict(deepcopy(world), retcode=0, data_type=values.get('data_type', 0))
    if name == 'GetOpenworldStageReq':
        # First-cycle source has multiAreaShow=0: no cross-area locks yet.
        return dict(retcode=0, avatar_list=deepcopy(runtime['avatars']),
                    cook_buffer_list=deepcopy(account.get('cooking_runtime', {}).get('buffs', [])) if _COOKING else [], area_list=deepcopy(area_teams))
    if name == 'OpenworldStageBeginReq':
        cycle_config = _cycle_configs()[world['cycle']]
        if account['main'].get('level', 0) < cycle_config['level']:
            return {'retcode': 2}
        if values.get('area_id') not in ((101, 102) if _CATALOG.get('fourth_cycle') else (101,)):
            return {'retcode': 6}
        ids = values.get('avatar_id_list', [])
        owned = {r['avatar_id'] for r in account.get('avatar_list', []) if r.get('star', 0) > 0}
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 3
                or any(type(i) is not int or i not in owned for i in ids)
                or len(set(ids)) != len(ids)):
            return {'retcode': 3}
        if _CATALOG.get('fourth_cycle') and not areas.enter(account, _CATALOG, values['area_id'], ids, time.time()):
            return {'retcode': 6}
        runtime['active'] = {'area_id': values['area_id'], 'avatar_ids': list(ids)}
        return {'retcode': 0}
    if name in ('ReportOpenworldSpawnPointReq', 'OpenworldStageEndReq'):
        if not runtime['active']:
            return {'retcode': 3 if name == 'OpenworldStageEndReq' else 1}
        try:
            _snapshot_avatars(runtime, values)
        except (ValueError, TypeError):
            return {'retcode': 6 if name == 'OpenworldStageEndReq' else 2}
        if name == 'ReportOpenworldSpawnPointReq':
            point = values.get('point_info')
            if not isinstance(point, str) or not point or len(point) > 8192:
                return {'retcode': 1}
            # Client-owned serialized point string; preserve it without guessing
            # or replacing its position/rotation/area format.
            world['spawn_point'] = point
            return {'retcode': 0}
        status = values.get('end_status')
        if type(status) is not int or status not in (1, 2, 3, 4):
            return {'retcode': 4}
        runtime['active'] = None
        return {'retcode': 0, 'end_status': status}

    if name == 'TakeOpenworldCycleFinishRewardReq':
        requested = values.get('cycle')
        configs = {1: (_CATALOG['cycle'], _CATALOG['cycle_reward'])}
        if _CATALOG.get('second_cycle'):
            configs[2] = (_CATALOG['second_cycle'], _CATALOG['second_cycle_reward'])
        if _CATALOG.get('third_cycle'):
            configs[3] = (_CATALOG['third_cycle'], _CATALOG['third_cycle_reward'])
        if _CATALOG.get('fourth_cycle'):
            configs[4] = (_CATALOG['fourth_cycle'], _CATALOG['fourth_cycle_reward'])
        if requested not in configs or configs[requested][0]['endstory'] not in world['finish_story_id_list']:
            return {'retcode': 1}
        claimed = runtime.setdefault('cycle_receipts', {})
        # Migrate the real first-cycle receipt, never infer a claim from cycle2.
        if runtime.get('cycle_receipt') and world.get('has_take_finish_reward_cycle', 0) >= 1:
            claimed.setdefault('1', deepcopy(runtime['cycle_receipt']))
        if str(requested) in claimed:
            return {'retcode': 0, 'reward_list': []}
        reward = deepcopy(configs[requested][1])
        import server19_missions as missions
        # Reuse the existing inventory capacity checks and original UID ranges.
        try:
            missions._preflight(account, reward)
        except missions._Rejected:
            return {'retcode': 1}
        stage._grant_drops(account, {(r['id'], r['level']): r['num'] for r in reward['item_list']})
        claimed[str(requested)] = {'reward': reward, 'claimed_at': time.time()}
        if requested == 1:
            runtime['cycle_receipt'] = deepcopy(claimed['1'])
        contiguous = 0
        while str(contiguous + 1) in claimed:
            contiguous += 1
        world['has_take_finish_reward_cycle'] = contiguous
        return {'retcode': 0, 'reward_list': [reward]}

    identity = values.get('story_id')
    config = next((r for r in _CATALOG['stories'] if r['StoryID'] == identity), None)
    if config is None:
        return {'retcode': 2 if name != 'AcceptOpenworldStoryReq' else 2}
    finished = world['finish_story_id_list']
    current = next((r for r in world['cur_story_list'] if r['story_id'] == identity), None)
    if name == 'AcceptOpenworldStoryReq':
        if identity in finished:
            return {'retcode': 7}
        if current is not None:
            return {'retcode': 6}
        if any(i and i not in finished for i in config['PreStory']):
            return {'retcode': 3}
        cycle_config = _cycle_configs()[config['Cycle']]
        if config['Cycle'] > world['cycle'] or account['main'].get('level', 0) < cycle_config['level']:
            return {'retcode': 2}
        world['cur_story_list'].append({'story_id': identity, 'story_progress': 0})
        return {'retcode': 0}
    if name == 'SetOpenworldStoryProgressReq':
        if current is None:
            return {'retcode': 2}
        progress = values.get('story_progress')
        if type(progress) is not int or not 0 <= progress <= config['MaxCount']:
            return {'retcode': 1}
        # The native request carries the absolute count; retry/reordering must
        # not double-count or roll back an already persisted objective.
        current['story_progress'] = max(current['story_progress'], progress)
        return {'retcode': 0}
    if name == 'TakeOpenworldStoryRewardReq':
        receipt = runtime['receipts'].get(str(identity))
        if receipt is not None:
            return {'retcode': 0, 'reward_list': []}
        if current is None:
            return {'retcode': 2}
        if current['story_progress'] != config['MaxCount']:
            return {'retcode': 1}
        reward = deepcopy(_CATALOG['rewards'][str(config['HuntRewardItem'])])
        if reward['item_list']:
            import server19_missions as missions
            missions._preflight(account, reward)
            stage._grant_drops(account, {(r['id'], r['level']): r['num'] for r in reward['item_list']})
        for key in ('scoin', 'hcoin'):
            account['main'][key] = stage._u32(account['main'].get(key, 0) + reward[key], key)
        world['cur_story_list'].remove(current)
        finished.append(identity)
        if identity == 405 and _CATALOG.get('fourth_cycle') and not world['servant_level']:
            world['servant_level'] = 1
        runtime['receipts'][str(identity)] = {'reward': reward, 'claimed_at': time.time()}
        return {'retcode': 0, 'reward_list': [reward]}
    raise AssertionError(name)


def response(name, account, values=None, *, account_path=None):
    if (_CATALOG is None or name not in REQUESTS
            or (name in commissions.REQUESTS and _COMMISSIONS is None)
            or (name in cooking.REQUESTS and _COOKING is None)):
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            result = _handle(name, current, values or {})
        except commissions.missions._Rejected:
            # Inventory rejection must roll back all grants and receipts.
            result = {'retcode': 1}
        if result['retcode'] == 0:
            stage._save(path, before, current)
            stage._sync(account, current)
    return name.removesuffix('Req') + 'Rsp', result


def commission_snapshot(name, account, *, account_path=None):
    if _COMMISSIONS is None and _COOKING is None:
        return []
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        runtime = current.get('commission_runtime', {})
        notices = runtime.pop('pending_settlements', [])
        stage._save(path, before, current)
        stage._sync(account, current)
    packets = []
    if name == 'AddServantExpReq':
        # Native MainStubPage80898 refreshes servant UI only for data_type=6.
        # Full data_type=0 updates cached values but leaves detail/skills stale.
        world = account['openworld_data']
        packets.append(('GetOpenworldRsp', dict(retcode=0, data_type=6,
            servant_level=world['servant_level'], servant_exp=world['servant_exp'],
            next_servant_collect_time=world.get('next_servant_collect_time', 0))))
    elif name in commissions.REQUESTS or name in cooking.REQUESTS or name == 'TakeOpenworldStoryRewardReq':
        packets.append(('GetOpenworldRsp', dict(deepcopy(account['openworld_data']), retcode=0, data_type=0)))
    if notices or name in ('AddServantExpReq', 'EatOpenworldCookReq', 'ChooseOpenworldQuestReq', 'RefreshOpenworldQuestReq',
                           'TakeOpenworldQuestRewardReq', 'TakeOpenworldKeyQuestRewardReq'):
        packets.extend(reward_snapshot(account))
    packets.extend(('OpenworldQuestSettleNotify', row) for row in notices)
    return packets


def reward_snapshot(account):
    import server19_initialization as initialization
    return [initialization.response('GetMainDataReq', account),
            ('GetEquipmentDataRsp', dict(retcode=0,
                weapon_list=deepcopy(account.get('weapon_list', [])),
                stigmata_list=deepcopy(account.get('stigmata_list', [])),
                material_list=deepcopy(account.get('material_list', []))))]
