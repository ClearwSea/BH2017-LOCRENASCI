"""Original Req556/558 chapter-star rewards with persisted atomic receipts.

Only reviewed Normal Acts in chapters1–6 and resource-ready account
stages contribute. Configurations/rewards are deployed filtered 2.4 rows;
historical 1.9 economy has not been recovered. This module never invents
clears, stars, first drops, repeated random drops or tutorial completion.
"""
from copy import deepcopy
import json
from pathlib import Path
import time

import server19_initialization as initialization
import server19_missions as missions
import server19_protocol as proto
import server19_stage as stage

HANDLED_REQUESTS = frozenset(("GetStageActDifficultyReq", "TakeStageActChallengeRewardReq"))
SOURCE_POLICY = "deployed24_scoped_act_star_rewards"
SUPPORTED_KEYS = tuple((act_id, 1) for act_id in range(101, 108))
_CURRENCIES = {"exp": "RewardExp", "scoin": "RewardSCoin", "hcoin": "RewardHCoin",
               "stamina": "RewardStamina", "skill_point": "RewardSkillPoint",
               "friends_point": "RewardFriendPoint", "duty_point": "RewardDutyPoint"}
_EXPECTED = {
    (101, 1): ((7, 990011, 2000, 0, [(3000, 0, 5)]),
               (11, 990012, 3000, 0, [(3000, 0, 9), (1001, 0, 15)]),
               (15, 990013, 4000, 30, [(3000, 0, 14)])),
    (102, 1): ((7, 990041, 2000, 0, [(3000, 0, 5)]),
               (11, 990042, 3000, 0, [(3000, 0, 10), (1001, 0, 15)]),
               (15, 990043, 4000, 30, [(3000, 0, 15)])),
    (103, 1): ((7, 990071, 2000, 0, [(3000, 0, 5)]),
               (11, 990072, 3000, 0, [(3000, 0, 10), (1001, 0, 15)]),
               (15, 990073, 5000, 30, [(3000, 0, 15)])),
    (104, 1): ((7, 990101, 2000, 0, [(3000, 0, 5)]),
               (11, 990102, 4000, 0, [(3000, 0, 11), (1001, 0, 15)]),
               (15, 990103, 5000, 30, [(3000, 0, 16)])),
    (105, 1): ((7, 990131, 2000, 0, [(3000, 0, 6)]),
               (11, 990132, 4000, 0, [(3000, 0, 11), (1001, 0, 20)]),
               (15, 990133, 5000, 30, [(3000, 0, 17)])),
    (106, 1): ((9, 990161, 3000, 0, [(3000, 0, 6)]),
               (13, 990162, 4000, 0, [(3000, 0, 12), (1001, 0, 20)]),
               (18, 990163, 5000, 30, [(3000, 0, 18)])),
    (107, 1): ((7, 990191, 3000, 0, [(3000, 0, 6)]),
               (11, 990192, 4000, 0, [(3000, 0, 13), (1001, 0, 20)]),
               (15, 990193, 6000, 30, [(3000, 0, 19)])),
}

# Reviewed source thresholds and reward quantities; never derive payouts from
# an unchecked client request. Actual stars still require persisted WINs.
_STORY_ACT_SOURCE = Path(__file__).with_name('server19_story_act_rewards.json')
_STORY_ACT_DATA = json.loads(_STORY_ACT_SOURCE.read_bytes())
# Generated JSON may change whitespace and key order without changing rewards.
from server19_build_capabilities import canonical_sha
if canonical_sha(_STORY_ACT_DATA) != '42df457893bfbce751a50d36475d8da2ae0b8b82a0639e937c6b825ec80a320d':
    raise ValueError('Reviewed story Act reward source changed')
for _act, _tiers in _STORY_ACT_DATA.items():
    _EXPECTED[int(_act), 1] = tuple((n, rid, coin, crystal, [tuple(x) for x in items])
                                  for n, rid, coin, crystal, items in _tiers)
SUPPORTED_KEYS = tuple(_EXPECTED)


