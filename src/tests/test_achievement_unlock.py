"""Achievement publication must respect tutorial-triggering level gates."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "achievement_under_test", Path(__file__).resolve().parents[1] / "server19_achievement.py")
achievement = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"server19_stage": types.ModuleType("server19_stage")}):
    spec.loader.exec_module(achievement)


class AchievementUnlockTests(unittest.TestCase):
    def setUp(self):
        achievement._LINEAR = {
            55020: dict(MissionID=55020, PreMissionId=0, MinLevel=16, IsAchievement=1),
            55021: dict(MissionID=55021, PreMissionId=55020, MinLevel=30, IsAchievement=1),
            50101: dict(MissionID=50101, PreMissionId=0, MinLevel=1, IsAchievement=1),
        }
        achievement._MISSIONS = {
            mid: dict(id=mid, finishWay=104, totalProgress=1) for mid in (55020, 55021)}
        achievement._MISSIONS[50101] = dict(id=50101, finishWay=36, totalProgress=10)
        achievement._REWARDS = {}

    def rows(self, level, claimed=()):
        account = dict(main=dict(level=level),
                       achievement_runtime=dict(claimed_ids=list(claimed)))
        return {r['mission_id']: r for r in achievement.achievement_rows(account)}

    def test_first_cycle_appears_at_source_level(self):
        for level in (1, 15):
            self.assertNotIn(55020, self.rows(level))
            self.assertIn(50101, self.rows(level))
        self.assertEqual(self.rows(16)[55020]['status'], achievement.MISSION_DOING)

    def test_next_cycle_requires_level_and_predecessor(self):
        self.assertNotIn(55021, self.rows(29, [55020]))
        self.assertNotIn(55021, self.rows(30))
        self.assertEqual(self.rows(30, [55020])[55021]['status'], achievement.MISSION_DOING)

    def test_imported_claimed_history_stays_closed(self):
        self.assertEqual(self.rows(1, [55020])[55020]['status'], achievement.MISSION_CLOSE)
        self.assertNotIn(55021, self.rows(1, [55020]))


if __name__ == '__main__':
    unittest.main()
