"""Supply missing typed table assets to the original native metadata readers.

The previous resource loader runs first. Only versioned files exported from
reference data are accepted; no player, module, reader or page is initialized
here. Native readers retain their own indexing and resource cleanup.
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
from server19_baked import Code

CAVE = 0xA62CD9
CAVE_END = 0xA63922
HOOK = 0x268673E
DEVICE_ROOT = "/sdcard/bh3-server19-metadata/"
CHAR_FIELDS = ("paramLogic_1", "paramLogic_2", "paramLogic_3")


class NativeCode(Code):
    def __init__(self, base):
        super().__init__(base)
        self.labels, self.fixups = {}, []

    def argsn(self, *values):
        regs = {name: i for i, name in enumerate(("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"))}
        for i, value in enumerate(values):
            offset = i * 4
            if isinstance(value, int):
                self.data.extend(bytes((0xC7, 0x04 if not offset else 0x44, 0x24)))
                if offset: self.data.append(offset)
                self.data.extend(struct.pack("<I", value))
            else:
                self.data.extend(bytes((0x89, (0x04 if not offset else 0x44) + regs[value] * 8, 0x24)))
                if offset: self.data.append(offset)

    def jump(self, opcode, name):
        self.fixups.append((self.branch(opcode), name))

    def guard(self):
        self.emit("85 c0")
        self.jump("0f 84", "failed")

    def label(self, name):
        self.labels[name] = len(self.data)

    def finish(self):
        for pos, name in self.fixups:
            struct.pack_into("<i", self.data, pos, self.labels[name] - pos - 4)
        return super().finish()


def char_fixups(c):
    """Restore source Char columns without the old serializer's String boxing."""
    c.string(".chars")
    c.emit("8b 54 24 78")
    c.argsn(0, "edx", "eax", 0)
    c.call(a.pointer(a.M[475]))
    c.emit("89 44 24 64")
    c.argsn(0, "eax", 0)
    c.call(a.pointer(a.M[2873]))
    c.emit("84 c0")
    c.jump("0f 84", "chars_done")
    c.emit("8b 44 24 64")
    c.argsn(0, "eax", 0)
    c.call(a.pointer(a.M[2879]))
    c.emit("89 44 24 64 8b 54 24 58 8b 4a 0c 89 4c 24 6c 6b c9 06 3b 48 0c")
    c.jump("0f 85", "failed")
    c.emit("83 7c 24 6c 00")
    c.jump("0f 84", "chars_done")
    c.emit("8b 52 08 89 54 24 68 8d 70 10")
    for index, field in enumerate(CHAR_FIELDS):
        c.raw_string(field)
        c.emit("8b 54 24 68 8b 52 10 8b 12")
        c.argsn("edx", "eax")
        c.call(0x2952F90)
        c.guard()
        c.argsn("eax")
        c.call(0x2953B90)
        c.emit("89 44 24 60 31 ff")
        c.label("chars_loop_" + str(index))
        c.emit("8b 44 24 68 8b 44 b8 10")
        c.guard()
        c.emit("8b 54 24 60 66 8b 0e 66 89 0c 10 83 c6 02 47 3b 7c 24 6c")
        c.jump("0f 8c", "chars_loop_" + str(index))
    c.label("chars_done")


def phase(c, value):
    c.emit("89 84 24 80 00 00 00")
    c.string("BH3SERVER19_TABLE_" + value + " ")
    c.emit("8b 54 24 78")
    c.argsn(0, "eax", "edx", 0)
    c.call(a.pointer(a.M[475]))
    c.argsn(0, "eax", 0)
    c.call(0x222EC7E)
    c.emit("8b 84 24 80 00 00 00")


