"""Save-scoped offline GM commands and app-private game-process mailbox."""
from copy import deepcopy
import json
import os
import secrets
import time

import server19_editor_captain as captain
import server19_editor_material_presets as presets
import server19_exboss as exboss
import server19_gm as gameplay
import server19_initialization as initialization
import server19_player_progression as progression
import server19_shop as shop
import server19_stage as stage
import server19_supply_rotation as supply

CATALOG = json.loads((shop.ROOT / 'gm-catalog.json').read_bytes())
SLOTS = {row['key']: row for row in CATALOG['slots']}
RESOURCE_KEYS = ('scoin', 'hcoin', 'stamina')


def common_materials():
    catalog = {
        'materialdata': list(shop.MATERIALS_TABLE.values()),
        'weapondata': list(shop.WEAPONS_TABLE.values()),
        'stigmatadata': list(shop.STIGMATAS_TABLE.values()),
    }
    return [{'id': group['id'], 'name': group['name'],
             'items': [row for row in group['items']
                       if CATALOG['items'].get(str(row['id']), {}).get('available')]}
            for group in presets.build(catalog, {})]


MATERIAL_PRESETS = common_materials()


def replenish(account, group_id):
    group = next((x for x in MATERIAL_PRESETS if x['id'] == group_id and x['items']), None)
    if group is None:
        raise ValueError('未知补充方案')
    for row in group['items']:
        item, target = row['id'], row['num']
        owned = sum(m['num'] for m in account.get('material_list', []) if m['id'] == item)
        if owned < target:
            grant(account, item, target - owned)


def save_gameplay(path, account, request):
    current = gameplay.describe(path.parent)
    next_week = request.get('effective_begin')
    option = request.get('option')
    if option == 'temperature':
        if account.get('endless_runtime', {}).get('active'):
            raise ValueError('请先结束当前深渊战斗')
        current['abyss_temperature'] = request.get('value')
    elif option == 'bosses':
        current['next_bosses'] = request.get('value')
    else:
        raise ValueError('未知玩法设置')
    gameplay.save(path.parent, {k: current[k] for k in ('abyss_temperature', 'next_bosses')}, next_week)
    gameplay.configure(path.parent)


def backup_before_reset(path, begin):
    backup = path.with_name(f'{path.stem}-exboss-{begin}-before-reset-{secrets.token_hex(8)}.json')
    with backup.open('xb') as output:
        output.write(path.read_bytes())
        output.flush()
        os.fsync(output.fileno())


def selection(slot, account):
    if slot['shop'] == 6:
        runtime = shop._get_shop_runtime(account)
        gid = runtime['exchange_house_goods'][slot['index']]
        return str(shop.GOODS_METADATA[gid]['ItemID'])
    return account.get('gm_shelves', {}).get(slot['key'], slot['default'])


def choices_for(slot):
    return CATALOG['choices'][slot['group']]


def shelf_goods(sid, account):
    return [gid for slot in SLOTS.values() if slot['shop'] == sid
            for gid in choices_for(slot)[selection(slot, account)]['goods']]


def replace_slot(account, key, target, expected):
    slot = SLOTS.get(key)
    if slot is None or target not in choices_for(slot):
        raise ValueError('这个商品不适用于所选槽位')
    current = selection(slot, account)
    if current != expected:
        raise ValueError('货架已经变动，请重新选择')
    if any(selection(other, account) == target for other in SLOTS.values()
           if other['group'] == slot['group'] and other != slot):
        raise ValueError('该商品已在同一货架')
    if slot['shop'] == 6:
        runtime = account['shop_runtime']
        runtime['exchange_house_goods'][slot['index']] = choices_for(slot)[target]['goods'][0]
    else:
        account.setdefault('gm_shelves', {})[key] = target


def grant(account, item, quantity):
    meta = CATALOG['items'].get(str(item)) if type(item) is int else None
    if not meta or not meta['available'] or type(quantity) is not int or not 1 <= quantity <= 9999:
        raise ValueError('物品或数量无效')
    kind = meta['kind']
    if kind in ('武器', '圣痕'):
        main = account['main']
        capacity = max(main.get('equipment_size_limit', 0), progression.expected_equipment_size_limit(main.get('level', 1)))
        owned = len(account.get('weapon_list', ())) + len(account.get('stigmata_list', ()))
        if owned >= capacity or quantity != 1:
            raise ValueError('每次发放一件装备，或仓库已满')
    elif kind == '材料道具':
        limit = shop.MATERIALS_TABLE[item].get('quantityLimit', 0)
        count = sum(row.get('num', 0) for row in account.get('material_list', []) if row['id'] == item)
        if limit > 0 and count + quantity > limit:
            raise ValueError('超过物品堆叠上限')
    elif kind == '服饰':
        if quantity != 1 or shop._owns_dress(account, item):
            raise ValueError('服饰只能发放一件，或已经拥有')
    try:
        shop._grant_item(account, item, quantity)
    except ValueError as exc:
        raise ValueError('超过原生仓库限制，或此物品暂不可发放') from exc


