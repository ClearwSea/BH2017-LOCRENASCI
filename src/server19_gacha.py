"""Native 1.9 supply ("补给") transactions.

Recovered from the original client (1.9.0 x86 IL2CPP metadata):

* proto.GachaType (type 2020) field defaults give the wire values used here:
  1 GACHA_FRIENDS_POINT, 2 GACHA_HCOIN, 3 GACHA_SPECIAL_HCOIN,
  4 GACHA_ACTIVITY, 5..7 GACHA_CUSTOM_1..3, 8 GACHA_BOX, 9 GACHA_UNIQUE,
  10 GACHA_EQUIP_HCOIN, 100 GACHA_TYPE_ERROR.
* proto.GachaRsp.Retcode (type 2860): SUCC/FAIL/FRIENDS_POINT_LACK/
  TICKET_LACK/EQUIPMENT_FULL/GACHA_CLOSED/HCOIN_LACK/EQUIPMENT_MATERIAL_LIMIT/
  EQUIPMENT_FRAGMENT_LIMIT/MAX_TIMES_LIMIT. networkerrcodedata carries the
  original text for each, so these values are the client's own.
* NetworkManager::RequestGacha 73012 @0x1158b69 builds
  GachaReq{type, num, gacha_random = GachaModule.GachaRandom, is_use_hcoin}
  and returns without sending when GachaRandom is zero. The seed therefore has
  to be non-zero in GetGachaDisplayRsp for the buttons to do anything.
* GachaModule::IsGachaDataExpired 68942 treats a channel as expired only when
  its data_expire_time is *specified* and in the past; a channel with no
  expire time never expires. This server omits the two time fields entirely
  rather than sending zero, which would mark every channel expired.
* GachaMainPageContext::IsTabOpen 78597 opens a tab exactly when its display
  object is present, and GetHcoinGachaDataByType 78596 resolves type 10 from
  hcoin_noup_gacha_data_list[0] and everything else from hcoin_gacha_data.
* gachaentrancemanage names the tabs (标配-女武神 / 标配-装备 / 友情扭蛋 / ...)
  and textmap Textmap_Gacha1Desc_2/10/6 carry the pool descriptions used below.
* materialdata ItemType "gacha_item" holds the supply tickets:
  1101 标配补给卡, 1105 装备补给卡. The 2.4 demo's own GetGachaDisplayRsp
  sample also pairs the hcoin channel with ticket 1101.
* basicconfig_GachaUnlockNeedPlayerLevel = 9 matches the entrance table's
  UnlockLevel, and the client applies it itself.

NOT recovered: the original pool composition and its probabilities. They lived
in a supply table the client never shipped and that no capture in this
repository contains (the client only ever received the pool from the server and
rendered it). PULL_TABLE below is an authored compatibility pool, not
historical drop probability, and is kept in one place so it can be replaced if
real data ever surfaces. Item identity is restricted to the deployed tables'
own rows intersected with the audited equipment-eligibility classes, so every
grantable item is one this 1.9 client can actually project.

Published channels include standard avatar/equipment, friendship, the authored
Ziyuan expansion and its focused equipment supply. Other activity/box/unique
channels remain absent. Historical completeness is recorded in developer docs.
"""
from copy import deepcopy
import json
from pathlib import Path
import random
import time

import server19_protocol as proto
import server19_stage as stage

HANDLED_REQUESTS = frozenset(("GetGachaDisplayReq", "GachaReq",
                              "GetGachaLogReq", "GetGachaProbReq",
                              "BuyGachaTicketReq"))

# Requests that change the wallet or the item list. Their own responses carry
# neither (BuyGachaTicketRsp has only material_id/num/hcoin_cost, GachaRsp only
# the drawn items), so the caller must follow them with notification_snapshot;
# without it the supply page keeps showing the pre-purchase ticket count and
# crystal balance, which reads as "nothing happened".
MUTATION_REQUESTS = frozenset(("GachaReq", "BuyGachaTicketReq"))

GACHA_FRIENDS_POINT = 1
GACHA_HCOIN = 2
GACHA_EQUIP_HCOIN = 10
GACHA_ZIYUAN = 5
GACHA_ZIYUAN_EQUIP = 3
ZIYUAN_EQUIP_PERIOD = 'ziyuan-bloodembrace-dracula-v1'
ZIYUAN_WEAPON = 20464
ZIYUAN_STIGMATA = (30629,30633,30637)
# Local partial banner: 2018-01-12 announcement roster, with601 withheld until
# its full dependency closure is ready. Rates below are an explicit compatible
# reconstruction, NOT the recovered probability table of this exact period.
ZIYUAN_PERIOD = 'ziyuan-20180112-local-v1'
ZIYUAN_CARD = 60502
ZIYUAN_A_CARDS = (60203, 60501, 60112)

