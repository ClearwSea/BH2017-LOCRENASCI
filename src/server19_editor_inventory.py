"""Pure account inventory edits driven by explicitly supplied client tables.

``apply`` is transactional: it returns a deep copy and never changes its input.
Catalog entries are the decoded rows of the runtime's tables, not editor-owned
copies of game data. The calling bridge is responsible for loading that data.
"""
from copy import deepcopy


SLOTS = {1: 'weapon_unique_id', 2: 'stigmata_unique_id_1',
         3: 'stigmata_unique_id_2', 4: 'stigmata_unique_id_3'}
U32 = (1 << 32) - 1


def _int(value, name, lo=0, hi=U32):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{name} must be an integer in {lo}..{hi}')
    return value


def _rows(catalog, name):
    rows = catalog.get(name)
    if not isinstance(rows, list):
        raise ValueError('Missing table: ' + name)
    return rows


def _one(rows, key, value):
    found = [row for row in rows if row.get(key) == value]
    if len(found) != 1:
        raise ValueError(f'Missing or duplicate {key}: {value}')
    return found[0]


def _meta(catalog, table, key, value):
    return _one(_rows(catalog, table), key, value)


def _avatar(account, identity):
    return _one(account.get('avatar_list', []), 'avatar_id', identity)


def _inventory(account):
    items = {}
    for key, kind, low, high in [('weapon_list', 'weapon', 1, 19999),
                                  ('stigmata_list', 'stigmata', 20001, 39999)]:
        for item in account.get(key, []):
            uid = _int(item.get('unique_id'), 'equipment UID', low, high)
            if uid in items:
                raise ValueError('Duplicate equipment UID')
            items[uid] = (kind, item)
    return items


def _owners(account, uid):
    return [(a, slot) for a in account.get('avatar_list', [])
            for slot, field in SLOTS.items() if a.get(field, 0) == uid]


def _locked(account, avatar_id=None, uid=None):
    active = (account.get('stage_runtime') or {}).get('active') or {}
    if avatar_id is not None and avatar_id in active.get('avatar_id_list', []):
        return True
    ex = account.get('exboss_runtime') or {}
    groups = list((ex.get('bosses') or {}).values())
    if ex.get('active'):
        groups.append(ex['active'])
    for group in groups:
        if avatar_id is not None and avatar_id in group.get('avatars', group.get('team', [])):
            return True
        if uid is not None and (uid in group.get('weapons', []) or uid in group.get('stigmata', [])):
            return True
    return False


def _editable(account, avatar_id=None, uid=None):
    if _locked(account, avatar_id, uid):
        raise ValueError('Character or equipment is locked by an active battle or Memorial Arena')
    if uid:
        for owner, _ in _owners(account, uid):
            if _locked(account, avatar_id=owner.get('avatar_id')):
                raise ValueError('Equipment is worn by a character locked in battle')


def _equipment_meta(catalog, kind, identity):
    return _meta(catalog, 'weapondata' if kind == 'weapon' else 'stigmatadata', 'ID', identity)


def _equipment_values(catalog, kind, item):
    meta = _equipment_meta(catalog, kind, item['id'])
    maximum = _int(meta.get('maxLv'), 'equipment max level', 1)
    level = _int(item.get('level'), 'equipment level', 1, maximum)
    exp_type = _int(meta.get('expType'), 'equipment experience type', 1, 7)
    row = _meta(catalog, 'equipmentleveldata', 'level', level)
    thresholds = row.get('Type1')
    if not isinstance(thresholds, list) or exp_type >= len(thresholds):
        raise ValueError('Missing equipment experience threshold')
    limit = _int(thresholds[exp_type], 'equipment experience threshold', 1)
    _int(item.get('exp', 0), 'equipment exp', 0, limit if level == maximum else limit - 1)
    if type(item.get('is_protected', False)) is not bool:
        raise ValueError('Invalid equipment protection')
    return meta


