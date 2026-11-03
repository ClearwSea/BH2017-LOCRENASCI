
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

def restore_constvaluesclient(path: Path) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    for row in data:
        if row.get("name") == "basicconfig_PlayerLevelNeedEnterIsland":
            row["value"] = "23"
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(encoded)
    return encoded

def generate_official_full_cabinleveldata() -> bytes:
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

        entry = {
            "cabinType": int(row_dict["cabinType"]),
            "cabinName": row_dict["cabinName"],
            "level": int(row_dict["level"]),
            "playerLevelNeed": int(row_dict["playerLevelNeed"]),
            "scoinNeed": int(row_dict.get("scoinNeed", 0) or 0),
            "itemListNeed": item_list,
            "upLevelTimeNeed": int(row_dict.get("upLevelTimeNeed", 0) or 0),
        }
        rows.append(entry)

    assert len(rows) == 325, f"Expected 325 cabinleveldata rows, got {len(rows)}"
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return encoded

def update_account_level(account_path: Path):
    if not account_path.exists():
        return
    acc = json.loads(account_path.read_text(encoding="utf-8"))
    main = acc.setdefault("main", {})
    main["level"] = 39
    main["exp"] = 0
    main["stamina"] = max(main.get("stamina", 0), 119)
    account_path.write_text(json.dumps(acc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated account level to 39 in {account_path}")

def main():
    device_id = "REFERENCE_DEVICE"

    # 1. Restore constvaluesclient to level 23 gate
    for target in CONSTVALUESCLIENT_TARGETS:
        if target.exists():
            restore_constvaluesclient(target)
            print(f"Restored basicconfig_PlayerLevelNeedEnterIsland=23 in {target.name}")

    # Push constvaluesclient to phone
    device_cvc = ROOT / "server19-run/metadata-device/_exceloutputasset/constvaluesclient"
    subprocess.run(["adb", "-s", device_id, "push", str(device_cvc), "/sdcard/bh3-server19-metadata/_exceloutputasset/constvaluesclient"], check=True)
    print("Pushed constvaluesclient to Sony device.")

    # 2. Generate and write official full cabinleveldata (325 rows with official playerLevelNeed)
    cabin_bytes = generate_official_full_cabinleveldata()
    for target in CABINLEVELDATA_TARGETS:
        target.write_bytes(cabin_bytes)
        print(f"Wrote official 325-row cabinleveldata to {target.name}")

    # Push cabinleveldata to phone
    device_cld = ROOT / "server19-run/metadata-device/_exceloutputasset/cabinleveldata"
    subprocess.run(["adb", "-s", device_id, "push", str(device_cld), "/sdcard/bh3-server19-metadata/_exceloutputasset/cabinleveldata"], check=True)
    print("Pushed official 325-row cabinleveldata to Sony device.")

    # 3. Update account level to 39
    account_paths = [
        ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json",
        ROOT / "server19-run/account.json",
        ROOT / "account.json",
    ]
    for ap in account_paths:
        update_account_level(ap)

if __name__ == "__main__":
    main()
