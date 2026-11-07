"""Reference assembly input and cache boundaries using synthetic payloads."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from packager import assemble
from packager.core import BuildError, write_json


class AssemblyChecks(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config_path = self.root / 'config.json'
        self.config = {key: key for key in assemble.PATH_KEYS}
        self.config.update(schema=1, mode='reference-artifacts', key_alias='test', resource_ledger_sha256='a' * 64)

    def test_reference_mode_must_be_explicit(self):
        self.config['mode'] = 'original-inputs'
        write_json(self.config_path, self.config)
        with self.assertRaisesRegex(BuildError, 'explicit mode'):
            assemble.load_config(self.config_path)

    def test_existing_output_requires_explicit_resume(self):
        write_json(self.config_path, self.config)
        (self.root / 'work_dir').mkdir()
        with self.assertRaisesRegex(BuildError, 'new assembly'):
            assemble.load_config(self.config_path)
        loaded = assemble.load_config(self.config_path, resume=True)
        self.assertEqual(loaded['work_dir'], self.root / 'work_dir')

    def test_corrupt_cached_resource_is_rejected(self):
        payload = b'synthetic audio payload'
        digest = hashlib.sha256(payload).hexdigest()
        ledger = self.root / 'ledger.json'
        write_json(ledger, [{'remote': '/sdcard/bh3-server19-audio/test.wem', 'local': 'test', 'sha256': digest}])
        embedded = self.root / 'embedded'
        embedded.mkdir()
        name = 'private/data/bh3-server19-audio/test.wem'
        write_json(embedded / 'client-resources.json', {'entries': [{'path': name, 'sha256': digest, 'size': len(payload), 'pack': 'main'}]})
        with zipfile.ZipFile(embedded / 'client-resources.zip', 'w') as z:
            z.writestr(name, payload)
        with zipfile.ZipFile(embedded / 'client-videos.zip', 'w'):
            pass
        config = {'resource_ledger': ledger}
        self.assertEqual(len(assemble.cached_resources(config, self.root)), 1)
        with zipfile.ZipFile(embedded / 'client-resources.zip', 'w') as z:
            z.writestr(name, b'changed')
        with self.assertRaisesRegex(BuildError, 'payload mismatch'):
            assemble.cached_resources(config, self.root)


if __name__ == '__main__':
    unittest.main()
