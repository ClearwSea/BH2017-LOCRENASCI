"""Prepare and explicitly deploy original-player CG resources.

准备与部署分开；资源存在不代表剧情解锁或游戏内播放已验收。
Preparation does not unlock story state or claim in-game playback acceptance.
All local inputs/outputs stay inside this project; original sources are read-only.
"""
from __future__ import annotations

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
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import zipfile

ROOT = Path(__file__).resolve().parent
PKG = "com.miHoYo.enterprise.NGHSoD"
BUILTIN = {"start.mp4", "Story_01.mp4"}
DEFAULT_APK = ".local-baseline/releases/baseline-20261007-audio-idle/20171123-android_versions_v1_9_resurrection_of_the_sacramental_guofu.apk"
DEFAULT_TABLE = ".local-baseline/server19-dev/metadata-fallback/_exceloutputasset/cgdata"
DEFAULT_OFFICIAL = "server19-run/cg-research-official/official-media-manifest.json"
DEFAULT_DECODER = "server19-run/cg-research-official/decoder-validation.json"
DEFAULT_PREPARED = ".local-baseline/server19-dev/cg-media/prepared"
DEFAULT_MANIFEST = DEFAULT_PREPARED + "/manifest.json"
SHA_RE = re.compile(r"[0-9a-f]{64}")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.mp4")
CG_ICON_PREFIX = "SpriteOutput/CGReplay/"


def timestamps():
    instant = datetime.now(timezone.utc)
    return {"utc": instant.isoformat(), "local": instant.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
            "timezone": "Asia/Shanghai"}


def local_path(value, *, exists=False):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("A nonempty project-local path is required")
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if path == ROOT or not path.is_relative_to(ROOT):
        raise ValueError(f"Path escapes project: {value}")
    if exists and not path.is_file():
        raise ValueError(f"Input file unavailable: {path}")
    return path


def relative(path):
    return local_path(path).relative_to(ROOT).as_posix()


def filename(value):
    if not isinstance(value, str) or not NAME_RE.fullmatch(value) or ".." in value:
        raise ValueError(f"Unsafe video filename: {value!r}")
    return value


def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(local_path(path, exists=True).read_text(encoding="utf-8-sig"))


def write_json(path, values):
    path = local_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial-" + str(os.getpid()))
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(8):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as error:
            # Windows readers/scanners can briefly deny replacement. Retrying
            # this already-closed, same-directory file keeps the update atomic.
            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 7:
                raise
            time.sleep(min(.05 * (attempt + 1), .2))


def validated_decode(decoder, source_path, expected_sha, expected_size):
    """Match evidence to exact bytes and path, including full EOF decode."""
    matches = [r for r in decoder.get("files", [])
               if r.get("local_path") and local_path(r["local_path"]) == source_path
               and r.get("sha256_before") == expected_sha]
    if len(matches) != 1:
        raise ValueError(f"Missing or ambiguous full decode receipt: {source_path}")
    row = matches[0]
    decode = row.get("ffmpeg_decode", {})
    probe = row.get("ffprobe", {})
    if not (row.get("result") == "full_decode_passed" and row.get("size") == expected_size
            and row.get("expected_sha256") == expected_sha and row.get("sha256_after") == expected_sha
            and row.get("source_unchanged") is True and probe.get("exit_code") == 0
            and not probe.get("timed_out") and decode.get("exit_code") == 0
            and not decode.get("timed_out") and decode.get("decoded_full_input") is True
            and decode.get("final_progress", {}).get("progress") == "end"
            and any(s.get("codec_type") == "video" for s in row.get("streams", []))):
        raise ValueError(f"Incomplete probe/decode evidence: {source_path}")
    return {"duration_seconds": row.get("duration_seconds"), "streams": row["streams"],
            "full_decode_exit_code": 0, "full_decode_through_eof": True}


