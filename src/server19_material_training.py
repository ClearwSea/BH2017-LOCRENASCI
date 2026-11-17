"""Local single-player material training and approved compatibility rewards.

The source activity and stage metadata come from the selected 2.4 input.  The
reward quantities are the user-approved local plan, not historical rates.
"""
from copy import deepcopy
from pathlib import Path

import server19_business_clock as clock

THEME_IDS = (1001, 1002, 1003, 1004, 1005)
REDPACKET_ID = 1301
MATERIAL_IDS = (1501, 1511, 1521, 1531, 1541)
ACTIVITY_IDS = THEME_IDS + (REDPACKET_ID,) + MATERIAL_IDS
ACTIVITIES = {**{1000 + n: (101000 + n * 100, (n - 1,)) for n in range(1, 6)},
              REDPACKET_ID: (101600, (5, 6)),
              1501: (45000, (1,)), 1511: (45100, (3,)),
              1521: (45200, (6,)), 1531: (45300, (2, 5)),
              1541: (45400, (0, 4))}
BASE_AMOUNTS = {
    'avatar': ((14, 10), (16, 14), (21, 18), (8, 4), (7, 5), (6, 6),
               (6, 7), (6, 8), (7, 9), (8, 10), (9, 11), (11, 12)),
    'equipment': ((4, 2), (4, 3), (4, 4), (4, 2), (5, 2), (6, 2),
                  (5, 3), (6, 3), (8, 3), (7, 4), (7, 5), (7, 6)),
}
# Each pair is ordered like BASE_AMOUNTS: lower-rarity, then higher-rarity.
ITEMS = {1501: ((1002, 1003), (1003, 1006)),
         1511: ((1002, 1005), (1005, 1008)),
         1521: ((1002, 1004), (1004, 1007)),
         1531: ((3002, 3003), (3003, 3004)),
         1541: ((3006, 3007), (3007, 3008))}
STAGE_ACTIVITY = {base + tier * 10 + slot: identity
                  for identity in MATERIAL_IDS for base, _ in (ACTIVITIES[identity],)
                  for tier in range(4) for slot in (1, 2, 3)}
STAGE_ACTIVITY.update({101000 + n * 100 + slot: 1000 + n
                       for n in range(1, 6) for slot in (1, 2, 3, 4)})
STAGE_ACTIVITY.update({101600 + slot: REDPACKET_ID for slot in (1, 2, 3, 4)})
DROP_POLICY = 'material_training_user_approved_x5_v1'


def activity_rows():
    import server19_stage as stage
    rows = stage._table('weekdayactivity', field='weekDayActivityID', identities=ACTIVITY_IDS)
    by_id = {row['weekDayActivityID']: row for row in rows}
    if len(rows) != len(ACTIVITY_IDS) or set(by_id) != set(ACTIVITY_IDS):
        raise ValueError('Material training activity metadata missing')
    return [by_id[identity] for identity in ACTIVITY_IDS]


def is_open(identity, now=None, account=None):
    if identity not in ACTIVITY_IDS:
        return False
    state = (account or {}).get('material_training_runtime', {})
    forced = state.get('day') == clock.day_key(now) and str(identity) in state.get('opened', {})
    return forced or clock.game_date(now).weekday() in ACTIVITIES[identity][1]


def completed_today(account, identity, now=None):
    state = account.get('material_training_runtime', {})
    return state.get('wins', {}).get(str(identity), 0) if state.get('day') == clock.day_key(now) else 0


def exchanged_today(account, identity, now=None):
    state = account.get('material_training_runtime', {})
    return state.get('exchanges', {}).get(str(identity), 0) if state.get('day') == clock.day_key(now) else 0


def daily_limit(identity):
    return 2 if identity in THEME_IDS or identity == REDPACKET_ID else 1


def record_win(account, stage_id, now=None):
    identity = STAGE_ACTIVITY[stage_id]
    day = clock.day_key(now)
    state = account.setdefault('material_training_runtime', {'day': day, 'wins': {}})
    if state.get('day') != day:
        state.update(day=day, wins={}, opened={}, exchanges={})
    key = str(identity)
    state['wins'][key] = state['wins'].get(key, 0) + 1