def _equip_check(account, catalog, avatar, slot, uid):
    if slot not in SLOTS or (slot == 1 and not uid):
        raise ValueError('Invalid or empty weapon slot')
    items = _inventory(account)
    if uid:
        if uid not in items:
            raise ValueError('Equipment not found')
        kind, item = items[uid]
        meta = _equipment_values(catalog, kind, item)
        ameta = _meta(catalog, 'avatardata', 'avatarID', avatar['avatar_id'])
        if slot == 1:
            compatible = kind == 'weapon' and meta.get('baseType') in ameta.get('weaponBaseTypeList', [])
        else:
            compatible = kind == 'stigmata' and meta.get('baseType') == slot - 1
        if not compatible or (kind == 'stigmata' and item.get('is_affix_identify', True) is not True):
            raise ValueError('Equipment is not compatible with this slot')
        if any(owner is not avatar or position != slot for owner, position in _owners(account, uid)):
            raise ValueError('Equipment is already worn')
    total = 0
    for position, field in SLOTS.items():
        candidate = uid if position == slot else avatar.get(field, 0)
        if candidate:
            if candidate not in items:
                raise ValueError('Missing equipped item')
            kind, item = items[candidate]
            total += _int(_equipment_meta(catalog, kind, item['id']).get('cost'), 'equipment cost')
    max_cost = _meta(catalog, 'avatarleveldata', 'level', avatar['level']).get('cost')
    if total > _int(max_cost, 'avatar maximum equipment cost'):
        raise ValueError('Equipment cost exceeds character capacity')


def _allocate(account, kind):
    items = _inventory(account)
    low, high = (1, 19999) if kind == 'weapon' else (20001, 39999)
    uid = next((candidate for candidate in range(low, high + 1) if candidate not in items), None)
    if uid is None:
        raise ValueError('Equipment UID range is exhausted')
    return uid


def _new_equipment(account, catalog, kind, identity, level=1, exp=0, protected=False):
    if kind not in ('weapon', 'stigmata'):
        raise ValueError('Unknown equipment kind')
    item = {'unique_id': _allocate(account, kind), 'id': _int(identity, 'equipment id', 1),
            'level': level, 'exp': exp, 'is_protected': protected}
    _equipment_values(catalog, kind, item)
    account.setdefault(kind + '_list', []).append(item)
    return item


def _set_skill(account, catalog, identity, skill_id, sub_id, level):
    avatar = _avatar(account, identity)
    if avatar.get('star', 0) <= 0:
        raise ValueError('Character is locked')
    meta = _meta(catalog, 'avatardata', 'avatarID', identity)
    submeta = _meta(catalog, 'avatarsubskilldata', 'avatarSubSkillId', sub_id)
    if skill_id not in meta.get('skillList', []) or submeta.get('skillId') != skill_id:
        raise ValueError('Skill does not belong to character')
    _int(level, 'skill level', 0, _int(submeta.get('maxLv'), 'skill max level'))
    skills = avatar.setdefault('skill_list', [])
    found = [entry for entry in skills if entry.get('skill_id') == skill_id]
    if len(found) > 1:
        raise ValueError('Duplicate skill')
    if not found:
        found = [{'skill_id': skill_id, 'sub_skill_list': []}]
        skills.extend(found)
    subs = found[0].setdefault('sub_skill_list', [])
    rows = [entry for entry in subs if entry.get('sub_skill_id') == sub_id]
    if len(rows) > 1:
        raise ValueError('Duplicate subskill')
    if rows:
        rows[0]['level'] = level
    else:
        subs.append({'sub_skill_id': sub_id, 'level': level, 'is_mask': False})


def _skill(account, catalog, op):
    identity = (_int(op.get('avatar_id'), 'avatar_id', 1),
                _int(op.get('skill_id'), 'skill_id', 1),
                _int(op.get('sub_skill_id'), 'sub_skill_id', 1))
    _editable(account, avatar_id=identity[0])
    _set_skill(account, catalog, *identity, op.get('level'))
    for pair in _rows(catalog, 'avatarexdata'):
        for entry in pair.get('commonSubSkillList', []):
            try:
                sides = [tuple(int(part) for part in entry[key].split('-')) for key in ('Skill1', 'Skill2')]
            except (KeyError, ValueError, AttributeError) as exc:
                raise ValueError('Malformed shared skill mapping') from exc
            if identity not in sides:
                continue
            other = sides[1] if sides[0] == identity else sides[0]
            owned = [row for row in account.get('avatar_list', []) if row.get('avatar_id') == other[0]]
            if len(owned) > 1:
                raise ValueError('Duplicate character')
            if owned and owned[0].get('star', 0) > 0:
                _editable(account, avatar_id=other[0])
                _set_skill(account, catalog, *other, op.get('level'))


