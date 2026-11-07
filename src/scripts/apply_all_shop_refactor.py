
import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META_DIR = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"
ACCOUNT_PATH = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json"

print("================ STARTING SHOP REFACTOR ================")

# ----------------------------------------------------
# 1. Dress Unlock: Unlock all 46 dresses for all avatars
# ----------------------------------------------------
print("\n[Step 1] Unlocking all dresses in account.json...")
dress_path = META_DIR / "dressdata"
with open(dress_path, "r", encoding="utf-8") as f:
    dresses = json.load(f)

avatar_to_dresses = {}
all_dress_ids = []
for d in dresses:
    did = d["dressID"]
    all_dress_ids.append(did)
    for aid in d.get("avatarIDList", []):
        avatar_to_dresses.setdefault(aid, []).append(did)

if ACCOUNT_PATH.exists():
    with open(ACCOUNT_PATH, "r", encoding="utf-8") as f:
        acc = json.load(f)
    
    # Add dresses to each avatar
    for av in acc.get("avatar_list", []):
        aid = av.get("avatar_id")
        current_dresses = set(av.get("dress_list", []))
        applicable = avatar_to_dresses.get(aid, [])
        for did in applicable:
            current_dresses.add(did)
        av["dress_list"] = sorted(list(current_dresses))
    
    # Add to has_got_item_id_list
    has_got = set(acc.setdefault("has_got_item_id_list", []))
    for did in all_dress_ids:
        has_got.add(did)
    acc["has_got_item_id_list"] = sorted(list(has_got))
    
    with open(ACCOUNT_PATH, "w", encoding="utf-8") as f:
        json.dump(acc, f, ensure_ascii=False, indent=2)
    print(f"  -> Successfully unlocked {len(all_dress_ids)} dresses across {len(acc.get('avatar_list', []))} avatars.")


# ----------------------------------------------------
# 2. Refine Event Shop (Shop 7) & Expand Exchange House (Shop 6)
# ----------------------------------------------------
print("\n[Step 2] Filtering Event items & expanding Exchange House with weapons...")
with open(META_DIR / "shopgoodsdata", "r", encoding="utf-8") as f:
    shopgoods = json.load(f)
goods_map = {g["ID"]: g for g in shopgoods}

with open(META_DIR / "materialdata", "r", encoding="utf-8") as f:
    mats = {m["ID"]: m for m in json.load(f)}
with open(META_DIR / "weapondata", "r", encoding="utf-8") as f:
    wpns = {w["ID"]: w for w in json.load(f)}
with open(META_DIR / "stigmatadata", "r", encoding="utf-8") as f:
    stgs = {s["ID"]: s for s in json.load(f)}

# Find core 4-star weapons for Exchange House
exchange_wpn_goods = []
for g in shopgoods:
    iid = g.get("ItemID")
    if iid in wpns:
        w = wpns[iid]
        if w.get("maxRarity", 1) >= 5 and w.get("rarity", 1) >= 4:
            exchange_wpn_goods.append(g["ID"])
# De-duplicate while preserving order
exchange_wpn_goods = sorted(list(set(exchange_wpn_goods)))
print(f"  Found {len(exchange_wpn_goods)} core 4-star weapon goods for Exchange House.")

# Existing 65 valid stigmata in Shop 6
old_config = json.load(open(ROOT / "server19_shop_config.json", "r", encoding="utf-8"))
old_s6 = [s for s in old_config if s["shop_id"] == 6][0]
s6_pool = sorted(list(set(old_s6["goods_pool"] + exchange_wpn_goods)))
print(f"  Exchange House combined pool: {len(s6_pool)} items (stigmata + weapons).")

# Update shopgoodsdata prices: All Shop 6 items = 6000 HCoin, 0 SCoin, 0 token
s6_set = set(s6_pool)
for g in shopgoods:
    if g["ID"] in s6_set:
        g["HCoinCost"] = 6000
        g["SCoinCost"] = 0
        for i in range(1, 6):
            g[f"CostItemId{i}"] = 0
            g[f"CostItemNum{i}"] = 0

