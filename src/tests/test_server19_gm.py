import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

import server19_gm as gm


def isolated(name, dependencies):
    path = Path(__file__).resolve().parents[1] / (name + '.py')
    spec = importlib.util.spec_from_file_location('_gm_test_' + name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, dependencies):
        spec.loader.exec_module(module)
    return module


class GMTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)
        self.now = 1794772800 + 60  # Mon 2026-11-16 04:01 Asia/Shanghai
        self.current, self.next = gm.period(self.now)
        self.addCleanup(gm.configure, self.data / 'missing')
        gm.configure(self.data)

    def test_defaults_and_real_restart_snapshot(self):
        settings = gm.describe(self.data, self.now)
        self.assertIsNone(settings['abyss_temperature'])
        self.assertIsNone(settings['next_bosses'])
        result = gm.save(self.data, {'abyss_temperature': 0, 'next_bosses': [701, 201, 1001]}, self.next, self.now)
        self.assertEqual(result['next_bosses'], [701, 201, 1001])
        self.assertIsNone(gm.temperature_override())  # Saved for next server start.
        gm.configure(self.data)
        self.assertEqual(gm.temperature_override(), 0)
        self.assertEqual(gm.bosses_for_period(self.next), [701, 201, 1001])
        self.assertIsNone(gm.bosses_for_period(self.current))

    def test_invalid_save_and_cross_week_are_atomic(self):
        gm.save(self.data, {'abyss_temperature': 35000, 'next_bosses': [701, 201, 1001]}, self.next, self.now)
        before = (self.data / 'gm-config.json').read_bytes()
        for values, stamp in [({'abyss_temperature': 180001, 'next_bosses': None}, self.now),
                              ({'abyss_temperature': True, 'next_bosses': None}, self.now),
                              ({'abyss_temperature': None, 'next_bosses': [201, 201, 1001]}, self.now),
                              ({'abyss_temperature': None, 'next_bosses': [201, 1001, 123]}, self.now),
                              ({'abyss_temperature': 1, 'next_bosses': None}, self.next)]:
            with self.subTest(values=values, stamp=stamp), self.assertRaises(ValueError):
                gm.save(self.data, values, self.next, stamp)
            self.assertEqual((self.data / 'gm-config.json').read_bytes(), before)

    def test_changing_next_preserves_current_roster_and_reset(self):
        gm.save(self.data, {'abyss_temperature': None, 'next_bosses': [701, 201, 1001]}, self.next, self.now)
        later = self.next + 60
        _, following = gm.period(later)
        gm.save(self.data, {'abyss_temperature': 180000, 'next_bosses': [601, 501, 3001]}, following, later)
        gm.configure(self.data)
        self.assertEqual(gm.bosses_for_period(self.next), [701, 201, 1001])
        self.assertEqual(gm.bosses_for_period(following), [601, 501, 3001])
        gm.save(self.data, {'abyss_temperature': None, 'next_bosses': None}, following, later)
        gm.configure(self.data)
        self.assertIsNone(gm.temperature_override())
        self.assertIsNone(gm.bosses_for_period(following))
        self.assertEqual(gm.bosses_for_period(self.next), [701, 201, 1001])

    def test_existing_roster_drives_score_and_transition(self):
        dependencies = {n: ModuleType(n) for n in ('server19_endless', 'server19_exboss_rank',
                        'server19_protocol', 'server19_stage', 'server19_missions')}
        ex = isolated('server19_exboss', dependencies)
        account = {'main': {'level': 80}}
        state = ex._state(account, self.now)
        state['bosses']['1001']['score'] = 1234
        gm.save(self.data, {'abyss_temperature': None, 'next_bosses': [701, 201, 1001]}, self.next, self.now)
        gm.configure(self.data)
        self.assertEqual(ex._state_roots(state), (1001, 201, 3001))
        self.assertEqual(state['bosses']['1001']['score'], 1234)
        with patch.object(ex, '_settle_previous') as settle:
            new_state = ex._state(account, self.next + 1)
        settled = settle.call_args.args[1]
        self.assertEqual(ex._state_roots(settled), (1001, 201, 3001))
        self.assertEqual(settled['bosses']['1001']['score'], 1234)
        self.assertEqual(ex._state_roots(new_state), (701, 201, 1001))
        # An older save without the explicit order still uses its own roster.
        old = dict(settled); old.pop('root_order')
        self.assertEqual(ex._state_roots(old), (1001, 201, 3001))

    def test_actual_endless_response_uses_override(self):
        dependencies = {n: ModuleType(n) for n in ('server19_protocol', 'server19_stage')}
        endless = isolated('server19_endless', dependencies)
        state = {'display_temperature': 35000, 'group': 2, 'begin': self.current}
        self.assertEqual(endless.temperature(state, self.now), 35000)
        gm.save(self.data, {'abyss_temperature': 12345, 'next_bosses': None}, self.next, self.now)
        gm.configure(self.data)
        self.assertEqual(endless.temperature(state, self.now), 12345)
        self.assertEqual(state['display_temperature'], 35000)
