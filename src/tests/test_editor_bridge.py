import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def source(name, path, modules):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(result)
    return result


class EditorBridgeTests(unittest.TestCase):
    def test_empty_backup_path_remains_none_through_bridge(self):
        calls = []
        store = ModuleType('server19_editor_store')
        store.save = lambda *args: calls.append(args) or 'saved'
        bridge = source('_test_editor_empty_backup', ROOT / 'android-server-probe/app/src/main/python/editor_entry.py',
                        {'server19_editor_store': store})
        context = SimpleNamespace(getFilesDir=lambda: SimpleNamespace(getAbsolutePath=lambda: 'editor-test-files'))
        with patch.dict(sys.modules, {'server19_editor_store': store}):
            self.assertEqual(bridge.save(context, '{"schema":1}', '', 'hash'), 'saved')
        self.assertIsNone(calls[0][2])

    def test_repeated_load_uses_one_isolated_runtime_and_compact_catalog(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); calls = []
            probe = ModuleType('probe_entry')
            probe.extract_runtime = lambda context: (calls.append('extract') or (root, root / 'runtime', 'sha'))
            portable = ModuleType('server19_portable')
            def configure(path):
                self.assertTrue(Path(path).is_dir())
                self.assertFalse((Path(path) / 'account.json').exists())
                calls.append('configure')
            portable.configure = configure
            stage = ModuleType('server19_stage')
            def table(name):
                if name == 'textmap':
                    return [{'ID': 'wanted', 'Text': '显示名称'}, {'ID': 'unused', 'Text': '无关文本'}]
                if name == 'avatardata':
                    return [{'avatarID': 101, 'fullName': 'wanted', 'unneeded': 'large data'}]
                return []
            stage._table = table
            progress = ModuleType('server19_editor_progress')
            progress.catalog_from_configured_runtime = lambda: {'stages': [], 'sakura': {'stories': []}, 'abyss_floors': 33}
            presets = ModuleType('server19_editor_material_presets'); presets.build = lambda c, g: []
            gacha = ModuleType('server19_gacha'); gacha.CHANNELS = {}
            captain = ModuleType('server19_editor_captain'); captain.limits = lambda a, c: {'level': {'min': 1, 'max': 80}}
            template = ModuleType('server19_editor_templates')
            template.create = lambda c, kind, uid: {'schema': 1, 'uid': uid, 'main': {'level': 1}}
            modules = {'probe_entry': probe, 'server19_portable': portable, 'server19_stage': stage,
                       'server19_editor_progress': progress, 'server19_editor_material_presets': presets,
                       'server19_gacha': gacha, 'server19_editor_captain': captain, 'server19_editor_templates': template}
            bridge = source('_test_editor_bridge', ROOT / 'android-server-probe/app/src/main/python/editor_entry.py', modules)
            context = SimpleNamespace(getFilesDir=lambda: SimpleNamespace(getAbsolutePath=lambda: str(root)),
                                      getApplicationInfo=lambda: SimpleNamespace(nativeLibraryDir=str(root)))
            with patch.dict(sys.modules, modules):
                first = json.loads(bridge.create(context, 222, 'starter'))
                original = {'schema': 1, 'uid': 333, 'main': {'level': 20},
                            'cabin_list': [{'type': 4, 'level': 3, 'tech_list': [{'pos_x': 1, 'pos_y': 2}]}],
                            'unknown': {'unchanged': True}}
                loaded = json.loads(bridge.load(context, json.dumps(original)))
                second = json.loads(bridge.create(context, 444, 'full_level'))
            self.assertEqual(calls, ['extract', 'configure'])
            self.assertTrue(Path(bridge._CONFIG_DIRECTORY.name).is_dir())
            self.assertEqual([first['account']['uid'], loaded['account']['uid'], second['account']['uid']], [222, 333, 444])
            self.assertEqual(loaded['account'], original)
            self.assertEqual(first['catalog']['textmap'], [{'ID': 'wanted', 'Text': '显示名称'}])
            self.assertNotIn('unneeded', first['catalog']['avatardata'][0])
            bridge._CONFIG_DIRECTORY.cleanup()


class CaptainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        skills = ModuleType('server19_avatar_skills'); skills.cabin4_skill_point_bonus = lambda a: 0; skills.RECOVERY_INTERVAL = 360
        prog = ModuleType('server19_player_progression'); prog.expected_equipment_size_limit = lambda level: 500 + (level - 1) * 20
        cls.captain = source('_test_editor_captain', ROOT / 'server19_editor_captain.py',
                             {'server19_avatar_skills': skills, 'server19_player_progression': prog})
        cls.catalog = {'playerleveldata': [{'level': 1, 'avatarLevelLimit': 15}, {'level': 80, 'avatarLevelLimit': 80}]}

    def test_lower_level_requires_first_lowering_owned_character(self):
        account = {'main': {'level': 80, 'exp': 50, 'skill_point_limit': 50, 'equipment_size_limit': 2080},
                   'avatar_list': [{'avatar_id': 101, 'star': 1, 'level': 80}]}
        with self.assertRaisesRegex(ValueError, '角色等级上限'):
            self.captain.apply(account, self.catalog, {'op': 'captain', 'level': 1})
        self.assertEqual(account['main']['level'], 80)
        account['avatar_list'][0]['level'] = 15
        result = self.captain.apply(account, self.catalog, {'op': 'captain', 'level': 1})
        self.assertEqual(result['main']['exp'], 0)
        self.assertEqual(result['main']['equipment_size_limit'], 2080)

    def test_simultaneous_limit_and_value(self):
        account = {'main': {'level': 1, 'skill_point': 20, 'skill_point_limit': 50, 'equipment_size_limit': 500}}
        result = self.captain.apply(account, self.catalog, {'op': 'captain', 'skill_point_limit': 100, 'skill_point': 90})
        self.assertEqual((result['main']['skill_point_limit'], result['main']['skill_point']), (100, 90))
        self.assertEqual(account['main']['skill_point'], 20)

    def test_lower_level_preserves_cabin_and_enforces_requirement(self):
        account = {'main': {'level': 80, 'skill_point_limit': 50, 'equipment_size_limit': 2080},
                   'avatar_list': [{'star': 1, 'level': 1}],
                   'cabin_list': [{'type': 4, 'level': 3, 'tech_list': [{'pos_x': 2, 'pos_y': 3}]}]}
        catalog = dict(self.catalog, cabinleveldata=[{'cabinType': 4, 'level': 3, 'playerLevelNeed': 30}])
        with self.assertRaisesRegex(ValueError, '舱室 4'):
            self.captain.apply(account, catalog, {'op': 'captain', 'level': 1})
        self.assertEqual(account['cabin_list'][0]['level'], 3)


if __name__ == '__main__':
    unittest.main()
