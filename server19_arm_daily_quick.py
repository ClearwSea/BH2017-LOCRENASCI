"""Build a micro-patch on the Sony ARM libil2cpp.so to filter 30099 from DailyMissionNeedNotify.

Preserves all prior typed-isolation, gacha, recharge, and asset fixes.
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

SOURCE = ROOT / ".local-baseline/server19-dev/sony-arm-gacha-recharge-v1/typed-isolation-v1/libil2cpp.so"
DEST_DIR = ROOT / ".local-baseline/server19-dev/sony-arm-daily-quick-v1"
DEST_DIR.mkdir(parents=True, exist_ok=True)
DEST = DEST_DIR / "libil2cpp.so"

RUN_DEST_DIR = ROOT / "server19-run/sony-arm/daily-quick-v1"
RUN_DEST_DIR.mkdir(parents=True, exist_ok=True)
RUN_DEST = RUN_DEST_DIR / "libil2cpp.so"


def build():
    data = bytearray(SOURCE.read_bytes())

    target_call = 0xe30474
    helper_entry = 0xe457bc
    is_daily_entry = 0xe2f900

    # Verify preimage at 0xe30474: bl #0xe2f900
    expected_bl = 0xebfffd21  # bl 0xe2f900
    actual_bl = struct.unpack_from("<I", data, target_call)[0]
    assert actual_bl == expected_bl, f"Preimage mismatch at {hex(target_call)}: {hex(actual_bl)} != {hex(expected_bl)}"

    disp1 = (helper_entry - target_call - 8) >> 2
    bl_insn = 0xeb000000 | (disp1 & 0xffffff)

    disp2 = (is_daily_entry - (helper_entry + 20) - 8) >> 2
    b_insn = 0xea000000 | (disp2 & 0xffffff)

    helper_code = struct.pack("<6I",
        0xe5913008,          # ldr r3, [r1, #8]
        0xe3072593,          # movw r2, #0x7593 (30099)
        0xe1530002,          # cmp r3, r2
        0x03a00000,          # moveq r0, #0
        0x012fff1e,          # bxeq lr
        b_insn               # b is_daily_entry
    )

    data[target_call:target_call + 4] = struct.pack("<I", bl_insn)
    data[helper_entry:helper_entry + 24] = helper_code

    # Verify
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    bl_dis = list(md.disasm(data[target_call:target_call + 4], target_call))
    assert len(bl_dis) == 1 and bl_dis[0].op_str == "#0xe457bc"

    helper_dis = list(md.disasm(data[helper_entry:helper_entry + 24], helper_entry))
    assert len(helper_dis) == 6

    DEST.write_bytes(data)
    RUN_DEST.write_bytes(data)
    print(f"Successfully built patched ARM libil2cpp.so to {DEST} and {RUN_DEST}")
    return DEST


if __name__ == "__main__":
    build()
