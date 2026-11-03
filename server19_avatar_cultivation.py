"""Original Req35 EXP-material growth and Req29 regular-rank promotion.

Original 1.9 wire, UI arithmetic and level cap; the deployed compatibility
tables supply numeric EXP values. This does not grant materials, coins, skills
or ownership. Positive EXP rows use original attribute-bonus consumers; regular
promotion uses stored fragments. Awakening/shared-fragment promotion stays closed.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct

import server19_protocol as proto
import server19_stage as stage

HANDLED_REQUESTS = frozenset(("AddAvatarExpByMaterialReq", "AvatarStarUpReq"))
SUPPORTED_AVATARS = frozenset((101, 201))
SUPPORTED_MATERIALS = frozenset((1001,))
FUKA_FRAGMENT_UNLOCK_ENABLED = False  # Opt in only with the matching resource overlay.
_TABLE_HASHES = {
    "materialdata": "c020cadada3bbe99eae313be315a704224d6ecea166c9816d047cce6d2250da0",
    "materialavatarexpbonusdata": "65aab801e1a6bf9ddef6085af5f43c29a1c9432a90e961b6469e005ae7699166",
    "avatardata": "472fce4f109bad435f7fd90ac995e048ff9706f3bde512321d5e4e14cabcf2ce",
    "avatarleveldata": "ecbd77af70cfaaa074bc08a7531898f59868b5ce398ba1d9a907f3b5d05fdc63",
    "playerleveldata": "c908e465b869bd64c13e798e0c5a3951fd2534debba97bf8262ab862549eeeeb",
    "avatarstardata": "bcd27e0bcbe1f2ffd616cf9025074a2481958e4306ccfba3c43c6a4aa4405ceb",
}


class _Rejected(Exception):
    def __init__(self, retcode):
        self.retcode = retcode


def _tables():
    result = {}
    for name, digest in _TABLE_HASHES.items():
        raw = Path(stage.TABLE_OVERRIDES.get(name, stage.TABLE_DIRECTORY / name)).read_bytes()
        permitted = {digest}
        if name == 'materialdata':
            permitted.add('41c93e6af3bd231df41a161ec0caaab1dc1458740facf117abd26f2a45cb7e07')
            permitted.add('c8527ce7777d7deb690972c3cbfb2e33a21e61d610fa175b78a544b80074300f')
        if hashlib.sha256(raw).hexdigest() not in permitted:
            raise ValueError("Avatar cultivation table changed: " + name)
        rows = json.loads(raw)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Malformed avatar cultivation table")
        result[name] = rows
    return result


def _one(rows, key, identity):
    found = [row for row in rows if row.get(key) == identity]
    if len(found) != 1:
        raise ValueError("Missing or ambiguous avatar cultivation row")
    return found[0]


def _i32(value, name):
    stage._u32(value, name)
    if value > 0x7fffffff:
        raise ValueError(name + " exceeds the original signed native range")
    return value


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _grow(account, values):
    avatar_id = stage._u32(values.get("avatar_id"), "avatar_id")
    material_id = stage._u32(values.get("material_id"), "material_id")
    amount = _i32(values.get("material_num"), "material_num")
    if not amount:
        raise ValueError("Empty material request")
    avatars = account["avatar_list"]
    if not isinstance(avatars, list):
        raise ValueError("Malformed avatar list")
    avatar = [row for row in avatars if row.get("avatar_id") == avatar_id]
    if not avatar or (len(avatar) == 1 and not avatar[0].get("star", 0)):
        raise _Rejected(2)  # AVATAR_NOT_EXIST
    if len(avatar) != 1:
        raise ValueError("Avatar outside the audited cultivation scope")
    avatar = avatar[0]
    tables = _tables()
    rows = tables["avatarleveldata"]
    if [row["level"] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("Original level-indexed list is not contiguous")
    thresholds = [_i32(row["exp"], "level EXP") for row in rows]
    if not thresholds or not all(thresholds):
        raise ValueError("Invalid avatar EXP threshold")
    captain = _i32(account["main"]["level"], "captain level")
    limit = min(_i32(_one(tables["playerleveldata"], "level", captain)["avatarLevelLimit"],
                     "avatar level cap"), len(rows))
    level = _i32(avatar["level"], "avatar level")
    exp = _i32(avatar.get("exp", 0), "avatar EXP")
    if not 1 <= level <= limit or exp > thresholds[level - 1] or \
            (level < limit and exp == thresholds[level - 1]):
        raise ValueError("Unnormalized avatar level/EXP")
    if level == limit and exp == thresholds[level - 1]:
        raise _Rejected(3)  # AVATAR_LEVEL_FULL: original UI fills the capped bar.
    metadata = _one(tables["materialdata"], "ID", material_id)
    # Preserve original GetBonus76172 -> UpdateInfo76171 float32 order.
    base_exp = _f32(metadata["characterExpProvide"])
    if not base_exp > 0:
        raise _Rejected(5)
    avatar_meta = _one(tables["avatardata"], "avatarID", avatar_id)
    bonuses = [row for row in tables["materialavatarexpbonusdata"] if row["materialId"] == material_id]
    if len(bonuses) > 1:
        raise ValueError("Duplicate attribute EXP bonus")
    # Original76172: attribute1 -> +0xc, 2 -> +0x10, 3 -> +0x14,
    # absent/other attribute ->100%; original76171 multiplies bonus*base*num.
    bonus_field = {1: "biologyExpBonus", 2: "psychoExpBonus", 3: "mechanicExpBonus"}.get(avatar_meta["attribute"])
    bonus = _f32(_f32(bonuses[0][bonus_field]) / _f32(100.0)) if bonuses and bonus_field else _f32(1.0)
    materials = account["material_list"]
    if not isinstance(materials, list):
        raise ValueError("Malformed material list")
    material = [row for row in materials if row.get("id") == material_id]
    if not material:
        raise _Rejected(4)
    if len(material) != 1:
        raise ValueError("Duplicate material stack")
    material = material[0]
    count = _i32(material["num"], "stored material count")
    if count > metadata["quantityLimit"] or amount > metadata["quantityLimit"]:
        raise ValueError("Material quantity exceeds the audited limit")
    if amount > count:
        raise _Rejected(4)  # MATERAIL_NOT_ENOUGH
    gain = _i32(int(_f32(_f32(bonus * base_exp) * _f32(amount))), "gained EXP")
    exp = _i32(exp + gain, "resulting EXP")
    while level < limit and exp >= thresholds[level - 1]:
        exp -= thresholds[level - 1]
        level += 1
    # Matches the native cap/full-bar preview. Overflow is discarded by this
    # explicit local compatibility policy; no unverified coin conversion.
    exp = min(exp, thresholds[level - 1]) if level == limit else exp
    avatar.update(level=level, exp=exp)
    material["num"] = count - amount  # Explicit zero tells Storage to delete it.


def notification_snapshot(account, avatar_id=None):
    """Send these BEFORE Rsp36: native level-up dialog reads the updated avatar.

    Avatar25 precedes Equipment27, which can close an exhausted material
    dialog. Rsp36 refreshes local skill status and closes the material dialog;
    it carries no canonical growth or inventory fields itself.
    """
    avatars = deepcopy(account["avatar_list"])
    if avatar_id is not None:
        # Original AvatarDetailPageContext77756 reads avatar_list[0] only for
        # its saved before-level-up avatar and native voice/dialog trigger.
        # Keep every avatar, put the actual mutation first (ARM14cfea8/14cfeac).
        avatars.sort(key=lambda row: row['avatar_id'] != avatar_id)
    packets = [("GetAvatarDataRsp", {"retcode": 0, "avatar_list": avatars}),
               ("GetEquipmentDataRsp", {"retcode": 0, **{key: deepcopy(account[key])
                for key in ("weapon_list", "stigmata_list", "material_list")}})]
    if FUKA_FRAGMENT_UNLOCK_ENABLED and avatar_id == 601:
        # The native avatar update resolves a newly created weapon UID through
        # Storage. Publish that equipment first for the601 unlock flow.
        packets.reverse()
    return packets


def _promote(account, values):
    identity = stage._u32(values['avatar_id'], 'avatar ID')
    owned = [row for row in account['avatar_list'] if row['avatar_id'] == identity]
    if FUKA_FRAGMENT_UNLOCK_ENABLED and identity == 601 and len(owned) == 1 and owned[0].get('star') == 0:
        tables = _tables()
        meta = _one(tables['avatardata'], 'avatarID', identity)
        if meta['baseAvatarID'] or meta['unlockStar'] != 2 or meta['initialWeapon'] != 20611:
            raise ValueError('Changed601 unlock metadata')
        # Original CalculateUnlockNeedFragment51683 sums rank0..unlockStar-1.
        rows = [row for row in tables['avatarstardata'] if row['avatarID'] == identity]
        need = sum(_i32(_one(rows, 'star', rank)['upgradeFragment'], 'unlock fragments')
                   for rank in range(meta['unlockStar']))
        fragments = _i32(owned[0].get('fragment', 0), 'stored fragments')
        if need != 30 or fragments < need:
            raise ValueError('Insufficient601 unlock fragments')
        import server19_gacha
        server19_gacha._grant_card(account, meta['avatarCardID'])
        owned[0]['fragment'] = fragments - need
        return
    if len(owned) != 1 or not owned[0].get('star'):
        raise ValueError('Promotion requires one owned, unlocked avatar')
    tables = _tables()
    meta = _one(tables['avatardata'], 'avatarID', identity)
    if meta['baseAvatarID']:
        raise ValueError('Awakening/shared-fragment promotion requires separate audit')
    avatar = owned[0]
    rank = stage._u32(avatar['star'], 'rank')
    rows = [row for row in tables['avatarstardata'] if row['avatarID'] == identity]
    current = _one(rows, 'star', rank)
    _one(rows, 'star', rank + 1)
    need = _i32(current['upgradeFragment'], 'promotion fragments')
    fragments = _i32(avatar.get('fragment', 0), 'stored fragments')
    if not need or fragments < need:
        raise ValueError('Promotion capped or insufficient fragments')
    # Original51610 compares avatar.fragment against51637.MaxFragment;
    # existing native regular-rank flow has no coin or material-stack cost.
    avatar.update(star=rank + 1, fragment=fragments - need)


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    response_name = request_name[:-3] + 'Rsp'
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            (_promote if request_name == 'AvatarStarUpReq' else _grow)(current, request_values or {})
            result = response_name, {"retcode": 0}
            proto.encode_message(*result)
            for packet in notification_snapshot(current):
                proto.encode_message(*packet)
            stage._save(path, before, current)
        except _Rejected as error:
            result = response_name, {"retcode": error.retcode}
        except (ValueError, TypeError, KeyError, IndexError, OSError, OverflowError):
            result = response_name, {"retcode": 1}
        stage._sync(account, current if result[1]["retcode"] == 0 else before)
        return result
