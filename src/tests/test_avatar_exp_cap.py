"""Chip growth after a previously full avatar EXP bar; uses generated tables."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated ARM runtime')
class AvatarExpCapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.environ['BH3_TEST_RUNTIME'])
        import server19_portable as portable
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        portable.configure(cls.tmp.name)
        import server19_avatar_cultivation as cultivation
        cls.c = cultivation
        cls.tables = cultivation._tables()

    def setUp(self):
        self.account = dict(schema=1, uid=1024, main=dict(level=3),
            avatar_list=[dict(avatar_id=101, star=1, level=3, exp=0)],
            material_list=[dict(id=1001, num=100), dict(id=1006, num=5)],
            weapon_list=[], stigmata_list=[])
        self.path = Path(self.tmp.name, 'growth.json')

    def request(self, material=1001, amount=1):
        self.path.write_text(json.dumps(self.account))
        return self.c.response('AddAvatarExpByMaterialReq', self.account,
            dict(avatar_id=101, material_id=material, material_num=amount),
            account_path=self.path)[1]['retcode']

    def test_reported_level_three_full_bar_resumes_at_captain_four(self):
        self.account['main']['level'] = 4
        self.account['avatar_list'][0]['exp'] = self.tables['avatarleveldata'][2]['exp']
        self.assertEqual(self.request(), 0)
        self.assertGreater(self.account['avatar_list'][0]['level'], 3)
        self.assertEqual(self.account['material_list'][0]['num'], 99)
        self.assertEqual(json.loads(self.path.read_bytes()), self.account)

    def test_overflow_at_old_cap_then_captain_increase_resumes(self):
        caps = self.tables['playerleveldata']
        before, after = next((a, b) for a, b in zip(caps, caps[1:])
                             if a['avatarLevelLimit'] < b['avatarLevelLimit'])
        cap = before['avatarLevelLimit']
        self.account['main']['level'] = before['level']
        av = self.account['avatar_list'][0]
        av.update(level=cap, exp=0)
        self.assertEqual(self.request(1006), 0)
        av = self.account['avatar_list'][0]
        self.assertEqual((av['level'], av['exp']),
                         (cap, self.tables['avatarleveldata'][cap - 1]['exp']))
        self.account['main']['level'] = after['level']
        self.assertEqual(self.request(), 0)
        self.assertGreater(self.account['avatar_list'][0]['level'], cap)
        self.assertLessEqual(self.account['avatar_list'][0]['level'], after['avatarLevelLimit'])

    def test_current_cap_full_bar_still_rejects_without_consuming(self):
        cap = self.tables['playerleveldata'][2]['avatarLevelLimit']
        self.account['avatar_list'][0].update(level=cap,
            exp=self.tables['avatarleveldata'][cap - 1]['exp'])
        before = deepcopy(self.account)
        self.assertEqual(self.request(), 3)
        self.assertEqual(self.account, before)

    def test_invalid_exp_above_threshold_stays_atomic(self):
        self.account['avatar_list'][0]['exp'] = self.tables['avatarleveldata'][2]['exp'] + 1
        before = deepcopy(self.account)
        self.assertEqual(self.request(), 1)
        self.assertEqual(self.account, before)

    def test_insufficient_chips_does_not_normalize_or_consume(self):
        self.account['avatar_list'][0]['exp'] = self.tables['avatarleveldata'][2]['exp']
        before = deepcopy(self.account)
        self.assertEqual(self.request(amount=101), 4)
        self.assertEqual(self.account, before)

    def test_normal_growth_preserves_exp_and_consumes_one_chip(self):
        self.assertEqual(self.request(), 0)
        self.assertEqual((self.account['avatar_list'][0]['level'],
                          self.account['avatar_list'][0]['exp']), (4, 25))
        self.assertEqual(self.account['material_list'][0]['num'], 99)


if __name__ == '__main__':
    unittest.main()
