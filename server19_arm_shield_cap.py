"""Restore source shield Clamp through a tagged original AbilitySpecial.

Only abilities carrying the projected marker are capped. Original unmarked
abilities, health, shield ratios, resume and hit behavior remain untouched.
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
import json
import struct
from pathlib import Path
import server19_arm_native as n
from server19_arm_resources import module_base, jump
from server19_story_all_resources import WORK

KEY = 'Server19_MaxShieldValue'
OUT = WORK/'goal-six-chapters-20261016'
SOURCE = WORK/'act2-batch-failures-v1/voice-return-trace-v1/libil2cpp.so'


def build():
    image = n.ArmImage(SOURCE, expected_sha256=None)
    original = n.ArmImage()
    site = 0x697b78
    before = bytes.fromhex('008a80ee0b0a84ed0c0a84ed')
    assert image.read(site, 12) == before == original.read(site, 12)
    # HasParam initializes its own original Dictionary<string,object>
    # ContainsKey MethodInfo. Reuse the exact same closed generic instance.
    base = 0xaba8b0 + struct.unpack('<i', original.read(0xaba8dc, 4))[0]
    got = base + struct.unpack('<i', original.read(0xaba8e0, 4))[0]
    assert got == 0x3451680
    contains = 0x1a2e974
    text = (KEY+'\0').encode()
    text_va = image.allocate_code('shield cap Special key', len(text), align_to=4)
    image.patch(text_va, bytes(len(text)), text, 'Original dictionary parameter name')
    # push40 + caller VFP8 + local16 =64; unwind skips caller r0-r3,
    # VFP d0 and locals before restoring the preserved core registers.
    hook = image.allocate_code('tagged source shield clamp', 2048,
                               unwind=n.unwind_for_push(0x41f0, 40))
    c = n.ArmCode(hook)
    c.push(0x41ff); c.emit(0xed2d0b02); c.emit(0xe24dd010)
    c.load(5, 4, 0x10)  # BaseAbilityMixin.instancedAbility
    c.emit(0xe3550000); c.branch('restore', cond='eq')
    module_base(c, 0); c.immediate(12, text_va); c.emit(0xe080000c)
    c.call(image.symbol('il2cpp_string_new')); c.mov(6, 0)
    c.mov(0, 5); c.mov(1, 6); c.immediate(2, 0)
    c.call(image.method(49382))  # HasParam; initializes the exact MI above.
    c.emit(0xe3500000); c.branch('evaluate', cond='ne')
    c.load(7, 5, 0x60); c.emit(0xe3570000); c.branch('restore', cond='eq')
    c.load(7, 7, 0x18); c.emit(0xe3570000); c.branch('restore', cond='eq')
    module_base(c, 2); c.immediate(12, got); c.emit(0xe082200c)
    c.load(2, 2); c.load(2, 2)
    c.mov(0, 7); c.mov(1, 6); c.call(contains)
    c.emit(0xe3500000); c.branch('restore', cond='eq')
    c.label('evaluate')
    c.mov(0, 5); c.mov(1, 6); c.immediate(2, 0)
    c.call(image.method(49383)); c.mov(3, 0)  # softfp cap bits
    c.immediate(0, 0); c.load(1, 13, 16); c.immediate(2, 0)
    c.store(2, 13, 0)  # fifth argument MethodInfo on stack
    c.call(image.method(17449))  # original Mathf.Clamp(float,float,float)
    c.store(0, 13, 16)  # replace saved s0 only
    c.label('restore')
    c.emit(0xe28dd010); c.emit(0xecbd0b02); c.pop(0x41ff)
    c.emit(before); jump(c, site+12)
    code = c.finish(); assert len(code) <= 2048
    image.patch(hook, bytes(len(code)), code, 'Preserve original state; cap only explicitly tagged abilities')
    image.patch(site, before, n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-site-12),
                'Restore source Clamp before shield/maxShield initialization')
    output = OUT/'native-shield-cap-v1/libil2cpp.so'; image.save(output)
    report = {'status':'prepared_offline_pending','hook':hook,'return':site+12,
              'site':site,'hook_bytes':len(code),'key_va':text_va,'contains_methodinfo_got':got,
              'contains':contains,'HasParam':image.method(49382),
              'GetFloatParam':image.method(49383),'Clamp':image.method(17449),
              'string_new':image.symbol('il2cpp_string_new'), 'stack_bytes':64,
              'original_sequence':before.hex(), 'source':str(SOURCE),
              'unmarked_behavior':'original, no clamp','device_operation':'none',
              'human_acceptance':'pending'}
    (output.parent/'bridge.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(build()))
