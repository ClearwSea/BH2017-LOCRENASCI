"""Pinned original1.9 A32 ELF/method mapping and bounded offline patch toolkit.

No device operations. Original methods are ARM, not Thumb. Appended code is
mapped by a new RX segment; PIC calls/jumps avoid absolute ASLR addresses.
Unwind registrations are explicit: callers must match their actual stack frame.
"""
from pathlib import Path
import bisect
import hashlib
import json
import struct

import analyze19 as metadata
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'work/extracted/client19/armeabi-v7a/libil2cpp.so'
SOURCE_SHA256 = '32e27ed130ed3a2a8c23d81c6a043510ae6cd99bd34b4bea4da1d71abae6c7a6'
CODE_REGISTRATION = 0x32dfaf8
METADATA_REGISTRATION = 0x331bf5c
CONDITIONS = {'eq': 0, 'ne': 1, 'cs': 2, 'hs': 2, 'cc': 3, 'lo': 3,
              'mi': 4, 'pl': 5, 'vs': 6, 'vc': 7, 'hi': 8, 'ls': 9,
              'ge': 10, 'lt': 11, 'gt': 12, 'le': 13, 'al': 14}


def align(value, boundary=4096):
    return (value + boundary - 1) // boundary * boundary


def word(value):
    return struct.pack('<I', value & 0xffffffff)


def prel31(value):
    if not -(1 << 30) <= value < (1 << 30):
        raise ValueError('PREL31 address outside range')
    return value & 0x7fffffff


def signed_prel31(value):
    value &= 0x7fffffff
    return value - (1 << 31) if value & (1 << 30) else value


def arm_branch(source, target, *, link=False, cond='al'):
    if (source | target) & 3:
        raise ValueError('A32 B/BL requires aligned ARM addresses')
    displacement = target - source - 8
    if displacement & 3 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError('A32 B/BL exceeds32MiB range; use PIC veneer')
    return word((CONDITIONS[cond] << 28) | (0x0b000000 if link else 0x0a000000) |
                ((displacement >> 2) & 0xffffff))


def arm_pic_jump(source, target):
    """16B tail jump, only volatile ip is changed; no absolute address literal."""
    if source & 3:
        raise ValueError('A32 veneer source must be aligned')
    return word(0xe59fc004) + word(0xe08fc00c) + word(0xe12fff1c) + word(target - source - 12)


def arm_pic_call(source, target):
    """20B PIC call; LR returns to B which skips the delta literal."""
    if source & 3:
        raise ValueError('A32 veneer source must be aligned')
    return (word(0xe59fc008) + word(0xe08fc00c) + word(0xe12fff3c) +
            arm_branch(source + 12, source + 20) + word(target - source - 12))