RSP_SUCC = 0
RSP_FAIL = 1
RSP_FRIENDS_POINT_LACK = 2
RSP_TICKET_LACK = 3
RSP_EQUIPMENT_FULL = 4
RSP_HCOIN_LACK = 6
RSP_EQUIPMENT_MATERIAL_LIMIT = 7

# BuyGachaTicketRsp.Retcode (Type 3243)
BUY_TICKET_RSP_SUCC = 0
BUY_TICKET_RSP_FAIL = 1
BUY_TICKET_RSP_MATERIAL_ID_ERROR = 2
BUY_TICKET_RSP_HCOIN_LACK = 3
BUY_TICKET_RSP_EQUIPMENT_MATERIAL_LIMIT = 4

# Channel identity, cost and display text. `ticket_material_id` is the supply
# ticket the client offers to buy with hcoin when storage holds too few.
#
# Standard `image` uses the native gachaentrancemanage resource. Event images
# have separate paths and empty title_image to avoid duplicating the poster.
# These strings are
# NOT optional decoration: proto.GachaDisplayCommonData's constructor 0x1bcfa9b
# only initialises its five repeated members, so every string member stays null
# until the server sets it. GachaMainPageContext::SetupHcoinTab passes
# supply_image straight into UIUtil::SplitGachaDisplayImagePath 0x144a62b,
# which throws NullReferenceException on null (title_image, content_url and
# btn_image_path are the guarded ones). Leaving the field out crashed the 补给
# page the first time the entry became reachable.
CHANNELS = {
    GACHA_ZIYUAN: {"title_image": "", "title": "处刑装·紫苑扩充补给",
                   "content": "处刑装·紫苑获取概率提升",
                   "rule": "每次补给消耗1张扩充补给卡或280水晶。每十回补给内必出A级或以上女武神。",
                   "image": "Server19/Gacha/Ziyuan",
                   "hcoin_cost": 280, "ticket_material_id": 1103, "max_pull": 10},
    GACHA_ZIYUAN_EQUIP: {"title_image": "", "title": "精准补给",
                   "content": "仿犹大·血之拥抱、德古拉获取概率提升",
                   "rule": "每次补给消耗1张精准补给卡或280水晶。每十回补给内必出一件4星武器或圣痕。",
                   "image": "Server19/Gacha/Dracula", "hcoin_cost": 280, "ticket_material_id": 1102, "max_pull": 10},
    GACHA_HCOIN: {"title": "标配补给",
                  "content": "可获得物品：女武神、武器、圣痕、材料",
                  "rule": "每次补给消耗1张标配补给卡或280水晶。十回补给必出A级或以上女武神。",
                  "image": "SpriteOutput/GachaImg/IconZJ",
                  "hcoin_cost": 280, "ticket_material_id": 1101, "max_pull": 10},
    GACHA_EQUIP_HCOIN: {"title": "标配补给·装备",
                        "content": "可获得物品：武器、圣痕、材料",
                        "rule": "每次补给消耗1张装备补给卡或280水晶。",
                        "image": "SpriteOutput/GachaImg/IconZB",
                        "hcoin_cost": 280, "ticket_material_id": 1105, "max_pull": 10},
    GACHA_FRIENDS_POINT: {"title": "友情补给",
                          "content": "可获得物品：2-4星装备、材料",
                          "rule": "每次补给消耗10友情点。",
                          # Empty override retains the original friend-tab art;
                          # TrySetupEventSprite returns before any Image write.
                          "image": "",
                          "friends_point_cost": 10, "ticket_material_id": 0,
                          "max_pull": 10},
}

# Authored compatibility pool (see module docstring). Entries are
# (kind, rarity, weight); rarity 0 is used by materials.
#
# GACHA_HCOIN is the 1.9 standard supply, which was the "non-awakened character
# catalogue": it hands out valkyries, low-tier equipment and materials, while
# the 装备补给 channel added in 1.9 is the full-equipment pool. The valkyrie
# side is therefore limited to 2-3 star equipment here, not 4-star.
PULL_TABLE = {
    GACHA_HCOIN: (("avatar_card", 4, 100),
                  ("weapon", 3, 180), ("stigmata", 3, 200),
                  ("weapon", 2, 150), ("stigmata", 2, 170),
                  ("material", 0, 200)),
    GACHA_EQUIP_HCOIN: (("weapon", 4, 150), ("stigmata", 4, 170),
                        ("weapon", 3, 200), ("stigmata", 3, 220),
                        ("weapon", 2, 130), ("stigmata", 2, 130)),
    GACHA_FRIENDS_POINT: (("weapon", 3, 120), ("stigmata", 3, 130),
                          ("weapon", 2, 250), ("stigmata", 2, 250),
                          ("material", 0, 250)),
}

