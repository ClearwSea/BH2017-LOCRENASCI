import hashlib
import unittest
from unittest.mock import patch

from packager.core import BuildError
from packager import material_training


def sha(value):
    return hashlib.sha256(value).hexdigest()


class WeekdayLuaCompatibilityTests(unittest.TestCase):
    def test_exact_edit_and_unchanged_other_scripts(self):
        source = b'begin\nold\nend\n'
        expected = b'begin\nnew\nend\n'
        edits = {'target': (sha(source), b'old', b'new', sha(expected))}
        with patch.dict(material_training.SCRIPT_EDITS, edits, clear=True):
            self.assertEqual(material_training.adapt_script('target', source), expected)
            self.assertEqual(material_training.adapt_script('other', source), source)
            with self.assertRaises(BuildError):
                material_training.adapt_script('target', source + b'changed')

    def test_rejects_ambiguous_preimage_and_wrong_output_fingerprint(self):
        duplicate = b'old old'
        with patch.dict(material_training.SCRIPT_EDITS,
                        {'target': (sha(duplicate), b'old', b'new', sha(b'new old'))}, clear=True):
            with self.assertRaises(BuildError):
                material_training.adapt_script('target', duplicate)
        with patch.dict(material_training.SCRIPT_EDITS,
                        {'target': (sha(b'old'), b'old', b'new', sha(b'wrong'))}, clear=True):
            with self.assertRaises(BuildError):
                material_training.adapt_script('target', b'old')


if __name__ == '__main__':
    unittest.main()
