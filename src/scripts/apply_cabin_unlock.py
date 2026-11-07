"""Unlock 23-level gate for Island/Cabin system in constvaluesclient and cabinleveldata.

Generates complete continuous cabinleveldata (325 rows) from official TSV source,
replaces missing levels 2..7, 2..11, 2..4, 2..6, and sets playerLevelNeed=1 for
the beginner upgrade tiers to eliminate level gate banners and NullReferenceExceptions.
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
import subprocess

ROOT = Path(__file__).resolve().parents[1]

CONSTVALUESCLIENT_TARGETS = [
    ROOT / ".local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset/constvaluesclient",
    ROOT / ".local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/constvaluesclient",
    ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/constvaluesclient",
    ROOT / "server19-run/metadata-device/_exceloutputasset/constvaluesclient",
]

CABINLEVELDATA_TARGETS = [
    ROOT / ".local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/cabinleveldata",
    ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/cabinleveldata",
    ROOT / "server19-run/metadata-device/_exceloutputasset/cabinleveldata",
]


def unlock_constvaluesclient(input_path: Path) -> bytes:
    bak = input_path.with_suffix(".bak-orig")
    src = bak if bak.exists() else input_path
    data = json.loads(src.read_text(encoding="utf-8"))
    modified_count = 0
    for row in data:
        if row.get("name") == "basicconfig_PlayerLevelNeedEnterIsland":
            row["value"] = "1"
            modified_count += 1
    assert modified_count > 0, f"basicconfig_PlayerLevelNeedEnterIsland not found in {input_path}"
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print(f"[{input_path.name}] Modified {modified_count} row in constvaluesclient")
    return encoded.encode("utf-8")


def generate_full_cabinleveldata() -> bytes:
    tsv_path = ROOT / ".local-baseline/server19-dev/resource-fallback/data/_exceloutput/cabinleveldata"
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if not line:
            continue
        parts = line.split("\t")
        row_dict = dict(zip(header, parts))

        item_str = row_dict.get("itemListNeed", "").strip()
        item_list = []
        if item_str and item_str != "0:0":
            for item in item_str.split(","):
                if ":" in item:
                    mid, mnum = item.split(":")
                    item_list.append({"itemMetaID": int(mid), "itemNum": int(mnum)})
        if not item_list:
            item_list = [{"itemMetaID": 0, "itemNum": 0}]

        p_lvl_need = int(row_dict["playerLevelNeed"])
        if p_lvl_need == 23:
            p_lvl_need = 1

        entry = {
            "cabinType": int(row_dict["cabinType"]),
            "cabinName": row_dict["cabinName"],
            "level": int(row_dict["level"]),
            "playerLevelNeed": p_lvl_need,
            "scoinNeed": int(row_dict.get("scoinNeed", 0) or 0),
            "itemListNeed": item_list,
            "upLevelTimeNeed": int(row_dict.get("upLevelTimeNeed", 0) or 0),
        }
        rows.append(entry)

    assert len(rows) == 325, f"Expected 325 cabinleveldata rows from TSV, got {len(rows)}"
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    print(f"Generated complete continuous cabinleveldata: {len(rows)} rows")
    return encoded.encode("utf-8")


def main():
    device_id = "REFERENCE_DEVICE"

    # 1. Update constvaluesclient
    for target in CONSTVALUESCLIENT_TARGETS:
        if not target.exists():
            continue
        bak = target.with_suffix(".bak-orig")
        if not bak.exists():
            bak.write_bytes(target.read_bytes())
        encoded_bytes = unlock_constvaluesclient(target)
        target.write_bytes(encoded_bytes)
        sha = hashlib.sha256(encoded_bytes).hexdigest()
        print(f"Updated {target} -> SHA256: {sha}")

    # Push constvaluesclient to phone
    remote_cv = "/sdcard/bh3-server19-metadata/_exceloutputasset/constvaluesclient"
    print(f"Pushing to device {device_id}: {remote_cv}...")
    subprocess.run(["adb", "-s", device_id, "push", str(CONSTVALUESCLIENT_TARGETS[0]), remote_cv], check=True)
    res = subprocess.run(["adb", "-s", device_id, "shell", f"sha256sum {remote_cv}"],
                         capture_output=True, text=True, check=True)
    remote_cv_sha = res.stdout.strip().split()[0]
    local_cv_sha = hashlib.sha256(CONSTVALUESCLIENT_TARGETS[0].read_bytes()).hexdigest()
    assert local_cv_sha == remote_cv_sha, "Remote constvaluesclient SHA mismatch!"
    print(f"Constvaluesclient verified on device: {remote_cv_sha}")

    # 2. Update cabinleveldata with complete 325 continuous rows
    encoded_cld = generate_full_cabinleveldata()
    for target in CABINLEVELDATA_TARGETS:
        if not target.exists():
            continue
        bak = target.with_suffix(".bak-orig")
        if not bak.exists():
            bak.write_bytes(target.read_bytes())
        target.write_bytes(encoded_cld)
        sha = hashlib.sha256(encoded_cld).hexdigest()
        print(f"Updated {target} -> SHA256: {sha}")

    # Push cabinleveldata to phone
    remote_cld = "/sdcard/bh3-server19-metadata/_exceloutputasset/cabinleveldata"
    print(f"Pushing to device {device_id}: {remote_cld}...")
    subprocess.run(["adb", "-s", device_id, "push", str(CABINLEVELDATA_TARGETS[0]), remote_cld], check=True)
    res = subprocess.run(["adb", "-s", device_id, "shell", f"sha256sum {remote_cld}"],
                         capture_output=True, text=True, check=True)
    remote_cld_sha = res.stdout.strip().split()[0]
    local_cld_sha = hashlib.sha256(CABINLEVELDATA_TARGETS[0].read_bytes()).hexdigest()
    assert local_cld_sha == remote_cld_sha, "Remote cabinleveldata SHA mismatch!"
    print(f"Cabinleveldata verified on device: {remote_cld_sha}")
    print("Full Island/Cabin level data deployed and verified on device successfully!")


if __name__ == "__main__":
    main()