def payload(previous_loader):
    c = NativeCode(CAVE)
    c.emit("55 89 e5 53 56 57 83 e4 f0 81 ec 90 00 00 00")
    c.pic()
    # Original generic signature: unused this, path, asset mode, MethodInfo.
    c.emit("8b 45 08 89 04 24 8b 45 0c 89 44 24 04 8b 45 10 89 44 24 08 8b 45 14 89 44 24 0c")
    c.call(previous_loader)
    c.emit("85 c0")
    c.jump("0f 85", "done")
    c.emit("8b 45 0c")
    c.guard()
    c.argsn("eax", 0)
    c.call(a.pointer(a.M[458]))
    c.emit("89 c6")
    c.string(DEVICE_ROOT)
    c.argsn(0, "eax", "esi", 0)
    c.call(a.pointer(a.M[475]))
    c.emit("89 44 24 78")
    c.argsn(0, "eax", 0)
    c.call(a.pointer(a.M[2873]))
    c.emit("84 c0")
    c.jump("0f 84", "failed")
    c.emit("8b 44 24 78")
    c.argsn(0, "eax", 0)
    c.call(0x222EC7E)
    # Resolve the actual inflated generic return type, not a guessed row type.
    c.emit("8b 45 14")
    c.argsn("eax")
    c.call(0x2954000)
    c.guard()
    c.argsn("eax")
    c.call(0x2954E10)
    c.guard()
    c.emit("89 c6")
    c.raw_string("itemList")
    c.argsn("esi", "eax")
    c.call(0x2952F90)
    c.guard()
    c.emit("89 44 24 74")
    c.argsn("eax")
    c.call(0x2953BC0)
    c.argsn("eax")
    c.call(0x2954DB0)
    c.emit("89 44 24 7c")
    c.argsn("esi")
    c.call(0x29532A0)
    c.argsn("eax")
    c.call(0x2954DB0)
    c.argsn(0, "eax", 0)
    c.call(a.pointer(a.M[16691]))
    c.guard()
    c.emit("89 44 24 70")
    phase(c, "ASSET")
    # Use the original serializer setup and original fsJsonParser.
    c.argsn(0, 0)
    c.call(a.pointer(a.M[87740]))
    phase(c, "SETUP")
    c.emit("8b 44 24 78")
    c.argsn(0, "eax", 0)
    c.call(a.pointer(a.M[2882]))
    phase(c, "READ")
    # Parse(string, out fsData) reports malformed input instead of throwing
    # through injected code that has no matching exception-unwind metadata.
    # fsResult uses a hidden 8-byte return buffer and callee `ret 4`.
    c.emit("c7 44 24 54 00 00 00 00 8d 94 24 88 00 00 00 8d 4c 24 54")
    c.argsn("edx", 0, "eax", "ecx", 0)
    c.call(a.pointer(a.M[30453]))
    c.emit("83 ec 04 80 bc 24 88 00 00 00 00")
    c.jump("0f 84", "parse_failed")
    c.emit("8b 44 24 54")
    phase(c, "PARSED")
    c.guard()
    c.emit("89 44 24 54 8b 83")
    c.data.extend(struct.pack("<i", 0x33E39D8 - 0x61EAC - c.pic_base))
    c.emit("8b 00")
    c.guard()
    c.emit("8b 40 50")
    c.guard()
    c.emit("8b 40 04")
    c.guard()
    c.emit("89 44 24 50 8b 00 89 c6")
    phase(c, "SERIALIZER")
    c.raw_string("TryDeserialize")
    c.argsn("esi", "eax", 3)
    c.call(0x2952FF0)
    c.guard()
    phase(c, "INVOKE")
    c.emit("c7 44 24 58 00 00 00 00 c7 44 24 5c 00 00 00 00 8b 54 24 54 89 54 24 40 8b 54 24 7c 89 54 24 44 8d 54 24 58 89 54 24 48 8b 54 24 50 8d 4c 24 40 8d 74 24 5c")
    c.argsn("eax", "edx", "ecx", "esi")
    c.call(0x29547B0)
    phase(c, "RETURN")
    c.emit("83 7c 24 5c 00")
    c.jump("0f 85", "exception")
    c.guard()
    c.emit("80 78 08 00")
    c.jump("0f 84", "failed")
    c.emit("8b 44 24 58")
    c.guard()
    char_fixups(c)
    # Store the reference at the runtime-reported field offset.
    c.emit("8b 44 24 74")
    c.argsn("eax")
    c.call(0x2953B90)
    c.emit("8b 54 24 70 8b 4c 24 58 89 0c 02 89 d0")
    phase(c, "READY")
    c.jump("e9", "done")
    c.label("parse_failed")
    phase(c, "PARSE_FAILED")
    c.emit("8d 84 24 88 00 00 00")
    c.argsn("eax", 0)
    c.call(0x15AA60E)  # Original unboxed fsResult message formatter.
    c.argsn(0, "eax", 0)
    c.call(0x222EC7E)
    c.jump("e9", "failed")
    c.label("exception")
    c.emit("8b 44 24 5c")
    c.argsn(0, "eax", 0)
    c.call(a.pointer(a.M[18027]))
    c.label("failed")
    c.emit("31 c0")
    c.label("done")
    c.emit("8d 65 f4 5f 5e 5b 5d c3")
    return c.finish()


def install(binary):
    if binary[HOOK] != 0xE9:
        raise ValueError("Expected the baked supplier to be installed first")
    previous = HOOK + 5 + struct.unpack_from("<i", binary, HOOK + 1)[0]
    if previous != 0xA64300:
        raise ValueError("Unknown previous resource supplier")
    code = payload(previous)
    if len(code) > CAVE_END - CAVE:
        raise ValueError("Typed resource supplier exceeds unused storage")
    assert binary[CAVE:CAVE + len(code)] == a.E[CAVE:CAVE + len(code)]
    binary[CAVE:CAVE + len(code)] = code
    binary[HOOK:HOOK + 5] = b"\xe9" + struct.pack("<i", CAVE - HOOK - 5)
    return {"device_root": DEVICE_ROOT, "stub_bytes": len(code),
            "previous_loader": hex(previous), "hook": hex(HOOK),
            "flow": "native load first, supply missing exported table asset, original reader continues"}
