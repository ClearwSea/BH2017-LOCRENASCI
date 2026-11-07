"""Explicit remote-emulator operations for the 1.9 server experiment.

No uninstall, account reset or general emulator firewall replacement.
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
import argparse
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "server19-run"
PKG = "com.miHoYo.enterprise.NGHSoD"
SERIAL = "TARGET_ADDRESS_REQUIRED:5555"


def adb(*args, binary=False, timeout=60):
    p = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr).decode(errors="replace"))
    return p.stdout if binary else p.stdout.decode(errors="replace")


def shell(script, root=False):
    p = subprocess.run(["adb", "-s", SERIAL, "shell", *( ["su", "-c", "sh"] if root else ["sh"])],
                       input=("set -e\n" + script + "\n").encode(), capture_output=True, timeout=60)
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr).decode(errors="replace"))
    return p.stdout.decode(errors="replace")


def identity():
    text = adb("shell", "dumpsys", "package", PKG)
    assert "versionName=1.9.0" in text and "primaryCpuAbi=x86" in text
    uid = int(re.search(r"userId=(\d+)", text).group(1))
    path = re.search(r"codePath=(\S+)", text).group(1)
    assert path.startswith("/data/app/" + PKG + "-")
    assert "uid=0(root)" in shell("id", root=True)
    return {"serial": SERIAL, "package": PKG, "uid": uid, "code_path": path,
            "library": path + "/lib/x86/libil2cpp.so"}


def isolate(host):
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host)
    info = identity()
    RUN.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (RUN / (stamp + "-iptables-before.txt")).write_text(shell("iptables-save", root=True))
    (RUN / (stamp + "-ip6tables-before.txt")).write_text(shell("ip6tables-save", root=True))
    uid = info["uid"]
    # Owned chain only; pre-existing OUTPUT rules are preserved.
    script = f"""
iptables -N BH3_SERVER19 2>/dev/null || true
iptables -F BH3_SERVER19
iptables -A BH3_SERVER19 -d 127.0.0.1/32 -p tcp --dport 21018 -j ACCEPT
iptables -A BH3_SERVER19 -d 127.0.0.1/32 -p tcp --dport 21019 -j ACCEPT
iptables -A BH3_SERVER19 -d {host}/32 -p tcp --dport 21018 -j ACCEPT
iptables -A BH3_SERVER19 -d {host}/32 -p tcp --dport 21019 -j ACCEPT
iptables -A BH3_SERVER19 -j REJECT
iptables -C OUTPUT -m owner --uid-owner {uid} -j BH3_SERVER19 2>/dev/null || iptables -I OUTPUT 1 -m owner --uid-owner {uid} -j BH3_SERVER19
ip6tables -N BH3_SERVER19 2>/dev/null || true
ip6tables -F BH3_SERVER19
ip6tables -A BH3_SERVER19 -j REJECT
ip6tables -C OUTPUT -m owner --uid-owner {uid} -j BH3_SERVER19 2>/dev/null || ip6tables -I OUTPUT 1 -m owner --uid-owner {uid} -j BH3_SERVER19
iptables -S BH3_SERVER19
ip6tables -S BH3_SERVER19
"""
    result = shell(script, root=True)
    info.update(server_host=host, ports=[21018, 21019], isolation=result)
    (RUN / "device.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))


def capture(label, pid=None):
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", label)
    RUN.mkdir(exist_ok=True)
    current_pid = shell("pidof " + PKG + " || true").strip()
    pid = current_pid if pid is None else str(pid)
    assert not pid or pid.isdigit()
    filters = ["--pid=" + pid] if pid.isdigit() else []
    log = adb("logcat", "-d", "-v", "threadtime", *filters)
    (RUN / (label + ".log")).write_text(log, encoding="utf-8")
    (RUN / (label + ".png")).write_bytes(adb("exec-out", "screencap", "-p", binary=True))
    info = {"pid": pid, "running_pid": current_pid, "label": label,
            "captured_at": int(time.time())}
    (RUN / (label + ".json")).write_text(json.dumps(info, indent=2))
    print(json.dumps(info))


def launch():
    identity()
    rules = shell("iptables -S BH3_SERVER19\nip6tables -S BH3_SERVER19", root=True)
    assert rules.count("-j REJECT") == 2
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    pid = ""
    for _ in range(20):
        pid = shell("pidof " + PKG + " || true").strip()
        if pid.isdigit():
            break
        time.sleep(.1)
    if not pid.isdigit():
        raise RuntimeError("Game process did not appear after launcher request")
    RUN.mkdir(exist_ok=True)
    (RUN / "last-launch.json").write_text(json.dumps({"pid": pid,
        "serial": SERIAL, "started_at": time.time()}), encoding="utf-8")
    print("Started original/native-server experiment on " + SERIAL + " PID " + pid)
    return pid


def deploy(library):
    library = Path(library).resolve()
    assert library.is_relative_to(ROOT)
    manifest = json.loads(library.with_suffix(library.suffix + ".json").read_text(encoding="utf-8"))
    expected = hashlib.sha256(library.read_bytes()).hexdigest()
    assert expected == manifest["output_sha256"]
    info = identity()
    target = info["library"]
    original = hashlib.sha256((ROOT / "1.9.0-official/lib__x86__libil2cpp.so").read_bytes()).hexdigest()
    backup = "/data/local/tmp/bh3-server19-original.so"
    # The initial backup was pulled and hash-verified before any patch install.
    assert shell("sha256sum " + backup, root=True).split()[0] == original
    adb("shell", "am", "force-stop", PKG)
    adb("push", str(library), "/data/local/tmp/bh3-server19-next.so")
    assert shell("sha256sum /data/local/tmp/bh3-server19-next.so", root=True).split()[0] == expected
    shell("cp /data/local/tmp/bh3-server19-next.so " + target +
          "\nchmod 755 " + target + "\nchown system:system " + target, root=True)
    assert shell("sha256sum " + target, root=True).split()[0] == expected
    print(json.dumps({"serial": SERIAL, "installed_sha256": expected, "backup_sha256": original}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["info", "isolate", "capture", "launch", "deploy"])
    p.add_argument("--host", default="TARGET_ADDRESS_REQUIRED")
    p.add_argument("--serial", default=SERIAL,
                   help="explicit ADB target; defaults to the existing remote instance")
    p.add_argument("--label", default="startup")
    p.add_argument("--library", type=Path)
    a = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", a.serial):
        p.error("Invalid ADB device serial")
    SERIAL = a.serial
    if a.command == "info": print(json.dumps(identity(), indent=2))
    elif a.command == "isolate": isolate(a.host)
    elif a.command == "capture": capture(a.label)
    elif a.command == "deploy": deploy(a.library)
    else: launch()
