"""Focused check of actual compiled ARM helper extab import and relocated PREL31.

No compilation, original toolkit suite repetition or device operations.
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
import server19_arm_native as n
from server19_arm_resources import Elf32


def verify(source=n.ROOT / '.local-baseline/server19-dev/sony-arm-resources/v1/resources.elf'):
    elf = Elf32(source)
    allocated = [s for s in elf.sections if s[2] & 2 and s[5]]
    base = min(s[3] for s in allocated)
    blob = elf.payload(base)
    image = n.ArmImage()
    # Reserve alignment padding before the fixture if network occupied earlier
    # space at link time. Never move a linked blob to an unproved virtual VA.
    if base < image.append_va:
        raise ValueError('Compiled helper virtual base precedes this RX mapping')
    if base > image.append_va:
        image.allocate_code('link-base-padding', base - image.append_va, align_to=4)
    start = image.allocate_code('actual-compiled-C-helper', len(blob), align_to=4)
    if start != base:
        raise ValueError('Actual ELF helper cannot be silently relocated')
    image.patch(start, image.read(start, len(blob)), blob, 'isolated real compiler EHABI fixture')
    section = elf.named['.ARM.exidx']
    original_entries, external = [], []
    for offset in range(0, section[5], 8):
        here = section[3] + offset
        first, desc = struct.unpack('<II', elf.mapped(here, 8))
        function = here + n.signed_prel31(first)
        extab = None if desc == 1 or desc & 0x80000000 else here + 4 + n.signed_prel31(desc)
        if desc == 1:
            continue  # Compiler's terminal .text sentinel is not a callable frame.
        if extab is None:
            image.register_unwind(function, desc)
        else:
            image.register_unwind_external(function, extab)
            external.append({'function': function, 'extab': extab, 'header': elf.mapped(extab, 4).hex()})
        original_entries.append((function, desc if extab is None else None, extab))
    if not external:
        raise ValueError('This fixture contains no real compiler external unwind entries')
    extab_section = elf.named['.ARM.extab']
    before = image.read(extab_section[3], extab_section[5])
    if before != elf.bytes(extab_section):
        raise AssertionError('Compiler extab bytes changed during import')
    image.finalize()
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', image.data)
    headers = [struct.unpack_from('<8I', image.data, h[5] + j * h[9]) for j in range(h[10])]
    exidx = next(p for p in headers if p[0] == 0x70000001)
    decoded = []
    for offset in range(0, exidx[4], 8):
        here = exidx[2] + offset
        first, desc = struct.unpack_from('<II', image.data, exidx[1] + offset)
        function = here + n.signed_prel31(first)
        extab = None if desc == 1 or desc & 0x80000000 else here + 4 + n.signed_prel31(desc)
        if start <= function < start + len(blob):
            decoded.append((function, desc if extab is None else None, extab))
    if decoded != original_entries:
        raise AssertionError('Relocated helper function/extab targets differ from actual compiler ELF')
    if image.read(extab_section[3], extab_section[5]) != before:
        raise AssertionError('External opcode/personality/extra data bytes changed')
    for item in external:
        if image.read(item['extab'], 4).hex() != item['header']:
            raise AssertionError('Actual external personality header drift')
    report = {'status': 'actual_compiled_extab_targets_and_bytes_verified',
              'source_elf': str(source), 'elf_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
              'helper_entries': len(original_entries), 'external_entries': external,
              'extab_bytes': extab_section[5], 'old_compiler_exidx_bytes': section[5],
              'helper_blob_bytes': len(blob), 'new_exidx_va': exidx[2],
              'external_personality_and_opcodes_preserved': True,
              'relocated_exidx_second_word_PREL31_verified': True,
              'exception_execution': 'not_executed', 'device_operation': 'none'}
    output = n.ROOT / 'server19-run/sony-arm/native-external-unwind-check/verification.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    report = verify()
    print(json.dumps({k: report[k] for k in ('status', 'helper_entries', 'extab_bytes', 'old_compiler_exidx_bytes', 'exception_execution')}))
