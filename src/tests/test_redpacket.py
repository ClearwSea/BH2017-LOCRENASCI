import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import server19_material_training as training
from packager.core import BuildError
from packager.material_training import adapt_redpacket_record_type


class RedPacketRulesTests(unittest.TestCase):
    def test_weekend_schedule_and_daily_limit(self):
        monday = datetime(2026, 11, 16, 12, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual([training.is_open(1301, monday + timedelta(days=d)) for d in range(7)],
                         [False, False, False, False, False, True, True])
        self.assertFalse(training.is_open(1301, datetime(2026, 11, 21, 3, 59, tzinfo=timezone(timedelta(hours=8)))))
        self.assertTrue(training.is_open(1301, datetime(2026, 11, 21, 4, 0, tzinfo=timezone(timedelta(hours=8)))))
        self.assertEqual(training.daily_limit(1301), 2)
        self.assertEqual([training.STAGE_ACTIVITY[i] for i in range(101601, 101605)], [1301] * 4)
        self.assertEqual(training.drop_plan(101601), [])

    def test_native_score_and_fivefold_payout(self):
        stage = types.ModuleType('server19_stage')
        def u32(value, _name):
            if type(value) is not int or not 0 <= value <= 0xffffffff:
                raise ValueError('invalid UInt32')
            return value
        stage._u32 = u32
        with patch.dict(sys.modules, {'server19_stage': stage}):
            for n in range(1, 5):
                self.assertEqual(training.redpacket_reward(101600 + n, 90, {'hardLevel': 15 * n}),
                                 (90 * 45 + n * 13500) * 5)
            with self.assertRaises(ValueError): training.redpacket_reward(101601, None, {'hardLevel': 15})
            with self.assertRaises(ValueError): training.redpacket_reward(101601, 90, {'hardLevel': 30})
            with self.assertRaises(ValueError): training.redpacket_reward(101601, 0xffffffff, {'hardLevel': 15})

    def test_record_type_changes_only_reviewed_rows(self):
        rows = [{'levelId': i, 'RecordLevelType': 0, 'other': 'preserved'}
                for i in range(101601, 101605)] + [{'levelId': 101501, 'RecordLevelType': 0}]
        expected = copy.deepcopy(rows)
        for row in expected[:4]: row['RecordLevelType'] = 1
        adapt_redpacket_record_type(rows)
        self.assertEqual(rows, expected)
        for invalid in (rows[:-2], rows + [copy.deepcopy(rows[0])]):
            before = copy.deepcopy(invalid)
            with self.assertRaises(BuildError): adapt_redpacket_record_type(invalid)
            self.assertEqual(invalid, before)

    def test_zero_display_sentinel_only_for_redpacket(self):
        path = Path(__file__).resolve().parents[1] / 'server19_stage_display.py'
        with patch.dict(sys.modules, {'server19_stage': types.ModuleType('server19_stage'),
                                     'server19_befall': types.ModuleType('server19_befall')}):
            spec = importlib.util.spec_from_file_location('redpacket_display_test', path)
            display = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(display)
        for identity in range(101601, 101605):
            self.assertEqual(display._record({'levelId': identity, 'displayDropList': [0],
                                              'firstDisplayDropList': []})['drop_item_id_list'], [])
        for identity, items in ((101600, [0]), (101601, [0, 1]), (101601, [False])):
            with self.assertRaises(ValueError):
                display._record({'levelId': identity, 'displayDropList': items, 'firstDisplayDropList': []})


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME') and os.environ.get('BH3_TEST_FIXTURE'),
                     'requires generated runtime and isolated fixture')
class RedPacketTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['BH3_TEST_RUNTIME'])
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location('server19_stage', Path(__file__).resolve().parents[1] / 'server19_stage.py')
        cls.stage = importlib.util.module_from_spec(spec)
        sys.modules['server19_stage'] = cls.stage
        spec.loader.exec_module(cls.stage)
        cls.stage.TABLE_DIRECTORY = root / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
        rows = cls.stage._table('stagedata_main', field='levelId', identities=range(101601, 101605))
        assert len(rows) == 4
        cls.rows = {row['levelId']: row for row in rows}
        cls.stage.stage_config = lambda identity=cls.stage.STAGE_ID: copy.deepcopy(cls.rows[identity])
        cls.stage.supported_stage_ids = lambda: tuple(cls.rows)
        cls.stage.notification_snapshot = lambda account: [('GetStageDataRsp', {
            'retcode': 0, 'stage_list': copy.deepcopy(account['stage_list'])})]
        cls.stage.player_progression.CAP_EXP_TO_SCOIN = True

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'account.json'
        self.account = json.loads(Path(os.environ['BH3_TEST_FIXTURE']).read_bytes())
        self.account['stage_list'] = []
        self.account.pop('stage_runtime', None)
        self.account.pop('material_training_runtime', None)
        self.account['main'].update(stamina=160, scoin=100000)
        self.path.write_text(json.dumps(self.account), encoding='utf8')
        self.open_patch = patch.object(training, 'is_open', return_value=True)
        self.open_patch.start()
        self.addCleanup(self.open_patch.stop)
        self.duty_patch = patch.dict(sys.modules, {'server19_duty': types.SimpleNamespace(note_event=lambda *args: None)})
        self.duty_patch.start()
        self.addCleanup(self.duty_patch.stop)

    def begin(self, identity):
        result = self.stage.response('StageBeginReq', self.account,
                {'stage_id': identity, 'avatar_id_list': [101, 0, 0]}, account_path=self.path)[1]
        self.assertEqual(result['retcode'], 0)
        return result

    def end_request(self, begin, score, client_coin=0, status=1):
        body = {'stage_id': begin['stage_id'], 'end_status': status, 'scoin_reward': client_coin,
                'avatar_exp_reward': 0, 'stage_pass_time': 180}
        if score is not None: body['score'] = score
        raw = self.stage.proto.encode_message('StageEndReqBody', body)
        return {'body': raw, 'sign': self.stage.stage_end_signature(raw, begin['sign_key'])}

    def test_win_retry_lower_score_and_no_double_client_coin(self):
        begin = self.begin(101601)
        self.assertEqual(self.account['main']['stamina'], 159)
        request = self.end_request(begin, 90, client_coin=17550)
        result = self.stage.response('StageEndReq', self.account, request, account_path=self.path)[1]
        self.assertEqual(result['retcode'], 0)
        # The level-80 EXP conversion is separate from the course payout.
        self.assertEqual(result['scoin_reward'], 87750 + 1)
        self.assertEqual(self.account['main']['scoin'], 100000 + 87750 + 1)
        self.assertEqual(self.account['stage_list'][0]['max_score'], 90)
        self.stage.proto.encode_message('Stage', self.account['stage_list'][0])
        after = copy.deepcopy(self.account)
        self.assertEqual(self.stage.response('StageEndReq', self.account, request, account_path=self.path)[1], result)
        self.assertEqual(self.account, after)
        second = self.begin(101601)
        self.assertEqual(self.stage.response('StageEndReq', self.account, self.end_request(second, 30), account_path=self.path)[1]['retcode'], 0)
        self.assertEqual(self.account['stage_list'][0]['max_score'], 90)
        self.assertEqual(training.completed_today(self.account, 1301), 2)
        self.assertNotEqual(self.stage.response('StageBeginReq', self.account, {'stage_id': 101601, 'avatar_id_list': [101,0,0]}, account_path=self.path)[1]['retcode'], 0)

    def test_missing_score_rejected_without_settlement_and_loss_has_no_payout(self):
        begin = self.begin(101602)
        before = copy.deepcopy(self.account)
        result = self.stage.response('StageEndReq', self.account, self.end_request(begin, None), account_path=self.path)[1]
        self.assertNotEqual(result['retcode'], 0)
        self.assertEqual(self.account, before)
        result = self.stage.response('StageEndReq', self.account, self.end_request(begin, None, status=3), account_path=self.path)[1]
        self.assertEqual(result['retcode'], 0)
        self.assertEqual(self.account['main']['scoin'], 100000)
        self.assertEqual(training.completed_today(self.account, 1301), 0)

    def test_zero_score_is_a_real_report_and_gives_base_reward(self):
        begin = self.begin(101604)
        self.assertEqual(self.account['main']['stamina'], 155)
        result = self.stage.response('StageEndReq', self.account, self.end_request(begin, 0), account_path=self.path)[1]
        self.assertEqual(result['retcode'], 0)
        self.assertEqual(result['scoin_reward'], 4 * 13500 * 5 + 5)
        self.assertEqual(self.account['stage_list'][0]['max_score'], 0)


if __name__ == '__main__':
    unittest.main()
