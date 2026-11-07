"""Apply the supported native compatibility patch to the original ARM library."""
import base64
import hashlib
from pathlib import Path
import struct
import zipfile
from .core import ROOT, BuildError, read_json


def signed_prel31(value):
    return (value & 0x7fffffff) - (0x80000000 if value & 0x40000000 else 0)


def apply(client19, output):
    spec = read_json(ROOT / 'rules/native-armv7.json')
    with zipfile.ZipFile(client19) as package:
        source = package.read('lib/armeabi-v7a/libil2cpp.so')
    if len(source) != spec['input_bytes'] or hashlib.sha256(source).hexdigest() != spec['input_sha256']:
        raise BuildError('Native patch requires the supported original 1.9 ARM library')
    result = bytearray(source)
    for row in spec['changes']:
        before, after = bytes.fromhex(row['before']), bytes.fromhex(row['after'])
        offset = row['offset']
        if len(before) != len(after) or source[offset:offset + len(before)] != before:
            raise BuildError('Native instruction preimage differs at ' + hex(offset))
        result[offset:offset + len(before)] = after
    for operation in spec['append']:
        if 'data' in operation:
            result.extend(base64.b64decode(operation['data'], validate=True))
        elif 'zero' in operation:
            result.extend(bytes(operation['zero']))
        elif 'copy' in operation:
            offset, size = operation['copy']
            if offset < 0 or offset + size > len(source):
                raise BuildError('Native patch copy is out of bounds')
            result.extend(source[offset:offset + size])
        elif 'relocate_original_unwind' in operation:
            r = operation['relocate_original_unwind']
            for i in range(r['bytes'] // 8):
                a, b = struct.unpack_from('<II', source, r['offset'] + i * 8)
                original_here, new_here = r['va'] + i * 8, r['to_va'] + i * 8
                function = original_here + signed_prel31(a)
                if b != 1 and not b & 0x80000000:
                    b = (original_here + 4 + signed_prel31(b) - new_here - 4) & 0x7fffffff
                result.extend(struct.pack('<II', (function - new_here) & 0x7fffffff, b))
        else:
            raise BuildError('Unknown native patch operation')
    digest = hashlib.sha256(result).hexdigest()
    if len(result) != spec['output_bytes'] or digest != spec['output_sha256']:
        raise BuildError('Native patch output differs from its supported profile')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(result)
    return {'sha256': digest, 'bytes': len(result), 'source': 'original-client19-plus-sparse-patch'}
