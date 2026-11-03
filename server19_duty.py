"""Daily / weekly duty ("每日使命") support for the 1.9 client.

Three things the original server did that this offline one did not:

1. Publish the daily task list. The client renders whatever the server puts in
   GetMissionDataRsp.mission_list; because that list was empty the client fell
   back to showing every daily task as already finished.

2. Track completion and the duty-point total behind it.

3. Answer TakeDutyRewardReq. proto.TakeDutyRewardReq{duty_type, duty_id} asks for
   a duty-point milestone reward; the milestone rows live in the deployed
   dutydailydata / dutyweeklydata tables (dutyId, needDuty, unlockLv, rewardId).

Daily task list (curated by the project owner, 2026-10-13) with the events that
complete them, keyed by missiondata.finishWay:

  30001 午餐        1   time window 11:00-14:00 (see TIMED_WINDOWS)
  30002 晚餐        1   time window 17:00-20:00
  31001 首次胜利    16  any cleared stage
  31003 好友助战    16  any cleared stage entered with an assistant
  32003 强化装备    15  EquipmentPowerUpReq / EquipmentEvoReq
  34005 技能升级    13  AvatarSubSkillLevelUpReq
  36002 常规补给    14  daily supply (see note on note_event)

finishWay=1 tasks are clock-driven, so they are neither completed nor shown
outside their window. The window bounds are not present in the deployed tables
(`PreviewTime` only carries a duration, and only for Dinner/Snack), so they are
stated here as constants and can be corrected in one place.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import time

import server19_business_clock as clock
import server19_stage as stage
import server19_protocol as proto

DUTY_DAILY, DUTY_WEEKLY = 1, 2          # proto.DutyType
DUTY_TABLES = {DUTY_DAILY: "dutydailydata", DUTY_WEEKLY: "dutyweeklydata"}
HANDLED_REQUESTS = frozenset(("TakeDutyRewardReq",))

MISSION_DOING = 2
MISSION_FINISH = 3
MISSION_CLOSE = 5

# Curated daily list, in display order.
QUICK_DUTY_MISSION_ID = 30099
REGULAR_DAILY_MISSION_IDS = (30001,   # TimedMissionName_Lunch          午餐
                             30002,   # TimedMissionName_Dinner         晚餐
                             31001,   # TimedMissionName_FirstVictory   首胜
                             31003,   # TimedMissionName_FriendAssist   好友助战
                             32003,   # MissionName_EnhanceEquipment    强化装备
                             34005,   # MissionName_AvatarSkillLevelUp  技能升级
                             36002)   # MissionName_RegularSupplyDaily  常规补给
DAILY_MISSION_IDS = (QUICK_DUTY_MISSION_ID,) + REGULAR_DAILY_MISSION_IDS

# Clock windows for the finishWay=1 tasks, as (start, end) local hours.
TIMED_WINDOWS = {30001: ((11, 0), (14, 0)),     # 描述原文 "11:00-14:00在线，可领取30体力"
                 30002: ((18, 0), (21, 0))}     # 描述原文 "18:00-21:00在线，可领取30体力"

# Which daily tasks each observable event advances.
EVENT_MISSIONS = {"stage_win": (31001,),
                  "stage_win_assist": (31003,),
                  "enhance_equipment": (32003,),
                  "skill_up": (34005,),
                  "supply": (36002,)}


def _target(mission_id):
    rows = stage._table("missiondata", field="id", identities=(mission_id,))
    if len(rows) != 1:
        raise ValueError("Daily mission row missing from the deployed tables")
    total = stage._u32(rows[0].get("totalProgress", 0), "totalProgress")
    return max(total, 1)


def _duty_points_of(mission_id):
    rows = stage._table("missiondata", field="id", identities=(mission_id,))
    if len(rows) != 1:
        raise ValueError("Daily mission row missing from the deployed tables")
    reward_id = stage._u32(rows[0]["rewardId"], "rewardId")
    rewards = stage._table("rewarddata", field="RewardID", identities=(reward_id,))
    if len(rewards) != 1:
        raise ValueError("Daily mission reward row missing from the deployed tables")
    return stage._u32(rewards[0].get("RewardDutyPoint", 0), "RewardDutyPoint")


def _window_state(mission_id, now=None):
    """Returns 'before', 'active', or 'passed' for timed missions; None for non-timed."""
    window = TIMED_WINDOWS.get(mission_id)
    if window is None:
        return None
    now = clock.local_now(now)
    minutes = now.hour * 60 + now.minute
    (sh, sm), (eh, em) = window
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    if minutes < start_minutes:
        return "before"
    if minutes < end_minutes:
        return "active"
    return "passed"


def _in_window(mission_id, now=None):
    state = _window_state(mission_id, now)
    return state is None or state == "active"


def daily_mission_ids(now=None):
    """The daily tasks to publish right now (clock tasks appear only in-window)."""
    return tuple(mission_id for mission_id in DAILY_MISSION_IDS
                 if _in_window(mission_id, now))


def _runtime(account, now=None):
    runtime = account.setdefault("duty_runtime",
                                 {"schema": 1, "weekly_point": 0,
                                  "daily_taken": [], "weekly_taken": [],
                                  "progress": {}, "receipts": []})
    if runtime.get("schema") != 1 or not isinstance(runtime.get("receipts"), list):
        raise ValueError("Unsupported duty transaction state")
    runtime.setdefault("progress", {})
    day, week = clock.day_key(now), clock.week_key(now)
    if "day_key" not in runtime:
        last = max((r.get("claimed_at", 0) for r in runtime["receipts"]), default=clock.local_now(now).timestamp())
        runtime["day_key"], runtime["week_key"] = clock.day_key(last), clock.week_key(last)
    if week > runtime.get("week_key", week):
        runtime["weekly_point"], runtime["weekly_taken"] = 0, []
        expired = [r for r in runtime["receipts"] if r.get("kind") == "milestone" and r.get("duty_type") == DUTY_WEEKLY]
        runtime.setdefault("receipt_archive", []).extend(expired)
        runtime["receipts"] = [r for r in runtime["receipts"] if r not in expired]
        runtime["week_key"] = week
    if day > runtime["day_key"]:
        expired = [r for r in runtime["receipts"] if not (r.get("kind") == "milestone" and r.get("duty_type") == DUTY_WEEKLY)]
        runtime.setdefault("receipt_archive", []).extend(expired)
        runtime["receipts"] = [r for r in runtime["receipts"] if r not in expired]
        runtime["daily_taken"], runtime["progress"] = [], {}
        runtime["day_key"] = day
    return runtime


def _progress(runtime, mission_id):
    return stage._u32(runtime["progress"].get(str(mission_id), 0), "duty mission progress")


def _mission_done(runtime, mission_id, now=None):
    """A clock task is claimable for as long as its window is open; the others
    need their counter to reach the configured total."""
    if mission_id in TIMED_WINDOWS:
        return _in_window(mission_id, now)
    return _progress(runtime, mission_id) >= _target(mission_id)


def note_event(account, kind, count=1):
    """Advance every daily task driven by `kind`; returns the ids that completed.

    Callers work on the account object staged by the stage transaction lock, so a
    rejected request cannot leave half-applied progress behind.
    """
    mission_ids = EVENT_MISSIONS.get(kind)
    if not mission_ids:
        return []
    runtime = _runtime(account)
    completed = []
    for mission_id in mission_ids:
        if mission_id not in DAILY_MISSION_IDS:
            continue
        target = _target(mission_id)
        if not _in_window(mission_id):
            continue
        current = _progress(runtime, mission_id)
        if current >= target:
            continue
        current = min(target, current + max(count, 0))
        runtime["progress"][str(mission_id)] = current
        if current >= target:
            completed.append(mission_id)
    return completed


def daily_mission_rows(now=None):
    """GetMissionDataRsp.mission_list rows for the visible daily tasks."""
    rows = []
    for mission_id in daily_mission_ids(now):
        target = _target(mission_id)
        rows.append({"mission_id": mission_id, "target": target})
    return rows


def _mission_times(mission_id, now=None):
    now = clock.local_now(now)
    if mission_id in TIMED_WINDOWS:
        (sh, sm), (eh, em) = TIMED_WINDOWS[mission_id]
        begin_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        return int(begin_dt.timestamp()), int(end_dt.timestamp())
    reset_today = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now < reset_today:
        begin_dt = reset_today - timedelta(days=1)
        end_dt = reset_today
    else:
        begin_dt = reset_today
        end_dt = reset_today + timedelta(days=1)
    return int(begin_dt.timestamp()), int(end_dt.timestamp())


def mission_rows(account, now=None):
    runtime = _runtime(account, now)
    rows = []
    quick_claimed = _claimed(runtime, QUICK_DUTY_MISSION_ID)
    current_duty = _daily_point(account, now)

    for mission_id in DAILY_MISSION_IDS:
        target = _target(mission_id)
        claimed = _claimed(runtime, mission_id)
        begin_time, end_time = _mission_times(mission_id, now)

        if mission_id == QUICK_DUTY_MISSION_ID:
            if claimed or current_duty >= 150:
                rows.append({"mission_id": mission_id,
                             "status": MISSION_CLOSE,
                             "progress": 1,
                             "begin_time": begin_time,
                             "end_time": end_time})
            else:
                rows.append({"mission_id": mission_id,
                             "status": MISSION_FINISH,
                             "progress": 1,
                             "begin_time": begin_time,
                             "end_time": end_time})
            continue

        if quick_claimed:
            rows.append({"mission_id": mission_id,
                         "status": MISSION_CLOSE,
                         "progress": 1,
                         "begin_time": begin_time,
                         "end_time": end_time})
            continue

        state = _window_state(mission_id, now)
        if claimed or state == "passed":
            rows.append({"mission_id": mission_id,
                         "status": MISSION_CLOSE,
                         "progress": 1,
                         "begin_time": begin_time,
                         "end_time": end_time})
        elif state == "before":
            continue
        else:
            done = _mission_done(runtime, mission_id, now)
            current = target if done else min(_progress(runtime, mission_id), target)
            rows.append({"mission_id": mission_id,
                         "status": MISSION_FINISH if done else MISSION_DOING,
                         "progress": 1 if done else current,
                         "begin_time": begin_time,
                         "end_time": end_time})
    return rows


def _claimed(runtime, mission_id):
    return any(row.get("kind") == "daily" and row.get("mission_id") == mission_id
               for row in runtime["receipts"])


def _daily_point(account, now=None):
    """Duty points earned today: the sum over claimed daily tasks, capped at 150 if quick completed."""
    runtime = _runtime(account, now)
    total = 0
    for row in runtime.get("receipts", []):
        if row.get("kind") == "daily":
            mid = row.get("mission_id")
            if mid == QUICK_DUTY_MISSION_ID:
                total += row.get("granted_duty", 150)
            elif mid in REGULAR_DAILY_MISSION_IDS:
                total += row.get("granted_duty", _duty_points_of(mid))
    if _claimed(runtime, QUICK_DUTY_MISSION_ID):
        return 150
    return total


def _weekly_point(account, now=None):
    runtime = _runtime(account, now)
    stored = stage._u32(runtime.get("weekly_point", 0), "weekly duty point")
    from_receipts = sum(row.get("granted_duty", _duty_points_of(row["mission_id"]))
                        for row in runtime.get("receipts", [])
                        if row.get("kind") == "daily")
    return max(stored, from_receipts)


def snapshot(account, now=None):
    """The duty fields carried by GetMissionDataRsp."""
    runtime = _runtime(account, now)
    return {"daily_duty_point": _daily_point(account, now),
            "weekly_duty_point": _weekly_point(account, now),
            "has_take_daily_duty_id_list": sorted(runtime.get("daily_taken", [])),
            "has_take_weekly_duty_id_list": sorted(runtime.get("weekly_taken", [])),
            "is_in_activity": False}


def _reward_of(reward_id):
    rows = stage._table("rewarddata", field="RewardID", identities=(reward_id,))
    if len(rows) != 1:
        raise ValueError("Reward row missing from the deployed tables")
    row = rows[0]
    items = {}
    for index in range(1, 6):
        item_id = stage._u32(row[f"RewardItem{index}ID"], "reward item id")
        if not item_id:
            continue
        level = stage._u32(row[f"RewardItem{index}Level"], "reward item level")
        num = stage._u32(row[f"RewardItem{index}Num"], "reward item num")
        items[(item_id, level)] = items.get((item_id, level), 0) + num
    return {"exp": stage._u32(row["RewardExp"], "RewardExp"),
            "scoin": stage._u32(row["RewardSCoin"], "RewardSCoin"),
            "hcoin": stage._u32(row["RewardHCoin"], "RewardHCoin"),
            "stamina": stage._u32(row["RewardStamina"], "RewardStamina"),
            "skill_point": stage._u32(row["RewardSkillPoint"], "RewardSkillPoint"),
            "friends_point": stage._u32(row["RewardFriendPoint"], "RewardFriendPoint"),
            "duty_point": stage._u32(row.get("RewardDutyPoint", 0), "RewardDutyPoint"),
            "item_list": [{"id": item_id, "level": level, "num": num}
                          for (item_id, level), num in sorted(items.items())],
            "_items": items}


def _pay(account, reward):
    if reward["exp"]:
        import server19_player_progression as player_progression
        player_progression.grant_player_exp(account["main"], reward["exp"])
    for key in ("scoin", "hcoin", "stamina", "skill_point", "friends_point"):
        if reward[key]:
            account["main"][key] = stage._u32(account["main"].get(key, 0) + reward[key],
                                              "stored duty reward " + key)
    if reward["_items"]:
        stage._grant_drops(account, reward["_items"])
    public = {key: value for key, value in reward.items() if key != "_items"}
    return public


def claim_daily(account, mission_id, now=None):
    """Collect one completed daily task's own reward (GetMissionRewardReq)."""
    mission_id = stage._u32(mission_id, "mission_id")
    if mission_id not in DAILY_MISSION_IDS:
        return None
    runtime = _runtime(account, now)
    previous = next((row for row in runtime["receipts"]
                     if row.get("kind") == "daily" and row["mission_id"] == mission_id), None)
    if previous is not None:
        return deepcopy(previous["response"])

    if mission_id == QUICK_DUTY_MISSION_ID:
        current_duty = _daily_point(account, now)
        if current_duty >= 150:
            return {"retcode": 3}
        needed = max(0, 150 - current_duty)
        rows = stage._table("missiondata", field="id", identities=(mission_id,))
        reward = _reward_of(stage._u32(rows[0]["rewardId"], "rewardId"))
        reward["duty_point"] = needed
        public = _pay(account, reward)
        result = {"retcode": 0, "reward_list": [public]}
        runtime["receipts"].append({"kind": "daily", "mission_id": mission_id,
                                    "response": deepcopy(result), "claimed_at": clock.local_now(now).timestamp(),
                                    "granted_duty": needed})
        runtime["weekly_point"] = stage._u32(
            runtime.get("weekly_point", 0) + needed,
            "weekly duty point"
        )
        return result

    if not _in_window(mission_id, now):
        return None
    if not _mission_done(runtime, mission_id, now):
        return {"retcode": 3}
    rows = stage._table("missiondata", field="id", identities=(mission_id,))
    reward = _reward_of(stage._u32(rows[0]["rewardId"], "rewardId"))
    public = _pay(account, reward)
    result = {"retcode": 0, "reward_list": [public]}
    runtime["receipts"].append({"kind": "daily", "mission_id": mission_id,
                                "response": deepcopy(result), "claimed_at": clock.local_now(now).timestamp(),
                                "granted_duty": reward.get("duty_point", 0)})
    if reward.get("duty_point"):
        runtime["weekly_point"] = stage._u32(
            runtime.get("weekly_point", 0) + reward["duty_point"],
            "weekly duty point"
        )
    return result


