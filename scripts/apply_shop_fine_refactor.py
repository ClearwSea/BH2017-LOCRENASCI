
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
TEXTMAP_PATH = ROOT / ".local-baseline/server19-dev/sony-human-fixes-v1/textmap"

print("================ PREPARING SHOP FINE REFACTOR ================")

# Load tables
with open(META_DIR / "shopgoodsdata", "r", encoding="utf-8") as f:
    raw_shopgoods = json.load(f)
shopgoods = [g for g in raw_shopgoods if g["ID"] < 900000]
goods_by_id = {g["ID"]: g for g in shopgoods}

alloc_counter = 900000
def alloc_gid():
    global alloc_counter
    alloc_counter += 1
    return alloc_counter

with open(META_DIR / "materialdata", "r", encoding="utf-8") as f:
    materials = {m["ID"]: m for m in json.load(f)}

with open(META_DIR / "avatarfragmentdata", "r", encoding="utf-8") as f:
    frags = {fr["ID"]: fr for fr in json.load(f)}

with open(META_DIR / "weapondata", "r", encoding="utf-8") as f:
    weapons = {w["ID"]: w for w in json.load(f)}

with open(META_DIR / "stigmatadata", "r", encoding="utf-8") as f:
    stigmatas = {s["ID"]: s for s in json.load(f)}

with open(META_DIR / "avatardata", "r", encoding="utf-8") as f:
    avatars = {a["avatarID"]: a for a in json.load(f)}

with open(TEXTMAP_PATH, "r", encoding="utf-8") as f:
    textmap = {item["ID"]: item["Text"] for item in json.load(f)}

def get_name(item):
    return textmap.get(item.get("displayTitle"), textmap.get(item.get("name"), ""))

# Identify S-rank fragments vs non-S fragments
s_rank_frag_ids = {
    10103,  # 白骑士·月光
    10204,  # 雷电女王的鬼铠
    10212,  # 御神装·勿忘
    10304,  # 次元边界突破
    10312,  # 异度黑核侵蚀
    10404,  # 血色玫瑰
    10502,  # 处刑装·紫苑
    10504,  # 神恩颂歌
}

print(f"Total valkyrie fragments: {len(frags)}")
print(f"S-rank fragments count: {len(s_rank_frag_ids)}")

# -------------------------------------------------------------------------
# 1. Build Shop 2: 角色碎片 (Exactly 26 unique fragments, 1 goods per frag)
# -------------------------------------------------------------------------
shop2_goods_pool = []
frag_to_goods = {}
for g in shopgoods:
    iid = g.get("ItemID")
    if iid in frags and iid not in frag_to_goods:
        frag_to_goods[iid] = g["ID"]

# Handle missing fragments (10112, 10212, 10312, 10504)
new_goods_to_add = []
for fid in frags:
    if fid not in frag_to_goods:
        new_gid = alloc_gid()
        new_g = {
            "ID": new_gid,
            "ItemID": fid,
            "ItemLevel": 1,
            "ItemNum": 1,
            "HCoinCost": 100 if fid in s_rank_frag_ids else 0,
            "SCoinCost": 0 if fid in s_rank_frag_ids else 20000,
            "CostItemId1": 0, "CostItemNum1": 0,
            "CostItemId2": 0, "CostItemNum2": 0,
            "CostItemId3": 0, "CostItemNum3": 0,
            "CostItemId4": 0, "CostItemNum4": 0,
            "CostItemId5": 0, "CostItemNum5": 0,
            "MaxBuyTimes": 9999,
            "PriceRateID": 1,
            "Discount": 10000,
            "IsSuperWorth": 0,
        }
        new_goods_to_add.append(new_g)
        goods_by_id[new_gid] = new_g
        frag_to_goods[fid] = new_gid

