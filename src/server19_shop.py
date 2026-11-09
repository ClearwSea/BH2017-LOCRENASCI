"""Shop (Store) handlers for Server 19.

Implements the 8 shop categories:
1. 常见材料商店 (Common Materials)
2. 角色碎片商店 (Avatar Fragments)
3. 高级军备商店 (Advanced Equipment & Materials)
4. 服装商城 (Fashion / Costumes)
5. 开放世界商店 (Open World Materials)
6. 置换空间 (Exchange House - Infinite Manual Refresh & Crystal Pricing)
7. 限时活动商店 (Limited Event Items - 1 SCoin)
8. 补给兑换商店 (Gacha Cards)
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import time

import server19_avatar_fragments as fragments
import server19_business_clock as clock
import server19_stage as stage

HANDLED_REQUESTS = frozenset((
    "GetShopListReq",
    "BuyGoodsReq",
    "ManualRefreshShopReq",
))

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "server19_shop_config.json"
META_DIR = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"

def reload_config():
    global SHOPS_CONFIG, GOODS_METADATA, MATERIALS_TABLE, WEAPONS_TABLE, STIGMATAS_TABLE, AVATAR_FRAGS_TABLE, DRESSES_TABLE
    SHOPS_CONFIG = []
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            SHOPS_CONFIG = json.load(f)

    GOODS_METADATA = {}
    shopgoods_path = META_DIR / "shopgoodsdata"
    if shopgoods_path.exists():
        with open(shopgoods_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                GOODS_METADATA[item["ID"]] = item

    MATERIALS_TABLE = {}
    mat_path = META_DIR / "materialdata"
    if mat_path.exists():
        with open(mat_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                MATERIALS_TABLE[item["ID"]] = item

    WEAPONS_TABLE = {}
    wpn_path = META_DIR / "weapondata"
    if wpn_path.exists():
        with open(wpn_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                WEAPONS_TABLE[item["ID"]] = item

    STIGMATAS_TABLE = {}
    stg_path = META_DIR / "stigmatadata"
    if stg_path.exists():
        with open(stg_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                STIGMATAS_TABLE[item["ID"]] = item

    AVATAR_FRAGS_TABLE = {}
    frag_path = META_DIR / "avatarfragmentdata"
    if frag_path.exists():
        with open(frag_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                AVATAR_FRAGS_TABLE[item["ID"]] = item

    DRESSES_TABLE = {}
    dress_path = META_DIR / "dressdata"
    if dress_path.exists():
        with open(dress_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                DRESSES_TABLE[item["dressID"]] = item

reload_config()


def _is_supported_item(item_id):
    return any(item_id in table for table in (
        MATERIALS_TABLE, AVATAR_FRAGS_TABLE, WEAPONS_TABLE, STIGMATAS_TABLE, DRESSES_TABLE))


def _goods_pool(shop):
    """Use actual item tables: 1xxxx includes valid avatar fragments."""
    return [gid for gid in shop.get("goods_pool", [])
            if gid in GOODS_METADATA and _is_supported_item(GOODS_METADATA[gid]["ItemID"])]


def _get_shop_runtime(account, now=None):
    """Retrieve or initialize persistent shop runtime in account."""
    if "shop_runtime" not in account:
        account["shop_runtime"] = {
            "exchange_house_goods": [],
            "buy_records": {},  # str(goods_id) -> buy_times
            "last_refresh_time": int(time.time()),
        }
    runtime = account["shop_runtime"]
    day = clock.day_key(now)
    previous = runtime.setdefault("day_key", clock.day_key(runtime.get("last_refresh_time", clock.local_now(now).timestamp())))
    if day > previous:
        runtime.setdefault("buy_record_archive", []).append({"day_key": previous, "buy_records": runtime.get("buy_records", {})})
        runtime["buy_records"], runtime["exchange_house_goods"] = {}, []
        runtime["last_refresh_time"] = clock.day_bounds(now)[0]
        runtime["day_key"] = day

    # Initialize exchange house goods if empty
    pool = []
    for s in SHOPS_CONFIG:
        if s["shop_id"] == 6:
            pool = _goods_pool(s)
            break

    current_shelf = runtime.get("exchange_house_goods", [])
    # Re-validate shelf goods against pool
    valid_shelf = [gid for gid in current_shelf if gid in pool]
    if len(valid_shelf) < 8 and len(pool) > 0:
        count = min(8, len(pool))
        runtime["exchange_house_goods"] = random.sample(pool, count)
    else:
        runtime["exchange_house_goods"] = valid_shelf
    return runtime


def _grant_item(account, item_id, num, level=1):
    """Grant purchased item to player account."""
    # 0. Dress -> avatar dress_list & has_got_item_id_list
    if item_id in DRESSES_TABLE:
        dress_meta = DRESSES_TABLE[item_id]
        avatar_ids = dress_meta.get("avatarIDList", [])
        for av in account.get("avatar_list", []):
            if av.get("avatar_id") in avatar_ids:
                dlist = av.setdefault("dress_list", [])
                if item_id not in dlist:
                    dlist.append(item_id)
        has_got = account.setdefault("has_got_item_id_list", [])
        if item_id not in has_got:
            has_got.append(item_id)
        return

    # Native fragment storage reads avatar.fragment, not material_list.
    if item_id in AVATAR_FRAGS_TABLE:
        materials = account.get("material_list", [])
        legacy_count = sum(row.get("num", 0) for row in materials if row.get("id") == item_id)
        fragments.grant(account, item_id, 0, num + legacy_count)
        account["material_list"] = [row for row in materials if row.get("id") != item_id]
        return

    # 1. Material -> material_list
    if item_id in MATERIALS_TABLE:
        materials = account.setdefault("material_list", [])
        for row in materials:
            if row.get("id") == item_id:
                row["num"] = row.get("num", 0) + num
                return
        materials.append({"id": item_id, "num": num})
        return

    # 2. Weapon -> weapon_list
    if item_id in WEAPONS_TABLE:
        weapons = account.setdefault("weapon_list", [])
        all_uids = [row["unique_id"] for name in ("weapon_list", "stigmata_list")
                    for row in account.get(name, [])]
        uid = max([v for v in all_uids if v < 20000], default=0) + 1
        if (len(all_uids) != len(set(all_uids)) or uid >= 20000 or uid in all_uids
                or any(not 0 < row["unique_id"] < 20000 for row in weapons)):
            raise ValueError("Invalid or exhausted native equipment UID range")
        weapons.append({
            "unique_id": uid,
            "id": item_id,
            "level": max(1, level),
            "exp": 0,
            "is_protected": False,
        })
        return

    # 3. Stigmata -> stigmata_list
    if item_id in STIGMATAS_TABLE:
        stigmatas = account.setdefault("stigmata_list", [])
        all_uids = [row["unique_id"] for name in ("weapon_list", "stigmata_list")
                    for row in account.get(name, [])]
        uid = max([v for v in all_uids if v >= 20000], default=20000) + 1
        if (len(all_uids) != len(set(all_uids)) or uid >= 40000 or uid in all_uids
                or any(not 20000 < row["unique_id"] < 40000 for row in stigmatas)):
            raise ValueError("Invalid or exhausted native equipment UID range")
        stigmatas.append({
            "unique_id": uid,
            "id": item_id,
            "level": max(1, level),
            "exp": 0,
            "is_protected": False,
        })
        return

    raise ValueError(f"Unsupported shop item: {item_id}")


def build_shop_list_payload(account, now=None):
    """Build proto.GetShopListRsp payload dict from account and configuration."""
    if now is None:
        now = int(time.time())
    runtime = _get_shop_runtime(account, now)
    shop_list = []
    for s in SHOPS_CONFIG:
        sid = s["shop_id"]
        stype = s["shop_type"]
        sname = s["shop_name"]
        currency_list = s.get("currency_list", [])
        goods_pool = _goods_pool(s)
        text_map_name = s.get("text_map_name", "")

        is_refreshable = s.get("is_refreshable", False)
        # Determine active shelf goods
        if sid == 6:  # 置换空间
            shelf_ids = runtime.get("exchange_house_goods", [])
        else:
            shelf_ids = goods_pool

        goods_list = []
        for gid in shelf_ids:
            if is_refreshable:
                buy_cnt = runtime.get("buy_records", {}).get(str(gid), 0)
            else:
                buy_cnt = 0  # 常驻商店无限出售，永不计限购
            goods_list.append({
                "goods_id": gid,
                "buy_times": buy_cnt,
                "can_be_refresh": is_refreshable,
                "refresh_time_type": 1,
            })

        shop_list.append({
            "shop_id": sid,
            "is_open": True,
            "shop_name": sname,
            "shop_type": stype,
            "unlock_level": 1,
            "currency_list": currency_list,
            "next_auto_refresh_time": clock.day_bounds(now)[1] if is_refreshable else 0,
            "manual_refresh_times": 0,
            "max_manual_refresh_times": 9999 if is_refreshable else 0,
            "next_refresh_cost": 0,
            "all_goods_id_list": goods_pool,
            "goods_list": goods_list,
            "is_hot": False,
            "is_double_confirm": False,
            "shop_icon_path": s.get("shop_icon_path", ""),
            "text_map_name": text_map_name,
        })

    return {
        "retcode": 0,
        "shop_list": shop_list,
    }


def get_shop_list_rsp(account, account_path=None):
    """Helper to return a ('GetShopListRsp', payload) tuple."""
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    if path.exists():
        try:
            with stage._transaction_lock(path):
                before = stage._read(path, account)
                current = deepcopy(before)
                payload = build_shop_list_payload(current)
                stage._save(path, before, current)
                stage._sync(account, current)
                return "GetShopListRsp", payload
        except Exception:
            pass
    return "GetShopListRsp", build_shop_list_payload(account)


def response(name, account, request_values=None, *, account_path=None):
    if name not in HANDLED_REQUESTS:
        return None

    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()

    # 1. GetShopListReq
    if name == "GetShopListReq":
        if path.exists():
            try:
                with stage._transaction_lock(path):
                    before = stage._read(path, account)
                    current = deepcopy(before)
                    payload = build_shop_list_payload(current)
                    stage._save(path, before, current)
                    stage._sync(account, current)
                    return "GetShopListRsp", payload
            except Exception:
                return "GetShopListRsp", build_shop_list_payload(account)
        return "GetShopListRsp", build_shop_list_payload(account)

    # 2. ManualRefreshShopReq
    if name == "ManualRefreshShopReq":
        sid = request_values.get("shop_id", 0) if request_values else 0
        with stage._transaction_lock(path):
            current = stage._read(path, account)
            runtime = _get_shop_runtime(current)

            # Find shop config
            target_shop = None
            for s in SHOPS_CONFIG:
                if s["shop_id"] == sid:
                    target_shop = s
                    break

            if target_shop and target_shop.get("is_refreshable"):
                pool = _goods_pool(target_shop)
                count = min(target_shop.get("display_count", 8), len(pool))
                before = deepcopy(current)
                runtime["exchange_house_goods"] = random.sample(pool, count) if count > 0 else []
                stage._save(path, before, current)
                stage._sync(account, current)

            return "ManualRefreshShopRsp", {"retcode": 0}

    # 3. BuyGoodsReq
    if name == "BuyGoodsReq":
        if not request_values:
            return "BuyGoodsRsp", {"retcode": 1}

        sid = request_values.get("shop_id", 0)
        gid = request_values.get("goods_id", 0)

        meta = GOODS_METADATA.get(gid)
        target_shop = next((s for s in SHOPS_CONFIG if s["shop_id"] == sid), None)
        if not meta or target_shop is None or gid not in _goods_pool(target_shop):
            return "BuyGoodsRsp", {"retcode": 1}

        with stage._transaction_lock(path):
            current = stage._read(path, account)
            before = deepcopy(current)
            runtime = _get_shop_runtime(current)
            if sid == 6 and gid not in runtime.get("exchange_house_goods", []):
                return "BuyGoodsRsp", {"retcode": 1}
            main = current.setdefault("main", {})

            # Pricing rules
            if sid == 6:  # 置换空间: 等量水晶 (6000 水晶)
                scoin_cost = 0
                hcoin_cost = 6000
                cost_items = []
            elif sid == 7:  # 限时活动: 全场 1 金币
                scoin_cost = 1
                hcoin_cost = 0
                cost_items = []
            else:
                scoin_cost = meta.get("SCoinCost", 0)
                hcoin_cost = meta.get("HCoinCost", 0)
                cost_items = []
                for i in range(1, 6):
                    cid = meta.get(f"CostItemId{i}", 0)
                    cnum = meta.get(f"CostItemNum{i}", 0)
                    if cid > 0 and cnum > 0:
                        cost_items.append((cid, cnum))

            # Balance checks
            if main.get("scoin", 0) < scoin_cost:
                return "BuyGoodsRsp", {"retcode": 2}  # SCoin not enough
            if main.get("hcoin", 0) < hcoin_cost:
                return "BuyGoodsRsp", {"retcode": 2}  # HCoin not enough

            # Check materials/tokens
            materials = current.setdefault("material_list", [])
            for cid, cnum in cost_items:
                owned = sum(row.get("num", 0) for row in materials if row.get("id") == cid)
                if owned < cnum:
                    return "BuyGoodsRsp", {"retcode": 2}  # Material token not enough

            # Deduct costs
            main["scoin"] = max(0, main.get("scoin", 0) - scoin_cost)
            main["hcoin"] = max(0, main.get("hcoin", 0) - hcoin_cost)
            for cid, cnum in cost_items:
                remain = cnum
                for row in materials:
                    if row.get("id") == cid:
                        deduct = min(row.get("num", 0), remain)
                        row["num"] -= deduct
                        remain -= deduct
                        if remain <= 0:
                            break

            # Grant items
            item_id = meta["ItemID"]
            num = meta.get("ItemNum", 1)
            if sid == 1:
                num = 100
            level = meta.get("ItemLevel", 1)
            try:
                _grant_item(current, item_id, num, level)
            except ValueError:
                # current is a transaction copy: neither costs nor legacy fragments persist.
                return "BuyGoodsRsp", {"retcode": 1}

            # Record buy count (only for refreshable Exchange House)
            if sid == 6:
                buy_records = runtime.setdefault("buy_records", {})
                buy_records[str(gid)] = buy_records.get(str(gid), 0) + 1
                curr_buy_times = buy_records[str(gid)]
            else:
                curr_buy_times = 0

            # Save state
            stage._save(path, before, current)
            stage._sync(account, current)

            return "BuyGoodsRsp", {
                "retcode": 0,
                "shop_id": sid,
                "goods_id": gid,
                "goods_buy_times": curr_buy_times,
                "item_id": item_id,
                "level": max(1, level),
                "num": num,
            }

    return None
