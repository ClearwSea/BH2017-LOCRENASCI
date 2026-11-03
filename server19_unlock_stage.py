"""Clear a stale in-progress stage so a crashed stage can be entered again.

A client crash never sends StageEndReq, so the server keeps `stage_runtime.active`
and answers the next StageBeginReq with retcode 1 whenever the team fingerprint
differs. This helper drops that stale record (after backing the account up) so
the stage can be entered again with any team.

Read-only except for the single `active` field; the account is copied first.
Run with --apply to write.

Usage:
  py -3.13 server19_unlock_stage.py <account.json> [--apply]
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
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    raw = args.account.read_bytes()
    account = json.loads(raw)
    runtime = account.get("stage_runtime")
    if not isinstance(runtime, dict):
        print(json.dumps({"status": "no stage_runtime"}, ensure_ascii=False))
        return 0
    active = runtime.get("active")
    if not active:
        print(json.dumps({"status": "no stale stage; nothing to do"}, ensure_ascii=False))
        return 0

    report = {"status": "dry-run" if not args.apply else "cleared",
              "stage_id": active.get("stage_id"),
              "team": active.get("avatar_id_list"),
              "avatar_slots": active.get("avatar_slots"),
              "begin_fingerprint": (active.get("begin_fingerprint") or "")[:16]}
    if not args.apply:
        print(json.dumps(report, ensure_ascii=False))
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.account.with_name(f"{args.account.stem}-before-unlock-{stamp}.json")
    backup.write_bytes(raw)
    runtime["active"] = None
    account["stage_runtime"] = runtime
    args.account.write_text(json.dumps(account, ensure_ascii=False, indent=2), encoding="utf-8")
    report["backup"] = str(backup)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
