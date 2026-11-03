
import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent

# Load common materials goods pool
cfg = json.loads((ROOT / "server19_shop_config.json").read_text(encoding="utf-8"))
common_pool = set(cfg[0]["goods_pool"])
print(f"Common materials pool contains {len(common_pool)} goods IDs.")

# Target files
targets = [
    ROOT / "server19-run/metadata-device/_exceloutputasset/shopgoodsdata",
    ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/shopgoodsdata",
]

for target in targets:
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
        modified_count = 0
        for item in data:
            if item.get("ID") in common_pool:
                item["ItemNum"] = 100
                modified_count += 1
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Updated {modified_count} goods in {target.relative_to(ROOT)}.")

# Push to device
device_file = ROOT / "server19-run/metadata-device/_exceloutputasset/shopgoodsdata"
if device_file.exists():
    cmd = ["adb", "-s", "REFERENCE_DEVICE", "push", str(device_file), "/sdcard/bh3-server19-metadata/_exceloutputasset/shopgoodsdata"]
    subprocess.run(cmd, check=True)
    print("Pushed updated shopgoodsdata to Sony device.")
