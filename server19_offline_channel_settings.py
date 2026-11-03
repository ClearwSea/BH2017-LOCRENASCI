"""Prepare an auditable two-boolean offline channel-settings override.

No device access, deployment, server/game operation, SDK identity changes or
save writes. Only Default/android01 ForceRealNameVerify true -> false changes;
the original text formatting and all other bytes/JSON values are preserved.
Run: py -3.13 server19_offline_channel_settings.py
Optionally pass --device-preimage PATH for a separately captured readback.
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
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import server19_resources as resources

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / ".local-baseline/server19-dev/resource-fallback/data/channelsettings"
OUTPUT = ROOT / "server19-run/battle-batch-20261012/realname-ready"
DEVICE_PATH = "/sdcard/bh3-server19-resources/data/channelsettings"
SOURCE_SHA256 = "a9a550dcd8e69c25495271d062d5bdbd76d0e2d1994de5bc5db2e919e6d32269"
CHANNELS = ("Default", "android01")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    return json.loads(resources.strip_json_comments(raw.decode("utf-8-sig")))


def prepare(device_preimage=None, output=OUTPUT):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "server19-run/battle-batch-20261012"):
        raise ValueError("Candidate output must stay in the designated research directory")
    source = SOURCE.read_bytes()
    if sha(source) != SOURCE_SHA256:
        raise ValueError("Audited channel-settings source changed")
    before = parse(source)
    expected = deepcopy(before)
    text = source.decode("utf-8")
    edits = []
    for channel in CHANNELS:
        if before[channel]["ForceRealNameVerify"] is not True or \
                before[channel]["ForceRealNameVerifyDialogCanCancel"] is not False:
            raise ValueError("Expected explicit source channel booleans")
        expected[channel]["ForceRealNameVerify"] = False
        # The complete parsed before/after comparison below guarantees that
        # matching comments/nested fields cannot silently alter another path.
        pattern = re.compile(r'"' + re.escape(channel) + r'"\s*:\s*\{.*?'
                             r'"ForceRealNameVerify"\s*:\s*(true)', re.DOTALL)
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            raise ValueError("Ambiguous source channel selector")
        start, end = matches[0].span(1)
        edits.append({"channel": channel, "json_path": [channel, "ForceRealNameVerify"],
                      "byte_start": len(text[:start].encode("utf-8")),
                      "byte_end": len(text[:end].encode("utf-8")),
                      "before": True, "after": False})
    ordered = sorted(edits, key=lambda row: row["byte_start"])
    if ordered[0]["byte_end"] > ordered[1]["byte_start"]:
        raise ValueError("Overlapping boolean replacements")
    pieces, cursor = [], 0
    for edit in ordered:
        start, end = edit["byte_start"], edit["byte_end"]
        if source[start:end] != b"true":
            raise ValueError("Unexpected original boolean bytes")
        pieces.extend((source[cursor:start], b"false"))
        cursor = end
    pieces.append(source[cursor:])
    candidate = b"".join(pieces)
    if len(candidate) != len(source) + 2 or parse(candidate) != expected:
        raise ValueError("More than the two intended JSON values changed")
    # Reverse each replacement, accounting for the one-byte length increase,
    # to establish exact preservation of every other original byte.
    reversed_bytes = candidate
    for position in reversed(range(len(ordered))):
        edit = ordered[position]
        start = edit["byte_start"] + position
        if reversed_bytes[start:start + 5] != b"false":
            raise ValueError("Candidate replacement bytes do not match")
        reversed_bytes = reversed_bytes[:start] + b"true" + reversed_bytes[start + 5:]
    if reversed_bytes != source:
        raise ValueError("Unrelated source bytes changed")
    captured = None
    if device_preimage is not None:
        path = Path(device_preimage).resolve()
        captured = path.read_bytes()
        if captured != source:
            raise ValueError("Device readback differs from the audited source; preserve and inspect before deployment")
    source_manifest = json.loads((SOURCE.parents[1] / "manifest.json").read_text(encoding="utf-8"))
    provenance = next(row for row in source_manifest["files"] if row["path"] == "data/channelsettings")
    if provenance["output_sha256"] != sha(source) or provenance["present_in_19"] is not False:
        raise ValueError("Existing export provenance disagrees")
    if output.exists():
        raise FileExistsError("Candidate directory already exists; preserve it")
    (output / "source/data").mkdir(parents=True)
    (output / "data").mkdir()
    (output / "source/data/channelsettings").write_bytes(source)
    (output / "data/channelsettings").write_bytes(candidate)
    if captured is not None:
        (output / "device-preimage-channelsettings").write_bytes(captured)
    report = {"format": "server19-offline-channelsettings-v1", "status": "candidate_only_not_deployed",
        "source": {"path": str(SOURCE), "sha256": sha(source), "bytes": len(source),
                   "source24": source_manifest["source"], "export_record": provenance},
        "device": {"serial": "REFERENCE_DEVICE", "path": DEVICE_PATH,
                   "required_preimage_sha256": sha(source),
                   "preimage_readback_verified": captured is not None,
                   "preimage_status": "verified" if captured is not None else "root_must_capture_and_compare_before_deployment"},
        "output": {"path": str(output / "data/channelsettings"), "sha256": sha(candidate), "bytes": len(candidate)},
        "changes": edits, "all_other_json_values_preserved": True, "all_other_bytes_preserved": True,
        "dialog_can_cancel_unchanged": {channel: before[channel]["ForceRealNameVerifyDialogCanCancel"] for channel in CHANNELS},
        "native_consumer": {"method_index": 79934, "address": "0xcc456e", "settings_field_offset": "0xd",
                            "false_branch": "original return0xcc4a76; no dialog constructed",
                            "settings_type": "MoleMole.Config.ChannelSetttings"},
        "sdk_identity_age_and_authentication_changed": False, "native_library_changed": False,
        "account_or_network_isolation_changed": False, "takes_effect": "next original channel-settings load",
        "deployment_files": ["data/channelsettings"]}
    (output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "manifest": str(output / "manifest.json"),
                      "source_sha256": sha(source), "output_sha256": sha(candidate),
                      "device_preimage_readback_verified": captured is not None,
                      "changes": [{"path": "/".join(edit["json_path"]), "before": True, "after": False}
                                  for edit in edits]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-preimage", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    prepare(arguments.device_preimage, arguments.output)
