import json
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if os.environ.get('BH3_TEST_RUNTIME'):
    sys.path.insert(0, os.environ['BH3_TEST_RUNTIME'])
    spec = importlib.util.spec_from_file_location('server19_gacha', Path(__file__).resolve().parents[1] / 'server19_gacha.py')
    gacha = importlib.util.module_from_spec(spec)
    sys.modules['server19_gacha'] = gacha
    spec.loader.exec_module(gacha)
    import server19_duty as duty
    import server19_missions as missions


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated protocol schema')
class TicketRefreshTest(unittest.TestCase):
    def test_committed_zero_count_survives_until_wire_snapshot_for_all_pools(self):
        for channel in (2, 3, 5, 10):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as directory:
                ticket = gacha.CHANNELS[channel]['ticket_material_id']
                account = {'schema': 1, 'uid': 1024, 'main': {'hcoin': 0},
                           'material_list': [{'id': ticket, 'num': 10}],
                           'avatar_list': [], 'weapon_list': [], 'stigmata_list': []}
                path = Path(directory) / 'account.json'
                path.write_text(json.dumps(account), encoding='utf8')
                def pull(current, values):
                    return {'retcode': gacha._charge(current, channel, 10, False)}
                with patch.dict(gacha._HANDLERS, {'GachaReq': pull}), \
                     patch.object(duty, 'note_event'), patch.object(missions, 'note_event'):
                    _, response = gacha.response('GachaReq', account, {}, account_path=path)
                self.assertEqual(response['retcode'], 0)
                self.assertNotIn(ticket, [row['id'] for row in account['material_list']])
                packet = dict(gacha.notification_snapshot(account, consume_ticket_updates=True))['GetEquipmentDataRsp']
                self.assertIn({'id': ticket, 'num': 0}, packet['material_list'])
                again = dict(gacha.notification_snapshot(account, consume_ticket_updates=True))['GetEquipmentDataRsp']
                self.assertNotIn(ticket, [row['id'] for row in again['material_list']])

    def test_failed_pull_does_not_emit_a_zero_ticket_update(self):
        with tempfile.TemporaryDirectory() as directory:
            ticket = gacha.CHANNELS[10]['ticket_material_id']
            account = {'schema': 1, 'uid': 1024, 'main': {'hcoin': 0},
                       'material_list': [{'id': ticket, 'num': 9}],
                       'avatar_list': [], 'weapon_list': [], 'stigmata_list': []}
            path = Path(directory) / 'account.json'
            path.write_text(json.dumps(account), encoding='utf8')
            def pull(current, values):
                return {'retcode': gacha._charge(current, 10, 10, False)}
            with patch.dict(gacha._HANDLERS, {'GachaReq': pull}):
                _, response = gacha.response('GachaReq', account, {}, account_path=path)
            self.assertNotEqual(response['retcode'], 0)
            packet = dict(gacha.notification_snapshot(account, consume_ticket_updates=True))['GetEquipmentDataRsp']
            self.assertEqual(packet['material_list'], [{'id': ticket, 'num': 9}])


if __name__ == '__main__':
    unittest.main()
