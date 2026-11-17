"""Shared skill purchases and legacy saves using the packaged game tables."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated ARM runtime')
class AwakenedSharedSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.environ['BH3_TEST_RUNTIME'])
        import server19_portable as portable
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        portable.configure(cls.tmp.name)
        import server19_avatar_skills as skills
        import server19_avatar_cultivation as cultivation
        import server19_stage as stage
        cls.skills, cls.cultivation, cls.stage = skills, cultivation, stage

    def setUp(self):
        self.account = {'schema': 1, 'uid': 1024,
            'main': {'scoin': 100000, 'skill_point': 50, 'skill_point_limit': 50},
            'avatar_list': [{'avatar_id': i, 'star': star, 'level': 80, 'skill_list': []}
                            for i, star in ((201, 4), (211, 2), (203, 4), (213, 2))],
            'material_list': [], 'weapon_list': [], 'stigmata_list': []}

    def level(self, avatar, skill, sub):
        a = next(row for row in self.account['avatar_list'] if row['avatar_id'] == avatar)
        return next((x['level'] for s in a['skill_list'] if s['skill_id'] == skill
                     for x in s['sub_skill_list'] if x['sub_skill_id'] == sub), 0)

    def upgrade(self, avatar, skill, sub):
        with patch('server19_duty.note_event'):
            return self.skills._upgrade(self.account,
                {'avatar_id': avatar, 'skill_id': skill, 'sub_skill_id': sub}, now=1800000000)

    def test_client_base_request_updates_both_sides_once(self):
        self.assertEqual(self.upgrade(201, 53, 514)['retcode'], 0)
        self.assertEqual((self.level(201, 53, 514), self.level(211, 176, 1714)), (1, 1))
        self.assertEqual(self.account['main']['skill_point'], 42)
        self.assertEqual(self.upgrade(201, 53, 514)['retcode'], 0)
        self.assertEqual((self.level(201, 53, 514), self.level(211, 176, 1714)), (2, 2))
        self.assertEqual(self.account['main']['skill_point'], 39)

    def test_reported_mei_pair_and_legacy_progress(self):
        self.assertEqual(self.upgrade(203, 76, 714)['retcode'], 0)
        self.assertEqual((self.level(203, 76, 714), self.level(213, 256, 2503)), (1, 1))
        self.assertEqual(self.upgrade(203, 76, 713)['retcode'], 0)
        self.assertEqual((self.level(203, 76, 713), self.level(213, 256, 2502)), (1, 1))
        base = next(a for a in self.account['avatar_list'] if a['avatar_id'] == 203)
        base['skill_list'] = []
        before = deepcopy(self.account['main'])
        self.cultivation.synchronize_common_skills(self.account)
        self.assertEqual((self.level(203, 76, 714), self.level(213, 256, 2503)), (1, 1))
        self.assertEqual((self.level(203, 76, 713), self.level(213, 256, 2502)), (1, 1))
        self.assertEqual(self.account['main'], before)

    def test_locked_partner_does_not_get_skills(self):
        next(a for a in self.account['avatar_list'] if a['avatar_id'] == 211)['star'] = 0
        self.assertEqual(self.upgrade(201, 53, 514)['retcode'], 0)
        self.assertEqual(self.level(211, 176, 1714), 0)

    def test_old_save_is_persisted_and_idempotent(self):
        self.upgrade(201, 53, 514)
        next(a for a in self.account['avatar_list'] if a['avatar_id'] == 211)['skill_list'] = []
        path = Path(self.tmp.name) / 'shared-skills.json'
        path.write_text(json.dumps(self.account), encoding='utf8')
        before = deepcopy(self.account['main'])
        self.skills.synchronize_common_skills(self.account, account_path=path)
        self.assertEqual((self.level(201, 53, 514), self.level(211, 176, 1714)), (1, 1))
        self.assertEqual(json.loads(path.read_bytes()), self.account)
        self.assertEqual(self.account['main'], before)
        first = path.read_bytes()
        self.skills.synchronize_common_skills(self.account, account_path=path)
        self.assertEqual(path.read_bytes(), first)

    def test_rejected_purchase_does_not_spend_or_change_save(self):
        self.account['main']['skill_point'] = 0
        path = Path(self.tmp.name) / 'rejected-skill.json'
        path.write_text(json.dumps(self.account), encoding='utf8')
        original = path.read_bytes()
        result = self.skills.response('AvatarSubSkillLevelUpReq', self.account,
            {'avatar_id': 201, 'skill_id': 53, 'sub_skill_id': 514},
            account_path=path, now=1800000000)
        self.assertEqual(result[1]['retcode'], 8)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual((self.level(201, 53, 514), self.level(211, 176, 1714)), (0, 0))

    def test_all_available_table_mappings_sync_in_both_directions(self):
        subs = {r['avatarSubSkillId']: r for r in self.stage._table('avatarsubskilldata')}
        checked = 0
        for pair in self.stage._table('avatarexdata'):
            for mapping in pair.get('commonSubSkillList', []):
                a, b = (tuple(map(int, mapping[key].split('-'))) for key in ('Skill1', 'Skill2'))
                if any(i[2] not in subs or subs[i[2]]['skillId'] != i[1] for i in (a, b)):
                    continue
                for source, target in ((a, b), (b, a)):
                    with self.subTest(source=source, target=target):
                        account = {'avatar_list': [
                            {'avatar_id': source[0], 'star': 2, 'skill_list': [
                                {'skill_id': source[1], 'sub_skill_list': [
                                    {'sub_skill_id': source[2], 'level': 1, 'is_mask': False}]}]},
                            {'avatar_id': target[0], 'star': 2, 'skill_list': []}]}
                        self.cultivation.synchronize_common_skills(account)
                        actual = account['avatar_list'][1]['skill_list'][0]
                        self.assertEqual((actual['skill_id'], actual['sub_skill_list'][0]['sub_skill_id'],
                                          actual['sub_skill_list'][0]['level']), (target[1], target[2], 1))
                    checked += 1
        self.assertGreater(checked, 0)


if __name__ == '__main__':
    unittest.main()