for fid in sorted(frags.keys()):
    gid = frag_to_goods[fid]
    g = goods_by_id[gid]
    g["ItemNum"] = 1
    g["ItemLevel"] = 1
    g["MaxBuyTimes"] = 9999
    if fid in s_rank_frag_ids:
        g["HCoinCost"] = 100
        g["SCoinCost"] = 0
    else:
        g["HCoinCost"] = 0
        g["SCoinCost"] = 20000
    for i in range(1, 6):
        g[f"CostItemId{i}"] = 0
        g[f"CostItemNum{i}"] = 0
    shop2_goods_pool.append(gid)

print(f"Shop 2 (角色碎片): {len(shop2_goods_pool)} items configured (8 S-rank for 100 Crystal, 18 non-S for 20k Coins).")

# -------------------------------------------------------------------------
# 2. Build Shop 6: 置换空间 (De-duplicate pool by ItemID, 6000 Crystals)
# -------------------------------------------------------------------------
# Load previous shop 6 pool
old_config = json.load(open(ROOT / "server19_shop_config.json", "r", encoding="utf-8"))
old_s6 = [s for s in old_config if s["shop_id"] == 6][0]

s6_seen_item_ids = set()
shop6_goods_pool = []
for gid in old_s6["goods_pool"]:
    g = goods_by_id.get(gid)
    if not g:
        continue
    iid = g["ItemID"]
    # Only 4-star weapons or stigmata
    is_valid = (iid in weapons and weapons[iid].get("rarity", 1) >= 4) or \
               (iid in stigmatas and stigmatas[iid].get("rarity", 1) >= 4)
    if is_valid and iid not in s6_seen_item_ids:
        s6_seen_item_ids.add(iid)
        g["ItemNum"] = 1
        g["HCoinCost"] = 6000
        g["SCoinCost"] = 0
        for i in range(1, 6):
            g[f"CostItemId{i}"] = 0
            g[f"CostItemNum{i}"] = 0
        g["MaxBuyTimes"] = 9999
        shop6_goods_pool.append(gid)

print(f"Shop 6 (置换空间): {len(shop6_goods_pool)} unique 4-star weapons and stigmata configured (6000 Crystal each).")

# -------------------------------------------------------------------------
# 3. Build Shop 7: 活动纪念 (Pure Event items: 1 SCoin, Base form only, No junk)
# -------------------------------------------------------------------------
evolved_wpn_ids = set(w.get("evoID") for w in weapons.values() if w.get("evoID"))
evolved_stg_ids = set(s.get("evoID") for s in stigmatas.values() if s.get("evoID"))

EXCLUDED_EVENT_ITEM_IDS = {
    7104,   # 服装兑换券
    7039,   # 普通崩坏碎片 x5
    7084,   # 时空封印箱子
    3107,   # 督学勋章
    9010,   # 联合勋章
    1001, 1002, 1003, 1004,  # 普通经验芯片
    20640,  # 天火原型重复项
}

event_item_candidates = set()

# 1. Event weapons: only base forms, exclude non-event standard weapons
for wid, w in weapons.items():
    if wid in evolved_wpn_ids or wid in EXCLUDED_EVENT_ITEM_IDS:
        continue
    name = get_name(w)
    if any(k in name for k in ['水妖精', '火妖精', '轩辕剑', '黑轩辕', '地藏御魂', '太虚', '樱花誓约', '茶茶']):
        continue
    if any(k in name for k in ['天火', '爱酱', '咸鱼', '原罪']):
        event_item_candidates.add(wid)

# 2. Event stigmata: only base forms
for sid, s in stigmatas.items():
    if sid in evolved_stg_ids or sid in EXCLUDED_EVENT_ITEM_IDS:
        continue
    name = get_name(s)
    if any(k in name for k in ['黑轩辕', '茶茶', '碎片']):
        continue
    if any(k in name for k in ['公主', '泳装', '清凉', '圣诞', '傲慢', '七夕', '旗袍', '一周年', '歌姬', '花嫁', '中秋', '万圣']):
        event_item_candidates.add(sid)

