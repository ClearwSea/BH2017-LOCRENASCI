"""Supply missing JSON text at four original async configuration consumers.

Each original request, operation and yield runs unchanged. The original getter
is called first. Only its NULL result can use the resource path still held by
the original coroutine, and only an existing versioned disk file is accepted.
These four consumers call virtual Object.ToString and their original JSON
deserializer; String.ToString returns the supplied text unchanged. This does
not globally alter the UnityEngine.Object return type of get_asset, construct
a TextAsset, initialize modules, or advance any startup state.
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

CAVE = 0xA6034F  # Unused FakePacketHelper body; no fake packet method is called.
CAVE_END = 0xA60636
GET_ASSET = 0x108FA97
DEVICE_ROOT = "/sdcard/bh3-server19-resources/"
GLOBAL_CONFIG_USAGE_GOT = 0x33E39D8 - 0x68E90

CONSUMERS = (
    {"name": "EffectData effect-pattern-name registry", "hook": 0x998CD8,
     "method": 59769, "request_field": "0x34", "path": "coroutine[0x0c][coroutine[0x30]]",
     "to_string": 0x998D0D, "parse": 0x998D47},
    {"name": "GraphicsSettingData volatile registry", "hook": 0xAF285F,
     "method": 60266, "request_field": "0x0c", "path": "GlobalConfig.metaConfig[0x4c]",
     "to_string": 0xAF2894, "parse": 0xAF28CE},
    {"name": "GraphicsSettingData setting registries", "hook": 0xAF2B04,
     "method": 60266, "request_field": "0x2c", "path": "coroutine[0x28]",
     "to_string": 0xAF2B39, "parse": 0xAF2E61},
    {"name": "AIData group-AI grid registries", "hook": 0xD9730E,
     "method": 58807, "request_field": "0x30", "path": "coroutine[0x2c]",
     "to_string": 0xD97343, "parse": 0xD97406},
)


class JsonCode(Code):
    def __init__(self, base):
        super().__init__(base)
        self.labels, self.fixups = {}, []

    def label(self, name):
        self.labels[name] = len(self.data)

    def jump(self, opcode, name):
        self.fixups.append((self.branch(opcode), name))

    def guard(self):
        self.emit("85 c0")
        self.jump("0f 84", "missing")

    def argsn(self, *values):
        regs = {name: i for i, name in enumerate(("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"))}
        for i, value in enumerate(values):
            offset = i * 4
            if isinstance(value, int):
                self.data.extend(bytes((0xC7, 0x04 if not offset else 0x44, 0x24)))
                if offset:
                    self.data.append(offset)
                self.data.extend(struct.pack("<I", value))
            else:
                self.data.extend(bytes((0x89, (0x04 if not offset else 0x44) + regs[value] * 8, 0x24)))
                if offset:
                    self.data.append(offset)

    def finish(self):
        for pos, name in self.fixups:
            struct.pack_into("<i", self.data, pos, self.labels[name] - pos - 4)
        return super().finish()


def payload(device_root=DEVICE_ROOT):
    if not device_root.startswith("/") or not device_root.endswith("/"):
        raise ValueError("Expected an absolute device resource directory ending in /")
    c = JsonCode(CAVE)
    entries = []
    # Four direct-call veneers retain the original two-argument getter ABI.
    for selector in range(4):
        entries.append(CAVE + len(c.data))
        c.emit("b8")
        c.data.extend(struct.pack("<I", selector))
        c.jump("e9", "start")
    c.label("start")
    c.emit("55 89 e5 53 56 57 83 e4 f0 83 ec 40 89 44 24 30")
    c.pic()
    c.emit("8b 45 08 89 04 24 8b 45 0c 89 44 24 04")
    c.call(GET_ASSET)
    c.emit("85 c0")
    c.jump("0f 85", "done")
    # MoveNext has an EBP frame and holds its coroutine at [caller EBP+8].
    # Resolve it only after the original getter has genuinely returned NULL.
    c.emit("8b 45 00")
    c.guard()
    c.emit("8b 78 08 89 f8")
    c.guard()
    c.emit("8b 44 24 30 83 f8 00")
    c.jump("0f 84", "effect_path")
    c.emit("83 f8 01")
    c.jump("0f 84", "volatile_path")
    c.emit("83 f8 02")
    c.jump("0f 84", "graphics_path")
    c.emit("83 f8 03")
    c.jump("0f 85", "missing")
    c.emit("8b 47 2c")
    c.jump("e9", "read_path")
    c.label("graphics_path")
    c.emit("8b 47 28")
    c.jump("e9", "read_path")
    c.label("effect_path")
    c.emit("8b 47 0c")
    c.guard()
    c.emit("8b 4f 30 3b 48 0c")
    c.jump("0f 83", "missing")  # Unsigned guard also rejects negative indices.
    c.emit("8b 44 88 10")
    c.jump("e9", "read_path")
    c.label("volatile_path")
    # The original volatile path is global, rather than saved in a local field.
    c.emit("8b 83")
    c.data.extend(struct.pack("<i", GLOBAL_CONFIG_USAGE_GOT - c.pic_base))
    for code in ("8b 00", "8b 40 50", "8b 00", "8b 40 4c"):
        c.guard()
        c.emit(code)
    c.label("read_path")
    c.guard()
    c.argsn("eax", 0)
    c.call(a.pointer(a.M[458]))  # String.ToLower: exported resource paths.
    c.emit("89 c6")
    c.string(device_root)
    c.argsn(0, "eax", "esi", 0)
    c.call(a.pointer(a.M[475]))  # String.Concat(root, path).
    c.emit("89 c6")
    c.argsn(0, "esi", 0)
    c.call(a.pointer(a.M[2873]))  # File.Exists.
    c.emit("84 c0")
    c.jump("0f 84", "missing")
    c.argsn(0, "esi", 0)
    c.call(0x222EC7E)  # Original Debug.Log records the actual input resource.
    c.argsn(0, "esi", 0)
    c.call(a.pointer(a.M[2882]))  # File.ReadAllText, original JSON follows.
    c.jump("e9", "done")
    c.label("missing")
    c.emit("31 c0")
    c.label("done")
    c.emit("8d 65 f4 5f 5e 5b 5d c3")
    return c.finish(), entries


def install(binary, device_root=DEVICE_ROOT):
    """Patch a root-owned bytearray and return exact reviewable changes."""
    code, entries = payload(device_root)
    if len(code) > CAVE_END - CAVE:
        raise ValueError("Async JSON resource supplier exceeds approved storage")
    if binary[CAVE:CAVE + len(code)] != a.E[CAVE:CAVE + len(code)]:
        raise ValueError("Async JSON supplier storage already modified")
    hooks = []
    for consumer, entry in zip(CONSUMERS, entries):
        address = consumer["hook"]
        before = b"\xe8" + struct.pack("<i", GET_ASSET - address - 5)
        if a.E[address:address + 5] != before or binary[address:address + 5] != before:
            raise ValueError(f"Original JSON get_asset call changed at {address:#x}")
        after = b"\xe8" + struct.pack("<i", entry - address - 5)
        hooks.append((address, before, after, consumer))
    changes = [{"offset": hex(CAVE), "size": len(code),
                "before": bytes(binary[CAVE:CAVE + len(code)]).hex(),
                "after": code.hex(), "purpose": "missing async JSON disk resource input"}]
    binary[CAVE:CAVE + len(code)] = code
    for address, before, after, consumer in hooks:
        binary[address:address + 5] = after
        changes.append({"offset": hex(address), "size": 5,
                        "before": before.hex(), "after": after.hex(),
                        "purpose": consumer["name"] + " resource input"})
    return {"device_root": device_root, "stub_bytes": len(code),
            "flow": "original async request and getter; missing JSON disk text; original ToString and parse",
            "consumers": [{**item, "hook": hex(item["hook"]),
                           "to_string": hex(item["to_string"]), "parse": hex(item["parse"]),
                           "entry": hex(entry)} for item, entry in zip(CONSUMERS, entries)],
            "changes": changes}
