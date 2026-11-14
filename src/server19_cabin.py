"""Cabin and Island base operations, building level-up, extension, and persistence."""
from copy import deepcopy
import secrets
import json
from pathlib import Path
import time

import server19_business_clock as clock
import server19_stage as stage

HANDLED_REQUESTS = frozenset((
    "GetIslandReq",
    "GetIslandVentureReq",
    "RefreshIslandVentureReq",
    "SpeedUpIslandVentureReq",
    "LevelUpCabinReq",
    "FinishCabinLevelUpReq",
    "SpeedUpIslandCabinReq",
    "ExtendCabinReq",
    "AddCabinTechReq",
    "ResetCabinTechReq",
    "IslandCollectReq",
    "GetCollectCabinReq",
    "DispatchIslandVentureReq",
    "CancelDispatchIslandVentureReq",
    "GetIslandVentureRewardReq",
    "GetIslandVisitRecordReq",
    "GetFriendIslandReq",
    "LikeFriendIslandReq",
    "HelpFriendIslandReq",
    "GetIslandEventReq",
    "FinishIslandEventReq",
    "GetRefreshIslandVentureInfoReq",
    "GetGuideRewardReq",
))

DEFAULT_INITIAL_CABINS = [
    {
        "type": cabin_type,
        "level": 1,
        "extend_grade": 1,
        "level_up_end_time": 0,
        "tech_list": [],
    }
    for cabin_type in range(1, 10)
]


def _ensure_cabin_list(account):
    player_level = account.get("main", {}).get("level", 39)
    if "cabin_list" not in account or not account["cabin_list"]:
        account["cabin_list"] = deepcopy(DEFAULT_INITIAL_CABINS)

    existing_types = {c["type"] for c in account["cabin_list"]}
    for ctype in range(1, 10):
        if ctype not in existing_types:
            account["cabin_list"].append({
                "type": ctype,
                "level": 1,
                "extend_grade": 1,
                "level_up_end_time": 0,
                "tech_list": [],
            })

    levels = _load_cabin_level_data()
    for cabin in account["cabin_list"]:
        ctype = cabin.get("type")
        if cabin.get("level", 0) < 1:
            row = next((r for r in levels if r.get("cabinType") == ctype and r.get("level") == 1), None)
            need_lvl = row.get("playerLevelNeed", 1) if row else 1
            if player_level >= need_lvl:
                cabin["level"] = 1

    return account["cabin_list"]


def _load_cabin_level_data():
    try:
        path = stage.TABLE_DIRECTORY / "cabinleveldata"
        if not path.exists():
            path = Path(__file__).resolve().parent / ".local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/cabinleveldata"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _get_guide_reward(guide_id):
    try:
        tutorials = stage._table("tutorialdata")
        guide_row = next((r for r in tutorials if r.get("id") == guide_id), None)
        if not guide_row:
            return 0, 0, []
        reward_id = guide_row.get("Reward", 0)
        if not reward_id:
            return 0, 0, []
        rewards = stage._table("rewarddata")
        reward_row = next((r for r in rewards if r.get("RewardID") == reward_id), None)
        if not reward_row:
            return 0, 0, []
        scoin = reward_row.get("RewardSCoin", 0)
        hcoin = reward_row.get("RewardHCoin", 0)
        items = []
        for i in range(1, 6):
            item_id = reward_row.get(f"RewardItem{i}ID", 0)
            item_num = reward_row.get(f"RewardItem{i}Num", 0)
            item_level = reward_row.get(f"RewardItem{i}Level", 0) or 1
            if item_id and item_num:
                items.append({"id": item_id, "level": item_level, "num": item_num})
        return scoin, hcoin, items
    except Exception:
        return 0, 0, []


MUTATION_REQUESTS = frozenset((
    "LevelUpCabinReq",
    "FinishCabinLevelUpReq",
    "SpeedUpIslandCabinReq",
    "ExtendCabinReq",
    "AddCabinTechReq",
    "ResetCabinTechReq",
    "IslandCollectReq",
    "DispatchIslandVentureReq",
    "RefreshIslandVentureReq",
    "SpeedUpIslandVentureReq",
    "CancelDispatchIslandVentureReq",
    "GetIslandVentureRewardReq",
    "GetGuideRewardReq",
))


def _get_speed_up_price(remain_seconds):
    if remain_seconds <= 0:
        return 0
    if remain_seconds <= 60:
        return 1
    if remain_seconds <= 3600:
        return 12
    if remain_seconds <= 86400:
        return 162
    if remain_seconds <= 604800:
        return 497
    return 1740