def catalog():
    """Audit thresholds, reward quantities and normal difficulty exactly."""
    acts = stage._table("actchallengedata", field="actId", identities=[key[0] for key in _EXPECTED])
    rewards = stage._table("rewarddata", field="RewardID", identities=[
        row[1] for expected in _EXPECTED.values() for row in expected])
    result = {}
    for key, expected in _EXPECTED.items():
        matches = [row for row in acts if (row.get("actId"), row.get("difficulty")) == key]
        if len(matches) != 1 or matches[0].get("isShow") != 1:
            raise ValueError("Missing or changed normal Act challenge configuration")
        config = matches[0]
        for index, (threshold, reward_id, scoin, hcoin, items) in enumerate(expected, 1):
            if (config.get(f"challengeNum{index}"), config.get(f"RewardID{index}")) != (threshold, reward_id):
                raise ValueError("Act star threshold or reward ID changed")
            selected = [row for row in rewards if row.get("RewardID") == reward_id]
            if len(selected) != 1:
                raise ValueError("Missing or ambiguous Act reward row")
            row = selected[0]
            reward = {name: stage._u32(row[field], field) for name, field in _CURRENCIES.items()}
            actual_items = []
            for slot in range(1, 6):
                item = tuple(stage._u32(row[f"RewardItem{slot}{field}"], "reward item")
                             for field in ("ID", "Level", "Num"))
                if item[0] and item[2]:
                    actual_items.append(item)
                elif item != (0, 0, 0):
                    raise ValueError("Malformed Act reward item slot")
            if reward != {"exp": 0, "scoin": scoin, "hcoin": hcoin, "stamina": 0,
                          "skill_point": 0, "friends_point": 0, "duty_point": 0} or actual_items != items:
                raise ValueError("Act star reward changed; audit before granting")
            for item_id, level, count in actual_items:
                if stage._item_metadata(item_id)[0] != "material" or level != 0:
                    raise ValueError("Act item storage type requires another audit")
            reward["item_list"] = [dict(zip(("id", "level", "num"), item)) for item in actual_items]
            result[key + (index,)] = {"threshold": threshold, "reward_id": reward_id, "reward": reward}
    return result


def star_count(account, act_id, difficulty):
    """Count unique valid saved challenges only on successfully settled WINs."""
    wins = missions._confirmed_wins(account)
    supported = frozenset(stage.supported_stage_ids())
    total = 0
    for saved in account.get("stage_list", []):
        identity = saved.get("id")
        if identity not in supported:
            continue
        config = stage.stage_config(identity)
        if (config["actId"], config["difficulty"]) != (act_id, difficulty):
            continue
        indices = saved.get("challenge_index_list", [])
        if not isinstance(indices, list) or any(type(index) is not int or
                not 0 <= index < len(config["challengeList"]) for index in indices) or len(indices) != len(set(indices)):
            raise ValueError("Invalid saved star indices")
        if identity in wins:
            total += len(indices)
    return total


def _groups(account):
    rows = account.get("stage_act_difficulty_list", [])
    if not isinstance(rows, list):
        raise ValueError("Malformed saved Act difficulty state")
    groups = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"act_id", "difficulty", "has_take_challenge_num_index"}:
            raise ValueError("Malformed saved Act difficulty row")
        key = (stage._u32(row["act_id"], "act_id"), stage._u32(row["difficulty"], "difficulty"))
        indices = row["has_take_challenge_num_index"]
        if not all(key) or key in groups or not isinstance(indices, list) or \
                any(type(index) is not int or index not in (1, 2, 3) for index in indices) or len(indices) != len(set(indices)):
            raise ValueError("Duplicate or invalid saved Act reward identity")
        groups[key] = deepcopy(row)
    return groups


def _runtime(account, audited, groups):
    runtime = account.get("act_reward_runtime", {"schema": 1, "source_policy": SOURCE_POLICY, "receipts": []})
    if not isinstance(runtime, dict) or runtime.get("schema") != 1 or runtime.get("source_policy") != SOURCE_POLICY:
        raise ValueError("Unsupported Act reward receipt schema")
    receipts = runtime.get("receipts")
    if not isinstance(receipts, list):
        raise ValueError("Malformed Act reward receipt list")
    keys = set()
    for row in receipts:
        if not isinstance(row, dict):
            raise ValueError("Malformed Act reward receipt")
        key = (row.get("act_id"), row.get("difficulty"), row.get("challenge_num_index"))
        if any(type(value) is not int for value in key) or key not in audited or key in keys:
            raise ValueError("Duplicate or invalid Act reward receipt identity")
        expected = {"retcode": 0, "act_id": key[0], "difficulty": key[1],
                    "challenge_num_index": key[2], "reward_list": [audited[key]["reward"]]}
        if row.get("response") != expected or key[2] not in groups.get(key[:2], {}).get("has_take_challenge_num_index", []):
            raise ValueError("Act claim marker and receipt disagree")
        keys.add(key)
    return deepcopy(runtime)