# A ten-pull whose first nine items miss the rule re-rolls the last one inside
# `tiers`; `card_min_star` additionally restricts avatar cards to that unlock
# star or above. The standard supply's "十连必出A级或以上女武神" is the rule for
# GACHA_HCOIN, so a ten-pull there always produces a valkyrie.
TEN_PULL_GUARANTEE = {
    GACHA_HCOIN: {"tiers": (("avatar_card", 4),), "card_min_star": 2},
    GACHA_EQUIP_HCOIN: {"tiers": (("weapon", 4), ("stigmata", 4))},
}

# Valkyries excluded from the standard supply.
#  * Awakened (灵魂觉醒) armours are not part of it; the client's own
#    avatarexdata table lists the six base->awakened pairs.
#  * Local period policy excludes502 and601 for the2018-01-12..01-26 banner.
#    The announcement explicitly delays601's standard-pool admission until
#    that banner ends.601 was filtered from the2.4 compatibility export by its
#    GameVersionBegin=2.0, despite native1.9 assets and CN release evidence.
#    That export omission is not evidence that the original client lacks601.
#    See docs/server19-fuka601-compatibility-20261013.md before publishing it.
BANNER_AVATAR_IDS = frozenset((502, 601))

# Materials this server is willing to hand out, with the amount per drop.
MATERIAL_POOL = ((1001, 2), (1002, 2), (2001, 1), (2002, 1),
                 (3001, 2), (3002, 2), (3003, 1))

# How many times one pull re-rolls after a grant is refused (quantity limit,
# UID exhaustion) before the channel reports a failure.
REROLL_LIMIT = 24

ELIGIBILITY = (Path(__file__).resolve().parent /
               "server19-run/equipment-eligibility-20261013/eligibility.json")
_POOLS = {}


def _eligible_ids():
    """Equipment identities this client can project, keyed (kind, rarity)."""
    report = json.loads(ELIGIBILITY.read_text(encoding="utf-8"))
    safe = {row["item_id"] for row in report["items"] if row["class"] == "safe"}
    if not safe:
        raise ValueError("Equipment eligibility audit is empty")
    pools = {}
    for name, kind in (("weapondata", "weapon"), ("stigmatadata", "stigmata")):
        for row in stage._table(name):
            if row["ID"] not in safe:
                continue
            rarity = stage._u32(row["rarity"], "equipment rarity")
            if 2 <= rarity <= 4:
                pools.setdefault((kind, rarity), []).append(row["ID"])
    for key in sorted(pools):
        pools[key] = sorted(set(pools[key]))
        if not pools[key]:
            raise ValueError("Empty supply pool tier")
    return pools


def _awakened_avatar_ids():
    """Awakened valkyries, taken from the client's own avatarexdata pairs."""
    ids = set()
    for row in stage._table("avatarexdata"):
        pair = row.get("avatarIDList") or []
        if len(pair) == 2:
            ids.add(stage._u32(pair[1], "awakened avatar id"))
    if not ids:
        raise ValueError("Awakened avatar table is empty")
    return frozenset(ids)


def _card_star(card_id):
    rows = stage._table("avatardata", field="avatarCardID", identities=(card_id,))
    return stage._u32(rows[0]["unlockStar"], "unlockStar") if rows else 0


def _pool(kind, rarity):
    """Grantable (item_id, num) options for one tier."""
    if not _POOLS:
        _POOLS.update(_eligible_ids())
    if kind == "avatar_card":
        blocked = _awakened_avatar_ids() | BANNER_AVATAR_IDS
        options = [(stage._u32(row["avatarCardID"], "avatarCardID"), 1)
                   for row in stage._table("avatardata")
                   if row.get("avatarCardID")
                   and stage._u32(row["avatarID"], "avatarID") not in blocked]
        if not options:
            raise ValueError("Standard supply has no eligible valkyrie")
        return options
    if kind == "material":
        return list(MATERIAL_POOL)
    return [(item_id, 1) for item_id in _POOLS[(kind, rarity)]]


