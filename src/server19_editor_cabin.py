"""Pure edits for the three locally implemented Island cabins.

The caller supplies decoded runtime tables. Edits return a deep copy and do not
advance clocks, finish ongoing upgrades, or change other Island state.
"""
from copy import deepcopy


def _integer(value, name, minimum=0, maximum=0xffffffff):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Invalid {name}')
    return value


def _table(catalog, name):
    rows = catalog.get(name)
    if not isinstance(rows, list):
        raise ValueError('Missing table: ' + name)
    return rows


def _unique(rows, **fields):
    selected = [row for row in rows if all(row.get(k) == v for k, v in fields.items())]
    if len(selected) != 1:
        raise ValueError('Missing or duplicate cabin table row')
    return selected[0]


def _bonus(cabin, catalog):
    if cabin.get('type') != 4:
        return 0
    result = 0
    for tech in cabin.get('tech_list', []):
        node = _unique(_table(catalog, 'cabintechtreedata'), Cabin=4,
                       X=tech.get('pos_x'), Y=tech.get('pos_y'))
        if node.get('AbilityType') == 11 and cabin['level'] >= node['UnlockLevel']:
            result += _integer(node.get('Argument1'), 'skill point bonus')
    return result


def _validate(cabin, catalog, account):
    kind = cabin['type']
    level = _integer(cabin.get('level'), 'cabin level', 1)
    grade = _integer(cabin.get('extend_grade'), 'cabin extension', 1)
    level_row = _unique(_table(catalog, 'cabinleveldata'), cabinType=kind, level=level)
    grade_row = _unique(_table(catalog, 'cabinextendgradedata'), cabinType=kind, extendGrade=grade)
    if level > grade_row['cabinLevelMax']:
        raise ValueError('Cabin level exceeds extension limit')
    if account.get('main', {}).get('level', 0) < level_row['playerLevelNeed']:
        raise ValueError('Captain level is below the cabin requirement')
    seen = set()
    for tech in cabin.get('tech_list', []):
        position = (tech.get('pos_x'), tech.get('pos_y'))
        if position in seen:
            raise ValueError('Duplicate cabin technology')
        seen.add(position)
        node = _unique(_table(catalog, 'cabintechtreedata'), Cabin=kind, X=position[0], Y=position[1])
        if level < node['UnlockLevel']:
            raise ValueError('Existing technology requires a higher cabin level')
        avatar_id = node.get('UnlockAvatarID', 0)
        if avatar_id and not any(a.get('avatar_id') == avatar_id and a.get('star', 0) > 0 and
                                 a.get('level', 0) >= node.get('UnlockAvatarLevel', 0)
                                 for a in account.get('avatar_list', [])):
            raise ValueError('Technology requires an unlocked character at a higher level')


def apply(account, catalog, operation):
    if not isinstance(account, dict) or not isinstance(catalog, dict) or not isinstance(operation, dict):
        raise ValueError('Expected account, catalog and operation objects')
    command = operation.get('op', operation.get('type'))
    if 'op' in operation and 'type' in operation and operation['op'] != operation['type']:
        raise ValueError('Conflicting operation names')
    if command not in ('cabin', 'cabin_tech'):
        raise ValueError('Unknown cabin operation')
    if command == 'cabin_tech':
        raise ValueError('Technology is read-only until native power and prerequisite rules are verified')
    kind = _integer(operation.get('cabin_type'), 'cabin type', 3, 5)
    result = deepcopy(account)
    cabins = result.setdefault('cabin_list', [])
    matching = [row for row in cabins if row.get('type') == kind]
    if len(matching) > 1:
        raise ValueError('Duplicate cabin')
    if matching:
        cabin = matching[0]
    else:
        cabin = {'type': kind, 'level': 1, 'extend_grade': 1,
                 'level_up_end_time': 0, 'tech_list': []}
        cabins.append(cabin)
    if cabin.get('level_up_end_time', 0):
        raise ValueError('Finish the ongoing cabin upgrade in game first')
    old_bonus = _bonus(cabin, catalog)
    for key in ('level', 'extend_grade'):
        if key in operation:
            requested = _integer(operation[key], key, 1)
            if requested < cabin.get(key, 1):
                raise ValueError('Lowering a cabin level or extension is not yet verified')
            cabin[key] = requested
    _validate(cabin, catalog, result)
    if kind == 4:
        main = result.setdefault('main', {})
        old_limit = _integer(main.get('skill_point_limit', 50), 'skill point limit')
        custom_base = max(50, old_limit - old_bonus)
        main['skill_point_limit'] = _integer(custom_base + _bonus(cabin, catalog), 'skill point limit')
    return result