# 3. Event materials/medals
for mid, m in materials.items():
    if mid in EXCLUDED_EVENT_ITEM_IDS:
        continue
    name = get_name(m)
    if any(k in name for k in ['督学', '联合', '时空封印', '碎片', '经验']):
        continue
    if mid in (7046, 7047, 7112) or any(k in name for k in ['礼盒', '粽', '月饼', '蛋糕', '刨冰', '夏日回忆', '清凉糖果', '一周年']):
        event_item_candidates.add(mid)

event_item_candidates -= EXCLUDED_EVENT_ITEM_IDS
print(f"Total pure event candidate item IDs: {len(event_item_candidates)}")

# Map candidates to shop goods (de-duplicate by ItemID)
s7_seen_item_ids = set()
shop7_goods_pool = []

for g in shopgoods:
    iid = g["ItemID"]
    if iid in event_item_candidates and iid not in s7_seen_item_ids:
        if iid in s6_seen_item_ids:
            continue
        s7_seen_item_ids.add(iid)
        g["ItemNum"] = 1
        g["SCoinCost"] = 1
        g["HCoinCost"] = 0
        for i in range(1, 6):
            g[f"CostItemId{i}"] = 0
            g[f"CostItemNum{i}"] = 0
        g["MaxBuyTimes"] = 9999
        shop7_goods_pool.append(g["ID"])

# Create goods for remaining event items if missing
for iid in sorted(event_item_candidates):
    if iid not in s7_seen_item_ids and iid not in s6_seen_item_ids:
        new_gid = alloc_gid()
        new_g = {
            "ID": new_gid,
            "ItemID": iid,
            "ItemLevel": 1,
            "ItemNum": 1,
            "HCoinCost": 0,
            "SCoinCost": 1,
            "CostItemId1": 0, "CostItemNum1": 0,
            "CostItemId2": 0, "CostItemNum2": 0,
            "CostItemId3": 0, "CostItemNum3": 0,
            "CostItemId4": 0, "CostItemNum4": 0,
            "CostItemId5": 0, "CostItemNum5": 0,
            "MaxBuyTimes": 9999,
            "PriceRateID": 1,
            "Discount": 10000,
            "IsSuperWorth": 0,
        }
        new_goods_to_add.append(new_g)
        goods_by_id[new_gid] = new_g
        s7_seen_item_ids.add(iid)
        shop7_goods_pool.append(new_gid)

print(f"Shop 7 (活动纪念): {len(shop7_goods_pool)} refined event items configured (1 Coin each).")

# -------------------------------------------------------------------------
# 4. Build Shop 3: 高级军备 (方向 A: 降临装备 + 3星实用过渡装备, 金币出售)
# -------------------------------------------------------------------------
ADVENT_PRACTICAL_KEYWORDS = [
    '餐刀', '清汤', '吞噬', '合金', '降临', '水妖精Ⅰ', '火妖精Ⅰ', '马尔科夫', '电磁手枪', '阴极子', '试作',
    '暴食', '复仇', '支配', '狡黠', '暴风', '迦尼萨', '龙马', '查理曼', '阿提拉', '特斯拉', '伊丽莎白', '奥托', '爱迪生', '薇拉'
]

shop3_goods_pool = []
s3_seen_item_ids = set()

for g in shopgoods:
    iid = g["ItemID"]
    if iid in s6_seen_item_ids or iid in s7_seen_item_ids or iid in frags:
        continue
    # Must be weapon or stigmata
    is_wpn = iid in weapons
    is_stg = iid in stigmatas
    if not (is_wpn or is_stg):
        continue

    item_obj = weapons.get(iid) or stigmatas.get(iid)
    name = get_name(item_obj)
    rarity = item_obj.get("rarity", 1)

    # Direction A: Advent equipment or 3-star practical equipment
    is_match = any(k in name for k in ADVENT_PRACTICAL_KEYWORDS) or rarity == 3
    if is_match and iid not in s3_seen_item_ids:
        s3_seen_item_ids.add(iid)
        g["ItemNum"] = 1
        g["HCoinCost"] = 0
        g["SCoinCost"] = 200000 if rarity >= 4 else 50000
        for i in range(1, 6):
            g[f"CostItemId{i}"] = 0
            g[f"CostItemNum{i}"] = 0
        g["MaxBuyTimes"] = 9999
        shop3_goods_pool.append(g["ID"])

