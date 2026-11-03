"""萌新关爱（新手登录与等级奖励）服务端实现 / Newbie Care server implementation."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import server19_business_clock as clock
import server19_stage as stage
import server19_player_progression as player_progression

ROOT = Path(__file__).resolve().parent
META_DIR = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'

HANDLED_REQUESTS = frozenset((
    "GetNewbieReq",
    "TakeNewbieLoginRewardReq",
    "TakeNewbieLevelRewardReq",
))

NEWBIE_LOGIN_MAX_TRIGGER_LEVEL = 15  # 只有初始等级 <= 15 的新用户才能激活触发萌新7天登录

_LOGIN_TABLE = None
_LEVEL_TABLE = None
_REWARD_TABLE = None


def _load_metadata():
    global _LOGIN_TABLE, _LEVEL_TABLE, _REWARD_TABLE
    if _LOGIN_TABLE is None:
        _LOGIN_TABLE = {x["loginDay"]: x for x in json.loads((META_DIR / "newbieguideloginreward").read_text(encoding="utf-8"))}
        _LEVEL_TABLE = {x["unlockLevel"]: x for x in json.loads((META_DIR / "newbieguidelevelreward").read_text(encoding="utf-8"))}
        _REWARD_TABLE = {x["RewardID"]: x for x in json.loads((META_DIR / "rewarddata").read_text(encoding="utf-8"))}


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


def _game_date_str():
    # 崩坏3以每日凌晨 04:00 换天
    return clock.day_key()


def _apply_reward(account, reward):
    if reward.get("exp"):
        player_progression.grant_player_exp(account["main"], reward["exp"])
    for key in ("scoin", "hcoin", "stamina"):
        val = reward.get(key, 0)
        if val:
            account["main"][key] = stage._u32(account["main"].get(key, 0) + val, f"newbie {key}")
    totals = {}
    for it in reward.get("item_list", []):
        iid = it["id"]
        # 女武神角色卡判断：存在于 avatardata 且为 avatarCardID
        card_rows = stage._table("avatardata", field="avatarCardID", identities=(iid,))
        if card_rows:
            import server19_gacha as gacha
            for _ in range(it.get("num", 1)):
                gacha._grant_card(account, iid)
        else:
            totals[(it["id"], it["level"])] = it["num"]
    if totals:
        stage._grant_drops(account, totals)


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    _load_metadata()
    response_name = request_name[:-3] + "Rsp"
    request_values = request_values or {}

    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        current = stage._read(path, account)
        before = deepcopy(current)
        runtime = current.setdefault("newbie_runtime", {})
        player_lvl = current.get("main", {}).get("level", 1)
        today = _game_date_str()

        # 检查是否激活新手7天登录：
        # 仅当玩家等级 <= NEWBIE_LOGIN_MAX_TRIGGER_LEVEL 时，才激活新手7天登录
        if "login_active" not in runtime:
            if player_lvl <= NEWBIE_LOGIN_MAX_TRIGGER_LEVEL:
                runtime["login_active"] = True
                runtime["login_days"] = 1
                runtime["last_login_date"] = today
                runtime["last_take_date"] = ""
                runtime["has_take_days_reward_list"] = []
            else:
                runtime["login_active"] = False
                runtime["login_days"] = 0
                runtime["last_login_date"] = today
                runtime["last_take_date"] = ""
                runtime["has_take_days_reward_list"] = []

        # 累计登录更新（仅在活动处于激活状态下）：
        if runtime.get("login_active"):
            login_days = runtime.get("login_days", 1)
            last_login = runtime.get("last_login_date", "")
            if today != last_login:
                # 跨天登录，累计登录天数 +1（最多7天）
                if login_days < 7:
                    login_days += 1
                    runtime["login_days"] = login_days
                runtime["last_login_date"] = today
        else:
            runtime["login_days"] = 0

        login_days = runtime.get("login_days", 0)
        taken_days = runtime.setdefault("has_take_days_reward_list", [])
        taken_levels = runtime.setdefault("has_take_level_reward_list", [])

        if before != current:
            stage._save(path, before, current)
            stage._sync(account, current)
            before = deepcopy(current)

        if request_name == "GetNewbieReq":
            rsp_payload = {
                "retcode": 0,
                "login_days": login_days,
                "has_take_days_reward_list": list(taken_days),
                "has_take_level_reward_list": list(taken_levels),
            }
            return response_name, rsp_payload

        elif request_name == "TakeNewbieLoginRewardReq":
            day = int(request_values.get("take_days", 0))
            # 校验活动激活状态与基础天数
            if not runtime.get("login_active") or day not in _LOGIN_TABLE or day > login_days or day in taken_days:
                return response_name, {"retcode": 1, "take_days": day, "reward_list": []}
            # 严格按顺序领取（不可跳过前面天数）
            if day != len(taken_days) + 1:
                return response_name, {"retcode": 1, "take_days": day, "reward_list": []}
            # 严格每日限领 1 次（累计签到模式，不可同一天连领多次）
            if runtime.get("last_take_date") == today:
                return response_name, {"retcode": 1, "take_days": day, "reward_list": []}

            reward_row = _REWARD_TABLE[_LOGIN_TABLE[day]["rewardID"]]
            reward = _parse_reward(reward_row)
            _apply_reward(current, reward)
            taken_days.append(day)
            taken_days.sort()
            runtime["last_take_date"] = today
            stage._save(path, before, current)
            stage._sync(account, current)
            return response_name, {"retcode": 0, "take_days": day, "reward_list": [reward]}

        elif request_name == "TakeNewbieLevelRewardReq":
            lvl = int(request_values.get("take_level", 0))
            if lvl not in _LEVEL_TABLE or lvl > player_lvl or lvl in taken_levels:
                return response_name, {"retcode": 1, "take_level": lvl, "reward_list": []}
            reward_row = _REWARD_TABLE[_LEVEL_TABLE[lvl]["rewardID"]]
            reward = _parse_reward(reward_row)
            _apply_reward(current, reward)
            taken_levels.append(lvl)
            taken_levels.sort()
            stage._save(path, before, current)
            stage._sync(account, current)
            return response_name, {"retcode": 0, "take_level": lvl, "reward_list": [reward]}

    return None