# Refine Event Shop (Shop 7):
# Filter out 1-2 star garbage equipment and basic mats (exp chips, evo mats)
# Keep only event tokens (7002, 7030, etc.), event medals, festival boxes, 4-star event stigmata
event_token_ids = {
    7002, 7004, 7005, 7008, 7012, 7013, 7016, 7028, 7029, 7030, 7031, 7032,
    7041, 7042, 7043, 7044, 7045, 7051, 7052, 7058, 7059, 7091, 7092, 7093,
    7094, 7095, 7121, 7151, 7152, 7155, 7156, 7157, 7158, 7163, 7173, 7174,
    7175, 7176, 7177, 7200, 7203, 7205, 7207, 7208, 7210, 7227, 905, 9101
}

old_s7 = [s for s in old_config if s["shop_id"] == 7][0]
s7_refined_pool = []
for gid in old_s7["goods_pool"]:
    g = goods_map.get(gid)
    if not g:
        continue
    iid = g.get("ItemID")
    # Keep if it is an event token / medal / box
    if iid in event_token_ids:
        s7_refined_pool.append(gid)
    # Keep if it is a 4-star event stigmata
    elif iid in stgs and stgs[iid].get("rarity", 1) >= 4:
        s7_refined_pool.append(gid)
    # Keep if it is an event special weapon (3-4 star)
    elif iid in wpns and wpns[iid].get("rarity", 1) >= 3 and "event" in wpns[iid].get("iconPath", "").lower():
        s7_refined_pool.append(gid)

# De-duplicate
s7_refined_pool = sorted(list(set(s7_refined_pool)))
print(f"  Event Shop refined from {len(old_s7['goods_pool'])} items down to {len(s7_refined_pool)} pure memorial items.")

# Set Shop 7 prices to 1 SCoin
s7_set = set(s7_refined_pool)
for g in shopgoods:
    if g["ID"] in s7_set:
        g["SCoinCost"] = 1
        g["HCoinCost"] = 0
        for i in range(1, 6):
            g[f"CostItemId{i}"] = 0
            g[f"CostItemNum{i}"] = 0

# Write updated shopgoodsdata
meta_targets = [
    META_DIR / "shopgoodsdata",
    ROOT / "server19-run/metadata-device/_exceloutputasset/shopgoodsdata",
]
for t in meta_targets:
    if t.parent.exists():
        with open(t, "w", encoding="utf-8") as f:
            json.dump(shopgoods, f, ensure_ascii=False, indent=2)
print("  -> shopgoodsdata successfully updated.")


# ----------------------------------------------------
# 3. New 5-Shop Configuration (Non-conflicting ShopTypes & Real Icons)
# ----------------------------------------------------
print("\n[Step 3] Building 5-Shop configuration with unique ShopTypes...")
old_s1 = [s for s in old_config if s["shop_id"] == 1][0]
old_s2 = [s for s in old_config if s["shop_id"] == 2][0]
old_s3 = [s for s in old_config if s["shop_id"] == 3][0]

