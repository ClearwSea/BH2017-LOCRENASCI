"""Read a pinned UnityFS bundle's Sprite names without decoding textures."""

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
import json
import lzma
from pathlib import Path
import struct
import zipfile
import server19_resources as resources


def decompress(raw, size, flags):
    kind = flags & 63
    if kind == 0:
        out = raw
    elif kind == 1:
        out = lzma.decompress(raw)
    elif kind in (2, 3):
        out, pos = bytearray(), 0
        while pos < len(raw):
            token = raw[pos]; pos += 1
            length = token >> 4
            if length == 15:
                while True:
                    value = raw[pos]; pos += 1; length += value
                    if value != 255: break
            out.extend(raw[pos:pos + length]); pos += length
            if pos == len(raw): break
            offset = struct.unpack_from('<H', raw, pos)[0]; pos += 2
            length = token & 15
            if length == 15:
                while True:
                    value = raw[pos]; pos += 1; length += value
                    if value != 255: break
            length += 4
            if not 0 < offset <= len(out): raise ValueError('Invalid LZ4 match offset')
            for _ in range(length): out.append(out[-offset])
        out = bytes(out)
    else:
        raise ValueError('Unsupported UnityFS compression')
    if len(out) != size: raise ValueError('UnityFS decoded size differs')
    return out


def nodes(raw):
    if not raw.startswith(b'UnityFS\0'): raise ValueError('UnityFS required')
    pos = 12
    for _ in range(2): pos = raw.index(0, pos) + 1
    total, compressed, size, flags = struct.unpack_from('>QIII', raw, pos); pos += 20
    blockinfo = decompress(raw[total - compressed:total] if flags & 128 else raw[pos:pos + compressed], size, flags)
    if total != len(raw): raise ValueError('UnityFS total size differs')
    q = 16
    count = struct.unpack_from('>I', blockinfo, q)[0]; q += 4
    blocks = []
    for _ in range(count): blocks.append(struct.unpack_from('>IIH', blockinfo, q)); q += 10
    count = struct.unpack_from('>I', blockinfo, q)[0]; q += 4
    records = []
    for _ in range(count):
        offset, size, _ = struct.unpack_from('>QQI', blockinfo, q); q += 20
        end = blockinfo.index(0, q); name = blockinfo[q:end].decode(); q = end + 1
        records.append((name, offset, size))
    pos = pos if flags & 128 else pos + compressed
    joined = bytearray()
    for size, compressed, flags in blocks:
        joined.extend(decompress(raw[pos:pos + compressed], size, flags)); pos += compressed
    return [(name, bytes(joined[offset:offset + size])) for name, offset, size in records]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apk', type=Path, default=resources.DEFAULT24)
    p.add_argument('--entry', default='assets/Asb/android/item.unity3d')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = {'apk': str(args.apk), 'entry': args.entry, 'sprites': [], 'nodes': []}
    with zipfile.ZipFile(args.apk) as z:
        for name, raw in nodes(z.read(args.entry)):
            if name.endswith(('.resS', '.resource')): continue
            parsed = resources.serialized(raw)
            result['nodes'].append({'name': name, 'bytes': len(raw), 'object_count': len(parsed['objects'])})
            for pid, obj in parsed['objects'].items():
                if obj['class'] != 213: continue
                sprite = resources.Reader(raw, obj['offset']).string()
                result['sprites'].append({'name': sprite, 'node': name, 'path_id': pid})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'nodes': result['nodes'], 'sprites': result['sprites']}, ensure_ascii=False))
