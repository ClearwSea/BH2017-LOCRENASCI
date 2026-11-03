"""Owned chapter1 acceptance capture for REFERENCE_DEVICE; no game/UI mutations.

prepare creates a fresh directory beneath server19-run/story-chain-batch/
acceptance, backs up the local save and records server/old-log byte offsets.
Use the returned --out path for collect/status/snapshot --label/stop.
collect streams all logcat buffers without clearing them. stop requests only
this directory's collector to stop; never kill the shared ADB daemon or game.
On Windows an owned kill-on-close Job also closes the child on parent exit.
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
from datetime import datetime
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import time

import server19_device as device

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "server19-run/story-chain-batch/acceptance"
RUN = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server"
OLD_LOG = ROOT / "server19-run/battle-batch-20261012/live-all-buffers.log"
SERIAL = "REFERENCE_DEVICE"


def save_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def write_bytes(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def summary(account):
    saved = {row["id"]: row for row in account.get("stage_list", [])}
    main = account["main"]
    active = account.get("stage_runtime", {}).get("active")
    return {"captain": {key: main.get(key) for key in
                ("level", "exp", "scoin", "hcoin", "stamina", "skill_point")},
            "stages": [{"id": identity, "saved": identity in saved,
                **{key: saved.get(identity, {}).get(key) for key in
                   ("progress", "is_done", "enter_times", "challenge_index_list")}}
                       for identity in range(10101, 10137)],
            "claimed_mission_ids": account.get("mission_runtime", {}).get("claimed_ids", []),
            "act_rewards": account.get("stage_act_difficulty_list", []),
            "active": {key: active.get(key) for key in
                ("stage_id", "avatar_id_list", "started_at")} if active else None,
            "settlement_count": len(account.get("stage_runtime", {}).get("settlements", []))}


def output_directory(args):
    if args.out:
        result = Path(args.out).resolve()
    elif args.action == "prepare":
        result = BASE / (datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4))
    else:
        raise ValueError("Pass the exact --out directory returned by prepare")
    if result == BASE.resolve() or not result.is_relative_to(BASE.resolve()):
        raise ValueError("Evidence directory must be a child of the acceptance directory")
    return result


def read_preparation(out):
    before = json.loads((out / "before.json").read_text(encoding="utf-8"))
    if before.get("schema") != 1 or before.get("serial") != SERIAL or not before.get("owner_token"):
        raise ValueError("Wrong or incomplete capture preparation")
    # Stored paths are evidence, not instructions to access another account.
    if before.get("account_source") != str(RUN / "account.json") or before.get("events_path") != str(RUN / "server-events.jsonl"):
        raise ValueError("Capture preparation does not identify this local server")
    return before


def prepare(out):
    device.SERIAL = SERIAL
    identity = device.identity()
    library_sha = device.shell("sha256sum " + shlex.quote(identity["library"]), root=True).split()[0]
    pid = device.shell("pidof " + device.PKG + " || true").strip()
    raw = (RUN / "account.json").read_bytes()
    events = RUN / "server-events.jsonl"
    record = {"schema": 1, "owner_token": secrets.token_hex(16), "time": time.time(),
        "serial": SERIAL, "device": identity, "library_sha256": library_sha, "pid": pid,
        "account_source": str(RUN / "account.json"), "account_sha256": digest(raw),
        "events_path": str(events), "events_start_bytes": events.stat().st_size if events.exists() else 0,
        "old_live_log_path": str(OLD_LOG), "old_live_log_start_bytes": OLD_LOG.stat().st_size if OLD_LOG.exists() else 0,
        "device_actions": "read-only identity, root identity and current PID; no screenshot or game operation"}
    out.mkdir(parents=True, exist_ok=False)
    write_bytes(out / "before-local-account.json", raw)
    save_json(out / "before.json", record)
    print(json.dumps({"prepared": str(out), "serial": SERIAL, "pid": pid,
                      "account_sha256": digest(raw)}, ensure_ascii=False), flush=True)


def owned_job(child):
    """Assign just our ADB child to a noninherited Windows kill-on-close Job."""
    if os.name != "nt":
        return None
    class BasicLimits(ctypes.Structure):
        _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSet", ctypes.c_size_t),
            ("MaximumWorkingSet", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD)]
    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperations", "WriteOperations",
            "OtherOperations", "ReadBytes", "WriteBytes", "OtherBytes")]
    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("Basic", BasicLimits), ("IO", Counters),
            ("ProcessMemory", ctypes.c_size_t), ("JobMemory", ctypes.c_size_t),
            ("PeakProcessMemory", ctypes.c_size_t), ("PeakJobMemory", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    try:
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or \
                not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(child._handle))):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    return kernel, handle


def collect(out, before):
    if (out / "STOP").exists() or (out / "collector.json").exists():
        raise ValueError("Capture already started or stopped; prepare a fresh directory")
    command = ["adb", "-s", SERIAL, "logcat", "-b", "all", "-v", "epoch", "-T", "1", "*:V"]
    child = None
    job = None
    with (out / "live-all-buffers.log").open("xb") as stream:
        try:
            child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            job = owned_job(child)
            save_json(out / "collector.json", {"time": time.time(), "parent_pid": os.getpid(),
                "child_pid": child.pid, "command": command, "owner_token": before["owner_token"],
                "windows_kill_on_parent_exit": bool(job)})
            print(json.dumps({"listening": SERIAL, "out": str(out), "child_pid": child.pid}), flush=True)
            while child.poll() is None:
                stop = out / "STOP"
                if stop.exists() and stop.read_text(encoding="utf-8").strip() == before["owner_token"]:
                    break
                time.sleep(1)
        finally:
            if child is not None:
                if child.poll() is None:
                    child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()  # Exact owned Popen instance only.
                    child.wait(timeout=5)
                save_json(out / "collector-completed.json", {"time": time.time(),
                    "child_pid": child.pid, "returncode": child.returncode,
                    "bytes": (out / "live-all-buffers.log").stat().st_size})
            if job:
                job[0].CloseHandle(job[1])


def snapshot(out, before, label):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", label):
        raise ValueError("Use a fresh label of ASCII letters, numbers, underscores or hyphens")
    target = out / "snapshots" / label
    target.mkdir(parents=True, exist_ok=False)
    device.SERIAL = SERIAL
    pid = device.shell("pidof " + device.PKG + " || true").strip()
    write_bytes(target / "screen.png", device.adb("exec-out", "screencap", "-p", binary=True))
    filters = ["--pid=" + pid] if pid.isdigit() else []
    write_bytes(target / "client.log", device.adb("logcat", "-d", "-b", "all", "-v", "epoch", *filters, binary=True))
    account = (RUN / "account.json").read_bytes()
    write_bytes(target / "account.json", account)
    events = RUN / "server-events.jsonl"
    start = before["events_start_bytes"]
    end = events.stat().st_size if events.exists() else 0
    truncated = end < start
    with (target / "server-events-from-start.jsonl").open("xb") as capture:
        if events.exists():
            with events.open("rb") as source:
                source.seek(0 if truncated else start)
                while chunk := source.read(1024 * 1024):
                    capture.write(chunk)
    save_json(target / "capture.json", {"time": time.time(), "serial": SERIAL,
        "pid": pid, "account_sha256": digest(account), "events_start_bytes": start,
        "events_observed_end_bytes": end, "events_truncated_since_prepare": truncated,
        "client_log_pid_filter": pid if pid.isdigit() else None,
        "summary": summary(json.loads(account))})
    print(json.dumps({"capture": str(target), "pid": pid, "account_sha256": digest(account)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect", "status", "snapshot", "stop"))
    parser.add_argument("--out", help="Exact directory returned by prepare")
    parser.add_argument("--label", default="human-observation")
    args = parser.parse_args()
    out = output_directory(args)
    if args.action == "prepare":
        prepare(out)
        return
    before = read_preparation(out)
    if args.action == "collect":
        collect(out, before)
    elif args.action == "snapshot":
        snapshot(out, before, args.label)
    elif args.action == "stop":
        stop = out / "STOP"
        if not stop.exists():
            write_bytes(stop, (before["owner_token"] + "\n").encode())
        elif stop.read_text(encoding="utf-8").strip() != before["owner_token"]:
            raise ValueError("Stop token belongs to another capture")
        print(json.dumps({"requested_owned_collector_stop": str(out)}))
    else:
        account = json.loads((RUN / "account.json").read_bytes())
        log = out / "live-all-buffers.log"
        print(json.dumps({"out": str(out), "serial": SERIAL, "time": time.time(),
            "collector_completed": (out / "collector-completed.json").exists(),
            "stop_requested": (out / "STOP").exists(), "log_bytes": log.stat().st_size if log.exists() else 0,
            **summary(account)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
