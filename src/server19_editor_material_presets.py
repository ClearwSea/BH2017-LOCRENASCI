"""Data-backed common material batch suggestions for the save editor.

These are modest minimum quantities, not game drop rules. Existing larger
stacks remain unchanged. IDs are selected only from proven runtime sources.
"""
from collections import Counter


def build(catalog, channels):
    materials = catalog.get('materialdata')
    weapons = catalog.get('weapondata')
    stigmata = catalog.get('stigmatadata')
    if not all(isinstance(v, list) for v in (materials, weapons, stigmata)) or not isinstance(channels, dict):
        raise ValueError('缺少材料、装备或补给目录')
    by_id = {}
    for row in materials:
        identity = row.get('ID')
        if type(identity) is not int or identity in by_id:
            raise ValueError('材料目录存在无效或重复 ID')
        by_id[identity] = row
    evolution_frequency = Counter()
    for equip in weapons + stigmata:
        entries = equip.get('evoMaterial', [])
        if not isinstance(entries, list):
            raise ValueError('装备进化材料表格式错误')
        for value in entries:
            if value == '0':
                continue
            if not isinstance(value, str) or ':' not in value:
                raise ValueError('装备进化材料表格式错误')
            try:
                identity, amount = map(int, value.split(':'))
            except ValueError as exc:
                raise ValueError('装备进化材料表格式错误') from exc
            if amount > 0 and identity in by_id and by_id[identity].get('ItemType') == 'evo_material':
                evolution_frequency[identity] += 1
    ticket_ids = {v.get('ticket_material_id') for v in channels.values() if isinstance(v, dict)} - {0, None}
    groups = [
        ('avatar_exp', '角色经验芯片', [i for i in range(1001, 1009) if i in by_id and
          by_id[i].get('ItemType') == 'exp_item' and by_id[i].get('characterExpProvide', 0) > 0], 500),
        ('equipment_exp', '装备强化材料', [i for i in range(3000, 3009) if i in by_id and
          by_id[i].get('ItemType') == 'evo_material' and by_id[i].get('gearExpProvideBase', 0) > 0], 500),
        ('equipment_evolution', '常用装备进化材料', [i for i, count in evolution_frequency.items() if count >= 5], 200),
        ('supply_tickets', '当前补给券', [i for i in ticket_ids if i in by_id and
          by_id[i].get('ItemType') == 'gacha_item'], 100),
    ]
    result = []
    for key, label, ids, target in groups:
        items = []
        for identity in sorted(ids):
            limit = by_id[identity].get('quantityLimit')
            if type(limit) is not int or limit <= 1:
                continue
            items.append({'id': identity, 'num': min(target, limit - 1)})
        if items:
            result.append({'id': key, 'name': label, 'items': items})
    return result
