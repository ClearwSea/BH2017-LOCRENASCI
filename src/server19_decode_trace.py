"""Log original packed-root kind/offset, preserving deserialization and gyro guard.

The log is joined to exact deployed containers by server19_batch_diagnostics.
It does not suppress exceptions, provide success, change saves or operate UI.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import hashlib
import json
import struct
import analyze19 as a
from server19_metadata import NativeCode

ROOT = Path(__file__).resolve().parent
CAVE = 0xA5FA00
END = 0xA5FD6B
GOT = 0x33E39D8
FORMAT = 'BH3SERVER19_DECODE kind=%u offset=%u length=%u header=%02x caller=%08x'
HOOKS = ((1, 57415, '_baked/bakedabilitydata'),
         (2, 57583, '_baked/bakedmonsterdata'),
         (3, 57435, '_baked/bakedavatardata'),
         (4, 57703, '_baked/bakedweapondata'))
PROLOGUE = bytes.fromhex('5589e5535756')

def helper(base, format_rva):
    c = NativeCode(base)
    c.emit('55 89e5 53 56 57 83e4f0 81ec80010000')
    c.call(c.base + len(c.data) + 5)
    pc = c.base + len(c.data)
    c.emit('5b 81c3'); c.data.extend(struct.pack('<i', GOT-pc))
    c.emit('8b4510 89442408 8b550c 8954240c')  # kind, offset
    c.emit('31c9 c7442414 ff000000 8b4508 85c0')
    c.jump('0f84', 'no_array')
    c.emit('8b480c 39ca'); c.jump('0f83', 'no_array')
    c.emit('0fb6441010 89442414')
    c.label('no_array'); c.emit('894c2410')
    c.emit('8db3'); c.data.extend(struct.pack('<i', -GOT))
    c.emit('8b4514 29f0 89442418 8d83')
    c.data.extend(struct.pack('<i', format_rva-GOT))
    c.emit('89442404 8db42480000000 893424 ff93f4170000 893424')
    c.call(0x29549A0)  # original il2cpp_string_new
    c.emit('89442404 c7042400000000 c744240800000000')
    c.call(0x222EC7E)  # original Debug.Log
    c.emit('8d65f4 5f5e5b5dc3')
    return c.finish()

def wrapper(base, helper_rva, kind, hook):
    c = NativeCode(base)
    c.emit('9c60 8b44242c 8b542430 8b4c2424 51 68')
    c.data.extend(struct.pack('<I', kind))
    c.emit('52 50'); c.call(helper_rva)
    c.emit('83c410 619d'); c.data.extend(PROLOGUE)
    c.jump('e9', 'resume')
    c.labels['resume'] = hook+len(PROLOGUE)-base
    return c.finish()

def payload():
    fmt_rva = END-0x70
    body = bytearray(helper(CAVE, fmt_rva))
    wrappers = []
    for kind, method, path in HOOKS:
        hook = a.pointer(a.M[method])
        if a.M[method][15] != 4 or a.E[hook:hook+6] != PROLOGUE:
            raise ValueError('Original root formatter signature/prologue changed')
        rva = CAVE+len(body)
        raw = wrapper(rva, CAVE, kind, hook)
        body.extend(raw)
        wrappers.append({'kind': kind, 'method': method, 'name': a.N[method],
                         'path': path, 'hook': hook, 'resume': hook+6,
                         'wrapper': rva, 'wrapper_bytes': len(raw)})
    if CAVE+len(body) > fmt_rva:
        raise ValueError('Decoder diagnostic exceeds audited cave')
    body.extend(bytes(fmt_rva-CAVE-len(body)))
    body.extend(FORMAT.encode('ascii')+b'\0')
    if CAVE+len(body)>END:
        raise ValueError('Decoder diagnostic format exceeds cave')
    return bytes(body), wrappers

def install(binary):
    before = bytes(binary)
    body, wrappers = payload()
    if before[CAVE:CAVE+len(body)] != a.E[CAVE:CAVE+len(body)]:
        raise ValueError('Decoder diagnostic storage is occupied')
    changes = [{'offset': hex(CAVE), 'size': len(body),
                'before': before[CAVE:CAVE+len(body)].hex(), 'after': body.hex()}]
    binary[CAVE:CAVE+len(body)] = body
    for row in wrappers:
        hook = row['hook']
        if before[hook:hook+6] != PROLOGUE:
            raise ValueError('Root formatter already modified')
        patch = b'\xe9'+struct.pack('<i',row['wrapper']-hook-5)+b'\x90'
        binary[hook:hook+6] = patch
        changes.append({'offset': hex(hook), 'size': 6,
                        'before': PROLOGUE.hex(), 'after': patch.hex()})
    allowed = [(int(r['offset'],16),int(r['offset'],16)+r['size']) for r in changes]
    if len(binary)!=len(before) or any(old!=new and not any(l<=i<r for l,r in allowed)
            for i,(old,new) in enumerate(zip(before,binary))):
        raise ValueError('Unexpected native byte changes')
    return {'enabled': True, 'format': FORMAT, 'hooks': wrappers, 'changes': changes,
            'input_sha256': hashlib.sha256(before).hexdigest(),
            'output_sha256': hashlib.sha256(binary).hexdigest(),
            'scope': 'root diagnostic only; original decode, exceptions, gameplay and guard retained',
            'array_layout': 'original byte[] max_length+0xc, data+0x10; unsigned offset bounds',
            'abi': 'wrapper preserves GPRs/flags/stack; replays exact original prologue'}

def build(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use existing workspace source and new workspace output')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='31c7659e99180fe6e26f27a20dfee7ceb4a144c045cb0ff2c6063ccd31144649':
        raise ValueError('Expected current pure gyro-guard baseline')
    binary = bytearray(raw); report = install(binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(binary)
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();report=build(args.source,args.output)
    print(json.dumps({'output_sha256':report['output_sha256'],'root_kinds':len(HOOKS)}))
