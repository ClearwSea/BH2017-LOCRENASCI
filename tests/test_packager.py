"""Failure-boundary checks using synthetic files; no game data is included."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from packager import core


class PackagerChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        self.root_patch = patch.object(core, 'ROOT', self.source)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.config_file = self.base / 'build-config.json'
        self.value = {'schema': 1, 'client19': 'inputs/a.bin', 'client24': 'inputs/b.bin',
                      'work_dir': 'build-output', 'stage_ratios': 'baseline'}

    def load(self):
        core.write_json(self.config_file, self.value)
        return core.load_config(self.config_file)

    def fake_inputs(self):
        config = self.load()
        profile = {}
        for key, raw in [('client19', b'original-client'), ('client24', b'reference-client')]:
            path = config[key]
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(raw)
            profile[key] = {'bytes': len(raw), 'sha256': core.digest(path)}
        core.write_json(self.source / 'profiles/android-launcher-20261102.json', profile)
        return config

    def test_relative_paths_use_config_location(self):
        config = self.load()
        self.assertEqual(config['client19'], self.base / 'inputs/a.bin')
        self.assertEqual(config['work_dir'], self.base / 'build-output')

    def test_unknown_config_key_rejected(self):
        self.value['workdir'] = 'typo'
        with self.assertRaisesRegex(core.BuildError, 'Unknown configuration'):
            self.load()

    def test_output_cannot_overlap_inputs(self):
        for name in ('.', 'inputs', 'inputs/generated'):
            self.value['work_dir'] = name
            with self.subTest(name=name), self.assertRaisesRegex(core.BuildError, 'separate'):
                self.load()

    def test_output_cannot_overwrite_source(self):
        self.value['work_dir'] = 'source/packager'
        with self.assertRaisesRegex(core.BuildError, 'source tree'):
            self.load()

    def test_invalid_ratio_policy_rejected(self):
        self.value['stage_ratios'] = 'automatic'
        with self.assertRaisesRegex(core.BuildError, 'stage_ratios'):
            self.load()

    def test_different_reference_hash_does_not_gate_inspection(self):
        config = self.fake_inputs()
        self.assertEqual(len(core.inspect_inputs(config)), 2)
        path = config['client24']
        path.write_bytes(b'X' * path.stat().st_size)
        result = core.inspect_inputs(config)
        self.assertFalse(result['client24']['reference_match'])

    def test_reference_size_difference_does_not_gate_inspection(self):
        config = self.fake_inputs()
        config['client19'].write_bytes(b'short')
        self.assertFalse(core.inspect_inputs(config)['client19']['reference_match'])

    def test_apk_target_fails_without_creating_output(self):
        config = self.load()
        with self.assertRaisesRegex(core.BuildError, 'not implemented'):
            core.build(config, 'apk')
        self.assertFalse(config['work_dir'].exists())

    def test_existing_output_unchanged(self):
        config = self.load()
        config['work_dir'].mkdir()
        marker = config['work_dir'] / 'retain.txt'
        marker.write_text('retain', encoding='utf-8')
        with self.assertRaisesRegex(core.BuildError, 'already exists'):
            core.build(config, 'data')
        self.assertEqual(marker.read_text(encoding='utf-8'), 'retain')

    def test_failed_stage_receipt_and_input_immutability(self):
        config = self.fake_inputs()
        before = {key: core.digest(config[key]) for key in ('client19', 'client24')}
        with patch.object(core, 'check_dependency', return_value='5.0.9'), \
                patch.object(core, 'source_inputs', return_value=[]), \
                patch.object(core, 'extract_inputs', side_effect=core.BuildError('synthetic failure')):
            with self.assertRaisesRegex(core.BuildError, 'synthetic failure'):
                core.build(config, 'data')
        receipt = core.read_json(config['work_dir'] / 'build.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['stages'][-1]['name'], 'extract')
        self.assertEqual(receipt['stages'][-1]['status'], 'failed')
        self.assertNotIn('artifacts', receipt)
        self.assertEqual(before, {key: core.digest(config[key]) for key in before})

    def verified_fixture(self):
        work = self.base / 'verify'
        artifact = work / 'generated/table'
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b'[]\n')
        receipt = {'schema': 1, 'target': 'data', 'status': 'success',
                   'artifacts': core.artifact_inventory(work)}
        core.write_json(work / 'build.json', receipt)
        return work

    def test_verify_detects_added_removed_and_changed_artifacts(self):
        work = self.verified_fixture()
        self.assertEqual(core.verify(work)['status'], 'PASS')
        extra = work / 'generated/extra'
        extra.write_text('unexpected', encoding='utf-8')
        with self.assertRaisesRegex(core.BuildError, 'verification failed'):
            core.verify(work)
        extra.unlink()
        item = work / 'generated/table'
        item.write_bytes(b'{}\n')
        with self.assertRaisesRegex(core.BuildError, 'verification failed'):
            core.verify(work)
        item.unlink()
        with self.assertRaisesRegex(core.BuildError, 'verification failed'):
            core.verify(work)

    def test_verify_rejects_parent_path_in_receipt(self):
        work = self.verified_fixture()
        receipt = core.read_json(work / 'build.json')
        receipt['artifacts'][0]['path'] = '../outside'
        core.write_json(work / 'build.json', receipt)
        with self.assertRaisesRegex(core.BuildError, 'Unsafe artifact path'):
            core.verify(work)

    def test_baseline_stage_policy_preserves_native_dependency(self):
        rows = [{'levelId': identity, 'avatarExpInside': float(identity % 100 - 31),
                 'scoinInside': identity % 100 - 31 + 0.7}
                for identity in (10432, 10433, 10434, 20432, 20433, 20434)]
        with self.assertRaisesRegex(core.BuildError, 'initialization dependency'):
            core.validate_stage_policy(rows, 'baseline')
        rows.append({'levelId': 900302})
        core.validate_stage_policy(rows, 'baseline')
        with self.assertRaisesRegex(core.BuildError, 'ratio policy'):
            core.validate_stage_policy(rows, 'repaired')

    def test_repaired_policy_changes_only_the_ratio_requirement(self):
        rows = [{'levelId': identity, 'avatarExpInside': 0.0, 'scoinInside': 0.7}
                for identity in (10432, 10433, 10434, 20432, 20433, 20434)]
        rows.append({'levelId': 900302})
        core.validate_stage_policy(rows, 'repaired')
        with self.assertRaisesRegex(core.BuildError, 'ratio policy'):
            core.validate_stage_policy(rows, 'baseline')


if __name__ == '__main__':
    unittest.main()