print(f"Shop 3 (高级军备): {len(shop3_goods_pool)} unique advent & 3-star practical equipment configured (Gold Coins).")

# -------------------------------------------------------------------------
# 5. Build Shop 1: 常见材料 (All materials, de-duplicated by ItemID, x1, unlimited)
# -------------------------------------------------------------------------
shop1_goods_pool = []
s1_seen_item_ids = set()

for g in shopgoods:
    iid = g["ItemID"]
    if iid not in materials:
        continue
    # Exclude event medals and tokens already in Shop 7
    if iid in s7_seen_item_ids:
        continue
    if iid in EXCLUDED_EVENT_ITEM_IDS:
        continue

    if iid not in s1_seen_item_ids:
        s1_seen_item_ids.add(iid)
        # Price: Keep sensible gold coin cost (1000 - 5000)
        old_cost = g.get("SCoinCost", 1000)
        g["ItemNum"] = 1
        g["HCoinCost"] = 0
        g["SCoinCost"] = max(500, min(old_cost, 10000))
        for i in range(1, 6):
            g[f"CostItemId{i}"] = 0
            g[f"CostItemNum{i}"] = 0
        g["MaxBuyTimes"] = 9999
        shop1_goods_pool.append(g["ID"])

print(f"Shop 1 (常见材料): {len(shop1_goods_pool)} unique cultivation materials configured (x1, unlimited).")

# -------------------------------------------------------------------------
# Save updated shopgoodsdata & server19_shop_config.json
# -------------------------------------------------------------------------
all_final_goods = shopgoods + new_goods_to_add
with open(META_DIR / "shopgoodsdata", "w", encoding="utf-8") as f:
    json.dump(all_final_goods, f, ensure_ascii=False, indent=2)

new_config = [
    {
        "shop_id": 1,
        "shop_type": 1,
        "shop_name": "常见材料",
        "text_map_name": "Shop_Common_Materials",
        "shop_icon_path": "SpriteOutput/MaterialIcons/1001",
        "currency_list": [],
        "is_refreshable": False,
        "goods_pool": shop1_goods_pool,
    },
    {
        "shop_id": 2,
        "shop_type": 5,
        "shop_name": "角色碎片",
        "text_map_name": "Shop_Avatar_Fragments",
        "shop_icon_path": "SpriteOutput/AvatarFragmentIcons/10101",
        "currency_list": [],
        "is_refreshable": False,
        "goods_pool": shop2_goods_pool,
    },
    {
        "shop_id": 3,
        "shop_type": 2,
        "shop_name": "高级军备",
        "text_map_name": "Shop_Advanced_Equip",
        "shop_icon_path": "SpriteOutput/MaterialIcons/9004",
        "currency_list": [],
        "is_refreshable": False,
        "goods_pool": shop3_goods_pool,
    },
    {
        "shop_id": 7,
        "shop_type": 3,
        "shop_name": "活动纪念",
        "text_map_name": "Shop_Event_Limited",
        "shop_icon_path": "SpriteOutput/MaterialIcons/7002",
        "currency_list": [],
        "is_refreshable": False,
        "goods_pool": shop7_goods_pool,
    },
    {
        "shop_id": 6,
        "shop_type": 7,
        "shop_name": "置换空间",
        "text_map_name": "Shop_Exchange_House",
        "shop_icon_path": "SpriteOutput/MaterialIcons/8004",
        "currency_list": [],
        "is_refreshable": True,
        "display_count": 8,
        "goods_pool": shop6_goods_pool,
    },
]

with open(ROOT / "server19_shop_config.json", "w", encoding="utf-8") as f:
    json.dump(new_config, f, ensure_ascii=False, indent=2)

print("\n================ SHOP FINE REFACTOR COMPLETE ================")