def _milestone(duty_type, duty_id):
    """The deployed milestone row, or None when it is not part of this version."""
    table = DUTY_TABLES.get(duty_type)
    if table is None:
        return None
    rows = stage._table(table, field="dutyId", identities=(duty_id,))
    return rows[0] if rows else None


def take_reward(account, values):
    """Grant one duty-point milestone reward; idempotent per (duty_type, duty_id)."""
    duty_type = stage._u32(values.get("duty_type", 0), "duty_type")
    duty_id = stage._u32(values.get("duty_id", 0), "duty_id")
    if duty_type not in DUTY_TABLES:
        raise ValueError("Unknown duty type")
    runtime = _runtime(account)
    taken_key = "daily_taken" if duty_type == DUTY_DAILY else "weekly_taken"
    previous = next((row for row in runtime["receipts"]
                     if row.get("kind") == "milestone"
                     and row["duty_type"] == duty_type and row["duty_id"] == duty_id), None)
    if previous is not None:
        return deepcopy(previous["response"])

    milestone = _milestone(duty_type, duty_id)
    if milestone is None:
        raise ValueError("Milestone is not part of the deployed 1.9 tables")
    need = stage._u32(milestone["needDuty"], "needDuty")
    earned = _daily_point(account) if duty_type == DUTY_DAILY else _weekly_point(account)
    if earned < need:
        # Not enough duty points yet: the milestone is simply not claimable.
        return {"retcode": 3, "duty_type": duty_type, "duty_id": duty_id}

    reward = _reward_of(stage._u32(milestone["rewardId"], "rewardId"))
    public = _pay(account, reward)
    result = {"retcode": 0, "duty_type": duty_type, "duty_id": duty_id,
              "reward_list": [public]}
    runtime[taken_key] = sorted(set(runtime.get(taken_key, [])) | {duty_id})
    runtime["receipts"].append({"kind": "milestone", "duty_type": duty_type,
                                "duty_id": duty_id, "need_duty": need,
                                "reward_id": milestone["rewardId"],
                                "response": deepcopy(result), "claimed_at": time.time()})
    return result


def response(request_name, account, request_values=None, *, account_path=None):
    """TakeDutyRewardReq through the same account lock and atomic writer."""
    if request_name not in HANDLED_REQUESTS:
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = stage.copy_account(before)
        try:
            payload = take_reward(current, request_values or {})
        except (ValueError, TypeError, KeyError, OSError):
            payload = {"retcode": 1}
        result = "TakeDutyRewardRsp", payload
        proto.encode_message(*result)
        if payload.get("retcode") == 0:
            import server19_missions
            for packet in server19_missions.notification_snapshot(current):
                proto.encode_message(*packet)
            stage._save(path, before, current)
            stage._sync(account, current)
        else:
            stage._sync(account, before)
        return result
