"""Extract original ETC2 textures; never redraw or modify their artwork."""

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
import ctypes
from pathlib import Path
import zipfile

from PIL import Image
import server19_resources as resources


def extract(decoder, output):
    output.mkdir(parents=True, exist_ok=True)
    library = ctypes.CDLL(str(decoder.resolve()))
    decode = library.decode_rgba
    decode.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_void_p]
    decode.restype = ctypes.c_int
    selected = [('b4d922e80719ac14988445b9669f026c', 'bloodembrace-native'),
                ('5a1b6669f5591934699115607a2b16d4', 'dracula-top-native'),
                ('980e774551cff524c9761805d6802004', 'ziyuan-card-native')]
    catalog = {row['path']: row for row in resources.resource_map(resources.DEFAULT19)}
    with zipfile.ZipFile(resources.DEFAULT19) as package:
        for number, label in [(2, 'dracula-middle-native'), (3, 'dracula-bottom-native')]:
            record = catalog['spriteoutput/stigmatafigures/s4ae_' + str(number)]
            prefab = resources.serialized(package.read('assets/bin/Data/' + record['file']))
            external = [x.rsplit('/', 1)[-1] for x in prefab['externals']
                        if 'unity default resources' not in x]
            if len(external) != 1:
                raise ValueError('Ambiguous original Sprite texture')
            selected.append((external[0], label))
        for filename, label in selected:
            data = package.read('assets/bin/Data/' + filename)
            info = resources.serialized(data)
            obj = next(o for o in info['objects'].values() if o['class'] == 28)
            raw = data[obj['offset']:obj['offset'] + obj['size']]
            reader = resources.Reader(raw)
            name = reader.string()
            width, height, size, fmt, mip = reader.read('5i')
            reader.pos += 36
            length = reader.read('i')
            payload = raw[reader.pos:reader.pos + length]
            if fmt != 47 or mip != 1 or length != size or size != width * height:
                raise ValueError('Expected one ETC2_RGBA8 texture: ' + name)
            pixels = (ctypes.c_uint32 * (width * height))()
            if not decode(payload, width, height, pixels):
                raise ValueError('ETC2 decoding failed: ' + name)
            image = Image.frombytes('RGBA', (width, height), bytes(pixels), 'raw', 'BGRA')
            # Unity stores rows from the bottom; this is coordinate decoding.
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            path = output / (label + '.png')
            image.save(path)
            print(name, width, height, path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decoder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    extract(args.decoder, args.output)