def dispatch(account, path, request, *, now=None):
    action = request.get('action')
    with stage._transaction_lock(path):
        now = int(time.time() if now is None else now)
        current = stage._read(path, account)
        before = deepcopy(current)
        if action == 'replace':
            replace_slot(current, str(request.get('slot')), str(request.get('target')), str(request.get('expected')))
        elif action == 'grant':
            grant(current, request.get('item'), request.get('quantity'))
        elif action == 'resources':
            field = request.get('field')
            if field not in RESOURCE_KEYS:
                raise ValueError('未知资源')
            catalog = {'playerleveldata': stage._table('playerleveldata')}
            current = captain.apply(current, catalog, {'op': 'captain', field: request.get('value')})
        elif action == 'replenish':
            replenish(current, request.get('group'))
        elif action == 'gameplay':
            save_gameplay(path, current, request)
        elif action == 'exboss_current':
            operation = request.get('operation')
            if operation not in ('replace', 'reset'):
                raise ValueError('未知记忆战场操作')
            exboss.change_current(current, now, request.get('begin'), request.get('revision'),
                                  operation, request.get('bosses'))
            if operation == 'reset':
                try:
                    backup_before_reset(path, request['begin'])
                except OSError as exc:
                    raise ValueError('无法备份存档，重置未执行') from exc
        elif action == 'supply_switch':
            supply.switch(current, request.get('channel'), request.get('target'), request.get('expected'))
        elif action not in ('state', 'supply_state', 'supply_history'):
            raise ValueError('GM 操作不存在')
        extra = {}
        if action in ('supply_state', 'supply_switch'):
            extra['supply'] = supply.describe(current)
        if action == 'supply_history':
            history = supply.recent(current, request.get('page'))
            extra['supply_history'] = history
            for row in history['rows']:
                for item in row['items']:
                    identity = item['item_id']
                    meta = CATALOG['items'].get(str(identity), {})
                    theme = supply.THEMES.get(row.get('theme'), {})
                    item['name'] = meta.get('name') or next(
                        (name for _, key, name in theme.get('items', ()) if key == identity), '')
        slots = {key: selection(slot, current) for key, slot in SLOTS.items()}
        stage._save(path, before, current)
        stage._sync(account, current)
    packets = []
    if action == 'resources':
        packets.append(initialization.response('GetMainDataReq', current))
    if action in ('grant', 'replenish'):
        shop.sync_owned_dresses(current)
        packets.extend([
            ('GetAvatarDataRsp', {'retcode': 0, 'avatar_list': current.get('avatar_list', [])}),
            ('GetEquipmentDataRsp', {'retcode': 0, 'weapon_list': current.get('weapon_list', []),
                                     'stigmata_list': current.get('stigmata_list', []),
                                     'material_list': [m for m in current.get('material_list', []) if m['num'] > 0]}),
        ])
    if action in ('replace', 'grant'):
        packets.append(('GetShopListRsp', shop.build_shop_list_payload(current)))
    main = current['main']
    return {'ok': True, 'slots': slots, 'resources': {k: main.get(k, 0) for k in RESOURCE_KEYS},
            'presets': [{'id': p['id'], 'name': p['name'], 'items': p['items']} for p in MATERIAL_PRESETS],
            'gameplay': {**gameplay.describe(path.parent, now),
                         'current_exboss': exboss.describe_current(current, now)}, **extra}, packets


def take_request(account, path):
    mailbox = path.parent.parent / 'gm-mailbox'
    pending = mailbox / 'request.json'
    if not pending.is_file():
        return None
    claimed = mailbox / 'processing.json'
    try:
        os.replace(pending, claimed)
    except FileNotFoundError:
        return None
    request = json.loads(claimed.read_bytes())
    claimed.unlink()
    if time.time() * 1000 > request['expires']:
        return None
    try:
        reply, packets = dispatch(account, path, request)
    except ValueError as exc:
        reply, packets = {'ok': False, 'message': str(exc)}, []
    except OSError:
        reply, packets = {'ok': False, 'message': '无法写入存档，请重试'}, []
    return mailbox, request['nonce'], reply, packets


def reply(mailbox, nonce, payload):
    pending = mailbox / 'reply.tmp'
    pending.write_text(json.dumps({'nonce': nonce, **payload}, ensure_ascii=False), encoding='utf-8')
    os.replace(pending, mailbox / 'reply.json')
