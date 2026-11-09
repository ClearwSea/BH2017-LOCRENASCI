"""Native 1.9 subskill transactions across the sourced 25-avatar affiliation table.

Protocol, constraints and formula come from original x86 consumers. Numerical
rows are the deployed 2.4 compatibility data, not recovered 1.9 server economy.
Missing skill levels are native constructor defaults (zero), never free unlocks.
The existing reference recovery interval is retained; a new clock begins at its
first observation, so old saves receive no invented historical recovery.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import time

import server19_protocol as proto
import server19_stage as stage

HANDLED_REQUESTS = frozenset(("AvatarSubSkillLevelUpReq",))
SUPPORTED_AVATARS = {101: tuple(range(11, 17)), 201: tuple(range(51, 57))}
# Current deployed closure audit restores old shield/invisibility/leader gates.
# Backstab613 retains native back-hit damage; only later score802021 is omitted.
# Two live subskills still require unsupported nonempty callbacks/UI metadata.
# 1301/2015 are absent from the current table and remain reserved, not unlocked.
UNSUPPORTED_SUBSKILLS = frozenset((713, 2502, 1301, 2015))
RECOVERY_INTERVAL = 7200  # Already accepted demo GetMainDataRsp reference.
_TABLE_HASHES = {
    "avatardata": "472fce4f109bad435f7fd90ac995e048ff9706f3bde512321d5e4e14cabcf2ce",
    "avatarskilldata": "b461ecfd851450c586d065aac6a38cc659d07a7767c7b1304f4a4c818dcddea3",
    "avatarsubskilldata": "45a03e50b23436eef4b44e3dd8d92eefd42a7fddeaf988dcdf8291e41b48286a",
    "avatarsubskillleveldata": "9342e758bfea38ea294ec7c995e1acb171144c95e1df5a9a57549332f0801b68",
}


class _Rejected(Exception):
    def __init__(self, retcode):
        self.retcode = retcode


def skill_catalog():
    tables = {}
    for name, digest in _TABLE_HASHES.items():
        if hashlib.sha256(Path(stage.TABLE_OVERRIDES.get(name, stage.TABLE_DIRECTORY / name)).read_bytes()).hexdigest() != digest:
            raise ValueError("Unreviewed skill table: " + name)
        tables[name] = stage._table(name)
    skills = {row["skillId"]: row for row in tables["avatarskilldata"]}
    subs = {row["avatarSubSkillId"]: row for row in tables["avatarsubskilldata"]}
    levels = {row["unlockLv"]: row for row in tables["avatarsubskillleveldata"]}
    if any(len(result) != len(tables[name]) for result, name in
           ((skills, "avatarskilldata"), (subs, "avatarsubskilldata"),
            (levels, "avatarsubskillleveldata"))):
        raise ValueError("Duplicate skill table identity")
    scoped = {row['avatarID']: tuple(row['skillList']) for row in tables['avatardata']}
    for avatar_id, expected in scoped.items():
        avatars = [row for row in tables["avatardata"] if row["avatarID"] == avatar_id]
        if len(avatars) != 1 or tuple(avatars[0]["skillList"]) != expected:
            raise ValueError("Changed avatar skill affiliation")
        if any(skill not in skills for skill in expected):
            raise ValueError("Missing skill metadata")
    return skills, subs, levels


def _stored_subskills(avatar, subs):
    """Validate existing lists; sparse old saves stay sparse until real purchase."""
    result = {}
    skills = avatar.get("skill_list", [])
    if not isinstance(skills, list):
        raise ValueError("Malformed stored skills")
    seen = set()
    affiliation = stage._table('avatardata', field='avatarID', identities=(avatar['avatar_id'],))
    if len(affiliation) != 1:
        raise ValueError('Missing or ambiguous actual avatar skill affiliation')
    allowed = set(affiliation[0]['skillList'])
    for skill in skills:
        sid = stage._u32(skill["skill_id"], "skill_id")
        if sid in seen or sid not in allowed:
            raise ValueError("Duplicate or foreign stored skill")
        seen.add(sid)
        rows = skill.get("sub_skill_list", [])
        if not isinstance(rows, list):
            raise ValueError("Malformed stored subskills")
        for row in rows:
            sub_id = stage._u32(row["sub_skill_id"], "sub_skill_id")
            if sub_id in result or sub_id not in subs or subs[sub_id]["skillId"] != sid:
                raise ValueError("Duplicate or foreign stored subskill")
            level = stage._u32(row.get("level", 0), "subskill level")
            if level > subs[sub_id]["maxLv"] or type(row.get("is_mask", False)) is not bool:
                raise ValueError("Malformed stored skill level/mask")
            result[sub_id] = row
    return result


def synchronize_skill_point(account, *, now=None):
    """Pure in-memory recovery; caller must hold shared transaction and persist.

    PlayerDataItem.GetSkillPointFullTime68587 computes
    (limit - 1 - points) * interval + left: each expiration is one point.
    RequestGetSkillPointRecoverLeftTime72975 sends GetMainDataReq type 10.
    """
    now = math.floor(time.time() if now is None else now)
    if now < 0:
        raise ValueError("Invalid recovery observation time")
    main = account["main"]
    points = stage._u32(main.get("skill_point", 0), "skill points")
    limit = stage._u32(main.get("skill_point_limit", 20), "skill point limit")
    if limit != 20:
        raise ValueError("Unreviewed skill point capacity")
    runtime = account.setdefault("skill_point_runtime", {
        "version": 1, "interval": RECOVERY_INTERVAL,
        "next_recover_at": now + RECOVERY_INTERVAL if points < limit else None})
    if not isinstance(runtime, dict) or runtime.get("version") != 1 or \
            runtime.get("interval") != RECOVERY_INTERVAL:
        raise ValueError("Malformed recovery clock")
    due = runtime.get("next_recover_at")
    if due is not None and (type(due) is not int or due < 0):
        raise ValueError("Malformed recovery deadline")
    if points >= limit:
        due = None
    elif due is None:
        due = now + RECOVERY_INTERVAL
    elif now >= due:
        count = (now - due) // RECOVERY_INTERVAL + 1
        points = min(limit, points + count)
        due = None if points >= limit else due + count * RECOVERY_INTERVAL
    runtime["next_recover_at"] = due
    main["skill_point"] = points
    main["skill_point_recover_config_time"] = RECOVERY_INTERVAL
    main["skill_point_recover_left_time"] = 0 if due is None else min(RECOVERY_INTERVAL, max(0, due - now))


def sync_skill_point(account, *, account_path=None, now=None):
    """Persist recovery before GetMainDataReq and return native MainRsp11."""
    import server19_initialization
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        try:
            before = stage._read(path, account)
        except (OSError, ValueError, TypeError, KeyError):
            return "GetMainDataRsp", {"retcode": 1}
        current = stage.copy_account(before)
        try:
            synchronize_skill_point(current, now=now)
            result = server19_initialization.response("GetMainDataReq", current)
            proto.encode_message(*result)
            stage._save(path, before, current)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            stage._sync(account, before)
            return "GetMainDataRsp", {"retcode": 1}
        stage._sync(account, current)
        return result


def material_cost(meta, levels, level):
    """Original 51852/51854: indexed comma-separated ID:count, or unlock list."""
    if level:
        required = meta['unlockLv'] + level * meta['unlockLvAdd']
        index = stage._u32(meta['lvUpItemType'], 'skill material type')
        raw = levels[required]['Item_1'][index]
        pairs = [tuple(map(int, entry.split(':'))) for entry in raw.split(',') if entry]
    else:
        pairs = [(r['itemMetaID'], r['itemNum']) for r in meta['unlockItemList']]
    result = {}
    for identity, amount in pairs:
        identity = stage._u32(identity, 'skill material id')
        amount = stage._u32(amount, 'skill material count')
        if identity and amount:
            result[identity] = stage._u32(result.get(identity, 0) + amount, 'total material cost')
    return result


def _upgrade(account, values, *, now=None):
    skills, subs, levels = skill_catalog()
    avatar_id = stage._u32(values["avatar_id"], "avatar_id")
    skill_id = stage._u32(values["skill_id"], "skill_id")
    sub_id = stage._u32(values["sub_skill_id"], "sub_skill_id")
    owned = [row for row in account["avatar_list"] if row["avatar_id"] == avatar_id]
    if not owned or owned[0].get("star", 0) == 0:
        raise _Rejected(2)
    if len(owned) != 1:
        raise ValueError("Duplicate owned avatar")
    avatar_rows = [row for row in stage._table('avatardata') if row['avatarID'] == avatar_id]
    if len(avatar_rows) != 1:
        raise _Rejected(1)
    if skill_id not in avatar_rows[0]['skillList']:
        raise _Rejected(3)
    if sub_id not in subs or subs[sub_id]["skillId"] != skill_id:
        raise _Rejected(4)
    if sub_id in UNSUPPORTED_SUBSKILLS:
        raise _Rejected(1)
    avatar, meta = owned[0], subs[sub_id]
    stored = _stored_subskills(avatar, subs)
    level = stored.get(sub_id, {}).get("level", 0)
    if level >= meta["maxLv"]:
        raise _Rejected(10)
    required_level = meta["unlockLv"] + level * meta["unlockLvAdd"]
    if stage._u32(avatar["level"], "avatar level") < required_level:
        raise _Rejected(5)
    required_star = (meta["unlockStar"] if not level else next(
        (row["starNeed"] for row in meta["upLevelStarNeedList"] if row["level"] == level + 1), 0))
    if stage._u32(avatar["star"], "avatar star") < required_star:
        raise _Rejected(6)
    if level:
        coin_type = stage._u32(meta["lvUpScoinType"], "skill coin type")
        coin = stage._u32(levels[required_level]["SCoin_1"][coin_type], "skill coin cost")
        points = stage._u32(meta["preLvPoint"], "skill point cost")
    else:
        coin = stage._u32(meta["unlockScoin"], "unlock coin cost")
        points = stage._u32(meta["unlockPoint"], "unlock point cost")
    costs = material_cost(meta, levels, level)
    inventory = {}
    if costs:
        known = {row['ID'] for row in stage._table('materialdata')}
        if not set(costs) <= known:
            raise ValueError('Missing skill material metadata')
        for row in account.get('material_list', []):
            identity = stage._u32(row['id'], 'material id')
            if identity in inventory:
                raise ValueError('Duplicate material inventory')
            stage._u32(row['num'], 'material quantity')
            inventory[identity] = row
    synchronize_skill_point(account, now=now)
    if stage._u32(account["main"]["scoin"], "owned coins") < coin:
        raise _Rejected(7)
    if account["main"]["skill_point"] < points:
        raise _Rejected(8)
    if any(inventory.get(identity, {}).get('num', 0) < amount for identity, amount in costs.items()):
        raise _Rejected(9)
    account["main"]["scoin"] -= coin
    account["main"]["skill_point"] -= points
    for identity, amount in costs.items():
        inventory[identity]['num'] -= amount
    # Spending from full starts a fresh interval; spending below full retains
    # existing fractional progress toward the next recovery.
    synchronize_skill_point(account, now=now)
    if sub_id in stored:
        stored[sub_id]["level"] = level + 1
    else:
        rows = avatar.setdefault("skill_list", [])
        target = next((row for row in rows if row["skill_id"] == skill_id), None)
        if target is None:
            target = {"skill_id": skill_id, "sub_skill_list": []}
            rows.append(target)
        target.setdefault("sub_skill_list", []).append({"sub_skill_id": sub_id,
                                                       "level": 1, "is_mask": False})
    # Daily task "技能升级" counts any sub-skill level-up.
    import server19_duty
    server19_duty.note_event(account, "skill_up")
    return {"retcode": 0}


def notification_snapshot(account):
    """Send BEFORE Rsp51; both native consumers immediately read skill objects."""
    import server19_initialization
    return [server19_initialization.response("GetMainDataReq", account),
            ("GetEquipmentDataRsp", {"retcode": 0,
                                     "weapon_list": deepcopy(account.get("weapon_list", [])),
                                     "stigmata_list": deepcopy(account.get("stigmata_list", [])),
                                     "material_list": deepcopy(account.get("material_list", []))}),
            ("GetAvatarDataRsp", {"retcode": 0,
                                  "avatar_list": deepcopy(account["avatar_list"])})]


def response(request_name, account, request_values=None, *, account_path=None, now=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        try:
            before = stage._read(path, account)
        except (OSError, ValueError, TypeError, KeyError):
            return "AvatarSubSkillLevelUpRsp", {"retcode": 1}
        current = deepcopy(before)
        try:
            result = ("AvatarSubSkillLevelUpRsp", _upgrade(current, request_values or {}, now=now))
            proto.encode_message(*result)
            for packet in notification_snapshot(current):
                proto.encode_message(*packet)
        except _Rejected as rejected:
            result = "AvatarSubSkillLevelUpRsp", {"retcode": rejected.retcode}
        except (ValueError, TypeError, KeyError, IndexError):
            result = "AvatarSubSkillLevelUpRsp", {"retcode": 1}
        if result[1]["retcode"] == 0:
            try:
                stage._save(path, before, current)
            except OSError:
                stage._sync(account, before)
                return "AvatarSubSkillLevelUpRsp", {"retcode": 1}
            stage._sync(account, current)
        else:
            stage._sync(account, before)
        return result
