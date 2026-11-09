"""User-authored supply policy; max evolution stars, independent saved pity.

No device/service operations. Cash pools use the same sequence for single and
ten draws. Friendship keeps its original transaction, excluding max-star5.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import random
import time

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'server19_gacha_policy.json'
CASH_CHANNELS = (2, 10, 3, 5)
ROLE_CHANNELS = (2, 5)
UP_GEAR = frozenset((20464, 30629, 30633, 30637))
UP_CARD = 60502


@lru_cache(maxsize=1)
def config():
    value = json.loads(CONFIG.read_text('utf8'))
    for name in ('role_weights', 'equipment_weights'):
        if sum(value[name].values()) != 10000 or any(type(x) is not int or x <= 0 for x in value[name].values()):
            raise ValueError('Supply weights must be positive and total10000')
    return value


@lru_cache(maxsize=1)
def catalog():
    import server19_gacha as g
    safe = {r['item_id'] for r in json.loads(g.ELIGIBILITY.read_text('utf8'))['items'] if r['class'] == 'safe'}
    # These four exact identities had a separate focused dependency repair.
    # Do not widen this exception to the remainder of the older blocked report.
    safe.update(UP_GEAR)
    gear, family, maximum = {}, {}, {}
    for name, kind in [('weapondata', 'weapon'), ('stigmatadata', 'stigmata')]:
        rows = {r['ID']: r for r in g.stage._table(name)}
        incoming = {r['evoID'] for r in rows.values() if r.get('evoID')}
        for identity, row in rows.items():
            if identity in incoming or row.get('subRarity', 0):
                continue
            chain, seen, item = [], set(), identity
            broken = False
            while item:
                if item in seen or item not in rows:
                    if identity in safe:
                        raise ValueError('Broken equipment evolution chain')
                    broken = True
                    break
                seen.add(item); chain.append(item); item = rows[item].get('evoID', 0)
            if broken:
                continue
            stars = max(rows[i]['rarity'] for i in chain)
            if row['maxRarity'] != stars:
                if identity in safe:
                    raise ValueError('Equipment maximum differs from evolution chain')
                continue
            for evolved in chain:
                family[(kind, evolved)] = identity
                maximum[(kind, evolved)] = stars
            if identity in safe and 2 <= stars <= 5:
                gear[(kind, identity)] = stars
    avatars = {}
    for row in g.stage._table('avatardata'):
        if row.get('avatarCardID') and row['unlockStar'] in (2, 3):
            avatars[row['avatarCardID']] = row['unlockStar']
    if not all(any(i == up for _, i in gear) for up in UP_GEAR):
        raise ValueError('UP equipment base identity missing')
    return gear, family, maximum, avatars


def tag(kind, identity):
    gear, family, maximum, avatars = catalog()
    if kind == 'avatar_card':
        return 'S' if avatars.get(identity, 0) >= 3 else 'A'
    if kind == 'material':
        return 'MATERIAL'
    stars = maximum[(kind, identity)]
    return 'GEAR' + str(stars) if stars >= 4 else 'LOW_' + kind.upper()


def is_up(kind, identity):
    if kind == 'avatar_card':
        return identity == UP_CARD
    return catalog()[1].get((kind, identity), identity) in UP_GEAR


def choices(channel):
    import server19_gacha as g
    gear, _, _, avatars = catalog()
    result = {key: [] for key in config()['role_weights' if channel in ROLE_CHANNELS else 'equipment_weights']}
    for (kind, identity), stars in gear.items():
        category = tag(kind, identity)
        if category not in result or (channel in (2, 10) and is_up(kind, identity)):
            continue
        result[category].append((kind, identity, 1, 1))
    if channel in ROLE_CHANNELS:
        blocked = (g._awakened_avatar_ids() | g.BANNER_AVATAR_IDS if channel == 2 else
                   (g._awakened_avatar_ids() | {601}) - {card - 60000 for card in g.ZIYUAN_A_CARDS})
        for identity, stars in avatars.items():
            if identity - 60000 in blocked:
                continue
            result['S' if stars == 3 else 'A'].append(('avatar_card', identity, 1, 1))
    result['MATERIAL'] = [('material', identity, 0, count) for identity, count in g.MATERIAL_POOL]
    if any(not rows for rows in result.values()):
        raise ValueError('Empty configured supply tier')
    return result


def state(account, channel):
    import server19_gacha as g
    runtime = g._runtime(account)
    key = ('expansion:' + g.ZIYUAN_PERIOD if channel == 5 else
           'focused:' + g.ZIYUAN_EQUIP_PERIOD if channel == 3 else 'standard:' + str(channel))
    states = runtime.setdefault('policy_v2', {})
    if key not in states:
        legacy = g._banner_runtime(account, channel) if channel in (3, 5) else {}
        # Old logs have no channel identity, so do not invent past rare/UP
        # streaks. New guarantees start at policy activation; old draws remain.
        states[key] = {'version': config()['version'], 'pulls': 0,
                       'previous_pulls': runtime['pull_count'].get(str(channel), 0),
                       'since_common': legacy.get('since_a', 0),
                       'since_rare': 0, 'since_up': 0, 'recent': []}
    s = states[key]
    for field, limit in [('pulls', None), ('since_common', 9), ('since_rare', 99), ('since_up', None)]:
        if type(s.get(field)) is not int or s[field] < 0 or (limit is not None and s[field] > limit):
            raise ValueError('Malformed supply pity counter')
    if not isinstance(s.get('recent'), list) or len(s['recent']) > 9:
        raise ValueError('Malformed rolling supply caps')
    return s


def has_up_pity(channel):
    return channel in (3, 5) or config()['standard_up_pity']


def force_category(channel, s):
    rare = 'S' if channel in ROLE_CHANNELS else 'GEAR5'
    common = 'A' if channel in ROLE_CHANNELS else 'GEAR4'
    if has_up_pity(channel) and s['since_up'] >= 199:
        return 'UP'
    if s['since_rare'] >= 99:
        return rare
    # Reserve the preceding draw when exact A/4star and rare/UP guarantees
    # would otherwise collide. S/5star does not replace the requested A/4star.
    if s['since_common'] >= 9 or (s['since_common'] >= 8 and
            (s['since_rare'] >= 98 or (has_up_pity(channel) and s['since_up'] >= 198))):
        return common
    return None


def select(account, channel):
    c = config(); s = state(account, channel); available = choices(channel)
    weights = c['role_weights' if channel in ROLE_CHANNELS else 'equipment_weights']
    caps = c['role_caps' if channel in ROLE_CHANNELS else 'equipment_caps']
    recent = Counter(s['recent'])
    valid = {k: v for k, v in available.items() if recent[k] < caps.get(k, 10)}
    forced = force_category(channel, s)
    rare = 'S' if channel in ROLE_CHANNELS else 'GEAR5'
    if forced == 'UP':
        # Standard, if approved, only receives UP via its200 guarantee.
        options = [x for x in choices(5 if channel in ROLE_CHANNELS else 3)[rare] if is_up(x[0], x[1])]
        # A due UP guarantee takes precedence over the rolling quantity cap.
        # Filtering it by `valid` strands existing saves at pull199 forever:
        # failed transactions cannot advance the window. Ordinary selections
        # still use `valid`; commit records this guaranteed item in the window.
        if channel not in ROLE_CHANNELS:
            family = catalog()[1]
            owned = {family.get((kind, row['id']), row['id'])
                     for kind, key in [('weapon', 'weapon_list'), ('stigmata', 'stigmata_list')]
                     for row in account.get(key, [])}
            missing = [x for x in options if x[1] not in owned]
            options = missing or options
    else:
        category = forced or random.choices(list(valid), [weights[k] for k in valid], k=1)[0]
        if category not in valid:
            raise ValueError('Guarantee conflicts with rolling cap')
        options = valid[category]
    if not options:
        raise ValueError('No supply item satisfies guarantee')
    item_weights = [c['up_weight'] if channel in (3, 5) and is_up(x[0], x[1]) else 1 for x in options]
    return random.choices(options, item_weights, k=1)[0]


def commit(account, channel, item):
    s = state(account, channel); category = tag(item[0], item[1])
    common = 'A' if channel in ROLE_CHANNELS else 'GEAR4'
    rare = 'S' if channel in ROLE_CHANNELS else 'GEAR5'
    s['pulls'] += 1
    s['since_common'] = 0 if category == common else s['since_common'] + 1
    s['since_rare'] = 0 if category == rare else s['since_rare'] + 1
    s['since_up'] = 0 if is_up(item[0], item[1]) else s['since_up'] + 1
    s['recent'] = (s['recent'] + [category])[-9:]
    # Validate before the transaction can be saved.
    state(account, channel)
    if channel in (3, 5):
        import server19_gacha as g
        legacy = g._banner_runtime(account, channel)
        legacy['pulls'] += 1; legacy['since_a'] = s['since_common']
        if is_up(item[0], item[1]): legacy['up_cards'] += 1


def draw(account, channel, num, use_hcoin):
    import server19_gacha as g
    saved = deepcopy(account)
    result = g._charge(account, channel, num, use_hcoin)
    if result:
        g._restore(account, saved); return result, []
    items = []
    for index in range(num):
        for retry in range(g.REROLL_LIMIT):
            snapshot = deepcopy(account)
            item = select(account, channel)
            kind, identity, level, count = item
            try:
                split = g._grant(account, *item)
                commit(account, channel, item)
            except (ValueError, TypeError, KeyError):
                g._restore(account, snapshot); continue
            break
        else:
            g._restore(account, saved); return g.RSP_EQUIPMENT_MATERIAL_LIMIT, []
        items.append({'kind': kind, 'item_id': identity, 'level': level, 'num': count,
                      'rarity': g._rarity_of(kind, identity),
                      'star': g._card_star(identity) if kind == 'avatar_card' else 0,
                      'split_fragment_num': split})
    runtime = g._runtime(account)
    runtime['pull_count'][str(channel)] = runtime['pull_count'].get(str(channel), 0) + num
    runtime['log'].append({'time': int(time.time()), 'channel': channel,
                           'items': [{k: x[k] for k in ('item_id', 'level', 'num')} for x in items]})
    del runtime['log'][:-200]
    return 0, items


def rule(channel):
    if channel in ROLE_CHANNELS:
        value = '每累计十回必出A级女武神，每连续十回最多3名A级、2名S级及2件满星4星装备。100回内必出S级。'
    else:
        value = '每累计十回必出满星4星装备，每连续十回最多3件满星4星、2件满星5星装备。100回内必出满星5星装备。'
    if has_up_pity(channel): value += '200回内必出当期UP；触发该保底时优先于每十回数量限制。'
    if channel == 3: value += 'UP保底优先获得尚未拥有的UP装备。'
    return value + '获得对应物品后重新计算该保底；单回与十回共用累计次数。装备按最高可进化星级分类。'


def probability(channel):
    weights = config()['role_weights' if channel in ROLE_CHANNELS else 'equipment_weights']
    options = choices(channel)
    labels = {'A': 'A级女武神', 'S': 'S级女武神', 'GEAR4': '最高4星装备',
              'GEAR5': '最高5星装备', 'LOW_WEAPON': '低星武器', 'LOW_STIGMATA': '低星圣痕', 'MATERIAL': '材料'}
    rows = []
    for order, (category, weight) in enumerate(weights.items()):
        rows.append({'name': labels[category], 'star': '0', 'content': labels[category],
                     'is_up': False, 'order_value': order, 'prob': f'{weight/100:.2f}%'})
    rare = 'S' if channel in ROLE_CHANNELS else 'GEAR5'
    if channel in (3, 5):
        denominator = sum(config()['up_weight'] if is_up(x[0], x[1]) else 1 for x in options[rare])
        labels_up = {60502: '处刑装·紫苑', 20464: '仿犹大·血之拥抱',
                     30629: '德古拉（上）', 30633: '德古拉（中）', 30637: '德古拉（下）'}
        for item in options[rare]:
            if is_up(item[0], item[1]):
                rows.append({'name': labels_up[item[1]], 'star': '0', 'content': '同档普通单个物品的2倍权重',
                             'is_up': True, 'order_value': len(rows),
                             'prob': f'{weights[rare]/100*config()["up_weight"]/denominator:.4f}%'})
    return {'retcode': 0, 'gacha_type': channel,
            'total_prob_list': [{'name': '基础概率（累计保底及每十回数量限制另行生效）', 'prob': '', 'order_value': 0}],
            'detail_prob_list': rows}
