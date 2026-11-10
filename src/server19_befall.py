"""Befall entrance/list recovery. Battle and settlement remain separately gated."""
from copy import deepcopy
import server19_stage as stage

ACTIVITY_IDS = tuple(range(1601, 1672, 10))
DAILY_SUCCESS_LIMIT = 3
# Approved local rotation: week one starts Monday 2026-11-09 at Beijing 04:00.
ROTATION_ANCHOR = '2026-11-09'
ROTATION = ((1601, 1611), (1621, 1631), (1641, 1651), (1661, 1671))


def rotation_window(now=None):
    from datetime import date, datetime, timedelta
    from server19_business_clock import game_date, BEIJING
    day = game_date(now)
    monday = day - timedelta(days=day.weekday())
    index = ((monday - date.fromisoformat(ROTATION_ANCHOR)).days // 7) % 4
    start = datetime(monday.year, monday.month, monday.day, 4, tzinfo=BEIJING)
    return ROTATION[index], int(start.timestamp()), int((start + timedelta(days=7)).timestamp())


def is_open(activity_id, now=None):
    return activity_id in rotation_window(now)[0]



def activities():
    rows = stage._table('weekdayactivity', field='weekDayActivityID', identities=ACTIVITY_IDS)
    by_id = {r['weekDayActivityID']: r for r in rows}
    if len(rows) != len(ACTIVITY_IDS) or set(by_id) != set(ACTIVITY_IDS):
        raise ValueError('Missing Befall activity metadata')
    return [by_id[i] for i in ACTIVITY_IDS]


def stage_ids():
    return {i for r in activities() for i in r['levelIDList']}


def stage_snapshots(account):
    if account.get('main', {}).get('level', 1) < 20:
        return []
    stored = {r['id']: r for r in account.get('stage_list', [])}
    return [deepcopy(stored.get(i, dict(id=i, progress=0, enter_times=0,
                reset_times=0, assist_enter_times=0, challenge_index_list=[],
                stamina_discount=100, is_done=False))) for i in sorted(stage_ids())]


def update_activity_list(activity, account):
    # User-approved two activities per week, four-week repeating schedule.
    # Do not reset saved attempts or create battle permissions here.
    previous = {r['activity_id']: r for r in activity['activity_list']}
    activity['activity_list'] = [r for r in activity['activity_list']
                                if r['activity_id'] not in ACTIVITY_IDS]
    level = account.get('main', {}).get('level', 1)
    opened, start, end = rotation_window()
    for meta in activities():
        if level < meta['minPlayerLevel'] or meta['weekDayActivityID'] not in opened:
            continue
        identity = meta['weekDayActivityID']
        record = deepcopy(previous.get(identity, {}))
        record.update(activity_id=identity, stage_id_list=list(meta['levelIDList']),
                      begin_time=0, end_time=2147483647,
                      activity_begin_time=start, activity_end_time=end)
        record.setdefault('enter_times', 0)
        if identity in BATTLE_ACTIVITIES:
            from server19_business_clock import day_bounds
            record['begin_time'], record['end_time'] = day_bounds()
            record['enter_times'] = completed_today(account, activity_id=identity)
        activity['activity_list'].append(record)


BATTLE_STAGE_ID = 55001
BATTLE_STAGE_IDS = (55001, 55002, 55003, 55011, 55012, 55013, 55021, 55022, 55023, 55031, 55032, 55033)
BATTLE_ACTIVITIES = {1601: ('Lua/Levels/Event/BossLevel01_L.lua', BATTLE_STAGE_IDS),
                     1611: ('Lua/Levels/Event/BossLevel03_L.lua', tuple(55100 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3))),
                     1621: ('Lua/Levels/Event/BossLevel02_H.lua', tuple(55200 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3))),
                     1631: ('Lua/Levels/Event/BossLevel06_H.lua', tuple(55300 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3))),
                     1641: ('Lua/Levels/Event/BossLevel04_H.lua', tuple(55400 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3))),
                     1651: ('Lua/Levels/Event/BossLevel07_H.lua', tuple(55500 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3))),
                     1661: ('Lua/Levels/Event/BossLevel05_H.lua', tuple(55600 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3))),
                     1671: ('Lua/Levels/Event/BossLevel08_H.lua', tuple(55700 + tier * 10 + slot for tier in range(4) for slot in (1, 2, 3)))}
