"""Project bounded, audited later Monster layouts onto native 1.9.

The reference APK and every retained Monster value stay byte exact. Only the
proven later fields are removed, and container offsets are rebuilt. The
independent stage2 profile also projects one nil TargetLocked pattern field.
This is later compatibility data, not recovered historical 1.9 Monster data.
The helper neither deploys files nor runs a client, service or native patch.
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
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

import analyze19 as native
from server19_baked import MessagePackSpanReader
from server19_metadata_export import SourceTypedDecoder, fields, type_info, type_pointer
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-monster-resources"
ACT101_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-entry-monster-resources"
STAGE2_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-entry-monster-resources-v2"
ACT101_PRIMARY = {8522: ("DG_020_Config", "DeadArcher"), 20957: ("UL_020_Config", "UlyssesFast")}
PATH = "_baked/bakedmonsterdata"
ORIGINAL19_SHA = "672c3eadd1300accb265f09dfce52f05965b15e4b1a8d54114913f3f4f87d5be"
SOURCE24_SHA = "41b0dfa3ed7ffb07cee808acab3691c7ada5f28361023b0c88f3b2aa2a2af042"
NATIVE19_SHA = "dc8365244e56a9de670b326d40510cab688d6876107e6a9151372917963ada7d"
SOURCE_ASSET_SHA = "bbd1c2c73c484d5a4e5e28347f7648977f2a104527ae8be169cfa0e797cbbafd"
SOURCE_CONTAINER_SHA = "9fb68d5664165e59d307ea265faa01f374a5f0f867c503c102334383e41ca283"
STRINGMAP_SHA = "03813a7f76d611631768bf0dc9dfab685d0213d81af0f6ccdfdc09ae81d22405"
SELECTED = {8500: ("DG_010_Config", "DeadWalker", 14),
            20931: ("UL_010_Config", "UlyssesWarrior", 15)}
ROOT_FIELDS = ["CommonArguments", "StateMachinePattern", "DynamicArguments", "EliteArguments",
               "AIArguments", "EntityProperties", "Abilities", "Skills", "NamedStates",
               "AnimEvents", "MultiAnimEvents", "AnimatorConfig", "ATKRatioNames",
               "DebuffResistance", "AnimEventOverrides", "BodyPartSetting",
               "AnimatorStateParamBinds", "AdditionalAnimatorArguments", "MPArguments"]
ROOT_TYPE = "MoleMole.Config.ConfigMonster"
SKILL_TYPE = "MoleMole.Config.ConfigMonsterSkill"
TARGET_LOCKED_TYPE = "MoleMole.Config.TargetLockedAnimatedColliderDetect"
ACTUAL_ATTACK_PATTERN_TAGS = (1, 2, 4, 5, 6, 7, 8, 9, 10)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def decode_integer(data, node):
    raw, code = data[node["start"]:node["end"]], node["code"]
    if code <= 0x7f:
        return code
    if code >= 0xe0:
        return code - 256
    if code in (0xcc, 0xcd, 0xce, 0xcf, 0xd0, 0xd1, 0xd2, 0xd3):
        return int.from_bytes(raw[1:], "big", signed=code >= 0xd0)
    raise ValueError("Expected an integer token")


def string_index(data, node, strings):
    value = decode_integer(data, node)
    if not 0 <= value < len(strings):
        raise ValueError("Monster string-map index is outside the source map")
    return strings[value]


class MonsterReader(MessagePackSpanReader):
    """Use the native formatter's logical fields, including its custom map.

    ConfigDynamicArguments encodes map(N), then key/type/value N times. Its
    physical body has 3*N tokens, so an ordinary MessagePack map/tree parser
    cannot locate the enclosing logical root's tail or next root reliably.
    """
    def header(self, kind):
        start, code = self.pos, self.integer(1)
        base = 0x90 if kind == "array" else 0x80
        large = (0xdc, 0xdd) if kind == "array" else (0xde, 0xdf)
        if base <= code <= base + 15:
            count = code & 15
        elif code in large:
            count = self.integer(2 if code == large[0] else 4)
        else:
            raise ValueError(f"Expected Monster {kind} header at {start}")
        if count > len(self.data):
            raise ValueError("Monster header count exceeds payload")
        return {"start": start, "header_end": self.pos, "code": code,
                "kind": kind, "count": count}

    def dynamic(self, strings):
        if self.data[self.pos:self.pos + 1] == b"\xc0":
            return self.node()
        result = self.header("map")
        items, keys = [], set()
        for _ in range(result["count"]):
            key, discriminator, value = self.node(), self.node(), self.node()
            name = string_index(self.data, key, strings)
            if name in keys:
                raise ValueError("Duplicate DynamicArguments key")
            keys.add(name)
            tag = decode_integer(self.data, discriminator)
            if tag == 1:
                valid = value["code"] in (0xc2, 0xc3)
            elif tag == 2:
                valid = value["code"] in (0xca, 0xcb)
            elif tag == 3:
                number = decode_integer(self.data, value)
                valid = -(1 << 31) <= number < (1 << 31)
            elif tag == 4:
                if value["code"] != 0xc0:
                    string_index(self.data, value, strings)
                valid = True
            else:
                raise ValueError("DynamicArguments type is outside original native 1..4")
            if not valid:
                raise ValueError("DynamicArguments value disagrees with native type")
            items.append({"key": name, "type": tag,
                          "source_byte_span": [key["start"], value["end"]]})
        result.update(end=self.pos, children=[], custom_items=items)
        return result

    def root(self, strings, count):
        result = self.header("array")
        if result["count"] != count:
            raise ValueError(f"Monster root must have the audited {count} logical fields")
        result["children"] = [self.dynamic(strings) if index == 2 else self.node()
                              for index in range(count)]
        result["end"] = self.pos
        return result


def unpack_container(payload):
    if len(payload) < 20:
        raise ValueError("Truncated baked Monster container")
    indexed, packed_hash = struct.unpack_from("<II", payload)
    if indexed != 0:
        raise ValueError("Monster container must remain non-indexed")
    pos, arrays = 8, []
    for size in (8, 12, 1):
        if pos + 4 > len(payload):
            raise ValueError("Truncated Monster count")
        count = struct.unpack_from("<I", payload, pos)[0]
        pos += 4
        end = pos + count * size
        if end > len(payload):
            raise ValueError("Monster array exceeds container")
        arrays.append(payload[pos:end])
        pos = end
    if pos != len(payload):
        raise ValueError("Unexpected bytes after Monster container")
    entries = list(struct.iter_unpack("<II", arrays[0]))
    overrides = list(struct.iter_unpack("<III", arrays[1]))
    packed = arrays[2]
    offsets = [row[1] for row in entries] + [row[2] for row in overrides]
    if (not packed or not offsets or min(offsets) != 0 or
            any(offset >= len(packed) for offset in offsets) or
            len(set(offsets)) != len(offsets)):
        raise ValueError("Monster source indices do not define distinct bounded roots")
    if len({row[0] for row in entries}) != len(entries) or len({row[:2] for row in overrides}) != len(overrides):
        raise ValueError("Duplicate Monster index key")
    return packed_hash, entries, overrides, packed


def pack_container(packed_hash, entries, overrides, packed):
    return (struct.pack("<III", 0, packed_hash, len(entries)) +
            b"".join(struct.pack("<II", *row) for row in entries) +
            struct.pack("<I", len(overrides)) +
            b"".join(struct.pack("<III", *row) for row in overrides) +
            struct.pack("<I", len(packed)) + packed)


def attack_pattern_union_evidence(source):
    """Resolve actual native switch cases through GetFormatterWithVerify<T>.

    These are original/source polymorphic type identities, not guessed numeric
    tag equivalence. The field projection below is permitted only for the same
    concrete TargetLockedAnimatedColliderDetect type.
    """
    result = []
    for original in (True, False):
        binary, metadata = (native.E, native.B) if original else (source.binary, source.metadata)
        base, table, usage_pair, spec_pair, inst_pair = (
            (0x33e39d8, 0x33e39d8 - 0x8e5f18, 0x34a67e4, 0x34a67cc, 0x34a67b4) if original else
            (0x42531e4, 0x42531e4 - 0xc43d18, 0x4252108, 0x42520f0, 0x42520d8))
        header = struct.unpack_from("<64I", metadata)
        count, pointers = struct.unpack_from("<II", binary, usage_pair)
        destinations = {struct.unpack_from("<I", binary, pointers + i * 4)[0]: i for i in range(count)}
        usage_pairs = dict(struct.iter_unpack("<II", metadata[header[50]:header[50] + header[51]]))
        usage = {address: usage_pairs[index] for address, index in destinations.items() if index in usage_pairs}
        for tag in ACTUAL_ATTACK_PATTERN_TAGS:
            branch = base + struct.unpack_from("<i", binary, table + (tag - 1) * 4)[0]
            instruction = next((ins for ins in native.MD.disasm(binary[branch:branch + 70], branch)
                                if ins.mnemonic == ("mov" if original else "lea") and
                                re.fullmatch(r"eax, (dword ptr )?\[ebx [+-] 0x[0-9a-f]+\]", ins.op_str)), None)
            if instruction is None:
                raise ValueError("Actual AttackPattern switch case changed")
            match = re.search(r"\[ebx ([+-]) (0x[0-9a-f]+)\]", instruction.op_str)
            address = base + (1 if match[1] == "+" else -1) * int(match[2], 16)
            address = struct.unpack_from("<I", binary, address)[0] if original else address
            token = usage.get(address)
            if token is None or token >> 29 != 6:
                raise ValueError("Actual AttackPattern branch lacks verified MethodRef")
            spec_count, specs = struct.unpack_from("<II", binary, spec_pair)
            spec_index = token & 0x1fffffff
            if spec_index >= spec_count:
                raise ValueError("AttackPattern MethodSpec outside registration")
            method, class_inst, method_inst = struct.unpack_from("<3i", binary, specs + spec_index * 12)
            method_data = native.M[method] if original else struct.unpack_from("<12I4H", metadata, header[12] + method * 56)
            method_name = native.string(method_data[0]) if original else source.string(method_data[0])
            if method_name != "GetFormatterWithVerify" or class_inst != -1 or method_inst < 0:
                raise ValueError("AttackPattern case is not a verified concrete formatter")
            inst_count, insts = struct.unpack_from("<II", binary, inst_pair)
            if method_inst >= inst_count:
                raise ValueError("AttackPattern generic instance outside registration")
            inst = struct.unpack_from("<I", binary, insts + method_inst * 4)[0]
            arg_count, args = struct.unpack_from("<II", binary, inst)
            if arg_count != 1:
                raise ValueError("AttackPattern formatter generic arguments changed")
            pointer = struct.unpack_from("<I", binary, args)[0]
            index, flags = struct.unpack_from("<II", binary, pointer)
            if flags >> 16 & 255 not in (17, 18):
                raise ValueError("AttackPattern generic argument is not a class")
            concrete = native.type_name(index) if original else source.name(index)
            result.append({"original": original, "tag": tag, "concrete": concrete,
                           "switch_table": hex(table), "branch": hex(branch),
                           "method_spec_index": spec_index, "usage_address": hex(address),
                           "branch_first16_sha256": sha(binary[branch:branch + 16])})
    old = {row["tag"]: row["concrete"] for row in result if row["original"]}
    new = {row["tag"]: row["concrete"] for row in result if not row["original"]}
    if old != new or old[10] != TARGET_LOCKED_TYPE:
        raise ValueError("Preserve exact original/source AttackPattern concrete identity")
    return result


def schema_evidence(package, attack_pattern_compat=False):
    """Check declarations recursively; custom consumers have separate evidence."""
    source = SourceTypedDecoder(package)
    originals = {native.type_name(index): index for index in range(len(native.T))}

    def info(pointer, original):
        if original:
            return type_info(pointer)
        data, flags = struct.unpack_from("<II", source.binary, pointer)
        return {"data": data, "kind": (flags >> 16) & 0xff, "attributes": flags & 0xffff}

    def typename(index, original):
        return native.type_name(index) if original else source.name(index)

    def signature(pointer, original):
        data, kind = (info(pointer, original)[key] for key in ("data", "kind"))
        if kind in (0x11, 0x12):
            return typename(data, original)
        if kind == 0x1d:
            return signature(data, original) + "[]"
        if kind == 0x15:
            binary = native.E if original else source.binary
            definition, inst = struct.unpack_from("<II", binary, data)
            count, argv = struct.unpack_from("<II", binary, inst)
            return typename(definition, original) + "[" + ",".join(
                signature(struct.unpack_from("<I", binary, argv + index * 4)[0], original)
                for index in range(count)) + "]"
        return f"primitive:{kind:#x}"

    def parent(index, original):
        native_type = (native.T if original else source.types)[index][6]
        if native_type == 0xffffffff:
            return None
        pointer = (type_pointer(native_type) if original else
                   struct.unpack_from("<I", source.binary, 0x409d890 + native_type * 4)[0])
        value = info(pointer, original)
        return value["data"] if value["kind"] in (0x11, 0x12) else None

    def members(index, original):
        declared = fields(index) if original else source.fields(index)
        result = [(name, pointer) for name, pointer in declared if not info(pointer, original)["attributes"] & 0x80]
        ancestor = parent(index, original)
        return result + (members(ancestor, original) if ancestor is not None else [])

    checked, checks = set(), []

    def inspect_pointer(pointer):
        data, kind = (info(pointer, True)[key] for key in ("data", "kind"))
        if kind == 0x1d:
            inspect_pointer(data)
        elif kind == 0x15:
            definition, inst = struct.unpack_from("<II", native.E, data)
            count, argv = struct.unpack_from("<II", native.E, inst)
            for index in range(count):
                inspect_pointer(struct.unpack_from("<I", native.E, argv + index * 4)[0])
            inspect_class(native.type_name(definition))
        elif kind in (0x11, 0x12):
            inspect_class(native.type_name(data))

    def inspect_class(name):
        if not name.startswith("MoleMole.") or name in checked:
            return
        checked.add(name)
        if name not in originals or name not in source.names:
            raise ValueError("Monster declaration missing: " + name)
        old, new = members(originals[name], True), members(source.names[name], False)
        excluded = []
        if name in (ROOT_TYPE, "MoleMole.Config.ConfigAnimatorEntity"):
            if not new or new[-1][0] != "ApplyRootMotionAnimationList":
                raise ValueError("Unexpected Monster inherited field layout")
            excluded, new = [new[-1][0]], new[:-1]
        elif name == SKILL_TYPE:
            if (len(old) != 16 or len(new) != 17 or new[-1][0] != "ApplyBuiltinRootMotion" or
                    signature(new[-1][1], False) != "primitive:0x2"):
                raise ValueError("Unexpected original/source MonsterSkill layout")
            excluded, new = [new[-1][0]], new[:-1]
        elif name == TARGET_LOCKED_TYPE and attack_pattern_compat:
            if (len(old) != 13 or len(new) != 14 or new[12][0] != "FollowOwnerTimeScale" or
                    signature(new[12][1], False) != "primitive:0x2" or old[-1][0] != "Scale"):
                raise ValueError("Unaudited TargetLocked attack-pattern layout")
            excluded, new = [new[12][0]], new[:12] + new[13:]
        if [(name, signature(pointer, True)) for name, pointer in old] != [(name, signature(pointer, False)) for name, pointer in new]:
            raise ValueError("Monster retained declaration differs: " + name)
        if name == ROOT_TYPE and [name for name, _ in old] != ROOT_FIELDS:
            raise ValueError("Monster logical root order changed")
        checks.append({"type": name, "fields": [name for name, _ in old],
                       "field_type_signatures": [signature(pointer, True) for _, pointer in old],
                       "excluded_source_fields": excluded,
                       "retained_declarations_equal": True})
        for _, pointer in old:
            inspect_pointer(pointer)
        ancestor = parent(originals[name], True)
        if ancestor is not None:
            inspect_class(native.type_name(ancestor))

    inspect_class(ROOT_TYPE)
    pattern_tags = attack_pattern_union_evidence(source) if attack_pattern_compat else []
    if attack_pattern_compat:
        for row in pattern_tags:
            inspect_class(row["concrete"])
    methods = [(57583, 0x69eab5, "ConfigMonster consumes own16 + inherited3; no tail skip"),
               (57607, 0x6a0044, "ConfigMonsterSkill consumes16; final UseAnimatorAngularVelocity at6a0c7e"),
               (60660, 0x1560d27, "Dynamic map key,type,value; types1..4 = bool,single,int,string"),
               (57603, 0x69e16c, "EliteArguments array10"),
               (57587, 0x69acff, "AIArguments array3"),
               (57615, 0x6a2c80, "MPArguments array15")]
    evidence = []
    for index, address, behavior in methods:
        if native.pointer(native.M[index]) != address:
            raise ValueError("Original native Monster formatter address changed")
        evidence.append({"method_index": index, "name": native.N[index], "address": hex(address),
                         "first64_sha256": sha(native.E[address:address + 64]), "audited_behavior": behavior})
    table = struct.unpack_from("<4i", native.E, 0x2b0078c)
    if tuple(0x33e39d8 + value for value in table) != (0x1560f9c, 0x1560ffd, 0x156105b, 0x15610c8):
        raise ValueError("Original DynamicArguments type switch changed")
    header = struct.unpack_from("<64I", source.metadata)
    source_methods = []
    for index, expected in ((69133, 0x25b6fbb), (69157, 0x25b8727)):
        method = struct.unpack_from("<12I4H", source.metadata, header[12] + index * 56)
        address = struct.unpack_from("<I", source.binary, 0x418f6e0 + method[6] * 4)[0]
        if address != expected:
            raise ValueError("Source Monster formatter address changed")
        source_methods.append({"method_index": index, "address": hex(address),
                               "first64_sha256": sha(source.binary[address:address + 64])})
    result = {"original_formatter_evidence": evidence, "source_formatter_evidence": source_methods,
            "source_native_sha256": sha(source.binary), "source_metadata_sha256": sha(source.metadata),
            "nested_declarations": checks,
            "custom_dynamic_mapping": {"method": 60660, "jump_table": "0x2b0078c",
                                       "tokens_per_entry": 3, "types": {"1": "Boolean", "2": "Single", "3": "Int32", "4": "StringMap"}},
            "declaration_scope": "Recursive declarations; equality does not prove all custom or polymorphic runtime payload semantics"}
    if attack_pattern_compat:
        if native.pointer(native.M[58667]) != 0x75a4ab or native.E[0x75adc5] != 0xc3:
            raise ValueError("Original TargetLocked fixed13 consumer changed")
        source_method = struct.unpack_from("<12I4H", source.metadata, header[12] + 70425 * 56)
        if struct.unpack_from("<I", source.binary, 0x418f6e0 + source_method[6] * 4)[0] != 0x24183f1:
            raise ValueError("Source TargetLocked formatter changed")
        result["attack_pattern_compatibility"] = {
            "same_concrete_union_evidence": pattern_tags,
            "original_consumer": "58667@75a4ab fixed13; final Scale ReadSingle@75ad96; bytecount@75adb4 and ret@75adc5, no extra-field skip",
            "original_consumer_sha256": sha(native.E[0x75a4ab:0x75adc6]),
            "source_consumer": "70425@24183f1: extra FollowOwnerTimeScale ReadBoolean@2418ccf then inherited Scale ReadSingle@2418d66; ret@2418d95",
            "source_consumer_sha256": sha(source.binary[0x24183f1:0x2418d96]),
            "policy": "Only delete actual nil new FollowOwnerTimeScale; preserve Scale, pattern tag and all original fields. Unknown nonnil extension is rejected."}
    return result


def anim_event_pattern_projection(packed, root, strings, original=False):
    """Locate the proven nil extension through the actual Monster event shape."""
    events, overrides = root["children"][9], root["children"][14]
    if events["kind"] != "map" or overrides["kind"] != "map":
        raise ValueError("Unaudited Monster event/override shape")
    # AnimEventOverrides is an unchanged StringMap-to-StringMap declaration.
    # Validate actual aliases and retain their bytes; they are not event bodies.
    for source, target in zip(overrides['children'][::2], overrides['children'][1::2]):
        string_index(packed, source, strings)
        string_index(packed, target, strings)
    edits, records, camera_refs = [], [], []
    expected_counts = {1: 14, 2: 4, 4: 11, 5: 12, 6: 4, 7: 5, 8: 6, 9: 10, 10: 13 if original else 14}
    for key, event in zip(events["children"][::2], events["children"][1::2]):
        event_name = string_index(packed, key, strings)
        if event["kind"] != "array" or event["count"] != 12:
            raise ValueError("Actual MonsterAnimEvent must preserve own2 + base10")
        camera = event["children"][6]
        if camera["code"] != 0xc0:
            camera_index = decode_integer(packed, camera)
            if not 0 <= camera_index < 563:
                raise ValueError("Actual Monster CameraShake index outside accepted563 dependency")
            camera_refs.append({"event": event_name, "index": camera_index,
                                "byte_span": [camera["start"], camera["end"]],
                                "encoded_hex": packed[camera["start"]:camera["end"]].hex()})
        union = event["children"][4]
        if union["code"] == 0xc0:
            continue
        if union["kind"] != "array" or union["count"] != 2:
            raise ValueError("Actual Monster AttackPattern must preserve its two-token union")
        tag_node, pattern = union["children"]
        tag = decode_integer(packed, tag_node)
        if tag not in expected_counts or pattern["kind"] != "array" or pattern["count"] != expected_counts[tag]:
            raise ValueError("Unaudited AttackPattern concrete tag/field shape")
        if tag != 10:
            continue
        fields = pattern["children"]
        if original:
            retained = fields
        else:
            extra = fields[12]
            if extra["code"] != 0xc0 or packed[extra["start"]:extra["end"]] != b"\xc0":
                raise ValueError("Refuse nonnil later TargetLocked FollowOwnerTimeScale")
            edits.extend([(pattern["start"], fields[0]["start"], b"\x9d"),
                          (extra["start"], extra["end"], b"")])
            retained = fields[:12] + fields[13:]
        record = {"event": event_name, "concrete_type": TARGET_LOCKED_TYPE,
                  "source_and_original_tag": 10, "pattern_byte_span": [pattern["start"], pattern["end"]],
                  "retained13_field_sha256": [sha(packed[node["start"]:node["end"]]) for node in retained],
                  "AttackProperty_hex": packed[event["children"][5]["start"]:event["children"][5]["end"]].hex(),
                  "CameraShake_hex": packed[camera["start"]:camera["end"]].hex(),
                  "Scale_hex": packed[retained[-1]["start"]:retained[-1]["end"]].hex()}
        if not original:
            record.update(excluded_field="FollowOwnerTimeScale", excluded_source_field_index=12,
                          excluded_byte_span=[extra["start"], extra["end"]], excluded_hex="c0",
                          header_before=packed[pattern["start"]:fields[0]["start"]].hex(), header_after="9d",
                          source_field_count=14, original_field_count=13)
        records.append(record)
    return edits, records, camera_refs


def project_root(packed, start, end, strings, attack_pattern_compat=False):
    reader = MonsterReader(packed)
    reader.pos = start
    root = reader.root(strings, 20)
    if reader.pos != end:
        raise ValueError("Selected Monster logical root does not end at its next index")
    nodes = root["children"]
    for index, expected in ((0, 27), (3, 10), (18, 15)):
        if nodes[index]["kind"] != "array" or nodes[index]["count"] != expected:
            raise ValueError("Selected Monster native argument field count differs")
    if nodes[4]["code"] != 0xc0 and (nodes[4]["kind"] != "array" or nodes[4]["count"] != 3):
        raise ValueError("Selected Monster AIArguments shape differs")
    tail = nodes[19]
    if tail["kind"] != "array" or tail["count"] != 0:
        raise ValueError("Unaccepted nonempty Monster ApplyRootMotionAnimationList")
    skills = nodes[7]
    if skills["kind"] != "map":
        raise ValueError("Selected Monster Skills must retain the actual source map")
    edits = [(root["start"], root["header_end"], b"\xdc\x00\x13"),
             (tail["start"], tail["end"], b"")]
    event_records, camera_refs = [], []
    if attack_pattern_compat:
        event_edits, event_records, camera_refs = anim_event_pattern_projection(packed, root, strings)
        edits.extend(event_edits)
    skill_records, keys = [], set()
    for key, node in zip(skills["children"][::2], skills["children"][1::2]):
        name = string_index(packed, key, strings)
        if name in keys or node["kind"] != "array" or node["count"] != 17:
            raise ValueError("Selected Monster skill name/layout changed")
        keys.add(name)
        first, excluded = node["children"][0], node["children"][-1]
        # The source declaration is Boolean, but all189 audited source skill
        # tails use nil. Accept only those actual pinned bytes; do not infer
        # nullable semantics or support uninspected later encodings.
        if excluded["code"] != 0xc0:
            raise ValueError("New MonsterSkill tail differs from audited source nil")
        edits.extend([(node["start"], first["start"], b"\xdc\x00\x10"),
                      (excluded["start"], excluded["end"], b"")])
        skill_records.append({"name": name, "source_byte_span": [node["start"], node["end"]],
                              "source_sha256": sha(packed[node["start"]:node["end"]]),
                              "retained16_byte_span": [first["start"], excluded["start"]],
                              "retained16_sha256": sha(packed[first["start"]:excluded["start"]]),
                              "excluded_field": "ApplyBuiltinRootMotion",
                              "excluded_byte_span": [excluded["start"], excluded["end"]],
                              "excluded_hex": packed[excluded["start"]:excluded["end"]].hex()})
    edits.sort()
    output, cursor = bytearray(), start
    for left, right, replacement in edits:
        if left < cursor or right > end or left >= right:
            raise ValueError("Overlapping or unbounded Monster edits")
        output.extend(packed[cursor:left])
        output.extend(replacement)
        cursor = right
    output.extend(packed[cursor:end])
    verify = MonsterReader(bytes(output))
    projected = verify.root(strings, 19)
    if verify.pos != len(output):
        raise ValueError("Projected Monster root boundary does not match original consumer")
    maps = []
    for index, (old, new) in enumerate(zip(nodes[:19], projected["children"])):
        old_raw = packed[old["start"]:old["end"]]
        new_raw = bytes(output[new["start"]:new["end"]])
        changed_fields = {7, 9} if event_records else {7}
        if index not in changed_fields and old_raw != new_raw:
            raise ValueError("A retained Monster field changed")
        maps.append({"field": ROOT_FIELDS[index], "source_byte_span": [old["start"], old["end"]],
                     "output_relative_byte_span": [new["start"], new["end"]],
                     "source_sha256": sha(old_raw), "output_sha256": sha(new_raw),
                     "byte_identical": index not in changed_fields})
    out_skills = projected["children"][7]
    if skills["count"] != out_skills["count"]:
        raise ValueError("Monster skill count changed")
    for source_key, source_skill, output_key, output_skill, record in zip(
            skills["children"][::2], skills["children"][1::2],
            out_skills["children"][::2], out_skills["children"][1::2], skill_records):
        if (packed[source_key["start"]:source_key["end"]] != output[output_key["start"]:output_key["end"]] or
                output_skill["kind"] != "array" or output_skill["count"] != 16):
            raise ValueError("Projected Monster skill key/field count changed")
        first, last = output_skill["children"][0], output_skill["children"][-1]
        retained = output[first["start"]:last["end"]]
        if sha(retained) != record["retained16_sha256"]:
            raise ValueError("Retained Monster skill value changed")
        record.update(output_relative_byte_span=[output_skill["start"], output_skill["end"]],
                      output_sha256=sha(output[output_skill["start"]:output_skill["end"]]),
                      retained16_byte_identical=True)
    record = {"source_byte_span": [start, end], "source_sha256": sha(packed[start:end]),
                           "output_sha256": sha(output), "logical_fields": "20 -> original19",
                           "mapping": maps, "skills": skill_records,
                           "dynamic_arguments": nodes[2].get("custom_items", []),
                           "excluded_field": "ApplyRootMotionAnimationList",
                           "excluded_byte_span": [tail["start"], tail["end"]],
                           "excluded_hex": packed[tail["start"]:tail["end"]].hex()}
    if attack_pattern_compat:
        _, output_events, output_cameras = anim_event_pattern_projection(bytes(output), projected, strings, True)
        if len(event_records) != len(output_events) or len(camera_refs) != len(output_cameras):
            raise ValueError("Projected Monster event/reference count changed")
        for source_event, target_event in zip(event_records, output_events):
            for key in ("event", "concrete_type", "source_and_original_tag", "retained13_field_sha256",
                        "AttackProperty_hex", "CameraShake_hex", "Scale_hex"):
                if source_event[key] != target_event[key]:
                    raise ValueError("Original TargetLocked field/next-event consumer value changed")
            source_event.update(output_relative_pattern_byte_span=target_event["pattern_byte_span"],
                                retained13_fields_byte_identical=True)
        if [(row["event"], row["index"], row["encoded_hex"]) for row in camera_refs] != [
                (row["event"], row["index"], row["encoded_hex"]) for row in output_cameras]:
            raise ValueError("Actual Monster CameraShake references changed")
        record.update(attack_pattern_projection=event_records, camera_shake_references=camera_refs)
    return bytes(output), record


def project_container(payload, strings, extra_primary=None, attack_pattern_compat=False):
    extra_primary = extra_primary or {}
    if sha(payload) != SOURCE_CONTAINER_SHA or sha("\x1f".join(strings).encode("utf-8")) != STRINGMAP_SHA:
        raise ValueError("Monster projection accepts only the audited exact source container/string map")
    packed_hash, entries, overrides, packed = unpack_container(payload)
    references = {row[1]: (row[0], None) for row in entries}
    references.update({row[2]: row[:2] for row in overrides})
    for key, variant in references.values():
        if not 0 <= key < len(strings) or (variant is not None and not 0 <= variant < len(strings)):
            raise ValueError("Monster index references an absent string")
    counts = Counter(key for key, _ in references.values() if key in SELECTED)
    if any(strings[key] != name or counts[key] != expected for key, (name, _, expected) in SELECTED.items()):
        raise ValueError("Selected Monster source identity or family size changed")
    offsets, output, audits = {}, bytearray(), []
    boundaries = sorted(references) + [len(packed)]
    unchanged = hashlib.sha256()
    for start, end in zip(boundaries, boundaries[1:]):
        key, variant = references[start]
        offsets[start] = len(output)
        selected = key in SELECTED or (variant is None and key in extra_primary)
        if selected:
            value, record = project_root(packed, start, end, strings, attack_pattern_compat)
            record.update(key=key, config=strings[key], monster=(SELECTED if key in SELECTED else extra_primary)[key][1],
                          variant_index=variant, variant=None if variant is None else strings[variant],
                          output_byte_span=[len(output), len(output) + len(value)])
            audits.append(record)
        else:
            value = packed[start:end]
            unchanged.update(value)
        output.extend(value)
    new_entries = [(key, offsets[offset]) for key, offset in entries]
    new_overrides = [(key, variant, offsets[offset]) for key, variant, offset in overrides]
    result = pack_container(packed_hash, new_entries, new_overrides, bytes(output))
    _, check_entries, check_overrides, check_packed = unpack_container(result)
    if [row[0] for row in check_entries] != [row[0] for row in entries] or [row[:2] for row in check_overrides] != [row[:2] for row in overrides]:
        raise ValueError("Monster index order/key changed")
    out_boundaries = sorted(offsets.values()) + [len(check_packed)]
    unchanged_check = hashlib.sha256()
    for source_start, left, right in zip(boundaries[:-1], out_boundaries, out_boundaries[1:]):
        identity = references[source_start]
        if identity[0] not in SELECTED and not (identity[1] is None and identity[0] in extra_primary):
            original = packed[source_start:boundaries[boundaries.index(source_start) + 1]]
            if original != check_packed[left:right]:
                raise ValueError("Unselected Monster source payload changed")
            unchanged_check.update(check_packed[left:right])
        else:
            check = MonsterReader(check_packed)
            check.pos = left
            check.root(strings, 19)
            if check.pos != right:
                raise ValueError("Reindexed selected Monster logical boundary changed")
    if unchanged.digest() != unchanged_check.digest():
        raise ValueError("Unselected Monster aggregate preservation failed")
    return result, {"selected_root_count": len(audits), "selected_monsters": [value[1] for value in SELECTED.values()] + [value[1] for value in extra_primary.values()],
                    "source_counts": [len(entries), len(overrides), len(packed)],
                    "output_counts": [len(entries), len(overrides), len(output)], "roots": audits,
                    "unselected_roots": len(references) - len(audits),
                    "unselected_roots_byte_identical": True, "unselected_aggregate_sha256": unchanged.hexdigest(),
                    "all_indices_recomputed_and_keys_order_preserved": True,
                    "packed_hash": packed_hash,
                    "packed_hash_policy": "Preserve source identifier; original shared lookup ctor stores it without recalculation/comparison",
                    "HP_attack_defence_and_all_retained_values_byte_identical": True}


def load_sources(apk19, apk24, attack_pattern_compat=False):
    if file_sha(apk19) != ORIGINAL19_SHA or sha(native.E) != NATIVE19_SHA:
        raise ValueError("Original 1.9 APK/native baseline changed")
    if file_sha(apk24) != SOURCE24_SHA:
        raise ValueError("Unaccepted later reference APK")
    old = {row["path"]: row for row in resources.resource_map(apk19)}
    if PATH in old:
        raise ValueError("Original Monster resource exists; refuse to replace it with later data")
    source_paths = {row["path"]: row for row in resources.resource_map(apk24)}
    with zipfile.ZipFile(apk24) as package:
        record = source_paths[PATH]
        obj, raw = resources.object_bytes(package, record)
        if obj["class"] != 114 or sha(raw) != SOURCE_ASSET_SHA:
            raise ValueError("Unaccepted source Monster ScriptableObject")
        cursor = resources.Reader(raw, 28)
        name = cursor.string()
        arrays = []
        for element_size in (8, 12, 1):
            count = cursor.read("I")
            size = count * element_size
            if cursor.pos + size > len(raw):
                raise ValueError("Source Monster array exceeds its Unity object")
            arrays.append((count, raw[cursor.pos:cursor.pos + size]))
            cursor.pos += size
            cursor.align()
        packed_hash = cursor.read("I")
        if cursor.pos != len(raw) or name != "BakedMonsterData":
            raise ValueError("Source Monster object boundary/name changed")
        container = struct.pack("<II", 0, packed_hash) + b"".join(struct.pack("<I", count) + data for count, data in arrays)
        if sha(container) != SOURCE_CONTAINER_SHA:
            raise ValueError("Reconstructed Monster source container changed")
        string_rec = source_paths["_baked/stringmap"]
        string_obj, string_raw = resources.object_bytes(package, string_rec)
        if string_obj["class"] != 114:
            raise ValueError("Source string map is not a ScriptableObject")
        reader = resources.Reader(string_raw, 28)
        string_name = reader.string()
        count = reader.read("I")
        if count > len(string_raw) // 4:
            raise ValueError("Invalid source string-map count")
        strings = [reader.string() for _ in range(count)]
        string_hash = reader.read("I")
        if reader.pos != len(string_raw) or any("\x1f" in value for value in strings):
            raise ValueError("Source string-map boundary/delimiter changed")
        string_bytes = "\x1f".join(strings).encode("utf-8")
        if sha(string_bytes) != STRINGMAP_SHA:
            raise ValueError("Selected Monster needs the accepted source string map")
        evidence = schema_evidence(package, attack_pattern_compat)
    provenance = {**record, "name": name, "class": obj["class"], "source_object_bytes": len(raw),
                  "source_object_sha256": sha(raw), "source_container_sha256": sha(container),
                  "original19_resource_present": False,
                  "source_version": "2.4.0 later compatibility; not historical 1.9 data",
                  "stringmap_dependency": {**string_rec, "name": string_name, "class": string_obj["class"],
                                           "source_object_sha256": sha(string_raw), "packed_hash": string_hash,
                                           "required_existing_path": "_baked/stringmap.txt",
                                           "output_sha256": STRINGMAP_SHA, "count": len(strings)},
                  "native_schema_evidence": evidence}
    return container, strings, provenance


def build(apk19, apk24, profile="firststage"):
    if profile not in ("firststage", "act101_entry", "act101_entry_stage2"):
        raise ValueError("Unsupported bounded Monster profile")
    pattern_compat = profile == "act101_entry_stage2"
    source, strings, provenance = load_sources(apk19, apk24, pattern_compat)
    extra = ACT101_PRIMARY if profile in ("act101_entry", "act101_entry_stage2") else {}
    if any(strings[key] != value[0] for key, value in extra.items()):
        raise ValueError("Actual Normal monster config string identity changed")
    payload, projection = project_container(source, strings, extra, pattern_compat)
    manifest = {"format": "server19-stage10101-monster-tail-projection-v1", "stage_id": 10101,
                "source19": {"path": str(apk19.resolve()), "sha256": ORIGINAL19_SHA},
                "source24": {"path": str(apk24.resolve()), "sha256": SOURCE24_SHA},
                "deployment_files": [PATH], "files": [{**provenance, "path": PATH,
                    "bytes": len(payload), "output_sha256": sha(payload),
                    "reference_path": "reference/" + PATH, "projection": projection}],
                "limits": ["Only DeadWalker/UlyssesWarrior and their source variants are projected; other287 roots remain source exact",
                           "This supplies later compatibility data, not recovered historical1.9 Monster balance/configuration",
                           "Only root ApplyRootMotionAnimationList and skill ApplyBuiltinRootMotion tail fields are deleted",
                           "Every retained value including HP/attack/defence keeps its exact source encoded bytes",
                           "DynamicArguments custom key/type/value map is read using the original consumer; its bytes stay exact",
                           "Recursive declarations and selected logical boundaries are checked; runtime/custom/poly behavior still needs actual play",
                           "The matching existing string map is required and is not deployed by this helper",
                           "No device/library/service/account/stamina/progress operations by this helper"]}
    if profile in ("act101_entry", "act101_entry_stage2"):
        from server19_stage_resources import ACT101_OUTPUT as LUA_OUTPUT
        lua_manifest = json.loads((LUA_OUTPUT / "manifest.json").read_bytes())
        actual = {(row["monsterName"], row["configFile"], row["configType"]) for stage in lua_manifest["stage_evidence"] for row in stage["native_basic_monster_rows"]}
        if actual != {(name, config, "Default") for config, name in [value[:2] for value in SELECTED.values()] + list(extra.values())}:
            raise ValueError("Project only the four actual Normal monster configs")
        manifest["format"] = "server19-act101-normal-and-act102-entry-monster-projection-v1"
        manifest["profile"] = profile
        manifest["stage_ids"] = list(range(10101, 10107))
        manifest["actual_normal_monster_config_refs"] = [list(row) for row in sorted(actual)]
        manifest["lua_manifest_sha256"] = file_sha(LUA_OUTPUT / "manifest.json")
        manifest["limits"][0] = "Retain all previous29 projected roots; add only DeadArcher/UlyssesFast default primary roots used by Normal10101–10106"
    if pattern_compat:
        changes = [(row["key"], row["variant_index"], event) for row in projection["roots"]
                   for event in row["attack_pattern_projection"]]
        if len(changes) != 1 or changes[0][:2] != (8522, None) or changes[0][2]["event"] != "ATK03":
            raise ValueError("Project only the single actual DG020 primary ATK03 extension")
        previous = (ACT101_OUTPUT / PATH).read_bytes()
        if sha(previous) != "6608058b07fc8229daab5355b1ea59a841ee5f802d13aa81d3d889f01fa38b51":
            raise ValueError("Preserve the previously accepted Act101 Monster artifact")
        _, prior_entries, prior_overrides, prior_packed = unpack_container(previous)
        _, next_entries, next_overrides, next_packed = unpack_container(payload)
        identities = [(key, None) for key, _ in prior_entries] + [(key, variant) for key, variant, _ in prior_overrides]
        prior_offsets = [offset for _, offset in prior_entries] + [offset for _, _, offset in prior_overrides]
        next_offsets = [offset for _, offset in next_entries] + [offset for _, _, offset in next_overrides]
        prior_ends = dict(zip(sorted(prior_offsets), sorted(prior_offsets)[1:] + [len(prior_packed)]))
        next_ends = dict(zip(sorted(next_offsets), sorted(next_offsets)[1:] + [len(next_packed)]))
        changed = [identity for identity, old, new in zip(identities, prior_offsets, next_offsets)
                   if prior_packed[old:prior_ends[old]] != next_packed[new:next_ends[new]]]
        if changed != [(8522, None)] or len(payload) != len(previous) - 1:
            raise ValueError("Only DG020 primary may change by the proven one-byte deletion")
        camera_path = "_baked/bakedconfigentitycamerashake"
        camera_payload = (ROOT / ".local-baseline/server19-dev/baked-fallback" / camera_path).read_bytes()
        if sha(camera_payload) != "3e692765ff4d5fda680835b6fdb9fedce79fedd423001e33c4f07db5142e7534":
            raise ValueError("Accepted indexed CameraShake dependency changed")
        indexed, camera_hash, camera_count = struct.unpack_from("<III", camera_payload)
        if indexed != 1 or camera_count != 563:
            raise ValueError("Actual CameraShake dependency index count changed")
        camera_offsets = struct.unpack_from("<563I", camera_payload, 12)
        packed_count = struct.unpack_from("<I", camera_payload, 12 + 563 * 4)[0]
        camera_packed = camera_payload[16 + 563 * 4:]
        if len(camera_packed) != packed_count:
            raise ValueError("CameraShake dependency packed boundary changed")
        # Indexed entries0/1 intentionally share packed offset0. Validate real
        # root boundaries instead of requiring a fictitious unique index map.
        boundary_reader = MessagePackSpanReader(camera_packed)
        camera_ends = {}
        while boundary_reader.pos < len(camera_packed):
            node = boundary_reader.node()
            camera_ends[node["start"]] = node["end"]
        if boundary_reader.pos != len(camera_packed) or any(offset not in camera_ends for offset in camera_offsets):
            raise ValueError("CameraShake dependency offset does not name a complete root")
        indices = sorted({item["index"] for row in projection["roots"] for item in row["camera_shake_references"]})
        dependencies = []
        for index in indices:
            left = camera_offsets[index]
            right = camera_ends[left]
            reader = MessagePackSpanReader(camera_packed)
            reader.pos = left
            node = reader.node()
            if node["kind"] != "array" or node["count"] != 6 or reader.pos != right:
                raise ValueError("Actual Monster CameraShake index must point to an exact six-field root")
            dependencies.append({"index": index, "packed_byte_span": [left, right],
                                 "sha256": sha(camera_packed[left:right])})
        manifest["format"] = "server19-act101-entry-monster-attack-pattern-projection-v2"
        manifest["files"][0]["required_existing_output_sha256"] = sha(previous)
        manifest["files"][0]["indexed_dependencies"] = [{"required_existing_path": camera_path,
            "output_sha256": sha(camera_payload), "bytes": len(camera_payload), "indexed_count": 563,
            "packed_hash": camera_hash, "actual_referenced_roots": dependencies,
            "policy": "Existing exact resource required; no CameraShake/index replacement or deployment"}]
        manifest["comparison_to_accepted_act101_v1"] = {
            "previous_output_sha256": sha(previous), "changed_identity": [8522, None],
            "other315_roots_byte_identical": True, "old29_projected_roots_byte_identical": True,
            "bytes_delta": -1, "all_offset_indices_recomputed": True}
        manifest["first_range_provenance"] = {
            "pid": 15313, "timestamp": "2026-10-11 20:37:45.495 Asia/Shanghai",
            "log": "server19-run/diagnostics/chain-fix-20261011-202519/live-logcat-15313.log",
            "sources": ["019a6ec2", "01b37630", "01b3df4f", "0096d7d2", "0069b935", "015f675d", "0069f5c2", "026849f7"],
            "consumer": "List<int>.get_Item -> indexed offset lookup -> CustomCameraShake60696 -> MonsterAnimEvent57591 -> Monster57583",
            "source_root": "DG_020_Config primary / AnimEvents.ATK03.TargetLockedAnimatedColliderDetect",
            "causal_bytes": "Source14 includes nil FollowOwnerTimeScale at12 before nil Scale13. Original fixed13 consumes extension as Scale; leftover Scale nil becomes AttackProperty; true AttackProperty808 becomes CameraShake index808 >= accepted563. Projection removes only the added nil and14->13.",
            "status": "Static source-consumer causality matches real trace; new payload runtime acceptance pending"}
        manifest["limits"][2] = "Delete existing proven tail extensions plus the single nil later DG020 TargetLocked FollowOwnerTimeScale; preserve all original functionality/values"
    return source, payload, manifest


def prepare(apk19, apk24, output, profile="firststage"):
    source, payload, manifest = build(apk19, apk24, profile)
    targets = {PATH: payload, "reference/" + PATH: source,
               "manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")}
    # Check all destinations before the first write; changed outputs are kept.
    for path, data in targets.items():
        target = output / path
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError("Preserve existing changed output: " + str(target))
    for path, data in targets.items():
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    return {"status": "explicit_monster_tail_projection_exported", "selected_roots": manifest["files"][0]["projection"]["selected_root_count"],
            "output": str(output.resolve()), "deployment_files": [PATH],
            "output_sha256": sha(payload), "manifest_sha256": file_sha(output / "manifest.json"),
            "runtime_compatibility": "unaccepted"}


def audit(apk19, apk24, output, profile="firststage"):
    source, payload, expected = build(apk19, apk24, profile)
    actual = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if actual != expected or (output / PATH).read_bytes() != payload or (output / "reference" / PATH).read_bytes() != source:
        raise ValueError("Monster export provenance or bytes changed")
    return {"status": "source_projection_and_retained_bytes_verified", "selected_roots": expected["files"][0]["projection"]["selected_root_count"],
            "output_sha256": sha(payload), "manifest_sha256": file_sha(output / "manifest.json"),
            "runtime_compatibility": "unaccepted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "audit"))
    parser.add_argument("--apk19", type=Path, default=resources.DEFAULT19)
    parser.add_argument("--apk24", type=Path, default=resources.DEFAULT24)
    parser.add_argument("--profile", choices=("firststage", "act101_entry", "act101_entry_stage2"), default="firststage")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (STAGE2_OUTPUT if args.profile == "act101_entry_stage2" else
                             ACT101_OUTPUT if args.profile == "act101_entry" else DEFAULT_OUTPUT)
    result = (prepare if args.command == "prepare" else audit)(args.apk19, args.apk24, output, args.profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
