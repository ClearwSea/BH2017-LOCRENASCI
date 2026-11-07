"""Export the single evidenced NPC hard-level row needed by native stage10101.

The row is real 2.4-package data whose TSV version begins at2.3. It is explicit
later compatibility, not recovered historical1.9 balancing. The original five
fields and source float32 values are preserved. No generic exporter, canonical
baseline, device, native library, service or account is changed by this tool.
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
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

import analyze19 as native
import server19_metadata_export as metadata
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-npc-level-resources"
ACT101_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-entry-npc-level-resources"
CANONICAL = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected"
REFERENCE20 = ROOT / ".local-baseline/original-apks/bh3-2.0-original-reference.apk"
PATH = "_exceloutputasset/npclevellogic"
TEXT_PATH = "data/_exceloutput/npclevellogic"
ORIGINAL19_SHA = "672c3eadd1300accb265f09dfce52f05965b15e4b1a8d54114913f3f4f87d5be"
ORIGINAL20_SHA = "4bf5d8d0be981e6c3cc319f55786490abf115f1db27f49d9e02f73a63a1b07e7"
NATIVE19_SHA = "dc8365244e56a9de670b326d40510cab688d6876107e6a9151372917963ada7d"
SOURCE24_SHA = "41b0dfa3ed7ffb07cee808acab3691c7ada5f28361023b0c88f3b2aa2a2af042"
SOURCE_ASSET_SHA = "322071734ff9e231f32e66a36f06f13bdee88cc035dabc314814388338c20883"
SOURCE_TEXT_OBJECT_SHA = "8323ea204fc65df0519ba8c285cdf558f51f686621f4090ab9cacfb7bb0ed7b7"
SOURCE_TSV_SHA = "be84aa3b203b95231cf2569a8f1dace293301105b4661cab6c5c1a7a8b15ece1"
EMPTY_SHA = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
STAGE_SHA = "e535124cbbb34f2f47a64cbd18453dc018cf7b8a724f9a8f8f8e8f266ed6b743"
MONSTER_SHA = "729d2454ab0d2dbdd8c95cb0832a6073e673c2348e86d8dc4d57b23fa66933bc"
FIELDS = ("HardLevel", "HPRatio", "ATKRatio", "DEFRatio", "ElementalResistRatio")
EXPECTED_ROW = {"HardLevel": 1, "HPRatio": 1.0, "ATKRatio": 1.0,
                "DEFRatio": 1.0, "ElementalResistRatio": 0.05}
METHODS = (55211, 55212, 55215, 47863, 65971, 69222, 68412, 65953, 66400)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def checked_file(path, expected):
    value = path.read_bytes()
    if sha(value) != expected:
        raise ValueError("Accepted source or evidence changed: " + str(path))
    return value


def original_schema():
    fields = metadata.serialized_fields(7195)
    if native.type_name(7195) != "MoleMole.NPCLevelMetaData" or tuple(n for n, _ in fields) != FIELDS:
        raise ValueError("Original NPCLevelMetaData fields changed")
    if [metadata.type_info(p)["kind"] for _, p in fields] != [8, 12, 12, 12, 12]:
        raise ValueError("Original NPC level field types changed")
    if struct.unpack_from("<II", native.E, 0x34a67d4) != (12645, 0x33e5924):
        raise ValueError("Original field-offset registration changed")
    ptr = struct.unpack_from("<I", native.E, 0x33e5924 + 7195 * 4)[0]
    offsets = [struct.unpack_from("<I", native.E, ptr + n * 4)[0] for n in range(5)]
    if offsets != [8, 12, 16, 20, 24]:
        raise ValueError("Original NPC level field offsets changed")
    consumers = [{"method_index": mid, "name": native.N[mid],
                  "address": hex(native.pointer(native.M[mid])),
                  "disassembly": native.disasm(mid, 16384)} for mid in METHODS]
    init = next(x["disassembly"] for x in consumers if x["method_index"] == 47863)
    for token in ("01022684", "0x1196740", "0102269b", "0x1022d0c", "010226a6", "01022777"):
        if token not in init:
            raise ValueError("Original NPC lookup/consumption evidence changed")
    return [{"name": name, "kind": metadata.type_info(pointer)["kind"], "native_offset": offset}
            for (name, pointer), offset in zip(fields, offsets)], consumers


def select_row(tsv, typed_rows):
    reader = csv.DictReader(io.StringIO(tsv.decode("utf-8")), delimiter="\t")
    expected_columns = list(FIELDS) + ["GameVersionBegin", "GameVersionEnd", "EffectRegionList"]
    if reader.fieldnames != expected_columns:
        raise ValueError("Source NPC TSV schema changed")
    rows = list(reader)
    if len(rows) != 2000 or len(typed_rows) != 2000:
        raise ValueError("Source NPC table count changed")
    if any(set(row) != set(expected_columns) or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed NPC TSV row")
    if any(row["GameVersionBegin"] != "2.3" or row["GameVersionEnd"] != "" or
           row["EffectRegionList"] != "all" or metadata.in_version(row, (1, 9)) for row in rows):
        raise ValueError("Source version-filtered empty provenance changed")
    selected = [(index, row) for index, row in enumerate(rows) if row["HardLevel"] == "1"]
    typed = [row for row in typed_rows if row.get("HardLevel") == 1]
    if len(selected) != 1 or len(typed) != 1:
        raise ValueError("NPC hard-level1 must exist exactly once in both real sources")
    index, row = selected[0]
    output = {name: int(row[name]) if name == "HardLevel" else float(row[name]) for name in FIELDS}
    if output != EXPECTED_ROW or type(typed[0]["HardLevel"]) is not int or set(typed[0]) != set(FIELDS):
        raise ValueError("Unaccepted NPC hard-level1 values")
    float_proof = {}
    for name in FIELDS[1:]:
        encoded = struct.pack("<f", output[name])
        if encoded != struct.pack("<f", typed[0][name]):
            raise ValueError("TSV/ScriptableObject NPC float32 mismatch: " + name)
        float_proof[name] = {"source_tsv": row[name], "source_typed": typed[0][name],
                             "output_json": output[name], "preserved_float32_hex": encoded.hex()}
    return output, {"source_row_index": index, "source_tsv_line": index + 2,
                    "source_row": row, "source_typed_row": typed[0], "float32_equality": float_proof,
                    "excluded_version_count": len(rows), "selected_compatibility_rows": 1}


def build(apk19=resources.DEFAULT19, apk24=resources.DEFAULT24):
    if file_sha(apk19) != ORIGINAL19_SHA or sha(native.E) != NATIVE19_SHA:
        raise ValueError("Original1.9 package/native changed")
    if file_sha(apk24) != SOURCE24_SHA or file_sha(REFERENCE20) != ORIGINAL20_SHA:
        raise ValueError("Audited source or original2.0 reference changed")
    old_maps = []
    for version, path in (("1.9", apk19), ("2.0", REFERENCE20)):
        mapped = resources.resource_map(path)
        matches = [record for record in mapped if "npclevel" in record["path"].lower()]
        if matches:
            raise ValueError("Older NPC resource is available; refuse later replacement without audit")
        old_maps.append({"version": version, "path": str(path.resolve()), "resource_count": len(mapped),
                         "search": "npclevel substring in ResourceManager paths", "matches": matches,
                         "limit": "Negative mapped-resource result, not a claim that every unindexed package object was searched"})
    mapped = {record["path"]: record for record in resources.resource_map(apk24)}
    with zipfile.ZipFile(apk24) as package:
        asset_obj, raw = resources.object_bytes(package, mapped[PATH])
        text_obj, text_raw = resources.object_bytes(package, mapped[TEXT_PATH])
        if asset_obj["class"] != 114 or text_obj["class"] != 49 or sha(raw) != SOURCE_ASSET_SHA or sha(text_raw) != SOURCE_TEXT_OBJECT_SHA:
            raise ValueError("Real source NPC object/class changed")
        name, tsv = resources.text_asset(text_raw)
        if name != "NPCLevelLogic" or sha(tsv) != SOURCE_TSV_SHA:
            raise ValueError("Real source NPC TextAsset changed")
        decoder = metadata.SourceTypedDecoder(package)
        source_fields = decoder.fields(decoder.names["MoleMole.NPCLevelMetaData"])
        if tuple(n for n, _ in source_fields) != FIELDS or [
                (struct.unpack_from("<II", decoder.binary, p)[1] >> 16) & 255 for _, p in source_fields] != [8, 12, 12, 12, 12]:
            raise ValueError("Original/source NPC five-field schema differs")
        source_rows = decoder.rows(raw, "MoleMole.NPCLevelMetaData")
        row, row_audit = select_row(tsv, source_rows)
    schema, consumers = original_schema()
    empty = checked_file(CANONICAL / PATH, EMPTY_SHA)
    if json.loads(empty) != []:
        raise ValueError("Canonical NPC table is not the audited empty table")
    canonical_manifest = json.loads((CANONICAL / "manifest.json").read_bytes())
    records = [record for record in canonical_manifest["files"] if record.get("resource_path") == PATH]
    if len(records) != 1 or any(records[0].get(k) != v for k, v in {
            "source_rows": 2000, "excluded_version": 2000, "output_rows": 0,
            "output_sha256": EMPTY_SHA, "missing_fields": [], "unsupported_fields": [], "conversion_errors": []}.items()):
        raise ValueError("Canonical empty-table filter audit changed")
    stage_data = checked_file(CANONICAL / "_exceloutputasset/stagedata_main", STAGE_SHA)
    stage_rows = [r for r in json.loads(stage_data) if r["levelId"] == 10101]
    if len(stage_rows) != 1 or any(stage_rows[0].get(k) != v for k, v in {
            "hardLevel": 1, "type": 1, "UseDynamicHardLv": 0}.items()):
        raise ValueError("Current real stage NPC hard-level condition changed")
    monster_data = checked_file(CANONICAL / "_exceloutputasset/monsterconfigdata", MONSTER_SHA)
    monsters = [r for r in json.loads(monster_data) if r.get("monsterName") == "DeadWalker" and r.get("typeName") == "Default"]
    if len(monsters) != 1 or any(monsters[0].get(k) != v for k, v in {
            "configFile": "DG_010_Config", "HP": 820.0, "attack": 8.0, "defense": 16.0}.items()):
        raise ValueError("Current first real Monster basic row changed")
    log_path = ROOT / "server19-run/diagnostics/stage-20261011-1629/fixture7-movement2.log"
    log = log_path.read_bytes()
    needle = "1791713508.060  8871  8954 I Unity   : BH3SERVER19_NULL caller=01022d11 parent=0102f57a"
    if needle.encode() not in log:
        raise ValueError("Actual first-Monster failure trace is absent")
    encoded, fixups = metadata.native_json([row])
    payload = (encoded + "\n").encode("utf-8")
    if fixups or json.loads(payload) != [EXPECTED_ROW]:
        raise ValueError("Original native JSON number/shape projection changed")
    references = {"reference/npclevellogic.tsv": tsv, "reference/npclevellogic-scriptableobject.bin": raw,
                  "reference/npclevellogic-textasset.bin": text_raw, "reference/canonical-empty.json": empty,
                  "reference/original-native-consumers.json": json_bytes(consumers)}
    manifest = {"format": "server19-stage10101-npc-hardlevel1-explicit-later-compatibility-v1",
        "stage_id": 10101, "hard_level": 1,
        "source19": {"path": str(apk19.resolve()), "sha256": ORIGINAL19_SHA, "native_sha256": NATIVE19_SHA},
        "source24": {"path": str(apk24.resolve()), "sha256": SOURCE24_SHA, "package_version": "2.4.0", "row_version_begin": "2.3"},
        "older_mapped_resource_search": old_maps,
        "deployment_files": [PATH], "files": [{"path": PATH, "bytes": len(payload), "output_sha256": sha(payload),
            "required_existing_sha256": EMPTY_SHA, "source_asset": {**mapped[PATH], "class": 114, "name": name,
                "bytes": len(raw), "sha256": sha(raw)},
            "source_text_asset": {**mapped[TEXT_PATH], "class": 49, "name": name, "bytes": len(text_raw), "sha256": sha(text_raw)},
            "source_text_sha256": sha(tsv), "projection": row_audit,
            "original_row_type": "MoleMole.NPCLevelMetaData", "original_five_fields": schema,
            "mapping": {field: field for field in FIELDS}, "missing_fields": [], "unsupported_fields": [],
            "omitted_tsv_metadata_fields": ["GameVersionBegin", "GameVersionEnd", "EffectRegionList"]}],
        "canonical_empty_evidence": {"path": str((CANONICAL / PATH).resolve()), "sha256": EMPTY_SHA,
            "record": records[0], "reason": "All2000 real source rows begin2.3, so original1.9 version filtering excludes every row",
            "device_readback": "Root independently confirmed the installed same-path [] SHA37517e5f; this helper does not read or deploy a device"},
        "stage_binding": {"metadata_path": "_exceloutputasset/stagedata_main", "sha256": STAGE_SHA,
            "levelId": 10101, "type": 1, "hardLevel": 1, "UseDynamicHardLv": 0,
            "native_chain": "LevelDataItem.get_NPCHardLevel68412 -> SetLevelBeginIntent69222 @c2bd5b writes LevelScoreManager+48 -> GetNPCHardLevel65971 -> CreateMonster65953 -> MonsterManager66400 -> InitLevelData47863 @1022684 looks up key1",
            "lua_wave_count_is_not_level": True, "tutorial_section_hard_level_add": 0,
            "basic_monster_row_sha256": MONSTER_SHA, "first_monster_basic_row": monsters[0]},
        "actual_failure": {"log_path": str(log_path.resolve()), "log_sha256": sha(log), "trace": needle,
            "npc_null_branch": "InitLevelData@102269b ->1022d0c ->Null helper return1022d11",
            "limit": "Shared Null exit also has other callers; deterministic missing key1 is evidenced, actual play after supplying it remains required"},
        "references": [{"path": path, "bytes": len(value), "sha256": sha(value)} for path, value in references.items()],
        "limits": ["Only real hard-level1 is supplied; no other NPC levels are exported",
            "Source2.4 package / version2.3 row is explicit later compatibility, not historical1.9 balance",
            "All original five values preserve source numeric values and float32 representations",
            "Generic1.9 version filter and canonical frozen artifacts remain unchanged",
            "Native Monster initialization and subsequent combat/settlement still need actual device verification",
            "No device, native-library, service, account, progress or stamina operation"]}
    return {PATH: payload, **references, "manifest.json": json_bytes(manifest)}, manifest


def build_act101(apk19=resources.DEFAULT19, apk24=resources.DEFAULT24):
    """Keep the frozen key1 profile; supply only actual Normal hard-levels1–3."""
    targets, manifest = build(apk19, apk24)
    existing = checked_file(DEFAULT_OUTPUT / PATH, "652d64bfbe1ab56ee2d26e91228b77196752424a6f6c43ae9e307f86a12a27da")
    if json.loads(existing) != [EXPECTED_ROW]:
        raise ValueError("Frozen key1 output changed")
    source_rows = list(csv.DictReader(io.StringIO(targets["reference/npclevellogic.tsv"].decode()), delimiter="\t"))
    with zipfile.ZipFile(apk24) as package:
        decoder = metadata.SourceTypedDecoder(package)
        typed = decoder.rows(targets["reference/npclevellogic-scriptableobject.bin"], "MoleMole.NPCLevelMetaData")
    selected, audits = [], []
    for level in (1, 2, 3):
        actual = [row for row in source_rows if row["HardLevel"] == str(level)]
        typed_actual = [row for row in typed if row["HardLevel"] == level]
        if len(actual) != 1 or len(typed_actual) != 1:
            raise ValueError("Required actual NPC hard-level row absent")
        row = {field: int(actual[0][field]) if field == "HardLevel" else float(actual[0][field]) for field in FIELDS}
        if row["HardLevel"] != level or actual[0]["GameVersionBegin"] != "2.3":
            raise ValueError("Required NPC row scope/version changed")
        for field in FIELDS[1:]:
            if struct.pack("<f", row[field]) != struct.pack("<f", typed_actual[0][field]):
                raise ValueError("Required NPC TSV/typed float32 differs")
        selected.append(row)
        audits.append({"source_row": actual[0], "source_typed_row": typed_actual[0],
                       "preserved_float32_hex": {field: struct.pack("<f", row[field]).hex() for field in FIELDS[1:]}})
    expected = [EXPECTED_ROW,
        {"HardLevel": 2, "HPRatio": 1.002, "ATKRatio": 1.08, "DEFRatio": 1.06, "ElementalResistRatio": 0.05},
        {"HardLevel": 3, "HPRatio": 1.015, "ATKRatio": 1.16, "DEFRatio": 1.13, "ElementalResistRatio": 0.05}]
    if selected != expected:
        raise ValueError("Audited real levels1/2/3 values changed")
    payload = (metadata.native_json(selected)[0] + "\n").encode()
    stages = [row for row in json.loads(checked_file(CANONICAL / "_exceloutputasset/stagedata_main", STAGE_SHA))
              if 10101 <= row["levelId"] <= 10106]
    bindings = [{key: row[key] for key in ("levelId", "actId", "type", "hardLevel", "UseDynamicHardLv")} for row in stages]
    if [(r["levelId"], r["hardLevel"], r["UseDynamicHardLv"]) for r in bindings] != [
            (10101, 1, 0), (10102, 1, 0), (10103, 2, 0), (10104, 2, 0), (10105, 2, 0), (10106, 3, 0)]:
        raise ValueError("Only six evidenced Normal stage bindings supported")
    manifest["format"] = "server19-act101-normal-and-act102-entry-npc-levels-explicit-later-compatibility-v1"
    manifest["profile"] = "act101_entry"
    manifest["stage_ids"] = list(range(10101, 10107))
    manifest["hard_levels"] = [1, 2, 3]
    manifest["files"][0].update(bytes=len(payload), output_sha256=sha(payload),
        required_existing_sha256=sha(existing), projection={"selected_real_rows": audits,
        "output_rows": selected, "all_values_and_float32_encodings_preserved": True,
        "source_version_filter_unchanged": True, "excluded_version_count": 2000})
    manifest["stage_binding"]["actual_six_normal_stage_bindings"] = bindings
    manifest["frozen_key1_sha256"] = sha(existing)
    manifest["limits"][0] = "Only real hard-levels1/2/3 required by Normal10101–10106; other NPC levels remain unavailable"
    targets[PATH] = payload
    targets["manifest.json"] = json_bytes(manifest)
    return targets, manifest


def prepare(apk19, apk24, output, profile="firststage"):
    resolved = output.resolve()
    if resolved == CANONICAL.resolve() or resolved in CANONICAL.resolve().parents or resolved.is_relative_to(CANONICAL.resolve()):
        raise ValueError("Independent output must not overwrite or contain the canonical baseline")
    targets, manifest = (build_act101 if profile == "act101_entry" else build)(apk19, apk24)
    for relative, data in targets.items():
        target = output / relative
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError("Preserve changed existing output: " + str(target))
    for relative, data in targets.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    return {"status": "explicit_real_later_npc_levels1_to3_exported" if profile == "act101_entry" else "explicit_real_later_npc_level1_exported", "output": str(resolved),
            "deployment_files": [PATH], "output_sha256": sha(targets[PATH]),
            "manifest_sha256": sha(targets["manifest.json"]), "bytes": len(targets[PATH]),
            "runtime_compatibility": "unaccepted"}


def audit(apk19, apk24, output, profile="firststage"):
    targets, manifest = (build_act101 if profile == "act101_entry" else build)(apk19, apk24)
    for relative, expected in targets.items():
        if (output / relative).read_bytes() != expected:
            raise ValueError("NPC export/source/evidence bytes changed: " + relative)
    return {"status": "real_source_and_original_five_fields_verified", "output": str(output.resolve()),
            "deployment_files": [PATH], "output_sha256": sha(targets[PATH]),
            "manifest_sha256": sha(targets["manifest.json"]), "bytes": len(targets[PATH]),
            "runtime_compatibility": "unaccepted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "audit"))
    parser.add_argument("--apk19", type=Path, default=resources.DEFAULT19)
    parser.add_argument("--apk24", type=Path, default=resources.DEFAULT24)
    parser.add_argument("--profile", choices=("firststage", "act101_entry"), default="firststage")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (ACT101_OUTPUT if args.profile == "act101_entry" else DEFAULT_OUTPUT)
    print(json.dumps((prepare if args.command == "prepare" else audit)(args.apk19, args.apk24, output, args.profile), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