new_shops_config = [
    {
        "shop_id": 1,
        "shop_type": 1,  # SHOP_NORMAL
        "shop_name": "常见材料",
        "text_map_name": "Shop_Common_Materials",
        "shop_icon_path": "SpriteOutput/MaterialIcons/1001",
        "currency_list": [],
        "goods_pool": old_s1["goods_pool"],
    },
    {
        "shop_id": 2,
        "shop_type": 5,  # SHOP_ARMADA (Distinct from 1 to avoid dict key collision!)
        "shop_name": "角色碎片",
        "text_map_name": "Shop_Avatar_Fragments",
        "shop_icon_path": "SpriteOutput/AvatarFragmentIcons/10101",
        "currency_list": [],
        "goods_pool": old_s2["goods_pool"],
    },
    {
        "shop_id": 3,
        "shop_type": 2,  # SHOP_ENDLESS
        "shop_name": "高级军备",
        "text_map_name": "Shop_Advanced_Equip",
        "shop_icon_path": "SpriteOutput/MaterialIcons/9004",
        "currency_list": [],
        "goods_pool": old_s3["goods_pool"],
    },
    {
        "shop_id": 7,
        "shop_type": 3,  # SHOP_ACTIVITY
        "shop_name": "活动纪念",
        "text_map_name": "Shop_Event_Limited",
        "shop_icon_path": "SpriteOutput/MaterialIcons/7002",
        "currency_list": [],
        "goods_pool": s7_refined_pool,
    },
    {
        "shop_id": 6,
        "shop_type": 7,  # SHOP_EXCHANGE_HOUSE
        "shop_name": "置换空间",
        "text_map_name": "Shop_Exchange_House",
        "shop_icon_path": "SpriteOutput/MaterialIcons/8004",
        "currency_list": [],
        "is_refreshable": True,
        "display_count": 8,
        "goods_pool": s6_pool,
    },
]

with open(ROOT / "server19_shop_config.json", "w", encoding="utf-8") as f:
    json.dump(new_shops_config, f, ensure_ascii=False, indent=2)
print(f"  -> Written 5 clean shops to server19_shop_config.json.")


# ----------------------------------------------------
# 4. Textmap additions for DropWay
# ----------------------------------------------------
print("\n[Step 4] Updating textmap with DropWay links and shop names...")
textmap_paths = [
    ROOT / ".local-baseline/server19-dev/sony-human-fixes-v1/textmap",
    META_DIR / "textmap",
]

NEW_TEXTS = {
    "Shop_Common_Materials": "常见材料",
    "Shop_Avatar_Fragments": "角色碎片",
    "Shop_Advanced_Equip": "高级军备",
    "Shop_Event_Limited": "活动纪念",
    "Shop_Exchange_House": "置换空间",
    "DropWay_CommonShop": "前往【常见材料商店】直接获取",
    "DropWay_FragmentShop": "前往【角色碎片商店】直接获取",
}

for tp in textmap_paths:
    if tp.exists():
        with open(tp, "r", encoding="utf-8") as f:
            tm = json.load(f)
        tm = [row for row in tm if row["ID"] not in NEW_TEXTS]
        for k, v in NEW_TEXTS.items():
            tm.append({"ID": k, "Text": v})
        with open(tp, "w", encoding="utf-8") as f:
            json.dump(tm, f, ensure_ascii=False, indent=2)
        print(f"  -> Updated {tp} with {len(NEW_TEXTS)} localized keys.")


# ----------------------------------------------------
# 5. Populate materialdata comeFromList
# ----------------------------------------------------
print("\n[Step 5] Injecting comeFromList in materialdata for smooth navigation...")
raw_mat_path = META_DIR / "materialdata"
with open(raw_mat_path, "r", encoding="utf-8") as f:
    raw_materials = json.load(f)

common_mat_tag = '<type="17|1" text="DropWay_CommonShop"/>'
injected_count = 0
for m in raw_materials:
    cfl = m.setdefault("comeFromList", [])
    if common_mat_tag not in cfl:
        # Prepend so it is the first primary option
        cfl.insert(0, common_mat_tag)
        injected_count += 1

mat_targets = [
    raw_mat_path,
    ROOT / ".local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset/materialdata",
    ROOT / "server19-run/metadata-device/_exceloutputasset/materialdata",
]
for mt in mat_targets:
    if mt.parent.exists():
        with open(mt, "w", encoding="utf-8") as f:
            json.dump(raw_materials, f, ensure_ascii=False, indent=2)
print(f"  -> Injected common shop link into {injected_count} materials across {len(mat_targets)} paths.")

print("\n================ REFACTOR COMPLETED SUCCESSFULLY ================")
