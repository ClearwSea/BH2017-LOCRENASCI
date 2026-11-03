"""Packaged proof validation; no device or game content is used."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server19_build_capabilities as capabilities
from packager.core import write_json


class CapabilityChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.native = self.root / 'native.bin'
        self.native.write_bytes(b'synthetic native bytes')
        self.ready = {'build_proof': 'packaged-artifacts-v1', 'required_native_capabilities': ['example']}
        self.value = {'schema': 1, 'evidence_kind': 'packaged-artifacts',
                      'native_sha256': hashlib.sha256(self.native.read_bytes()).hexdigest(),
                      'native_capabilities': ['example'],
                      'records': {'test': capabilities.canonical_sha(self.ready)}}
        write_json(self.root / 'build-capabilities.json', self.value)
        root_patch = patch.object(capabilities, 'ROOT', self.root)
        env_patch = patch.dict(os.environ, {'BH3_PACKAGED_NATIVE_LIBRARY': str(self.native)})
        root_patch.start()
        env_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(env_patch.stop)
        capabilities._verified_native = None

    def test_valid_packaged_proof_does_not_require_device_receipt(self):
        capabilities.require('test', self.ready)
        self.assertNotIn('device', self.ready)
        self.assertNotIn('readback_verified', self.ready)

    def test_changed_native_rejected_even_after_cached_verification(self):
        capabilities.require('test', self.ready)
        self.native.write_bytes(b'replaced native bytes!')
        with self.assertRaisesRegex(ValueError, 'native library'):
            capabilities.require('test', self.ready)

    def test_modified_ready_record_rejected(self):
        self.ready['deployed'] = True
        with self.assertRaisesRegex(ValueError, 'record does not match'):
            capabilities.require('test', self.ready)

    def test_missing_native_capability_rejected(self):
        self.value['native_capabilities'] = []
        write_json(self.root / 'build-capabilities.json', self.value)
        with self.assertRaisesRegex(ValueError, 'capabilities are absent'):
            capabilities.require('test', self.ready)


if __name__ == '__main__':
    unittest.main()
