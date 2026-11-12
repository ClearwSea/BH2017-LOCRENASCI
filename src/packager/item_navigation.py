"""Keep item acquisition links within the selected native client's tables."""
import re

TABLES = ('materialdata', 'avatarfragmentdata', 'weapondata', 'stigmatadata')
LINK = re.compile(r'<type="(\d+)(?:\|([0-9]+(?:;[0-9]+)*))?" text="([^"<>]+)"/>')
SPLIT_SHOP_TAIL = '630401" text="Obtain_Source_Desc_703201"/>'
# Original 1.9 E_MissionLinkType metadata: 0..41, OpenBrowser=101,
# PlayerProfileAccount=102. Later type 43 has no native dispatch case.
NATIVE_LINK_TYPES = frozenset(range(42)) | {101, 102}


def destination_catalog(tables, output, source):
    """Describe rewards of the generated local runtime, not the reference game."""
    import json
    from .runtime_data import READY
    def read(path):
        return json.loads(path.read_bytes())
    supported = set(range(10101, 10108))
    for key in ('chapter1', 'story', 'extra_story'):
        ready = read(output / READY[key])
        supported.update(ready.get('ready_stage_ids', ready.get('stage_ids', [])))
    befall = read(source / 'server19_befall_drop_policy.json')
    supported.update(map(int, befall))
    repeat = read(source / 'server19_repeat_drop_policy.json')
    equipment = {r['ID'] for name in ('weapondata', 'stigmatadata') for r in tables[name]}
    drops = {}
    for row in tables['stagedata_main']:
        sid = row['levelId']
        if sid not in supported:
            continue
        if str(sid) in befall:
            policy = befall[str(sid)]
            items = {r['id'] for k in ('first', 'repeat') for r in policy[k]
                     if r['num'] > 0 and r['percent'] > 0}
        else:
            items = {r['id'] for r in row['firstDisplayDropList'] if r['num'] > 0}
            items.update(i for i in row['displayDropList']
                         if repeat['weights']['equipment' if i in equipment else 'material'] > 0)
        drops[sid] = items
    activities = {r['weekDayActivityID']: set().union(
        *(drops.get(sid, set()) for sid in r['levelIDList'])) for r in tables['weekdayactivity']}
    goods = {r['ID']: r for r in tables['shopgoodsdata']}
    known = {r['ID'] for name in TABLES for r in tables[name]}
    known.update(r['dressID'] for r in tables['dressdata'])
    shops = {}
    for row in read(source / 'server19_shop_config.json'):
        shops[row['shop_type']] = dict(name=row['shop_name'], items={
            goods[g]['ItemID'] for g in row['goods_pool']
            if g in goods and goods[g]['ItemID'] in known})
    # Native ShopPageContext adds this tab outside GetShopListRsp. Purchases
    # use BuyGachaTicketReq, whose allowed materials come from CHANNELS.
    import ast
    module = ast.parse((source / 'server19_gacha.py').read_text(encoding='utf-8-sig'))
    channels = next(n.value for n in module.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'CHANNELS' for t in n.targets))
    configs = [ast.literal_eval(value) for value in channels.values]
    shops[6] = dict(name='补给卡', items={c['ticket_material_id'] for c in configs
                                       if c.get('hcoin_cost')})
    commissions = read(output / 'server19-run/sakura-commissions-20261025/candidate-v3/catalog.json')
    # Key quests grant levels[].keyQuestReward, not their reference rewardId.
    rewards = {r['rewardId'] for r in commissions['quests']}
    rewards.update(r[k] for r in commissions['levels']
                   for k in ('completeReward', 'monthlyReward', 'keyQuestReward') if r[k])
    world_items = {i['id'] for rid in rewards for i in commissions['rewards'][str(rid)]['item_list']
                   if i['num'] > 0}
    cycles = read(output / 'server19-run/sakura-cycle4-20261026/candidate-v1/catalog.json')
    for key in ('cycle_reward', 'second_cycle_reward', 'third_cycle_reward', 'fourth_cycle_reward'):
        world_items.update(i['id'] for i in cycles[key]['item_list'] if i['num'] > 0)
    world_items.update(i['id'] for r in cycles['rewards'].values()
                       for i in r['item_list'] if i['num'] > 0)
    rewards = {r['RewardID']: r for r in tables['rewarddata']}
    duty_ids = {r['rewardId'] for name in ('dutydailydata', 'dutyweeklydata') for r in tables[name]}
    duty_items = {r[f'RewardItem{i}ID'] for rid in duty_ids for r in (rewards[rid],)
                  for i in range(1, 6) if r[f'RewardItem{i}Num'] > 0}
    return dict(shops=shops, stages=drops, activities=activities, openworld=world_items,
                duty=duty_items)


