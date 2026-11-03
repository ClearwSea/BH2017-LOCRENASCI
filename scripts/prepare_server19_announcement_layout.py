"""Keep the stock announcement image and its layout slot at the same aspect."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.local-baseline/server19-dev/fuka601-tools/python'))
import UnityPy
import server19_arm_native as native

ENTRY = 'assets/bin/Data/b753f392eb85c9b4e9a3255042f9064a'


def prepare(game, source, output, image_path):
    output.mkdir(parents=True, exist_ok=False)
    png = image_path.read_bytes()
    width, height = struct.unpack_from('>II', png, 16)
    assert (width, height) == (2172, 547)
    display_width = 774.0
    display_height = display_width * height / width
    with zipfile.ZipFile(game) as archive:
        raw = archive.read(ENTRY)
    assert hashlib.sha256(raw).hexdigest() == '65dc6c7fff940b4bd9b7c9659dae1837b15d8692c7ce39bca8ae887f054d1ebb'
    env = UnityPy.load(raw)
    objects = {o.path_id: o for o in env.objects}
    before = {i: o.get_raw_data() for i, o in objects.items()}
    # Pics and its decorative Frame; Content already has top pivot/alignment,
    # image first, then Title and Body. Preserve all other stock components.
    for oid, old_width, old_height, new_height in (
        (112, 774.0, 160.0, display_height),
        (118, 780.0, 166.0, display_height + 6.0),
    ):
        tree = objects[oid].read_typetree()
        assert tree['m_SizeDelta'] == dict(x=old_width, y=old_height)
        tree['m_SizeDelta']['y'] = new_height
        objects[oid].save_typetree(tree)
    packed = env.file.save()
    check = {o.path_id: o for o in UnityPy.load(packed).objects}
    assert {i for i in before if before[i] != check[i].get_raw_data()} == {112, 118}
    (output / 'announcement.prefab').write_bytes(packed)

    image = native.ArmImage(source, expected_sha256='b6fe91484be8530c02e52ed2963bdd31602433b83d78ef90c6da5dd16a514fde')
    # ShowBulletinById feeds raw sprite pixels into LayoutElement preferred
    # height/width while Pics has a fixed display size. Replace those two
    # local reads with the display dimensions; no global Rect getter change.
    for site, getter, value in ((0x81964c, 0x25c8ab4, display_height),
                                (0x819694, 0x25c8a94, display_width)):
        expected = native.arm_branch(site, getter, link=True) + native.word(0xe1a0a000)
        bits = struct.unpack('<I', struct.pack('<f', value))[0]
        def move(base, half):
            return native.word(base | ((half & 0xf000) << 4) | (10 << 12) | (half & 0xfff))
        code = move(0xe3000000, bits & 0xffff) + move(0xe3400000, bits >> 16)
        image.patch(site, expected, code, 'announcement display size matches image layout')
    # No allocation or stack change: preserve ELF headers/EHABI byte-for-byte.
    # ArmImage.save rebuilds an appended unwind table, which is unnecessary here.
    assert not image.allocations and len(image.data) == len(image.original)
    (output / 'libil2cpp.so').write_bytes(image.data)
    (output / 'libil2cpp.so.json').write_text(json.dumps(image.manifest(), indent=2))
    report = dict(width=width, height=height, display_width=display_width,
                  display_height=display_height, prefab_entry=ENTRY,
                  changed_prefab_objects=[112, 118], native_sites=['0x81964c', '0x819694'])
    (output / 'layout.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('game', 'native', 'output', 'image'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    prepare(args.game, args.native, args.output, args.image)