def update_activity_list(activity, account, now=None):
    previous = {row['activity_id']: row for row in activity['activity_list']}
    activity['activity_list'] = [row for row in activity['activity_list']
                                 if row['activity_id'] not in ACTIVITY_IDS]
    start, end = clock.day_bounds(now)
    for meta in activity_rows():
        identity = meta['weekDayActivityID']
        if account.get('main', {}).get('level', 1) < meta['minPlayerLevel'] or not is_open(identity, now, account):
            continue
        row = deepcopy(previous.get(identity, {}))
        row.update(activity_id=identity, stage_id_list=list(meta['levelIDList']),
                   begin_time=start, end_time=end, activity_begin_time=start,
                   activity_end_time=end, enter_times=completed_today(account, identity, now),
                   exchange_times=exchanged_today(account, identity, now))
        state = account.get('material_training_runtime', {})
        if state.get('day') == clock.day_key(now):
            force_time = state.get('opened', {}).get(str(identity))
            if force_time:
                row['force_open_time'] = force_time
        activity['activity_list'].append(row)


def response(name, account, values=None, *, account_path=None, now=None):
    if name not in ('OpenWeekDayActivityReq', 'ExchangeWeekDayActivityTimesReq'):
        return None
    import server19_stage as stage
    import server19_protocol as proto
    identity = (values or {}).get('activity_id')
    rsp = name.removesuffix('Req') + 'Rsp'
    if identity not in ACTIVITY_IDS:
        return rsp, {'retcode': 1}
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            meta = next(row for row in activity_rows() if row['weekDayActivityID'] == identity)
            main = current['main']
            if main.get('level', 1) < meta['minPlayerLevel']:
                raise ValueError('Activity level requirement not met')
            opening = name == 'OpenWeekDayActivityReq'
            if opening == is_open(identity, now, current):
                raise ValueError('Activity status does not allow request')
            count = 1 if opening else (values or {}).get('activity_times')
            if type(count) is not int or count != 1:
                raise ValueError('Unsupported activity exchange quantity')
            cost = meta['activityCoinCost'] * count
            gold = meta['openScoinCost'] if opening else 0
            badge = next((row for row in current.get('material_list', [])
                          if row.get('id') == meta['activityCoinID']), None)
            if not badge or badge['num'] < cost or main['scoin'] < gold:
                raise ValueError('Insufficient materials')
            badge['num'] -= cost
            main['scoin'] -= gold
            day = clock.day_key(now)
            state = current.setdefault('material_training_runtime', {})
            if state.get('day') != day:
                state.update(day=day, wins={}, opened={}, exchanges={})
            if opening:
                state.setdefault('opened', {})[str(identity)] = int(clock.local_now(now).timestamp())
            else:
                exchanges = state.setdefault('exchanges', {})
                key = str(identity)
                exchanges[key] = exchanges.get(key, 0) + count
            result = {'retcode': 0}
            if not opening:
                result['coin_cost'] = cost
            proto.encode_message(rsp, result)
            stage._save(path, before, current)
        except (OSError, ValueError, TypeError, KeyError, StopIteration):
            stage._sync(account, before)
            return rsp, {'retcode': 1}
        stage._sync(account, current)
    return rsp, result


def configure_battle():
    import server19_stage as stage
    rows = stage._table('stagedata_main', field='levelId', identities=STAGE_ACTIVITY)
    by_id = {row['levelId']: row for row in rows}
    if len(rows) != len(STAGE_ACTIVITY) or set(by_id) != set(STAGE_ACTIVITY):
        raise ValueError('Material training stage metadata missing')
    for row in rows:
        if (row['type'], row['battleType'], row['teamNum']) != (2, 1, 1):
            raise ValueError('Material training source stage changed')
    previous_config, previous_ids = stage.stage_config, stage.supported_stage_ids
    stage.stage_config = lambda identity=stage.STAGE_ID: (deepcopy(by_id[identity])
        if identity in by_id else previous_config(identity))
    stage.supported_stage_ids = lambda: tuple(sorted(set(previous_ids()) | set(STAGE_ACTIVITY)))


