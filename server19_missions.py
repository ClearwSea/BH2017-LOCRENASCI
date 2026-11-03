"""Thirty audited linear story missions using the original 1.9 protocol.

IDs 10001..10030 and their linear/reward rows come from the already deployed
filtered 2.4 compatibility tables, not recovered official 1.9 economy. Their
finishWay=180 is absent from the original enum (SPECIFIC_STAGE_ID=5). This
explicit server evaluator uses only resource-ready catalog stages' saved
WIN settlements, without rewriting client tables or completing other tasks.
Manual claims persist rewards and receipts atomically through the stage lock.
"""
from copy import deepcopy
from pathlib import Path
import time

import server19_stage as stage
import server19_progression as progression
import server19_protocol as proto
import server19_player_progression as player_progression
import server19_duty as duty
import server19_achievement as achievement

BASE_MISSION_IDS = tuple(range(10001, 10031))
SUPPORTED_MISSION_IDS = BASE_MISSION_IDS
EXTENDED_CATALOG = {}
# 10031 has no linear-mission row. 10032 onwards target Chapter2, not
# character-story stages10132..10136. Do not invent a prerequisite or grant.
NEW_MISSION_IDS = tuple(range(10011, 10031))
NEW_MISSION_SOURCE_SHA256 = "d00d0b7197aa65a92282513a7dc3c2b0134bf6dabc20819a0886823583d584b9"
HANDLED_REQUESTS = frozenset(("GetMissionDataReq", "GetMissionRewardReq",
                              "GetHasGotItemIdListReq")) | duty.HANDLED_REQUESTS
SOURCE_POLICY = "deployed24_scoped_story_manual_claim"
MISSION_DOING = 2
MISSION_FINISH = 3
MISSION_CLOSE = 5

# Guidance tasks the client's own unlock table waits for. Scanning every call
# site of UnlockUIDataReaderExtend::UnLockByMission in the 1.9 ELF shows the
# only ids ever requested are 1/2/3/6, i.e. missions 10007, 11001 and 13004.
# 10007 and 11001 come from the published story chain; 13004 does not, and
# SupplyEntrancePageContext::SetupGacha 78670 renders the 补给 card only when
# UnLockByMission(6) succeeds. That call returns 1 for any known status of
# mission 13004 (unlockuidata row 6 has OnDoing/OnFinish/OnClose all set), and
# 0 when MissionModule has never heard of it -- which is why the 补给 entry was
# missing. 13004 is the original row "标配补给 完成1次标配补给", finishWay 14,
# LinkType 7 (前往补给).
GUIDANCE_MISSION_IDS = (13004,)
GUIDANCE_EVENTS = {13004: "supply"}
_CURRENCIES = {"exp": "RewardExp", "scoin": "RewardSCoin", "hcoin": "RewardHCoin",
               "stamina": "RewardStamina", "skill_point": "RewardSkillPoint",
               "friends_point": "RewardFriendPoint", "duty_point": "RewardDutyPoint"}
_REWARD_VECTORS = {
    10001: (12, 0, 0, 0, [(30004, 1, 1)]),
    10002: (12, 0, 0, 0, [(3000, 0, 2)]),
    10003: (12, 0, 0, 0, [(4005, 0, 1)]),
    10004: (18, 550, 0, 0, []),
    10005: (0, 0, 0, 6, [(60201, 0, 1)]),
    10006: (18, 610, 0, 0, []),
    10007: (12, 610, 0, 0, []),
    10008: (12, 640, 0, 0, []),
    10009: (12, 640, 0, 0, []),
    10010: (12, 640, 0, 0, []),
    10011: (12, 660, 0, 0, []),
    10012: (12, 660, 0, 0, []),
    10013: (12, 690, 0, 0, []),
    10014: (12, 690, 0, 0, []),
    10015: (12, 690, 0, 0, []),
    10016: (12, 720, 0, 0, []),
    10017: (12, 720, 0, 0, []),
    10018: (12, 720, 0, 0, []),
    10019: (12, 750, 0, 0, []),
    10020: (12, 750, 0, 0, []),
    10021: (12, 770, 0, 0, []),
    10022: (12, 770, 0, 0, []),
    10023: (12, 770, 0, 0, []),
    10024: (12, 800, 0, 0, []),
    10025: (12, 800, 0, 0, []),
    10026: (12, 830, 0, 0, []),
    10027: (12, 830, 0, 0, []),
    10028: (12, 830, 0, 0, []),
    10029: (12, 860, 0, 0, []),
    10030: (12, 860, 0, 0, []),
}


