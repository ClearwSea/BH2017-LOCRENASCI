"""Batch original-APK avatar identity and bounded battle-resource closure.

Read stock1.9 identities and sourced compatible tables. Extend the accepted58
ability container; unsupported roots stay exact and are reported per avatar.
No device, account, native library, server, unlock or battle operation occurs.
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
import copy
import csv
import io
import json
import re
import struct
from pathlib import Path
import zipfile

import server19_resources as resources
import server19_stage_abilities as ability
import server19_stage_monsters as baked

ROOT = Path(__file__).resolve().parent
BASE = ROOT / ".local-baseline/server19-dev/stage7-ready"
TABLES = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"
DEFAULT_OUTPUT = ROOT / ".local-baseline/server19-dev/avatar-battle-ready"
BASE_SHA = "366e62ea5c81edf75af5c20ab36fbae93339331978c9419868b32ea36c23ede8"
STRINGS = ROOT / ".local-baseline/server19-dev/act101-native-prop-resources/_baked/stringmap.txt"
AVATARS = ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/bakedavatardata"
WEAPONS = ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/bakedweapondata"
WEAPON_ATTACH_PROOF = ROOT / "server19-run/avatar-roster-audit/weapon-attach/weapon-attach-mapping.json"
STATISTICS_PROOF = ROOT / "server19-run/avatar-roster-audit/later-statistics/later-statistics-proof.json"
GATE_PROOF = ROOT / "server19-run/avatar-roster-audit/avatar-ability-gates.json"
SKILL_END_PROOF = ROOT / "server19-run/avatar-roster-audit/later-statistics/avatar-skill-end-coverage.json"
STOP_RANK = "MoleMole.Config.StopLevelScoreRankAutoReduce"
SKILL_END = "MoleMole.Config.AvatarSkillEnd"


class BattleSchema(ability.CultivationSchema):
    """Batch-only schema evidence; legacy bounded builders stay unchanged."""
    camera_indices = tuple(range(563))
    fixed_global_types = ("MoleMole.Config.AddGlobalValue", "MoleMole.Config.ClearGlobalValue")
    batch_later_score = True

    def __init__(self, package, strings):
        super().__init__(package)
        # Any literal string is allowed only with the already-proven Evaluate
        # false -> fixedValue branch; dynamic keys still fail in AbilityReader.
        if self.source.binary[0x14a0752:0x14a075a] != bytes.fromhex("8b460ce988000000"):
            raise ValueError("Fixed DynamicString original source consumer changed")
        self.fixed_global_keys = frozenset(strings)
        maps = {x["path"]: x for x in resources.resource_map(Path(package.filename))}
        _, raw = resources.object_bytes(package, maps["data/_exceloutput/levelstatistics"])
        _, data = resources.text_asset(raw)
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8")), delimiter="\t"))
        self.score_rows = [row for row in rows
            if row["GameVersionBegin"] and tuple(map(int, row["GameVersionBegin"].split("."))) > (1, 9) and row["type"] == "Score"]
        self.later_score_ids = tuple(int(row["statisticsID"]) for row in self.score_rows)
        self.batch_indexed = {}
        proof_raw = WEAPON_ATTACH_PROOF.read_bytes()
        self.weapon_attach_proof = json.loads(proof_raw)
        proof = self.weapon_attach_proof
        if proof["original_library_sha256"] != baked.NATIVE19_SHA or proof["source_library_sha256"] != baked.sha(self.source.binary):
            raise ValueError("WeaponAttach proof references different native binaries")
        for key, binary in (("original_poly_read", ability.a.E), ("source_poly_read", self.source.binary)):
            part = proof[key]; left, right = int(part["rva"], 16), int(part["end_rva"], 16)
            if baked.sha(binary[left:right]) != part["method_sha256"]:
                raise ValueError("WeaponAttach source/native switch proof changed")
        self.weapon_attach_proof_sha256 = baked.sha(proof_raw)
        if ability.STATISTICS in self.original_names:
            raise ValueError("Original absent later score-framework proof changed")
        self.statistics_proof = json.loads(STATISTICS_PROOF.read_bytes())
        proof = self.statistics_proof
        for key, value in (("original_library_sha256", baked.NATIVE19_SHA),
                           ("source_library_sha256", baked.sha(self.source.binary)),
                           ("original_metadata_sha256", baked.sha(ability.a.B)),
                           ("source_metadata_sha256", baked.sha(self.source.metadata)),
                           ("source_ability_container_sha256", ability.SOURCE_SHA)):
            if proof[key] != value:
                raise ValueError("Later action proof references a different input: " + key)
        for method in proof["native_methods"].values():
            left, right = int(method["rva"], 16), int(method["end_rva"], 16)
            if baked.sha(self.source.binary[left:right]) != method["sha256"]:
                raise ValueError("Later action handler proof changed")
        for name, absent in proof["original_types_absent"].items():
            if absent and name in self.original_names:
                raise ValueError("Later action exists in the original: " + name)
        if baked.sha(data) != proof["source_TSV"]["text_sha256"]:
            raise ValueError("Later statistics table differs from proof")
        self.mission_rows = [row for row in rows if int(row["statisticsID"]) in (2021, 2131)]
        if len(self.mission_rows) != 2 or any(row["type"] != "Mission" or row["GameVersionBegin"] != "2.1" or row["overrideList"] != "TargetNum:3" for row in self.mission_rows):
            raise ValueError("Only separately proven later Mission2021/2131 are allowed")
        self.later_action_mappings = []
        gates = json.loads(GATE_PROOF.read_bytes())
        if gates["original_library_sha256"] != baked.NATIVE19_SHA:
            raise ValueError("Original avatar gate proof changed")
        for method in gates["methods"]:
            left, right = int(method["rva"], 16), int(method["end_rva"], 16)
            if baked.sha(ability.a.E[left:right]) != method["method_sha256"]:
                raise ValueError("Original avatar gate consumer changed")
        self.skill_end_proof = None
        if SKILL_END_PROOF.exists():
            raw = SKILL_END_PROOF.read_bytes()
            if baked.sha(raw) != "fc8aee396b8e22ffb421b2894be08646019becb909c9b6309101dde63fa6c56b":
                raise ValueError("Frozen skill-end consumer-coverage proof changed")
            end = json.loads(raw)
            for key, value in (("original_library_sha256", baked.NATIVE19_SHA),
                               ("source_library_sha256", baked.sha(self.source.binary)),
                               ("original_metadata_sha256", baked.sha(ability.a.B)),
                               ("source_metadata_sha256", baked.sha(self.source.metadata))):
                if end[key] != value:
                    raise ValueError("Skill-end consumer proof input differs")
            if end["matching_generic_inst_indices"] != [11531] or end["unresolved_reference_candidates"]:
                raise ValueError("Skill-end registration coverage differs")
            if [(x["index"], x["method_inst"]) for x in end["matching_method_specs"]] != [(16487, 11531), (16495, 11531)]:
                raise ValueError("Skill-end register/remove consumers differ")
            for method in end["method_bodies"]:
                binary = ability.a.E if method["original"] else self.source.binary
                left, right = int(method["rva"], 16), int(method["end_rva"], 16)
                if baked.sha(binary[left:right]) != method["sha256"]:
                    raise ValueError("Skill-end source/original method proof changed")
            for name in end["later_types_absent_from_original"]:
                if name in self.original_names:
                    raise ValueError("Preserve an original skill-end consumer")
            plugin = end["original_plugin"]; ti = plugin["type_index"]
            old_type = ability.a.T[ti]
            methods = [ability.a.N[i] for i in range(old_type[17], old_type[17] + old_type[24])]
            if ability.a.type_name(ti) != plugin["name"] or methods != plugin["method_names"] or not any(n.endswith("::ListenSkillStart") for n in methods) or any(n.endswith("::ListenSkillEnd") for n in methods):
                raise ValueError("Preserve exact original damage-statistics plugin and SkillStart")
            self.skill_end_proof = end

    def check(self, name):
        if name in self.checks:
            return
        if name in self.fixed_global_types:
            old, new = self.members(name, True), self.members(name, False)
            os = [(n, self.signature(p, True)) for n, p in old]
            ns = [(n, self.signature(p, False)) for n, p in new]
            extras = [n for n, _ in new if n not in dict(old)]
            ns = [(n, s) for n, s in ns if n in dict(old)]
            if len(os) != len(ns) or [n for n, _ in old] != [n for n, _ in ns]:
                raise ValueError("Global-value declaration requires separate evidence: " + name)
            if [(n, s) for n, s in os if n != "Key"] != [(n, s) for n, s in ns if n != "Key"] or dict(os)["Key"] != "primitive:0xe" or dict(ns)["Key"] != "MoleMole.DynamicString":
                raise ValueError("Only fixed Key wrapper type difference supported: " + name)
            self.checks[name] = {"type": name, "excluded_fields": extras, "original_fields": [n for n, _ in old],
                "source_fields": [n for n, _ in new], "only_proven_fixed_key_wrapper_differs": True}
            return
        try:
            super().check(name)
        except ValueError:
            if name not in self.original_names or name not in self.source.names:
                raise
            old, new = self.members(name, True), self.members(name, False)
            old_names = {n for n, _ in old}
            kept = [(n, p) for n, p in new if n in old_names]
            if [(n, self.signature(p, True)) for n, p in old] != [(n, self.signature(p, False)) for n, p in kept]:
                raise
            extras = [n for n, _ in new if n not in old_names]
            if not extras:
                raise
            self.checks[name] = {"type": name, "original_fields": [n for n, _ in old],
                "source_fields": [n for n, _ in new], "excluded_fields": extras,
                "retained_type_signatures": [self.signature(p, True) for _, p in old],
                "retained_declarations_equal": True,
                "policy": "Exact original retained order/types verified; each extra must be actual nil or the root fails"}


class BattleReader(ability.AbilityReader):
    def class_value(self, name, path, depth=0):
        try:
            if name == ability.ACTION and not self.original and self.data[self.pos] != 0xc0:
                q = baked.MessagePackSpanReader(self.data); q.pos = self.pos
                code = self.data[q.pos]
                width = 1 if code == 0x92 else 3 if code == 0xdc and self.data[q.pos + 1:q.pos + 3] == b"\x00\x02" else 5 if code == 0xdd and self.data[q.pos + 1:q.pos + 5] == b"\x00\x00\x00\x02" else 0
                if not width:
                    raise ValueError("Action union must retain tag/payload")
                q.pos += width
                tag = baked.decode_integer(self.data, q.node())
                concrete, mapping = self.schema.resolve_tag(name, tag, False)
                if concrete not in (ability.STATISTICS, STOP_RANK, SKILL_END):
                    return super().class_value(name, path, depth)
                q.pos = self.pos; node = q.node()
                remove, facts = False, {}
                if concrete == ability.STATISTICS:
                    self.schema.check(concrete)
                    payload = node["children"][1]
                    if payload["kind"] != "array" or payload["count"] != 6:
                        raise ValueError("Later statistics six-field payload changed")
                    ident = payload["children"][0]
                    if ident["kind"] == "array" and ident["count"] == 3:
                        dynamic, fixed, key = ident["children"]
                        if dynamic["code"] in (0xc0, 0xc2) and key["code"] == 0xc0 and fixed["code"] != 0xc0:
                            number = baked.decode_integer(self.data, fixed)
                            if number in self.schema.later_score_ids:
                                remove, facts = True, {"StatisticsID": number, "statistics_type": "Score", "source_version": "post1.9 (2.2/2.3)"}
                            elif number in (2021, 2131):
                                value = payload["children"][1]
                                exact = (value["kind"] == "array" and value["count"] == 3
                                    and self.data[value["start"]:value["end"]] == bytes.fromhex("93c0ca3f800000c0")
                                    and all(child["code"] == 0xc0 for child in payload["children"][2:]))
                                if exact:
                                    remove, facts = True, {"StatisticsID": number, "Value": 1.0, "statistics_type": "Mission", "source_version": "2.1"}
                elif concrete == STOP_RANK:
                    payload = node["children"][1]
                    fields = self.schema.members(concrete, False)
                    if payload["kind"] != "array" or payload["count"] != len(fields) or [n for n, _ in fields] != ["Duration", "Target", "TargetOption", "Predicates", "MPTotallyLocal"]:
                        raise ValueError("Later rank-maintenance source fields changed")
                    # Common handler proof writes only the later plugin timer.
                    # Its predicates remain inside this whole removed action.
                    remove, facts = True, {"statistics_type": "RankDecayMaintenance", "fields": [n for n, _ in fields]}
                elif concrete == SKILL_END and self.schema.skill_end_proof is not None:
                    payload = node["children"][1]
                    fields = self.schema.members(concrete, False)
                    expected = [("CDSkillID", "primitive:0xe"), ("CountInStatistics", "primitive:0x2"),
                        ("Target", "MoleMole.Config.AbilityTargetting"), ("TargetOption", "MoleMole.Config.TargettingOption"),
                        ("Predicates", ability.PREDICATE + "[]"), ("MPTotallyLocal", "primitive:0x2")]
                    if payload["kind"] != "array" or payload["count"] != 6 or [(n, self.schema.signature(p, False)) for n, p in fields] != expected:
                        raise ValueError("Later skill-duration notification payload changed")
                    remove, facts = True, {"statistics_type": "LaterSkillDurationNotification",
                        "source_version": "Absent original1.9/present pinned2.4; first release unknown",
                        "skill_end_coverage_proof_sha256": baked.file_sha(SKILL_END_PROOF),
                        "original_LevelDamageStasticsPlugin_and_SkillStart_preserved": True}
                if remove:
                    tail = q.node(); local_id = baked.decode_integer(self.data, tail)
                    if not 0 <= local_id < 1 << 31:
                        raise ValueError("Removed action configLocalID must retain Int32 range")
                    node["end"] = q.pos; node["remove_from_array"] = True; self.pos = q.pos
                    self.schema.later_action_mappings.append({"path": path, "source": mapping, "original_type_absent": True})
                    self.records.append({"operation": "remove_later_statistics_action", "path": path,
                        "source_class": concrete, "source_byte_span": [node["start"], q.pos],
                        "source_raw_hex": self.data[node["start"]:q.pos].hex(),
                        "source_sha256": baked.sha(self.data[node["start"]:q.pos]),
                        "handler_proof_sha256": baked.file_sha(STATISTICS_PROOF), **facts,
                        "reason": "Verified later statistics-only framework absent in original1.9; every other action retained"})
                    return node
            if name == "MoleMole.Config.ConfigWeaponAttach":
                nil = self.nullable(path)
                if nil is not None:
                    return nil
                node = self.header("array")
                if node["count"] != 2:
                    raise ValueError("WeaponAttach union must retain tag/payload")
                tag = self.node(); value = baked.decode_integer(self.data, tag)
                proof = self.schema.weapon_attach_proof
                rows = proof["mapping"] if self.original else proof["source_tag_translation"]
                matching = [row for row in rows if row["original_tag" if self.original else "source_tag"] == value]
                if len(matching) != 1 or matching[0]["original_tag"] is None:
                    raise ValueError("WeaponAttach tag unavailable in original1.9")
                row = matching[0]
                if not self.original and row["original_tag"] != value:
                    self.edits.append((tag["start"], tag["end"], ability.integer_bytes(row["original_tag"])))
                    self.records.append({"operation": "union_tag_same_type", "path": path,
                        "source_tag": value, "original_tag": row["original_tag"], "concrete": row["type"],
                        "source_byte_span": [tag["start"], tag["end"]]})
                child = self.class_value(row["type"], path + "<" + row["type"] + ">", depth + 1)
                node["children"] = [tag, child]; node["end"] = self.pos
                return node
            files = {"MoleMole.Config.ConfigEntityAttackProperty": "_baked/bakedconfigentityattackproperty",
                "MoleMole.Config.ConfigEntityAttackEffect": "_baked/bakedconfigentityattackeffect"}
            if name in files and self.data[self.pos] not in (0xc0, 0xdc, 0xdd) and not 0x90 <= self.data[self.pos] <= 0x9f:
                node = self.node(); index = baked.decode_integer(self.data, node)
                cache = self.schema.batch_indexed
                if name not in cache:
                    payload = (ROOT / ".local-baseline/server19-dev/baked-fallback" / files[name]).read_bytes()
                    base = json.loads((ROOT / ".local-baseline/server19-dev/baked-fallback/manifest.json").read_bytes())
                    expected = next(row for row in base["resources"] if row["path"] == files[name])["output_sha256"]
                    if baked.sha(payload) != expected:
                        raise ValueError("Preserve accepted indexed dependency")
                    flag, packed_hash, count = struct.unpack_from("<III", payload)
                    if flag != 1:
                        raise ValueError("Expected indexed dependency container")
                    offsets = struct.unpack_from("<" + str(count) + "I", payload, 12)
                    size = struct.unpack_from("<I", payload, 12 + count * 4)[0]
                    data = payload[16 + count * 4:]
                    if len(data) != size:
                        raise ValueError("Indexed dependency byte count differs")
                    cache[name] = {"path": files[name], "sha256": expected, "count": count,
                        "offsets": offsets, "data": data, "checked": {}}
                item = cache[name]
                if not 0 <= index < item["count"]:
                    raise ValueError("Indexed dependency outside original container")
                if index not in item["checked"]:
                    left = item["offsets"][index]
                    q = baked.MessagePackSpanReader(item["data"]); q.pos = left; expected = q.node()
                    if self.data is item["data"]:
                        raise ValueError("Recursive indexed root")
                    reader = BattleReader(item["data"], self.strings, self.schema, True); reader.pos = left
                    reader.class_value(name, path + "[indexed]")
                    if reader.pos != expected["end"]:
                        raise ValueError("Original indexed root consumer boundary differs")
                    item["checked"][index] = {"index": index, "span": [left, reader.pos],
                        "sha256": baked.sha(item["data"][left:reader.pos]), "original_consumed": True}
                self.schema.indexed_references.append({"type": name, "index": index, "path": path,
                    "resource": files[name], "resource_sha256": item["sha256"]})
                return self.leaf(path, node)
            return super().class_value(name, path, depth)
        except ValueError as error:
            raise ValueError(str(error) + " at " + path + " (" + name + ")") from error


def packed(raw):
    h, entries, overrides, data = baked.unpack_container(raw)
    refs = {off: (key, None) for key, off in entries}
    refs.update({off: (key, variant) for key, variant, off in overrides})
    if len(refs) != len(entries) + len(overrides):
        raise ValueError("Shared packed roots need separate identity evidence")
    ends = dict(zip(sorted(refs), sorted(refs)[1:] + [len(data)]))
    return h, entries, overrides, data, refs, {identity: (off, ends[off]) for off, identity in refs.items()}


def retained_terminals(reader):
    """Track original semantic paths after removing proved later array entries."""
    excluded = {row["path"] for row in reader.records if row["operation"] == "remove_later_field"}
    removed = [row for row in reader.records if row["operation"] in ("remove_later_statistics_action",'remove_later_ui_action')]
    groups = {}
    for row in removed:
        match = re.fullmatch(r"(.*)\[(\d+)\]", row["path"])
        if match is None:
            raise ValueError("Removed later action must be an actual array entry")
        groups.setdefault(match[1], set()).add(int(match[2]))
    source, translated = {}, {}
    for path, leaf in reader.leaves.items():
        left, right = leaf["span"]
        if path in excluded or any(a <= left and right <= b for row in removed for a, b in [row["source_byte_span"]]):
            continue
        source[path] = leaf
        target = path
        # Inner original prefixes must be translated before their parent index.
        for parent, indices in sorted(groups.items(), key=lambda x: len(x[0]), reverse=True):
            match = re.match(re.escape(parent) + r"\[(\d+)\]", target)
            if match:
                index = int(match[1])
                if index in indices:
                    raise ValueError("Deleted action retained a terminal")
                new_index = index - sum(i < index for i in indices)
                target = parent + f"[{new_index}]" + target[match.end():]
        for record in reader.records:
            if record['operation'] not in ('project_leader_physical_reduction', 'approximate_trial_all_channel_reduction'):continue
            prefix=record['path']
            if target.startswith(prefix+'.'):
                target=target.replace('<MoleMole.Config.ModifyDamageTakenWithRestrictMixin>',
                                      '<MoleMole.Config.ModifyDamageTakenMixin>')
        if target in translated:
            raise ValueError("Array removal collapsed distinct retained terminals")
        translated[target] = leaf
    return source, translated


def apply_edits(data, left, right, reader):
    removed = [row["source_byte_span"] for row in reader.records
               if row["operation"] == "remove_later_statistics_action"]
    # A removed complete action already owns its child bytes. Edits proved for
    # those children are redundant and cannot overlap the final byte splice.
    edits = [(a, b, value) for a, b, value in reader.edits
             if not any(x <= a and b <= y and (x, y) != (a, b) for x, y in removed)]
    output, cursor = bytearray(), left
    for a, b, value in sorted(set(edits)):
        if not cursor <= a < b <= right:
            raise ValueError("Overlapping/beyond-root edits")
        output.extend(data[cursor:a]); output.extend(value); cursor = b
    output.extend(data[cursor:right])
    return bytes(output)


def build(apk19, apk24, reuse_final=None):
    if baked.file_sha(apk19) != baked.ORIGINAL19_SHA or baked.file_sha(apk24) != baked.SOURCE24_SHA:
        raise ValueError("Pinned original/reference APK identity changed")
    previous = (BASE / ability.PATH).read_bytes()
    base_manifest_raw = (BASE / "ability-manifest.json").read_bytes()
    baseline = json.loads(base_manifest_raw)
    if baked.sha(previous) != BASE_SHA or baseline["files"][0]["projection"]["selected_roots"] != 58:
        raise ValueError("Preserve the accepted58 ability baseline")
    source = (BASE / "reference" / ability.PATH).read_bytes()
    if baked.sha(source) != ability.SOURCE_SHA:
        raise ValueError("Exact later source ability bytes required")
    strings_raw = STRINGS.read_bytes()
    if baked.sha(strings_raw) != "297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1":
        raise ValueError("Never replace or renumber the accepted extended StringMap")
    strings = strings_raw.decode("utf-8").split("\x1f")
    avatar_raw, weapon_raw = AVATARS.read_bytes(), WEAPONS.read_bytes()
    if baked.sha(avatar_raw) != "dfd331e7b89063be037e6cfbf930fc6f48a42a9189ca3a54307c73a43bfab6e2":
        raise ValueError("Preserve existing64 Avatar structural projections")
    _, avatar_entries, _, avatar_data, _, _ = packed(avatar_raw)
    _, weapon_entries, _, weapon_data, _, weapon_spans = packed(weapon_raw)
    h, entries, overrides, old_data, refs, old_spans = packed(previous)
    _, _, _, source_data, _, source_spans = packed(source)
    already = {(row["key"], row["variant"]) for row in baseline["files"][0]["projection"]["roots"]}
    table_names = ("avatardata", "avatarskilldata", "avatarsubskilldata", "weapondata")
    inputs = {name: (TABLES / name).read_bytes() for name in table_names}
    tables = {name: json.loads(raw) for name, raw in inputs.items()}
    skills = {row["skillId"]: row for row in tables["avatarskilldata"]}
    subs = {row["avatarSubSkillId"]: row for row in tables["avatarsubskilldata"]}
    weapon_meta = {row["ID"]: row for row in tables["weapondata"]}
    original_map = {row["path"]: row for row in resources.resource_map(apk19)}
    source_map = {row["path"]: row for row in resources.resource_map(apk24)}
    changes, records, errors, nested, results = {}, [], {}, {}, []
    weapon_changes, weapon_records = {}, []
    identity_pending, original_proofs = [], {}
    cached = None
    if reuse_final is not None:
        cached_raw = (reuse_final / "manifest.json").read_bytes()
        if baked.sha(cached_raw) != "8e5ecec671189a9d2c491644f4c116585547f98a15e8c8551a8d1bf0d0eaddb9":
            raise ValueError("Only the frozen, checked final candidate may be reused")
        cached = json.loads(cached_raw)
        if baked.file_sha(reuse_final / "verification.json") != "85729b3c1de27a1ad0e5b1673e62a8b8dca8f15d35330ff82b8e0396ccceaa9b":
            raise ValueError("Frozen final verification receipt changed")
        for row in cached["table_inputs"]:
            if baked.sha(inputs[row["name"]]) != row["sha256"]:
                raise ValueError("Reused avatar/table input differs")
        prior_raw = (reuse_final / ability.PATH).read_bytes()
        if baked.sha(prior_raw) != "0e818456ae0c17dccfe45a7ccd2f99c7904bce5b1352757c93b0df7a54cf5638":
            raise ValueError("Frozen final ability bytes changed")
        _, _, _, pd, _, ps = packed(prior_raw)
        verified = json.loads((reuse_final / "verification.json").read_bytes())
        verified_rows = {(r["key"], r["variant"]): r for r in verified["per_root_checks"]}
        for row in cached["projection"]["projected_roots"]:
            identity = row["key"], row["variant"]; left, right = ps[identity]
            value = pd[left:right]
            if baked.sha(value) != row["output_sha256"] or baked.sha(value) != verified_rows[identity]["sha256"]:
                raise ValueError("Reused root differs from original-consumer checked bytes")
            changes[identity] = value
            nested[identity] = [tuple(x) for x in row["nested_refs"]]
            record = copy.deepcopy(row); record["validation_reused_from_frozen_final"] = True
            records.append(record)
        errors.update({(r["key"], r["variant"]): r["reason"] for r in cached["unsupported_roots"]
                       if "MoleMole.Config.AvatarSkillEnd" not in r["reason"]})
        results = copy.deepcopy(cached["roster"])
        for report in results:
            report["blockers"] = [b for b in report["blockers"] if "chain" not in b]
        original_proofs.update({r["path"]: r for r in cached["original_resource_evidence"]})
        prior_weapon = (reuse_final / "_baked/bakedweapondata").read_bytes()
        if baked.sha(prior_weapon) != "a80515b45debbfe6e95cf25b34cb47912ee0ec91951223df631c4e553a36bafa":
            raise ValueError("Frozen final weapon bytes changed")
        _, _, _, pwd, _, pws = packed(prior_weapon)
        for identity in map(tuple, cached["weapon_changed_roots"]):
            left, right = pws[identity]; weapon_changes[identity] = pwd[left:right]
        weapon_records = copy.deepcopy(cached["weapon_roots"])

    def number(data, node):
        return None if node["code"] == 0xc0 else baked.decode_integer(data, node)

    def text(data, node):
        key = number(data, node)
        return None if key is None else strings[key]

    with zipfile.ZipFile(apk19) as original, zipfile.ZipFile(apk24) as reference:
        decoder = ability.SourceTypedDecoder(reference)
        _, raw = resources.object_bytes(reference, source_map["data/_exceloutput/avatardata"])
        _, avatar_tsv = resources.text_asset(raw)
        source_rows = list(csv.DictReader(io.StringIO(avatar_tsv.decode("utf-8")), delimiter="\t"))
        compatible_ids = {row["avatarID"] for row in tables["avatardata"]}
        for row in source_rows:
            reg = row["avatarRegistryKey"].lower()
            model = f"entities/avatar/{reg}/avatar_{reg}"
            if model in original_map and int(row["avatarID"]) not in compatible_ids:
                identity_pending.append({"avatar_id": int(row["avatarID"]), "registry": row["avatarRegistryKey"],
                    "original_model": original_map[model], "source_version_begin": row["GameVersionBegin"],
                    "status": "original_APK_preinstalled_identity_or_release_scope_pending",
                    "reason": "Model presence alone does not establish playable1.9 armor; absent from current sourced1.9 table"})
        # Effect group identities live inside original ScriptableObjects. All
        # native model/material/animation resource bytes stay in the stock APK.
        effect_groups = {}
        for path, record in original_map.items():
            if not path.startswith("effect/data/"):
                continue
            obj, raw = resources.object_bytes(original, record)
            effect_groups[path] = (record, obj, raw)

        def original_proof(path):
            if path not in original_map:
                return None
            if path not in original_proofs:
                obj, raw = resources.object_bytes(original, original_map[path])
                original_proofs[path] = {"path": path, "resource": original_map[path], "class": obj["class"],
                    "object_sha256": baked.sha(raw), "object_bytes": len(raw), "operation": "original_APK_retained"}
            return path

        schema = BattleSchema(reference, strings)
        if cached is not None:
            schema.checks.update({row["type"]: copy.deepcopy(row) for row in cached["schema_evidence"]})
            schema.mapping_checks.extend(copy.deepcopy(cached["union_mapping_evidence"]))
            schema.indexed_references.extend(copy.deepcopy(cached["indexed_references"]))
            schema.later_action_mappings.extend(copy.deepcopy(cached["later_action_mapping_evidence"]))

        def project(identity):
            if identity in already or identity in changes or identity in errors:
                return
            if identity not in source_spans or identity not in old_spans:
                errors[identity] = "Required actual ability registry identity missing"
                return
            left, right = source_spans[identity]
            start, end = old_spans[identity]
            if old_data[start:end] != source_data[left:right]:
                errors[identity] = "Unselected source root was changed outside accepted58 baseline"
                return
            reader = BattleReader(source_data, strings, schema)
            reader.pos = left
            # Save dependency side effects only for successfully parsed roots.
            index_start = len(schema.indexed_references)
            try:
                reader.class_value(ability.ABILITY, "ability")
                if reader.pos != right:
                    raise ValueError("Source root does not end at its registry boundary")
                output = apply_edits(source_data, left, right, reader)
                check = BattleReader(bytes(output), strings, schema, True)
                check.class_value(ability.ABILITY, "ability")
                retained, translated = retained_terminals(reader)
                if check.pos != len(output) or set(translated) != set(check.leaves) or any(
                        leaf["sha256"] != check.leaves[path]["sha256"] for path, leaf in translated.items()):
                    raise ValueError("Original consumer or retained terminal values differ")
                dependencies = []
                for path, leaf in retained.items():
                    if path == "ability.AbilityName" or not path.endswith(".AbilityName"):
                        continue
                    q = baked.MessagePackSpanReader(source_data); q.pos = leaf["span"][0]; key = number(source_data, q.node())
                    if key is None:
                        continue
                    prefix = path.removesuffix("AbilityName")
                    variant = None
                    companion = retained.get(prefix + "AbilityOverride")
                    if companion:
                        q.pos = companion["span"][0]; variant = number(source_data, q.node())
                        if variant is not None and strings[variant] == "Default":
                            variant = None
                    dependencies.append((key, variant))
                changes[identity] = bytes(output)
                nested[identity] = dependencies
                records.append({"key": identity[0], "variant": identity[1], "name": strings[identity[0]],
                    "source_span": [left, right], "source_sha256": baked.sha(source_data[left:right]),
                    "output_sha256": baked.sha(output), "adaptations": reader.records,
                    "original_full_root_consumed": True, "retained_terminal_values_byte_identical": True,
                    "retained_terminal_count": len(retained), "nested_refs": [list(x) for x in dependencies]})
                for dependency in dependencies:
                    project(dependency)
            except (ValueError, KeyError, IndexError) as error:
                errors[identity] = str(error)
                del schema.indexed_references[index_start:]

        if cached is not None:
            for report in results:
                for dependency in report["dependencies"]:
                    project((dependency["key"], dependency["variant"]))
        for row in ([] if cached is not None else tables["avatardata"]):
            aid, reg = row["avatarID"], row["avatarRegistryKey"]
            lower = reg.lower()
            model = f"entities/avatar/{lower}/avatar_{lower}"
            animator = model + "_anicontroller"
            report = {"avatar_id": aid, "registry": reg, "full_name_key": row["fullName"],
                "scope_evidence": "Sourced1.9-filtered avatar row crossed with original1.9 model/animator/effect identities",
                "source_avatar_rows": [x for x in source_rows if x["avatarID"] == str(aid)],
                "original_resources": [], "dependencies": [], "blockers": [], "warnings": []}
            for path in (model,):
                proof = original_proof(path)
                if proof is None:
                    report["blockers"].append({"scope": "base", "path": path, "reason": "Original model/animator absent"})
                else:
                    report["original_resources"].append(proof)
            # Shared controllers and embedded references cannot be inferred
            # from a per-armor filename convention. Inspect real Animator PPtr.
            if model in original_map:
                record = original_map[model]
                full = original.read("assets/bin/Data/" + record["file"])
                layout = resources.serialized(full)
                animator_refs = []
                for obj in layout["objects"].values():
                    if obj["class"] != 95:
                        continue
                    file_id, path_id = struct.unpack_from("<iq", full, obj["offset"] + 28)
                    controller_file = layout["externals"][file_id - 1].rsplit("/", 1)[-1] if file_id else record["file"]
                    controller_file = "globalgamemanagers" if controller_file == "globalgamemanagers.assets" else controller_file
                    data = original.read("assets/bin/Data/" + controller_file)
                    controller = resources.serialized(data)["objects"].get(path_id)
                    if controller is None or controller["class"] not in (91, 221):
                        raise ValueError("Original Animator controller reference is invalid")
                    value = data[controller["offset"]:controller["offset"] + controller["size"]]
                    animator_refs.append({"file": controller_file, "path_id": path_id, "class": controller["class"],
                        "object_sha256": baked.sha(value), "origin": "Original model Animator95 m_Controller PPtr+28"})
                report["original_animator_references"] = animator_refs
                if not animator_refs:
                    report["blockers"].append({"scope": "base", "reason": "Original model lacks evidenced Animator controller"})
            key = strings.index(reg) if reg in strings else None
            if key not in dict(avatar_entries):
                report["blockers"].append({"scope": "base", "reason": "Avatar configuration root missing"})
                results.append(report); continue
            q = baked.MessagePackSpanReader(avatar_data); q.pos = dict(avatar_entries)[key]; actor = q.node()
            if actor["count"] != 25:
                raise ValueError("Preserve original25-field Avatar structure")
            common = actor["children"][0]
            if common["count"] != 20:
                raise ValueError("Avatar CommonArguments source shape changed")
            for node in common["children"][15]["children"]:
                group = text(avatar_data, node)
                encoded_group = group.encode("utf-8")
                serialized_group = struct.pack("<I", len(encoded_group)) + encoded_group
                matching = [path for path, (_, _, data) in effect_groups.items() if serialized_group in data]
                if not matching:
                    report["blockers"].append({"scope": "base", "effect_group": group, "reason": "Original effect group absent"})
                for path in matching:
                    report["original_resources"].append(original_proof(path))
            report["sound_bank_names"] = [text(avatar_data, n) for n in common["children"][16]["children"]]
            # Both constant and every real unlock reference are inventoried.
            # Conditional skill failures do not masquerade as base-entry failure.
            def dependency(key, variant, scope, evidence):
                if variant is not None and strings[variant] == "Default":
                    variant = None
                identity = key, variant
                report["dependencies"].append({"key": key, "variant": variant, "name": strings[key],
                    "scope": scope, "evidence": evidence})
                project(identity)
            constants = actor["children"][9]
            for name, value in zip(constants["children"][::2], constants["children"][1::2]):
                if value["count"] != 2:
                    raise ValueError("Constant ability entry shape changed")
                dependency(number(avatar_data, value["children"][0]), number(avatar_data, value["children"][1]),
                    "base", {"constant_entry": text(avatar_data, name), "actor_span": [value["start"], value["end"]]})
            for unlock in actor["children"][8]["children"]:
                if unlock["count"] != 12:
                    raise ValueError("Original12-field avatar unlock changed")
                values = unlock["children"]
                skill_id, sub_id = number(avatar_data, values[1]), number(avatar_data, values[2])
                skill, sub = skills.get(skill_id), subs.get(sub_id)
                is_skill = values[0]["code"] == 0xc3
                # Original59454 branches on IsUnlockBySkill, not on whether
                # SubSkillID is zero. False always calls the purchased-subskill
                # check59456; true checks main skill open-state59455.
                scope = "main_skill" if is_skill else "conditional_subskill"
                if skill_id == row["captainSkillID"]:
                    scope = "conditional_leader"
                # Level1/default-star main skills are conservative base needs;
                # higher gates remain conditional, and no unlock is granted.
                if scope == "main_skill" and skill and skill["unlockLv"] <= 1 and skill["unlockStar"] <= row["unlockStar"]:
                    scope = "base"
                dependency(number(avatar_data, values[3]), number(avatar_data, values[4]), scope,
                    {"skill_id": skill_id, "sub_skill_id": sub_id, "skill_gate": skill,
                     "subskill_gate": sub, "IsUnlockBySkill": is_skill,
                     "default_level1_star": row["unlockStar"], "default_subskill_level": 0,
                     "native_gate": "59455 main-open/leader" if is_skill else "59456 purchased-subskill",
                     "actor_span": [unlock["start"], unlock["end"]]})
            weapon_id = row["initialWeapon"]
            weapon = weapon_meta.get(weapon_id)
            if weapon_id not in dict(weapon_entries) or weapon is None:
                report["blockers"].append({"scope": "base", "weapon_id": weapon_id, "reason": "Actual initial weapon metadata/config absent"})
            else:
                proof = original_proof(weapon["bodyMod"].lower())
                if proof is None:
                    report["blockers"].append({"scope": "base", "path": weapon["bodyMod"], "reason": "Initial weapon model absent in originalAPK"})
                else:
                    report["original_resources"].append(proof)
                left, right = weapon_spans[weapon_id, None]
                q = baked.MessagePackSpanReader(weapon_data); q.pos = left; w = q.node()
                report["initial_weapon"] = {"id": weapon_id, "model": weapon["bodyMod"],
                    "root_sha256": baked.sha(weapon_data[left:right]), "field_count": w["count"],
                    "policy": "Keep exact existing weapon bytes; structural/union compatibility checked separately"}
                try:
                    reader = BattleReader(weapon_data, strings, schema); reader.pos = left
                    reader.class_value("MoleMole.Config.ConfigWeapon", "weapon")
                    if reader.pos != right:
                        raise ValueError("Original-compatible weapon root boundary changed")
                    value, cursor = bytearray(), left
                    for start, end, replacement in sorted(reader.edits):
                        if not cursor <= start < end <= right:
                            raise ValueError("Weapon edits overlap")
                        value.extend(weapon_data[cursor:start]); value.extend(replacement); cursor = end
                    value.extend(weapon_data[cursor:right])
                    check = BattleReader(bytes(value), strings, schema, True)
                    check.class_value("MoleMole.Config.ConfigWeapon", "weapon")
                    if check.pos != len(value) or set(reader.leaves) != set(check.leaves) or any(
                            leaf["sha256"] != check.leaves[path]["sha256"] for path, leaf in reader.leaves.items()):
                        raise ValueError("Weapon retained terminals/original consumer differ")
                    if reader.edits:
                        weapon_changes[weapon_id, None] = bytes(value)
                    report["initial_weapon"].update(original_full_root_consumed=True, adaptations=reader.records,
                        output_root_sha256=baked.sha(value), retained_terminal_values_byte_identical=True)
                    weapon_effects = []
                    for path, leaf in reader.leaves.items():
                        if not any(path.endswith("." + field) for field in ("WeaponEffectPattern", "LightingWeaponShell", "FireWeaponShell")):
                            continue
                        q = baked.MessagePackSpanReader(weapon_data); q.pos = leaf["span"][0]
                        effect = text(weapon_data, q.node())
                        if not effect:
                            continue
                        encoded = effect.encode("utf-8")
                        exact = struct.pack("<I", len(encoded)) + encoded
                        if path.endswith(".WeaponEffectPattern"):
                            matches = [name for name, (_, _, raw) in effect_groups.items() if exact in raw]
                        else:
                            # Himeko shell fields are actual prefab paths, not
                            # effect-pattern group names.
                            matches = [effect.lower()] if effect.lower() in original_map else []
                        weapon_effects.append({"field": path, "pattern": effect, "original_effect_groups": matches})
                        if not matches:
                            report["blockers"].append({"scope": "base", "weapon_id": weapon_id,
                                "effect_pattern": effect, "reason": "Original initial weapon effect pattern absent"})
                        for name in matches:
                            report["original_resources"].append(original_proof(name))
                    report["initial_weapon"]["effect_references"] = weapon_effects
                    if not any(row["weapon_id"] == weapon_id for row in weapon_records):
                        weapon_records.append({"weapon_id": weapon_id, **report["initial_weapon"]})
                except ValueError as error:
                    report["blockers"].append({"scope": "base", "weapon_id": weapon_id, "reason": str(error)})
                # ConfigWeapon.Meta is NotSerialized; AdditionalAbilities is
                # field3 in the original10-field stream.
                if w["count"] != 10:
                    report["blockers"].append({"scope": "base", "reason": "Weapon effective10-field layout differs"})
                else:
                    additional = w["children"][3]
                    if additional["code"] != 0xc0:
                        if additional["kind"] not in ("map", "array"):
                            report["blockers"].append({"scope": "base", "reason": "Weapon ability dictionary representation unresolved"})
                        else:
                            weapon_refs = additional["children"] if additional["kind"] == "array" else additional["children"][1::2]
                            for value in weapon_refs:
                                if value["count"] != 3:
                                    raise ValueError("Weapon ability entry shape changed")
                                dependency(number(weapon_data, value["children"][1]), number(weapon_data, value["children"][2]),
                                    "base", {"initial_weapon": weapon_id, "trigger_name": text(weapon_data, value["children"][0])})
                    report["warnings"].append("Human equipment-load/switch behavior still pending; static weapon proof is not gameplay")
            results.append(report)
        indexed = copy.deepcopy(schema.indexed_references)
        indexed_proofs = [{"type": name, "path": row["path"], "sha256": row["sha256"],
            "original_consumer_checked_roots": list(row["checked"].values())} for name, row in schema.batch_indexed.items()]
        if cached is not None:
            indexed_proofs = copy.deepcopy(cached["indexed_dependency_proofs"]) + indexed_proofs
        schemas = copy.deepcopy(list(schema.checks.values()))
        union_mappings = copy.deepcopy(schema.mapping_checks)
        score_rows = schema.score_rows
        mission_rows = schema.mission_rows
        later_action_mappings = copy.deepcopy(schema.later_action_mappings)

    # Filter out incomplete recursive closures; do not deploy half a mandatory
    # chain. Independent compatible branches remain useful to other avatars.
    def closure_error(identity, seen=None):
        seen = set() if seen is None else seen
        if identity in seen:
            return []
        seen.add(identity)
        if identity in errors:
            return [{"key": identity[0], "variant": identity[1], "reason": errors[identity]}]
        return [error for child in nested.get(identity, []) for error in closure_error(child, seen)]
    ready = {key: value for key, value in changes.items() if not closure_error(key)}
    for report in results:
        for dependency in report["dependencies"]:
            failures = closure_error((dependency["key"], dependency["variant"]))
            if failures:
                report["blockers"].append({"scope": dependency["scope"], "ability_name": dependency["name"], "chain": failures})
        report["original_resources"] = sorted(set(report["original_resources"]))
        report["base_closure_status"] = "blocked" if any(x["scope"] == "base" for x in report["blockers"]) else "source_closure_candidate_human_battle_pending"
        report["all_optional_skills_status"] = "blocked" if report["blockers"] else "candidate"
    output, offsets = bytearray(), {}
    for off, end in zip(sorted(refs), sorted(refs)[1:] + [len(old_data)]):
        offsets[off] = len(output); output.extend(ready.get(refs[off], old_data[off:end]))
    candidate = baked.pack_container(h, [(key, offsets[off]) for key, off in entries],
        [(key, variant, offsets[off]) for key, variant, off in overrides], bytes(output))
    _, next_entries, next_overrides, next_data, _, next_spans = packed(candidate)
    if [key for key, _ in entries] != [key for key, _ in next_entries] or [(key, variant) for key, variant, _ in overrides] != [(key, variant) for key, variant, _ in next_overrides]:
        raise ValueError("Batch changed registry identities/order")
    for identity, (left, right) in old_spans.items():
        after, end = next_spans[identity]
        if identity not in ready and old_data[left:right] != next_data[after:end]:
            raise ValueError("Accepted58/unsupported/unselected root was changed")
    wh, we, wo, wd, wr, ws = packed(weapon_raw)
    new_weapon_data, woffsets = bytearray(), {}
    for left, right in zip(sorted(wr), sorted(wr)[1:] + [len(wd)]):
        woffsets[left] = len(new_weapon_data)
        new_weapon_data.extend(weapon_changes.get(wr[left], wd[left:right]))
    next_weapon = baked.pack_container(wh, [(key, woffsets[off]) for key, off in we],
        [(key, variant, woffsets[off]) for key, variant, off in wo], bytes(new_weapon_data))
    _, ne, no, nw, _, nsp = packed(next_weapon)
    if [key for key, _ in ne] != [key for key, _ in we] or [(key, v) for key, v, _ in no] != [(key, v) for key, v, _ in wo]:
        raise ValueError("Weapon registry/order changed")
    for identity, (left, right) in ws.items():
        start, end = nsp[identity]
        if identity not in weapon_changes and wd[left:right] != nw[start:end]:
            raise ValueError("Unselected weapon root changed")
    for record in records:
        record["deployed"] = (record["key"], record["variant"]) in ready
        record["output_span"] = list(next_spans[record["key"], record["variant"]])
    retained_rows = copy.deepcopy(baseline["files"][0]["projection"]["roots"])
    for row in retained_rows:
        row["output_byte_span"] = list(next_spans[row["key"], row["variant"]])
    manifest = {"format": "server19-original-avatar-battle-batch-candidate-v1", "runtime_compatibility": "human_battle_pending",
        "source19": {"sha256": baked.ORIGINAL19_SHA}, "source24": {"sha256": baked.SOURCE24_SHA},
        "input58_manifest_sha256": baked.sha(base_manifest_raw), "avatar_tsv_sha256": baked.sha(avatar_tsv),
        "table_inputs": [{"name": n, "path": str(TABLES / n), "sha256": baked.sha(raw)} for n, raw in inputs.items()],
        "preserved_inputs": [{"path": str(path), "sha256": baked.file_sha(path)} for path in (AVATARS, WEAPONS, STRINGS, BASE / "manifest.json")],
        "deployment_files": ([ability.PATH] if ready else []) + (["_baked/bakedweapondata"] if weapon_changes else []),
        "files": [{"path": ability.PATH, "bytes": len(candidate), "output_sha256": baked.sha(candidate),
            "required_existing_sha256": BASE_SHA, "source_container_sha256": ability.SOURCE_SHA}],
        "projection": {"previous58_roots_byte_identical": True, "all_other_roots_byte_identical": True,
            "new_projected_count": len(ready), "projected_roots": [row for row in records if row["deployed"]],
            "preserved58_records": retained_rows, "all_keys_order_preserved": True, "all_offsets_recomputed": True},
        "roster": results, "identity_pending": identity_pending, "original_resource_evidence": list(original_proofs.values()),
        "unsupported_roots": [{"key": key, "variant": variant, "name": strings[key], "reason": reason} for (key, variant), reason in sorted(errors.items(), key=lambda x: (x[0][0], -1 if x[0][1] is None else x[0][1]))],
        "indexed_references": indexed,
        "indexed_dependency_proofs": indexed_proofs, "schema_evidence": schemas,
        "union_mapping_evidence": union_mappings, "later_score_source_rows": score_rows,
        "later_mission_source_rows": mission_rows, "later_action_mapping_evidence": later_action_mappings,
        "statistics_handler_proof_sha256": baked.file_sha(STATISTICS_PROOF),
        "avatar_gate_proof_sha256": baked.file_sha(GATE_PROOF),
        "skill_end_coverage_proof_sha256": baked.file_sha(SKILL_END_PROOF) if schema.skill_end_proof is not None else None,
        "fixed_global_key_evidence": {"source_Evaluate": "58144@14a0631 false/nil isDynamic ->14a0752 fixedValue",
            "actual_dynamic_keys_rejected": True, "literal_Key_child_encoding_preserved": True},
        "weapon_attach_proof_sha256": schema.weapon_attach_proof_sha256,
        "weapon_roots": weapon_records, "weapon_changed_roots": [list(x) for x in weapon_changes],
        "limits": ["No ownership, skill unlock, leader selection, native library31c, graphics or StringMap change",
            "25 sourced compatible-table identities crossed with originalAPK assets; other APK-preinstalled/later-table identities remain scope pending",
            "Static closures are candidates, not confirmed battle entry or original balancing/history",
            "Common-consumer proven fixed literal DynamicString, sourced post1.9 Score actions, exact Mission2021/2131 and later rank timer; dynamic IDs/unavailable gameplay actions remain blocked",
            "Original/source WeaponAttach mapping and original typed weapon roots checked; human switching/equipment behavior unverified",
            "No deployed resource outside this explicit ability/one-weapon overlay is regenerated or removed"]}
    if weapon_changes:
        manifest["files"].append({"path": "_baked/bakedweapondata", "bytes": len(next_weapon),
            "output_sha256": baked.sha(next_weapon), "required_existing_sha256": baked.sha(weapon_raw),
            "changed_roots": len(weapon_changes), "all_other_roots_byte_identical": True})
    if cached is not None:
        manifest["reused_final"] = {"path": str(reuse_final.resolve()), "manifest_sha256": baked.sha(cached_raw),
            "verification_sha256": baked.file_sha(reuse_final / "verification.json"),
            "projected_roots_reused_by_exact_hash": len(cached["projection"]["projected_roots"]),
            "only_new_roots_reparsed": len(ready) - len(cached["projection"]["projected_roots"])}
    if schema.skill_end_proof is not None:
        manifest["limits"].append("Only the proved later AvatarSkillEnd duration-statistics notification excluded; original Stats plugin/SkillStart and other actions retained; exact first release unknown")
    return {ability.PATH: candidate, "_baked/bakedweapondata": next_weapon,
        "reference/weapon-attach-mapping.json": WEAPON_ATTACH_PROOF.read_bytes(), "reference/before-weapon": weapon_raw,
        "reference/later-statistics-proof.json": STATISTICS_PROOF.read_bytes(),
        "reference/avatar-ability-gates.json": GATE_PROOF.read_bytes(),
        "reference/avatar-skill-end-coverage.json": SKILL_END_PROOF.read_bytes() if schema.skill_end_proof is not None else b"null\n",
        "reference/source-ability": source, "reference/before58-ability": previous,
        "manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()}, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk19", type=Path, default=resources.DEFAULT19)
    parser.add_argument("--apk24", type=Path, default=resources.DEFAULT24)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reuse-final", type=Path, help="Reuse only the exact frozen final receipt; check new roots only")
    args = parser.parse_args()
    targets, manifest = build(args.apk19, args.apk24, args.reuse_final)
    for relative, raw in targets.items():
        path = args.output / relative
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Preserve changed output; choose a new candidate directory")
    for relative, raw in targets.items():
        path = args.output / relative; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
    print(json.dumps({"output": str(args.output.resolve()), "roster": len(manifest["roster"]),
        "base_candidates": sum(x["base_closure_status"] != "blocked" for x in manifest["roster"]),
        "new_roots": manifest["projection"]["new_projected_count"], "blocked_roots": len(manifest["unsupported_roots"]),
        "manifest_sha256": baked.file_sha(args.output / "manifest.json"), "files": manifest["files"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