def _calc_collect_scoin(collect_data, collect_level=1, now=None):
    now = now or int(time.time())
    last_time = collect_data.get("last_collect_time", now)
    elapsed = max(0, now - last_time)

    # 18,000 scoin per hour base (5 scoin/sec) for offline single-player comfort
    rate = 5.0 * (1.0 + 0.1 * max(0, collect_level - 1))
    max_storage = 5000 + max(0, collect_level - 1) * 1000
    min_interval = 30

    if elapsed < min_interval:
        scoin = 0
        next_add = last_time + min_interval
    else:
        scoin = min(max_storage, int(elapsed * rate))
        next_add = now + min_interval

    return scoin, next_add


def _get_collect_data(account):
    now = int(time.time())
    data = account.setdefault("collect_cabin", {})
    if "last_collect_time" not in data:
        data["last_collect_time"] = now - 3600
        data["scoin"] = 5000
        data["next_add_time"] = now + 30
    return data


def _venture_level(account):
    cabin = next((c for c in account.get("cabin_list", []) if c["type"] == 5), None)
    unlock = next(r for r in stage._table("cabinleveldata")
                  if r["cabinType"] == 5 and r["level"] == 1)
    if not cabin or not cabin.get("level") or account["main"]["level"] < unlock["playerLevelNeed"]:
        return None
    return next((r for r in stage._table("venturecabinbasedata")
                 if r["level"] == cabin["level"]), None)


def _venture_refresh_count(account):
    if account.get("venture_refresh_day") != clock.game_date().isoformat():
        return 0
    return account.get("venture_refresh_times", 0)


def _venture_refresh_price(level, count):
    prices = stage._table("cabinventurerefreshdata", field="level", identities=(count + 1,))
    return prices[0][f'Type{level["refreshType"]}'][0] if prices else None


def _venture_offers(account):
    """Send table identities. The native client owns display and status."""
    level = _venture_level(account)
    if level is None:
        return []
    unlocked = {(r["level"], r["difficulty"]) for r in level["UnlockVentureList"]}
    offers = sorted(r["ID"] for r in stage._table("cabindispatchventuredata")
                    if (r["level"], r["difficulty"]) in unlocked)
    existing = {r["id"]: r for r in account.get("venture_list", [])}
    rows = [dict(row) for row in existing.values() if row.get("end_time")]
    if offers:
        day = clock.game_date().toordinal()
        offset = (day + _venture_refresh_count(account)) % len(offers)
        offers = offers[offset:] + offers[:offset]
    for identity in offers:
        if len(rows) >= level["maxVentureNumBase"]:
            break
        if identity not in existing or not existing[identity].get("end_time"):
            rows.append({"id": identity, "end_time": 0})
    return rows


def _venture_snapshot(account):
    return "GetIslandVentureRsp", {
        "retcode": 0, "venture_list": _venture_offers(account),
        "is_all": True, "refresh_times": _venture_refresh_count(account),
    }


