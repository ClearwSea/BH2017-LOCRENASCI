"""Necessary independent Capstone/ELF/EHABI checks for the new ARM toolkit.

Offline validation only; it does not establish phone execution or bridge entry.
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
import json
import struct
import server19_arm_native as n
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB

OUT = n.ROOT / 'server19-run/sony-arm/native-toolkit-check'


def verify():
    image = n.ArmImage()
    md, thumb = Cs(CS_ARCH_ARM, CS_MODE_ARM), Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    results = []
    def passed(name, details): results.append({'name': name, 'status': 'PASS', 'details': details})
    assert len(image.method_pointers) == 85308 and all(not p & 1 for p in image.method_pointers)
    assert image.method(43279) == 0x56ccbc and image.method(72965) == 0x1285860
    assert image.symbol('il2cpp_string_new') == 0x2c3d518
    passed('actual_ARM_method_and_export_mapping', {'methods': 85308, 'ISA': 'A32', 'source_sha256': image.source_sha256})
    for p in image.loads:
        for off in (0, 1, 17, p[4] - 1):
            assert image.read(p[2] + off, 1) == image.original[p[1] + off:p[1] + off + 1]
    passed('PT_LOAD_and_odd_data_address_mapping', {'load_segments': len(image.loads)})
    branches = 0
    for start, target in ((0x1000, 0x2000), (0x2000, 0x1000), (0x10000000, 0x12000004), (0x12000000, 0x10000008)):
        for link in (False, True):
            ins = list(md.disasm(n.arm_branch(start, target, link=link), start))
            assert len(ins) == 1 and ins[0].mnemonic == ('bl' if link else 'b') and int(ins[0].op_str.removeprefix('#'), 0) == target
            branches += 1
    for target in (0x10000000 + (1 << 25) + 8, 0x10000000 - (1 << 25) + 4):
        try: n.arm_branch(0x10000000, target)
        except ValueError: pass
        else: raise AssertionError('Out-of-range branch accepted')
    passed('A32_B_BL_disassembler_targets_and_range_guard', {'branches': branches})
    pic_cases = 0
    for start, target in ((0x353a000, 0x56ccbc), (0xafa6c4, 0x353a000), (0x353a100, 0x2c3d518)):
        for code, literal_off in ((n.arm_pic_call(start, target), 16), (n.arm_pic_jump(start, target), 12)):
            instructions = list(md.disasm(code[:literal_off], start))
            assert instructions[0].mnemonic == 'ldr' and instructions[1].mnemonic == 'add'
            assert instructions[2].mnemonic in ('bx', 'blx') and instructions[2].op_str == 'ip'
            delta = struct.unpack_from('<i', code, literal_off)[0]
            for slide in (0, 0x30000000):
                runtime_add_pc = start + slide + 12
                runtime_destination = (runtime_add_pc + delta) & 0xffffffff
                assert runtime_destination == (target + slide) & 0xffffffff
            if literal_off == 16:
                assert instructions[3].mnemonic == 'b' and int(instructions[3].op_str.removeprefix('#'), 0) == start + 20
            pic_cases += 1
    passed('far_PIC_calls_and_tail_jumps_ASLR_arithmetic', {'cases': pic_cases})
    for start, target in ((0x1001, 0x2001), (0x2001, 0x1001), (0x1000001, 0x2000001)):
        for link in (False, True):
            ins = list(thumb.disasm(n.thumb_branch(start, target, link=link), start & ~1))
            assert len(ins) == 1 and ins[0].mnemonic in (('bl',) if link else ('b.w',))
            assert int(ins[0].op_str.removeprefix('#'), 0) == target & ~1
    passed('optional_Thumb2_encoding', {'used_by_original_ARM_image': False})
    base = image.allocate_code('test-frame-4-6-lr', 64, unwind=n.unwind_for_push(0x4070))
    code = n.ArmCode(base)
    code.push(0x4070); code.movw(4, 0xabcd); code.movt(4, 0x1234)
    code.load(5, 4, 16); code.store(5, 4, -4); code.pop(0x8070)
    payload = code.finish()
    decoded = list(md.disasm(payload, base))
    assert [i.mnemonic for i in decoded] == ['push', 'movw', 'movt', 'ldr', 'str', 'pop']
    assert decoded[1].op_str == 'r4, #0xabcd' and decoded[2].op_str == 'r4, #0x1234'
    image.patch(base, image.read(base, len(payload)), payload, 'isolated emitter fixture')
    passed('bounded_A32_emitter_and_matching_frame_description', {'unwind': hex(n.unwind_for_push(0x4070))})
    image.finalize()
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', image.data)
    headers = [struct.unpack_from('<8I', image.data, h[5] + i * h[9]) for i in range(h[10])]
    added = headers[-1]
    assert added[0] == 1 and added[6] == 5 and added[1] % 4096 == added[2] % 4096
    assert added[1] <= h[5] < added[1] + added[4] and len(headers) == len(image.program_headers) + 1
    phdr = next(p for p in headers if p[0] == 6)
    assert phdr[1] == h[5] and phdr[4] == len(headers) * 32
    passed('new_RX_segment_and_relocated_mapped_PHDR', {'new_program_header_count': len(headers), 'file_offset': hex(added[1]), 'VA': hex(added[2])})
    ex = next(p for p in headers if p[0] == 0x70000001)
    rebuilt = []
    for off in range(ex[1], ex[1] + ex[4], 8):
        here = ex[2] + off - ex[1]
        func, desc = struct.unpack_from('<II', image.data, off)
        extab = None if desc == 1 or desc & 0x80000000 else here + 4 + n.signed_prel31(desc)
        rebuilt.append((here + n.signed_prel31(func), desc if extab is None else None, extab))
    original = [(r['function_va'], r['descriptor'] if r['extab_va'] is None else None, r['extab_va']) for r in image.exidx]
    old_limit = max(r[0] for r in original)
    assert [r for r in rebuilt if r[0] <= old_limit] == original
    assert (base, 0x80aab0b0, None) in rebuilt
    assert image.read(n.CODE_REGISTRATION, 72) == image.original[n.CODE_REGISTRATION:n.CODE_REGISTRATION + 72]
    passed('EHABI_original_targets_duplicate_order_and_new_frame', {'old_entries': len(original), 'new_entries': len(rebuilt) - len(original)})
    report = {'status': 'offline_toolkit_checks_passed', 'checks': results,
              'not_verified': ['Android dynamic-loader execution', 'native helper exception execution', 'phone bridge entry'],
              'device_operation': 'none', 'toolkit_manifest': image.manifest()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    report = verify()
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']), 'output': str(OUT / 'verification.json')}))
