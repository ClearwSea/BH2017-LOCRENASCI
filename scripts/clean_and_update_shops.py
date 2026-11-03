
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
META_DIR = ROOT / ".local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset"
corrected_meta = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"

def load_table(name, id_key="ID"):
    p1 = META_DIR / name
    p2 = corrected_meta / name
    p = p1 if p1.exists() else p2
    with open(p, "r", encoding="utf-8") as f:
        return {item[id_key]: item for item in json.load(f)}

goods_table = load_table("shopgoodsdata")
mats = load_table("materialdata")
wpns = load_table("weapondata")
stgs = load_table("stigmatadata")
frags = load_table("avatarfragmentdata")
dresses = load_table("dressdata", "dressID")

all_valid_items = set(mats.keys()) | set(wpns.keys()) | set(stgs.keys()) | set(frags.keys()) | set(dresses.keys())

TEXT_MAP_NAMES = {
    1: "Shop_Common_Materials",
    2: "Shop_Avatar_Fragments",
    3: "Shop_Advanced_Equip",
    4: "Shop_Costume_Store",
    5: "Shop_Open_World",
    6: "Shop_Exchange_House",
    7: "Shop_Event_Limited",
    8: "Shop_Gacha_Cards",
}

config_path = ROOT / "server19_shop_config.json"
with open(config_path, "r", encoding="utf-8") as f:
    shops_config = json.load(f)

# 1. Clean up pools and set text_map_name
cleaned_shops = []
shop6_valid_ids = set()
shop7_valid_ids = set()

for s in shops_config:
    sid = s["shop_id"]
    old_pool = s.get("goods_pool", [])
    new_pool = []
    for gid in old_pool:
        meta = goods_table.get(gid)
        if not meta:
            continue
        item_id = meta.get("ItemID")
        if item_id in all_valid_items:
            new_pool.append(gid)
    s["goods_pool"] = new_pool
    s["text_map_name"] = TEXT_MAP_NAMES[sid]
    s["currency_list"] = []  # Keep currency_list empty to avoid MonoShopStoreTab NRE
    cleaned_shops.append(s)
    if sid == 6:
        shop6_valid_ids = set(new_pool)
    elif sid == 7:
        shop7_valid_ids = set(new_pool)
    print("Shop %d (%s, text_map_name=%s): %d -> %d goods" % (
        sid, s.get("shop_name"), s.get("text_map_name"), len(old_pool), len(new_pool)
    ))

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(cleaned_shops, f, ensure_ascii=False, indent=2)

# 2. Modify shopgoodsdata
shopgoods_raw_path = corrected_meta / "shopgoodsdata"
with open(shopgoods_raw_path, "r", encoding="utf-8") as f:
    shopgoods_list = json.load(f)

shop6_modified = 0
shop7_modified = 0
for row in shopgoods_list:
    gid = row.get("ID")
    if gid in shop6_valid_ids:
        row["HCoinCost"] = 6000
        row["SCoinCost"] = 0
        for i in range(1, 6):
            row["CostItemId%d" % i] = 0
            row["CostItemNum%d" % i] = 0
        shop6_modified += 1
    elif gid in shop7_valid_ids:
        row["SCoinCost"] = 1
        row["HCoinCost"] = 0
        for i in range(1, 6):
            row["CostItemId%d" % i] = 0
            row["CostItemNum%d" % i] = 0
        shop7_modified += 1

# Write to metadata paths
meta_targets = [
    corrected_meta / "shopgoodsdata",
    ROOT / "server19-run/metadata-device/_exceloutputasset/shopgoodsdata",
]
for target in meta_targets:
    if target.parent.exists():
        with open(target, "w", encoding="utf-8") as f:
            json.dump(shopgoods_list, f, ensure_ascii=False, indent=2)
        print("Wrote updated shopgoodsdata to %s (Shop 6 updated: %d, Shop 7 updated: %d)" % (
            target, shop6_modified, shop7_modified
        ))