def _costume(account, catalog, dress_id, owned):
    if type(owned) is not bool:
        raise ValueError('Costume ownership must be boolean')
    meta = _meta(catalog, 'dressdata', 'dressID', dress_id)
    if meta.get('dressType') != 1 or not isinstance(meta.get('avatarIDList'), list):
        raise ValueError('Costume is not an unlockable character outfit')
    inventory = account.setdefault('has_got_item_id_list', [])
    if owned and dress_id not in inventory:
        inventory.append(dress_id)
    elif not owned:
        inventory[:] = [value for value in inventory if value != dress_id]
    for avatar in account.get('avatar_list', []):
        if avatar.get('avatar_id') not in meta['avatarIDList']:
            continue
        dresses = avatar.setdefault('dress_list', [])
        if owned and dress_id not in dresses:
            dresses.append(dress_id)
        elif not owned:
            dresses[:] = [value for value in dresses if value != dress_id]
            if avatar.get('dress_id') == dress_id:
                avatar['dress_id'] = 0


def _material(account, catalog, identity, num, minimum=False):
    meta = _meta(catalog, 'materialdata', 'ID', identity)
    if any(row.get('avatarFragmentID') == identity for row in _rows(catalog, 'avatardata')):
        raise ValueError('Use character fragment editing for fragments')
    limit = _int(meta.get('quantityLimit'), 'material limit')
    _int(num, 'material quantity', 0, limit)
    if minimum and num and num >= limit:
        raise ValueError('Material batch target must leave room for rewards')
    materials = account.setdefault('material_list', [])
    found = [row for row in materials if row.get('id') == identity]
    if len(found) > 1:
        raise ValueError('Duplicate material')
    if found:
        if not minimum or found[0].get('num', 0) < num:
            found[0]['num'] = num
    elif num:
        materials.append({'id': identity, 'num': num})