def difficulty_snapshot(account):
    audited = catalog()
    groups = _groups(account)
    _runtime(account, audited, groups)
    # Include unclaimed supported Acts explicitly. Preserve saved other groups
    # without granting their rewards or deriving unavailable difficulty stars.
    for act_id, difficulty in SUPPORTED_KEYS:
        groups.setdefault((act_id, difficulty), {"act_id": act_id, "difficulty": difficulty,
                                                "has_take_challenge_num_index": []})
    return "GetStageActDifficultyRsp", {"retcode": 0, "act_difficulty_list": list(groups.values())}


def _claim(account, values):
    key = tuple(stage._u32(values.get(field, 0), field)
                for field in ("act_id", "difficulty", "challenge_num_index"))
    audited = catalog()
    if key not in audited:
        return {"retcode": 1}  # Original FAIL=1; no fabricated other Act/difficulty.
    groups = _groups(account)
    runtime = _runtime(account, audited, groups)
    for receipt in runtime["receipts"]:
        if tuple(receipt[field] for field in ("act_id", "difficulty", "challenge_num_index")) == key:
            return deepcopy(receipt["response"])
    if key[2] in groups.get(key[:2], {}).get("has_take_challenge_num_index", []):
        # Imported prior claims have no authored response receipt to replay.
        return {"retcode": 2}  # Original HAS_TAKE=2.
    if star_count(account, *key[:2]) < audited[key]["threshold"]:
        return {"retcode": 3}  # Original CHALLENGE_NUM_LACK=3.
    reward = audited[key]["reward"]
    # Apply all inventory/currency changes to the caller's transaction copy;
    # any capacity/metadata error aborts without a saved marker or partial loot.
    stage._grant_drops(account, {(item["id"], item["level"]): item["num"] for item in reward["item_list"]})
    for currency in ("scoin", "hcoin"):
        account["main"][currency] = stage._u32(account["main"].get(currency, 0) + reward[currency], currency)
    group = groups.setdefault(key[:2], {"act_id": key[0], "difficulty": key[1], "has_take_challenge_num_index": []})
    group["has_take_challenge_num_index"] = sorted(group["has_take_challenge_num_index"] + [key[2]])
    account["stage_act_difficulty_list"] = list(groups.values())
    result = {"retcode": 0, "act_id": key[0], "difficulty": key[1],
              "challenge_num_index": key[2], "reward_list": [deepcopy(reward)]}
    runtime["receipts"].append({"act_id": key[0], "difficulty": key[1], "challenge_num_index": key[2],
                                "response": deepcopy(result), "claimed_at": time.time()})
    account["act_reward_runtime"] = runtime
    return result


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            result = difficulty_snapshot(current) if request_name == "GetStageActDifficultyReq" else (
                "TakeStageActChallengeRewardRsp", _claim(current, request_values or {}))
            proto.encode_message(*result)
            if request_name == "TakeStageActChallengeRewardReq" and result[1].get("retcode") == 0:
                for packet in notification_snapshot(current):
                    proto.encode_message(*packet)
            if result[1].get("retcode") == 0:
                stage._save(path, before, current)
                stage._sync(account, current)
            else:
                stage._sync(account, before)
        except (ValueError, TypeError, KeyError, OSError):
            result = request_name[:-3] + "Rsp", {"retcode": 1}
            stage._sync(account, before)
        return result


def notification_snapshot(account):
    """Snapshots: send the final claim-state packet before Rsp559 redraws UI.

    Main/inventory follow the reward response; this ordering applies to all
    supported Acts and tiers, including idempotent receipt replay.
    """
    return [initialization.response("GetMainDataReq", account),
            ("GetEquipmentDataRsp", {"retcode": 0, **{key: deepcopy(account.get(key, []))
                for key in ("weapon_list", "stigmata_list", "material_list")}}),
            difficulty_snapshot(account)]
