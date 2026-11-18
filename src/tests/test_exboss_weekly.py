import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if os.environ.get('BH3_TEST_RUNTIME'):
    sys.path.insert(0, os.environ['BH3_TEST_RUNTIME'])
    import server19_exboss as ex
    import server19_stage as stage
    import server19_endless as endless


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated protocol schema')
class WeeklyExBossTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'account.json'
        self.now = ex.ROTATION_EPOCH + 3600
        self.account = {'schema': 1, 'uid': 1024, 'main': {'nickname': 'test', 'level': 80},
                        'avatar_list': [dict(avatar_id=i, star=1, weapon_unique_id=i,
                                             stigmata_unique_id_1=20000+i)
                                        for i in range(1, 5)]}
        self.path.write_text(json.dumps(self.account), encoding='utf8')
        self.old_catalog = endless.CATALOG
        endless.CATALOG = {'bot_names': ['captain-%03d' % i for i in range(100)]}
        self.addCleanup(setattr, endless, 'CATALOG', self.old_catalog)

        def table(name, **kwargs):
            if name == 'exbossmonsterdata':
                return [{'BossId': i, 'BossNextId': i if i % 1000 == 5 else i + 1,
                         'MonsterBaseScore': 16000} for i in kwargs['identities']]
            if name == 'exbossscorereward':
                return []
            if name == 'exbossrankreward':
                return [{'configId': 103, 'scheduleId': 0, 'rank': 20, 'rewardId': 777}]
            if name == 'rewarddata':
                return [dict(RewardID=777, RewardExp=0, RewardSCoin=30, RewardHCoin=0,
                             RewardStamina=0, RewardSkillPoint=0, RewardFriendPoint=0,
                             RewardDutyPoint=0, **{f'RewardItem{i}ID': 0 for i in range(1, 6)})]
            if name == 'medaldata':
                return [{'medalID': 101036, 'timeType': 2, 'during': 10080}]
            raise AssertionError(name)
        self.table_patch = patch.object(stage, '_table', side_effect=table)
        self.table_patch.start()
        self.addCleanup(self.table_patch.stop)

    def call(self, name, values=None, now=None):
        return ex.response(name, self.account, values or {}, account_path=self.path,
                           now=self.now if now is None else now)[1]

    def test_rotation_and_boundaries(self):
        self.assertEqual(ex._roots(ex.ROTATION_EPOCH), (1001, 201, 3001))
        self.assertEqual(ex._roots(ex.ROTATION_EPOCH + 7 * 86400), (4001, 501, 601))
        self.assertEqual(ex._roots(ex.ROTATION_EPOCH + 14 * 86400), (701, 8001, 9001))
        self.assertEqual(ex.period(ex.ROTATION_EPOCH - 1)[0], ex.ROTATION_EPOCH - 7 * 86400)
        self.assertEqual(ex.period(ex.ROTATION_EPOCH)[0], ex.ROTATION_EPOCH)
        info = self.call('GetExBossInfoReq')['boss_info']
        self.assertEqual([v['boss_id'] for v in info['boss_id_list']], [1001, 201, 3001])

    def test_schedule_is_visible_before_unlock_and_other_requests_are_rejected(self):
        self.account['main']['level'] = 37
        self.path.write_text(json.dumps(self.account), encoding='utf8')
        self.assertEqual(self.call('GetExBossScheduleReq')['min_level'], 38)
        self.assertEqual(self.call('GetExBossInfoReq')['retcode'], 1)

    def test_failures_consume_daily_limit_and_next_day_resets(self):
        for _ in range(5):
            self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]})['retcode'], 0)
            self.assertEqual(self.call('ExBossStageEndReq', {'boss_id': 1001, 'end_status': 2, 'score': 0})['retcode'], 0)
        self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]})['retcode'], 1)
        self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]}, self.now + 86400)['retcode'], 0)

    def test_low_and_middle_groups_have_four_attempts(self):
        for level in (38, 55, 56, 69):
            with self.subTest(level=level):
                self.account.pop('exboss_runtime', None)
                self.account['main']['level'] = level
                self.path.write_text(json.dumps(self.account), encoding='utf8')
                for _ in range(4):
                    self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]})['retcode'], 0)
                    self.assertEqual(self.call('ExBossStageEndReq', {'boss_id': 1001, 'end_status': 2, 'score': 0})['retcode'], 0)
                self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]})['retcode'], 1)

    def test_victory_locks_character_and_equipment_across_bosses(self):
        self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]})
        self.call('ExBossStageEndReq', {'boss_id': 1001, 'end_status': 1, 'score': 1900})
        self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 201, 'avatar_id_list': [1]})['retcode'], 1)
        self.account['avatar_list'][1]['weapon_unique_id'] = 1
        self.path.write_text(json.dumps(self.account), encoding='utf8')
        self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 201, 'avatar_id_list': [2]})['retcode'], 1)
        self.assertEqual(self.call('ExBossStageBeginReq', {'boss_id': 201, 'avatar_id_list': [3]})['retcode'], 0)

    def test_weekly_rank_reward_exactly_once_after_restart(self):
        self.account['main']['scoin'] = 0
        self.path.write_text(json.dumps(self.account), encoding='utf8')
        self.call('ExBossStageBeginReq', {'boss_id': 1001, 'avatar_id_list': [1]})
        self.call('ExBossStageEndReq', {'boss_id': 1001, 'end_status': 1, 'score': 95000})
        next_week = ex.ROTATION_EPOCH + 7 * 86400
        self.assertEqual(self.call('GetExBossScheduleReq', now=next_week)['retcode'], 0)
        self.assertEqual(self.account['main']['scoin'], 0)
        self.assertFalse(self.account['exboss_rank_receipts'][0]['claimed'])
        self.assertEqual(self.call('GetExBossInfoReq', now=next_week)['retcode'], 0)
        self.assertEqual(self.account['main']['scoin'], 30)
        self.assertEqual(len(self.account['exboss_rank_receipts']), 1)
        self.assertTrue(self.account['exboss_rank_receipts'][0]['claimed'])
        self.call('GetExBossInfoReq', now=next_week + 1)
        self.assertEqual(self.account['main']['scoin'], 30)
        self.assertEqual(len(ex.take_notifications(self.account, self.path)), 1)
        self.assertEqual(ex.take_notifications(self.account, self.path), [])

    def test_original_timed_medal_is_granted_and_renewed(self):
        self.account['main']['scoin'] = 0
        reward = {'exp': 0, 'scoin': 0, 'hcoin': 0, 'stamina': 0, 'skill_point': 0,
                  'friends_point': 0, 'duty_point': 0,
                  'item_list': [{'id': 101036, 'level': 0, 'num': 1}]}
        ex._grant(self.account, reward, self.now)
        self.assertEqual(self.account['medal_list'], [{'id': 101036, 'end_time': self.now + 7 * 86400}])
        ex._grant(self.account, reward, self.now + 86400)
        self.assertEqual(self.account['medal_list'], [{'id': 101036, 'end_time': self.now + 14 * 86400}])


if __name__ == '__main__':
    unittest.main()
