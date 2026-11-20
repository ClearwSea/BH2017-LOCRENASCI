import struct
import unittest

from packager.resources import _patch_baked_abilities


def _build_baked(entries_data):
    """Build a minimal bakedabilitydata binary for testing."""
    names = []
    entries = []
    payload = bytearray()
    for name, chunk in entries_data:
        idx = len(names)
        names.append(name)
        entries.append((idx, len(payload)))
        payload.extend(chunk)
    out = bytearray(struct.pack('<III', 0, 1, len(entries)))
    for k, o in entries:
        out.extend(struct.pack('<II', k, o))
    out.extend(struct.pack('<I', 0))
    out.extend(struct.pack('<I', len(payload)))
    out.extend(payload)
    return bytes(out), '\x1f'.join(names).encode('utf-8')


class BakedAbilityPatchTest(unittest.TestCase):
    def test_patches_hom_blew_himself_and_garland_of_fire(self):
        garland = bytearray(b'\x00' * 966)
        hom = bytearray(b'\x00' * 385)
        raw, sm = _build_baked([
            ('Equip_EX3_GarlandOfFire', bytes(garland)),
            ('Equip_EX6_HomBlewHimself', bytes(hom)),
        ])
        patched = _patch_baked_abilities(raw, sm)
        ne = struct.unpack_from('<I', patched, 8)[0]
        self.assertEqual(ne, 2)
        _, off0 = struct.unpack_from('<II', patched, 12)
        _, off1 = struct.unpack_from('<II', patched, 20)
        dlen = struct.unpack_from('<I', patched, 28 + 4)[0]
        self.assertEqual(off0, 0)
        self.assertEqual(off1, 946)
        self.assertEqual(dlen, 946 + 375)


if __name__ == '__main__':
    unittest.main()