def _table_for(channel):
    if channel == GACHA_ZIYUAN_EQUIP:
        for name, identities in (('weapondata',(ZIYUAN_WEAPON,)),('stigmatadata',ZIYUAN_STIGMATA)):
            rows = stage._table(name, field='ID', identities=identities)
            if len(rows) != len(identities) or any(row['rarity'] != 4 for row in rows):
                raise ValueError('Focused equipment identity/rarity missing')
        return ((250,'weapon',4,((ZIYUAN_WEAPON,1),)),
                (750,'stigmata',4,tuple((item,1) for item in ZIYUAN_STIGMATA)),
                (1500,'weapon',3,tuple(_pool('weapon',3))),
                (2500,'stigmata',3,tuple(_pool('stigmata',3))),
                (5000,'material',0,tuple(MATERIAL_POOL)))
    if channel == GACHA_ZIYUAN:
        # Early published rates establish1.5% S and13.5% A as a reference;
        # the omitted601 and remaining rewards make this authored partial pool.
        for card in (ZIYUAN_CARD, *ZIYUAN_A_CARDS):
            if len(stage._table('avatardata',field='avatarCardID',identities=(card,))) != 1:
                raise ValueError('Missing banner card metadata')
        return ((150,'avatar_card',4,((ZIYUAN_CARD,1),)),
                (1350,'avatar_card',4,tuple((card,1) for card in ZIYUAN_A_CARDS)),
                (750,'weapon',3,tuple(_pool('weapon',3))),
                (2250,'stigmata',3,tuple(_pool('stigmata',3))),
                (5500,'material',0,tuple(MATERIAL_POOL)))
    tiers = []
    for kind, rarity, weight in PULL_TABLE[channel]:
        options = _pool(kind, rarity)
        if channel == GACHA_FRIENDS_POINT and kind in ('weapon', 'stigmata'):
            name = 'weapondata' if kind == 'weapon' else 'stigmatadata'
            maximum = {row['ID']: row['maxRarity'] for row in stage._table(name)}
            options = [item for item in options if maximum[item[0]] <= 4]
        if options:
            tiers.append((weight, kind, rarity, tuple(options)))
    if not tiers:
        raise ValueError("Supply channel has no grantable items")
    return tuple(tiers)


def _roll(channel, *, guaranteed=None):
    """One item. `guaranteed` is a TEN_PULL_GUARANTEE rule to satisfy."""
    tiers = _table_for(channel)
    if guaranteed is not None:
        only = set(guaranteed["tiers"])
        tiers = tuple(tier for tier in tiers if (tier[1], tier[2]) in only)
        if not tiers:
            raise ValueError("Supply guarantee has no matching tier")
    min_star = (guaranteed or {}).get("card_min_star")
    for _ in range(64):
        total = sum(tier[0] for tier in tiers)
        pick = random.randrange(total)
        for weight, kind, rarity, options in tiers:
            pick -= weight
            if pick < 0:
                break
        else:  # pragma: no cover - the loop always breaks above
            raise ValueError("Supply tier selection failed")
        if min_star is not None:
            options = tuple(option for option in options
                            if kind != "avatar_card" or _card_star(option[0]) >= min_star)
            if not options:
                continue
        item_id, num = random.choice(options)
        return kind, item_id, (0 if kind == "material" else 1), num
    raise ValueError("Supply pool has no item that satisfies the guarantee")


def _meets_guarantee(channel, item):
    rule = TEN_PULL_GUARANTEE.get(channel)
    if rule is None:
        return True
    if rule.get("card_min_star") is not None:
        return item["kind"] == "avatar_card" and item["star"] >= rule["card_min_star"]
    return (item["kind"], item["rarity"]) in set(rule["tiers"])


def _runtime(account):
    runtime = account.setdefault("gacha_runtime", {
        "schema": 1, "gacha_random": 0, "pull_count": {}, "log": []})
    if runtime.get("schema") != 1 or not isinstance(runtime.get("log"), list):
        raise ValueError("Unsupported supply transaction state")
    runtime.setdefault("pull_count", {})
    return runtime


def _gacha_random(account):
    """A fresh non-zero seed. The client refuses to send GachaReq at seed 0."""
    seed = random.randrange(1, 0x8000_0000)
    _runtime(account)["gacha_random"] = seed
    return seed


def _banner_runtime(account, channel=GACHA_ZIYUAN):
    banners = _runtime(account).setdefault('banners', {})
    period = ZIYUAN_EQUIP_PERIOD if channel == GACHA_ZIYUAN_EQUIP else ZIYUAN_PERIOD
    state = banners.setdefault(period, {'pulls':0,'since_a':0,'up_cards':0})
    if any(type(state.get(key)) is not int or state[key] < 0 for key in ('pulls','since_a','up_cards')) or state['since_a'] > 9:
        raise ValueError('Malformed independent banner counters')
    return state


def _restore(account, snapshot):
    account.clear()
    account.update(snapshot)


# ---------------------------------------------------------------- display

def _common_data(channel):
    config = CHANNELS[channel]
    if channel != GACHA_FRIENDS_POINT:
        import server19_gacha_policy as policy
        rule = policy.rule(channel)
    else:
        rule = config['rule']
    return {"title_image": config.get("title_image", config["image"]),
            "supply_image": config["image"],
            "title": config["title"], "content": config["content"],
            "rule": rule, "content_detail": rule,
            "content_url": "", "btn_image_path": ""}


def _hcoin_data(channel):
    config = CHANNELS[channel]
    return {"common_data": _common_data(channel),
            "ticket_hcoin_cost": config["hcoin_cost"],
            "ticket_material_id": config["ticket_material_id"]}