def _edit_avatar(account, catalog, op):
    identity = _int(op.get('avatar_id'), 'avatar_id', 1)
    meta = _meta(catalog, 'avatardata', 'avatarID', identity)
    candidates = [a for a in account.setdefault('avatar_list', []) if a.get('avatar_id') == identity]
    if len(candidates) > 1:
        raise ValueError('Duplicate character')
    avatar = candidates[0] if candidates else None
    old_star = avatar.get('star', 0) if avatar else 0
    star = _int(op.get('star', old_star), 'character rank', 0, 5)
    if star and star < _int(meta.get('unlockStar'), 'initial rank', 1, 5):
        raise ValueError('Character rank is below its initial rank')
    _editable(account, avatar_id=identity)
    for pair in _rows(catalog, 'avatarexdata'):
        ids = pair.get('avatarIDList', [])
        if len(ids) != 2:
            continue
        if star and identity == ids[1] and not any(a.get('avatar_id') == ids[0] and a.get('star', 0) > 0 for a in account['avatar_list']):
            raise ValueError('Unlock the original character before its awakened version')
        if not star and identity == ids[0] and any(a.get('avatar_id') == ids[1] and a.get('star', 0) > 0 for a in account['avatar_list']):
            raise ValueError('Lock the awakened character first')
    if old_star and not star:
        if sum(bool(a.get('star', 0)) for a in account['avatar_list']) <= 1:
            raise ValueError('Cannot lock the last unlocked character')
        for key in ('avatar_team_list', 'custom_avatar_team_list'):
            for team in account.get(key, []):
                if identity in team.get('avatar_id_list', []):
                    raise ValueError('Remove character from saved teams first')
    if avatar is None:
        avatar = {'avatar_id': identity, 'star': 0, 'level': 1, 'exp': 0, 'fragment': 0}
        account['avatar_list'].append(avatar)
    if star and not old_star:
        if not avatar.get('weapon_unique_id'):
            weapon = _new_equipment(account, catalog, 'weapon', meta['initialWeapon'])
            avatar['weapon_unique_id'] = weapon['unique_id']
        for key in ('touch_goodfeel', 'stage_goodfeel', 'stigmata_unique_id_1',
                    'stigmata_unique_id_2', 'stigmata_unique_id_3'):
            avatar.setdefault(key, 0)
        avatar.setdefault('skill_list', [])
        owned_dresses = account.get('has_got_item_id_list', [])
        dresses = avatar.setdefault('dress_list', [])
        for dress in _rows(catalog, 'dressdata'):
            if dress.get('dressID') in owned_dresses and identity in dress.get('avatarIDList', []) and dress['dressID'] not in dresses:
                dresses.append(dress['dressID'])
    avatar['star'] = star
    if 'level' in op:
        if not star:
            raise ValueError('Cannot change the level of a locked character')
        captain = account.get('main', {}).get('level')
        cap = _meta(catalog, 'playerleveldata', 'level', captain).get('avatarLevelLimit')
        level = _int(op['level'], 'character level', 1, _int(cap, 'character level cap', 1))
        _meta(catalog, 'avatarleveldata', 'level', level)
        if level != avatar.get('level'):
            avatar['level'], avatar['exp'] = level, 0
            if avatar.get('weapon_unique_id'):
                _equip_check(account, catalog, avatar, 1, avatar['weapon_unique_id'])
    for key in ('touch_goodfeel', 'stage_goodfeel'):
        if key in op:
            if not star:
                raise ValueError('Cannot change affection of a locked character')
            avatar[key] = _int(op[key], key)
    if 'fragment' in op:
        fragment = _meta(catalog, 'avatarfragmentdata', 'ID', meta.get('avatarFragmentID'))
        if any(row.get('id') == meta.get('avatarFragmentID') for row in account.get('material_list', [])):
            raise ValueError('Legacy material fragment stack needs migration before editing')
        avatar['fragment'] = _int(op['fragment'], 'fragment count', 0,
                                  _int(fragment.get('quantityLimit'), 'fragment limit'))
    if star and not old_star:
        # Reconcile existing shared skills on both now-unlocked forms. Sparse
        # skills are treated as level zero, as in server19_avatar_cultivation.
        for pair in _rows(catalog, 'avatarexdata'):
            for entry in pair.get('commonSubSkillList', []):
                try:
                    sides = [tuple(map(int, entry[key].split('-'))) for key in ('Skill1', 'Skill2')]
                except (KeyError, ValueError, AttributeError) as exc:
                    raise ValueError('Malformed shared skill mapping') from exc
                if identity not in [side[0] for side in sides]:
                    continue
                chars = [next((a for a in account['avatar_list'] if a.get('avatar_id') == side[0] and a.get('star', 0)), None) for side in sides]
                if not all(chars):
                    continue
                levels = []
                for side, char in zip(sides, chars):
                    skill = next((s for s in char.get('skill_list', []) if s.get('skill_id') == side[1]), {})
                    sub = next((s for s in skill.get('sub_skill_list', []) if s.get('sub_skill_id') == side[2]), {})
                    levels.append(sub.get('level', 0))
                if max(levels):
                    for side in sides:
                        _editable(account, avatar_id=side[0])
                        _set_skill(account, catalog, *side, max(levels))


def describe(account, catalog):
    """Return editor state and tables as independent JSON-compatible values."""
    return {'account': deepcopy(account), 'catalog': deepcopy(catalog)}