class _Rejected(Exception):
    def __init__(self, retcode):
        self.retcode = retcode


def _one(rows, field, identity):
    selected = [row for row in rows if row.get(field) == identity]
    if len(selected) != 1:
        raise ValueError("Missing or ambiguous supported story mission row")
    return selected[0]


def mission_catalog():
    """Audit the exact bounded condition, prerequisite and reward inputs."""
    missions = stage._table("missiondata", field="id", identities=BASE_MISSION_IDS)
    linear = stage._table("linearmissiondata", field="MissionID", identities=BASE_MISSION_IDS)
    rewards = stage._table("rewarddata", field="RewardID", identities=BASE_MISSION_IDS)
    # Whole-row source binding includes descriptions/links/linear conditions,
    # while reward vectors below preserve every already saved receipt.
    import hashlib, json
    new_source = {"missions": [row for row in missions if row.get("id") in NEW_MISSION_IDS],
        "linear": [row for row in linear if row.get("MissionID") in NEW_MISSION_IDS],
        "rewards": [row for row in rewards if row.get("RewardID") in NEW_MISSION_IDS]}
    digest = hashlib.sha256(json.dumps(new_source, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")).hexdigest()
    if digest != NEW_MISSION_SOURCE_SHA256:
        raise ValueError("Reviewed Chapter1 mission batch changed; audit before use")
    catalog = {}
    for mission_id in BASE_MISSION_IDS:
        stage_id = mission_id + 100
        row = _one(missions, "id", mission_id)
        expected = {"type": 1, "subType": 0, "finishWay": 180,
                    "finishParaInt": stage_id, "finishParaStr": "", "totalProgress": 1,
                    "rewardId": mission_id, "isAutoReward": False,
                    "LinkType": 1, "LinkParam": stage_id, "LinkParams": [stage_id],
                    "PreviewTime": -1, "NoDisplay": 0, "IsNeedDisplay": 1}
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError("Story mission condition changed; audit before use")
        predecessor = 0 if mission_id == BASE_MISSION_IDS[0] else mission_id - 1
        if _one(linear, "MissionID", mission_id) != {
                "MissionID": mission_id, "PreMissionId": predecessor,
                "MinLevel": 1, "IsAchievement": 0}:
            raise ValueError("Story mission prerequisite changed; audit before use")
        reward_row = _one(rewards, "RewardID", mission_id)
        reward = {name: stage._u32(reward_row[key], key) for name, key in _CURRENCIES.items()}
        items = []
        for index in range(1, 6):
            values = tuple(stage._u32(reward_row[f"RewardItem{index}{field}"], "reward item")
                           for field in ("ID", "Level", "Num"))
            if values[0]:
                if not values[2]:
                    raise ValueError("Empty configured mission item reward")
                items.append(values)
            elif values != (0, 0, 0):
                raise ValueError("Malformed empty configured mission reward slot")
        exp, scoin, hcoin, stamina, expected_items = _REWARD_VECTORS[mission_id]
        expected_reward = {"exp": exp, "scoin": scoin, "hcoin": hcoin, "stamina": stamina,
                           "skill_point": 0, "friends_point": 0, "duty_point": 0}
        if reward != expected_reward or items != expected_items:
            raise ValueError("Story mission reward changed; audit before granting")
        reward["item_list"] = [dict(zip(("id", "level", "num"), values)) for values in items]
        catalog[mission_id] = {"mission_id": mission_id, "stage_id": stage_id,
                               "predecessor": predecessor, "reward": reward}
    catalog.update(deepcopy(EXTENDED_CATALOG))
    return catalog


def _mission_rows(account):
    data = account.get("mission_data", {})
    if not isinstance(data, dict):
        raise ValueError("Malformed stored mission data")
    rows = data.get("mission_list", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Malformed stored mission list")
    ids = [stage._u32(row["mission_id"], "stored mission ID") for row in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Duplicate or empty stored mission identity")
    return rows


def _runtime(account, catalog):
    runtime = account.get("mission_runtime")
    if runtime is None:
        # Explicit previously closed story tasks must not become claimable
        # again. No response/reward receipt is invented for imported history.
        closed = sorted(row["mission_id"] for row in _mission_rows(account)
                        if row["mission_id"] in SUPPORTED_MISSION_IDS and
                        row.get("status") == MISSION_CLOSE)
        runtime = {"schema": 1, "source_policy": SOURCE_POLICY,
                   "claimed_ids": closed, "receipts": []}
        account["mission_runtime"] = runtime
    if not isinstance(runtime, dict) or runtime.get("schema") != 1 or \
            runtime.get("source_policy") != SOURCE_POLICY:
        raise ValueError("Unsupported story mission receipt schema")
    claimed = runtime.get("claimed_ids")
    if not isinstance(claimed, list) or any(type(value) is not int or value not in catalog for value in claimed) or len(set(claimed)) != len(claimed):
        raise ValueError("Invalid story mission claim identities")
    base_claimed = [identity for identity in claimed if identity in BASE_MISSION_IDS]
    if base_claimed != list(BASE_MISSION_IDS[:len(base_claimed)]):
        raise ValueError("Original story claims must retain their linear prefix")
    for index, identity in enumerate(claimed):
        predecessor = catalog[identity]["predecessor"]
        if predecessor and predecessor not in claimed[:index]:
            raise ValueError("Claimed story prerequisite is missing")
    receipts = runtime.get("receipts")
    if not isinstance(receipts, list) or any(not isinstance(row, dict) for row in receipts):
        raise ValueError("Malformed story mission receipts")
    ids = []
    for receipt in receipts:
        identity = receipt.get("mission_id")
        if type(identity) is not int or identity not in claimed or identity in ids or \
                receipt.get("stage_id") != catalog[identity]["stage_id"] or \
                receipt.get("response") != {"retcode": 0,
                    "reward_list": [catalog[identity]["reward"]]}:
            raise ValueError("Invalid persisted story reward receipt")
        ids.append(identity)
    return runtime


def _confirmed_wins(account):
    """Require actual successful local settlements as well as saved Stage state."""
    levels = account.get("stage_list", [])
    if not isinstance(levels, list) or any(not isinstance(row, dict) for row in levels):
        raise ValueError("Malformed saved stage list")
    supported = frozenset(stage.supported_stage_ids())
    selected = [row for row in levels if row.get("id") in supported]
    ids = [row["id"] for row in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate supported stage record")
    runtime = account.get("stage_runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("Malformed stage settlement state")
    receipts = runtime.get("settlements", [])
    if not isinstance(receipts, list) or any(not isinstance(row, dict) for row in receipts):
        raise ValueError("Malformed stage settlement receipts")
    won = set()
    for row in receipts:
        result = row.get("response", {})
        if not isinstance(result, dict):
            raise ValueError("Malformed saved stage settlement response")
        if type(row.get("end_status")) is int and row["end_status"] == stage.STAGE_WIN and \
                type(result.get("retcode")) is int and result["retcode"] == 0 and \
                type(result.get("progress")) is int and result["progress"] == 1:
            stage_id = row.get("stage_id")
            if type(stage_id) is int and stage_id in supported:
                won.add(stage_id)
    return {row["id"] for row in selected if row.get("is_done") is True and
            type(row.get("progress")) is int and row["progress"] == 1 and row["id"] in won}


def _guidance_runtime(account):
    runtime = account.setdefault("guidance_runtime", {"schema": 1, "done": []})
    done = runtime.get("done")
    if runtime.get("schema") != 1 or not isinstance(done, list) or \
            any(type(value) is not int or value not in GUIDANCE_MISSION_IDS for value in done) or \
            len(done) != len(set(done)):
        raise ValueError("Unsupported guidance task state")
    return runtime


def _guidance_rows(account):
    """Publish the guidance tasks the client's unlock table waits for.

    Their reward rows are not claimed here: the original gate only needs the
    mission to exist, and its own row is IsNeedDisplay 0.
    """
    done = set(_guidance_runtime(account)["done"])
    rows = []
    for mission_id in GUIDANCE_MISSION_IDS:
        finished = mission_id in done
        rows.append({"mission_id": mission_id,
                     "status": MISSION_FINISH if finished else MISSION_DOING,
                     "progress": 1 if finished else 0})
    return rows


def note_event(account, kind):
    """Mark the guidance tasks driven by `kind` as finished."""
    runtime = _guidance_runtime(account)
    for mission_id, event in GUIDANCE_EVENTS.items():
        if event == kind and mission_id not in runtime["done"]:
            runtime["done"].append(mission_id)
            runtime["done"].sort()


def synchronize(account):
    """Derive only mission state on the caller's transaction copy; no I/O/locks.

    Completion is retrospective for these audited compatibility rows. Claiming the
    predecessor exposes the next mission; already won stages then finish it
    immediately. This does not modify Stage progress, first drops or any asset.
    """
    catalog = mission_catalog()
    rows = _mission_rows(account)
    runtime = _runtime(account, catalog)
    claimed = set(runtime["claimed_ids"])
    won = _confirmed_wins(account)
    active = []
    if stage._u32(account["main"]["level"], "stored player level") >= 1:
        for mission_id, config in catalog.items():
            if (mission_id not in claimed and account["main"]["level"] >= config.get("min_level", 1)
                    and (not config["predecessor"] or config["predecessor"] in claimed)):
                done = config["stage_id"] in won
                active.append({"mission_id": mission_id,
                               "status": MISSION_FINISH if done else MISSION_DOING,
                               "progress": 1 if done else 0})
        active.extend(_guidance_rows(account))
    data = account.setdefault("mission_data", {})
    data["mission_list"] = [deepcopy(row) for row in rows
                            if row["mission_id"] not in SUPPORTED_MISSION_IDS
                            and row["mission_id"] not in GUIDANCE_MISSION_IDS] + active
    return account


def mission_snapshot(account):
    """Retain unrelated state and explicitly close every already claimed task.

    Original OnGetMissionDataRsp70036 merges rows into its mission dictionary;
    is_all only replaces duty lists. Omitting claimed rows leaves old FINISH
    buttons in memory. FilterOneMissionByType80562 excludes explicit CLOSE5.
    """
    result = {"mission_list": [], "daily_duty_point": 0,
              "has_take_daily_duty_id_list": [], "weekly_duty_point": 0,
              "has_take_weekly_duty_id_list": [], "is_in_activity": False,
              **deepcopy(account.get("mission_data", {}))}
    runtime = account.get("mission_runtime", {})
    receipted = {row["mission_id"] for row in runtime.get("receipts", [])}
    closed = [{"mission_id": identity, "status": MISSION_CLOSE,
               **({"progress": 1} if identity in receipted else {})}
              for identity in runtime.get("claimed_ids", [])]
    import server19_extra_achievements as extra_achievements
    result["mission_list"] = (closed + duty.mission_rows(account)
                              + extra_achievements.mission_rows(account)
                              + achievement.achievement_rows(account)
                              + result["mission_list"])
    result.update(duty.snapshot(account))
    result.update(retcode=0, is_all=True)
    return "GetMissionDataRsp", result


def _preflight(account, reward):
    equipment_count = 0
    material_ids = [row["id"] for row in account.get("material_list", [])]
    if len(material_ids) != len(set(material_ids)):
        raise ValueError("Duplicate stored material identity")
    for item in reward["item_list"]:
        if item["id"] == progression.STORY_CARD_ID:
            if item["num"] != 1 or item["level"] != 0:
                raise ValueError("Unsupported avatar-card quantity or level")
            progression.story_card_plan(account, item["id"])
            continue
        kind, metadata = stage._item_metadata(item["id"])
        if kind in ("weapon", "stigmata"):
            equipment_count += item["num"]
        else:
            old = next((row.get("num", 0) for row in account.get("material_list", [])
                        if row["id"] == item["id"]), 0)
            if stage._u32(old + item["num"], "stored reward material num") > metadata["quantityLimit"]:
                raise _Rejected(5)  # EQUIPMENT_MATERIAL_LIMIT
    size = sum(len(account.get(key, [])) for key in ("weapon_list", "stigmata_list"))
    if equipment_count and size + equipment_count > stage._u32(
            account["main"]["equipment_size_limit"], "equipment size limit"):
        raise _Rejected(4)  # EQUIPMENT_FULL


def _claim(account, values):
    mission_id = stage._u32(values.get("mission_id", 0), "mission_id")
    import server19_extra_achievements as extra_achievements
    extra = extra_achievements.claim(account, mission_id)
    if extra is not None:
        return extra
    daily = duty.claim_daily(account, mission_id)
    if daily is not None:
        return daily
    ach = achievement.claim_achievement(account, mission_id)
    if ach is not None:
        return ach
    if achievement.is_achievement(mission_id):
        raise _Rejected(3)
    if mission_id not in SUPPORTED_MISSION_IDS:
        raise _Rejected(2)  # MISSION_ID_ERROR
    catalog = mission_catalog()
    runtime = _runtime(account, catalog)
    previous = next((row for row in runtime["receipts"] if row["mission_id"] == mission_id), None)
    if previous is not None:
        # Native OnMissionRewardGot silently ignores STATUS_ERROR3. Replaying
        # success reopens its reward dialog even though no second grant occurs.
        return {"retcode": 3}
    row = next((row for row in _mission_rows(account) if row["mission_id"] == mission_id), None)
    if row is None or row.get("status") != MISSION_FINISH or row.get("progress") != 1:
        raise _Rejected(3)  # MISSION_STATUS_ERROR
    config = catalog[mission_id]
    if config["stage_id"] not in _confirmed_wins(account):
        raise _Rejected(3)
    reward = config["reward"]
    _preflight(account, reward)
    exp_audit = player_progression.grant_player_exp(account["main"], reward["exp"]) if reward["exp"] else None
    for key in ("scoin", "hcoin", "stamina"):
        if reward[key]:
            account["main"][key] = stage._u32(account["main"].get(key, 0) + reward[key],
                                             "stored mission " + key)
    totals = {}
    for item in reward["item_list"]:
        if item["id"] == progression.STORY_CARD_ID:
            progression.grant_story_avatar_card(account, item["id"])
        else:
            totals[(item["id"], item["level"])] = item["num"]
    stage._grant_drops(account, totals)
    result = {"retcode": 0, "reward_list": [deepcopy(reward)]}
    runtime["claimed_ids"].append(mission_id)
    runtime["receipts"].append({"mission_id": mission_id, "stage_id": config["stage_id"],
                               "response": deepcopy(result), "claimed_at": time.time()})
    if exp_audit is not None:
        runtime["receipts"][-1]["player_progression"] = exp_audit
    synchronize(account)
    return result


def _has_got_snapshot(account):
    ids = account.get("has_got_item_id_list", [])
    if not isinstance(ids, list) or any(type(value) is not int or not 0 < value <= 0xFFFFFFFF for value in ids):
        raise ValueError("Malformed previously obtained item IDs")
    actual = set(ids)
    actual.update(stage._u32(row["id"], "owned item ID") for key in
                  ("weapon_list", "stigmata_list", "material_list") for row in account.get(key, []))
    runtime = account.get("stage_runtime", {})
    if not isinstance(runtime, dict) or not isinstance(runtime.get("settlements", []), list):
        raise ValueError("Malformed saved item acquisition history")
    for receipt in runtime.get("settlements", []):
        if not isinstance(receipt, dict) or not isinstance(receipt.get("response", {}), dict):
            raise ValueError("Malformed saved item acquisition receipt")
        if receipt.get("end_status") == stage.STAGE_WIN and receipt.get("response", {}).get("retcode") == 0:
            actual.update(stage._u32(item["item_id"], "accepted stage item ID")
                          for item in receipt.get("accepted_drops", []))
    if "mission_runtime" in account:
        for receipt in _runtime(account, mission_catalog())["receipts"]:
            actual.update(item["id"] for reward in receipt["response"]["reward_list"]
                          for item in reward["item_list"])
    if 0 in actual:
        raise ValueError("Empty owned item identity")
    account["has_got_item_id_list"] = sorted(actual)
    return "GetHasGotItemIdListRsp", {"retcode": 0,
                                     "item_id_list": list(account["has_got_item_id_list"])}


def response(request_name, account, request_values=None, *, account_path=None):
    """Refresh/commit through the exact shared stage lock and atomic writer."""
    if request_name in duty.HANDLED_REQUESTS:
        # The duty module takes the same account lock itself, so it must not be
        # called from inside this function's lock.
        return duty.response(request_name, account, request_values,
                             account_path=account_path)
    if request_name not in HANDLED_REQUESTS:
        return None
    response_name = request_name[:-3] + "Rsp"
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = stage.copy_account(before)
        try:
            if request_name == "GetHasGotItemIdListReq":
                result = _has_got_snapshot(current)
            else:
                synchronize(current)
                result = mission_snapshot(current) if request_name == "GetMissionDataReq" else (
                    response_name, _claim(current, request_values or {}))
            # Validate every packet before committing a reward. Preserving an
            # unrelated account field cannot commit a claim whose snapshot is
            # later rejected by the original serializer.
            proto.encode_message(*result)
            if request_name == "GetMissionRewardReq" and result[1].get("retcode") == 0:
                for packet in notification_snapshot(current):
                    proto.encode_message(*packet)
            if result[1].get("retcode") == 0:
                stage._save(path, before, current)
                stage._sync(account, current)
            else:
                stage._sync(account, before)
        except _Rejected as rejected:
            result = response_name, {"retcode": rejected.retcode}
        except (ValueError, TypeError, KeyError, OSError):
            result = response_name, {"retcode": 1}
        if result[1].get("retcode") != 0:
            stage._sync(account, before)
        return result


def notification_snapshot(account):
    """Send AFTER GetMissionRewardRsp; equipment must precede avatar UIDs.

    Original MissionRewardGotDialogContext.OnNotify76318 listens for avatar
    unlock Notify0x22 and opens AvatarUnlockDialog. Sending AvatarData first
    would emit that notification before the reward dialog exists. Original
    UpdateEquipmentBySlot67519 resolves each new avatar UID through Storage.
    """
    import server19_initialization
    materials = [m for m in account.get("material_list", []) if m.get("num", 0) > 0]
    return [("GetEquipmentDataRsp", {"retcode": 0,
                                     "weapon_list": deepcopy(account.get("weapon_list", [])),
                                     "stigmata_list": deepcopy(account.get("stigmata_list", [])),
                                     "material_list": deepcopy(materials)}),
            server19_initialization.response("GetMainDataReq", account),
            mission_snapshot(account),
            ("GetAvatarDataRsp", {"retcode": 0,
                                  "avatar_list": deepcopy(account.get("avatar_list", []))})]
