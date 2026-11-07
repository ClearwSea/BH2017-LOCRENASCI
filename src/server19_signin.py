"""Monthly sign-in and catch-up (补签) service for Server 19.

Maintains daily sign-in rotation based on month parity (odd/even),
and enables catching up for missed days up to the current calendar day.
"""
from copy import deepcopy
import datetime
from pathlib import Path
import time

import server19_business_clock as clock
import server19_duty as duty
import server19_stage as stage

HANDLED_REQUESTS = frozenset((
    "GetSignInRewardStatusReq",
    "GetSignInRewardReq",
))


# User-approved replacement is scoped to sign-in, preserving table/status IDs.
# 客户端同步显示10000金币；不影响共享任务奖励表或领取状态。
def _reward_of(reward_id):
    return duty._reward_of(60048 if reward_id in (1211, 1212, 1213, 1214) else reward_id)


def _get_table_for_month(month):
    table_name = "oddsigninrewarddata" if (month % 2 == 1) else "evensigninrewarddata"
    return stage._table(table_name)


def _ensure_runtime(account, now=None):
    now = now if type(now) is datetime.date else clock.game_date(now)
    r = account.setdefault("sign_in_runtime", {
        "month": now.month,
        "signed_days": 0,
        "last_sign_time": 0,
    })
    if "year" not in r:
        previous = clock.game_date(r["last_sign_time"]) if r.get("last_sign_time") else now
        r["year"] = previous.year - (not r.get("last_sign_time") and r["month"] > now.month)
    if (now.year, now.month) > (r["year"], r["month"]):
        r.setdefault("month_archive", []).append({k: r.get(k) for k in ("year", "month", "signed_days", "last_sign_time")})
        r["year"] = now.year
        r["month"] = now.month
        r["signed_days"] = 0
        r["last_sign_time"] = 0
    return r


def status_info(account, now=None):
    now = now if type(now) is datetime.date else clock.game_date(now)
    r = _ensure_runtime(account, now)
    table = _get_table_for_month(now.month)
    total_days = len(table)
    signed_days = r.get("signed_days", 0)

    # Catch-up (补签): if signed_days < current day of month, can sign in
    can_sign = ((r["year"], r["month"]) == (now.year, now.month)
                and signed_days < now.day and signed_days < total_days)
    next_day = min(signed_days + 1, total_days)
    next_reward_id = table[next_day - 1]["rewardItemID"] if total_days > 0 else 0

    return {
        "retcode": 0,
        "is_need_sign_in": can_sign,
        "next_sign_in_day": next_day,
        "next_sign_in_reward_id": next_reward_id,
    }


def response(name, account, values=None, *, account_path=None, now=None):
    if name not in HANDLED_REQUESTS:
        return None

    now = now if type(now) is datetime.date else clock.game_date(now)

    if name == "GetSignInRewardStatusReq":
        return "GetSignInRewardStatusRsp", status_info(account, now)

    if name == "GetSignInRewardReq":
        path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
        with stage._transaction_lock(path):
            before = stage._read(path, account)
            current = deepcopy(before)
            r = _ensure_runtime(current, now)
            table = _get_table_for_month(now.month)
            total_days = len(table)
            signed_days = r.get("signed_days", 0)

            if (r["year"], r["month"]) != (now.year, now.month) or signed_days >= now.day or signed_days >= total_days:
                return "GetSignInRewardRsp", {"retcode": 1, "reward_list": []}

            end_day = min(now.day, total_days)
            combined_reward = {
                "exp": 0, "scoin": 0, "hcoin": 0, "stamina": 0,
                "skill_point": 0, "friends_point": 0, "duty_point": 0,
                "item_list": [],
                "_items": {},
            }
            for day in range(signed_days + 1, end_day + 1):
                reward_id = table[day - 1]["rewardItemID"]
                r_item = _reward_of(reward_id)
                for k in ("exp", "scoin", "hcoin", "stamina", "skill_point", "friends_point", "duty_point"):
                    combined_reward[k] += r_item.get(k, 0)
                for it in r_item.get("item_list", []):
                    existing = next((x for x in combined_reward["item_list"] if x["id"] == it["id"]), None)
                    if existing:
                        existing["num"] += it.get("num", 1)
                    else:
                        combined_reward["item_list"].append(deepcopy(it))
                for it_id, count in r_item.get("_items", {}).items():
                    combined_reward["_items"][it_id] = combined_reward["_items"].get(it_id, 0) + count

            public_reward = duty._pay(current, combined_reward)
            r["signed_days"] = end_day
            r["last_sign_time"] = int(clock.local_now().timestamp())

            stage._save(path, before, current)
            stage._sync(account, current)

        return "GetSignInRewardRsp", {
            "retcode": 0,
            "reward_list": [public_reward],
        }

    return None
