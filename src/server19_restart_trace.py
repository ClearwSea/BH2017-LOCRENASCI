"""Record original RestartGame callers and continue the unmodified function.

This diagnostic uses unused AutoTest storage. It neither invokes AutoTest nor
changes an exception, return value, login state, resource or initialization flag.
Root owns binary file writes, integration and device deployment.
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


CAVE = 0xA63ADC
CAVE_END = 0xA63BEF
FORMAT_SLOT = 0xA63EEF
FORMAT_END = 0xA64000
HOOK = 0xADBA4E
HOOK_SIZE = 6
GOT = 0x33E39D8
FRAME_COUNT = 8
FRAME_LIMIT = 0x10000
FORMAT = "BH3SERVER19_RESTART " + " ".join(
    f"source{i}=%08x" for i in range(FRAME_COUNT)
)


def payload():
    """Return code and a separate NUL-terminated native format string."""
    code = bytearray.fromhex("55 89 e5 53 57 56 83 e4 f0 81 ec 80 01 00 00")
    labels, fixups = {}, []

    def emit(value):
        code.extend(bytes.fromhex(value))

    def call(target):
        code.extend(b"\xe8" + struct.pack("<i", target - CAVE - len(code) - 5))

    def branch(opcode, name):
        emit(opcode)
        fixups.append((len(code), name))
        code.extend(bytes(4))

    def label(name):
        labels[name] = len(code)

    call(CAVE + len(code) + 5)
    pic = CAVE + len(code)
    emit("5b 81 c3")
    code.extend(struct.pack("<i", GOT - pic))
    # Module-relative return addresses, independent of the current PID/base.
    emit("8d b3")
    code.extend(struct.pack("<i", -GOT))
    emit("8b 45 04 29 f0 89 44 24 08")
    for index in range(1, FRAME_COUNT):
        emit("c7 44 24 " + f"{8 + index * 4:02x}" + " 00 00 00 00")

    # EBP is above the current ESP. Linked frames must be four-byte aligned,
    # strictly increasing and contained within 64 KiB of this live stack frame.
    # Stop before dereferencing a frame that fails any check.
    emit("89 ea 81 c2")
    code.extend(struct.pack("<I", FRAME_LIMIT - 8))
    branch("0f 82", "log")
    emit("8b 7d 00 89 e8 b9 01 00 00 00")
    label("walk")
    emit("83 f9 " + f"{FRAME_COUNT:02x}")
    branch("0f 83", "log")
    emit("f7 c7 03 00 00 00")
    branch("0f 85", "log")
    emit("39 c7")
    branch("0f 86", "log")
    emit("39 d7")
    branch("0f 87", "log")
    emit("8b 47 04 29 f0 89 44 8c 08 89 f8 8b 3f 41")
    branch("e9", "walk")

    label("log")
    emit("8d 83")
    code.extend(struct.pack("<i", FORMAT_SLOT - GOT))
    # sprintf writes at ESP+0x80, leaving all eight arguments below it.
    emit("89 44 24 04 8d b4 24 80 00 00 00 89 34 24 ff 93 f4 17 00 00 89 34 24")
    call(0x29549A0)  # il2cpp_string_new.
    emit("89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00")
    call(0x222EC7E)  # Original Debug.Log, without a catch or state update.
    emit("8d 65 f4 5e 5f 5b 5d")
    original = a.E[HOOK:HOOK + HOOK_SIZE]
    assert original == bytes.fromhex("55 89 e5 53 57 56")
    code.extend(original)
    branch("e9", "resume")
    labels["resume"] = HOOK + HOOK_SIZE - CAVE
    for position, name in fixups:
        struct.pack_into("<i", code, position, labels[name] - position - 4)

    fmt = FORMAT.encode("ascii") + b"\0"
    if len(code) > CAVE_END - CAVE or len(fmt) > FORMAT_END - FORMAT_SLOT:
        raise ValueError("Restart diagnostic exceeds its reserved AutoTest storage")
    assert len(FORMAT.replace("%08x", "0" * 8)) + 1 <= 0x100
    return bytes(code), fmt


def install(binary):
    """Apply to a bytearray only; validate all input ranges before mutation."""
    code, fmt = payload()
    jump = b"\xe9" + struct.pack("<i", CAVE - HOOK - 5) + b"\x90"
    patches = [(CAVE, code, "guarded original RestartGame call-source logging"),
               (FORMAT_SLOT, fmt, "native diagnostic format only"),
               (HOOK, jump, "replay original prologue and resume at adba54")]
    input_sha = hashlib.sha256(binary).hexdigest()
    changes = []
    for offset, after, purpose in patches:
        before = bytes(binary[offset:offset + len(after)])
        if before != a.E[offset:offset + len(after)]:
            raise ValueError(f"Restart diagnostic input range {offset:#x} is already occupied")
        changes.append({"offset": hex(offset), "size": len(after),
                        "before": before.hex(), "after": after.hex(), "purpose": purpose})
    for offset, after, _ in patches:
        binary[offset:offset + len(after)] = after
    return {
        "purpose": "record original RestartGame call sources; original restart remains active",
        "entry": hex(HOOK), "resume": hex(HOOK + HOOK_SIZE),
        "code_bytes": len(code), "format_bytes": len(fmt), "frames": FRAME_COUNT,
        "frame_guards": "4-byte alignment, strictly increasing, within 64 KiB above live EBP",
        "callee_saved": "helper restores EBP/EBX/EDI/ESI, then replays the six original entry bytes",
        "application_flags_changed": False, "exceptions_suppressed": False,
        "log_format": FORMAT, "input_sha256": input_sha,
        "output_sha256": hashlib.sha256(binary).hexdigest(), "changes": changes,
    }