def display_payload(account, *, seed=None):
    """GetGachaDisplayRsp body. No time fields: an unspecified expire time is
    what GachaModule::IsGachaDataExpired treats as 'never expires'."""
    return {"retcode": RSP_SUCC,
            "hcoin_gacha_data": _hcoin_data(GACHA_HCOIN),
            "friends_point_gacha_data":
                {"common_data": _common_data(GACHA_FRIENDS_POINT),
                 "friends_point_cost": CHANNELS[GACHA_FRIENDS_POINT]["friends_point_cost"]},
            "hcoin_noup_gacha_data_list": [_hcoin_data(GACHA_EQUIP_HCOIN)],
            "special_hcoin_gacha_data_list": [{**_hcoin_data(GACHA_ZIYUAN_EQUIP),
                "data_begin_time":1,"data_expire_time":2147483647}],
            "custom_gacha_data_list": [{**_hcoin_data(GACHA_ZIYUAN),
                "gacha_type": GACHA_ZIYUAN, "cost_material_id": 1103,
                "cost_material_num": 1, "is_enable_baodi": False,
                # IsCustomValid78543 reads the value unconditionally, unlike
                # IsGachaDataExpired's Specified guard for standard supply.
                # Keep this local test period open until the signed2038 bound.
                "data_begin_time": 1, "data_expire_time": 2147483647,
                "total_gacha_times": 0,
                "gacha_times": _banner_runtime(account)['pulls'],
                "item_list": []}],
            "gacha_random": seed if seed is not None else _gacha_random(account)}


# ---------------------------------------------------------------- granting

def _grant_fragment(account, avatar_id, fragment_id, count):
    """Duplicate-card fragments, under server19_avatar_fragments' own rules.

    That module only audits the two Chapter1 story fragments; the supply
    channel needs every original avatar, so the same checks (original row,
    owned avatar, quantity limit) are applied here against the deployed table.
    """
    rows = stage._table("avatarfragmentdata", field="ID", identities=(fragment_id,))
    if len(rows) != 1 or rows[0].get("ItemType") != "11002":
        raise ValueError("Avatar fragment is not an original row")
    limit = stage._u32(rows[0]["quantityLimit"], "fragment quantity limit")
    avatars = [row for row in account.get("avatar_list", [])
               if row.get("avatar_id") == avatar_id]
    if len(avatars) != 1 or stage._u32(avatars[0].get("star", 0), "avatar star") <= 0:
        raise ValueError("Fragment supply requires its actual owned avatar")
    total = stage._u32(avatars[0].get("fragment", 0), "stored avatar fragment") + count
    if total > limit:
        raise ValueError("Avatar fragment would exceed its quantity limit")
    avatars[0]["fragment"] = total


def _duplicate_fragments(account, avatar_id):
    """Fragments a repeated card yields.

    avatarstardata carries upgradeFragment (the star-up cost) and
    recountFragment (what a repeated card converts into). recountFragment is 0
    at star 0, which is exactly the "not owned yet" case that must not convert.
    """
    owned = [row for row in account.get("avatar_list", []) if row["avatar_id"] == avatar_id]
    if len(owned) != 1:
        raise ValueError("Repeated card has no single owned avatar")
    star = stage._u32(owned[0].get("star", 0), "avatar star")
    for row in stage._table("avatarstardata", field="avatarID", identities=(avatar_id,)):
        if stage._u32(row["star"], "star") == star:
            count = stage._u32(row["recountFragment"], "recountFragment")
            if count <= 0:
                raise ValueError("Repeated card has no configured fragment yield")
            return count
    raise ValueError("Avatar has no star-data row for its current star")


def _grant_card(account, card_id):
    """One avatar card: unlock the valkyrie, or convert a repeat.

    Returns the fragment count for a repeat and 0 for a new unlock; GachaRsp
    carries that number as split_fragment_num, which is the only thing that
    makes GachaMainPageContext::OnGachaRsp call AvatarCardDataItem
    ::SpliteToFragment. Without it the client shows an ordinary card while the
    account silently gains fragments.
    """
    rows = stage._table("avatardata", field="avatarCardID", identities=(card_id,))
    if len(rows) != 1:
        raise ValueError("Supply card is not an original avatar card")
    meta = rows[0]
    avatar_id = stage._u32(meta["avatarID"], "avatarID")
    avatars = account.setdefault("avatar_list", [])
    owned = [row for row in avatars if row["avatar_id"] == avatar_id]
    if len(owned) > 1:
        raise ValueError("Duplicate owned avatar")
    if owned and stage._u32(owned[0].get("star", 0), "avatar star") > 0:
        fragment_id = stage._u32(meta["avatarFragmentID"], "avatarFragmentID")
        count = _duplicate_fragments(account, avatar_id)
        _grant_fragment(account, avatar_id, fragment_id, count)
        return count
    weapons = account.setdefault("weapon_list", [])
    all_uids = [row["unique_id"] for name in ("weapon_list", "stigmata_list")
                for row in account.get(name, [])]
    uid = max([value for value in all_uids if value < 20000], default=0) + 1
    if uid >= 20000 or uid in all_uids:
        raise ValueError("Original weapon UID range is exhausted")
    weapons.append({"unique_id": uid,
                    "id": stage._u32(meta["initialWeapon"], "initialWeapon"),
                    "level": 1, "exp": 0, "is_protected": False})
    if owned:
        target = owned[0]
        target.update({"star": stage._u32(meta["unlockStar"], "unlockStar"),
                       "level": 1, "exp": 0, "weapon_unique_id": uid,
                       "touch_goodfeel": 0, "stage_goodfeel": 0,
                       "stigmata_unique_id_1": 0, "stigmata_unique_id_2": 0,
                       "stigmata_unique_id_3": 0, "skill_list": []})
    else:
        avatars.append({"avatar_id": avatar_id,
                        "star": stage._u32(meta["unlockStar"], "unlockStar"),
                        "level": 1, "exp": 0, "fragment": 0, "weapon_unique_id": uid,
                        "touch_goodfeel": 0, "stage_goodfeel": 0,
                        "stigmata_unique_id_1": 0, "stigmata_unique_id_2": 0,
                        "stigmata_unique_id_3": 0, "skill_list": []})
    return 0