def reconcile(tables, catalog):
    """Normalize existing acquisition routes against actual local rewards.

    Do not add new gameplay or invent rewards. Shop rows are replaced by all
    configured shops that really stock the item, with one entry per tab.
    Locked but implemented destinations remain available to the native UI.
    """
    report = dict(changed=[], labels=[])
    labels = {f'LocalObtainShop{kind}': '【购买】' + shop['name']
              for kind, shop in catalog['shops'].items()}
    labels['LocalObtainSakura'] = '【获取】樱色轮回任务与奖励'
    for name in TABLES:
        for row in tables.get(name, []):
            old = row.get('comeFromList')
            if old is None:
                continue
            kept, seen, had_shop = [], set(), False
            for entry in old:
                match = LINK.fullmatch(entry)
                if not match:
                    raise ValueError('Normalize navigation before reconciling destinations')
                kind, args, text = int(match[1]), match[2], match[3]
                if kind == 17:
                    had_shop = True
                    continue
                if kind in (10, 11, 15, 16, 30, 37, 39):
                    # Account inventory is not rewarded by these local handlers
                    # (or no local handler exists for this later feature).
                    continue
                if kind == 1 and row['ID'] not in catalog['stages'].get(int(args), set()):
                    continue
                if kind in (2, 3) and row['ID'] not in catalog['activities'].get(int(args or 0), set()):
                    continue
                if kind == 32 and row['ID'] not in catalog['duty']:
                    continue
                if kind == 23:
                    if row['ID'] not in catalog['openworld']:
                        continue
                    args, text = '1', 'LocalObtainSakura'
                    entry = f'<type="23|1" text="{text}"/>'
                destination = kind, args
                if destination not in seen:
                    kept.append(entry)
                    seen.add(destination)
            if had_shop:
                shops = [f'<type="17|{kind}" text="LocalObtainShop{kind}"/>'
                         for kind, shop in catalog['shops'].items() if row['ID'] in shop['items']]
                kept = shops + kept
            if old != kept:
                report['changed'].append(dict(table=name, id=row['ID'], before=old, after=kept))
            row['comeFromList'] = kept
    used = {LINK.fullmatch(e)[3] for name in TABLES for row in tables.get(name, [])
            for e in row.get('comeFromList', [])}
    report['labels'] = [dict(ID=k, Text=v) for k, v in labels.items() if k in used]
    return report


def adapt(tables):
    """Remove unavailable stage destinations; keep every other valid link intact.

    MonoDropLink constructs a LevelDataItem for type 1 even when its stage is
    absent, then dereferences the missing metadata while building the dialog.
    A selected older client must not advertise filtered-out later stages.
    """
    stages = {row['levelId'] for row in tables['stagedata_main']}
    removed = []
    checked = 0
    pending = []
    for name in TABLES:
        for row in tables.get(name, []):
            if 'comeFromList' not in row:
                continue
            kept = []
            for entry in row['comeFromList']:
                checked += 1
                match = LINK.fullmatch(entry) if isinstance(entry, str) else None
                reason = None
                if not match:
                    # The 2.4 source splits a comma inside shop arguments into
                    # two array entries. The existing policy replaces its head
                    # with a compatible shop link; this orphan cannot navigate.
                    if name == 'materialdata' and row['ID'] == 7032 and entry == SPLIT_SHOP_TAIL:
                        reason = 'orphaned source shop argument'
                    else:
                        raise ValueError(f'Malformed item navigation: {name}:{row["ID"]}: {entry!r}')
                elif int(match[1]) not in NATIVE_LINK_TYPES:
                    reason = 'navigation type absent from selected native client'
                elif int(match[1]) == 1:
                    args = match[2]
                    if args is None or ';' in args:
                        raise ValueError(f'Invalid stage navigation arguments: {name}:{row["ID"]}')
                    if int(args) not in stages:
                        reason = 'stage absent from selected client'
                if reason:
                    removed.append(dict(table=name, id=row['ID'], entry=entry, reason=reason))
                else:
                    kept.append(entry)
            pending.append((row, kept))
    # Validate the complete input before changing any lists.
    for row, kept in pending:
        row['comeFromList'] = kept
    return dict(checked_links=checked, removed=removed)


def restore_text(tables, source_rows):
    """Restore only missing acquisition labels from the supplied source textmap."""
    required = set()
    for name in TABLES:
        for row in tables.get(name, []):
            for entry in row.get('comeFromList', []):
                match = LINK.fullmatch(entry)
                if not match:
                    raise ValueError('Normalize navigation before restoring its text')
                required.add(match[3])
    present = {row['ID'] for row in tables['textmap']}
    missing = required - present
    source = {row['ID']: row['Text'] for row in source_rows if row['ID'] in missing}
    if missing - source.keys():
        raise ValueError('Missing source acquisition text: ' + ', '.join(sorted(missing - source.keys())))
    tables['textmap'].extend({'ID': key, 'Text': source[key]} for key in sorted(missing))
    return sorted(missing)
