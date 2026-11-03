"""Cabin and Island base operations, building level-up, extension, and persistence."""
from copy import deepcopy
import json
from pathlib import Path
import time

import server19_business_clock as clock
import server19_stage as stage

HANDLED_REQUESTS = frozenset((
    "GetIslandReq",
    "LevelUpCabinReq",
    "FinishCabinLevelUpReq",
    "SpeedUpIslandCabinReq",
    "ExtendCabinReq",
    "AddCabinTechReq",
    "ResetCabinTechReq",
    "IslandCollectReq",
    "GetCollectCabinReq",
    "IslandDisjoinEquipmentReq",
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
        return "GetRefreshIslandVentureInfoRsp", {
            "retcode": 0,
            "refresh_times": 0,
            "next_refresh_time": clock.day_bounds()[1],
        }

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

        if request_name == "IslandDisjoinEquipmentReq":
            stage._sync(account, before)
            return "IslandDisjoinEquipmentRsp", {"retcode": 0}

        if request_name == "DispatchIslandVentureReq":
            venture_id = request_values.get("venture_id", 0)
            avatar_id_list = request_values.get("avatar_id_list", [])
            ventures = current.setdefault("venture_list", [])
            existing = next((v for v in ventures if v.get("id") == venture_id), None)
            if existing:
                existing["end_time"] = int(time.time()) + 300
                existing["avatar_id"] = avatar_id_list[0] if avatar_id_list else 101
            else:
                ventures.append({
                    "id": venture_id,
                    "end_time": int(time.time()) + 300,
                    "avatar_id": avatar_id_list[0] if avatar_id_list else 101,
                })
            stage._save(path, before, current)
            stage._sync(account, current)
            return "DispatchIslandVentureRsp", {"retcode": 0}

        if request_name == "CancelDispatchIslandVentureReq":
            venture_id = request_values.get("venture_id", 0)
            ventures = current.setdefault("venture_list", [])
            current["venture_list"] = [v for v in ventures if v.get("id") != venture_id]
            stage._save(path, before, current)
            stage._sync(account, current)
            return "CancelDispatchIslandVentureRsp", {"retcode": 0}

        if request_name == "GetIslandVentureRewardReq":
            venture_id = request_values.get("venture_id", 0)
            ventures = current.setdefault("venture_list", [])
            current["venture_list"] = [v for v in ventures if v.get("id") != venture_id]
            stage._save(path, before, current)
            stage._sync(account, current)
            return "GetIslandVentureRewardRsp", {
                "retcode": 0,
                "reward_list": [],
                "drop_item_list": [],
                "succ_type": 1,
            }

    return None