def _grant_material(account, item_id, num):
    rows = stage._table("materialdata", field="ID", identities=(item_id,))
    if len(rows) != 1:
        raise ValueError("Supply material is not an original row")
    limit = stage._u32(rows[0]["quantityLimit"], "material quantity limit")
    materials = account.setdefault("material_list", [])
    stored = [row for row in materials if row.get("id") == item_id]
    if len(stored) > 1:
        raise ValueError("Duplicate stored material IDs")
    if stored:
        if stage._u32(stored[0].get("num", 0), "stored material num") + num > limit:
            raise ValueError("Supply material would exceed its quantity limit")
        stored[0]["num"] += num
    elif num <= limit:
        materials.append({"id": item_id, "num": num})
    else:
        raise ValueError("Supply material exceeds its quantity limit")


def _grant(account, kind, item_id, level, num):
    """Apply one drawn item; returns the duplicate fragment count (cards only)."""
    if kind == "avatar_card":
        return _grant_card(account, item_id)
    if kind == "material":
        _grant_material(account, item_id, num)
    else:
        stage._grant_drops(account, {(item_id, level): num})
    return 0


def _rarity_of(kind, item_id):
    if kind == "avatar_card":
        return 4
    name = {"material": "materialdata", "weapon": "weapondata",
            "stigmata": "stigmatadata"}[kind]
    rows = stage._table(name, field="ID", identities=(item_id,))
    return stage._u32(rows[0]["rarity"], "item rarity") if rows else 0


def _charge(account, channel, num, use_hcoin):
    """Spend tickets when they cover the pull, otherwise fall back to hcoin."""
    config = CHANNELS[channel]
    if "friends_point_cost" in config:
        cost = config["friends_point_cost"] * num
        if account["main"].get("friends_point", 0) < cost:
            return RSP_FRIENDS_POINT_LACK
        account["main"]["friends_point"] -= cost
        return RSP_SUCC
    ticket = config["ticket_material_id"]
    materials = account.setdefault("material_list", [])
    held = next((row for row in materials if row.get("id") == ticket), None)
    if held is not None and held.get("num", 0) >= num:
        held["num"] -= num
        return RSP_SUCC
    if not use_hcoin:
        return RSP_TICKET_LACK
    cost = config["hcoin_cost"] * num
    if account["main"].get("hcoin", 0) < cost:
        return RSP_HCOIN_LACK
    account["main"]["hcoin"] -= cost
    return RSP_SUCC


