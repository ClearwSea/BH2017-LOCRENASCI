"""Login/session ordering regression without game assets or a live save."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

class LoginOrderingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('session_under_test', Path(__file__).resolve().parents[1] / 'server19_battle_session.py')
        self.m = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'server19_stage': types.ModuleType('server19_stage')}):
            spec.loader.exec_module(self.m)
        self.m.recover = Mock(return_value={'cleared': {}, 'backup': None})
        self.account = {'stage_runtime': {'active': {'id': 1}}}
        self.event = Mock()
        self.path = Path('unused-account.json')

    def frame(self, session, name):
        with session.frame(name, self.account, self.path, self.event):
            pass

    def test_heartbeat_between_token_and_login_does_not_disconnect_or_claim_account(self):
        session = self.m.Session()
        for name in ('KeepAliveNotify', 'GetPlayerTokenReq', 'KeepAliveNotify'):
            self.frame(session, name)
        self.assertFalse(session.logged_in)
        self.assertEqual(self.m.OWNERS, {})
        self.m.recover.assert_not_called()
        self.assertEqual(self.account['stage_runtime']['active'], {'id': 1})
        self.frame(session, 'PlayerLoginReq')
        self.frame(session, 'KeepAliveNotify')
        self.frame(session, 'PlayerLoginReq')
        self.assertTrue(session.logged_in)
        self.m.recover.assert_called_once()

    def test_business_requests_still_require_login(self):
        for name in ('GetMainDataReq', 'StageBeginReq', 'EndlessStageEndReq', 'EquipmentSellReq'):
            with self.subTest(name=name):
                with self.assertRaises(ConnectionAbortedError):
                    self.frame(self.m.Session(), name)
        self.m.recover.assert_not_called()

    def test_prelogin_heartbeat_does_not_retire_existing_owner(self):
        old, new = self.m.Session(), self.m.Session()
        self.frame(old, 'PlayerLoginReq')
        self.frame(new, 'KeepAliveNotify')
        self.assertFalse(old.retired)
        self.frame(new, 'PlayerLoginReq')
        self.assertTrue(old.retired)
        for name in ('KeepAliveNotify', 'StageEndReq'):
            with self.assertRaises(ConnectionAbortedError):
                self.frame(old, name)

if __name__ == '__main__':
    unittest.main()