def apply(account, catalog, operation):
    if not isinstance(account, dict) or not isinstance(catalog, dict) or not isinstance(operation, dict):
        raise ValueError('Expected account, catalog and operation objects')
    result = deepcopy(account)
    kind = operation.get('type', operation.get('op'))
    if 'type' in operation and 'op' in operation and operation['type'] != operation['op']:
        raise ValueError('Conflicting editor operation names')
    if kind == 'avatar':
        _edit_avatar(result, catalog, operation)
    elif kind == 'skill':
        _skill(result, catalog, operation)
    elif kind == 'costume':
        if 'owned' in operation:
            _costume(result, catalog, _int(operation.get('dress_id'), 'dress_id', 1), operation['owned'])
        else:
            identity = _int(operation.get('avatar_id'), 'avatar_id', 1)
            avatar = _avatar(result, identity)
            dress = _int(operation.get('equip'), 'dress_id')
            _editable(result, avatar_id=identity)
            if not avatar.get('star', 0):
                raise ValueError('Character is locked')
            if dress not in (0, identity):
                meta = _meta(catalog, 'dressdata', 'dressID', dress)
                if dress not in avatar.get('dress_list', []) or identity not in meta.get('avatarIDList', []) or meta.get('dressType') != 1:
                    raise ValueError('Costume is not unlocked for character')
                for other in result.get('avatar_list', []):
                    if other is not avatar and other.get('dress_id') == dress:
                        other['dress_id'] = 0
            avatar['dress_id'] = 0 if dress == identity else dress
    elif kind == 'costume_all':
        if operation.get('owned') is not True:
            raise ValueError('Only bulk unlock is supported')
        for meta in _rows(catalog, 'dressdata'):
            if meta.get('dressType') == 1 and meta.get('avatarIDList'):
                _costume(result, catalog, meta['dressID'], True)
    elif kind == 'material':
        _material(result, catalog, _int(operation.get('id'), 'material id', 1), operation.get('num'))
    elif kind == 'materials_batch':
        items = operation.get('items')
        if not isinstance(items, list):
            raise ValueError('Missing material batch')
        for item in items:
            _material(result, catalog, _int(item.get('id'), 'material id', 1), item.get('num'), True)
    elif kind == 'equipment_add':
        _new_equipment(result, catalog, operation.get('kind'), operation.get('id'),
                       operation.get('level', 1), operation.get('exp', 0), operation.get('is_protected', False))
    elif kind == 'equipment_exchange':
        first_id = _int(operation.get('avatar_id_1'), 'first avatar_id', 1)
        second_id = _int(operation.get('avatar_id_2'), 'second avatar_id', 1)
        if first_id == second_id:
            raise ValueError('Two different characters are required')
        first, second = _avatar(result, first_id), _avatar(result, second_id)
        if not first.get('star', 0) or not second.get('star', 0):
            raise ValueError('Both characters must be unlocked')
        first_uid, second_uid = first.get('weapon_unique_id', 0), second.get('weapon_unique_id', 0)
        if not first_uid or not second_uid or first_uid == second_uid:
            raise ValueError('Two different equipped weapons are required')
        for identity, uid in ((first_id, first_uid), (second_id, second_uid)):
            _editable(result, avatar_id=identity, uid=uid)
        first['weapon_unique_id'], second['weapon_unique_id'] = second_uid, first_uid
        _equip_check(result, catalog, first, 1, second_uid)
        _equip_check(result, catalog, second, 1, first_uid)
    elif kind in ('equipment_edit', 'equipment_delete', 'equipment_equip'):
        uid = _int(operation.get('unique_id'), 'equipment UID')
        items = _inventory(result)
        if kind == 'equipment_equip':
            identity = _int(operation.get('avatar_id'), 'avatar_id', 1)
            avatar = _avatar(result, identity)
            slot = _int(operation.get('slot'), 'equipment slot', 1, 4)
            if not avatar.get('star', 0):
                raise ValueError('Character is locked')
            _editable(result, avatar_id=identity, uid=uid)
            _editable(result, uid=avatar.get(SLOTS[slot], 0))
            _equip_check(result, catalog, avatar, slot, uid)
            avatar[SLOTS[slot]] = uid
        else:
            if uid not in items:
                raise ValueError('Equipment not found')
            _editable(result, uid=uid)
            equipment_kind, item = items[uid]
            if kind == 'equipment_edit':
                for key in ('level', 'exp', 'is_protected'):
                    if key in operation:
                        item[key] = operation[key]
                _equipment_values(catalog, equipment_kind, item)
            else:
                owners = _owners(result, uid)
                if len(owners) > 1:
                    raise ValueError('Equipment has multiple owners')
                if owners:
                    avatar, slot = owners[0]
                    _editable(result, avatar_id=avatar['avatar_id'])
                    replacement = _int(operation.get('replacement_uid', 0), 'replacement UID')
                    if replacement == uid:
                        raise ValueError('Replacement must be another item')
                    _editable(result, uid=replacement)
                    _equip_check(result, catalog, avatar, slot, replacement)
                    avatar[SLOTS[slot]] = replacement
                result[equipment_kind + '_list'].remove(item)
    else:
        raise ValueError('Unsupported editor operation: ' + str(kind))
    return result
