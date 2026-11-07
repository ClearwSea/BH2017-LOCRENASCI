"""Boost head pat affection points and remove battle-gate clamp in touch data."""

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
import subprocess

ROOT = Path(__file__).resolve().parents[1]

HEAD_POINTS_BY_LEVEL = {
    1: 300,
    2: 500,
    3: 1000,
    4: 3000,
    5: 0,
}

TOUCHDATA_TARGETS = [
    ROOT / ".local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/touchdata",
    ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/touchdata",
    ROOT / "server19-run/metadata-device/_exceloutputasset/touchdata",
]

TOUCHLEVELDATA_TARGETS = [
    ROOT / ".local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/touchleveldata",
    ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/touchleveldata",
    ROOT / "server19-run/metadata-device/_exceloutputasset/touchleveldata",
]


def boost_touchdata(input_path: Path) -> bytes:
    bak = input_path.with_suffix(".bak-orig")
    src = bak if bak.exists() else input_path
    data = json.loads(src.read_text(encoding="utf-8"))
    modified_count = 0
    for row in data:
        touch_id = row.get("touchId", 0)
        lvl = row.get("level", 1)
        if touch_id % 100 == 2:
            row["point"] = HEAD_POINTS_BY_LEVEL.get(lvl, 0)
            modified_count += 1
        elif lvl >= 5:
            row["point"] = 0
            modified_count += 1
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print(f"[{input_path.name}] Modified {modified_count} rows in touchdata")
    return encoded.encode("utf-8")


def fix_touchleveldata(input_path: Path) -> bytes:
    if not input_path.exists() or input_path.stat().st_size < 10:
        src = TOUCHLEVELDATA_TARGETS[0]
        data = json.loads(src.read_text(encoding="utf-8"))
    else:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        if not data:
            src = TOUCHLEVELDATA_TARGETS[0]
            data = json.loads(src.read_text(encoding="utf-8"))

    modified_count = 0
    for row in data:
        # Set rate to 0.0 to eliminate QueryLevelUpFeelNeedBattle clamp (stuck at 890)
        row["rate"] = 0.0
        modified_count += 1
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print(f"[{input_path.name}] Cleared battle rate clamp in {modified_count} touchlevel rows")
    return encoded.encode("utf-8")


def main():
    device_id = "REFERENCE_DEVICE"

    # 1. Update touchdata
    for target in TOUCHDATA_TARGETS:
        if not target.exists():
            continue
        bak = target.with_suffix(".bak-orig")
        if not bak.exists():
            bak.write_bytes(target.read_bytes())
        encoded_bytes = boost_touchdata(target)
        target.write_bytes(encoded_bytes)
        sha = hashlib.sha256(encoded_bytes).hexdigest()
        print(f"Updated {target} -> SHA256: {sha}")

    # Push touchdata to phone
    remote_td = "/sdcard/bh3-server19-metadata/_exceloutputasset/touchdata"
    print(f"Pushing to device {device_id}: {remote_td}...")
    subprocess.run(["adb", "-s", device_id, "push", str(TOUCHDATA_TARGETS[0]), remote_td], check=True)
    res = subprocess.run(["adb", "-s", device_id, "shell", f"sha256sum {remote_td}"],
                         capture_output=True, text=True, check=True)
    remote_td_sha = res.stdout.strip().split()[0]
    local_td_sha = hashlib.sha256(TOUCHDATA_TARGETS[0].read_bytes()).hexdigest()
    assert local_td_sha == remote_td_sha, "Remote touchdata SHA mismatch!"
    print(f"Touchdata verified on device: {remote_td_sha}")

    # 2. Update touchleveldata
    for target in TOUCHLEVELDATA_TARGETS:
        bak = target.with_suffix(".bak-orig")
        if target.exists() and not bak.exists():
            bak.write_bytes(target.read_bytes())
        encoded_bytes = fix_touchleveldata(target)
        target.write_bytes(encoded_bytes)
        sha = hashlib.sha256(encoded_bytes).hexdigest()
        print(f"Updated {target} -> SHA256: {sha}")

    # Push touchleveldata to phone
    remote_tld = "/sdcard/bh3-server19-metadata/_exceloutputasset/touchleveldata"
    print(f"Pushing to device {device_id}: {remote_tld}...")
    subprocess.run(["adb", "-s", device_id, "push", str(TOUCHLEVELDATA_TARGETS[0]), remote_tld], check=True)
    res = subprocess.run(["adb", "-s", device_id, "shell", f"sha256sum {remote_tld}"],
                         capture_output=True, text=True, check=True)
    remote_tld_sha = res.stdout.strip().split()[0]
    local_tld_sha = hashlib.sha256(TOUCHLEVELDATA_TARGETS[0].read_bytes()).hexdigest()
    assert local_tld_sha == remote_tld_sha, "Remote touchleveldata SHA mismatch!"
    print(f"Touchleveldata verified on device: {remote_tld_sha}")
    print("ALL touch metadata updates successfully applied and verified on device!")


if __name__ == "__main__":
    main()
