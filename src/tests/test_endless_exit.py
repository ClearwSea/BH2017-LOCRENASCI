import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Keep these settlement tests independent of extracted client metadata.
spec = importlib.util.spec_from_file_location('endless_exit_under_test', Path(__file__).parents[1] / 'server19_endless.py')
endless = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'server19_stage': types.SimpleNamespace(_u32=lambda value, label: value), 'server19_protocol': types.SimpleNamespace()}):
    spec.loader.exec_module(endless)

class EndlessExitTests(unittest.TestCase):
    def setUp(self):
        endless.CATALOG = {'floors': 33, 'item_ids': [70001]}
        period = patch.object(endless, 'calendar', return_value=(1794168000, 1794427200))
        period.start()
        self.addCleanup(period.stop)
        self.now = 1794208389
        self.account = {'uid': 1024, 'main': {'level': 80, 'scoin': 100, 'hcoin': 20},
                        'avatar_list': [{'avatar_id': i, 'star': 1} for i in (401, 304, 312)]}
        result = endless._handle('EndlessStageBeginReq', self.account, {'avatar_id_list': [401, 304, 312]}, self.now - 30)
        self.assertEqual(result['retcode'], 0)
        # Exact decoded values from the native 1.9 voluntary-exit packet.
        self.request = {'end_status': 4, 'avatar_hp_list': [
            {'avatar_id': 401, 'hp_percent': 48, 'next_recover_time': 0, 'is_die': False, 'sp_percent': 1},
            {'avatar_id': 312, 'hp_percent': 50, 'next_recover_time': 0, 'is_die': False, 'sp_percent': 0},
            {'avatar_id': 304, 'hp_percent': 50, 'next_recover_time': 0, 'is_die': False, 'sp_percent': 3}],
            'cheat_type': 0, 'stage_pass_time': 12}

    def test_captured_exit_closes_battle_without_rewards_and_allows_reordered_team(self):
        before = copy.deepcopy(self.account)
        result = endless._handle('EndlessStageEndReq', self.account, self.request, self.now)
        self.assertEqual(result['retcode'], 0)
        self.assertEqual(result['end_status'], 4)
        s = self.account['endless_runtime']
        self.assertIsNone(s['active'])
        self.assertEqual(s['progress'], 0)
        self.assertEqual(s['claimed_floors'], [])
        self.assertEqual(self.account['main'], before['main'])
        self.assertEqual(s['items'], before['endless_runtime']['items'])
        self.assertEqual({h['avatar_id']: (h['hp_percent'], h['sp_percent']) for h in s['hp']}, {401: (48, 1), 312: (50, 0), 304: (50, 3)})
        self.assertTrue(all(h['next_recover_time'] == self.now + 3600 for h in s['hp']))
        self.assertEqual(endless._handle('EndlessStageBeginReq', self.account, {'avatar_id_list': [401, 312, 304]}, self.now + 1)['retcode'], 0)

    def test_exit_retry_is_idempotent(self):
        first = endless._handle('EndlessStageEndReq', self.account, self.request, self.now)
        saved = copy.deepcopy(self.account)
        self.assertEqual(endless._handle('EndlessStageEndReq', self.account, self.request, self.now), first)
        self.assertEqual(self.account, saved)

    def test_invalid_status_remains_rejected(self):
        self.request['end_status'] = 5
        self.assertEqual(endless._handle('EndlessStageEndReq', self.account, self.request, self.now)['retcode'], 1)
        self.assertIsNotNone(self.account['endless_runtime']['active'])

    def test_invalid_hp_remains_rejected(self):
        self.request['avatar_hp_list'][0]['hp_percent'] = 101
        self.assertEqual(endless._handle('EndlessStageEndReq', self.account, self.request, self.now)['retcode'], 1)
        self.assertIsNotNone(self.account['endless_runtime']['active'])

    def test_victory_still_advances_and_awards_once(self):
        self.request['end_status'] = 1
        result = endless._handle('EndlessStageEndReq', self.account, self.request, self.now)
        self.assertEqual(result['retcode'], 0)
        self.assertEqual(self.account['endless_runtime']['progress'], 1)
        self.assertEqual(self.account['main']['scoin'], 1100)
        saved = copy.deepcopy(self.account)
        endless._handle('EndlessStageEndReq', self.account, self.request, self.now)
        self.assertEqual(self.account, saved)
