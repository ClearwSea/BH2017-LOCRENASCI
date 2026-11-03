"""Deploy updated metadata (constvaluesclient, materialdata) and patched libil2cpp.so to Sony device.

Strict safety checks:
- Device identity and serial check
- No game process running
- SHA-256 pre-check and readback verification
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
import hashlib
import json
import shlex
import time

import server19_device as device
import server19_sony_monitor as sony

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "server19-run/sony-deploy-record"
RUN.mkdir(parents=True, exist_ok=True)

EXPECTED_BEFORE_LIB_SHA = "839cedd5b2731810886453ff53d739e3f4b960cb57e249d5e21a7acb599cb73d"
CANDIDATE_LIB = ROOT / "server19-run/sony-arm/feedback-v1/libil2cpp.so"
CANDIDATE_CONSTVALUES = ROOT / ".local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset/constvaluesclient"
CANDIDATE_MATERIALDATA = ROOT / ".local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset/materialdata"


def file_sha(raw_bytes):
    return hashlib.sha256(raw_bytes).hexdigest()


def remote_sha(remote_path):
    out = device.shell("sha256sum " + shlex.quote(remote_path), root=True).strip()
    return out.split()[0] if out else ""


def main():
    device.SERIAL = sony.SERIAL
    identity = sony.identity()

    # 1. Verify game is not running
    pid = device.shell("pidof " + device.PKG + " || true").strip()
    if pid:
        raise ValueError(f"Game is running with pid {pid}; must exit game before updating.")

    lib_target = identity["library"]
    current_lib_sha = remote_sha(lib_target)
    if current_lib_sha != EXPECTED_BEFORE_LIB_SHA:
        raise ValueError(f"Unexpected remote library sha256: {current_lib_sha} != {EXPECTED_BEFORE_LIB_SHA}")

    candidate_lib_bytes = CANDIDATE_LIB.read_bytes()
    candidate_lib_sha = file_sha(candidate_lib_bytes)

    candidate_cv_bytes = CANDIDATE_CONSTVALUES.read_bytes()
    candidate_cv_sha = file_sha(candidate_cv_bytes)

    candidate_md_bytes = CANDIDATE_MATERIALDATA.read_bytes()
    candidate_md_sha = file_sha(candidate_md_bytes)

    out_dir = RUN / ("update-" + time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(exist_ok=False)

    print(f"Deploying to {identity['serial']} ({identity['package']})...")

    # 2. Deploy constvaluesclient
    cv_target = "/sdcard/bh3-server19-metadata/_exceloutputasset/constvaluesclient"
    device.adb("pull", cv_target, str(out_dir / "constvaluesclient-before"))
    cv_tmp = "/data/local/tmp/constvaluesclient.next"
    device.adb("push", str(CANDIDATE_CONSTVALUES), cv_tmp)
    device.shell("cat " + shlex.quote(cv_tmp) + " > " + shlex.quote(cv_target), root=True)
    device.shell("rm -f " + shlex.quote(cv_tmp), root=True)
    readback_cv_sha = remote_sha(cv_target)
    if readback_cv_sha != candidate_cv_sha:
        raise ValueError(f"constvaluesclient readback sha mismatch: {readback_cv_sha} != {candidate_cv_sha}")
    print("constvaluesclient successfully deployed and verified.")

    # 3. Deploy materialdata
    md_target = "/sdcard/bh3-server19-metadata/_exceloutputasset/materialdata"
    device.adb("pull", md_target, str(out_dir / "materialdata-before"))
    md_tmp = "/data/local/tmp/materialdata.next"
    device.adb("push", str(CANDIDATE_MATERIALDATA), md_tmp)
    device.shell("cat " + shlex.quote(md_tmp) + " > " + shlex.quote(md_target), root=True)
    device.shell("rm -f " + shlex.quote(md_tmp), root=True)
    readback_md_sha = remote_sha(md_target)
    if readback_md_sha != candidate_md_sha:
        raise ValueError(f"materialdata readback sha mismatch: {readback_md_sha} != {candidate_md_sha}")
    print("materialdata successfully deployed and verified.")

    # 4. Deploy libil2cpp.so
    device.adb("pull", lib_target, str(out_dir / "libil2cpp-before.so"))
    lib_tmp = "/data/local/tmp/libil2cpp-feedback.so.next"
    device.adb("push", str(CANDIDATE_LIB), lib_tmp)
    if remote_sha(lib_tmp) != candidate_lib_sha:
        raise ValueError("Staged library sha mismatch on device")

    device.shell("cat " + shlex.quote(lib_tmp) + " > " + shlex.quote(lib_target), root=True)
    device.shell("rm -f " + shlex.quote(lib_tmp), root=True)
    readback_lib_sha = remote_sha(lib_target)
    if readback_lib_sha != candidate_lib_sha:
        raise ValueError(f"libil2cpp.so readback sha mismatch: {readback_lib_sha} != {candidate_lib_sha}")
    print("libil2cpp.so successfully deployed and verified.")

    record = {
        "timestamp": time.time(),
        "serial": identity["serial"],
        "package": identity["package"],
        "library_target": lib_target,
        "library_sha_before": current_lib_sha,
        "library_sha_after": readback_lib_sha,
        "constvalues_sha_after": readback_cv_sha,
        "materialdata_sha_after": readback_md_sha,
        "status": "deployed_and_verified",
    }
    (out_dir / "deployment.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"Deployment record written to {out_dir / 'deployment.json'}")
    return record


if __name__ == "__main__":
    main()
