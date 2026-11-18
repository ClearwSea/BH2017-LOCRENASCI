import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import server19_editor_store as store


class EditorStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.account = self.root / 'account.json'
        self.receipt = self.root / 'receipt.json'
        self.initial = {'schema': 1, 'uid': 12, 'main': {'scoin': 5}}
        self.raw = json.dumps(self.initial).encode()
        self.locker = patch.object(store, '_lock', lambda path: nullcontext())
        self.locker.start()
        self.account.write_bytes(self.raw)
        self.receipt.write_text('{"uid":12}', encoding='utf-8')

    def tearDown(self):
        self.locker.stop()
        self.tmp.cleanup()

    def test_verified_backup_and_atomic_replace(self):
        value, digest = store.read(self.account, self.receipt)
        value['main']['scoin'] = 10
        next_digest = store.save(self.account, self.receipt, self.root / 'backup', digest, value)
        self.assertEqual((self.root / 'backup/account.json').read_bytes(), self.raw)
        self.assertEqual(json.loads((self.root / 'backup/metadata.json').read_bytes()), {'source': 'editor'})
        self.assertEqual(json.loads(self.account.read_bytes()), value)
        self.assertEqual(next_digest, hashlib.sha256(self.account.read_bytes()).hexdigest())

    def test_later_session_save_does_not_create_backup(self):
        value, digest = store.read(self.account, self.receipt)
        value['main']['scoin'] = 25
        store.save(self.account, self.receipt, None, digest, value)
        self.assertEqual(json.loads(self.account.read_bytes())['main']['scoin'], 25)
        self.assertFalse((self.root / 'backup').exists())

    def test_interrupted_backup_never_publishes_partial_history(self):
        value, digest = store.read(self.account, self.receipt)
        value['main']['scoin'] = 11
        for stop in (1, 2, 3):
            calls = []
            def interrupt(fd):
                calls.append(fd)
                if len(calls) == stop:
                    raise OSError('interrupted backup')
            target = self.root / ('backup-' + str(stop))
            with patch.object(store.os, 'fsync', side_effect=interrupt):
                with self.assertRaises(OSError):
                    store.save(self.account, self.receipt, target, digest, value)
            self.assertFalse(target.exists())
            self.assertEqual(self.account.read_bytes(), self.raw)

    def test_changed_account_and_identity_are_rejected(self):
        value, digest = store.read(self.account, self.receipt)
        self.account.write_bytes(self.raw + b' ')
        with self.assertRaises(ValueError):
            store.save(self.account, self.receipt, self.root / 'backup', digest, value)
        self.assertEqual(self.account.read_bytes(), self.raw + b' ')
        _, digest = store.read(self.account, self.receipt)
        value['uid'] = 13
        with self.assertRaises(ValueError):
            store.save(self.account, self.receipt, self.root / 'backup', digest, value)
        self.assertFalse((self.root / 'backup').exists())