def copy_verified(source, destination, expected_sha, expected_size):
    destination = local_path(destination)
    if destination == source or destination.is_relative_to(source.parent):
        raise ValueError("Prepared output must be separate from source directory")
    if destination.exists():
        if destination.stat().st_size != expected_size or hash_file(destination) != expected_sha:
            raise ValueError(f"Existing prepared file differs; preserved: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        raise ValueError(f"Existing partial output preserved: {temporary}")
    shutil.copyfile(source, temporary)
    if temporary.stat().st_size != expected_size or hash_file(temporary) != expected_sha:
        raise ValueError(f"Prepared copy failed byte verification: {temporary}")
    # Windows rename refuses an existing destination; never replace prior media.
    os.rename(temporary, destination)


def accepted_references(path, targets):
    """Explicit optional later-client references; default path is never consulted.

    JSON contract: {"entries": [{"source": project_path, "target": "name.mp4",
      "sha256": "...", "compatibility_note": "...",
      "historical_identity": "reference_only_not_original19",
      "probe_evidence": project_json_path, "decoder_evidence": project_json_path}]}.
    Probe evidence contains files[{local_path,sha256,size,ffprobe_exit_code,ffprobe}].
    Decoder evidence uses the same exact-file full-EOF schema as the official audit.
    """
    if not path:
        return {}
    data = read_json(path)
    accepted = {}
    for entry in data.get("entries", []):
        name = filename(entry.get("target"))
        if name not in targets or name in BUILTIN or name in accepted:
            raise ValueError(f"Unexpected/duplicate reference target: {name}")
        if (entry.get("historical_identity") != "reference_only_not_original19"
                or not isinstance(entry.get("compatibility_note"), str)
                or not entry["compatibility_note"].strip()):
            raise ValueError("Reference must state compatibility limits and nonhistorical identity")
        source = local_path(entry.get("source"), exists=True)
        filename(source.name)
        expected = entry.get("sha256", "")
        if not SHA_RE.fullmatch(expected) or hash_file(source) != expected or source.stat().st_size <= 0:
            raise ValueError(f"Reference SHA/length verification failed: {name}")
        size = source.stat().st_size
        probes = read_json(entry.get("probe_evidence"))
        rows = probes.get("files", [])
        matching = [r for r in rows if r.get("local_path") and local_path(r["local_path"]) == source
                    and r.get("sha256") == expected and r.get("size") == size
                    and r.get("ffprobe_exit_code") == 0
                    and any(s.get("codec_type") == "video" for s in r.get("ffprobe", {}).get("streams", []))]
        if len(matching) != 1:
            raise ValueError(f"Missing exact-file reference probe: {name}")
        decode = validated_decode(read_json(entry.get("decoder_evidence")), source, expected, size)
        accepted[name] = {"source_path": relative(source), "sha256": expected, "size": size,
                          "origin": "explicitly_accepted_later_reference", "compatibility_note": entry["compatibility_note"],
                          "historical_identity": entry["historical_identity"], "decode": decode,
                          "probe_evidence": relative(local_path(entry["probe_evidence"])),
                          "probe_evidence_sha256": hash_file(local_path(entry["probe_evidence"])),
                          "decoder_evidence": relative(local_path(entry["decoder_evidence"])),
                          "decoder_evidence_sha256": hash_file(local_path(entry["decoder_evidence"]))}
    return accepted


def download_table_provenance(current_path, official, explicit_download_table=None):
    """Only an explicit, exact icon-field correction can bridge table hashes.

    Native MonoCgIconButton.InitData (84177) adds CG_ICON_PREFIX itself. The
    original download receipt remains bound to its unmodified source table;
    this narrow adaptation does not change video identity or story semantics.
    """
    current_path = local_path(current_path, exists=True)
    current_sha = hash_file(current_path)
    expected_sha = official.get("source_table_sha256", "")
    if not isinstance(expected_sha, str) or not SHA_RE.fullmatch(expected_sha):
        raise ValueError("Official receipt lacks a valid source table SHA")
    if current_sha != expected_sha and not explicit_download_table:
        raise ValueError("Different CgData SHA requires explicit --download-table; no automatic hash relaxation")
    download_path = local_path(explicit_download_table, exists=True) if explicit_download_table else current_path
    if hash_file(download_path) != expected_sha:
        raise ValueError("Explicit download table does not match official receipt source SHA")
    if current_sha == expected_sha:
        return {"download_source_table": relative(download_path), "download_source_table_sha256": expected_sha,
                "download_table_adaptation": None}
    original, current = read_json(download_path), read_json(current_path)
    if not isinstance(original, list) or not isinstance(current, list) or len(original) != 76 or len(current) != 76:
        raise ValueError("Icon-only table adaptation requires exactly 76 source and target records")
    ids, changes = set(), []
    for before, after in zip(original, current):
        if not isinstance(before, dict) or not isinstance(after, dict) or set(before) != set(after):
            raise ValueError("Icon adaptation cannot add/remove row fields")
        cg_id = before.get("CgID")
        if type(cg_id) is not int or cg_id in ids:
            raise ValueError("Icon adaptation source has invalid/duplicate CG IDs")
        ids.add(cg_id)
        source_icon, target_icon = before.get("CgIconSpritePath"), after.get("CgIconSpritePath")
        if not isinstance(source_icon, str) or not source_icon.startswith(CG_ICON_PREFIX):
            raise ValueError("Only the confirmed CGReplay prefix may be removed")
        basename = source_icon[len(CG_ICON_PREFIX):]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", basename) or ".." in basename or target_icon != basename:
            raise ValueError("Icon adaptation is not an exact prefix-to-basename correction")
        old_fields = {k: v for k, v in before.items() if k != "CgIconSpritePath"}
        new_fields = {k: v for k, v in after.items() if k != "CgIconSpritePath"}
        # JSON comparison keeps booleans/numeric types distinct, unlike Python
        # equality (True == 1). All IDs, paths, modes, levels and order stay exact.
        canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical(old_fields) != canonical(new_fields):
            raise ValueError(f"Icon adaptation changes non-icon fields/order/types at CG {cg_id}")
        changes.append({"cg_id": cg_id, "from": source_icon, "to": basename})
    return {"download_source_table": relative(download_path), "download_source_table_sha256": expected_sha,
            "download_table_adaptation": {
                "kind": "original19_cg_icon_prefix_to_basename_only", "field": "CgIconSpritePath",
                "removed_prefix": CG_ICON_PREFIX, "native_consumer_method": 84177,
                "record_count": 76, "changed_records": changes,
                "description_zh": "原1.9消费端自行拼接CGReplay前缀；仅将76条图标字段的该前缀移除，其余字段、类型和记录顺序完全一致。",
                "description_en": "Native 1.9 prepends the CGReplay prefix. Only the 76 icon fields remove that exact prefix; all other fields, JSON types and row order remain identical."}}


def official_media_by_name(official):
    indexed = {}
    for row in official.get("media", []):
        if row.get("kind") != "mp4":
            continue
        name = filename(row.get("filename"))
        if name in indexed:
            raise ValueError("Duplicate official media receipt")
        indexed[name] = row
    return indexed


def prepare(args):
    table_path = local_path(args.cg_table, exists=True)
    apk_path = local_path(args.apk, exists=True)
    output = local_path(args.output)
    # Only this resource workspace is an eligible staging destination.
    media_root = local_path(".local-baseline/server19-dev/cg-media")
    if not output.is_relative_to(media_root) or output == media_root:
        raise ValueError("Prepared output must be a dedicated directory below cg-media")
    table = read_json(table_path)
    if not isinstance(table, list) or not table:
        raise ValueError("CgData must be a nonempty row list")
    groups = {}
    ids = set()
    for row in table:
        if not isinstance(row, dict) or not isinstance(row.get("CgID"), int) or row["CgID"] in ids:
            raise ValueError("CgData contains invalid or duplicate IDs")
        ids.add(row["CgID"])
        name = filename(str(row.get("CgPath", "")) + ".mp4")
        groups.setdefault(name, []).append(row)
    official_path = local_path(args.official_manifest, exists=True)
    decoder_path = local_path(args.decoder_manifest, exists=True)
    official, decoder = read_json(official_path), read_json(decoder_path)
    table_provenance = download_table_provenance(table_path, official, getattr(args, "download_table", None))
    official_by_name = official_media_by_name(official)
    references = accepted_references(args.accepted_reference_manifest, groups)
    resources = []
    with zipfile.ZipFile(apk_path) as apk:
        for name, rows in sorted(groups.items()):
            base = {"filename": name, "native_key": "Video/" + name,
                    "cg_ids": [r["CgID"] for r in rows],
                    "play_modes": sorted({r.get("CgPlayMode") for r in rows}),
                    "deploy_external": name not in BUILTIN}
            if name in BUILTIN:
                entry = "assets/Video/" + name
                info = apk.getinfo(entry)
                if info.file_size <= 0:
                    raise ValueError(f"Zero-sized original APK video: {name}")
                h = hashlib.sha256()
                with apk.open(entry) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                expected = h.hexdigest()
                matching = [r for r in decoder.get("files", []) if r.get("source") == "original19_apk"
                            and r.get("apk_entry") == entry and r.get("sha256_before") == expected]
                if len(matching) != 1:
                    raise ValueError(f"No decoded extraction for original APK video: {name}")
                source = local_path(matching[0]["local_path"], exists=True)
                if hash_file(source) != expected or source.stat().st_size != info.file_size:
                    raise ValueError("Original APK extraction no longer matches")
                decode = validated_decode(decoder, source, expected, info.file_size)
                destination = output / "builtin-reference" / "Video" / name
                copy_verified(source, destination, expected, info.file_size)
                resources.append({**base, "status": "available_builtin", "origin": "original19_apk",
                                  "apk_path": relative(apk_path), "apk_entry": entry,
                                  "source_path": relative(source), "prepared_path": relative(destination),
                                  "size": info.file_size, "sha256": expected, "decode": decode,
                                  "historical_identity": "original19_apk_bytes", "deploy_external": False})
                continue
            row = official_by_name.get(name, {})
            if row.get("result") in {"downloaded_verified", "existing_validated_preserved"}:
                source = local_path(row.get("local_path"), exists=True)
                if source.name != name:
                    raise ValueError(f"Official filename differs: {name}")
                size, expected = row.get("size"), row.get("sha256", "")
                if not (isinstance(size, int) and size > 0 and row.get("total_length") == size
                        and SHA_RE.fullmatch(expected) and source.stat().st_size == size
                        and hash_file(source) == expected):
                    raise ValueError(f"Official byte/length verification failed: {name}")
                decode = validated_decode(decoder, source, expected, size)
                selected = {"source_path": relative(source), "size": size, "sha256": expected,
                            "origin": "official_current_url", "url": row.get("final_url"),
                            "last_modified": row.get("last_modified"), "decode": decode,
                            "historical_identity": "official_current_bytes_not_proven_original19",
                            "compatibility_note": "Current original-format CDN content; Windows full decode passed, Android game playback remains unaccepted."}
            elif name in references:
                selected = references[name]
                source = local_path(selected["source_path"], exists=True)
                size, expected = selected["size"], selected["sha256"]
            else:
                resources.append({**base, "status": "missing", "deploy_external": False,
                                  "reason": row.get("result", "no_official_receipt"),
                                  "http_status": row.get("http_status"), "url": row.get("final_url", row.get("url")),
                                  "historical_identity": "unresolved; no automatic later-client substitution"})
                continue
            destination = output / "Video" / name
            copy_verified(source, destination, expected, size)
            resources.append({**base, **selected, "status": "available_external", "prepared_path": relative(destination)})
    manifest = {"schema_version": 1, "prepared_at": timestamps(),
                "source_table": relative(table_path), "source_table_sha256": hash_file(table_path),
                **table_provenance,
                "table_provenance_limit": official.get("table_provenance_limit", "not proven original19 table"),
                "original_apk": relative(apk_path), "original_apk_sha256": hash_file(apk_path),
                "official_manifest": relative(official_path), "official_manifest_sha256": hash_file(official_path),
                "decoder_manifest": relative(decoder_path), "decoder_manifest_sha256": hash_file(decoder_path),
                "accepted_reference_manifest": relative(local_path(args.accepted_reference_manifest)) if args.accepted_reference_manifest else None,
                "accepted_reference_manifest_sha256": hash_file(local_path(args.accepted_reference_manifest)) if args.accepted_reference_manifest else None,
                "cg_record_count": len(table), "unique_path_count": len(groups), "cg_records": table,
                "resources": resources, "summary": {"builtin": sum(r["status"] == "available_builtin" for r in resources),
                    "external": sum(r["status"] == "available_external" for r in resources),
                    "missing": sum(r["status"] == "missing" for r in resources)},
                "boundaries": ["No story/guide/CG completion state is altered.",
                               "Built-in start and Story_01 never overwrite external files.",
                               "Full Windows decode does not prove in-game Android playback.",
                               "Later-client references require an explicitly supplied acceptance manifest."]}
    write_json(output / "manifest.json", manifest)
    (output / "README.txt").write_text(
        "CG资源准备 / CG resource preparation\n"
        f"记录 {len(table)} / 唯一路径 {len(groups)} / 外部 {manifest['summary']['external']} / 缺失 {manifest['summary']['missing']}\n"
        "Video/仅包含可部署外部文件；builtin-reference/Video保留APK原文件供比对，不部署。\n"
        "Video/ contains deployable external bytes only. Builtin-reference stays local.\n"
        "manifest.json记录来源、原生key、完整性与解码证据。未声称剧情解锁或游戏内验收。\n"
        "Use explicit deploy after reviewing the manifest. No story state or player library is changed.\n",
        encoding="utf-8")
    return {"manifest": relative(output / "manifest.json"), "summary": manifest["summary"],
            "cg_record_count": len(table), "unique_path_count": len(groups)}


def validate_prepared(path):
    manifest_path = local_path(path, exists=True)
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported prepared manifest schema")
    # A staged manifest cannot manufacture a passing decoder flag. Re-open
    # immutable evidence and original source bytes on every deploy/audit.
    for path_key, sha_key in [("source_table", "source_table_sha256"),
                              ("original_apk", "original_apk_sha256"),
                              ("official_manifest", "official_manifest_sha256"),
                              ("decoder_manifest", "decoder_manifest_sha256")]:
        evidence_path = local_path(manifest.get(path_key), exists=True)
        if hash_file(evidence_path) != manifest.get(sha_key):
            raise ValueError(f"Prepared evidence changed: {path_key}")
    decoder = read_json(manifest["decoder_manifest"])
    official = read_json(manifest["official_manifest"])
    official_by_name = official_media_by_name(official)
    table_provenance = download_table_provenance(manifest["source_table"], official,
                                                manifest.get("download_source_table"))
    # Older same-SHA manifests remain valid without these additive fields.
    if "download_source_table" in manifest:
        for key, actual in table_provenance.items():
            if manifest.get(key) != actual:
                raise ValueError(f"Prepared download-table provenance mismatch: {key}")
    records = manifest.get("cg_records", [])
    if records != read_json(manifest["source_table"]):
        raise ValueError("Prepared CG records differ from their source table")
    references = accepted_references(manifest.get("accepted_reference_manifest"),
                                     {filename(str(r.get("CgPath", "")) + ".mp4") for r in records})
    if manifest.get("accepted_reference_manifest") and hash_file(local_path(manifest["accepted_reference_manifest"])) != manifest.get("accepted_reference_manifest_sha256"):
        raise ValueError("Reference acceptance manifest changed")
    resources = manifest.get("resources", [])
    if manifest.get("cg_record_count") != len(records) or manifest.get("unique_path_count") != len(resources):
        raise ValueError("Prepared manifest coverage mismatch")
    wanted = {filename(str(row.get("CgPath", "")) + ".mp4") for row in records}
    names = [filename(row.get("filename")) for row in resources]
    if len(set(names)) != len(names) or set(names) != wanted:
        raise ValueError("Prepared resources do not cover exactly the CgData paths")
    eligible = []
    for row in resources:
        name = row["filename"]
        if row.get("native_key") != "Video/" + name:
            raise ValueError("Prepared native key mismatch")
        if row.get("status") == "missing":
            if row.get("deploy_external"):
                raise ValueError("Missing resource cannot be deployed")
            continue
        source = local_path(row.get("prepared_path"), exists=True)
        if not source.is_relative_to(manifest_path.parent) or source.name != name:
            raise ValueError("Prepared media escapes its manifest directory")
        expected = row.get("sha256", "")
        if not (SHA_RE.fullmatch(expected) and isinstance(row.get("size"), int) and row["size"] > 0
                and source.stat().st_size == row["size"] and hash_file(source) == expected
                and row.get("decode", {}).get("full_decode_through_eof") is True
                and row["decode"].get("full_decode_exit_code") == 0):
            raise ValueError(f"Prepared verification failed: {name}")
        original_source = local_path(row.get("source_path"), exists=True)
        if original_source.stat().st_size != row["size"] or hash_file(original_source) != expected:
            raise ValueError(f"Original source changed: {name}")
        origin = row.get("origin")
        decode_receipt = decoder
        if name in BUILTIN:
            if row.get("deploy_external") or row.get("status") != "available_builtin" or origin != "original19_apk":
                raise ValueError("Built-in files must not be deployed externally")
            entry = "assets/Video/" + name
            if (row.get("apk_path") != manifest["original_apk"] or row.get("apk_entry") != entry
                    or row.get("historical_identity") != "original19_apk_bytes"):
                raise ValueError("Built-in provenance differs from the original APK")
            with zipfile.ZipFile(local_path(manifest["original_apk"], exists=True)) as apk:
                if hashlib.sha256(apk.read(entry)).hexdigest() != expected:
                    raise ValueError("Built-in preference no longer matches original APK bytes")
        else:
            if row.get("status") != "available_external" or row.get("deploy_external") is not True:
                raise ValueError(f"Invalid resource status: {name}")
            receipt = official_by_name.get(name, {})
            official_available = receipt.get("result") in {"downloaded_verified", "existing_validated_preserved"}
            if origin == "official_current_url":
                # Passing decode evidence proves the bytes are a valid video,
                # not that they are the CG named by this prepared resource.
                # Bind this name to its exact immutable download receipt row.
                if not official_available:
                    raise ValueError(f"Official provenance has no verified receipt for {name}")
                receipt_source = local_path(receipt.get("local_path"), exists=True)
                if (receipt_source.name != name or receipt_source != original_source
                        or type(receipt.get("size")) is not int or receipt["size"] <= 0
                        or receipt.get("total_length") != receipt["size"]
                        or receipt["size"] != row["size"] or receipt.get("sha256") != expected
                        or row.get("url") != receipt.get("final_url")
                        or row.get("last_modified") != receipt.get("last_modified")
                        or row.get("historical_identity") != "official_current_bytes_not_proven_original19"):
                    raise ValueError(f"Official provenance does not match the exact receipt for {name}")
            elif origin == "explicitly_accepted_later_reference":
                accepted = references.get(name)
                if official_available:
                    raise ValueError(f"Reference cannot replace verified official bytes for {name}")
                if not accepted or any(row.get(key) != value for key, value in accepted.items()):
                    raise ValueError("Reference not covered by the exact explicit acceptance manifest row")
                decode_receipt = read_json(accepted["decoder_evidence"])
            else:
                raise ValueError(f"Invalid external resource origin: {name}: {origin}")
            eligible.append(row)
        if row["decode"] != validated_decode(decode_receipt, original_source, expected, row["size"]):
            raise ValueError(f"Prepared decode summary differs from exact-file evidence: {name}")
    return manifest, eligible


def merge_version(original, names):
    """Keep original BOM, newline style, unknown lines and keys; only merge actual CGs."""
    if original.startswith(b"\xef\xbb\xbf"):
        bom, codec = b"\xef\xbb\xbf", "utf-8"
    elif original.startswith(b"\xff\xfe"):
        bom, codec = b"\xff\xfe", "utf-16-le"
    elif original.startswith(b"\xfe\xff"):
        bom, codec = b"\xfe\xff", "utf-16-be"
    else:
        bom, codec = b"", "utf-8"
    text = original[len(bom):].decode(codec, errors="strict")
    if "\x00" in text:
        raise ValueError("Unsupported Version.txt encoding")
    newline = "\r\n" if "\r\n" in text else "\n"
    targets = {"Video/" + filename(n) for n in names}
    seen, output = set(), []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        columns = body.split("\t")
        if len(columns) == 2:
            key = columns[0]
            if key in seen:
                raise ValueError(f"Duplicate native version key: {key}")
            seen.add(key)
            if key in targets:
                body = key + "\t1"
        output.append(body + ending)
    result = "".join(output)
    missing = sorted(targets - seen)
    if missing and result and not result.endswith(("\r", "\n")):
        result += newline
    result += "".join(key + "\t1" + newline for key in missing)
    return bom + result.encode(codec)


def version_keys(raw):
    # Parsing preserves File.ReadAllLines / exactly-two-tab-columns semantics.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    found = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            if parts[0] in found:
                raise ValueError(f"Duplicate native Version.txt key: {parts[0]}")
            found[parts[0]] = parts[1]
    return found


class Device:
    """Only named-package file operations; no firewall, account or library mutation."""
    def __init__(self, serial):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", serial):
            raise ValueError("Invalid ADB serial")
        self.serial = serial

    def adb(self, *args, timeout=180):
        # An interrupted host-daemon connection can occur between file pushes.
        # Retry only the byte-verified, tool-owned staging upload; do not retry
        # arbitrary shell mutations or restart the shared ADB daemon.
        for attempt in range(3):
            proc = subprocess.run(["adb", "-s", self.serial, *map(str, args)], capture_output=True, timeout=timeout)
            if not proc.returncode:
                return proc.stdout
            message = (proc.stdout + proc.stderr).decode(errors="replace")[:4000]
            transient = any(value in message for value in
                            ("daemon still not running", "cannot connect to daemon", "(10060)"))
            if not args or args[0] != "push" or not transient or attempt == 2:
                raise RuntimeError(message)
            time.sleep(1 + attempt)

    def shell(self, script, root=False):
        for attempt in range(3):
            proc = subprocess.run(["adb", "-s", self.serial, "shell", *(["su", "-c", "sh"] if root else ["sh"])],
                                  input=("set -e\n" + script + "\n").encode(), capture_output=True, timeout=180)
            if not proc.returncode:
                return proc.stdout.decode(errors="replace").replace("\r", "")
            message = (proc.stdout + proc.stderr).decode(errors="replace")[:4000]
            # This exact host-daemon connection failure precedes dispatch of
            # the remote shell. Never retry a remote error or lost reply.
            undispatched = "daemon still not running" in message and "cannot connect to daemon" in message
            if not undispatched or attempt == 2:
                raise RuntimeError(message)
            time.sleep(1 + attempt)

    def identity(self):
        package = self.adb("shell", "dumpsys", "package", PKG).decode(errors="replace")
        abi_match = re.search(r"primaryCpuAbi=(\S+)", package)
        library_dirs = {"x86": "x86", "armeabi-v7a": "arm"}
        if not re.search(r"versionName=1\.9\.0(?:\s|$)", package) or not abi_match or abi_match.group(1) not in library_dirs:
            raise ValueError("Expected original 1.9.0 x86 or ARMv7 package")
        uid_match, code_match = re.search(r"userId=(\d+)", package), re.search(r"codePath=(\S+)", package)
        if not uid_match or not code_match or "uid=0(root)" not in self.shell("id", root=True):
            raise ValueError("Expected package identity and root access")
        code = code_match.group(1)
        if not code.startswith("/data/app/" + PKG + "-") or not re.fullmatch(r"/[A-Za-z0-9_./+=-]+", code):
            raise ValueError("Unexpected installed package path")
        return {"serial": self.serial, "package": PKG, "uid": int(uid_match.group(1)),
                "code_path": code, "abi": abi_match.group(1),
                "library": code + "/lib/" + library_dirs[abi_match.group(1)] + "/libil2cpp.so"}

    def persistent_directory(self, explicit_files_path):
        if not isinstance(explicit_files_path, str) or not explicit_files_path.startswith("/"):
            raise ValueError("Supply observed absolute Android persistent files path")
        if PurePosixPath(explicit_files_path).name != "files" or ".." in PurePosixPath(explicit_files_path).parts:
            raise ValueError("Expected the named package's files directory")
        resolved = self.shell("test -d " + shlex.quote(explicit_files_path) + "\nreadlink -f " + shlex.quote(explicit_files_path), root=True).strip()
        suffix = "/Android/data/" + PKG + "/files"
        if not resolved.endswith(suffix) or not re.fullmatch(r"/storage/emulated/\d+" + re.escape(suffix), resolved):
            raise ValueError(f"Persistent path outside named package: {resolved}")
        # Existing child directories may not redirect app-owned writes elsewhere.
        for child in [resolved + "/assets", resolved + "/assets/Video"]:
            result = self.shell("test ! -L " + shlex.quote(child)
                                + "\nif test -e " + shlex.quote(child) + "; then test -d " + shlex.quote(child)
                                + "; readlink -f " + shlex.quote(child) + "; fi", root=True).strip()
            if result and result != child:
                raise ValueError(f"Persistent resource directory resolves elsewhere: {child}")
        return resolved

    def exists(self, path):
        return self.shell("if test -e " + shlex.quote(path) + "; then echo yes; else echo no; fi", root=True).strip() == "yes"

    def file_state(self, path):
        if not self.exists(path):
            return {"exists": False, "path": path}
        raw = self.shell("test -f " + shlex.quote(path) + "\ntest ! -L " + shlex.quote(path)
                         + "\nstat -c %s " + shlex.quote(path) + "\nsha256sum " + shlex.quote(path), root=True).splitlines()
        size, digest = int(raw[0]), raw[1].split()[0]
        if not SHA_RE.fullmatch(digest):
            raise ValueError("Unexpected device hash response")
        return {"exists": True, "path": path, "size": size, "sha256": digest}

    def read_bytes(self, path):
        # su shell may alter binary newlines; base64 keeps byte-exact backups.
        return base64.b64decode(self.shell("base64 " + shlex.quote(path), root=True))

    def install(self, staged, destination):
        temporary = destination + ".server19-cg-new-" + str(time.time_ns())
        if self.exists(temporary):
            raise ValueError(f"Preexisting install temporary preserved: {temporary}")
        self.shell("cp " + shlex.quote(staged) + " " + shlex.quote(temporary)
                   + "\nmv " + shlex.quote(temporary) + " " + shlex.quote(destination), root=True)

    def remove_created_index(self, path, expected_sha):
        """Restore prior absence only for this tool's exact newly written index."""
        state = self.file_state(path)
        if not state["exists"]:
            return
        if state.get("sha256") != expected_sha:
            raise ValueError("New Version.txt differs; cannot prove ownership for removal")
        if PurePosixPath(path).name != "Version.txt" or not SHA_RE.fullmatch(expected_sha):
            raise ValueError("Only the owned newly created native index can be removed")
        self.shell("test -f " + shlex.quote(path) + "\ntest ! -L " + shlex.quote(path)
                   + "\ntest \"$(sha256sum " + shlex.quote(path) + " | cut -d ' ' -f1)\" = "
                   + shlex.quote(expected_sha) + "\nrm " + shlex.quote(path), root=True)
        if self.exists(path):
            raise ValueError("New native index remained after restoring prior absence")


def audit(args, device=None):
    manifest, eligible = validate_prepared(args.manifest)
    device = device or Device(args.serial)
    info = device.identity()
    files = device.persistent_directory(args.persistent_files)
    target = files + "/assets/Video"
    version = target + "/Version.txt"
    raw = device.read_bytes(version) if device.exists(version) else b""
    keys = version_keys(raw)
    library = device.file_state(info["library"])
    account_path = local_path(args.account, exists=True)
    account_sha = hash_file(account_path)
    previous = read_json(args.deployment_receipt) if getattr(args, "deployment_receipt", None) else None
    checked = []
    for row in eligible:
        state = device.file_state(target + "/" + row["filename"])
        checked.append({"filename": row["filename"], "native_key": row["native_key"], "file": state,
                        "file_matches": state.get("size") == row["size"] and state.get("sha256") == row["sha256"],
                        "registered": row["native_key"] in keys, "version_value": keys.get(row["native_key"])})
    result = {"audited_at": timestamps(), "identity": info, "persistent_files": files,
              "prepared_manifest": relative(local_path(args.manifest)), "files": checked,
              "version_path": version, "version_sha256": hashlib.sha256(raw).hexdigest(),
              "version_key_count": len(keys), "library": library,
              "account_path": relative(account_path), "account_sha256": account_sha,
              "all_external_files_and_keys_valid": all(r["file_matches"] and r["registered"] for r in checked),
              "builtin_external_override_paths_present": [n for n in sorted(BUILTIN) if device.exists(target + "/" + n)],
              "missing": [r["filename"] for r in manifest["resources"] if r["status"] == "missing"],
              "validation_boundary": "File/key availability audit only; no playback/plot completion assertion."}
    if previous:
        result["library_matches_deployment_before"] = library.get("sha256") == previous["before"]["library"].get("sha256")
        result["account_matches_deployment_before"] = account_sha == previous["before"]["account_sha256"]
    if getattr(args, "output", None):
        write_json(args.output, result)
    return result


def deploy(args, device=None):
    manifest, eligible = validate_prepared(args.manifest)
    if not eligible:
        raise ValueError("No verified external CG files to deploy")
    device = device or Device(args.serial)
    info = device.identity()
    files = device.persistent_directory(args.persistent_files)
    target = files + "/assets/Video"
    account_path = local_path(args.account, exists=True)
    stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S-%f")
    evidence_root = local_path(args.evidence_root)
    if not evidence_root.is_relative_to(local_path("server19-run")):
        raise ValueError("Deployment evidence must stay below server19-run")
    evidence = evidence_root / stamp
    if evidence.exists():
        raise ValueError("Deployment evidence directory already exists")
    evidence.mkdir(parents=True)
    version_path = target + "/Version.txt"
    receipt = {"schema_version": 1, "started_at": timestamps(), "identity": info,
               "persistent_files": files, "target_directory": target,
               "prepared_manifest": relative(local_path(args.manifest)),
               "prepared_manifest_sha256": hash_file(local_path(args.manifest)),
               "status": "preflight", "files": [], "index_committed": False,
               "evidence_directory": relative(evidence),
               "scope": "Only verified external CG bytes and native Version.txt; no account/library/firewall changes."}
    receipt_path = evidence / "deployment.json"
    write_json(receipt_path, receipt)
    try:
        before = {"library": device.file_state(info["library"]), "account_sha256": hash_file(account_path),
                  "account_path": relative(account_path)}
        if not before["library"].get("exists") or before["library"].get("size", 0) <= 0:
            raise ValueError("Installed client library unavailable")
        receipt["before"] = before
        # The only process action. Do not launch or stop server/ADB/firewall helpers.
        device.adb("shell", "am", "force-stop", PKG)
        if hash_file(account_path) != before["account_sha256"]:
            raise ValueError("Account changed during package stop; no resources installed")
        device.shell("mkdir -p " + shlex.quote(target), root=True)
        state = device.file_state(version_path)
        original_version = device.read_bytes(version_path) if state["exists"] else b""
        if state["exists"] and hashlib.sha256(original_version).hexdigest() != state["sha256"]:
            raise ValueError("Version backup changed during read")
        backup_dir = evidence / "backup" / "Video"
        backup_dir.mkdir(parents=True)
        (backup_dir / "Version.txt").write_bytes(original_version)
        receipt["before"]["version"] = {**state, "backup_path": relative(backup_dir / "Version.txt")}
        merged = merge_version(original_version, [r["filename"] for r in eligible])
        next_version = evidence / "Version.next.txt"
        next_version.write_bytes(merged)
        staged_root = "/data/local/tmp/bh3-server19-cg-" + stamp
        # ADB上传使用shell身份；暂存目录由同一身份创建。
        # Keep staging owned by shell so non-root adbd can push on ARM devices.
        device.shell("test ! -e " + shlex.quote(staged_root) + "\nmkdir " + shlex.quote(staged_root))
        receipt["remote_staging_directory"] = staged_root
        receipt["status"] = "backing_up"
        # All overwritten bytes are backed up before the first replacement.
        for row in eligible:
            destination = target + "/" + row["filename"]
            old = device.file_state(destination)
            item = {"filename": row["filename"], "native_key": row["native_key"], "expected_sha256": row["sha256"],
                    "expected_size": row["size"], "before": old, "installed": False}
            if old["exists"]:
                data = device.read_bytes(destination)
                if len(data) != old["size"] or hashlib.sha256(data).hexdigest() != old["sha256"]:
                    raise ValueError(f"Device backup verification failed: {row['filename']}")
                backup = backup_dir / row["filename"]
                backup.write_bytes(data)
                item["before"]["backup_path"] = relative(backup)
            receipt["files"].append(item)
            write_json(receipt_path, receipt)
        receipt["status"] = "staging_and_installing"
        for row, item in zip(eligible, receipt["files"]):
            staged = staged_root + "/" + row["filename"]
            device.adb("push", str(local_path(row["prepared_path"], exists=True)), staged)
            remote = device.file_state(staged)
            if remote.get("size") != row["size"] or remote.get("sha256") != row["sha256"]:
                raise ValueError(f"Staged hash mismatch: {row['filename']}")
            destination = target + "/" + row["filename"]
            if device.file_state(destination) != {k: v for k, v in item["before"].items() if k != "backup_path"}:
                raise ValueError(f"Device target changed after backup: {row['filename']}")
            device.install(staged, destination)
            installed = device.file_state(destination)
            if installed.get("size") != row["size"] or installed.get("sha256") != row["sha256"]:
                raise ValueError(f"Installed readback mismatch: {row['filename']}")
            item.update({"installed": True, "after": installed})
            write_json(receipt_path, receipt)
        # A second complete target pass is required immediately before index change.
        for row in eligible:
            remote = device.file_state(target + "/" + row["filename"])
            if remote.get("size") != row["size"] or remote.get("sha256") != row["sha256"]:
                raise ValueError("Target changed before native version commit")
        if device.file_state(info["library"])["sha256"] != before["library"]["sha256"] or hash_file(account_path) != before["account_sha256"]:
            raise ValueError("Account or client library changed; native version index not committed")
        current_version = device.file_state(version_path)
        if current_version != state:
            raise ValueError("Version.txt changed externally; index not committed")
        staged_version = staged_root + "/Version.next.txt"
        device.adb("push", str(next_version), staged_version)
        if device.file_state(staged_version).get("sha256") != hashlib.sha256(merged).hexdigest():
            raise ValueError("Staged native version hash mismatch")
        receipt["status"] = "committing_native_index"
        write_json(receipt_path, receipt)
        device.install(staged_version, version_path)
        committed = device.file_state(version_path)
        if committed.get("sha256") != hashlib.sha256(merged).hexdigest():
            raise ValueError("Version index readback failed")
        receipt["index_committed"] = True
        receipt["after"] = {"version": committed, "library": device.file_state(info["library"]),
                            "account_sha256": hash_file(account_path)}
        receipt["unchanged"] = {"library": receipt["after"]["library"]["sha256"] == before["library"]["sha256"],
                                "account": receipt["after"]["account_sha256"] == before["account_sha256"]}
        if not all(receipt["unchanged"].values()):
            raise ValueError("Post-deployment account/library preservation check failed")
        receipt["status"] = "deployed_verified"
        receipt["finished_at"] = timestamps()
        write_json(receipt_path, receipt)
        return {"receipt": relative(receipt_path), "deployed_count": len(eligible), "status": receipt["status"],
                "index_committed": True, "unchanged": receipt["unchanged"],
                "missing": [r["filename"] for r in manifest["resources"] if r["status"] == "missing"]}
    except Exception as error:
        # If commit/readback fails, restore exact previous index bytes. No new
        # success keys survive failure. Media/backups remain for explicit recovery.
        if receipt.get("status") == "committing_native_index" or receipt.get("index_committed"):
            try:
                if not state["exists"]:
                    device.remove_created_index(version_path, hashlib.sha256(merged).hexdigest())
                    receipt["previous_index_absence_restored"] = True
                else:
                    restore = evidence / "Version.restore.txt"
                    restore.write_bytes(original_version)
                    staged_restore = staged_root + "/Version.restore.txt"
                    device.adb("push", str(restore), staged_restore)
                    if device.file_state(staged_restore).get("sha256") != hashlib.sha256(original_version).hexdigest():
                        raise ValueError("Restore stage hash mismatch")
                    device.install(staged_restore, version_path)
                    if device.file_state(version_path).get("sha256") != hashlib.sha256(original_version).hexdigest():
                        raise ValueError("Previous native index could not be read back")
                receipt["index_committed"] = False
                receipt["index_restored_after_failure"] = True
            except Exception as restore_error:
                receipt["index_restore_error"] = str(restore_error)
        receipt.update({"status": "failed", "finished_at": timestamps(), "error_type": type(error).__name__, "error": str(error)})
        write_json(receipt_path, receipt)
        raise RuntimeError(f"CG deployment failed; inspect {relative(receipt_path)}: {error}") from error


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    sub = command.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Read-only inputs; stage verified media locally")
    prep.add_argument("--apk", default=DEFAULT_APK)
    prep.add_argument("--cg-table", default=DEFAULT_TABLE)
    prep.add_argument("--download-table", help="Explicit unmodified source table matching download receipt; only the confirmed 76-row icon-prefix correction may differ from --cg-table")
    prep.add_argument("--official-manifest", default=DEFAULT_OFFICIAL)
    prep.add_argument("--decoder-manifest", default=DEFAULT_DECODER)
    prep.add_argument("--accepted-reference-manifest", help="Explicit acceptance JSON; default disables all references")
    prep.add_argument("--output", default=DEFAULT_PREPARED)
    for name in ["deploy", "audit"]:
        item = sub.add_parser(name, help="Explicit device mutation" if name == "deploy" else "Read-only native file/key/hash audit")
        item.add_argument("--manifest", default=DEFAULT_MANIFEST)
        item.add_argument("--serial", default="TARGET_ADDRESS_REQUIRED:5555")
        item.add_argument("--persistent-files", required=True, help="Actual observed Android persistentDataPath; existing named-package files directory")
        item.add_argument("--account", default="server19-run/account.json")
        if name == "deploy":
            item.add_argument("--evidence-root", default="server19-run/cg-deployments")
        else:
            item.add_argument("--deployment-receipt", help="Compare account/library against exact deployment-before receipt")
            item.add_argument("--output", help="Optional project-local audit JSON")
    return command


if __name__ == "__main__":
    arguments = parser().parse_args()
    result = {"prepare": prepare, "deploy": deploy, "audit": audit}[arguments.command](arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))
