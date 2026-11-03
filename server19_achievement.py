"""成就系统服务端评估与领奖 / Achievement system server evaluation and claims."""
from copy import deepcopy
import json
from pathlib import Path
import time

import server19_stage as stage
import server19_player_progression as player_progression

ROOT = Path(__file__).resolve().parent
META_DIR = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'

MISSION_DOING = 2
MISSION_FINISH = 3
MISSION_CLOSE = 5

_LINEAR = None
_MISSIONS = None
_REWARDS = None


def _load_meta():
    global _LINEAR, _MISSIONS, _REWARDS
    if _LINEAR is None:
        _LINEAR = {x["MissionID"]: x for x in json.loads((META_DIR / "linearmissiondata").read_text(encoding="utf-8"))}
        _MISSIONS = {x["id"]: x for x in json.loads((META_DIR / "missiondata").read_text(encoding="utf-8"))}
        _REWARDS = {x["RewardID"]: x for x in json.loads((META_DIR / "rewarddata").read_text(encoding="utf-8"))}


def is_achievement(mission_id):
    _load_meta()
    lin = _LINEAR.get(mission_id)
    return lin is not None and lin.get("IsAchievement") == 1


def _parse_reward(row):
    items = []
    for i in range(1, 6):
        iid = row.get(f"RewardItem{i}ID", 0)
        num = row.get(f"RewardItem{i}Num", 0)
        lv = row.get(f"RewardItem{i}Level", 0)
        if iid and num:
            items.append({"id": iid, "level": lv, "num": num})
    return {
        "exp": row.get("RewardExp", 0),
        "scoin": row.get("RewardSCoin", 0),
        "hcoin": row.get("RewardHCoin", 0),
        "stamina": row.get("RewardStamina", 0),
        "skill_point": row.get("RewardSkillPoint", 0),
        "friends_point": row.get("RewardFriendPoint", 0),
        "duty_point": row.get("RewardDutyPoint", 0),
        "item_list": items,
    }


def achievement_rows(account):
    _load_meta()
    runtime = account.setdefault("achievement_runtime", {"claimed_ids": []})
    claimed = set(runtime.setdefault("claimed_ids", []))

    player_lvl = account.get("main", {}).get("level", 1)
    weapons_cnt = len(account.get("weapon_list", []))
    stigmata_cnt = len(account.get("stigmata_list", []))
    avatars_cnt = len(account.get("avatar_list", []))

    rows = []
    # Add claimed achievements with MISSION_CLOSE so client recognizes them
    for cid in sorted(claimed):
        # Filter orphan linear rows: the native achievement filter dereferences
        # MissionDataItem.metaData after accepting the linear achievement flag.
        if cid not in _MISSIONS or not is_achievement(cid):
            continue
        rows.append({"mission_id": cid, "status": MISSION_CLOSE, "progress": 1})

    for mid, m in _MISSIONS.items():
        lin = _LINEAR.get(mid)
        if not lin or lin.get("IsAchievement") != 1:
            continue
        pre = lin.get("PreMissionId", 0)
        if pre != 0 and pre not in claimed:
            continue
        if mid in claimed:
            continue

        fw = m.get("finishWay")
        tp = m.get("totalProgress", 1)
        is_fin = False
        prog = 0

        if 50102 <= mid <= 50109:
            req_lv = (mid - 50101) * 10
            prog = min(player_lvl, req_lv)
            is_fin = (player_lvl >= req_lv)
        elif fw == 36:  # player level
            prog = min(player_lvl, tp)
            is_fin = (player_lvl >= tp)
        elif fw == 38 and m.get("finishParaInt") == 1:
            prog = min(avatars_cnt, tp)
            is_fin = (avatars_cnt >= tp)
        elif fw == 40:  # weapon count
            prog = min(weapons_cnt, tp)
            is_fin = (weapons_cnt >= tp)
        elif fw == 41:  # stigmata count
            prog = min(stigmata_cnt, tp)
            is_fin = (stigmata_cnt >= tp)
        elif fw == 1:
            req_lv = m.get("finishParaInt") or tp or 10
            prog = min(player_lvl, req_lv)
            is_fin = (player_lvl >= req_lv)
        else:
            prog = 0
            is_fin = False

        status = MISSION_FINISH if is_fin else MISSION_DOING
        rows.append({"mission_id": mid, "status": status, "progress": prog})

    return rows


def claim_achievement(account, mission_id):
    _load_meta()
    if not is_achievement(mission_id):
        return None
    runtime = account.setdefault("achievement_runtime", {"claimed_ids": [], "receipts": []})
    claimed = set(runtime.setdefault("claimed_ids", []))
    receipts = {r["mission_id"]: r["response"] for r in runtime.setdefault("receipts", [])}
    if mission_id in receipts:
        return deepcopy(receipts[mission_id])
    if mission_id in claimed:
        return {"retcode": 0, "reward_list": []}

    # Check that mission is actually finished
    active = {r["mission_id"]: r for r in achievement_rows(account)}
    row = active.get(mission_id)
    if not row or row.get("status") != MISSION_FINISH:
        return None

    m = _MISSIONS[mission_id]
    reward_row = _REWARDS.get(m.get("rewardId"))
    if not reward_row:
        return None
    reward = _parse_reward(reward_row)

    # Grant rewards
    if reward.get("exp"):
        player_progression.grant_player_exp(account["main"], reward["exp"])
    for key in ("scoin", "hcoin", "stamina"):
        val = reward.get(key, 0)
        if val:
            account["main"][key] = stage._u32(account["main"].get(key, 0) + val, f"achieve {key}")
    totals = {}
    for it in reward.get("item_list", []):
        totals[(it["id"], it["level"])] = it["num"]
    if totals:
        stage._grant_drops(account, totals)

    runtime["claimed_ids"].append(mission_id)
    runtime["claimed_ids"].sort()
    resp = {"retcode": 0, "reward_list": [deepcopy(reward)]}
    runtime["receipts"].append({
        "mission_id": mission_id,
        "response": deepcopy(resp),
        "claimed_at": time.time(),
    })
    return resp
