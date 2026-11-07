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
