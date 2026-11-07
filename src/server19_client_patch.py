"""Redirect 1.9's existing dispatch URL list after its original deserializer.

The original ConfigChannel object, account branches, network/login handlers and
game initialization flow remain intact. This does not enable network debug or
call FakePacketHelper; one unreachable automatic-test method is storage only.
No device writes are performed by this script.
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
import argparse
import hashlib
import json
import struct
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "1.9.0-official" / "lib__x86__libil2cpp.so"
HOOK = 0x1150465
ORIGINAL_DESERIALIZE = 0x2685878
CAVE = 0xA63A44
CAVE_END = 0xA63B3D
STRING_NEW = 0x29549A0


def relative_call(position, target):
    return b"\xe8" + struct.pack("<i", target - position - 5)


def build(output, dispatch_url, source=ORIGINAL):
    parsed = urlsplit(dispatch_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("Use an explicit HTTP dispatch endpoint without query/fragment")
    dispatch_url.encode("ascii")
    binary = bytearray(source.read_bytes())
    expected = relative_call(HOOK, ORIGINAL_DESERIALIZE)
    if binary[HOOK:HOOK + 5] != expected:
        raise ValueError("The input does not contain the original 1.9 ConfigChannel call")
    if binary[0x5471DF:0x5471E3] != bytes.fromhex("c6 40 01 00"):
        raise ValueError("Input has network debug enabled; use the original x86 library")
    # cdecl: original static call (unused this, JSON string, generic MethodInfo).
    code = bytearray.fromhex("55 89 e5 53 56 57 83 e4 f0 83 ec 20")
    def emit(hexadecimal):
        code.extend(bytes.fromhex(hexadecimal))
    def call(target):
        code.extend(relative_call(CAVE + len(code), target))
    call(CAVE + len(code) + 5)
    pic = CAVE + len(code)
    emit("5b")
    emit("8b 45 08 89 04 24 8b 45 0c 89 44 24 04 8b 45 10 89 44 24 08")
    call(ORIGINAL_DESERIALIZE)
    emit("89 c6 85 f6 0f 84")
    config_guard = len(code)
    code.extend(b"\0" * 4)
    emit("8b 7e 18 85 ff 0f 84")
    array_guard = len(code)
    code.extend(b"\0" * 4)
    emit("8d 83")
    url_fixup = len(code)
    code.extend(b"\0" * 4)
    emit("89 04 24")
    call(STRING_NEW)
    # DispatchUrls is List<string>, proven by the original coroutine's calls to
    # List.Count (0x19ad11a) and List.get_Item (0x19ad12a), not a direct array.
    # List+0xc is _size; List+8 is _items, whose element data begins at +0x10.
    emit("8b 4f 0c 8b 7f 08 85 ff 0f 84")
    items_guard = len(code)
    code.extend(b"\0" * 4)
    # Only occupied URL elements change; preserve list size/capacity/version.
    emit("85 c9 74 07 89 44 8f 0c 49 75 f9")
    done = len(code)
    emit("89 f0 8d 65 f4 5f 5e 5b 5d c3")
    for position in (config_guard, array_guard, items_guard):
        struct.pack_into("<i", code, position, done - position - 4)
    struct.pack_into("<i", code, url_fixup, CAVE + len(code) - pic)
    code.extend(dispatch_url.encode("ascii") + b"\0")
    if len(code) > CAVE_END - CAVE:
        raise ValueError("URL and stub do not fit the reserved unused method")
    old_cave = bytes(binary[CAVE:CAVE + len(code)])
    binary[CAVE:CAVE + len(code)] = code
    binary[HOOK:HOOK + 5] = relative_call(HOOK, CAVE)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(binary)
    manifest = {
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(binary).hexdigest(),
        "dispatch_url": dispatch_url,
        "changes": [
            {"offset": hex(HOOK), "before": expected.hex(),
             "after": bytes(binary[HOOK:HOOK + 5]).hex(),
             "purpose": "post-deserialization dispatch URL list input redirection"},
            {"offset": hex(CAVE), "size": len(code),
             "before": old_cave.hex(), "after": code.hex(),
             "purpose": "storage in unused AutoTestForAndroid method; no debug path invoked"},
        ],
        "preserved": ["DISABLE_NETWORK_DEBUG=false", "original ConfigChannel deserialization",
                      "SDK login", "game transport", "packet consumers", "page lifecycle",
                      "resource loading", "original boot-to-Bridge flow"],
        "verification": "built and statically checked; runtime verification is separate",
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2), encoding="utf8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dispatch-url", required=True)
    parser.add_argument("--source", type=Path, default=ORIGINAL)
    args = parser.parse_args()
    result = build(args.output, args.dispatch_url, args.source)
    print(json.dumps({k: result[k] for k in ["output_sha256", "dispatch_url"]}, indent=2))
