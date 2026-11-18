import unittest
import os
import sys

if os.environ.get('BH3_TEST_RUNTIME'):
    sys.path.insert(0, os.environ['BH3_TEST_RUNTIME'])
    import server19_endless as endless
    from server19_endless import INFINITE_LEADERS
    from server19_exboss_rank import leaderboard


@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME'), 'requires generated protocol schema')
class ExBossRankTest(unittest.TestCase):
    def setUp(self):
        self.account = {'uid': 1024, 'main': {'nickname': 'player'}}
        self.names = ['captain-%03d' % i for i in range(149)]

    def rank(self, score, now=150, rank_id=103):
        return leaderboard(self.account, 100, 200, now, score, 120, rank_id, self.names, 32000)

    def test_fixed_leaders_and_endless_uids_always_outrank_player(self):
        for score in (1, 20000, 31996):
            result = self.rank(score)
            first = result['rank_list'][:3]
            self.assertEqual([x['nickname'] for x in first], list(INFINITE_LEADERS))
            self.assertEqual([x['uid'] for x in first], [900000000, 900000001, 900000002])
            self.assertTrue(all(x['score'] > score for x in first))
            self.assertGreaterEqual(result['my_rank']['rank'], 4)

        capped = self.rank(32000)
        self.assertEqual([x['score'] for x in capped['rank_list'][:3]], [32000] * 3)
        self.assertGreaterEqual(capped['my_rank']['rank'], 4)

    def test_population_is_deterministic_and_advances_with_time(self):
        self.assertEqual(self.rank(18000), self.rank(18000))
        self.assertGreaterEqual(self.rank(18000, 190)['my_rank']['rank'],
                                self.rank(18000, 110)['my_rank']['rank'])
        self.assertEqual(self.rank(0)['my_rank']['rank'], 0)

    def test_distinct_groups_and_requested_leaders(self):
        expected = {
            101: ['第二名我求你了', '我就差一分啊！', '差两分睡不着'],
            102: ['停手吧你没机会的', '差一分你给我等着', '第二名也给我等着'],
            103: list(INFINITE_LEADERS),
        }
        names, ids = set(), set()
        for group in (101, 102, 103):
            rows = self.rank(18000, rank_id=group)['rank_list']
            self.assertEqual([row['nickname'] for row in rows[:3]], expected[group])
            self.assertFalse(names & {row['nickname'] for row in rows})
            self.assertFalse(ids & {row['uid'] for row in rows})
            names.update(row['nickname'] for row in rows)
            ids.update(row['uid'] for row in rows)


if __name__ == '__main__':
    unittest.main()
