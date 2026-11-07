"""Build a micro-patch on the Sony ARM libil2cpp.so to disable Feedback button.

Patches MainPageContext::OnFeedbackButtonClick entry (0xd9fbdc) to bx lr (0x012fff1e),
preserving all prior daily-quick, typed-isolation, gacha, recharge, and asset fixes.
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
import struct
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "analysis-deps"))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

SOURCE = ROOT / "server19-run/sony-arm/daily-quick-v1/libil2cpp.so"
DEST_DIR = ROOT / ".local-baseline/server19-dev/sony-arm-feedback-v1"
DEST_DIR.mkdir(parents=True, exist_ok=True)
DEST = DEST_DIR / "libil2cpp.so"

RUN_DEST_DIR = ROOT / "server19-run/sony-arm/feedback-v1"
RUN_DEST_DIR.mkdir(parents=True, exist_ok=True)
RUN_DEST = RUN_DEST_DIR / "libil2cpp.so"

TARGET_ADDR = 0xd9fbdc
EXPECTED_INSN = 0xe92d4ff0  # push {r4, r5, r6, r7, r8, sb, sl, fp, lr}
PATCH_INSN = 0xe12fff1e     # bx lr (unconditional)


def build():
    data = bytearray(SOURCE.read_bytes())

    actual = struct.unpack_from("<I", data, TARGET_ADDR)[0]
    assert actual == EXPECTED_INSN, f"Preimage mismatch at {hex(TARGET_ADDR)}: {hex(actual)} != {hex(EXPECTED_INSN)}"

    struct.pack_into("<I", data, TARGET_ADDR, PATCH_INSN)

    # Disassembly verification
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    dis = list(md.disasm(data[TARGET_ADDR:TARGET_ADDR + 4], TARGET_ADDR))
    assert len(dis) == 1 and dis[0].mnemonic == "bx" and dis[0].op_str == "lr", f"Disasm verification failed: {dis}"

    DEST.write_bytes(data)
    RUN_DEST.write_bytes(data)
    print(f"Successfully built feedback-disabled ARM libil2cpp.so to {DEST} and {RUN_DEST}")
    return DEST


if __name__ == "__main__":
    build()