def notification_snapshot(account, command=None):
    cabins = _ensure_cabin_list(account)
    materials = [deepcopy(m) for m in account.get("material_list", [])]
    snapshots = [
        ("GetIslandRsp", {
            "retcode": 0,
            "cabin_list": deepcopy(cabins),
            "help_num": account.get("island_help_num", 0),
        }),
        ("GetMainDataRsp", {"retcode": 0, **deepcopy(account["main"])}),
        ("GetEquipmentDataRsp", {
            "retcode": 0,
            "weapon_list": deepcopy(account.get("weapon_list", [])),
            "stigmata_list": deepcopy(account.get("stigmata_list", [])),
            "material_list": materials,
        }),
    ]
    if command in ("DispatchIslandVentureReq", "CancelDispatchIslandVentureReq",
                   "RefreshIslandVentureReq", "SpeedUpIslandVentureReq", "GetIslandVentureRewardReq"):
        snapshots.append(_venture_snapshot(account))
    if command == "IslandCollectReq" or "collect_cabin" in account:
        collect_cabin = next((c for c in cabins if c.get("type") == 3), None)
        collect_level = collect_cabin.get("level", 1) if collect_cabin else 1
        collect_data = account.get("collect_cabin", {})
        scoin, next_add = _calc_collect_scoin(collect_data, collect_level)
        snapshots.append(("GetCollectCabinRsp", {
            "retcode": 0,
            "add_scoin": scoin,
            "next_add_time": next_add,
            "drop_item_list": [],
        }))
    return snapshots


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    request_values = request_values or {}
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()

    if request_name == "GetIslandVentureReq":
        with stage._transaction_lock(path):
            current = stage._read(path, account)
            stage._sync(account, current)
            return _venture_snapshot(current)

    if request_name == "GetCollectCabinReq":
        with stage._transaction_lock(path):
            before = stage._read(path, account)
            current = deepcopy(before)
            cabins = _ensure_cabin_list(current)
            collect_cabin = next((c for c in cabins if c.get("type") == 3), None)
            collect_level = collect_cabin.get("level", 0) if collect_cabin else 0
            if collect_level >= 1:
                collect_data = current.setdefault("collect_cabin", {})
                if "last_collect_time" not in collect_data:
                    collect_data["last_collect_time"] = int(time.time()) - 3600
                scoin, next_add = _calc_collect_scoin(collect_data, collect_level)
                collect_data["scoin"] = scoin
                collect_data["next_add_time"] = next_add
                stage._save(path, before, current)
                stage._sync(account, current)
                return "GetCollectCabinRsp", {
                    "retcode": 0,
                    "add_scoin": scoin,
                    "next_add_time": next_add,
                    "drop_item_list": [],
                }
            stage._sync(account, before)
            return "GetCollectCabinRsp", {
                "retcode": 0,
                "add_scoin": 0,
                "drop_item_list": [],
            }

    if request_name == "GetIslandVisitRecordReq":
        return "GetIslandVisitRecordRsp", {
            "retcode": 0,
            "record_list": [],
        }

    if request_name == "GetFriendIslandReq":
        target_uid = request_values.get("target_uid", 0)
        return "GetFriendIslandRsp", {
            "retcode": 0,
            "target_uid": target_uid,
            "target_cabin_list": [
                {"type": 1, "level": 1, "extend_grade": 1},
                {"type": 3, "level": 1, "extend_grade": 1},
                {"type": 4, "level": 1, "extend_grade": 1},
                {"type": 5, "level": 1, "extend_grade": 1},
            ],
            "target_like_num": 10,
            "is_can_like": True,
            "event_id": 0,
            "help_num": 0,
            "is_can_be_help": False,
        }

    if request_name == "LikeFriendIslandReq":
        return "LikeFriendIslandRsp", {"retcode": 0}

    if request_name == "HelpFriendIslandReq":
        return "HelpFriendIslandRsp", {"retcode": 0}

    if request_name == "GetIslandEventReq":
        return "GetIslandEventRsp", {
            "retcode": 0,
            "avatar_pos_list": [],
        }

    if request_name == "FinishIslandEventReq":
        return "FinishIslandEventRsp", {"retcode": 0}

    if request_name == "GetRefreshIslandVentureInfoReq":
        with stage._transaction_lock(path):
            current = stage._read(path, account)
            level = _venture_level(current)
            price = _venture_refresh_price(level, _venture_refresh_count(current)) if level else None
            return "GetRefreshIslandVentureInfoRsp", ({"retcode": 1} if price is None else
                                                      {"retcode": 0, "refresh_price": price})

    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        cabins = _ensure_cabin_list(current)

        if request_name == "GetIslandReq":
            if before.get("cabin_list") != current.get("cabin_list"):
                stage._save(path, before, current)
            stage._sync(account, current)
            return "GetIslandRsp", {
                "retcode": 0,
                "cabin_list": deepcopy(cabins),
                "help_num": current.get("island_help_num", 0),
            }

        if request_name == "GetGuideRewardReq":
            guide_id = request_values.get("guide_id", 0)
            guide_list = current.setdefault("guide_id_list", [])
            already_done = guide_id in guide_list

            scoin, hcoin, items = _get_guide_reward(guide_id)

            if not already_done:
                guide_list.append(guide_id)
                if guide_id == 9083:
                    for gid in (9081, 9082, 9083):
                        if gid not in guide_list:
                            guide_list.append(gid)
                guide_list.sort()

                if scoin:
                    main_data = current.setdefault("main", {})
                    main_data["scoin"] = main_data.get("scoin", 0) + scoin
                if hcoin:
                    main_data = current.setdefault("main", {})
                    main_data["hcoin"] = main_data.get("hcoin", 0) + hcoin
                if items:
                    materials = current.setdefault("material_list", [])
                    for it in items:
                        mat = next((m for m in materials if m.get("id") == it["id"]), None)
                        if mat:
                            mat["num"] = mat.get("num", 0) + it["num"]
                        else:
                            materials.append({"id": it["id"], "num": it["num"]})

                stage._save(path, before, current)
                stage._sync(account, current)

            reward_list = []
            if (scoin or hcoin or items) and not already_done:
                reward_list.append({
                    "exp": 0,
                    "scoin": scoin,
                    "hcoin": hcoin,
                    "stamina": 0,
                    "skill_point": 0,
                    "friends_point": 0,
                    "item_list": items,
                    "duty_point": 0,
                })
            return "GetGuideRewardRsp", {"retcode": 0, "reward_list": reward_list}

        if request_name == "LevelUpCabinReq":
            cabin_type = request_values.get("cabin_type")
            target = next((c for c in cabins if c.get("type") == cabin_type), None)
            if target is None:
                stage._sync(account, before)
                return "LevelUpCabinRsp", {"retcode": 1}

            next_level = target.get("level", 0) + 1
            levels = _load_cabin_level_data()
            row = next((r for r in levels if r.get("cabinType") == cabin_type and r.get("level") == next_level), None)
            up_time = row.get("upLevelTimeNeed", 0) if row else 3
            scoin_need = row.get("scoinNeed", 0) if row else 0
            items_need = row.get("itemListNeed", []) if row else []

            main_data = current.setdefault("main", {})
            current_scoin = main_data.get("scoin", 0)
            if current_scoin < scoin_need:
                stage._sync(account, before)
                return "LevelUpCabinRsp", {"retcode": 1}

            materials = current.setdefault("material_list", [])
            for req_item in items_need:
                item_id = req_item.get("itemMetaID", 0)
                item_num = req_item.get("itemNum", 0)
                if item_id and item_num > 0:
                    mat = next((m for m in materials if m.get("id") == item_id), None)
                    if mat and mat.get("num", 0) >= item_num:
                        mat["num"] -= item_num

            main_data["scoin"] = current_scoin - scoin_need
            target["level_up_end_time"] = int(time.time()) + up_time

            stage._save(path, before, current)
            stage._sync(account, current)
            return "LevelUpCabinRsp", {"retcode": 0}

        if request_name == "FinishCabinLevelUpReq":
            cabin_type = request_values.get("cabin_type")
            target = next((c for c in cabins if c.get("type") == cabin_type), None)
            if target is None:
                stage._sync(account, before)
                return "FinishCabinLevelUpRsp", {"retcode": 1}

            now = int(time.time())
            end_time = target.get("level_up_end_time", 0)
            if end_time > now:
                remain_seconds = end_time - now
                price = _get_speed_up_price(remain_seconds)
                main_data = current.setdefault("main", {})
                current_hcoin = main_data.get("hcoin", 0)
                main_data["hcoin"] = max(0, current_hcoin - price)

            target["level"] = target.get("level", 0) + 1
            target["level_up_end_time"] = 0

            stage._save(path, before, current)
            stage._sync(account, current)
            return "FinishCabinLevelUpRsp", {"retcode": 0}

        if request_name == "SpeedUpIslandCabinReq":
            cabin_id = request_values.get("cabin_id")
            material_id = request_values.get("material_id", 0)
            num = request_values.get("num", 1)
            target = next((c for c in cabins if c.get("type") == cabin_id), None)
            if target is not None:
                now = int(time.time())
                end_time = target.get("level_up_end_time", now)
                if material_id:
                    materials = current.setdefault("material_list", [])
                    mat = next((m for m in materials if m.get("id") == material_id), None)
                    if mat and mat.get("num", 0) >= num:
                        mat["num"] -= num
                    target["level_up_end_time"] = max(now, end_time - num * 1800)
                else:
                    remain_seconds = max(0, end_time - now)
                    price = _get_speed_up_price(remain_seconds)
                    main_data = current.setdefault("main", {})
                    main_data["hcoin"] = max(0, main_data.get("hcoin", 0) - price)
                    target["level_up_end_time"] = now

            stage._save(path, before, current)
            stage._sync(account, current)
            return "SpeedUpIslandCabinRsp", {"retcode": 0}

        if request_name == "ExtendCabinReq":
            cabin_type = request_values.get("cabin_type")
            target = next((c for c in cabins if c.get("type") == cabin_type), None)
            if target is None:
                stage._sync(account, before)
                return "ExtendCabinRsp", {"retcode": 1}

            target["extend_grade"] = target.get("extend_grade", 1) + 1

            stage._save(path, before, current)
            stage._sync(account, current)
            return "ExtendCabinRsp", {"retcode": 0}

        if request_name == "AddCabinTechReq":
            cabin_type = request_values.get("cabin_type")
            pos_x = request_values.get("pos_x", 0)
            pos_y = request_values.get("pos_y", 0)
            target = next((c for c in cabins if c.get("type") == cabin_type), None)
            if target is None:
                stage._sync(account, before)
                return "AddCabinTechRsp", {"retcode": 1}

            tech_list = target.setdefault("tech_list", [])
            if not any(t.get("pos_x") == pos_x and t.get("pos_y") == pos_y for t in tech_list):
                tech_list.append({"pos_x": pos_x, "pos_y": pos_y})

            stage._save(path, before, current)
            stage._sync(account, current)
            return "AddCabinTechRsp", {"retcode": 0}

        if request_name == "ResetCabinTechReq":
            cabin_type = request_values.get("cabin_type")
            target = next((c for c in cabins if c.get("type") == cabin_type), None)
            if target is None:
                stage._sync(account, before)
                return "ResetCabinTechRsp", {"retcode": 1}

            target["tech_list"] = []

            stage._save(path, before, current)
            stage._sync(account, current)
            return "ResetCabinTechRsp", {"retcode": 0}

        if request_name == "IslandCollectReq":
            cabins = _ensure_cabin_list(current)
            collect_cabin = next((c for c in cabins if c.get("type") == 3), None)
            collect_level = collect_cabin.get("level", 0) if collect_cabin else 0
            if collect_level < 1:
                stage._sync(account, before)
                return "IslandCollectRsp", {"retcode": 1}

            collect_data = current.setdefault("collect_cabin", {})
            if "last_collect_time" not in collect_data:
                collect_data["last_collect_time"] = int(time.time()) - 3600

            scoin, _ = _calc_collect_scoin(collect_data, collect_level)
            add_scoin = scoin
            now = int(time.time())
            collect_data["last_collect_time"] = now
            collect_data["scoin"] = 0
            collect_data["next_add_time"] = now + 30

            main_data = current.setdefault("main", {})
            main_data["scoin"] = main_data.get("scoin", 0) + add_scoin

            stage._save(path, before, current)
            stage._sync(account, current)
            return "IslandCollectRsp", {
                "retcode": 0,
                "add_scoin": add_scoin,
                "is_extra": False,
                "drop_item_list": [],
            }

        if request_name in ("DispatchIslandVentureReq", "CancelDispatchIslandVentureReq"):
            response_name = request_name[:-3] + "Rsp"
            rejected = response_name, {"retcode": 1}
            level = _venture_level(current)
            if level is None:
                return rejected
            venture_id = request_values.get("venture_id")
            if type(venture_id) is not int:
                return rejected
            meta = next((r for r in stage._table("cabindispatchventuredata")
                         if r["ID"] == venture_id), None)
            if meta is None:
                return rejected
            ventures = current.setdefault("venture_list", [])
            existing = next((v for v in ventures if v["id"] == venture_id and v.get("end_time")), None)
            stamina = current["main"]["stamina"]
            now = int(time.time())
            result = {"retcode": 0}
            if request_name == "DispatchIslandVentureReq":
                if existing or venture_id not in {v["id"] for v in _venture_offers(current)}:
                    return rejected
                if sum(v.get("end_time", 0) > now for v in ventures) >= level["maxVentureInProgressNumBase"]:
                    return rejected
                avatars = request_values.get("avatar_id_list", [])
                owned = {a["avatar_id"] for a in current["avatar_list"] if a.get("star", 0) > 0}
                if (not isinstance(avatars, list) or not 1 <= len(avatars) <= meta["avatarMaxNum"]
                        or any(type(i) is not int or i not in owned for i in avatars)
                        or len(avatars) != len(set(avatars)) or stamina < meta["staminaCost"]):
                    return rejected
                busy = set()
                for row in ventures:
                    if row.get("end_time", 0) > now:
                        assigned = row.get("avatar_id", [])
                        busy.update(assigned if isinstance(assigned, list) else [assigned])
                if busy.intersection(avatars):
                    return rejected
                ventures[:] = [row for row in ventures if row["id"] != venture_id]
                ventures.append({"id": venture_id, "avatar_id": avatars,
                                 "end_time": now + meta["timeCost"]})
                current["main"]["stamina"] -= meta["staminaCost"]
                current.get("venture_claim_receipts", {}).pop(str(venture_id), None)
            else:
                if not existing or existing["end_time"] <= now:
                    return rejected
                from server19_exchange import STAMINA_SYSTEM_LIMIT
                # Native GetStaminaReturnOnCancel uses floor(cost * remaining / duration).
                remaining = min(existing["end_time"] - now, meta["timeCost"])
                refund = meta["staminaCost"] * remaining // meta["timeCost"]
                refund = min(refund, max(0, STAMINA_SYSTEM_LIMIT - stamina))
                ventures.remove(existing)
                current["main"]["stamina"] += refund
                result["add_stamina"] = refund
            import server19_protocol as proto
            proto.encode_message(response_name, result)
            proto.encode_message(*_venture_snapshot(current))
            stage._save(path, before, current)
            stage._sync(account, current)
            return response_name, result

        if request_name in ("RefreshIslandVentureReq", "SpeedUpIslandVentureReq",
                            "GetIslandVentureRewardReq"):
            response_name = request_name[:-3] + "Rsp"
            try:
                result = _venture_finish_action(current, request_name, request_values)
                if result is None:
                    return response_name, {"retcode": 1}
                import server19_protocol as proto
                proto.encode_message(response_name, result)
                for packet in notification_snapshot(current, command=request_name):
                    proto.encode_message(*packet)
                stage._save(path, before, current)
            except (ValueError, TypeError, KeyError, IndexError, OSError):
                return response_name, {"retcode": 1}
            stage._sync(account, current)
            return response_name, result

    return None