def unwind_for_push(register_mask, stack_bytes=0):
    """EHABI personality0 unwind for exact push-mask then optional SUB sp.

    No frame-pointer change, VFP save or conditional stack action is implied.
    Callers must prove their emitted prologue matches this recipe.
    """
    if register_mask & ~0xfff0 or register_mask & (1 << 13) or not register_mask:
        raise ValueError('Only saved r4..r12/lr/pc integer frame masks supported')
    if stack_bytes < 0 or stack_bytes % 4 or stack_bytes > 256:
        raise ValueError('Inline EHABI stack adjustment outside bounded range')
    codes = []
    if stack_bytes:
        codes.append(stack_bytes // 4 - 1)
    regs = register_mask & ~(1 << 14)
    if register_mask & (1 << 14) and regs in [((1 << (end + 1)) - 1) & ~15 for end in range(4, 12)]:
        last = regs.bit_length() - 1
        codes.append(0xa8 + last - 4)
    else:
        mask = register_mask >> 4
        codes += [0x80 | (mask >> 8), mask & 255]
    if len(codes) > 3:
        raise ValueError('Frame recipe needs an external EHABI table')
    codes += [0xb0] * (3 - len(codes))
    return (0x80 << 24) | (codes[0] << 16) | (codes[1] << 8) | codes[2]


def thumb_branch(source, target, *, link=False):
    """Thumb2 B.W/BL, used only when a caller has proved Thumb entry mode."""
    source, target = source & ~1, target & ~1
    delta = target - source - 4
    if delta & 1 or not -(1 << 24) <= delta < (1 << 24):
        raise ValueError('Thumb2 branch exceeds16MiB or alignment')
    immediate = delta & 0x1ffffff
    s, i1, i2 = (immediate >> 24) & 1, (immediate >> 23) & 1, (immediate >> 22) & 1
    j1, j2 = 1 ^ i1 ^ s, 1 ^ i2 ^ s
    first = 0xf000 | (s << 10) | ((immediate >> 12) & 0x3ff)
    second = (0xd000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | ((immediate >> 1) & 0x7ff)
    return struct.pack('<HH', first, second)


class ArmImage:
    def __init__(self, path=SOURCE, expected_sha256=SOURCE_SHA256):
        self.path = Path(path)
        self.original = self.path.read_bytes()
        self.source_sha256 = hashlib.sha256(self.original).hexdigest()
        if expected_sha256 and self.source_sha256 != expected_sha256:
            raise ValueError('ARM source preimage differs')
        self.data = bytearray(self.original)
        self.bytes = self.data
        self.header = struct.unpack_from('<16sHHIIIIIHHHHHH', self.data)
        h = self.header
        if h[0][:7] != b'\x7fELF\x01\x01\x01' or h[1:4] != (3, 40, 1) or (h[8], h[9]) != (52, 32):
            raise ValueError('Expected original little-endian ELF32 ARM ET_DYN')
        self.program_headers = [list(struct.unpack_from('<8I', self.data, h[5] + i * h[9])) for i in range(h[10])]
        self.sections = [list(struct.unpack_from('<10I', self.data, h[6] + i * h[11])) for i in range(h[12])]
        self.loads = [p for p in self.program_headers if p[0] == 1]
        self.changes, self.allocations, self.unwinds = [], [], []
        self.external_unwinds = []
        self.veneer_cursors = {}
        self.finalized = False
        self.append_offset = align(len(self.original))
        self.append_va = align(max(p[2] + p[5] for p in self.loads))
        self.next_offset = self.append_offset
        self.exports = {}
        for section in self.sections:
            if section[1] not in (2, 11):
                continue
            strings_section = self.sections[section[6]]
            strings = self.original[strings_section[4]:strings_section[4] + strings_section[5]]
            for offset in range(section[4], section[4] + section[5], section[9]):
                name, value, size, info, other, index = struct.unpack_from('<IIIBBH', self.original, offset)
                name = strings[name:strings.index(0, name)].decode('utf-8', errors='replace')
                if value and name:
                    self.exports[name] = value
        count, table = struct.unpack('<II', self.read(CODE_REGISTRATION, 8))
        expected_count = max(m[6] for m in metadata.M if m[6] != 0xffffffff) + 1
        if count != expected_count or table != 0x331bf9c:
            raise ValueError('Original ARM method registration differs')
        self.method_pointers = struct.unpack('<' + str(count) + 'I', self.read(table, count * 4))
        if any(not p or not self.is_executable(p & ~1) for p in self.method_pointers):
            raise ValueError('Method registration points outside original executable mapping')
        self.method_starts = sorted(set(p & ~1 for p in self.method_pointers))
        self.registration = list(struct.iter_unpack('<II', self.read(METADATA_REGISTRATION, 64)))
        if self.registration[3][0] != 63040 or self.registration[5][0] != len(metadata.T) or self.registration[6][0] != len(metadata.T):
            raise ValueError('Original type/field registration differs')
        self.exidx = []
        segment = next(p for p in self.program_headers if p[0] == 0x70000001)
        for offset in range(segment[1], segment[1] + segment[4], 8):
            va = segment[2] + offset - segment[1]
            function, descriptor = struct.unpack_from('<II', self.original, offset)
            target = va + signed_prel31(function)
            extab = None if descriptor == 1 or descriptor & 0x80000000 else va + 4 + signed_prel31(descriptor)
            self.exidx.append({'function_va': target, 'entry_va': va, 'descriptor': descriptor, 'extab_va': extab})
        if self.exidx != sorted(self.exidx, key=lambda x: x['function_va']):
            raise ValueError('ARM exidx table is not ordered')

    def va_to_offset(self, va, size=1):
        for p in self.loads:
            if p[2] <= va and va + size <= p[2] + p[4]:
                return p[1] + va - p[2]
        if self.append_va <= va and va + size <= self.append_va + max(0, len(self.data) - self.append_offset):
            return self.append_offset + va - self.append_va
        raise ValueError('Virtual address is not file-backed: ' + hex(va))

    def read(self, va, size):
        offset = self.va_to_offset(va, size)
        return bytes(self.data[offset:offset + size])

    read_va = read

    def is_executable(self, va):
        return any(p[6] & 1 and p[2] <= va < p[2] + p[4] for p in self.loads)

    def method(self, mid):
        index = metadata.M[mid][6]
        if index == 0xffffffff:
            raise ValueError('Generic method has no direct registered pointer: ' + str(mid))
        return self.method_pointers[index]

    method_addr = method

    def method_code_addr(self, mid):
        return self.method(mid) & ~1

    def method_range(self, mid):
        start = self.method_code_addr(mid)
        index = bisect.bisect_right(self.method_starts, start)
        if index == len(self.method_starts):
            raise ValueError('Last method boundary requires explicit evidence')
        return start, self.method_starts[index]

    def disasm(self, mid=None, *, va=None, size=None):
        if mid is not None:
            entry = self.method(mid)
            start, end = self.method_range(mid)
            size = end - start if size is None else min(size, end - start)
        else:
            entry, start = va, va & ~1
            if size is None: raise ValueError('Explicit disassembly size required')
        md = Cs(CS_ARCH_ARM, (CS_MODE_THUMB if entry & 1 else CS_MODE_ARM) | CS_MODE_LITTLE_ENDIAN)
        return list(md.disasm(self.read(start, size), start))

    def symbol(self, name):
        if name not in self.exports:
            raise ValueError('Defined ARM ELF symbol absent: ' + name)
        return self.exports[name]

    def field_offset(self, owner, field):
        ti = owner if isinstance(owner, int) else next(i for i in range(len(metadata.T)) if metadata.type_name(i) == owner)
        definition = metadata.T[ti]
        pointers = self.registration[5][1]
        offsets = struct.unpack('<I', self.read(pointers + 4 * ti, 4))[0]
        for local in range(definition[26]):
            fi = definition[16] + local
            row = struct.unpack_from('<4I', metadata.B, 9233316 + fi * 16)
            if metadata.string(row[0]) == field:
                value = struct.unpack('<I', self.read(offsets + local * 4, 4))[0]
                return value - (1 << 32) if value & 0x80000000 else value
        raise ValueError('ARM field not found: ' + str(owner) + '.' + field)

    def usage_address(self, destination_index):
        count, table = self.registration[7]
        if not 0 <= destination_index < count:
            raise ValueError('Metadata usage destination outside registration')
        return struct.unpack('<I', self.read(table + destination_index * 4, 4))[0]

    def patch(self, va, before, after, purpose):
        before, after = bytes(before), bytes(after)
        if self.finalized or len(before) != len(after):
            raise ValueError('Patch must preserve size before finalize')
        offset = self.va_to_offset(va, len(before))
        if self.data[offset:offset + len(before)] != before:
            raise ValueError('Patch preimage differs: ' + hex(va))
        for old in self.changes:
            if offset < old['offset'] + old['size'] and old['offset'] < offset + len(before):
                raise ValueError('Overlapping independent ARM patches')
        self.data[offset:offset + len(after)] = after
        record = {'va': va, 'offset': offset, 'size': len(after), 'before': before.hex(), 'after': after.hex(), 'purpose': purpose}
        self.changes.append(record)
        return record

    write_va = patch

    def allocate_code(self, name, size, align_to=16, *, unwind=None):
        if self.finalized or size <= 0 or any(r['name'] == name for r in self.allocations):
            raise ValueError('Invalid/duplicate finalized allocation')
        offset = align(self.next_offset, align_to)
        va = self.append_va + offset - self.append_offset
        self.data.extend(bytes(max(0, offset + size - len(self.data))))
        self.next_offset = offset + size
        record = {'name': name, 'va': va, 'offset': offset, 'size': size}
        self.allocations.append(record)
        if unwind is not None:
            self.register_unwind(va, unwind)
        return va

    def register_unwind(self, function_va, compact):
        if self.finalized:
            raise ValueError('Cannot register unwind after finalization')
        if compact != 1 and (compact >> 24) != 0x80:
            raise ValueError('Only explicit EHABI cantunwind or personality0 inline compact entries')
        if any(r[0] == function_va for r in self.unwinds) or any(r['function_va'] == function_va for r in self.external_unwinds):
            raise ValueError('Duplicate unwind registration')
        self.unwinds.append((function_va, compact))

    def register_unwind_external(self, function_va, extab_va):
        """Bind a real mapped compiler extab, without copying its old PREL31.

        The caller has imported the linked PIC blob at the linked virtual VA.
        Finalization encodes this table's relocated second-word PREL31 afresh.
        Compact personality1/2 is kept intact; generic personality references
        must resolve to actual executable original/appended code.
        """
        if self.finalized or (function_va | extab_va) & 3:
            raise ValueError('External ARM unwind requires aligned addresses before finalization')
        if any(r[0] == function_va for r in self.unwinds) or any(r['function_va'] == function_va for r in self.external_unwinds):
            raise ValueError('Duplicate unwind registration')
        self.read(function_va, 4)
        first = struct.unpack('<I', self.read(extab_va, 4))[0]
        if first & 0x80000000:
            personality = first >> 24
            if personality not in (0x80, 0x81, 0x82):
                raise ValueError('Unknown ARM compact external personality')
            words = 1 if personality == 0x80 else 1 + ((first >> 16) & 255)
            self.read(extab_va, words * 4)
            description = {'model': 'compact', 'personality_index': personality - 0x80,
                           'minimum_unwind_bytes': words * 4}
        else:
            personality_va = extab_va + signed_prel31(first)
            if not self.is_executable(personality_va & ~1) and not (
                    self.append_va <= (personality_va & ~1) < self.append_va + len(self.data) - self.append_offset):
                raise ValueError('External personality is not mapped executable code')
            self.read(extab_va, 8)
            description = {'model': 'generic', 'personality_va': personality_va}
        self.external_unwinds.append({'function_va': function_va, 'extab_va': extab_va,
                                     'header_hex': self.read(extab_va, 4).hex(), **description})

    def near_veneer(self, source, target, *, storage_mid=72868, name='network-tail-veneer'):
        """Use bounded unused AutoTest storage only as a zero-stack tail jump.

        No FakePacket method is called; never reuse its exception handler data
        as a newly authored helper's stack description.
        """
        start, end = self.method_range(storage_mid)
        cursor = self.veneer_cursors.get(storage_mid, start)
        start = align(cursor, 4)
        code = arm_pic_jump(start, target)
        if len(code) > end - start:
            raise ValueError('Unused method does not fit the PIC tail veneer')
        arm_branch(source, start, link=True)
        self.patch(start, self.read(start, len(code)), code, name + ': storage only, no stack frame')
        self.veneer_cursors[storage_mid] = start + len(code)
        return start

    def finalize(self):
        if self.finalized:
            return self.manifest()
        # Every code allocation beginning a callable helper should have a real
        # registered stack description. Unannotated allocation is explicit
        # cantunwind, never represented as preserving exceptions.
        annotated = {x[0] for x in self.unwinds} | {r['function_va'] for r in self.external_unwinds}
        for allocation in self.allocations:
            if allocation['va'] not in annotated:
                self.unwinds.append((allocation['va'], 1))
        code_end_va = self.append_va + len(self.data) - self.append_offset
        combined = [(r['function_va'], r['descriptor'], r['extab_va']) for r in self.exidx]
        old_starts = {r['function_va'] for r in self.exidx}
        new_starts = [va for va, _ in self.unwinds] + [r['function_va'] for r in self.external_unwinds] + [code_end_va]
        if len(set(new_starts)) != len(new_starts) or any(va in old_starts for va in new_starts):
            raise ValueError('New unwind entry collides with an existing function start')
        combined.extend((va, desc, None) for va, desc in self.unwinds)
        combined.extend((r['function_va'], 0, r['extab_va']) for r in self.external_unwinds)
        combined.append((code_end_va, 1, None))
        combined.sort(key=lambda x: x[0])
        # Original exidx contains same-start entries. Preserve their original
        # stable order and descriptors; do not normalize authored unwind data.
        exidx_offset = align(len(self.data), 4)
        self.data.extend(bytes(exidx_offset - len(self.data)))
        exidx_va = self.append_va + exidx_offset - self.append_offset
        for index, (function, descriptor, extab) in enumerate(combined):
            here = exidx_va + index * 8
            self.data.extend(word(prel31(function - here)))
            self.data.extend(word(descriptor if extab is None else prel31(extab - here - 4)))
        ph_offset = align(len(self.data), 16)
        self.data.extend(bytes(ph_offset - len(self.data)))
        ph_va = self.append_va + ph_offset - self.append_offset
        headers = [p[:] for p in self.program_headers]
        for p in headers:
            if p[0] == 6:
                p[1:6] = [ph_offset, ph_va, ph_va, (len(headers) + 1) * 32, (len(headers) + 1) * 32]
            if p[0] == 0x70000001:
                p[1:6] = [exidx_offset, exidx_va, exidx_va, len(combined) * 8, len(combined) * 8]
        segment_size = ph_offset + (len(headers) + 1) * 32 - self.append_offset
        headers.append([1, self.append_offset, self.append_va, self.append_va, segment_size, segment_size, 5, 4096])
        for p in headers: self.data.extend(struct.pack('<8I', *p))
        structural = []
        for offset, raw, purpose in ((28, word(ph_offset), 'ELF e_phoff to mapped relocated program headers'),
                                     (44, struct.pack('<H', len(headers)), 'ELF e_phnum includes the additional RX segment')):
            before = bytes(self.data[offset:offset + len(raw)])
            self.data[offset:offset + len(raw)] = raw
            structural.append({'offset': offset, 'size': len(raw), 'before': before.hex(), 'after': raw.hex(), 'purpose': purpose})
        # Keep the tooling section view consistent with the actual exidx PHDR.
        for i, s in enumerate(self.sections):
            if s[1] == 0x70000001:
                offset = self.header[6] + i * self.header[11] + 12
                raw = struct.pack('<III', exidx_va, exidx_offset, len(combined) * 8)
                before = bytes(self.data[offset:offset + len(raw)])
                self.data[offset:offset + len(raw)] = raw
                structural.append({'offset': offset, 'size': len(raw), 'before': before.hex(), 'after': raw.hex(),
                                   'purpose': 'Keep the ARM exidx section view consistent with its relocated program header'})
        self.finalized = True
        self.final_program_headers = headers
        self.structural_changes = structural
        self.unwind_table = {'va': exidx_va, 'offset': exidx_offset, 'entries': len(combined),
                             'original_entries': len(self.exidx), 'original_function_and_extab_targets_retained': True}
        return self.manifest()

    def manifest(self):
        return {'schema': 1, 'source': str(self.path), 'source_sha256': self.source_sha256,
                'output_sha256': hashlib.sha256(self.data).hexdigest(),
                'original_bytes': len(self.original), 'output_bytes': len(self.data),
                'method_registration': {'va': CODE_REGISTRATION, 'table': 0x331bf9c, 'count': len(self.method_pointers),
                                        'ISA': 'all85308_A32'},
                'metadata_registration_va': METADATA_REGISTRATION, 'changes': self.changes,
                'allocations': self.allocations, 'unwind_registrations': self.unwinds,
                'external_unwind_registrations': self.external_unwinds,
                'structural_changes': getattr(self, 'structural_changes', []),
                'new_rx_segment': {'offset': self.append_offset, 'va': self.append_va},
                'unwind_table': getattr(self, 'unwind_table', None), 'finalized': self.finalized,
                'device_operation': 'none', 'human_acceptance': 'pending'}

    def save(self, output):
        output = Path(output).resolve()
        if not output.is_relative_to(ROOT) or output.exists() or output == self.path.resolve():
            raise ValueError('Use a fresh workspace output file, never the source or existing candidate')
        self.finalize()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(self.data)
        output.with_suffix(output.suffix + '.json').write_text(json.dumps(self.manifest(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return self.manifest()


class ArmCode:
    """Small explicit A32 emitter with checked branch/PC-relative fixups."""
    def __init__(self, base):
        if base & 3: raise ValueError('A32 code base must be aligned')
        self.base, self.data, self.labels, self.fixups = base, bytearray(), {}, []

    @property
    def pc(self): return self.base + len(self.data)

    def emit(self, value):
        self.data.extend(word(value) if isinstance(value, int) else bytes.fromhex(value) if isinstance(value, str) else bytes(value))

    def label(self, name):
        if name in self.labels: raise ValueError('Duplicate assembler label')
        self.labels[name] = self.pc

    def branch(self, target, *, link=False, cond='al'):
        if isinstance(target, str):
            self.fixups.append((len(self.data), target, link, cond)); self.emit(0)
        else: self.emit(arm_branch(self.pc, target, link=link, cond=cond))

    def call(self, target):
        try: self.emit(arm_branch(self.pc, target, link=True))
        except ValueError: self.emit(arm_pic_call(self.pc, target))

    def push(self, mask): self.emit(0xe92d0000 | mask)
    def pop(self, mask): self.emit(0xe8bd0000 | mask)
    def bx(self, register): self.emit(0xe12fff10 | register)
    def blx(self, register): self.emit(0xe12fff30 | register)
    def mov(self, dst, src): self.emit(0xe1a00000 | (dst << 12) | src)

    def movw(self, dst, immediate):
        if not 0 <= immediate <= 65535: raise ValueError('MOVW immediate out of range')
        self.emit(0xe3000000 | ((immediate & 0xf000) << 4) | (dst << 12) | (immediate & 0xfff))

    def movt(self, dst, immediate):
        if not 0 <= immediate <= 65535: raise ValueError('MOVT immediate out of range')
        self.emit(0xe3400000 | ((immediate & 0xf000) << 4) | (dst << 12) | (immediate & 0xfff))

    def immediate(self, dst, value):
        self.movw(dst, value & 0xffff)
        if value >> 16: self.movt(dst, (value >> 16) & 0xffff)

    def load(self, dst, base, offset=0, *, byte=False):
        if abs(offset) > 4095: raise ValueError('LDR immediate outside12 bits')
        self.emit((0xe5900000 if offset >= 0 else 0xe5100000) | ((1 << 22) if byte else 0) | (base << 16) | (dst << 12) | abs(offset))

    def store(self, src, base, offset=0, *, byte=False):
        if abs(offset) > 4095: raise ValueError('STR immediate outside12 bits')
        self.emit((0xe5800000 if offset >= 0 else 0xe5000000) | ((1 << 22) if byte else 0) | (base << 16) | (src << 12) | abs(offset))

    def finish(self):
        for position, name, link, cond in self.fixups:
            if name not in self.labels: raise ValueError('Undefined assembler label: ' + name)
            self.data[position:position + 4] = arm_branch(self.base + position, self.labels[name], link=link, cond=cond)
        return bytes(self.data)
