"""Transactional checks using generated, external game data (never committed).

Set BH3_TEST_RUNTIME to an extracted runtime and BH3_PACKAGED_NATIVE_LIBRARY
to its matching library. No live save or device is used.
"""
from copy import deepcopy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated runtime')
class ConsumptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['BH3_TEST_RUNTIME'])
        sys.path.insert(0, str(cls.root))
        import server19_stage as stage
        import server19_protocol as proto
        spec = importlib.util.spec_from_file_location('equipment_tested',
            Path(__file__).resolve().parents[1] / 'server19_equipment.py')
        cls.e = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.e)
        cls.e.FULL_CULTIVATION_READY_FILE = cls.root / '.local-baseline/server19-dev/cultivation-full-equipment-ready/runtime-ready.json'
        stage.TABLE_OVERRIDES['materialdata'] = cls.root / '.local-baseline/server19-dev/story-all-20261015/metadata/materialdata'
        manifest = {r['path']: r['sha256'] for r in json.loads((cls.root/'portable-manifest.json').read_bytes())['files']}
        for name in cls.e._POWER_UP_TABLE_HASHES:
            path = Path(stage.TABLE_OVERRIDES.get(name, stage.TABLE_DIRECTORY / name))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == manifest[path.relative_to(cls.root).as_posix()]
            cls.e._POWER_UP_TABLE_HASHES[name] = digest
        cls.stage, cls.proto = stage, proto

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'account.json'
        self.account = dict(schema=1, uid=1024, main=dict(level=80, scoin=10000),
            avatar_list=[dict(avatar_id=101, weapon_unique_id=1)],
            weapon_list=[dict(unique_id=i, id=20001, level=1, exp=0, is_protected=False) for i in (1,2,3)],
            stigmata_list=[dict(unique_id=i, id=30001, level=1, exp=0, is_protected=False) for i in (20001,20002)],
            material_list=[dict(id=3000, num=5)],
            cabin_list=[dict(type=4, level=7, tech_list=[dict(pos_x=0,pos_y=-4)])], unrelated={'keep':[1,2,3]})

    def run_request(self, name, values):
        self.path.write_text(json.dumps(self.account), encoding='utf8')
        values = self.proto.decode_message(name, self.proto.encode_message(name, values))
        return self.e.response(name, self.account, values, account_path=self.path)[1]

    @staticmethod
    def item(kind, uid):
        return dict(type=kind, id_or_unique_id=uid)

    def power(self, sources, kind=3, uid=1):
        return dict(main_item=self.item(kind, uid), consume_item_list=dict(item_list=sources))

    def sell(self, items):
        return dict(sell_item_list=dict(item_list=items))

    def test_material_sale_and_zero_stack_notification(self):
        self.account['material_list'] = [dict(id=7022, num=3), dict(id=8403, num=1)]
        result = self.run_request('EquipmentSellReq', self.sell([
            dict(type=1, id_or_unique_id=7022, num=3),
            dict(type=1, id_or_unique_id=8403, num=1)]))
        self.assertEqual(result, dict(retcode=0, scoin_add=4000))
        self.assertEqual(self.account['main']['scoin'], 14000)
        packets = dict(self.e.notification_snapshot(self.account, 'EquipmentSellReq'))
        self.assertEqual(packets['GetEquipmentDataRsp']['material_list'],
                         [dict(id=7022, num=0), dict(id=8403, num=0)])

    def test_material_sale_invalid_mixed_request_is_atomic(self):
        for rows, code in (([(7022, 1), (7022, 1)], 4),
                           ([(7022, 3)], 2), ([(7022, 0)], 2),
                           ([(7022, 1), (7178, 1)], 9)):
            self.account['material_list'] = [dict(id=7022, num=2), dict(id=7178, num=1)]
            before = deepcopy(self.account)
            result = self.run_request('EquipmentSellReq', self.sell([
                dict(type=1, id_or_unique_id=i, num=n) for i, n in rows]))
            self.assertEqual(result['retcode'], code)
            self.assertEqual(self.account, before)

    def test_costume_boxes_grant_configured_rewards(self):
        for box, dresses, materials in (
                (7217, (50024, 50043), ()),
                (7220, (50040,), (7221, 7222))):
            with self.subTest(box=box):
                self.account['material_list'] = [dict(id=box, num=1)]
                result = self.run_request('UseMaterialReq', dict(material_id=box))
                self.assertEqual(result['retcode'], 0, self.e.rejection_detail('UseMaterialReq'))
                self.assertEqual(result['gift_reward_list'][0]['item_list'],
                                 [dict(id=item, level=0, num=1) for item in dresses + materials])
                self.assertTrue(set(dresses) <= set(self.account['has_got_item_id_list']))
                self.assertEqual({row['id']: row['num'] for row in self.account['material_list']},
                                 {box: 0, **dict.fromkeys(materials, 1)})
                self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=box))['retcode'], 2)

    def test_crystal_boxes_credit_wallet_and_exhaust_inventory(self):
        self.account['main']['hcoin'] = 100
        self.account['material_list'] = [dict(id=7221, num=2), dict(id=7222, num=2)]
        expected = 100
        for item, reward in ((7221, 1000), (7222, 888)):
            for remaining in (1, 0):
                response = self.run_request('UseMaterialReq', dict(material_id=item))
                self.assertEqual(response['retcode'], 0)
                self.assertEqual(response['gift_reward_list'][0]['hcoin'], reward)
                expected += reward
                saved = json.loads(self.path.read_bytes())
                self.assertEqual(saved['main']['hcoin'], expected)
                self.assertEqual(next(m['num'] for m in saved['material_list'] if m['id'] == item),
                                 remaining)
            before = deepcopy(self.account)
            self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=item))['retcode'], 2)
            self.assertEqual(self.account, before)

    def test_costume_box_with_full_reward_stack_is_atomic(self):
        self.account['material_list'] = [dict(id=7220, num=1), dict(id=7222, num=9999)]
        before = deepcopy(self.account)
        self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=7220))['retcode'], 5)
        self.assertEqual(self.account, before)

    def test_fixed_gift_rewards_and_empty_inventory(self):
        self.account['main']['stamina'] = 100
        for identity, gain in zip(range(7022, 7028), (1000, 2000, 5000, 10000, 20000, 50000)):
            self.account['material_list'] = [dict(id=identity, num=1)]
            before = self.account['main']['scoin']
            result = self.run_request('UseMaterialReq', dict(material_id=identity))
            self.assertEqual(result['retcode'], 0)
            self.assertEqual(self.account['main']['scoin'], before + gain)
            self.assertEqual(result['gift_reward_list'][0]['scoin'], gain)
            result = self.run_request('UseMaterialReq', dict(material_id=identity))
            self.assertEqual(result['retcode'], 2)
            self.assertEqual(self.account['main']['scoin'], before + gain)

    def test_stamina_cap_and_missing_treasure_do_not_consume(self):
        self.account['main']['stamina'] = 100
        self.account['material_list'] = [dict(id=7033, num=2), dict(id=8403, num=1)]
        self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=7033))['retcode'], 0)
        self.assertEqual(self.account['main']['stamina'], 130)
        self.account['main']['stamina'] = 980
        before = deepcopy(self.account)
        self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=7033))['retcode'], 6)
        self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=999999))['retcode'], 1)
        self.assertEqual(self.account, before)

    def test_sakura_jar_weight_boundaries_and_native_storage(self):
        original = deepcopy(self.account)
        for draw in range(100):
            self.account = deepcopy(original)
            self.account['material_list'] = [dict(id=8403, num=1)]
            with patch.object(self.e.secrets, 'randbelow', return_value=draw) as rng:
                result = self.run_request('UseMaterialReq', dict(material_id=8403))
            self.assertEqual(result['retcode'], 0)
            rng.assert_called_once_with(100)
            expected, avatar = (10212, 212) if draw < 50 else (10304, 304)
            self.assertEqual(result['drop_item_list'], [dict(item_id=expected, level=0, num=1, rarity=4)])
            self.assertEqual(self.account['material_list'], [dict(id=8403, num=0)])
            owned = next(a for a in self.account['avatar_list'] if a['avatar_id'] == avatar)
            self.assertEqual(owned['fragment'], 1)
            self.assertEqual(owned['star'], 0)
            self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=8403))['retcode'], 2)

    def test_sakura_jar_full_storage_and_save_failure_are_atomic(self):
        self.account['material_list'] = [dict(id=8403, num=2)]
        self.account['avatar_list'].append(dict(avatar_id=212, star=1, fragment=2999))
        before = deepcopy(self.account)
        with patch.object(self.e.secrets, 'randbelow') as rng:
            self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=8403))['retcode'], 5)
            rng.assert_not_called()
        self.assertEqual(self.account, before)
        self.account['avatar_list'][-1]['fragment'] = 10
        before = deepcopy(self.account)
        with patch.object(self.e.secrets, 'randbelow', return_value=0), patch.object(self.stage, '_save', side_effect=OSError('test')):
            self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=8403))['retcode'], 1)
        self.assertEqual(self.account, before)
        with patch.object(self.e.secrets, 'randbelow', return_value=0):
            self.assertEqual(self.run_request('UseMaterialReq', dict(material_id=8403))['retcode'], 0)
        self.assertEqual(self.account['avatar_list'][-1]['fragment'], 11)
        self.assertEqual(self.account['material_list'][0]['num'], 1)

    def test_mixed_fodder_matches_native_preview_and_deletes_uids(self):
        # Source LV2 weapon=90, LV1 stigmata=75, crystal=200: 365EXP, 182coins.
        self.account['weapon_list'][1]['level'] = 2
        result = self.run_request('EquipmentPowerUpReq', self.power([
            self.item(3,2), self.item(4,20002), dict(type=1,id_or_unique_id=3000,num=1)]))
        self.assertEqual(result['retcode'],0)
        self.assertEqual(self.account['main']['scoin'],9818)
        self.assertEqual(self.account['weapon_list'][0]['level'],5)
        self.assertEqual(self.account['weapon_list'][0]['exp'],63)
        self.assertEqual([i['unique_id'] for i in self.account['weapon_list']],[1,3])
        self.assertEqual([i['unique_id'] for i in self.account['stigmata_list']],[20001])
        self.assertEqual(self.account['material_list'][0]['num'],4)
        packets = self.e.notification_snapshot(self.account, 'EquipmentPowerUpReq')
        self.assertEqual(dict(packets)['DelEquipmentNotify'],dict(weapon_unique_id_list=[2],stigmata_unique_id_list=[20002]))
        for name, body in packets:
            self.proto.encode_message(name, body)

    def test_stigmata_target_accepts_weapon_fodder(self):
        result=self.run_request('EquipmentPowerUpReq',self.power([self.item(3,2)],4,20001))
        self.assertEqual(result['retcode'],0)
        self.assertEqual(self.account['main']['scoin'],9963)
        self.assertEqual((self.account['stigmata_list'][0]['level'],self.account['stigmata_list'][0]['exp']),(4,33))

    def test_lightning_angel_all_ranks_strengthen_and_persist(self):
        for identity in (20457, 20458, 20459):
            with self.subTest(identity=identity):
                self.account['weapon_list'][0].update(id=identity, level=1, exp=0)
                coins = self.account['main']['scoin']
                material = self.account['material_list'][0]['num']
                result = self.run_request('EquipmentPowerUpReq', self.power([
                    dict(type=1, id_or_unique_id=3000, num=1)]))
                self.assertEqual(result['retcode'], 0)
                self.assertEqual(self.account['weapon_list'][0]['id'], identity)
                self.assertEqual(self.account['weapon_list'][0]['unique_id'], 1)
                self.assertGreater(self.account['weapon_list'][0]['level'], 1)
                self.assertEqual(self.account['main']['scoin'], coins - 100)
                self.assertEqual(self.account['material_list'][0]['num'], material - 1)
                self.assertEqual(json.loads(self.path.read_bytes()), self.account)

    def test_lightning_angel_failure_does_not_charge(self):
        self.account['weapon_list'][0].update(id=20457, level=1, exp=0)
        request = self.power([dict(type=1, id_or_unique_id=3000, num=1)])
        for level, coins, code in ((25, 10000, 3), (1, 0, 8)):
            self.account['weapon_list'][0]['level'] = level
            self.account['main']['scoin'] = coins
            before = deepcopy(self.account)
            self.assertEqual(self.run_request('EquipmentPowerUpReq', request)['retcode'], code)
            self.assertEqual(self.account, before)
            self.assertEqual(json.loads(self.path.read_bytes()), before)

    def test_table_growth_keeps_default_and_x86_scope(self):
        self.assertNotIn(20457, self.e._audited_growth_ids())
        self.assertIn(20457, self.e._audited_growth_ids(table_growth=True))
        with patch.object(self.e, 'X86_STARTER_GROWTH', True):
            self.assertEqual(self.e._audited_growth_ids(table_growth=True), {20001})

    def test_lightning_angel_evolution_chain_rebinds_and_charges_exact_recipe(self):
        for identity, next_id in ((20457, 20458), (20458, 20459)):
            meta = self.e._metadata('weapondata', identity)
            item = self.account['weapon_list'][0]
            item.update(id=identity, level=meta['maxLv'], exp=0)
            old_uid = item['unique_id']
            self.account['avatar_list'] = [dict(avatar_id=501, level=80, weapon_unique_id=old_uid)]
            required = dict(tuple(map(int, x.split(':'))) for x in meta['evoMaterial'])
            self.account['material_list'] = [dict(id=i, num=n+10) for i,n in required.items()]
            self.account['main']['scoin'] = 1000000
            request = dict(main_item=self.item(3, old_uid), consume_item_list=dict(item_list=[
                dict(type=1, id_or_unique_id=i, num=n) for i,n in required.items()]))
            before = deepcopy(self.account)
            with patch.object(self.stage, '_save', side_effect=OSError('test')):
                self.assertEqual(self.run_request('EquipmentEvoReq', request)['retcode'], 1)
            self.assertEqual(self.account, before)
            result = self.run_request('EquipmentEvoReq', request)
            self.assertEqual(result['retcode'], 0)
            new_uid = result['new_item']['id_or_unique_id']
            self.assertNotEqual(new_uid, old_uid)
            item = self.account['weapon_list'][0]
            self.assertEqual((item['id'],item['level'],item['exp']), (next_id,1,0))
            self.assertEqual(self.account['avatar_list'][0]['weapon_unique_id'],new_uid)
            self.assertTrue(all(m['num']==10 for m in self.account['material_list']))
            cost = self.e._row(self.e._power_up_tables(),'equipmentleveldata',meta['maxLv'],'level')['weaponEvoCost']
            self.assertEqual(self.account['main']['scoin'],1000000-cost)
            self.assertEqual(json.loads(self.path.read_bytes()),self.account)

    def test_sell_multiple_equipment_once(self):
        self.account['weapon_list'][1]['level']=5
        result=self.run_request('EquipmentSellReq',self.sell([self.item(3,2),self.item(4,20002)]))
        self.assertEqual(result,dict(retcode=0,scoin_add=140))
        self.assertEqual(self.account['main']['scoin'],10140)

        self.assertEqual(len(self.account['weapon_list']),2)
        self.assertEqual(len(self.account['stigmata_list']),1)
        again=self.e.response('EquipmentSellReq',self.account,self.sell([self.item(3,2)]),account_path=self.path)[1]
        self.assertEqual(again['retcode'],2)
        self.assertEqual(self.account['main']['scoin'],10140)

    def test_befall_duplicate_weapon_recipe_and_equal_level_cap(self):
        self.account['avatar_list'] = []
        self.account['weapon_list'] = [dict(unique_id=1,id=25013,level=35,exp=0),
            dict(unique_id=2,id=25011,level=1,exp=0),
            dict(unique_id=3,id=25011,level=1,exp=0)]
        self.account['main']['scoin'] = 1000000
        request=dict(main_item=self.item(3,1),consume_item_list=dict(item_list=[self.item(3,2),self.item(3,3)]))
        before=deepcopy(self.account)
        with patch.object(self.stage,'_save',side_effect=OSError('test')):
            self.assertEqual(self.run_request('EquipmentEvoReq',request)['retcode'],1)
        self.assertEqual(self.account,before)
        result=self.run_request('EquipmentEvoReq',request)
        self.assertEqual(result['retcode'],0)
        self.assertEqual(len(self.account['weapon_list']),1)
        self.assertEqual(self.account['weapon_list'][0]['id'],25014)
        deleted=[v for n,v in self.e.notification_snapshot(self.account,'EquipmentEvoReq') if n=='DelEquipmentNotify']
        self.assertEqual({uid for row in deleted for uid in row['weapon_unique_id_list']},{1,2,3})
        self.assertEqual(json.loads(self.path.read_bytes()),self.account)

    def test_coin_gift_is_not_blocked_by_existing_stamina_over_cap(self):
        self.account['main']['stamina']=1000
        self.account['material_list']=[dict(id=7022,num=2),dict(id=7033,num=2)]
        coins=self.account['main']['scoin']
        self.assertEqual(self.run_request('UseMaterialReq',dict(material_id=7022))['retcode'],0)
        self.assertGreater(self.account['main']['scoin'],coins)
        self.assertEqual(self.account['main']['stamina'],1000)
        self.assertEqual(self.account['material_list'][0]['num'],1)
        before=deepcopy(self.account)
        self.assertEqual(self.run_request('UseMaterialReq',dict(material_id=7033))['retcode'],6)
        self.assertEqual(self.account,before)

    def test_befall_evolution_rejects_invalid_fodder_without_consumption(self):
        self.account['avatar_list']=[]
        self.account['weapon_list']=[dict(unique_id=1,id=25001,level=15,exp=0),
            dict(unique_id=2,id=25001,level=1,exp=0)]
        self.account['main']['scoin']=1000000
        base=deepcopy(self.account)
        for case in ('self','locked','equipped','wrong_model','duplicate'):
            self.account=deepcopy(base)
            entries=[self.item(3,2)]
            if case=='self':entries=[self.item(3,1)]
            elif case=='locked':self.account['weapon_list'][1]['is_protected']=True
            elif case=='equipped':self.account['avatar_list']=[dict(avatar_id=101,weapon_unique_id=2)]
            elif case=='wrong_model':self.account['weapon_list'][1]['id']=20001
            elif case=='duplicate':entries.append(self.item(3,2))
            before=deepcopy(self.account)
            request=dict(main_item=self.item(3,1),consume_item_list=dict(item_list=entries))
            self.assertNotEqual(self.run_request('EquipmentEvoReq',request)['retcode'],0,case)
            self.assertEqual(self.account,before,case)
            self.assertEqual(json.loads(self.path.read_bytes()),before,case)
    def test_disjoin_requires_activated_technology_not_only_cabin_level(self):
        for level, techs in ((8, []), (8, [dict(pos_x=0,pos_y=0)]),
                             (6, [dict(pos_x=0,pos_y=-4)])):
            self.account['cabin_list'] = [dict(type=4,level=level,tech_list=techs)]
            before = deepcopy(self.account)
            result = self.run_request('IslandDisjoinEquipmentReq',dict(type=3,unique_id=2,disjoin_type=1))
            self.assertEqual(result['retcode'], 2)
            self.assertEqual(self.account, before)

    def test_disjoin_both_kinds_matches_native_recipe(self):
        for kind,uid in [(3,2),(4,20002)]:
            result=self.run_request('IslandDisjoinEquipmentReq',dict(type=kind,unique_id=uid,disjoin_type=1))
            self.assertEqual(result['retcode'],0)
        self.assertEqual(self.account['main']['scoin'],9980)
        self.assertEqual(self.account['material_list'],[dict(id=3000,num=9)])
        self.assertEqual(self.account['unrelated'],{'keep':[1,2,3]})

    def test_reject_batch_atomically(self):
        cases=[('EquipmentSellReq',self.sell([self.item(3,2),self.item(3,1)]),3),
               ('EquipmentSellReq',self.sell([self.item(3,2),self.item(3,2)]),4),
               ('EquipmentPowerUpReq',self.power([self.item(3,2),self.item(3,1)]),7),
               ('EquipmentPowerUpReq',self.power([self.item(3,2),self.item(3,2)]),6)]
        for name,request,code in cases:
            with self.subTest(name=name,code=code):
                before=deepcopy(self.account)
                self.assertEqual(self.run_request(name,request)['retcode'],code)
                self.assertEqual(self.account,before)
                self.assertEqual(json.loads(self.path.read_bytes()),before)

    def test_protection_missing_coins_and_capacity_preserve_save(self):
        self.account['weapon_list'][1]['is_protected']=True
        for name,request in [('EquipmentSellReq',self.sell([self.item(3,2)])),
                             ('EquipmentPowerUpReq',self.power([self.item(3,2)])),
                             ('IslandDisjoinEquipmentReq',dict(type=3,unique_id=2))]:
            before=deepcopy(self.account)
            self.assertNotEqual(self.run_request(name,request)['retcode'],0)
            self.assertEqual(self.account,before)
        self.account['weapon_list'][1]['is_protected']=False
        self.account['main']['scoin']=0
        before=deepcopy(self.account)
        self.assertEqual(self.run_request('IslandDisjoinEquipmentReq',dict(type=3,unique_id=2))['retcode'],6)
        self.assertEqual(self.account,before)
        self.assertEqual(self.run_request('EquipmentPowerUpReq',self.power([self.item(3,2)]))['retcode'],8)
        self.assertEqual(self.account,before)
        self.account['main']['scoin']=10000
        self.account['material_list'][0]['num']=999999999
        before=deepcopy(self.account)
        self.assertEqual(self.run_request('IslandDisjoinEquipmentReq',dict(type=3,unique_id=2))['retcode'],7)
        self.assertEqual(self.account,before)

    def test_disk_failure_does_not_consume_equipment(self):
        before=deepcopy(self.account)
        with patch.object(self.stage,'_save',side_effect=OSError('test disk failure')):
            result=self.run_request('EquipmentSellReq',self.sell([self.item(3,2)]))
        self.assertEqual(result['retcode'],1)
        self.assertEqual(self.account,before)
        self.assertEqual(json.loads(self.path.read_bytes()),before)


if __name__ == '__main__':
    unittest.main()