STAGE_ACTIVITY = {sid: aid for aid, (_, ids) in BATTLE_ACTIVITIES.items() for sid in ids}
BATTLE_STAGE_IDS = tuple(STAGE_ACTIVITY)
DROP_POLICY = 'befall_55001_compat_v1'


def configure_battle():
    """Enable audited Befall stages, preserving table scaling."""
    rows = stage._table('stagedata_main', field='levelId', identities=BATTLE_STAGE_IDS)
    by_id = {r['levelId']: r for r in rows}
    if set(by_id) != set(BATTLE_STAGE_IDS):
        raise ValueError('Missing audited Befall stages')
    for identity, row in by_id.items():
        tier = (identity % 100 - 1) // 10
        expected = {'type': 3, 'battleType': 5, 'staminaCost': 10 + tier * 2,
                    'maxProgress': 1, 'luaFile': BATTLE_ACTIVITIES[STAGE_ACTIVITY[identity]][0]}
        if any(row.get(k) != v for k, v in expected.items()):
            raise ValueError('Befall stage changed; audit before enabling')
    previous_config, previous_ids = stage.stage_config, stage.supported_stage_ids
    stage.stage_config = lambda identity=stage.STAGE_ID: (deepcopy(by_id[identity])
        if identity in by_id else previous_config(identity))
    stage.supported_stage_ids = lambda: tuple(sorted(set(previous_ids()) | set(BATTLE_STAGE_IDS)))


def _policy(stage_id=BATTLE_STAGE_ID):
    import json
    from pathlib import Path
    policies = json.loads(Path(__file__).with_name('server19_befall_drop_policy.json').read_bytes())
    value = policies[str(stage_id)]
    if value.get('policy') != DROP_POLICY or value.get('stage_id') != stage_id or stage_id not in BATTLE_STAGE_IDS:
        raise ValueError('Invalid Befall policy')
    for mode in ('first', 'repeat'):
        rows = value[mode]
        if len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate Befall drop')
        for row in rows:
            if row['id'] not in (7032, 25041, 25051, 25081, 25091, 25061, 25071, 25021, 25031, 25101, 25111, 25141, 25151, 25001, 25011, 25121, 25131) or type(row['num']) is not int or row['num'] < 1 \
                    or type(row['percent']) is not int or not 0 <= row['percent'] <= 100:
                raise ValueError('Invalid Befall drop')
    return value


def _drop(row):
    kind, meta = stage._item_metadata(row['id'])
    return dict(item_id=row['id'], num=row['num'], level=1 if kind == 'weapon' else 0,
                rarity=meta['rarity'], is_equip_drop=False)


def draw(progress, stage_id=BATTLE_STAGE_ID):
    import secrets
    policy = _policy(stage_id)
    mode = 'first' if progress == 0 else 'repeat'
    rolls = [secrets.randbelow(100) for row in policy[mode]]
    plan = [_drop(row) for row, roll in zip(policy[mode], rolls) if roll < row['percent']]
    return plan, dict(policy=policy, mode=mode, rolls=rolls)


def validate_active(active, config):
    try:
        audit = active['drop_audit']
        begin = active['begin_response']
        mode = 'first' if begin['progress'] == 0 else 'repeat'
        policy = audit['policy']
        rows = policy[mode]
        rolls = audit['rolls']
        if policy != _policy(active['stage_id']) or audit['mode'] != mode or len(rows) != len(rolls):
            return False
        if any(type(v) is not int or not 0 <= v < 100 for v in rolls):
            return False
        expected = [_drop(row) for row, roll in zip(rows, rolls) if roll < row['percent']]
        return (active['stage_id'] == begin['stage_id'] == config['levelId']
                and active['stage_id'] in BATTLE_STAGE_IDS
                and active['drop_plan'] == begin['drop_item_list'] == expected)
    except (KeyError, ValueError, TypeError):
        return False


def completed_today(account, now=None, activity_id=1601):
    from server19_business_clock import day_key
    state = account.get('befall_runtime', {})
    return state.get('wins', {}).get(str(activity_id), 0) if state.get('day') == day_key(now) else 0


def record_win(account, stage_id=BATTLE_STAGE_ID):
    from server19_business_clock import day_key
    day = day_key()
    state = account.setdefault('befall_runtime', {'day': day, 'wins': {}})
    if state.get('day') != day:
        state.update(day=day, wins={})
    key = str(STAGE_ACTIVITY[stage_id])
    state['wins'][key] = state['wins'].get(key, 0) + 1
