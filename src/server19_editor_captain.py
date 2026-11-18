"""Captain editor operations against the deployed level table."""
from copy import deepcopy
import time

import server19_avatar_skills as skills
import server19_player_progression as progression


def limits(account, catalog):
    levels = [r['level'] for r in catalog['playerleveldata'] if type(r.get('level')) is int]
    if not levels:
        raise ValueError('缺少舰长等级表')
    main = account['main']
    bonus = skills.cabin4_skill_point_bonus(account)
    return {
        'level': {'min': min(levels), 'max': max(levels)},
        'scoin': {'min': 0, 'max': 100000000},
        'hcoin': {'min': 0, 'max': 0xffffffff},
        'stamina': {'min': 0, 'max': 999},
        'friends_point': {'min': 0, 'max': 100000},
        'skill_point': {'min': 0, 'max': main.get('skill_point_limit', 50 + bonus)},
        'skill_point_limit': {'min': 50 + bonus, 'max': 0xffffffff},
        'equipment_size_limit': {'min': progression.expected_equipment_size_limit(main.get('level', 1)),
                                 'max': 0xffffffff},
    }


def apply(account, catalog, operation):
    result = deepcopy(account)
    main = result['main']
    fields = limits(result, catalog)
    changed = set(operation) - {'op', 'type'}
    if not changed or not changed <= fields.keys():
        raise ValueError('未知舰长编辑项')
    new_level = operation.get('level', main.get('level', 1))
    if type(new_level) is int and fields['level']['min'] <= new_level <= fields['level']['max']:
        fields['equipment_size_limit']['min'] = progression.expected_equipment_size_limit(new_level)
    new_limit = operation.get('skill_point_limit', main.get('skill_point_limit', fields['skill_point']['max']))
    if type(new_limit) is int:
        fields['skill_point']['max'] = new_limit
    # A level change cannot leave invalid experience or capacity.
    for key in changed:
        value = operation[key]
        bounds = fields[key]
        if type(value) is not int or not bounds['min'] <= value <= bounds['max']:
            raise ValueError(f"{key} 允许范围为 {bounds['min']}–{bounds['max']}")
        main[key] = value
    if 'level' in changed:
        if main['level'] < account['main']['level']:
            selected = [row for row in catalog['playerleveldata'] if row.get('level') == main['level']]
            if len(selected) != 1 or type(selected[0].get('avatarLevelLimit')) is not int:
                raise ValueError('舰长等级表缺少角色等级上限')
            cap = selected[0]['avatarLevelLimit']
            if any(a.get('star', 0) > 0 and a.get('level', 1) > cap
                   for a in result.get('avatar_list', [])):
                raise ValueError(f'目标舰长等级的角色等级上限为 {cap}，请先降低超出上限的角色等级')
            for cabin in result.get('cabin_list', []):
                kind, cabin_level = cabin.get('type'), cabin.get('level', 0)
                if kind not in (3, 4, 5) or cabin_level <= 0:
                    continue
                rows = [row for row in catalog.get('cabinleveldata', [])
                        if row.get('cabinType') == kind and row.get('level') == cabin_level]
                if len(rows) != 1 or type(rows[0].get('playerLevelNeed')) is not int:
                    raise ValueError(f'舱室 {kind} 的舰长等级要求不可用')
                needed = rows[0]['playerLevelNeed']
                if main['level'] < needed:
                    raise ValueError(f'舱室 {kind} 的当前等级需要舰长达到 {needed} 级')
        if main['level'] != account['main']['level']:
            main['exp'] = 0
        floor = progression.expected_equipment_size_limit(main['level'])
        main['equipment_size_limit'] = max(main.get('equipment_size_limit', 0), floor)
    if main.get('skill_point', 0) > main.get('skill_point_limit', 0) and \
            changed.intersection({'skill_point', 'skill_point_limit'}):
        raise ValueError('技能点不能超过技能点上限')
    if changed.intersection({'skill_point', 'skill_point_limit'}):
        interval = skills.RECOVERY_INTERVAL
        result['skill_point_runtime'] = {'version': 1, 'interval': interval,
            'next_recover_at': int(time.time()) + interval if main['skill_point'] < main['skill_point_limit'] else None}
    return result