def _draw(account, channel, num, use_hcoin):
    """Atomic pull: a refused grant rolls the whole transaction back."""
    if channel != GACHA_FRIENDS_POINT:
        import server19_gacha_policy as policy
        return policy.draw(account, channel, num, use_hcoin)
    saved = deepcopy(account)
    retcode = _charge(account, channel, num, use_hcoin)
    if retcode != RSP_SUCC:
        _restore(account, saved)
        return retcode, []
    items = []
    banner = _banner_runtime(account,channel) if channel in (GACHA_ZIYUAN,GACHA_ZIYUAN_EQUIP) else None
    for index in range(num):
        guarantee = None
        if banner is not None and banner['since_a'] >= 9:
            guarantee = ({'tiers':(('weapon',4),('stigmata',4))} if channel == GACHA_ZIYUAN_EQUIP else
                         {'tiers': (('avatar_card',4),), 'card_min_star': 2})
        elif num >= 10 and index == num - 1 and banner is None:
            rule = TEN_PULL_GUARANTEE.get(channel)
            if rule is not None and not any(_meets_guarantee(channel, item) for item in items):
                guarantee = rule
        for _ in range(REROLL_LIMIT):
            kind, item_id, level, count = _roll(channel, guaranteed=guarantee)
            snapshot = deepcopy(account)
            try:
                split = _grant(account, kind, item_id, level, count)
            except (ValueError, TypeError, KeyError):
                _restore(account, snapshot)
                continue
            break
        else:
            _restore(account, saved)
            return RSP_EQUIPMENT_MATERIAL_LIMIT, []
        items.append({"kind": kind, "item_id": item_id, "level": level, "num": count,
                      "rarity": _rarity_of(kind, item_id),
                      "star": _card_star(item_id) if kind == "avatar_card" else 0,
                      "split_fragment_num": split})
        if banner is not None:
            # A rejected reward re-roll restores a deep snapshot, replacing
            # nested dictionaries. Reacquire the committed counter object.
            banner = _banner_runtime(account,channel)
            banner['pulls'] += 1
            qualified = (kind in ('weapon','stigmata') and _rarity_of(kind,item_id) >= 4) if channel == GACHA_ZIYUAN_EQUIP else (kind == 'avatar_card' and _card_star(item_id) >= 2)
            banner['since_a'] = 0 if qualified else banner['since_a'] + 1
            if item_id in ((ZIYUAN_WEAPON,*ZIYUAN_STIGMATA) if channel == GACHA_ZIYUAN_EQUIP else (ZIYUAN_CARD,)):
                banner['up_cards'] += 1
    runtime = _runtime(account)
    runtime["pull_count"][str(channel)] = (
        stage._u32(runtime["pull_count"].get(str(channel), 0), "pull count") + num)
    runtime["log"].append({"time": int(time.time()),
                           "items": [{"item_id": item["item_id"],
                                      "level": item["level"], "num": item["num"]}
                                     for item in items]})
    del runtime["log"][:-200]
    return RSP_SUCC, items


# ---------------------------------------------------------------- requests

def _gacha(account, values):
    channel = stage._u32(values.get("type", 0), "gacha type")
    num = stage._u32(values.get("num", 0), "gacha num")
    if channel not in CHANNELS or not 1 <= num <= CHANNELS[channel]["max_pull"]:
        return {"retcode": RSP_FAIL}
    if channel in (GACHA_ZIYUAN,GACHA_ZIYUAN_EQUIP) and num not in (1,10):
        return {"retcode": RSP_FAIL}
    retcode, items = _draw(account, channel, num, bool(values.get("is_use_hcoin", False)))
    if retcode != RSP_SUCC:
        return {"retcode": retcode}
    rows = []
    for item in items:
        row = {"item_id": item["item_id"], "level": item["level"], "num": item["num"],
               "is_rare_drop": item["rarity"] >= 4}
        if item["split_fragment_num"]:
            # Only a repeated card sets this, and only a set value makes the
            # client convert it (split_fragment_numSpecified).
            row["split_fragment_num"] = item["split_fragment_num"]
        rows.append(row)
    seed = _gacha_random(account)
    return {"retcode": RSP_SUCC, "item_list": rows,
            "is_first_baodi_unique": False,
            "gacha_random": seed,
            "display": display_payload(account, seed=seed)}


def _log(account):
    runtime = _runtime(account)
    return {"retcode": RSP_SUCC,
            "hcoin_gacha_log_list": [{"time": row["time"], "item": deepcopy(row["items"][0])}
                                     for row in reversed(runtime["log"])
                                     if row["items"]][:100]}


