"""Bounded avatar-card progression used by the real story mission claim.

The deployed compatibility metadata links mission 10005's card 60201 to
Avatar 201, unlockStar 1 and initialWeapon 20041. This is not a StageEnd
award: the caller must commit it with a successful GetMissionRewardReq.
The native equipment consumer requires an actual inventory UID. This bounded
compatibility policy binds an existing, unoccupied initial weapon (already a
real 1-1 first-clear drop); it creates no extra weapon. Historical card default
weapon issuance, duplicate-card conversion and fragment-star-up are unaudited.
"""
from copy import deepcopy

import server19_stage as stage

STORY_AVATAR_ID = 201
STORY_CARD_ID = 60201
STORY_WEAPON_ID = 20041


def _one(table, field, identity):
    rows = [row for row in stage._table(table) if row.get(field) == identity]
    if len(rows) != 1:
        raise ValueError("Missing or ambiguous story avatar metadata")
    return rows[0]


def story_card_plan(account, item_id=STORY_CARD_ID):
    """Validate this single new-avatar grant without changing the account."""
    if type(item_id) is not int or item_id != STORY_CARD_ID:
        raise ValueError("Avatar card is outside the audited story reward")
    metadata = _one("avatardata", "avatarID", STORY_AVATAR_ID)
    expected = {"classID": 2, "roleID": 2, "avatarRegistryKey": "Mei_C2_CK",
                "unlockStar": 1, "initialWeapon": STORY_WEAPON_ID,
                "avatarCardID": STORY_CARD_ID, "avatarFragmentID": 10201,
                "weaponBaseTypeList": [2], "skillList": [51, 52, 53, 54, 55, 56],
                "baseAvatarID": 0}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Story avatar metadata changed; audit before granting")
    card = _one("avatarcarddata", "ID", item_id)
    if card.get("ItemType") != "29998" or card.get("BaseType") != 2:
        raise ValueError("Story avatar-card storage type changed")
    weapon = _one("weapondata", "ID", metadata["initialWeapon"])
    if weapon.get("baseType") != 2 or weapon.get("weaponType") != "katana" or \
            weapon.get("maxLv") != 5 or weapon.get("rarity") != 1:
        raise ValueError("Story avatar's initial weapon changed")
    if _one("avatarleveldata", "level", 1).get("cost") < weapon.get("cost", 0):
        raise ValueError("Initial weapon exceeds the native level-one cost")
    avatars = account.get("avatar_list", [])
    if not isinstance(avatars, list) or any(not isinstance(row, dict) for row in avatars):
        raise ValueError("Malformed owned avatar list")
    ids = [stage._u32(row["avatar_id"], "stored avatar ID") for row in avatars]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Duplicate or empty owned avatar identity")
    existing = next((row for row in avatars if row["avatar_id"] == STORY_AVATAR_ID), None)
    if existing is not None:
        # An explicit locked packet may carry legitimately collected fragments.
        # Preserve those values, but do not guess how an owned card duplicates
        # or how a noncanonical locked avatar should be repaired.
        if stage._u32(existing.get("star", 0), "stored avatar star") != 0:
            raise ValueError("Duplicate avatar-card conversion is not audited")
        if existing.get("level", 1) != 1 or existing.get("exp", 0) != 0 or any(
                existing.get(key, 0) for key in ("weapon_unique_id",
                    "stigmata_unique_id_1", "stigmata_unique_id_2", "stigmata_unique_id_3")):
            raise ValueError("Noncanonical locked story avatar state")
        for key in ("fragment", "touch_goodfeel", "today_has_add_goodfeel", "stage_goodfeel"):
            stage._u32(existing.get(key, 0), "stored avatar " + key)
    weapons = account.get("weapon_list", [])
    if not isinstance(weapons, list) or any(not isinstance(row, dict) for row in weapons):
        raise ValueError("Malformed stored weapon list")
    all_uids = [stage._u32(row["unique_id"], "stored equipment UID")
                for key in ("weapon_list", "stigmata_list") for row in account.get(key, [])]
    if len(all_uids) != len(set(all_uids)):
        raise ValueError("Duplicate stored equipment UID")
    occupied = {row.get("weapon_unique_id", 0) for row in avatars}
    candidates = []
    for item in weapons:
        uid = stage._u32(item["unique_id"], "stored weapon UID")
        if not 0 < uid < 20000:
            raise ValueError("Stored weapon UID is outside its original range")
        if item.get("id") == metadata["initialWeapon"] and uid not in occupied:
            level = stage._u32(item["level"], "stored initial weapon level")
            if not 1 <= level <= weapon["maxLv"]:
                raise ValueError("Stored initial weapon level is invalid")
            stage._u32(item.get("exp", 0), "stored initial weapon EXP")
            candidates.append(uid)
    if not candidates:
        raise ValueError("Story avatar requires an existing unoccupied initial weapon")
    return {"avatar_id": STORY_AVATAR_ID, "star": metadata["unlockStar"],
            "weapon_id": metadata["initialWeapon"], "weapon_unique_id": min(candidates)}


def grant_story_avatar_card(account, item_id=STORY_CARD_ID):
    """Apply the card to a caller-owned transaction copy; no I/O or locks.

    Preserve the actual inventory weapon, including its level and EXP. The
    original AvatarDataItem constructor builds the metadata skill list;
    leaving skill_list absent grants no invented subskill levels. The original
    AvatarModule uses star>0 to mark ownership and emit its unlock notification.
    """
    plan = story_card_plan(account, item_id)
    avatars = account.setdefault("avatar_list", [])
    existing = next((row for row in avatars if row["avatar_id"] == plan["avatar_id"]), None)
    avatar = deepcopy(existing) if existing is not None else {}
    avatar.update(avatar_id=plan["avatar_id"], star=plan["star"], level=1, exp=0,
                  weapon_unique_id=plan["weapon_unique_id"], stigmata_unique_id_1=0,
                  stigmata_unique_id_2=0, stigmata_unique_id_3=0)
    for key in ("fragment", "touch_goodfeel", "today_has_add_goodfeel", "stage_goodfeel"):
        avatar.setdefault(key, 0)
    if existing is None:
        avatars.append(avatar)
    else:
        existing.clear()
        existing.update(avatar)
    return plan["avatar_id"]
