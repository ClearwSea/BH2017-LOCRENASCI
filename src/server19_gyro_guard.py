"""Guard malformed original gyro input; retain original camera/navigation.

Original gyro getter output is checked at its epilogue. Valid16-byte input is
unchanged. Initial invalid input produces identity; subsequent invalid input
holds the last valid input. State is new zero-initialized RW BSS storage, never
an original field or an RX code-cave write. A separate RX LOAD contains helper,
PIC thunk and the relocated program-header table. No device operations here.
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
import hashlib
import struct

import analyze19 as a
from server19_metadata import NativeCode

HOOK = 0x227917D
RESUME = 0x2279182
HOOK_BYTES = bytes.fromhex("8d65f85e5b")
STATE_RVA = 0x365196C
STATE_SIZE = 20
EPSILON_BITS = 0x2B8CBCCC  # f32 squared norm ~1e-12.
PAGE = 0x1000
ORIGINAL_PH = 0x34
ORIGINAL_PH_COUNT = 7
PH_SIZE = 32
NEW_PH_COUNT = 8
ORIGINAL_LENGTH = len(a.E)


def _align(value, alignment):
    return (value + alignment - 1) & -alignment


def make_helper(base):
    """cdecl void guard(float*out16, State*state20), SSE2 x86.

    EBX/ESI/EDI/EBP and ESP are preserved; the caller supplies zeroed RW state.
    Integer float exponent checks reject NaN/Inf before calculating the norm.
    An overflowing squared norm is also rejected, rather than accepted as >eps.
    """
    c = NativeCode(base)
    c.emit("55 89 e5 53 56 57 8b 75 08 8b 7d 0c")
    for offset in (0, 4, 8, 12):
        c.emit("8b 06" if not offset else f"8b 46 {offset:02x}")
        c.emit("25 00 00 80 7f 3d 00 00 80 7f")
        c.jump("0f 84", "invalid")
    c.emit("0f 10 06 0f 59 c0 0f 28 c8 0f c6 c9 4e 0f 58 c1")
    c.emit("0f 28 c8 0f c6 c9 b1 f3 0f 58 c1")
    c.emit("68")
    c.data.extend(struct.pack("<I", EPSILON_BITS))
    c.emit("0f 2e 04 24 58")
    c.jump("0f 86", "invalid")
    c.emit("66 0f 7e c0 25 00 00 80 7f 3d 00 00 80 7f")
    c.jump("0f 84", "invalid")
    c.emit("0f 10 06 0f 11 47 04 c7 07 01 00 00 00")
    c.jump("e9", "done")
    c.label("invalid")
    c.emit("83 3f 01")
    c.jump("0f 85", "identity")
    c.emit("0f 10 47 04 0f 11 06")
    c.jump("e9", "done")
    c.label("identity")
    c.emit("c7 06 00 00 00 00 c7 46 04 00 00 00 00")
    c.emit("c7 46 08 00 00 00 00 c7 46 0c 00 00 80 3f")
    c.label("done")
    c.emit("5f 5e 5b 89 ec 5d c3")
    return c.finish()


def make_thunk(base, helper_address, state_rva=STATE_RVA):
    """Getter epilogue JMP adapter; state address calculated from runtime PC."""
    c = NativeCode(base)
    c.emit("9c 50 51 52")  # Original flags/scratch registers survive.
    c.call(c.base + len(c.data) + 5)
    pc_rva = c.base + len(c.data)
    c.emit("5a 81 c2")
    c.data.extend(struct.pack("<i", state_rva - pc_rva))
    c.emit("52 56")  # cdecl args: state, output(ESI).
    c.call(helper_address)
    c.emit("83 c4 08 5a 59 58 9d")
    c.emit(HOOK_BYTES.hex())
    c.emit("e9")
    c.data.extend(struct.pack("<i", RESUME - c.base - len(c.data) - 4))
    return c.finish()


def _native_ranges():
    # Every original MainMenuCameraNavigater method, including drag and Start,
    # plus remaining original camera behavior. The gyro getter alone is hooked.
    result = []
    for method in range(66891, 66900):
        start = a.pointer(a.M[method])
        end = min(value for value in a.ADDR if value > start)
        result.append((start, end, a.N[method]))
    return result


def _headers(binary):
    if not isinstance(binary, bytearray):
        raise TypeError("install requires a bytearray")
    if len(binary) != ORIGINAL_LENGTH:
        raise ValueError("Unexpected library length or guard already installed")
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", binary)
    if header != a.H:
        raise ValueError("Unexpected original ELF header")
    ph = [struct.unpack_from("<8I", binary, ORIGINAL_PH + i * PH_SIZE)
          for i in range(ORIGINAL_PH_COUNT)]
    original_ph = [struct.unpack_from("<8I", a.E, ORIGINAL_PH + i * PH_SIZE)
                   for i in range(ORIGINAL_PH_COUNT)]
    if ph != original_ph:
        raise ValueError("Original program headers changed")
    if ph[0][0] != 6 or ph[1] != (1, 0, 0, 0, 0x3372FC4, 0x3372FC4, 5, PAGE) or \
            ph[2] != (1, 0x3373000, 0x3373000, 0x3373000, 0x267D60, 0x2DE96C, 6, PAGE):
        raise ValueError("Unreviewed LOAD/PHDR layout")
    if binary[header[6]:header[6] + header[11] * header[12]] != \
            a.E[header[6]:header[6] + header[11] * header[12]]:
        raise ValueError("Original section headers changed")
    bss = struct.unpack_from("<10I", binary, header[6] + 21 * header[11])
    if bss != a.SECTIONS[21] or bss[1] != 8 or bss[3] + bss[5] != STATE_RVA:
        raise ValueError("Unreviewed original BSS boundary")
    if ph[2][2] + ph[2][5] != STATE_RVA:
        raise ValueError("RW LOAD/BSS tail mismatch")
    if binary[HOOK:HOOK + 5] != HOOK_BYTES:
        raise ValueError("Original gyro epilogue changed")
    getter_start = a.pointer(a.M[18080])
    getter_end = a.pointer(a.M[18081])
    if binary[getter_start:getter_end] != a.E[getter_start:getter_end]:
        raise ValueError("Original gyro getter changed")
    for start, end, name in _native_ranges():
        if binary[start:end] != a.E[start:end]:
            raise ValueError("Original camera/navigation changed: " + name)
    gap_start, gap_end = ph[1][1] + ph[1][4], ph[2][1]
    if gap_end - gap_start != 60 or any(binary[gap_start:gap_end]):
        raise ValueError("Unreviewed original RX/RW alignment padding")
    # State cannot conflict with any original relocation target.
    for section in (a.SECTIONS[5], a.SECTIONS[6]):
        for offset in range(section[4], section[4] + section[5], 8):
            target, _ = struct.unpack_from("<II", binary, offset)
            if STATE_RVA <= target < STATE_RVA + STATE_SIZE:
                raise ValueError("Original relocation addresses reserved new state")
    return header, ph


def install(binary):
    """Append a separate RX LOAD, reserve20 new BSS bytes; return audit manifest.

    All checks and payload construction precede mutation. Existing segment
    file offsets and section-header positions remain unchanged; original bytes
    survive except ELF header fields, BSS size, and the5-byte gyro epilogue JMP.
    """
    header, ph = _headers(binary)
    before = bytes(binary)
    append_offset = _align(len(binary), PAGE)
    segment_rva = _align(STATE_RVA + STATE_SIZE, PAGE)
    if append_offset % PAGE != segment_rva % PAGE:
        raise ValueError("New LOAD violates ELF congruent offset/address rule")
    table_size = NEW_PH_COUNT * PH_SIZE
    helper_rva = segment_rva + _align(table_size, 16)
    helper = make_helper(helper_rva)
    thunk_rva = _align(helper_rva + len(helper), 16)
    thunk = make_thunk(thunk_rva, helper_rva)
    appended_size = thunk_rva + len(thunk) - segment_rva
    new_ph = list(ph)
    new_ph[0] = (6, append_offset, segment_rva, segment_rva,
                 table_size, table_size, 4, 4)
    rw = list(new_ph[2]); rw[5] += STATE_SIZE; new_ph[2] = tuple(rw)
    new_ph.append((1, append_offset, segment_rva, segment_rva,
                   appended_size, appended_size, 5, PAGE))
    # Original LOADs keep all bytes/VA mappings. New BSS ends before new RX.
    loads = [row for row in new_ph if row[0] == 1]
    if any(left[2] + left[5] > right[2] for left, right in zip(loads, loads[1:])):
        raise ValueError("Overlapping LOAD segments")
    if new_ph[2][2] + new_ph[2][5] != STATE_RVA + STATE_SIZE:
        raise ValueError("Invalid new state coverage")
    appended = bytearray(appended_size)
    for i, row in enumerate(new_ph):
        struct.pack_into("<8I", appended, i * PH_SIZE, *row)
    appended[helper_rva - segment_rva:helper_rva - segment_rva + len(helper)] = helper
    appended[thunk_rva - segment_rva:thunk_rva - segment_rva + len(thunk)] = thunk
    candidate = bytearray(binary)
    candidate.extend(bytes(append_offset - len(candidate)))
    candidate.extend(appended)
    struct.pack_into("<I", candidate, 28, append_offset)  # ELF e_phoff.
    struct.pack_into("<H", candidate, 44, NEW_PH_COUNT)
    struct.pack_into("<I", candidate, 0x88, ph[2][5] + STATE_SIZE)
    bss_size_offset = header[6] + 21 * header[11] + 20
    struct.pack_into("<I", candidate, bss_size_offset, a.SECTIONS[21][5] + STATE_SIZE)
    candidate[HOOK:HOOK + 5] = b"\xe9" + struct.pack("<i", thunk_rva - HOOK - 5)
    allowed = ((28, 32), (44, 46), (0x88, 0x8C),
               (bss_size_offset, bss_size_offset + 4), (HOOK, HOOK + 5))
    for index, (old, new) in enumerate(zip(before, candidate)):
        if old != new and not any(low <= index < high for low, high in allowed):
            raise ValueError("Guard unexpectedly changed original bytes")
    for start, end, name in _native_ranges():
        if candidate[start:end] != before[start:end]:
            raise ValueError("Guard changed navigation behavior: " + name)
    manifest = {
        "enabled": True, "scope": "malformed original gyro quaternion input only",
        "input_sha256": hashlib.sha256(before).hexdigest(),
        "output_sha256": hashlib.sha256(candidate).hexdigest(),
        "hook": {"method": 18080, "rva": hex(HOOK), "size": 5,
                 "before": HOOK_BYTES.hex(), "after": bytes(candidate[HOOK:HOOK + 5]).hex(),
                 "resume_rva": hex(RESUME)},
        "helper": {"rva": hex(helper_rva), "file_offset": hex(append_offset + helper_rva - segment_rva),
                   "size": len(helper), "abi": "cdecl void guard(out16,state20)"},
        "thunk": {"rva": hex(thunk_rva), "file_offset": hex(append_offset + thunk_rva - segment_rva),
                  "size": len(thunk), "state_addressing": "runtime PC relative; ASLR safe"},
        "state": {"rva": hex(STATE_RVA), "size": STATE_SIZE, "storage": "new zero-initialized RW BSS tail",
                  "layout": "uint32 has_valid; exact16bytes last_valid", "process_lifetime": True},
        "elf": {"old_phoff": header[5], "new_phoff": append_offset,
                "old_phnum": ORIGINAL_PH_COUNT, "new_phnum": NEW_PH_COUNT,
                "new_rx_rva": segment_rva, "new_rx_file_offset": append_offset,
                "new_rx_size": appended_size, "old_file_length": len(before),
                "new_file_length": len(candidate), "original_section_header_offset": header[6],
                "rw_memsz_before": ph[2][5], "rw_memsz_after": new_ph[2][5],
                "bss_size_before": a.SECTIONS[21][5], "bss_size_after": a.SECTIONS[21][5] + STATE_SIZE},
        "append": {"offset": len(before), "size": len(candidate) - len(before),
                   "sha256": hashlib.sha256(candidate[len(before):]).hexdigest()},
        "prefix_changes": [{"offset": hex(low), "size": high - low,
                            "before": before[low:high].hex(), "after": bytes(candidate[low:high]).hex()}
                           for low, high in allowed],
        "policy": {"invalid": "nonfinite component or f32 squared norm nonfinite/<=~1e-12",
                   "initial_invalid": "identity", "later_invalid": "last valid input",
                   "valid": "exact16bytes preserved, no normalization",
                   "main_gyro_singleton": "current original Input.get_gyro object; native sensor stream"},
        "preserved": [name for _, _, name in _native_ranges()],
        "verification": "static ELF/ranges verified; native harness and device acceptance separate",
    }
    binary[:] = candidate
    return manifest
