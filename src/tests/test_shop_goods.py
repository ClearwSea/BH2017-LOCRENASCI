"""Shop regression checks against externally generated runtime tables."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("BH3_TEST_RUNTIME"), "requires generated runtime")
class ShopGoodsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ["BH3_TEST_RUNTIME"])
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location("shop_under_test", Path(__file__).resolve().parents[1] / "server19_shop.py")
        cls.shop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.shop)
        cls.shop.CONFIG_PATH = root / "server19_shop_config.json"
        cls.shop.META_DIR = root / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"
        cls.shop.reload_config()
        fragment_spec = importlib.util.spec_from_file_location("fragments_under_test", Path(__file__).resolve().parents[1] / "server19_avatar_fragments.py")
        cls.shop.fragments = importlib.util.module_from_spec(fragment_spec)
        fragment_spec.loader.exec_module(cls.shop.fragments)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "account.json"
        self.account = dict(schema=1, uid=1024, main=dict(level=80, scoin=100000000, hcoin=100000000),
            material_list=[dict(id=i, num=10000000) for i in self.shop.MATERIALS_TABLE],
            weapon_list=[], stigmata_list=[], avatar_list=[])

    def request(self, name, values):
        self.path.write_text(json.dumps(self.account), encoding="utf-8")
        return self.shop.response(name, self.account, values, account_path=self.path)[1]

    def test_all_configured_goods_can_be_purchased_and_granted(self):
        for shop in self.shop.SHOPS_CONFIG:
            for gid in shop["goods_pool"]:
                with self.subTest(shop=shop["shop_id"], goods=gid):
                    if shop["shop_id"] == 6:
                        pool = self.shop._goods_pool(shop)
                        self.account["shop_runtime"] = dict(exchange_house_goods=[gid]+[g for g in pool if g != gid][:7], buy_records={})
                    result = self.request("BuyGoodsReq", dict(shop_id=shop["shop_id"], goods_id=gid))
                    self.assertEqual(result["retcode"], 0)
                    item = self.shop.GOODS_METADATA[gid]["ItemID"]
                    if item in self.shop.DRESSES_TABLE:
                        self.assertIn(item, self.account["has_got_item_id_list"])
                    elif item in self.shop.AVATAR_FRAGS_TABLE:
                        avatar_id = self.shop.fragments.AUDITED_IDS[item]
                        self.assertTrue(any(a["avatar_id"] == avatar_id and a["fragment"] > 0 for a in self.account["avatar_list"]))
                        self.assertFalse(any(r["id"] == item for r in self.account["material_list"]))
                    else:
                        self.assertTrue(any(r["id"] == item for key in ("material_list", "weapon_list", "stigmata_list") for r in self.account[key]))

    def test_full_rank_fragment_purchase_migrates_legacy_count_once(self):
        self.account["avatar_list"] = [dict(avatar_id=501, star=5, level=80, fragment=7)]
        self.account["material_list"].append(dict(id=10501, num=2))
        gid = next(g for g in self.shop.SHOPS_CONFIG[1]["goods_pool"] if self.shop.GOODS_METADATA[g]["ItemID"] == 10501)
        for expected in (29, 49):
            result = self.request("BuyGoodsReq", dict(shop_id=2, goods_id=gid))
            self.assertEqual(result["retcode"], 0)
            self.assertEqual(self.account["avatar_list"][0]["fragment"], expected)
            self.assertFalse(any(r["id"] == 10501 for r in self.account["material_list"]))

    def test_fragment_limit_rejection_preserves_currency_and_legacy_items(self):
        self.account["avatar_list"] = [dict(avatar_id=501, star=5, level=80, fragment=2999)]
        self.account["material_list"].append(dict(id=10501, num=1))
        gid = next(g for g in self.shop.SHOPS_CONFIG[1]["goods_pool"] if self.shop.GOODS_METADATA[g]["ItemID"] == 10501)
        before = deepcopy(self.account)
        result = self.request("BuyGoodsReq", dict(shop_id=2, goods_id=gid))
        self.assertEqual(result["retcode"], 1)
        self.assertEqual(self.account, before)
        self.assertEqual(json.loads(self.path.read_text()), before)

    def test_orphan_goods_rejected_without_account_or_disk_change(self):
        for gid, meta in self.shop.GOODS_METADATA.items():
            if self.shop._is_supported_item(meta["ItemID"]):
                continue
            with self.subTest(goods=gid):
                before = deepcopy(self.account)
                result = self.request("BuyGoodsReq", dict(shop_id=7, goods_id=gid))
                self.assertEqual(result["retcode"], 1)
                self.assertEqual(self.account, before)
                self.assertEqual(json.loads(self.path.read_text()), before)

    def test_fragment_goods_remain_visible_and_unknown_pool_entries_are_removed(self):
        shop = deepcopy(self.shop.SHOPS_CONFIG[1])
        original = list(shop["goods_pool"])
        self.assertTrue(all(self.shop.GOODS_METADATA[g]["ItemID"] in self.shop.AVATAR_FRAGS_TABLE for g in original))
        orphan = next(g for g,m in self.shop.GOODS_METADATA.items() if not self.shop._is_supported_item(m["ItemID"]))
        shop["goods_pool"] += [orphan, -1]
        self.assertEqual(self.shop._goods_pool(shop), original)

    def test_wrong_shop_and_stale_exchange_shelf_rejected(self):
        exchange = next(s for s in self.shop.SHOPS_CONFIG if s["shop_id"] == 6)
        pool = self.shop._goods_pool(exchange)
        for sid,gid in ((999, pool[0]), (6, pool[8])):
            self.account["shop_runtime"] = dict(exchange_house_goods=pool[:8], buy_records={})
            before = deepcopy(self.account)
            result = self.request("BuyGoodsReq", dict(shop_id=sid, goods_id=gid))
            self.assertEqual(result["retcode"], 1)
            self.assertEqual(self.account, before)

    def test_refresh_removes_legacy_orphan_shelf(self):
        self.account["shop_runtime"] = dict(exchange_house_goods=[88, -1], buy_records={})
        self.assertEqual(self.request("ManualRefreshShopReq", dict(shop_id=6))["retcode"], 0)
        payload = self.shop.build_shop_list_payload(self.account)
        for shop in payload["shop_list"]:
            for goods in shop["goods_list"]:
                self.assertTrue(self.shop._is_supported_item(self.shop.GOODS_METADATA[goods["goods_id"]]["ItemID"]))


    def test_shop_equipment_uid_boundary_rejects_without_deduction(self):
        for kind, table, uid in [('weapon_list', self.shop.WEAPONS_TABLE, 19999), ('stigmata_list', self.shop.STIGMATAS_TABLE, 39999), ('stigmata_list', self.shop.STIGMATAS_TABLE, 40029)]:
            shop = next(s for s in self.shop.SHOPS_CONFIG if s['shop_id'] != 6 and any(self.shop.GOODS_METADATA[g]['ItemID'] in table for g in s['goods_pool']))
            gid = next(g for g in shop['goods_pool'] if self.shop.GOODS_METADATA[g]['ItemID'] in table)
            item_id = self.shop.GOODS_METADATA[gid]['ItemID']
            self.account[kind] = [dict(unique_id=uid, id=item_id, level=1, exp=0, is_protected=False)]
            before = deepcopy(self.account)
            result = self.request('BuyGoodsReq', dict(shop_id=shop['shop_id'], goods_id=gid))
            self.assertEqual(result['retcode'], 1)
            self.assertEqual(self.account, before)
            self.assertEqual(json.loads(self.path.read_text()), before)
            self.account[kind] = []

    def test_repaired_stigmata_inventory_allocates_in_range(self):
        item_id = next(iter(self.shop.STIGMATAS_TABLE))
        self.account['stigmata_list'] = [dict(unique_id=20029, id=item_id, level=1, exp=0)]
        self.shop._grant_item(self.account, item_id, 1)
        self.assertEqual(self.account['stigmata_list'][-1]['unique_id'], 20030)


if __name__ == "__main__":
    unittest.main()