def _venture_finish_action(account, command, values):
    level = _venture_level(account)
    if level is None:
        return None
    main = account["main"]
    if command == "RefreshIslandVentureReq":
        count = _venture_refresh_count(account)
        price = _venture_refresh_price(level, count)
        if price is None or main["hcoin"] < price:
            return None
        main["hcoin"] -= price
        account["venture_refresh_day"] = clock.game_date().isoformat()
        account["venture_refresh_times"] = count + 1
        return {"retcode": 0}

    identity = stage._u32(values.get("venture_id"), "venture id")
    ventures = account.get("venture_list", [])
    active = next((row for row in ventures if row["id"] == identity and row.get("end_time")), None)
    if active is None:
        if command == "GetIslandVentureRewardReq":
            return deepcopy(account.get("venture_claim_receipts", {}).get(str(identity)))
        return None
    now = int(time.time())
    if command == "SpeedUpIslandVentureReq":
        item = stage._u32(values.get("material_id"), "speed-up material")
        count = stage._u32(values.get("num"), "speed-up quantity")
        rows = stage._table("materialventurespeedupdata", field="MaterialID", identities=(item,))
        stacks = [row for row in account.get("material_list", []) if row["id"] == item]
        if active["end_time"] <= now or len(rows) != 1 or len(stacks) != 1 or not 0 < count <= stacks[0]["num"]:
            return None
        stacks[0]["num"] -= count
        active["end_time"] = max(now - 1, active["end_time"] - count * rows[0]["SpeedUpTime"])
        return {"retcode": 0}

    if active["end_time"] > now:
        return None
    meta, = stage._table("cabindispatchventuredata", field="ID", identities=(identity,))
    reward, = stage._table("rewarddata", field="RewardID", identities=(meta["rewardId"],))
    exp = stage._u32(reward["RewardExp"], "venture experience")
    coins = stage._u32(reward["RewardSCoin"], "venture coins")
    if any(value for key, value in reward.items() if key not in ("RewardID", "RewardExp", "RewardSCoin")):
        return None
    main["scoin"] = stage._u32(main["scoin"] + coins, "venture coin balance")
    import server19_player_progression
    progression = server19_player_progression.grant_player_exp(main, exp)
    coins += progression.get("cap_exp_conversion", {}).get("scoin", 0)
    # Local compatibility policy: one uniformly chosen material from the
    # task preview. Learning chips are items, distinct from captain EXP.
    candidates = []
    for item in dict.fromkeys(meta["rewardItemShowList"]):
        rows = stage._table("materialdata", field="ID", identities=(item,))
        if not rows:
            continue
        row, = rows
        candidates.append((item, row["rarity"]))
    drops = []
    if candidates:
        item, rarity = secrets.choice(candidates)
        stage._grant_drops(account, {(item, 0): 1})
        drops.append({"item_id": item, "level": 0, "num": 1, "rarity": rarity})
    ventures.remove(active)
    result = {"retcode": 0, "reward_list": [{"exp": exp, "scoin": coins}],
              "drop_item_list": drops, "succ_type": 0}
    account.setdefault("venture_claim_receipts", {})[str(identity)] = deepcopy(result)
    return result