def _prob(account, values):
    channel = stage._u32(values.get("gacha_type", 0), "gacha_type")
    if channel not in CHANNELS:
        return {"retcode": RSP_FAIL}
    if channel != GACHA_FRIENDS_POINT:
        import server19_gacha_policy as policy
        return policy.probability(channel)
    if channel == GACHA_ZIYUAN:
        return {'retcode':0,'gacha_type':channel,
            'total_prob_list':[{'name':'基础概率（不含十回保底）','prob':'','order_value':0}],
            'detail_prob_list':[
                {'name':label,'star':star,'content':label,'is_up':up,'order_value':i,'prob':prob}
                for i,(label,star,up,prob) in enumerate((
                    ('处刑装·紫苑','4',True,'1.50%'),
                    ('女武神·强袭','4',False,'4.50%'),
                    ('女武神·誓约','4',False,'4.50%'),
                    ('圣仪装·今样','4',False,'4.50%'),
                    ('3星武器','3',False,'7.50%'),
                    ('3星圣痕','3',False,'22.50%'),
                    ('材料','0',False,'55.00%')))]}
    if channel == GACHA_ZIYUAN_EQUIP:
        labels = (('仿犹大·血之拥抱','4',True,'2.50%'),('德古拉（上）','4',True,'2.50%'),
                  ('德古拉（中）','4',True,'2.50%'),('德古拉（下）','4',True,'2.50%'),
                  ('3星武器','3',False,'15.00%'),('3星圣痕','3',False,'25.00%'),('材料','0',False,'50.00%'))
        return {'retcode':0,'gacha_type':channel,
            'total_prob_list':[{'name':'基础概率（不含十回保底）','prob':'','order_value':0}],
            'detail_prob_list':[{'name':name,'star':star,'content':name,'is_up':up,'order_value':i,'prob':prob}
                                for i,(name,star,up,prob) in enumerate(labels)]}
    tiers = _table_for(channel)
    total = sum(tier[0] for tier in tiers)
    labels = {"avatar_card": "女武神", "weapon": "武器", "stigmata": "圣痕",
              "material": "材料"}
    share = {}
    for weight, kind, rarity, _options in tiers:
        key = rarity if kind != "material" else 0
        share[key] = share.get(key, 0) + weight
    total_list = []
    for order, rarity in enumerate(sorted(share, reverse=True)):
        name = "材料" if rarity == 0 else "%d★" % rarity
        total_list.append({"name": name, "prob": "%.2f%%" % (share[rarity] * 100.0 / total),
                           "order_value": order})
    detail_list = []
    for order, (weight, kind, rarity, options) in enumerate(
            sorted(tiers, key=lambda tier: -tier[2])):
        label = labels.get(kind, "")
        detail_list.append({"name": label, "star": "%d" % rarity,
                            "content": label, "is_up": False, "order_value": order,
                            "prob": "%.4f%%" % (weight * 100.0 / total / len(options))})
    return {"retcode": RSP_SUCC, "gacha_type": channel,
            "total_prob_list": total_list, "detail_prob_list": detail_list}


def _buy_ticket(account, values):
    material_id = stage._u32(values.get("material_id", 0), "material_id")
    num = stage._u32(values.get("num", 0), "num")
    price = next((config["hcoin_cost"] for config in CHANNELS.values()
                  if config.get("hcoin_cost") and config["ticket_material_id"] == material_id),
                 None)
    if price is None or not 1 <= num <= 100:
        return {"retcode": BUY_TICKET_RSP_FAIL}
    if account["main"].get("hcoin", 0) < price * num:
        return {"retcode": BUY_TICKET_RSP_HCOIN_LACK}
    rows = stage._table("materialdata", field="ID", identities=(material_id,))
    if len(rows) != 1:
        raise ValueError("Supply ticket is not an original material row")
    limit = stage._u32(rows[0]["quantityLimit"], "ticket quantity limit")
    materials = account.setdefault("material_list", [])
    held = next((row for row in materials if row.get("id") == material_id), None)
    if (held.get("num", 0) if held else 0) + num > limit:
        return {"retcode": BUY_TICKET_RSP_EQUIPMENT_MATERIAL_LIMIT}
    account["main"]["hcoin"] -= price * num
    if held is not None:
        held["num"] += num
    else:
        materials.append({"id": material_id, "num": num})
    return {"retcode": BUY_TICKET_RSP_SUCC, "material_id": material_id, "num": num,
            "hcoin_cost": price * num}


_HANDLERS = {"GetGachaDisplayReq": lambda account, values: display_payload(account),
             "GachaReq": _gacha,
             "GetGachaLogReq": lambda account, values: _log(account),
             "GetGachaProbReq": _prob,
             "BuyGachaTicketReq": _buy_ticket}


def notification_snapshot(account):
    """Authoritative snapshots after a successful pull; sent after the Rsp."""
    import server19_initialization
    return [server19_initialization.response("GetMainDataReq", account),
            ("GetAvatarDataRsp", {"retcode": 0,
                                  "avatar_list": deepcopy(account.get("avatar_list", []))}),
            ("GetEquipmentDataRsp", {"retcode": 0, **{
                key: deepcopy(account.get(key, []))
                for key in ("weapon_list", "stigmata_list", "material_list")}})]


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            payload = _HANDLERS[request_name](current, request_values or {})
            result = request_name[:-3] + "Rsp", payload
            proto.encode_message(*result)
            if request_name in MUTATION_REQUESTS and payload.get("retcode") == RSP_SUCC:
                # Validate before committing; server19.py sends these after the
                # response so the client's wallet and storage match the save.
                for packet in notification_snapshot(current):
                    proto.encode_message(*packet)
                if request_name == "GachaReq":
                    # The daily task "常规补给" and the guidance task 13004
                    # (finishWay 14) are both driven by this one event.
                    import server19_duty
                    import server19_missions
                    server19_duty.note_event(current, "supply")
                    server19_missions.note_event(current, "supply")
            if payload.get("retcode") == RSP_SUCC:
                stage._save(path, before, current)
                stage._sync(account, current)
            else:
                stage._sync(account, before)
        except (ValueError, TypeError, KeyError, OSError, IndexError):
            result = request_name[:-3] + "Rsp", {"retcode": RSP_FAIL}
            stage._sync(account, before)
        return result
