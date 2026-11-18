import unittest
import struct

from packager.core import BuildError
from packager.exboss_resources import _MODELS, adapt
from packager.material_training import adapt_ability_data


class ExBossResourcesTest(unittest.TestCase):
    def test_maps_retained_models_and_keeps_unresolved_model(self):
        rows = [{'BossPrefabPath': source} for source in _MODELS]
        rows.append({'BossPrefabPath': 'Entities/Monster/Boss/BOSS_110/SinDemonEx/Boss_110'})
        paths = ['entities/sindemonex/' + name.lower() for name in _MODELS.values()]
        self.assertEqual(adapt(rows, paths), 9)
        self.assertEqual([r['BossPrefabPath'].lower() for r in rows[:-1]], paths)
        self.assertIn('BOSS_110', rows[-1]['BossPrefabPath'])

    def test_missing_native_model_is_rejected(self):
        with self.assertRaises(BuildError):
            adapt([{'BossPrefabPath': source} for source in _MODELS], [])

    def test_variant_conversion_preserves_other_roots(self):
        import hashlib
        original = b'base' + b'old-variant'
        payload = (struct.pack('<III', 0, 0, 1) + struct.pack('<II', 0, 0) +
                   struct.pack('<I', 1) + struct.pack('<III', 0, 1, 4) +
                   struct.pack('<I', len(original)) + original)
        edits = {('monster', 'variant'): (hashlib.sha256(b'old-variant').hexdigest(),
                                          hashlib.sha256(b'new-variant').hexdigest(),
                                          ((0, 3, b'new'),))}
        result = adapt_ability_data(payload, b'monster\x1fvariant', edits)
        self.assertTrue(result.endswith(b'basenew-variant'))
        self.assertEqual(struct.unpack_from('<II', result, 12), (0, 0))
