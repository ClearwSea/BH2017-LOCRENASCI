"""Log original null-throw callers without changing exception behavior."""

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


def install(source, output):
    source, output = Path(source), Path(output)
    b = bytearray(source.read_bytes())
    cave = 0xA63BEF
    code = bytearray.fromhex("55 89 e5 53 57 56 83 e4 f0 81 ec 00 01 00 00")
    def call(target):
        position = cave + len(code)
        code.extend(b"\xe8" + struct.pack("<i", target - position - 5))
    call(cave + len(code) + 5)
    pic = cave + len(code)
    code.extend(b"\x5b\x81\xc3" + struct.pack("<i", 0x33E39D8 - pic))
    code.extend(bytes.fromhex("8d 83 28 c6 c1 fc 8b 55 04 29 c2 89 54 24 08 8b 55 00 8b 52 04 29 c2 89 54 24 0c"))
    fmt = len(code)
    code.extend(b"\x8d\x83\0\0\0\0")
    code.extend(bytes.fromhex("89 44 24 04 8d 74 24 40 89 34 24 ff 93 f4 17 00 00 89 34 24"))
    call(0x29549A0)
    code.extend(bytes.fromhex("89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00"))
    call(0x222EC7E)
    code.extend(bytes.fromhex("8d 65 f4 5e 5f 5b 5d"))
    position = cave + len(code)
    code.extend(b"\xe9" + struct.pack("<i", 0x298B180 - position - 5))
    struct.pack_into("<i", code, fmt + 2, cave + len(code) - 0x33E39D8)
    code.extend(b"BH3SERVER19_NULL caller=%08x parent=%08x\0")
    assert cave + len(code) <= 0xA63CB0
    old = bytes(b[cave:cave + len(code)])
    assert b[0x42D4D0:0x42D4D6] == bytes.fromhex("ff a3 44 00 00 00")
    b[cave:cave + len(code)] = code
    b[0x42D4D0:0x42D4D6] = b"\xe9" + struct.pack("<i", cave - 0x42D4D0 - 5) + b"\x90"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b)
    manifest = json.loads(source.with_suffix(source.suffix + ".json").read_text())
    manifest["output_sha256"] = hashlib.sha256(b).hexdigest()
    manifest["changes"].extend([
        {"offset": hex(cave), "size": len(code), "before": old.hex(), "after": code.hex(),
         "purpose": "diagnostic null caller logging; original exception still thrown"},
        {"offset": "0x42d4d0", "before": "ffa344000000", "after": bytes(b[0x42D4D0:0x42D4D6]).hex(),
         "purpose": "trace and tail-call original null throw"}])
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(manifest, indent=2))
    return manifest["output_sha256"]


if __name__ == "__main__":
    import sys
    print(install(sys.argv[1], sys.argv[2]))
