"""Local weekly ExBoss schedule, battle records and original reward tables."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import time

import server19_endless as endless
import server19_exboss_rank as ranking
import server19_protocol as proto
import server19_stage as stage
import server19_missions as missions
import server19_gm as gm

REQUESTS = {'GetExBossScheduleReq', 'GetExBossInfoReq', 'GetExBossRankReq',
            'ExBossStageBeginReq', 'ExBossStageEndReq'}
ROTATION = ((1001, 201, 3001), (4001, 501, 601), (701, 8001, 9001))
# Monday 2026-11-16 04:00 China time; deterministic for every account.
ROTATION_EPOCH = 1794772800
DAILY_LIMITS = {101: 4, 102: 4, 103: 5}


def period(now):
    day = datetime.fromtimestamp(now, timezone(timedelta(hours=8)))
    today = day.replace(hour=4, minute=0, second=0, microsecond=0)
    if day < today:
        today -= timedelta(days=1)
    first = today - timedelta(days=today.weekday())
    return int(first.timestamp()), int((first + timedelta(days=7)).timestamp()), int(today.timestamp())


def _roots(begin):
    selected = gm.bosses_for_period(begin)
    return tuple(selected) if selected is not None else _default_roots(begin)


def _default_roots(begin):
    return ROTATION[((begin - ROTATION_EPOCH) // (7 * 86400)) % len(ROTATION)]


def _state_roots(s):
    # Once a week has started, the actual saved roster is authoritative even
    # if the next week's GM selection changes before this week is settled.
    bosses = s.get('bosses')
    if not isinstance(bosses, dict) or len(bosses) != 3:
        raise ValueError('Invalid saved ExBoss roster')
    try:
        roots = tuple(int(k) for k in bosses)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid saved ExBoss roster') from exc
    if len(set(roots)) != 3 or not set(roots) <= gm.ALLOWED_BOSSES or any(str(int(k)) != k for k in bosses):
        raise ValueError('Invalid saved ExBoss roster')
    order = s.get('root_order')
    if order is not None:
        if not isinstance(order, list) or len(order) != 3 or set(order) != set(roots):
            raise ValueError('Invalid saved ExBoss roster order')
        return tuple(order)
    # Older accounts used the fixed rotation and did not store an order.
    expected = _default_roots(s['begin'])
    return expected if set(expected) == set(roots) else roots


def _fresh_roster(state, roots):
    state['root_order'] = list(roots)
    state['bosses'] = {str(root): {'boss_id': root, 'score': 0, 'score_time': 0,
                                  'avatars': [], 'weapons': [], 'stigmata': []}
                       for root in roots}


def _has_entered(state):
    # Earlier saves have no weekly marker. Failed or exited runs retain last_end.
    return bool(state.get('has_entered') or state.get('enter_times') or state.get('active')
                or state.get('last_end') or state.get('score_rewards')
                or state['score_time'] != state['begin']
                or any(row['boss_id'] != int(root) or row['score'] or row['avatars']
                       for root, row in state['bosses'].items()))


def _state(account, now):
    begin, end, day = period(now)
    state = account.get('exboss_runtime')
    if not state or state['begin'] != begin:
        if state:
            _settle_previous(account, state)
        state = {'begin': begin, 'end': end, 'day': day, 'enter_times': 0,
                 'rank_id': _config_id(account) if account['main']['level'] >= 38 else 101,
                 'score_time': begin, 'active': None,
                 'last_end': None, 'score_rewards': []}
        _fresh_roster(state, _roots(begin))
        account['exboss_runtime'] = state
    if 'has_entered' not in state:
        state['has_entered'] = _has_entered(state)
    if state['day'] != day:
        state['day'], state['enter_times'] = day, 0
    return state


def describe_current(account, now):
    begin, end, day = period(now)
    saved = account.get('exboss_runtime') or {}
    state = saved if saved.get('begin') == begin else None
    settled = saved.get('begin', begin) > begin or any(
        row['begin'] == begin for row in account.get('exboss_rank_receipts', ()))
    revision = hashlib.sha256(json.dumps(
        [begin, day, state], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    available = account['main']['level'] >= 38 and not settled
    return {'begin': begin, 'end': end, 'available': available, 'settled': settled,
            'bosses': list(_state_roots(state) if state else _roots(begin)),
            'entered': _has_entered(state) if state else False,
            'active': bool(saved.get('active')), 'revision': revision}


def change_current(account, now, expected_begin, revision, operation, bosses):
    current = describe_current(account, now)
    if expected_begin != current['begin'] or current['settled']:
        raise ValueError('本周已结束或结算，请重新打开玩法设置')
    if not current['available']:
        raise ValueError('记忆战场在舰长等级 38 级解锁')
    if current['active']:
        raise ValueError('请先结束正在进行的记忆战场战斗')
    if operation == 'replace' and current['entered']:
        raise ValueError('本周已有出战记录，请重新打开玩法设置并使用「重置本周」')
    if revision != current['revision']:
        raise ValueError('本周记录已变化，请重新打开玩法设置后再操作')
    if operation == 'replace' or bosses is not None:
        roots = gm._bosses(bosses)
    else:
        roots = current['bosses']
    state = _state(account, now)
    _fresh_roster(state, roots)
    if operation == 'reset':
        # score_rewards and the account's rank receipts remain authoritative.
        state.update(enter_times=0, score_time=state['begin'], last_end=None,
                     has_entered=current['entered'], gm_reset_count=state.get('gm_reset_count', 0) + 1)


def _config_id(account):
    level = account['main']['level']
    if not 38 <= level <= 80:
        raise ValueError('ExBoss level outside configured groups')
    return 103 if level >= 70 else 102 if level >= 56 else 101


def _info(s, account):
    return {'enter_times': s['enter_times'], 'schedule_id': 0, 'rank_id': s['rank_id'],
            'boss_id_list': [{'boss_id': s['bosses'][str(root)]['boss_id'],
                              'score': s['bosses'][str(root)]['score'],
                              'avatar_id_list': s['bosses'][str(root)]['avatars'],
                              'weapon_id_list': s['bosses'][str(root)]['weapons'],
                              'stigmata_id_list': s['bosses'][str(root)]['stigmata']}
                             for root in _state_roots(s)]}


def _rank(account, s, now):
    roots = _state_roots(s)
    finals = stage._table('exbossmonsterdata', field='BossId', identities=tuple(root + 4 for root in roots))
    if len(finals) != len(roots):
        raise ValueError('Missing boss maximum scores')
    score = sum(s['bosses'][str(root)]['score'] for root in roots)
    return ranking.leaderboard(account, s['begin'], s['end'], now, score,
                               s['score_time'], s['rank_id'], endless.CATALOG['bot_names'],
                               2 * sum(row['MonsterBaseScore'] for row in finals))


def _reward(reward_id):
    rows = stage._table('rewarddata', field='RewardID', identities=(reward_id,))
    if len(rows) != 1:
        raise ValueError('Missing ExBoss reward')
    item = rows[0]
    reward = {key: item[source] for key, source in {
        'exp': 'RewardExp', 'scoin': 'RewardSCoin', 'hcoin': 'RewardHCoin',
        'stamina': 'RewardStamina', 'skill_point': 'RewardSkillPoint',
        'friends_point': 'RewardFriendPoint', 'duty_point': 'RewardDutyPoint'}.items()}
    reward['item_list'] = [{'id': item[f'RewardItem{i}ID'], 'level': item[f'RewardItem{i}Level'],
                            'num': item[f'RewardItem{i}Num']} for i in range(1, 6)
                           if item[f'RewardItem{i}ID']]
    if any(reward[k] for k in ('exp', 'stamina', 'skill_point', 'friends_point', 'duty_point')):
        raise ValueError('Unsupported ExBoss reward currency')
    return reward


def _grant(account, reward, now):
    # 101036 is an original, timed ExBoss medal, not a material item. Its
    # native medal table and all three native sprites are retained in 1.9.
    medals = [item for item in reward['item_list'] if item['id'] == 101036]
    regular = {**reward, 'item_list': [item for item in reward['item_list'] if item['id'] != 101036]}
    missions._preflight(account, regular)
    if medals:
        config = stage._table('medaldata', field='medalID', identities=(101036,))
        if (len(medals) != 1 or medals[0]['num'] != 1 or len(config) != 1 or
                config[0]['timeType'] != 2 or config[0]['during'] != 10080):
            raise ValueError('ExBoss medal metadata changed')
        existing = [row for row in account.setdefault('medal_list', []) if row['id'] == 101036]
        if len(existing) > 1:
            raise ValueError('Duplicate ExBoss medal')
        end_time = stage._u32(max(now, existing[0]['end_time'] if existing else 0) + 10080 * 60,
                              'ExBoss medal expiration')
        if existing:
            existing[0]['end_time'] = end_time
        else:
            account['medal_list'].append({'id': 101036, 'end_time': end_time})
    for key in ('scoin', 'hcoin'):
        account['main'][key] = stage._u32(account['main'].get(key, 0) + reward[key], key)
    totals = {}
    for item in regular['item_list']:
        identity = (item['id'], item['level'])
        totals[identity] = totals.get(identity, 0) + item['num']
    stage._grant_drops(account, totals)


def _settle_previous(account, s):
    # Persist an immutable receipt before opening the next week. Unrecognized
    # items remain pending, never silently dropped or substituted.
    result = _rank(account, s, s['end'])['my_rank']
    rank, score = result['rank'], result['score']
    if not score or not rank:
        return
    rows = sorted((r for r in stage._table('exbossrankreward')
                   if r['configId'] == s['rank_id'] and r['scheduleId'] == 0
                   and rank <= r['rank']), key=lambda r: r['rank'])
    if rows:
        receipts = account.setdefault('exboss_rank_receipts', [])
        if not any(row['begin'] == s['begin'] for row in receipts):
            receipts.append({'begin': s['begin'], 'rank': rank, 'score': score,
                             'reward_id': rows[0]['rewardId'], 'claimed': False})


def _deliver_previous(account, now):
    delivered = []
    for receipt in account.get('exboss_rank_receipts', []):
        if receipt['claimed']:
            continue
        reward = _reward(receipt['reward_id'])
        trial = deepcopy(account)
        try:
            _grant(trial, reward, now)
        except (ValueError, missions._Rejected):
            continue
        _grant(account, reward, now)
        receipt['claimed'] = True
        delivered.append({'rank': receipt['rank'], 'score': receipt['score'], 'reward_list': [reward]})
    return delivered


def _score_rewards(account, s, now):
    config = s['rank_id']
    visible_score = sum(s['bosses'][str(root)]['score'] for root in _state_roots(s))
    rows = [r for r in stage._table('exbossscorereward')
            if r['configId'] == config and r['scheduleId'] == 0
            and r['score'] <= visible_score and r['ID'] not in s['score_rewards']]
    delivered = []
    for row in sorted(rows, key=lambda r: r['score']):
        reward = _reward(row['rewardId'])
        _grant(account, reward, now)
        s['score_rewards'].append(row['ID'])
        delivered.append(reward)
    return delivered


def _handle(name, account, request, now):
    if name != 'GetExBossScheduleReq' and account['main']['level'] < 38:
        return {'retcode': 1}
    s = _state(account, now)
    # The schedule request can arrive during client startup. Deliver when the
    # player opens the ExBoss page, so its native reward consumer is ready.
    delivered = _deliver_previous(account, now) if name == 'GetExBossInfoReq' else []
    if delivered:
        account.setdefault('exboss_notifications', []).extend(delivered)
    if name == 'GetExBossScheduleReq':
        return {'retcode': 0, 'begin_time': s['begin'], 'end_time': s['end'],
                'min_level': 38, 'image_path': 'SpriteOutput/ChapterCover/Event/BookEventMemory'}
    if name == 'GetExBossInfoReq':
        return {'retcode': 0, 'boss_info': _info(s, account)}
    if name == 'GetExBossRankReq':
        return _rank(account, s, now)
    if name == 'ExBossStageBeginReq':
        team = request.get('avatar_id_list', [])
        if not isinstance(team, list):
            team = [team]
        boss = request.get('boss_id')
        owned = {a['avatar_id']: a for a in account.get('avatar_list', []) if a.get('star', 0) > 0}
        matches = [root for root in _state_roots(s)
                   if s['bosses'][str(root)]['boss_id'] == boss]
        if (len(matches) != 1 or not 1 <= len(team) <= 3
                or len(set(team)) != len(team) or any(a not in owned for a in team)):
            return {'retcode': 1}
        if s['active']:
            return {'retcode': 0} if s['active']['team'] == team and s['active']['boss'] == boss else {'retcode': 1}
        weapons = [owned[a].get('weapon_unique_id', 0) for a in team]
        stigmata = [owned[a].get(f'stigmata_unique_id_{i}', 0) for a in team for i in (1, 2, 3)]
        if s['enter_times'] >= DAILY_LIMITS[s['rank_id']]:
            return {'retcode': 1}
        for root in _state_roots(s):
            if root == matches[0]:
                continue
            locked = s['bosses'][str(root)]
            if (set(team) & set(locked['avatars']) or
                    set(weapons) - {0} & set(locked['weapons']) or
                    set(stigmata) - {0} & set(locked['stigmata'])):
                return {'retcode': 1}
        s['active'] = {'team': team, 'boss': boss, 'root': matches[0], 'weapons': [x for x in weapons if x],
                       'stigmata': [x for x in stigmata if x]}
        s['enter_times'] += 1
        s['has_entered'] = True
        return {'retcode': 0}
    if name == 'ExBossStageEndReq':
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        if not s['active']:
            last = s.get('last_end')
            return deepcopy(last['response']) if last and last['digest'] == digest else {'retcode': 1}
        active = s['active']
        status, boss, score = request.get('end_status'), request.get('boss_id'), request.get('score', 0)
        if status not in (1, 2, 3, 4) or boss != active['boss'] or type(score) is not int or not 0 <= score <= (1 << 32) - 4:
            return {'retcode': 1}
        result = {'retcode': 0, 'end_status': status, 'boss_id': boss}
        rewards = []
        if status == 1:
            rows = stage._table('exbossmonsterdata', field='BossId', identities=(boss,))
            if len(rows) != 1:
                raise ValueError('Boss is missing')
            selected = s['bosses'][str(active['root'])]
            if score > selected['score']:
                selected['score'], selected['score_time'] = score, now
                s['score_time'] = now
            selected['avatars'], selected['weapons'], selected['stigmata'] = active['team'], active['weapons'], active['stigmata']
            selected['boss_id'] = rows[0]['BossNextId']
            rewards = _score_rewards(account, s, now)
        s['active'] = None
        s['last_end'] = {'digest': digest, 'response': deepcopy(result), 'rewards': rewards}
        return result
    raise ValueError('unknown request')


def take_notifications(account, account_path):
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = stage.copy_account(before)
        notices = current.pop('exboss_notifications', [])
        if notices:
            stage._save(path, before, current)
        stage._sync(account, current)
    return notices


def response(name, account, values=None, *, account_path=None, now=None):
    if name not in REQUESTS:
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    now = int(time.time() if now is None else now)
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = stage.copy_account(before)
        try:
            result = _handle(name, current, values or {}, now)
            proto.encode_message(name[:-3] + 'Rsp', result)
        except (ValueError, TypeError, KeyError, OverflowError, missions._Rejected):
            result = {'retcode': 1}
        if result['retcode'] == 0:
            stage._save(path, before, current)
            stage._sync(account, current)
    return name[:-3] + 'Rsp', result
