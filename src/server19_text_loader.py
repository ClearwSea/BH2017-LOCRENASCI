"""Supply extracted configuration text to the original text loader.

Only absent Resources TextAssets use the versioned external resource directory;
the original config deserializers and startup sequence continue normally.
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
import json
from pathlib import Path
import struct
import analyze19 as a


CAVE = 0xA63D00
CAVE_END = 0xA63EEF
HOOK = 0xD1F590
HOOK_SIZE = 6
ASSET_PRESENT = 0xD1F596
ORIGINAL_RETURN = 0xD1F5C2
ORIGINAL_MISSING = 0xD1F5CA


def text_loader_code():
    """Run only after the original resource loader has returned its asset.

    The six displaced bytes are mov esi,eax; test esi,esi; je missing.
    A present asset resumes the original TextAsset.get_text/UnloadAsset path.
    The missing-asset path has its own frame inside the live original frame;
    both exits restore it and jump back to original code, never return here.
    """
    cave = CAVE
    c = bytearray.fromhex("89 c6 85 f6 0f 85")
    c.extend(struct.pack("<i", ASSET_PRESENT - cave - len(c) - 4))
    c.extend(bytes.fromhex("55 89 e5 53 56 57 83 e4 f0 83 ec 20"))
    fixes = []
    def emit(text): c.extend(bytes.fromhex(text))
    def call(target): c.extend(b"\xe8" + struct.pack("<i", target - cave - len(c) - 5))
    def jump(target): c.extend(b"\xe9" + struct.pack("<i", target - cave - len(c) - 5))
    missing, file_missing = [], []
    def if_missing(opcode, log_path=False):
        emit(opcode)
        (file_missing if log_path else missing).append(len(c))
        c.extend(b"\0" * 4)
    call(cave + len(c) + 5)
    pic = cave + len(c)
    emit("5b")
    def string(value):
        emit("8d 83")
        fixes.append((len(c), value))
        c.extend(b"\0" * 4)
        emit("89 04 24")
        call(0x29549A0)
    def args(): emit("89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00")
    # The saved EBP is the live LoadTextFileToString frame; its second
    # native argument is the original resource name. Keep the original
    # missing-asset error for null/empty names without calling ToLower.
    emit("8b 45 00 8b 40 0c 85 c0")
    if_missing("0f 84")
    emit("83 78 08 00")
    if_missing("0f 84")
    emit("89 04 24 c7 44 24 04 00 00 00 00")
    call(a.pointer(a.M[458]))
    emit("89 c6")
    string("/sdcard/bh3-server19-resources/")
    args()
    emit("89 74 24 08 c7 44 24 0c 00 00 00 00")
    call(a.pointer(a.M[475]))
    emit("89 c6")
    args()
    call(a.pointer(a.M[2873]))
    emit("84 c0")
    if_missing("0f 84", log_path=True)
    emit("89 f0")
    args()
    call(0x222EC7E)
    emit("89 f0")
    args()
    call(a.pointer(a.M[2882]))
    # This helper was entered by JMP with the original locals still live.
    # Restore its frame and let the original epilogue return the string.
    emit("8d 65 f4 5f 5e 5b 5d")
    jump(ORIGINAL_RETURN)
    for pos in file_missing:
        struct.pack_into("<i", c, pos, len(c) - pos - 4)
    # Only the absent-file branch logs its original resource name. The
    # original LoadText frame remains live; no missing text is substituted.
    string("BH3SERVER19_TEXT_MISSING ")
    emit("8b 55 00 8b 52 0c")
    args()
    emit("89 54 24 08 c7 44 24 0c 00 00 00 00")
    call(a.pointer(a.M[475]))
    args()
    call(0x222EC7E)
    for pos in missing:
        struct.pack_into("<i", c, pos, len(c) - pos - 4)
    emit("8d 65 f4 5f 5e 5b 5d")
    # RaiseNull remains at its original address and in its original frame.
    jump(ORIGINAL_MISSING)
    for pos, value in fixes:
        struct.pack_into("<i", c, pos, cave + len(c) - pic)
        c.extend(value.encode() + b"\0")
    assert len(c) < CAVE_END - cave
    return bytes(c)


def install(source, output):
    source, output = Path(source), Path(output)
    b = bytearray(source.read_bytes())
    cave = CAVE
    c = text_loader_code()
    original = a.E[HOOK:HOOK + HOOK_SIZE]
    assert original == bytes.fromhex("89 c6 85 f6 74 34")
    assert b[HOOK:HOOK + HOOK_SIZE] == original
    # Reject the retired disk-first entry adapter if supplied as input.
    assert b[0xD1F511:0xD1F516] == a.E[0xD1F511:0xD1F516]
    old = bytes(b[cave:cave + len(c)])
    assert old == a.E[cave:cave + len(c)]
    b[cave:cave + len(c)] = c
    b[HOOK:HOOK + HOOK_SIZE] = b"\xe9" + struct.pack("<i", cave - HOOK - 5) + b"\x90"
    output.write_bytes(b)
    manifest = json.loads(source.with_suffix(source.suffix + ".json").read_text())
    manifest["output_sha256"] = hashlib.sha256(b).hexdigest()
    manifest["changes"].extend([
        {"offset": hex(cave), "size": len(c), "before": old.hex(), "after": c.hex(),
         "purpose": "external configuration text only after the original resource lookup returns NULL"},
        {"offset": hex(HOOK), "size": HOOK_SIZE, "before": original.hex(),
         "after": bytes(b[HOOK:HOOK + HOOK_SIZE]).hex(),
         "purpose": "preserve original TextAsset read/unload; adapt only the missing-asset branch"}])
    manifest["text_loader"] = {
        "priority": "original Resources/StreamingAssetBundle/AssetBundle lookup before external file",
        "hook": hex(HOOK), "asset_present": hex(ASSET_PRESENT),
        "external_success": hex(ORIGINAL_RETURN), "external_missing": hex(ORIGINAL_MISSING),
        "missing_file_log": "BH3SERVER19_TEXT_MISSING <original resource name>",
        "cave_bytes": len(c), "startup_flags_changed": False,
    }
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(manifest, indent=2))
    print(manifest["output_sha256"])


if __name__ == "__main__":
    import sys
    install(sys.argv[1], sys.argv[2])
