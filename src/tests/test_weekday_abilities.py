import hashlib
import struct
import unittest
from unittest.mock import patch

from packager.core import BuildError
from packager import material_training


def sha(data):
    return hashlib.sha256(data).hexdigest()


class WeekdayAbilityContainerTests(unittest.TestCase):
    def test_projects_selected_roots_and_preserves_other_payloads(self):
        entries = ((0, 0), (1, 4), (2, 7))
        data = b'abcdabcUNCHANGED'
        container = (struct.pack('<III', 0, 7, len(entries)) +
                     b''.join(struct.pack('<II', *entry) for entry in entries) +
                     struct.pack('<II', 0, len(data)) + data)
        edits = {'one': (sha(b'abcd'), sha(b'axcd'), ((1, 2, b'x'),)),
                 'two': (sha(b'abc'), sha(b'ac'), ((1, 2, b''),))}
        with patch.dict(material_training.ABILITY_EDITS, edits, clear=True):
            result = material_training.adapt_ability_data(container, b'one\x1ftwo\x1fother')
            self.assertEqual(struct.unpack_from('<IIIIII', result, 12), (0, 0, 1, 4, 2, 6))
            self.assertEqual(result[44:], b'axcdacUNCHANGED')
            broken = container[:-1] + b'Z'
            # An unrelated root is deliberately preserved without reinterpreting it.
            self.assertTrue(material_training.adapt_ability_data(broken, b'one\x1ftwo\x1fother').endswith(b'UNCHANGED'[:-1] + b'Z'))
            changed = bytearray(container)
            changed[44] ^= 1
            with self.assertRaises(BuildError):
                material_training.adapt_ability_data(bytes(changed), b'one\x1ftwo\x1fother')


if __name__ == '__main__':
    unittest.main()