def drop_plan(stage_id):
    identity = STAGE_ACTIVITY[stage_id]
    if identity == REDPACKET_ID:
        # The native course creates its own coin drop; currency settlement is
        # calculated separately from the observed native score.
        return []
    import server19_stage as stage
    if identity in THEME_IDS:
        # User-approved local compatibility amounts; original drop rates are unavailable.
        items = stage.stage_config(stage_id)['displayDropList']
        if len(items) != 2 or len(set(items)) != 2:
            raise ValueError('Theme stage display items changed')
        typed = []
        for item_id in items:
            kind, meta = stage._item_metadata(item_id)
            if kind != 'material':
                raise ValueError('Theme reward item changed type')
            typed.append((meta['rarity'], item_id, meta))
        typed.sort(key=lambda row: row[0])
        if typed[0][0] == typed[1][0]:
            raise ValueError('Theme reward rarities are ambiguous')
        result = []
        # These scripts reserve six item positions.  Preserve the totals while
        # using native pickup records, as in the tested pilot.
        for (_, item_id, meta), count in zip(typed, (30, 15)):
            if count > meta['quantityLimit']:
                raise ValueError('Theme reward outside item limits')
            result.extend({'item_id': item_id, 'level': 0, 'num': count // 3,
                           'rarity': stage._u32(meta['rarity'], 'drop rarity'),
                           'is_equip_drop': False} for _ in range(3))
        return result
    base, _ = ACTIVITIES[identity]
    number = stage_id - base
    tier, slot = (number - 1) // 10, (number - 1) % 10
    if not 0 <= tier < 4 or slot not in (0, 1, 2):
        raise ValueError('Unknown material training stage')
    amounts = BASE_AMOUNTS['avatar' if identity < 1531 else 'equipment'][tier * 3 + slot]
    items = ITEMS[identity][0 if tier == 0 else 1]
    result = []
    # The original avatar/stigmata scripts reserve twelve drop positions.
    # Distribute each approved total across six original item records. This
    # changes neither item identities nor the total, and uses native pickups.
    slots = 6 if identity != 1531 else 1
    for item_id, amount in zip(items, amounts):
        kind, metadata = stage._item_metadata(item_id)
        if kind != 'material':
            raise ValueError('Material training item changed type')
        count = amount * 5
        if count < slots or count > metadata['quantityLimit']:
            raise ValueError('Material training reward outside item limits')
        quotient, remainder = divmod(count, slots)
        for index in range(slots):
            result.append({'item_id': item_id, 'level': 0,
                           'num': quotient + (index < remainder),
                           'rarity': stage._u32(metadata['rarity'], 'drop rarity'),
                           'is_equip_drop': False})
    return result


def redpacket_reward(stage_id, score, config):
    """Approved fivefold local payout, based on the client's native score."""
    import server19_stage as stage
    if STAGE_ACTIVITY.get(stage_id) != REDPACKET_ID:
        raise ValueError('Not a red-packet stage')
    score = stage._u32(score, 'red-packet score')
    hardlevel = config.get('hardLevel')
    if type(hardlevel) is not int or hardlevel != (stage_id - 101600) * 15:
        raise ValueError('Red-packet native difficulty changed')
    return stage._u32((score * 45 + (hardlevel // 15) * 13500) * 5,
                      'red-packet reward')


def validate_active(active, config):
    try:
        plan = drop_plan(active['stage_id'])
        begin = active['begin_response']
        return (active.get('drop_policy') == DROP_POLICY and
                active['stage_id'] == begin['stage_id'] == config['levelId'] and
                active['drop_plan'] == begin['drop_item_list'] == plan)
    except (KeyError, TypeError, ValueError):
        return False
