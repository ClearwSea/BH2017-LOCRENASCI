"""Overnight sweep: find the equipment set that actually boots the 1.9 client.

Method (empirical, because no static screen is reliable):
  keep a "good" account state; repeatedly try to add a batch of candidate items,
  cold-restart the game, and check that it reaches the bridge with no error
  signature. A batch that boots becomes the new good state; a batch that fails is
  bisected so only the offending items are dropped.

Writes the verified-safe item set and a running receipt. Always restores the
last good account state before each attempt, so a failed batch can never be left
installed.

Usage: py -3.13 server19_equip_sweep.py --minutes 240 --batch 20
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
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACC = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json"
EVENTS = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/server-events.jsonl"
META = ROOT / ".local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset"
ELIG = ROOT / "server19-run/equipment-eligibility-20261013/eligibility.json"
OUT = ROOT / "server19-run/equipment-sweep-20261013"
SERIAL = "REFERENCE_DEVICE"
PKG = "com.miHoYo.enterprise.NGHSoD"
ACT = PKG + "/com.miHoYo.overridenativeactivity.OverrideNativeActivity"
SIGS = ("NullReferenceException", "code is invalid", "Mismatched Enter/Exit", "LuaScriptException")
BOOT_WAIT, ENTER_WAIT = 78, 52


def adb(*a, timeout=120):
    return subprocess.run(["adb", "-s", SERIAL, *a], capture_output=True, timeout=timeout).stdout


def boot_ok():
    """Cold restart the game and report whether it reaches the bridge cleanly."""
    adb("reverse", "tcp:21018", "tcp:21028")
    adb("reverse", "tcp:21019", "tcp:21029")
    before = EVENTS.stat().st_size if EVENTS.exists() else 0
    adb("shell", "am", "force-stop", PKG)
    time.sleep(3)
    adb("shell", "am", "start", "-n", ACT)
    time.sleep(BOOT_WAIT)
    adb("shell", "input", "tap", "960", "540")
    time.sleep(ENTER_WAIT)
    events = EVENTS.read_bytes()[before:].decode("utf-8", "replace") if EVENTS.exists() else ""
    log = adb("logcat", "-d", "-t", "1200", "-v", "epoch").decode("utf-8", "replace")
    connected = "game_connected" in events
    hits = sorted({s for s in SIGS if s in log})
    return connected and not hits, {"connected": connected, "signatures": hits}


def load():
    return json.loads(ACC.read_text(encoding="utf-8"))


def save(state):
    ACC.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def grant(state, item_ids, weapons_by_id, stigmata_by_id):
    have_w = {w["id"] for w in state.get("weapon_list", [])}
    have_s = {s["id"] for s in state.get("stigmata_list", [])}
    uid = max([w["unique_id"] for w in state.get("weapon_list", [])] + [0]) + 1
    suid = max([s["unique_id"] for s in state.get("stigmata_list", [])] + [20000]) + 1
    for item in item_ids:
        if item in weapons_by_id and item not in have_w and uid < 20000:
            state.setdefault("weapon_list", []).append({"unique_id": uid, "id": item, "level": 1, "exp": 0, "is_protected": False})
            have_w.add(item)
            uid += 1
        elif item in stigmata_by_id and item not in have_s and suid < 40000:
            state.setdefault("stigmata_list", []).append({"unique_id": suid, "id": item, "level": 1, "exp": 0, "is_protected": False})
            have_s.add(item)
            suid += 1
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=240)
    parser.add_argument("--batch", type=int, default=20)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + args.minutes * 60

    eligibility = {i["item_id"]: i["class"] for i in json.loads(ELIG.read_text(encoding="utf-8"))["items"]}
    weapons = {r["ID"] for r in json.loads((META / "weapondata").read_text(encoding="utf-8"))}
    stigmata = {r["ID"] for r in json.loads((META / "stigmatadata").read_text(encoding="utf-8"))}
    good = load()
    owned = {w["id"] for w in good.get("weapon_list", [])} | {s["id"] for s in good.get("stigmata_list", [])}
    candidates = [i for i, k in sorted(eligibility.items()) if k == "safe" and i not in owned]
    log = {"started": datetime.now().isoformat(), "batch": args.batch,
           "initial_owned": sorted(owned), "candidates": len(candidates),
           "accepted": [], "rejected": [], "boots": 0, "attempts": []}
    (OUT / "sweep.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")

    good_state = good
    # bisect a failing batch down to the individual offending items
    def try_items(items, retries=2):
        if not items or time.time() > deadline:
            return []
        for attempt in range(retries + 1):
            save(grant(json.loads(json.dumps(good_state)), items, weapons, stigmata))
            ok, info = boot_ok()
            log["boots"] += 1
            log["attempts"].append({"items": items, "ok": ok, "attempt": attempt, **info})
            (OUT / "sweep.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
            if ok:
                log["accepted"].extend(items)
                return items
        # Consistent failure: bisect. A single flaky boot no longer splits a batch.
        if len(items) == 1:
            log["rejected"].append(items[0])
            return []
        mid = len(items) // 2
        return try_items(items[:mid]) + try_items(items[mid:])

    i = 0
    while i < len(candidates) and time.time() < deadline:
        batch = candidates[i:i + args.batch]
        i += args.batch
        accepted = try_items(batch)
        if accepted:
            good_state = grant(json.loads(json.dumps(good_state)), accepted, weapons, stigmata)
        save(good_state)
        log["kept_state_items"] = len(good_state.get("weapon_list", [])) + len(good_state.get("stigmata_list", []))
        (OUT / "sweep.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"progress": i, "of": len(candidates), "accepted": len(log["accepted"]),
                          "rejected": len(log["rejected"]), "boots": log["boots"]}, ensure_ascii=False), flush=True)
    save(good_state)
    log["finished"] = datetime.now().isoformat()
    (OUT / "sweep.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"done": True, "accepted": len(log["accepted"]), "rejected": log["rejected"],
                      "boots": log["boots"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
