"""Reference comparisons are advisory and directory checks never read contents."""
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from packager.input_reference import ComparisonCancelled, compare_file, quick_directory


class ReferenceChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_hash_mismatch_returns_a_result_without_rejecting_input(self):
        path = self.root / 'input.bin'
        path.write_bytes(b'current')
        result = compare_file(path, {'sha256': hashlib.sha256(b'reference').hexdigest()}, threading.Event())
        self.assertFalse(result['matches_reference'])
        self.assertEqual(result['actual_sha256'], hashlib.sha256(b'current').hexdigest())

    def test_cancellation_stops_file_read(self):
        path = self.root / 'input.bin'
        path.write_bytes(b'current')
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(ComparisonCancelled):
            compare_file(path, {'sha256': 'unused'}, cancel)

    def test_quick_comparison_reports_differences_without_content_reads(self):
        folder = self.root / 'Video'; folder.mkdir()
        (folder / 'same.usm').write_bytes(b'abcd')
        (folder / 'changed.usm').write_bytes(b'ab')
        (folder / 'extra.usm').write_bytes(b'a')
        reference = {'files': [{'path': 'Video/same.usm', 'bytes': 4},
                               {'path': 'Video/changed.usm', 'bytes': 4},
                               {'path': 'Video/missing.usm', 'bytes': 2}]}
        with patch.object(Path, 'open', side_effect=AssertionError('Content read forbidden')):
            result = quick_directory(self.root, reference, threading.Event())
        self.assertFalse(result['matches_reference'])
        self.assertEqual(result['missing'], ['Video/missing.usm'])
        self.assertEqual(result['different_size'][0]['path'], 'Video/changed.usm')
        self.assertEqual(result['additional'], ['Video/extra.usm'])


if __name__ == '__main__':
    unittest.main()
