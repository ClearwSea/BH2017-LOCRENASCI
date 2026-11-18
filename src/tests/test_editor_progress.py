import copy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
import server19_editor_progress as editor
import server19_editor_templates as templates


def load_source(name, modules):
    path = Path(__file__).resolve().parents[1] / (name + '.py')
    spec = importlib.util.spec_from_file_location('_editor_test_' + name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


stage = load_source('server19_stage', {'server19_protocol': ModuleType('server19_protocol'),
                                      'server19_player_progression': ModuleType('server19_player_progression')})
missions = ModuleType('server19_missions')
missions._confirmed_wins = lambda account: set()
commissions = ModuleType('server19_commissions'); commissions.REQUESTS = frozenset()
cooking = ModuleType('server19_cooking'); cooking.REQUESTS = frozenset()
areas = ModuleType('server19_sakura_areas'); areas.state = lambda *args: []
service = load_source('server19_openworld', {'server19_stage': stage,
                      'server19_commissions': commissions, 'server19_cooking': cooking})


def row(i, pre=(), stars=0, difficulty=1, kind='story', chapter=1):
    return dict(id=i, chapterId=chapter, difficulty=difficulty, unlockPlayerLevel=1,
                unlockStarNum=stars, maxProgress=1, preLevelID=list(pre), challengeList=[{}, {}, {}], kind=kind)


def base():
    return {'main': {'level': 80, 'scoin': 123, 'hcoin': 12}, 'stage_list': [],
            'stage_runtime': {'schema': 1, 'active': None, 'settlements': []},
            'mission_runtime': {'claimed_ids': [987]}, 'unknown': {'keep': True}}


class EditorProgressTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {'stages': [row(1), row(2, [1]), row(3, [2], 4)], 'abyss_floors': 33}

    def test_unlock_and_star_gate(self):
        original = base(); before = copy.deepcopy(original)
        edited, _ = editor.apply(original, self.catalog, {'op': 'story_unlock', 'stage_id': 3})
        self.assertEqual(original, before)
        records = {r['id']: r for r in edited['stage_list']}
        self.assertEqual(set(records), {1, 2})
        self.assertTrue(records[1]['is_done'] and records[2]['is_done'])
        self.assertEqual(sum(len(r['challenge_index_list']) for r in records.values()), 4)
        self.assertEqual(edited['stage_runtime']['settlements'], [])
        self.assertEqual(edited['mission_runtime'], original['mission_runtime'])
        configs = {r['id']: r for r in self.catalog['stages']}
        with patch.dict(sys.modules, {'server19_missions': missions}), \
             patch.object(stage, 'stage_config', side_effect=lambda i: configs[i]), \
             patch.object(missions, '_confirmed_wins', return_value=set()):
            self.assertEqual(stage.chapter_star_count(edited, 1, 1), 4)
            records[1]['challenge_index_list'] = []
            self.assertEqual(stage.chapter_star_count(edited, 1, 1), 1)

    def test_preserve_existing_target_and_later(self):
        source = base()
        source['stage_list'] = [{'id': 3, 'is_done': True, 'progress': 1, 'challenge_index_list': [0]},
                                {'id': 88, 'opaque': 42}]
        edited, _ = editor.apply(source, self.catalog, {'op': 'story_unlock', 'stage_id': 3})
        self.assertEqual(edited['stage_list'][:2], source['stage_list'])

    def test_real_win_count(self):
        source = base()
        source['stage_list'] = [{'id': 1, 'is_done': True, 'progress': 1, 'challenge_index_list': [0, 2]}]
        with patch.dict(sys.modules, {'server19_missions': missions}), \
             patch.object(stage, 'stage_config', return_value=self.catalog['stages'][0]), \
             patch.object(missions, '_confirmed_wins', return_value={1}):
            self.assertEqual(stage.chapter_star_count(source, 1, 1), 2)

    def test_max_stars_scoped_no_claim(self):
        catalog = {'stages': [row(1), row(2, difficulty=2), row(3, kind='extra')]}
        source = base()
        edited, _ = editor.apply(source, catalog, {'op': 'story_max_stars', 'chapter_id': 1, 'difficulty': 1, 'kind': 'story'})
        self.assertEqual([r['id'] for r in edited['stage_list']], [1])
        self.assertEqual(edited['stage_list'][0]['challenge_index_list'], [0, 1, 2])
        self.assertEqual(edited['stage_runtime'], source['stage_runtime'])
        self.assertEqual(edited['mission_runtime'], source['mission_runtime'])

    def test_extra_story_uses_navigation_chapter_not_native_zero(self):
        first, second = row(20, chapter=0, kind='extra'), row(21, chapter=0, kind='extra')
        first['editor_chapter_id'], second['editor_chapter_id'] = 1, 2
        catalog = {'stages': [first, second]}
        edited, _ = editor.apply(base(), catalog, {'op': 'story_max_stars', 'chapter_id': 1,
                                                  'difficulty': 1, 'kind': 'extra'})
        self.assertEqual([r['id'] for r in edited['stage_list']], [20])

    def fixture(self):
        source = base()
        source['openworld_data'] = {'cycle': 1, 'finish_story_id_list': [101, 102],
             'cur_story_list': [], 'servant_level': 0, 'spawn_point': 'client-owned'}
        source['openworld_runtime'] = {'schema': 1, 'active': None, 'avatars': [],
             'receipts': {'101': {'reward': {'scoin': 10}}, '102': {'reward': {'scoin': 10}}},
             'cycle_receipts': {'1': {'reward': {}}}, 'area_teams': [1]}
        catalog = {'sakura': {'cycle': {'level': 16}, 'stories': [
            {'StoryID': 101, 'Cycle': 1, 'PreStory': [0], 'MaxCount': 1},
            {'StoryID': 102, 'Cycle': 1, 'PreStory': [101], 'MaxCount': 1},
            {'StoryID': 103, 'Cycle': 1, 'PreStory': [102], 'MaxCount': 1}]}}
        return source, catalog

    def test_rewind_and_replay(self):
        source, catalog = self.fixture()
        edited, _ = editor.apply(source, catalog, {'op': 'sakura_set_part', 'cycle': 1, 'story_id': 102})
        self.assertEqual(edited['openworld_data']['finish_story_id_list'], [101])
        self.assertEqual(edited['openworld_runtime']['receipts'], source['openworld_runtime']['receipts'])
        self.assertEqual(edited['openworld_runtime']['cycle_receipts'], source['openworld_runtime']['cycle_receipts'])
        edited['openworld_data']['cur_story_list'] = [{'story_id': 102, 'story_progress': 0}]
        with patch.dict(sys.modules, {'server19_sakura_areas': areas}), \
             patch.object(service, '_CATALOG', catalog['sakura']), patch.object(service, '_COMMISSIONS', None), \
             patch.object(service, '_COOKING', None), patch.object(areas, 'state', return_value=[]):
            self.assertEqual(service._handle('TakeOpenworldStoryRewardReq', edited, {'story_id': 102}), {'retcode': 1})
            edited['openworld_data']['cur_story_list'][0]['story_progress'] = 1
            response = service._handle('TakeOpenworldStoryRewardReq', edited, {'story_id': 102})
        self.assertEqual(response, {'retcode': 0, 'reward_list': []})
        self.assertEqual(edited['openworld_data']['finish_story_id_list'], [101, 102])
        self.assertEqual(edited['openworld_data']['cur_story_list'], [])
        self.assertEqual(edited['main'], source['main'])
        self.assertEqual(edited['openworld_runtime']['receipts'], source['openworld_runtime']['receipts'])

    def test_legacy_unknown_reward_rewind_rejected(self):
        source, catalog = self.fixture(); del source['openworld_runtime']['receipts']['102']
        before = copy.deepcopy(source)
        with self.assertRaisesRegex(ValueError, '缺少领奖记录'):
            editor.apply(source, catalog, {'op': 'sakura_set_part', 'cycle': 1, 'story_id': 102})
        self.assertEqual(source, before)

    def test_editor_skipped_can_revisit(self):
        source, catalog = self.fixture()
        source['openworld_data']['finish_story_id_list'] = [101]
        del source['openworld_runtime']['receipts']['102']
        forward, _ = editor.apply(source, catalog, {'op': 'sakura_set_part', 'cycle': 1, 'story_id': 103})
        self.assertEqual(forward['openworld_editor_skipped'], [102])
        back, _ = editor.apply(forward, catalog, {'op': 'sakura_set_part', 'cycle': 1, 'story_id': 102})
        self.assertNotIn('102', back['openworld_runtime']['receipts'])

    def test_legacy_cycle_claim_without_receipt_is_not_replayed(self):
        source, catalog = self.fixture()
        source['openworld_data']['has_take_finish_reward_cycle'] = 1
        source['openworld_runtime']['cycle_receipts'] = {}
        with self.assertRaisesRegex(ValueError, '结算奖励缺少回执'):
            editor.apply(source, catalog, {'op': 'sakura_set_part', 'cycle': 1, 'story_id': 102})

    def test_abyss_preserves_claims(self):
        source = base()
        source['endless_runtime'] = {'begin': 100, 'end': 300, 'group': 2, 'progress': 10,
             'max_progress': 20, 'progress_time': 100, 'active': None, 'claimed_floors': [1, 2, 3]}
        edited, _ = editor.apply(source, self.catalog, {'op': 'abyss_set', 'group': 3, 'floor': 5}, now=200)
        self.assertEqual(edited['endless_runtime']['progress'], 4)
        self.assertEqual(edited['endless_runtime']['max_progress'], 20)
        self.assertEqual(edited['endless_runtime']['claimed_floors'], [1, 2, 3])
        before = copy.deepcopy(source)
        with self.assertRaises(ValueError):
            editor.apply(source, self.catalog, {'op': 'abyss_set', 'group': 3, 'floor': 34}, now=200)
        self.assertEqual(source, before)

    def test_starter_template_uid_and_first_login_are_explicit(self):
        catalog = {'playerleveldata': [{'level': 1, 'stamina': 80}],
                   'avatardata': [{'avatarID': 101, 'unlockStar': 1, 'initialWeapon': 20001}]}
        starter = templates.create(catalog, 'starter', uid=43210)
        first = templates.create(catalog, 'starter_first_login', uid=43211)
        self.assertEqual((starter['uid'], first['uid']), (43210, 43211))
        self.assertEqual((starter['is_first_login'], first['is_first_login']), (False, True))
        self.assertEqual(starter['stage_list'][0]['progress'], 0)
        self.assertEqual(starter['guide_id_list'], [])
        first['avatar_list'][0]['level'] = 9
        self.assertEqual(starter['avatar_list'][0]['level'], 1)
        with self.assertRaises(ValueError):
            templates.create(catalog, 'starter', uid=0)


if __name__ == '__main__':
    unittest.main()
