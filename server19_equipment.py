"""Original 1.9 equipment and dress commands using the shared account transaction.

DressEquipmentReq (39) changes one native equipment slot; unique_id=0
removes a stigmata. The original UI does not allow an empty weapon slot.
An occupied weapon is transferred by ExchangeAvatarWeaponReq (135), while
the native stigmata confirmation sends separate unequip/equip requests.
SetDressReq (248) changes an avatar's equipped outfit; dress_id=0 or
dress_id=avatar_id restores the default outfit.
EquipmentPowerUpReq (31) strengthens checked evolution closures with material
3000. EquipmentEvoReq (37) follows exact recipes. Formula and protocol are the
original 1.9 consumer's;
table values and cost rate are the already accepted 2.4/7.0 reference values,
not independently recovered historical 1.9 server economy. Unknown equipment
fodder, boosts, discounts, special conversions and unchecked models remain unsupported.
No items, affixes, skills, or panel values are created here.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import struct
import threading

import server19_stage as stage
import server19_protocol as proto

HANDLED_REQUESTS = frozenset(("DressEquipmentReq", "ExchangeAvatarWeaponReq",
                              "EquipmentPowerUpReq", "EquipmentEvoReq", "EquipSynthesisReq",
                              "UpdateEquipmentProtectedStatusReq", "SetDressReq"))
SLOT_FIELDS = {1: "weapon_unique_id", 2: "stigmata_unique_id_1",
               3: "stigmata_unique_id_2", 4: "stigmata_unique_id_3"}

# Original proto.EquipmentType and Rsp32.Retcode constants. The native request
# builder72993@1155d01 sets num only for material; equipment descriptors use 0.
MATERIAL = 1
WEAPON = 3
STIGMATA = 4
POWER_UP_TARGET_IDS = frozenset((20001, 20041, 30001, 30004, 30057, 30110))
POWER_UP_CONFIG = {"same_type_power_up_rate": 100,
                   "power_up_scoin_cost_rate": 50}
# No original server probability has been recovered. This explicit existing
# local policy gives the ordinary 100% outcome, never an invented random bonus.
POWER_UP_BOOST_RATE = 100
FULL_CULTIVATION_READY_FILE = None  # Explicitly selected only by the updated local instance.
EXTRA_AUDITED_GROWTH_IDS = frozenset()  # Explicit reviewed per-instance dependency additions.
_REJECTION = threading.local()
_MUTATION = threading.local()
_POWER_UP_TABLE_HASHES = {
    "weapondata": "82db882548dbed50a4d024dab08061cb8a7c48d265b6942f9d31467629e25c34",
    "stigmatadata": "fbf59b98e37855475e2559357dbdba6416489451c79ef4b8d6759e3b4614ebbd",
    "materialdata": "c020cadada3bbe99eae313be315a704224d6ecea166c9816d047cce6d2250da0",
    "equipmentleveldata": "c65341912abc5287b5852053a01cb7d5a9fc1148326d666bd598ed2685444599",
    "materialexpbonusdata": "cce3bbd71c88b00bff8593cda5b180b316d23860a2d24624cccf3beead6d7641",
}


class _Rejected(Exception):
    def __init__(self, retcode):
        self.retcode = retcode


def _metadata(table, identity, field="ID"):
    rows = [row for row in stage._table(table) if row.get(field) == identity]
    if len(rows) != 1:
        raise ValueError("Missing or ambiguous equipment/avatar metadata")
    return rows[0]


def _avatars(account):
    result = {}
    for avatar in account["avatar_list"]:
        avatar_id = stage._u32(avatar["avatar_id"], "avatar_id")
        if not avatar_id or avatar_id in result:
            raise ValueError("Duplicate or empty owned avatar identity")
        result[avatar_id] = avatar
    return result


def _inventory(account):
    result = {}
    # These are the native UID_BEGIN_NUM/MAX_UID_NUM ranges. As in the
    # reward writer, stay inside the boundaries, not on either sentinel.
    for key, kind, low, high in (("weapon_list", "weapon", 0, 20000),
                                ("stigmata_list", "stigmata", 20000, 40000)):
        for item in account[key]:
            uid = stage._u32(item["unique_id"], "unique_id")
            if not low < uid < high or uid in result:
                raise ValueError("Duplicate or invalid native equipment UID")
            result[uid] = (kind, item)
    return result


def _item(inventory, uid):
    kind, item = inventory[uid]
    table = "weapondata" if kind == "weapon" else "stigmatadata"
    metadata = _metadata(table, stage._u32(item["id"], "equipment id"))
    level = stage._u32(item["level"], "equipment level")
    if not 1 <= level <= metadata["maxLv"]:
        raise ValueError("Equipment level is outside its metadata range")
    return kind, item, metadata


def _owners(avatars, uid):
    return [(avatar_id, slot) for avatar_id, avatar in avatars.items()
            for slot, field in SLOT_FIELDS.items() if avatar.get(field, 0) == uid]


def _compatible(avatar, kind, metadata, slot):
    if slot == 1:
        avatar_metadata = _metadata("avatardata", avatar["avatar_id"], "avatarID")
        return kind == "weapon" and metadata["baseType"] in \
            avatar_metadata["weaponBaseTypeList"]
    return kind == "stigmata" and metadata["baseType"] == slot - 1


def _max_cost(avatar):
    # AvatarDataItem.get_MaxCost51638@1336a0b reads avatarleveldata.cost
    # plus PlayerDataItem.costAddByAvatarStar. GetConfigRsp currently sends
    # no avatar_cost_plus_config_list, so that native dictionary is empty.
    _metadata("avatardata", avatar["avatar_id"], "avatarID")
    level = stage._u32(avatar["level"], "avatar level")
    return stage._u32(_metadata("avatarleveldata", level, "level")["cost"],
                      "avatar maximum cost")


def _cost(avatar, inventory, changed_slot, changed_uid):
    total = 0
    for slot, field in SLOT_FIELDS.items():
        uid = changed_uid if slot == changed_slot else avatar.get(field, 0)
        uid = stage._u32(uid, "equipped unique_id")
        if not uid:
            continue
        kind, _, metadata = _item(inventory, uid)
        if not _compatible(avatar, kind, metadata, slot):
            raise ValueError("Account contains incompatible equipped item")
        total += stage._u32(metadata["cost"], "equipment cost")
    return total


def _dress(account, values):
    avatar_id = stage._u32(values["avatar_id"], "avatar_id")
    uid = stage._u32(values["unique_id"], "unique_id")
    slot = values["slot"]
    avatars = _avatars(account)
    if avatar_id not in avatars:
        raise _Rejected(2)  # AVATAR_NOT_EXIST
    if type(slot) is not int or slot not in SLOT_FIELDS or (slot == 1 and uid == 0):
        raise _Rejected(5)  # EQUIPMENT_SLOT_ERROR
    avatar = avatars[avatar_id]
    _max_cost(avatar)
    inventory = _inventory(account)
    if uid:
        if uid not in inventory:
            raise _Rejected(3)  # EQUIPMENT_NOT_EXIST
        kind, item, metadata = _item(inventory, uid)
        if not _compatible(avatar, kind, metadata, slot):
            raise _Rejected(5)
        if any(owner != (avatar_id, slot) for owner in _owners(avatars, uid)):
            raise _Rejected(4)  # EQUIPMENT_DRESSED
        # StorageModule.OnGetEquipmentDataRsp70850@13ad9bd-13ad9e1
        # defaults to identified when this optional proto field is absent.
        # No random affix or new identification action is synthesized.
        if kind == "stigmata":
            identified = item.get("is_affix_identify", True)
            if type(identified) is not bool:
                raise ValueError("Malformed stigmata identify flag")
            if not identified:
                raise _Rejected(7)  # AFFIX_NOT_IDENTIFY
    if _cost(avatar, inventory, slot, uid) > _max_cost(avatar):
        raise _Rejected(6)  # COST_LACK
    avatar[SLOT_FIELDS[slot]] = uid


def _exchange(account, values):
    first_id = stage._u32(values["avatar_id_1"], "avatar_id_1")
    second_id = stage._u32(values["avatar_id_2"], "avatar_id_2")
    avatars = _avatars(account)
    if first_id == second_id or first_id not in avatars or second_id not in avatars:
        raise _Rejected(2)  # AVATAR_ERROR
    first, second = avatars[first_id], avatars[second_id]
    first_uid = stage._u32(first.get("weapon_unique_id", 0), "weapon_unique_id")
    second_uid = stage._u32(second.get("weapon_unique_id", 0), "weapon_unique_id")
    inventory = _inventory(account)
    if not first_uid or not second_uid or first_uid == second_uid:
        raise _Rejected(2)
    first_kind, _, first_metadata = _item(inventory, first_uid)
    second_kind, _, second_metadata = _item(inventory, second_uid)
    if _owners(avatars, first_uid) != [(first_id, 1)] or \
            _owners(avatars, second_uid) != [(second_id, 1)]:
        raise _Rejected(2)
    if not _compatible(first, second_kind, second_metadata, 1) or \
            not _compatible(second, first_kind, first_metadata, 1):
        raise _Rejected(3)  # WEAPON_TYPE_ERROR
    if _cost(first, inventory, 1, second_uid) > _max_cost(first) or \
            _cost(second, inventory, 1, first_uid) > _max_cost(second):
        raise _Rejected(4)  # COST_LACK
    first["weapon_unique_id"], second["weapon_unique_id"] = second_uid, first_uid


def _power_up_tables():
    """Bind transactions to the exact configuration supplied to the client."""
    tables = {}
    for name, expected in _POWER_UP_TABLE_HASHES.items():
        raw = Path(stage.TABLE_OVERRIDES.get(name, stage.TABLE_DIRECTORY / name)).read_bytes()
        permitted = {expected}
        if name == 'materialdata':
            # Explicit chapter1 dependency3108, all741 accepted rows retained.
            permitted.add('41c93e6af3bd231df41a161ec0caaab1dc1458740facf117abd26f2a45cb7e07')
        if hashlib.sha256(raw).hexdigest() not in permitted:
            raise ValueError("Equipment power-up source changed; audit before use")
        tables[name] = json.loads(raw)
    return tables


def _row(tables, table, identity, field="ID"):
    matches = [row for row in tables[table] if row.get(field) == identity]
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous power-up metadata")
    return matches[0]


def _i32_nonnegative(value, name):
    result = stage._u32(value, name)
    if result > 0x7FFFFFFF:
        raise ValueError(name + " exceeds original native Int32")
    return result


def _f32(value):
    # Original native calculator uses SSE single-precision arithmetic, including
    # the multiplication before division and the final truncation of coin cost.
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _descriptor(value):
    if not isinstance(value, dict) or set(value) - {"type", "id_or_unique_id", "num"}:
        raise ValueError("Malformed original EquipmentItem")
    kind = value["type"]
    if type(kind) is not int or kind not in (MATERIAL, WEAPON, STIGMATA):
        raise ValueError("Unsupported original equipment type")
    identity = _i32_nonnegative(value["id_or_unique_id"], "equipment identity")
    count = _i32_nonnegative(value.get("num", 0), "equipment count")
    if not identity or (kind != MATERIAL and count != 0):
        raise ValueError("Invalid original equipment descriptor")
    return kind, identity, count


def _power_up(account, values):
    if POWER_UP_CONFIG != {"same_type_power_up_rate": 100,
                           "power_up_scoin_cost_rate": 50} or POWER_UP_BOOST_RATE != 100:
        raise ValueError("Power-up reference config changed; audit before use")
    if not isinstance(values, dict) or set(values) != {"main_item", "consume_item_list"}:
        raise ValueError("Malformed original power-up request")
    kind, uid, _ = _descriptor(values["main_item"])
    inventory = _inventory(account)
    expected_kind = {WEAPON: "weapon", STIGMATA: "stigmata"}.get(kind)
    if uid not in inventory or inventory[uid][0] != expected_kind:
        raise _Rejected(2)  # MAIN_ITEM_NOT_EXIST
    _, item, _ = _item(inventory, uid)
    item_id = stage._u32(item["id"], "equipment id")
    if item_id not in _audited_growth_ids():
        raise ValueError("Power-up model is outside the current audited scope")
    tables = _power_up_tables()
    metadata = _row(tables, "weapondata" if kind == WEAPON else "stigmatadata", item_id)
    if not 1 <= metadata['maxLv'] <= len(tables['equipmentleveldata']) or not 0 < metadata['expType'] < 8:
        raise ValueError("Growth indices outside native table")
    thresholds = [_i32_nonnegative(_row(tables, "equipmentleveldata", level, "level")
                  ["Type1"][metadata["expType"]], "equipment EXP threshold")
                  for level in range(1, metadata["maxLv"] + 1)]
    if any(not threshold for threshold in thresholds):
        raise ValueError("Nonpositive equipment EXP threshold")
    level = stage._u32(item["level"], "equipment level")
    exp = _i32_nonnegative(item["exp"], "equipment exp")
    if exp > thresholds[level - 1] or (level < metadata["maxLv"] and
                                       exp == thresholds[level - 1]):
        raise ValueError("Equipment EXP is inconsistent with its level")
    if kind == STIGMATA:
        identified = item.get("is_affix_identify", True)
        if type(identified) is not bool:
            raise ValueError("Malformed stigmata identify flag")
        if not identified:
            raise _Rejected(10)  # MAIN_ITEM_AFFIX_NOT_IDENTIFY
    if level >= metadata["maxLv"]:
        raise _Rejected(3)  # MAIN_ITEM_LEVEL_FULL
    container = values["consume_item_list"]
    if not isinstance(container, dict) or set(container) != {"item_list"} or \
            not isinstance(container["item_list"], list) or not container["item_list"]:
        raise ValueError("No original power-up material selection")
    materials = {}
    for material in account["material_list"]:
        material_id = stage._u32(material["id"], "material id")
        amount = _i32_nonnegative(material["num"], "material amount")
        if not material_id or material_id in materials:
            raise ValueError("Duplicate or empty material identity")
        materials[material_id] = (material, amount)
    avatars = _avatars(account)
    selected = set()
    consumed_materials = []
    total_exp_f32 = _f32(0.0)
    for descriptor in container["item_list"]:
        source_kind, source_id, amount = _descriptor(descriptor)
        identity = (source_kind, source_id)
        if identity in selected:
            raise _Rejected(6)  # CONSUME_ITEM_REPEAT
        selected.add(identity)
        if source_kind != MATERIAL:
            if identity == (kind, uid):
                raise _Rejected(7)  # MAIN_ITEM_IN_CONSUME_ITEM_LIST
            expected = {WEAPON: "weapon", STIGMATA: "stigmata"}[source_kind]
            if source_id not in inventory or inventory[source_id][0] != expected:
                raise _Rejected(4)  # CONSUME_ITEM_NOT_EXIST
            if _owners(avatars, source_id):
                raise _Rejected(5)  # CONSUME_ITEM_IN_USE
            source = inventory[source_id][1]
            protected = source.get("is_protected", False)
            if type(protected) is not bool:
                raise ValueError("Malformed equipment protection flag")
            if protected:
                raise _Rejected(9)  # CONSUME_ITEM_PROTECTED
            # Equipment fodder additionally depends on unlock/new-device/grand
            # key/gacha-ticket rules. These are not inferred from rarity; leave
            # every otherwise legal equipment sacrifice unsupported for now.
            raise ValueError("Equipment fodder is not yet audited")
        if not amount:
            raise ValueError("Empty power-up material count")
        if source_id not in materials or amount > materials[source_id][1]:
            raise _Rejected(4)
        material_rows = [row for row in tables["materialdata"] if row.get("ID") == source_id]
        if len(material_rows) != 1:
            raise ValueError("Power-up material is outside the current audited scope")
        mat_meta = material_rows[0]
        base_exp = mat_meta.get("gearExpProvideBase", 0.0)
        if base_exp <= 0.0 or mat_meta.get("maxLv", 1) != 1 or mat_meta.get("gearExpPorvideAdd", 0.0) != 0.0:
            raise ValueError("Power-up material is outside the current audited scope")
        if amount > mat_meta.get("quantityLimit", 9999):
            raise ValueError("Power-up quantity exceeds the original material limit")
        # GetGearExp52245@ccd821: (base + (level-1)*add)*number.
        item_base = _f32(_f32(base_exp) * _f32(amount))
        # UIUtil.CalCulateExpFromItems82365@143d2d9: apply MaterialExpBonus if present.
        bonus_rows = [row for row in tables["materialexpbonusdata"] if row.get("materialId") == source_id]
        if bonus_rows:
            bonus = bonus_rows[0]["weaponExpBonus" if kind == WEAPON else "stigmataExpBonus"]
            bonus_factor = _f32(_f32(bonus) / _f32(100.0))
            item_exp = _f32(item_base * bonus_factor)
        else:
            item_exp = item_base
        total_exp_f32 = _f32(total_exp_f32 + item_exp)
        consumed_materials.append((source_id, amount))
    gain = math.floor(total_exp_f32)
    _i32_nonnegative(gain, "gained equipment exp")
    if not gain:
        raise ValueError("No positive power-up EXP")
    # GetScoinNeedFromExpGet82367@143d825 truncates rate*EXP/100 before
    # applying the discount percentage. GetConfig supplies no discount schedule,
    # so the original GetDiscountValue68612@11fa7d4 returns100. Cost50 is the
    # previously authorized 7.0 reference coefficient, not a historical claim.
    cost = math.trunc(_f32(_f32(_f32(POWER_UP_CONFIG["power_up_scoin_cost_rate"]) *
                               _f32(gain)) / _f32(100)))
    _i32_nonnegative(cost, "power-up coin cost")
    coins = _i32_nonnegative(account["main"]["scoin"], "account coins")
    if coins < cost:
        raise _Rejected(8)  # SCOIN_LACK
    exp = _i32_nonnegative(exp + gain, "resulting equipment exp")
    while exp >= thresholds[level - 1]:
        if level == metadata["maxLv"]:
            exp = thresholds[level - 1]
            break
        exp -= thresholds[level - 1]
        level += 1
    # All validation is complete. Persist wallet, material, and the same native
    # UID's growth in one shared atomic save. Explicit zero material rows cause
    # original OnGetEquipmentDataRsp70850@13ae6ae to remove exhausted UI entries.
    account["main"]["scoin"] = coins - cost
    consumed_ids = set()
    for source_id, amount in consumed_materials:
        materials[source_id][0]["num"] -= amount
        consumed_ids.add(source_id)
    _MUTATION.power_up_consumed = consumed_ids
    item["level"], item["exp"] = level, exp
    return {"main_item": {"type": kind, "id_or_unique_id": uid},
            "boost_rate": POWER_UP_BOOST_RATE}


def _audited_growth_ids():
    """Use the complete checked evolution closures, not six initial models."""
    path = stage.ROOT / '.local-baseline/server19-dev/equipment-chain-batch-ready-v3/matrix.json'
    expected = '31225e6b70c7703d738a8b69b9368cc4989c881de43578e7bf50588ca242c9aa'
    if FULL_CULTIVATION_READY_FILE is not None and Path(FULL_CULTIVATION_READY_FILE).is_file():
        receipt = json.loads(Path(FULL_CULTIVATION_READY_FILE).read_bytes())
        if receipt.get('build_proof'):
            from server19_build_capabilities import require
            require('equipment', receipt)
        elif receipt.get('schema') != 1 or receipt.get('serial') != 'REFERENCE_DEVICE' or receipt.get('readback_verified') is not True:
            raise ValueError('Full cultivation resource readiness invalid')
        path = stage.ROOT / '.local-baseline/server19-dev/cultivation-full-equipment-ready/matrix.json'
        expected = receipt['matrix_sha256']
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Equipment battle closure changed; audit before growth')
    matrix = json.loads(raw)
    return {row['item_id'] for row in matrix['items'] if not row['blockers']} | set(EXTRA_AUDITED_GROWTH_IDS)


def _evolve(account, values):
    kind, uid, _ = _descriptor(values['main_item'])
    inventory = _inventory(account)
    if uid not in inventory or inventory[uid][0] != {WEAPON: 'weapon', STIGMATA: 'stigmata'}.get(kind):
        raise ValueError('Evolution target not owned')
    _, item, meta = _item(inventory, uid)
    ready = _audited_growth_ids()
    next_id = stage._u32(meta['evoID'], 'evolution target ID')
    if item['id'] not in ready or next_id not in ready or not next_id or item['level'] != meta['maxLv']:
        raise ValueError('Evolution unavailable, unaudited or not at level cap')
    table = 'weapondata' if kind == WEAPON else 'stigmatadata'
    target = _metadata(table, next_id)
    if target['baseType'] != meta['baseType'] or target.get('setID') != meta.get('setID') or target['maxLv'] <= meta['maxLv']:
        raise ValueError('Unsupported evolution branch/category conversion')
    if kind == STIGMATA and item.get('is_affix_identify', True) is not True:
        raise ValueError('Unidentified stigmata cannot evolve')
    required = {}
    for entry in meta['evoMaterial']:
        material, count = map(int, entry.split(':'))
        if material in required or count <= 0:
            raise ValueError('Invalid evolution recipe')
        required[material] = count
    supplied = {}
    for entry in values['consume_item_list']['item_list']:
        entry_kind, material, count = _descriptor(entry)
        if entry_kind != MATERIAL or material in supplied or not count:
            raise ValueError('Only exact nonduplicate recipe materials are supported')
        supplied[material] = count
    if not required or supplied != required:
        raise ValueError('Evolution recipe does not match original preview')
    materials = {}
    for row in account['material_list']:
        if row['id'] in materials:
            raise ValueError('Duplicate material stack')
        materials[row['id']] = row
    for material, count in required.items():
        _metadata('materialdata', material)
        if material not in materials or _i32_nonnegative(materials[material]['num'], 'material count') < count:
            raise ValueError('Insufficient evolution materials')
    # Original52642 and52113 key the current level, not rarity/new level.
    levels = _power_up_tables()
    cost = _i32_nonnegative(_row(levels, 'equipmentleveldata', item['level'], 'level')
                           ['weaponEvoCost' if kind == WEAPON else 'stigmataEvoCost'], 'evolution coins')
    if _i32_nonnegative(account['main']['scoin'], 'coins') < cost:
        raise ValueError('Insufficient evolution coins')
    # Original Storage70850 never refreshes metadata for an existing UID.
    # Create a new native entity, remove the old one and rebind its owners.
    # This is a consumer-based compatibility transaction, not recovered old
    # server code. Existing saves are not rewritten to advance an evolution.
    inventory_name = 'weapon_list' if kind == WEAPON else 'stigmata_list'
    limit = 20000 if kind == WEAPON else 40000
    new_uid = max(row['unique_id'] for row in account[inventory_name]) + 1
    if new_uid >= limit or new_uid in inventory:
        raise ValueError('Native equipment UID space exhausted')
    avatars = _avatars(account)
    owners = _owners(avatars, uid)
    if len(owners) > 1:
        raise ValueError('Evolution target has duplicate equipped owners')
    replacement = deepcopy(item)
    replacement.update(unique_id=new_uid, id=next_id, level=1, exp=0)
    for avatar_id, slot in owners:
        if not _compatible(avatars[avatar_id], inventory_name.removesuffix('_list'), target, slot):
            raise ValueError('Evolution target would be incompatible with its owner')
    # All validation precedes changes to the transactional account copy.
    account['main']['scoin'] -= cost
    consumed_ids = set()
    for material, count in required.items():
        materials[material]['num'] -= count
        consumed_ids.add(material)
    _MUTATION.power_up_consumed = consumed_ids
    index = account[inventory_name].index(item)
    account[inventory_name][index] = replacement
    for avatar_id, slot in owners:
        avatars[avatar_id][SLOT_FIELDS[slot]] = new_uid
    _MUTATION.evolution = {'kind': kind, 'old_uid': uid, 'new_uid': new_uid,
        'old_id': item['id'], 'new_id': next_id, 'owners': owners}
    return {'new_item': {'type': kind, 'id_or_unique_id': new_uid}}


def _protect(account, values):
    protected = values['is_protected']
    if type(protected) is not bool:
        raise ValueError('Protection must be an original Boolean')
    inventory, targets, seen = _inventory(account), [], set()
    for field, kind in [('weapon_unique_id_list','weapon'),('stigmata_unique_id_list','stigmata')]:
        rows = values.get(field, [])
        if not isinstance(rows, list):
            raise ValueError('Invalid protection targets')
        for uid in rows:
            stage._u32(uid, 'protected UID')
            if uid in seen or uid not in inventory or inventory[uid][0] != kind:
                raise ValueError('Duplicate, missing or mismatched protection target')
            seen.add(uid); targets.append(inventory[uid][1])
    if not targets:
        raise ValueError('Empty protection selection')
    for item in targets:
        item['is_protected'] = protected


def _set_dress(account, values):
    if not isinstance(values, dict) or set(values) - {"avatar_id", "dress_id"}:
        raise ValueError("Malformed original set-dress request")
    avatar_id = stage._u32(values.get("avatar_id"), "avatar_id")
    dress_id = stage._u32(values.get("dress_id", 0), "dress_id")
    avatars = _avatars(account)
    if avatar_id not in avatars or not avatars[avatar_id].get("star", 0):
        raise _Rejected(2)  # AVATAR_NOT_EXIST
    _metadata("avatardata", avatar_id, "avatarID")
    avatar = avatars[avatar_id]
    if dress_id in (0, avatar_id):
        avatar["dress_id"] = 0
        return
    try:
        meta = _metadata("dressdata", dress_id, "dressID")
    except ValueError:
        raise _Rejected(3)  # DRESS_NOT_EXIST
    unlocked = avatar.get("dress_list") or []
    if not isinstance(unlocked, list) or dress_id not in unlocked:
        raise _Rejected(3)  # DRESS_NOT_EXIST
    if avatar_id not in meta.get("avatarIDList", []) or meta.get("dressType") != 1:
        raise _Rejected(4)  # DRESS_CAN_NOT_USE
    for other_id, other in avatars.items():
        if other_id != avatar_id and other.get("dress_id") == dress_id:
            other["dress_id"] = 0
    avatar["dress_id"] = dress_id



def _synthesis(account, values):
    """Native fragment recipe: cost is fragment count, not a currency price."""
    if set(values) != {'material', 'equip_item'}:
        raise ValueError('Malformed synthesis request')
    material, target = values['material'], values['equip_item']
    identity = stage._u32(material.get('id'), 'fragment id')
    recipe = _metadata('equipfragdata', identity, 'fragID')
    count = stage._u32(target.get('num'), 'synthesis count')
    item_id = stage._u32(target.get('id_or_unique_id'), 'synthesis equipment id')
    if not count or item_id != recipe['equipment']:
        raise ValueError('Synthesis target does not match fragment recipe')
    kind, meta = stage._item_metadata(item_id)
    equipment_type = {'weapon': WEAPON, 'stigmata': STIGMATA}.get(kind)
    if equipment_type is None or target.get('type') != equipment_type:
        raise ValueError('Synthesis equipment type mismatch')
    cost = stage._u32(recipe['cost'] * count, 'fragment cost')
    if not recipe['cost'] or material.get('num') != cost:
        raise ValueError('Synthesis fragment count mismatch')
    owned = [r for r in account.get('material_list', []) if r['id'] == identity]
    if len(owned) != 1 or owned[0]['num'] < cost:
        raise ValueError('Insufficient synthesis fragments')
    size = len(account.get('weapon_list', [])) + len(account.get('stigmata_list', []))
    if size + count > account['main']['equipment_size_limit']:
        raise ValueError('Equipment storage full')
    # Shared allocator preserves original UID ranges. Transaction rollback
    # covers every grant and deduction if validation or serialization fails.
    stage._grant_drops(account, {(item_id, 1): count})
    owned[0]['num'] -= cost
    _MUTATION.power_up_consumed = {identity}  # include a zero balance snapshot
    # Native result75924 calls GetDummyStorageDataItem: this is a config ID,
    # not the newly allocated inventory UID.
    return {'equip_list': {'item_list': [dict(type=equipment_type,
        id_or_unique_id=item_id, num=count)]}}


def response(request_name, account, request_values=None, *, account_path=None):
    """Persist a native equipment command; return None for other commands."""
    if request_name not in HANDLED_REQUESTS:
        return None
    _REJECTION.detail = None
    _MUTATION.evolution = None
    _MUTATION.power_up_consumed = None
    handler = {"DressEquipmentReq": _dress, "ExchangeAvatarWeaponReq": _exchange,
               "EquipmentPowerUpReq": _power_up, "EquipmentEvoReq": _evolve,
               "EquipSynthesisReq": _synthesis,
               "UpdateEquipmentProtectedStatusReq": _protect,
               "SetDressReq": _set_dress}[request_name]
    response_name = request_name[:-3] + "Rsp"
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        result = {}
        try:
            result = handler(current, request_values or {}) or {}
            if request_name in ("EquipmentPowerUpReq", "EquipmentEvoReq"):
                # Daily task "强化装备" counts either strengthening or evolving.
                import server19_duty
                server19_duty.note_event(current, "enhance_equipment")
            proto.encode_message(response_name, {'retcode': 0, **result})
            for packet in notification_snapshot(current, request_name):
                proto.encode_message(*packet)
            stage._save(path, before, current)
            retcode = 0
        except _Rejected as rejected:
            retcode = rejected.retcode
            _REJECTION.detail = {'command': request_name, 'error': 'NativeRetcode',
                                 'retcode': retcode}
        except (ValueError, TypeError, KeyError, IndexError, OSError, OverflowError) as error:
            retcode = 1
            _REJECTION.detail = {'command': request_name, 'error': type(error).__name__,
                                 'message': str(error)[:500], 'retcode': retcode}
        if retcode == 0:
            stage._sync(account, current)
        else:
            stage._sync(account, before)
    return response_name, {"retcode": retcode, **(result if retcode == 0 else {})}


def rejection_detail(request_name):
    """Server-side diagnostics only; no extra fields enter the original wire."""
    detail = getattr(_REJECTION, 'detail', None)
    return deepcopy(detail) if detail and detail['command'] == request_name else None


def evolution_detail():
    return deepcopy(getattr(_MUTATION, 'evolution', None))


def notification_snapshot(account, request_name=None):
    """Authoritative native snapshots after the successful equipment Rsp."""
    avatars = [{"stigmata_unique_id_1": 0, "stigmata_unique_id_2": 0,
                "stigmata_unique_id_3": 0, **deepcopy(avatar)}
               for avatar in account["avatar_list"]]
    consumed_ids = getattr(_MUTATION, "power_up_consumed", None) or set()
    materials = [deepcopy(m) for m in account.get("material_list", [])
                 if m.get("num", 0) > 0 or m.get("id") in consumed_ids]
    snapshots = [("GetAvatarDataRsp", {"retcode": 0,
                                  "avatar_list": avatars}),
            ("GetEquipmentDataRsp", {"retcode": 0,
                "weapon_list": deepcopy(account.get("weapon_list", [])),
                "stigmata_list": deepcopy(account.get("stigmata_list", [])),
                "material_list": materials})]
    if request_name == 'EquipmentEvoReq':
        change = evolution_detail()
        if not change or change['new_uid'] not in _inventory(account) or change['old_uid'] in _inventory(account):
            raise ValueError('Missing or inconsistent evolution replacement context')
        deleted = {'weapon_unique_id_list': [], 'stigmata_unique_id_list': []}
        deleted['weapon_unique_id_list' if change['kind'] == WEAPON else 'stigmata_unique_id_list'] = [change['old_uid']]
        # New Storage object must exist before avatar references and EvoRsp38.
        snapshots = [('DelEquipmentNotify', deleted), snapshots[1], snapshots[0]]
    if request_name in ("EquipmentPowerUpReq", "EquipmentEvoReq"):
        # Caller sends these BEFORE Rsp32. The original result dialog reads the
        # current storage object immediately upon receipt; Rsp32 does not apply
        # canonical equipment/wallet changes itself.
        import server19_initialization
        snapshots.insert(0, server19_initialization.response("GetMainDataReq", account))
    return snapshots
