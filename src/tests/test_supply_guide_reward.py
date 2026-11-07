"""Tutorial reward transactions against generated external runtime tables."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated runtime')
class SupplyGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['BH3_TEST_RUNTIME'])
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location('tested_supply_stage', Path(__file__).resolve().parents[1] / 'server19_stage.py')
        cls.s = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.s)
        cls.s.TABLE_DIRECTORY = root / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
        cls.s.TABLE_OVERRIDES['materialdata'] = root / '.local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset/materialdata'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'account.json'
        self.account = {'schema': 1, 'uid': 1024, 'main': {'hcoin': 0}, 'guide_id_list': [], 'material_list': []}
        self.persist()

    def persist(self):
        self.path.write_text(json.dumps(self.account), encoding='utf8')

    def report(self, ids, force=False):
        return self.s.response('FinishGuideReportReq', self.account,
            {'guide_id_list': ids, 'is_force_finish': force}, account_path=self.path)[1]

    def test_first_report_and_replay_after_consumption(self):
        ids = [9102, 9103, 9106, 9107]
        self.assertEqual(self.report(ids)['retcode'], 0)
        self.assertEqual(self.account['material_list'], [{'id': 1101, 'num': 1}])
        self.assertEqual(self.report(ids)['retcode'], 0)
        self.assertEqual(self.account['material_list'][0]['num'], 1)
        self.account['material_list'][0]['num'] = 0
        self.persist()
        self.assertEqual(self.report(ids)['retcode'], 0)
        self.assertEqual(self.account['material_list'][0]['num'], 0)
        self.assertEqual(self.account['main']['hcoin'], 0)

    def test_invalid_batch_is_atomic(self):
        before = self.path.read_bytes()
        self.assertEqual(self.report([9103, -1])['retcode'], 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_capacity_failure_does_not_complete_guide(self):
        limit = self.s._item_metadata(1101)[1]['quantityLimit']
        self.account['material_list'] = [{'id': 1101, 'num': limit}]
        self.persist()
        before = self.path.read_bytes()
        self.assertEqual(self.report([9103])['retcode'], 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotIn(9103, self.account['guide_id_list'])

    def test_unrelated_guide_does_not_grant(self):
        self.assertEqual(self.report([9102])['retcode'], 0)
        self.assertEqual(self.account['material_list'], [])
        self.assertEqual(self.s.guide_notification_snapshot(self.account, {'guide_id_list': [9102]}), [])

    def test_reward_snapshot_is_serializable(self):
        self.assertEqual(self.report([9103])['retcode'], 0)
        packets = self.s.guide_notification_snapshot(self.account, {'guide_id_list': [9103]})
        self.assertEqual(packets[0][1]['material_list'], [{'id': 1101, 'num': 1}])
        for packet in packets:
            self.s.proto.encode_message(*packet)

if __name__ == '__main__':
    unittest.main()
