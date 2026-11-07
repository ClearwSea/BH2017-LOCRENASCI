"""Trace MessagePack invalid-code exception sources without changing behavior.

Only the original exception message prefix selects logging. The original
constructor, caller's throw, resource bytes, deserializers and flags stay intact.
The unused method body is storage only and is never called as FakePacket code.
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
import struct

import analyze19 as a

CAVE = 0xA5F67C
CAVE_END = 0xA5FD6B
HOOK = 0x234E21C
HOOK_SIZE = 5
GOT = 0x33E39D8
FRAME_COUNT = 8
FRAME_LIMIT = 0x10000
PREFIX = "code is invalid."
FORMAT = "BH3SERVER19_MSGPACK " + " ".join(f"source{i}=%08x" for i in range(FRAME_COUNT))


def payload():
    code = bytearray.fromhex("55 89 e5 53 57 56 83 e4 f0 81 ec 80 01 00 00")
    labels, fixups = {}, []

    def emit(value):
        code.extend(bytes.fromhex(value))

    def call(address):
        code.extend(b"\xe8" + struct.pack("<i", address - CAVE - len(code) - 5))

    def branch(opcode, label):
        emit(opcode)
        fixups.append((len(code), label))
        code.extend(bytes(4))

    def label(name):
        labels[name] = len(code)

    call(CAVE + len(code) + 5)
    pic = CAVE + len(code)
    emit("5b 81 c3")
    code.extend(struct.pack("<i", GOT - pic))

    # The original constructor arguments remain in the original stack slots.
    # Managed String: object header +8 length, +c UTF-16 character data.
    emit("8b 4d 0c 85 c9")
    branch("0f 84", "restore")
    emit("83 79 08 " + f"{len(PREFIX):02x}")
    branch("0f 8c", "restore")
    prefix = PREFIX.encode("utf-16le")
    for offset in range(0, len(prefix), 4):
        emit("81 79 " + f"{12 + offset:02x}")
        code.extend(prefix[offset:offset + 4])
        branch("0f 85", "restore")

    # Runtime image base = runtime GOT address - original GOT RVA.
    emit("8d b3")
    code.extend(struct.pack("<i", -GOT))
    emit("8b 45 04 29 f0 89 44 24 08")
    for index in range(1, FRAME_COUNT):
        emit("c7 44 24 " + f"{8 + index * 4:02x}" + " 00 00 00 00")

    # The first linked EBP belongs to the original decoder, whose saved return
    # address points at ReadPrimitive. Each accepted frame must be aligned,
    # strictly above the preceding frame, and fit in [EBP, EBP + 64 KiB).
    # EBP is already above current ESP, so this also enforces the lower bound.
    emit("89 ea 81 c2")
    code.extend(struct.pack("<I", FRAME_LIMIT - 8))
    branch("0f 82", "log")  # Unsigned overflow of the upper bound.
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
    format_fixup = len(code)
    code.extend(bytes(4))
    emit("89 44 24 04 8d b4 24 80 00 00 00 89 34 24 ff 93 f4 17 00 00 89 34 24")
    call(0x29549A0)  # il2cpp_string_new: native log buffer -> managed String.
    emit("89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00")
    call(0x222EC7E)  # Debug.Log; no exception catch or state modification.
    label("restore")
    emit("8d 65 f4 5e 5f 5b 5d")
    original = a.E[HOOK:HOOK + HOOK_SIZE]
    assert original == bytes.fromhex("55 89 e5 53 56")
    code.extend(original)
    code.extend(b"\xe9" + struct.pack("<i", HOOK + HOOK_SIZE - CAVE - len(code) - 5))

    code_size = len(code)
    struct.pack_into("<i", code, format_fixup, CAVE + len(code) - GOT)
    code.extend(FORMAT.encode("ascii") + b"\0")
    for position, name in fixups:
        struct.pack_into("<i", code, position, labels[name] - position - 4)
    if len(code) > CAVE_END - CAVE:
        raise ValueError("MessagePack diagnostic exceeds its reserved unused body")
    # Buffer is 256 bytes; all eight unsigned RVAs print as exactly eight hex
    # digits. The longest output including the terminator fits without truncation.
    assert len(FORMAT.replace("%08x", "0" * 8)) + 1 <= 0x100
    return bytes(code), code_size


def install(binary):
    """Patch an existing bytearray; root owns all file writes and deployment."""
    code, code_size = payload()
    original = a.E[HOOK:HOOK + HOOK_SIZE]
    if bytes(binary[HOOK:HOOK + HOOK_SIZE]) != original:
        raise ValueError("InvalidOperationException constructor is already patched")
    before = bytes(binary[CAVE:CAVE + len(code)])
    if before != a.E[CAVE:CAVE + len(code)]:
        raise ValueError("MessagePack diagnostic cave is already occupied")
    jump = b"\xe9" + struct.pack("<i", CAVE - HOOK - 5)
    binary[CAVE:CAVE + len(code)] = code
    binary[HOOK:HOOK + HOOK_SIZE] = jump
    return {
        "purpose": "record original MessagePack invalid-code call sources; retain original exception",
        "message_prefix": PREFIX,
        "constructor": hex(HOOK),
        "resume": hex(HOOK + HOOK_SIZE),
        "cave_bytes": len(code),
        "code_bytes": code_size,
        "frames": FRAME_COUNT,
        "frame_guards": "4-byte alignment, strictly increasing, at most 64 KiB above live EBP",
        "log_format": FORMAT,
        "changes": [
            {"offset": hex(CAVE), "size": len(code), "before": before.hex(), "after": code.hex(),
             "purpose": "MessagePack exception source logging only"},
            {"offset": hex(HOOK), "size": HOOK_SIZE, "before": original.hex(), "after": jump.hex(),
             "purpose": "trace selected messages, replay original constructor prologue and resume"},
        ],
    }
