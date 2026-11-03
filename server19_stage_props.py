"""Project verified 2.4 PropArguments onto the original 1.9 baked reader.

The arguments_only profile keeps all 421 roots' eight outer fields, removes
seven proven newer PropArguments fields, and preserves every retained token.
The independent act101_native_props profile additionally corrects only the
verified AdvancedBox/GeneralBox PrefabPath nodes and pairs them with two appended
StringMap entries; every earlier string and index remains byte exact. This does
not recover historical 1.9 data or implement removed 2.4-only features. No device,
service, account, APK, or earlier resource export is changed by this helper.
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
from server19_metadata_export import PackageObjects, SourceTypedDecoder, fields, type_info
import server19_resources as resources
from server19_stage_monsters import decode_integer, pack_container, unpack_container

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / ".local-baseline/server19-dev/prop-compat-resources"
NATIVE_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-native-prop-resources"
PATH = "_baked/bakedpropdata"
ROOT_TYPE = "MoleMole.Config.ConfigPropObject"
ARGS_TYPE = "MoleMole.Config.ConfigPropArguments"
ORIGINAL19_SHA = "672c3eadd1300accb265f09dfce52f05965b15e4b1a8d54114913f3f4f87d5be"
SOURCE24_SHA = "41b0dfa3ed7ffb07cee808acab3691c7ada5f28361023b0c88f3b2aa2a2af042"
NATIVE19_SHA = "dc8365244e56a9de670b326d40510cab688d6876107e6a9151372917963ada7d"
SOURCE_NATIVE_SHA = "ce219cb782f558f8db984f1653af98f60fa4c2e592d202ab676ed506916d003f"
SOURCE_METADATA_SHA = "3cfa77b4bcba2421c67c4f02139e7b33fbd794667a1334266b735011203f4f9c"
SOURCE_ASSET_SHA = "96ddfdb8293ec07eec009aa11d721276fb3b0c8f7036fb355d5e96d924afb6d2"
SOURCE_CONTAINER_SHA = "82b6189b92368e407a246b133eb82f88806d447c86be64c9857062e0198c65f3"
STRINGMAP_SHA = "03813a7f76d611631768bf0dc9dfab685d0213d81af0f6ccdfdc09ae81d22405"
ROOT_FIELDS = ["Name", "PrefabPath", "CommonArguments", "PropArguments",
               "BeHitEffect", "Abilities", "AnimEvents", "MPArguments"]
OLD_FIELDS = ["EagleEyeMode", "IsTargetable", "IsTriggerField", "OnlyReduceHPByOne",
              "HP", "Attack", "UseOwnerAttack", "UseOwnerAttackProperty", "EffectDuration",
              "CD", "Length", "TriggerHitWhenFieldEnter", "AnimEventIDForHit", "Acceleration",
              "MaxMoveSpeed", "WarningRange", "EscapeRange", "DieWhenFieldEnter",
              "OnKillEffectPattern", "OnDestroyEffectPattern", "RetreatType", "Duration",
              "DurationIgnoreLevelTimeScale", "SpeedIgnoreTimeScale", "CanAffectMonsters",
              "HideByOwnerInvisible", "HitableType", "DontAutoClear", "HasDieAnim",
              "UseHitboxLayerCollider", "AllowFullAnimCameraShake", "VisibleWhenSpecialState",
              "TagName", "ImmuneType", "MPOverrideRemoteMode"]
EXTRA_INDICES = {4: "Nature", 5: "UseOwnerNature", 10: "FollowOwnerTimeScale",
                 27: "CanAffectAvatars", 32: "CantKillInLevel", 37: "ShowStateus", 38: "DisplayName"}
NEW_FIELDS = []
_old = iter(OLD_FIELDS)
for _index in range(42):
    NEW_FIELDS.append(EXTRA_INDICES[_index] if _index in EXTRA_INDICES else next(_old))
KEEP_INDICES = [NEW_FIELDS.index(name) for name in OLD_FIELDS]
REMOVED_ALLOWED = {"Nature": ("c0",), "UseOwnerNature": ("c0", "c2"),
                   "FollowOwnerTimeScale": ("c0",), "CanAffectAvatars": ("c0", "c2"),
                   "CantKillInLevel": ("c0",), "ShowStateus": ("c0", "c3"),
                   "DisplayName": ("c0", "cd35fd")}
OLD_OFFSETS = [8,12,13,14,16,20,24,25,28,32,36,40,44,48,52,56,60,64,68,72,
               76,80,84,85,86,87,88,92,93,94,95,96,100,104,108]
NEW_OFFSETS = [8,12,13,14,15,16,20,24,28,29,30,32,36,40,44,48,52,56,60,64,
               68,72,76,80,84,88,89,90,91,92,96,100,101,102,103,104,105,106,
               108,112,116,120]
ARGUMENTS_ONLY_SHA = "07cf4e7802fb462de101212eab5cbf327042eb17e1a1b3e0d6dbedd8f7d62a12"
APPENDED_STRINGMAP_SHA = "297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1"
NATIVE_PREFABS = (
    {"key":2339,"name":"AdvancedBox","old_index":9700,"new_index":22416,
     "path":"entities/propobject/level1/advancedbox","file_id":5394,"path_id":3,
     "file":"04a06777a91dcdf4291141e06af716e0",
     "root_sha256":"daf450a65467d8ef8d8c5e51f7f74458f040973e6494e679de638c68c88b6192",
     "component_sha256":"3280524fc1b29138d6f5cfcaeb0f9ee6e6f84092c025f02ba09c609470b22846"},
    {"key":12099,"name":"GeneralBox","old_index":9748,"new_index":22417,
     "path":"entities/propobject/level1/generalbox","file_id":5401,"path_id":1,
     "file":"f5ce5060d50063a43a66da734e4537e4",
     "root_sha256":"06000503db5a5c9203e904859f2cb4647df5869daa1a46aaa85e427c43af47c2",
     "component_sha256":"1d56a4d38c7715314b7a6b9ec9e2f80b486627cb6c6f02146de963f1169dd0f5"},
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def check_field_mapping(old, new):
    """Reject new/changed declarations, including a changed retained type."""
    if [name for name, _ in old] != OLD_FIELDS or [name for name, _ in new] != NEW_FIELDS:
        raise ValueError("Unaudited PropArguments field names/order/count")
    if old != [new[index] for index in KEEP_INDICES]:
        raise ValueError("Unaudited retained PropArguments type mismatch")


def schema_evidence(package):
    source = SourceTypedDecoder(package)
    if sha(native.E) != NATIVE19_SHA or sha(source.binary) != SOURCE_NATIVE_SHA or sha(source.metadata) != SOURCE_METADATA_SHA:
        raise ValueError("Unaudited original/source native metadata")
    originals = {native.type_name(index): index for index in range(len(native.T))}

    def info(pointer, original):
        if original:
            return type_info(pointer)
        data, flags = struct.unpack_from("<II", source.binary, pointer)
        return {"data": data, "kind": flags >> 16 & 255, "attributes": flags & 65535}

    def signature(pointer, original):
        value = info(pointer, original)
        data, kind = value["data"], value["kind"]
        if kind in (0x11, 0x12):
            return native.type_name(data) if original else source.name(data)
        if kind == 0x1d:
            return signature(data, original) + "[]"
        if kind == 0x15:
            binary = native.E if original else source.binary
            definition, inst = struct.unpack_from("<II", binary, data)
            count, argv = struct.unpack_from("<II", binary, inst)
            name = native.type_name(definition) if original else source.name(definition)
            return name + "[" + ",".join(signature(struct.unpack_from("<I", binary, argv + index * 4)[0], original)
                                         for index in range(count)) + "]"
        return f"primitive:{kind:#x}"

    def members(name, original, serialized=False):
        declared = fields(originals[name]) if original else source.fields(source.names[name])
        return [(field, signature(pointer, original)) for field, pointer in declared
                if not serialized or not info(pointer, original)["attributes"] & 0x80]

    old, new = members(ARGS_TYPE, True), members(ARGS_TYPE, False)
    check_field_mapping(old, new)
    old_root, new_root = members(ROOT_TYPE, True, True), members(ROOT_TYPE, False, True)
    if old_root != new_root or [name for name, _ in old_root] != ROOT_FIELDS:
        raise ValueError("Unaudited baked Prop root fields/types")

    # Verify actual generated consumers, not just metadata declaration order.
    # Every non-nil setter occurs once in this order; nil branches advance one
    # token and keep constructor defaults. The final Nullable value is qword.
    consumers = []
    for original, method, start, end, expected_offsets, names in (
        (True,57651,0x6a9093,0x6aab64,OLD_OFFSETS,OLD_FIELDS),
        (False,69201,0x25c168e,0x25c3601,NEW_OFFSETS,NEW_FIELDS),
        (True,57655,0x6abe6f,0x6ac7cd,[8,12,16,20,24,28,32,40],ROOT_FIELDS),
        (False,69205,0x25c4916,0x25c52ac,[8,12,16,20,24,28,32,40],ROOT_FIELDS),
    ):
        binary = native.E if original else source.binary
        if original:
            address = native.pointer(native.M[method])
        else:
            header = struct.unpack_from("<64I", source.metadata)
            row = struct.unpack_from("<12I4H", source.metadata, header[12] + method * 56)
            address = struct.unpack_from("<I", binary, 0x418f6e0 + row[6] * 4)[0]
        if address != start or binary[end - 1] != 0xc3:
            raise ValueError("Prop generated consumer boundary changed")
        setters = []
        for instruction in native.MD.disasm(binary[start:end], start):
            match = re.fullmatch(r"(byte|dword|qword) ptr \[(?:eax|ecx) \+ (0x[0-9a-f]+|[0-9]+)\], (al|eax|xmm0)", instruction.op_str)
            if instruction.mnemonic in ("mov", "movss", "movsd") and match:
                setters.append({"address": hex(instruction.address), "offset": int(match[2],0),
                                "instruction": instruction.mnemonic + " " + instruction.op_str,
                                "storage": match[1]})
        if [row["offset"] for row in setters] != expected_offsets:
            raise ValueError("Prop consumer setter order changed")
        for name, setter in zip(names, setters):
            setter["field"] = name
        consumers.append({"original": original, "method_index": method, "address": hex(start),
                          "end": hex(end), "sha256": sha(binary[start:end]), "setters": setters})
    return {"original_args": old, "source_args": new, "baked_root": old_root,
            "retained_field_types_equal": True, "consumers": consumers,
            "CommonConfig": "NonSerialized in both versions; both actual consumers read eight fields, skipping offset0x24",
            "scope": "Actual Prop root and scalar PropArguments order/types. Other retained nested/custom/polymorphic payloads are byte preserved, not globally certified compatible."}


def raw_node(data, node):
    return data[node["start"]:node["end"]]


def validate_scalar(data, node, signature, strings):
    if node["code"] == 0xc0:
        return
    if signature == "primitive:0x2":
        valid = node["code"] in (0xc2,0xc3)
    elif signature == "primitive:0xc":
        # Original ReadSingle expects an actual float, not an integer coercion.
        valid = node["code"] == 0xca
    elif signature == "primitive:0xe":
        number = decode_integer(data,node)
        valid = 0 <= number < len(strings)
    else:
        # Actual enum and Nullable<enum> data are integer/nil scalar tokens.
        number = decode_integer(data,node)
        valid = -(1 << 31) <= number < (1 << 31)
    if not valid or node["kind"] != "scalar":
        raise ValueError("PropArguments token disagrees with the retained native scalar type")


def project_root(data, start, end, strings, signatures):
    reader = MessagePackSpanReader(data)
    reader.pos = start
    root = reader.node()
    if root["kind"] != "array" or root["count"] != 8 or reader.pos != end:
        raise ValueError("Prop root is not the exact baked eight-field shape")
    children = root["children"]
    for index in (0,1):
        validate_scalar(data,children[index],"primitive:0xe",strings)
    args = children[3]
    record = {"source_span": [start,end], "source_sha256": sha(data[start:end]),
              "root_fields": 8, "removed_fields": [], "retained_fields": []}
    if args["code"] == 0xc0:
        record.update(arguments_nil=True, output_sha256=record["source_sha256"])
        return data[start:end],record
    if args["kind"] != "array" or args["count"] != 42:
        raise ValueError("Unaudited source PropArguments count/shape")
    for old_index,new_index in enumerate(KEEP_INDICES):
        node = args["children"][new_index]
        validate_scalar(data,node,signatures[old_index],strings)
        record["retained_fields"].append({"field": OLD_FIELDS[old_index], "source_index": new_index,
                                         "output_index": old_index, "source_span": [node["start"],node["end"]],
                                         "sha256": sha(raw_node(data,node))})
    for index,name in EXTRA_INDICES.items():
        node = args["children"][index]
        raw = raw_node(data,node)
        if raw.hex() not in REMOVED_ALLOWED[name]:
            raise ValueError("Unaudited newer PropArguments value: " + name)
        value = None if node["code"] == 0xc0 else bool(node["code"] == 0xc3) if node["code"] in (0xc2,0xc3) else decode_integer(data,node)
        record["removed_fields"].append({"field": name, "source_index": index,
                                         "source_span": [node["start"],node["end"]],
                                         "token": raw.hex(), "value": value,
                                         **({"string": strings[value]} if name == "DisplayName" and value is not None else {})})
    encoded_args = b"\xdc\x00\x23" + b"".join(raw_node(data,args["children"][index]) for index in KEEP_INDICES)
    encoded = data[start:args["start"]] + encoded_args + data[args["end"]:end]
    check = MessagePackSpanReader(encoded)
    result = check.node()
    if check.pos != len(encoded) or result["count"] != 8 or result["children"][3]["count"] != 35:
        raise ValueError("Projected Prop boundary/count failed")
    for index in range(8):
        if index != 3 and raw_node(data,children[index]) != raw_node(encoded,result["children"][index]):
            raise ValueError("Retained outer Prop field changed")
    for old_index,new_index in enumerate(KEEP_INDICES):
        if raw_node(data,args["children"][new_index]) != raw_node(encoded,result["children"][3]["children"][old_index]):
            raise ValueError("Retained PropArguments field changed")
    record.update(arguments_nil=False, output_sha256=sha(encoded),
                  other_outer_fields_byte_exact=True, retained35_byte_exact=True)
    return encoded,record


def project_container(payload, strings, evidence):
    if sha(payload) != SOURCE_CONTAINER_SHA or sha("\x1f".join(strings).encode("utf-8")) != STRINGMAP_SHA:
        raise ValueError("Unaccepted Prop resource/string-map input")
    packed_hash,entries,overrides,packed = unpack_container(payload)
    if len(entries) != 421 or overrides:
        raise ValueError("Unaudited Prop entry/override population")
    offsets = sorted({row[1] for row in entries} | {row[2] for row in overrides})
    output, records, new_offsets = bytearray(), [], {}
    signatures = [signature for _,signature in evidence["original_args"]]
    removals = {name: Counter() for name in EXTRA_INDICES.values()}
    for start,end in zip(offsets,offsets[1:]+[len(packed)]):
        new_offsets[start] = len(output)
        encoded,record = project_root(packed,start,end,strings,signatures)
        root = MessagePackSpanReader(packed)
        root.pos = start
        children = root.node()["children"]
        name_index = decode_integer(packed,children[0])
        record.update(output_span=[len(output),len(output)+len(encoded)], name=strings[name_index],
                      keys=[key for key,offset in entries if offset == start])
        for row in record["removed_fields"]:
            removals[row["field"]][row["token"]] += 1
        output.extend(encoded)
        records.append(record)
    new_entries = [(key,new_offsets[offset]) for key,offset in entries]
    new_overrides = [(key,other,new_offsets[offset]) for key,other,offset in overrides]
    result = pack_container(packed_hash,new_entries,new_overrides,output)
    check_hash,check_entries,check_overrides,check_packed = unpack_container(result)
    if check_hash != packed_hash or check_entries != new_entries or check_overrides != new_overrides or check_packed != output:
        raise ValueError("Projected Prop indices/container verification failed")
    return result, {"entry_count": len(entries), "override_count": len(overrides), "root_count": len(records),
                    "root_fields": 8, "source_arguments_fields": 42, "original_arguments_fields": 35,
                    "mapping": [{"field": name,"source_index": new,"output_index": old}
                                for old,(name,new) in enumerate(zip(OLD_FIELDS,KEEP_INDICES))],
                    "removed_field_token_counts": {name:dict(values) for name,values in removals.items()},
                    "retained35_and_other7_outer_fields_byte_exact": True,
                    "entry_and_override_key_order_exact": True,
                    "packed_hash_policy": "Retain source provenance identifier; original shared lookup does not recalculate it. Output SHA256 identifies projected bytes.",
                    "roots": records}


def load_sources(apk19,apk24):
    if file_sha(apk19) != ORIGINAL19_SHA or file_sha(apk24) != SOURCE24_SHA:
        raise ValueError("Unaccepted original/reference APK")
    if PATH in {row["path"] for row in resources.resource_map(apk19)}:
        raise ValueError("Original Prop resource exists; refuse later replacement")
    paths = {row["path"]:row for row in resources.resource_map(apk24)}
    with zipfile.ZipFile(apk24) as package:
        record = paths[PATH]
        obj,raw = resources.object_bytes(package,record)
        if obj["class"] != 114 or sha(raw) != SOURCE_ASSET_SHA:
            raise ValueError("Unaccepted Prop ScriptableObject")
        reader = resources.Reader(raw,28)
        name,arrays = reader.string(), []
        for size in (8,12,1):
            count = reader.read("I")
            if reader.pos + count*size > len(raw):
                raise ValueError("Prop Unity array exceeds object")
            arrays.append((count,raw[reader.pos:reader.pos+count*size]))
            reader.pos += count*size
            reader.align()
        packed_hash = reader.read("I")
        if reader.pos != len(raw) or name != "BakedPropData":
            raise ValueError("Prop Unity object boundary/name changed")
        container = struct.pack("<II",0,packed_hash) + b"".join(struct.pack("<I",count)+data for count,data in arrays)
        if sha(container) != SOURCE_CONTAINER_SHA:
            raise ValueError("Prop source container changed")
        string_obj,string_raw = resources.object_bytes(package,paths["_baked/stringmap"])
        sr = resources.Reader(string_raw,28)
        string_name = sr.string()
        strings = [sr.string() for _ in range(sr.read("I"))]
        string_hash = sr.read("I")
        if string_obj["class"] != 114 or sr.pos != len(string_raw) or any("\x1f" in value for value in strings) or sha("\x1f".join(strings).encode("utf-8")) != STRINGMAP_SHA:
            raise ValueError("Prop requires the accepted string map")
        evidence = schema_evidence(package)
    return container,strings,{**record,"name": name,"class":obj["class"],"source_asset_sha256":sha(raw),
                               "source_container_sha256":sha(container),"original_resource_present":False,
                               "stringmap_dependency":{"name":string_name,"count":len(strings),"packed_hash":string_hash,
                                                        "required_existing_path":"_baked/stringmap.txt","sha256":STRINGMAP_SHA},
                               "native_schema_evidence":evidence}


def verify_native_prefabs(apk19):
    """Require original resource records, root identities and real components."""
    records = {row["path"]:row for row in resources.resource_map(apk19)}
    result = []
    with zipfile.ZipFile(apk19) as package:
        objects = PackageObjects(package)
        for spec in NATIVE_PREFABS:
            expected = {key:spec[key] for key in ("path","file_id","path_id","file")}
            record = records.get(spec["path"])
            if record != expected:
                raise ValueError("Original native Prop resource identity changed")
            obj,raw = objects.object(record)
            if obj["class"] != 1 or sha(raw) != spec["root_sha256"]:
                raise ValueError("Original native Prop root is not the accepted GameObject")
            reader = resources.Reader(raw)
            count = reader.read("i")
            if count != 4:
                raise ValueError("Original native Prop components changed")
            components = [reader.read("iiq") for _ in range(count)]
            layer,name = reader.read("I"),reader.string()
            if name != spec["name"] or len([row for row in components if row[0] == 114]) != 1:
                raise ValueError("Original native Prop root name/component differs")
            _,file_id,path_id = next(row for row in components if row[0] == 114)
            if file_id != 0:
                raise ValueError("Native Prop component unexpectedly external")
            component,component_raw = objects.object({"file":spec["file"],"path_id":path_id})
            if component["class"] != 114 or sha(component_raw) != spec["component_sha256"]:
                raise ValueError("Original native Prop MonoBehaviour changed")
            script_type = objects.script_type(record,component_raw)
            if script_type != "MoleMole.MonoHitableProp":
                raise ValueError("Native Prop is not the original MonoHitableProp")
            result.append({"key":spec["key"],"resource":expected,"root_class":1,"root_name":name,
                           "root_sha256":sha(raw),"layer":layer,"components":components,
                           "component_class":114,"component_path_id":path_id,"component_type":script_type,
                           "component_sha256":sha(component_raw)})
    return result


def appended_stringmap(strings):
    original = "\x1f".join(strings).encode("utf-8")
    if len(strings) != 22416 or len(original) != 518120 or sha(original) != STRINGMAP_SHA:
        raise ValueError("Native Prop extension requires the exact original string-map prefix")
    paths = [spec["path"] for spec in NATIVE_PREFABS]
    if any(path.lower() in {value.lower() for value in strings} for path in paths):
        raise ValueError("Native Prop appended path already has a source index")
    extended = strings + paths
    output = "\x1f".join(extended).encode("utf-8")
    if (len(extended) != 22418 or len(output) != 518197 or sha(output) != APPENDED_STRINGMAP_SHA or
            output[:len(original)] != original or extended[:22416] != strings):
        raise ValueError("Native Prop string-map append differs from the audited plan")
    if any(extended[spec["new_index"]] != spec["path"] or not 0 < spec["new_index"] <= 65535 for spec in NATIVE_PREFABS):
        raise ValueError("Native Prop appended index/path/UInt16 relation changed")
    return original,output,extended


def project_native_paths(payload,strings,assets):
    """Only replace two PrefabPath nodes relative to arguments-only07cf."""
    if sha(payload) != ARGUMENTS_ONLY_SHA or len(assets) != 2:
        raise ValueError("Native Prop profile requires the accepted arguments-only candidate")
    original_map,new_map,extended = appended_stringmap(strings)
    for spec,asset in zip(NATIVE_PREFABS,assets):
        if (asset["key"] != spec["key"] or asset["resource"] != {key:spec[key] for key in ("path","file_id","path_id","file")} or
                asset["root_sha256"] != spec["root_sha256"] or asset["component_sha256"] != spec["component_sha256"] or
                asset["root_name"] != spec["name"] or asset["component_type"] != "MoleMole.MonoHitableProp"):
            raise ValueError("Native Prop target resource proof disagrees with the accepted original asset")
    packed_hash,entries,overrides,packed = unpack_container(payload)
    if len(entries) != 421 or overrides:
        raise ValueError("Unaudited native Prop key population")
    selected = {spec["key"]:spec for spec in NATIVE_PREFABS}
    by_offset = {offset:key for key,offset in entries}
    offsets = sorted(by_offset)
    output,records,new_offsets = bytearray(),[],{}
    unchanged = hashlib.sha256()
    for start,end in zip(offsets,offsets[1:]+[len(packed)]):
        new_offsets[start] = len(output)
        key = by_offset[start]
        root_reader = MessagePackSpanReader(packed)
        root_reader.pos = start
        root = root_reader.node()
        if root_reader.pos != end or root["kind"] != "array" or root["count"] != 8 or root["children"][3]["count"] != 35:
            raise ValueError("Native Prop path projection received an unaudited logical root")
        old_raw = packed[start:end]
        if key not in selected:
            output.extend(old_raw)
            unchanged.update(old_raw)
            continue
        spec = selected[key]
        name_node,path_node = root["children"][0],root["children"][1]
        if strings[key] != spec["name"] or decode_integer(packed,name_node) != key or raw_node(packed,path_node) != b"\xcd"+struct.pack(">H",spec["old_index"]):
            raise ValueError("Native Prop selected root Name/PrefabPath/UInt16 identity differs")
        old_path = strings[spec["old_index"]]
        if old_path != "Entities/PropObject/"+spec["name"]:
            raise ValueError("Native Prop source prefab path identity differs")
        replacement = b"\xcd"+struct.pack(">H",spec["new_index"])
        encoded = packed[start:path_node["start"]]+replacement+packed[path_node["end"]:end]
        verifier = MessagePackSpanReader(encoded)
        projected = verifier.node()
        if verifier.pos != len(encoded) or projected["count"] != 8:
            raise ValueError("Native Prop path projection boundary changed")
        for index in range(8):
            if index != 1 and raw_node(packed,root["children"][index]) != raw_node(encoded,projected["children"][index]):
                raise ValueError("Native Prop projection changed another outer field/argument")
        if decode_integer(encoded,projected["children"][1]) != spec["new_index"] or extended[spec["new_index"]] != spec["path"]:
            raise ValueError("Native Prop new token does not resolve to the verified original path")
        records.append({"key":key,"name":spec["name"],"source_root_span":[start,end],
                        "output_root_span":[len(output),len(output)+len(encoded)],
                        "source_root_sha256":sha(old_raw),"output_root_sha256":sha(encoded),
                        "old_index":spec["old_index"],"new_index":spec["new_index"],"old_path":old_path,"new_path":spec["path"],
                        "old_token":raw_node(packed,path_node).hex(),"new_token":replacement.hex(),
                        "other7_outer_nodes_and_all35_arguments_byte_exact":True})
        output.extend(encoded)
    if sorted(row["key"] for row in records) != sorted(selected):
        raise ValueError("Native Prop projection did not replace exactly the two accepted targets")
    new_entries = [(key,new_offsets[offset]) for key,offset in entries]
    new_overrides = [(key,other,new_offsets[offset]) for key,other,offset in overrides]
    result = pack_container(packed_hash,new_entries,new_overrides,output)
    check_hash,check_entries,check_overrides,check_packed = unpack_container(result)
    if check_hash != packed_hash or check_entries != new_entries or check_overrides != new_overrides or check_packed != output or len(result) != len(payload):
        raise ValueError("Native Prop container/key order/offset verification failed")
    return result,new_map,{"previous_arguments_only_sha256":sha(payload),"changed_root_count":2,
                           "unselected419_roots_byte_exact":True,"unselected_aggregate_sha256":unchanged.hexdigest(),
                           "all421_original35_arguments_byte_exact_relative_to_arguments_only":True,
                           "entry_and_override_key_order_exact":True,"old_offset_to_new_offset":new_offsets,
                           "roots":records,"original_native_prefabs":assets,
                           "stringmap":{"source_sha256":sha(original_map),"source_count":22416,"source_bytes":len(original_map),
                                        "output_sha256":sha(new_map),"output_count":22418,"output_bytes":len(new_map),
                                        "source_byte_prefix_and_all_old_indices_exact":True,
                                        "appended":[{"index":spec["new_index"],"path":spec["path"]} for spec in NATIVE_PREFABS]},
                           "packed_hash_policy":"Keep original container and StringMap packedHash values; they contribute to bakeBaseHash/dataContentHash. Never recompute from appended text; separate SHA256 identifies changed bytes.",
                           "native_loader_proof":"server19-run/prop-fix-research/advancedbox/native/stringmap-append-safety.json; existing supplier Split and reader bounds use dynamic array length, no fixed22416 count"}


def build(apk19,apk24,profile="arguments_only",artifacts=None):
    if profile not in ("arguments_only","act101_native_props"):
        raise ValueError("Unsupported audited Prop profile")
    source,strings,provenance = load_sources(apk19,apk24)
    payload,projection = project_container(source,strings,provenance["native_schema_evidence"])
    manifest = {"format":"server19-prop-compat-1","source19":{"path":str(apk19.resolve()),"sha256":ORIGINAL19_SHA},
                "source24":{"path":str(apk24.resolve()),"sha256":SOURCE24_SHA},
                "runtime_compatibility":"unaccepted","source_version":"2.4 compatibility projection; not historical1.9 data",
                "limitations":["Seven original-absent fields are not implemented by 1.9; removed nonnil values are explicitly recorded.",
                               "Other retained CommonArguments, BeHitEffect, Abilities, AnimEvents and MPArguments bytes are untouched; their nested/custom/polymorphic runtime compatibility is not globally proven.",
                               "This resource projection is static evidence, not a claim of completion of any stage or later feature."],
                "files":[{"path":PATH,"bytes":len(payload),"output_sha256":sha(payload),
                          "required_existing_output_sha256":SOURCE_CONTAINER_SHA,"provenance":provenance,"projection":projection}]}
    if profile == "act101_native_props":
        if provenance["stringmap_dependency"]["packed_hash"] != 182510128:
            raise ValueError("Native Prop extension requires the unchanged source StringMap packedHash")
        previous = payload
        payload,new_map,native_projection = project_native_paths(previous,strings,verify_native_prefabs(apk19))
        original_map = "\x1f".join(strings).encode("utf-8")
        manifest["format"] = "server19-act101-native-prop-compat-1"
        manifest["profile"] = profile
        prop = manifest["files"][0]
        prop.update(bytes=len(payload),output_sha256=sha(payload),required_existing_output_sha256=ARGUMENTS_ONLY_SHA,
                    native_path_projection=native_projection)
        prop["arguments_only_projection"] = prop.pop("projection")
        prop["projection"] = native_projection
        prop["provenance"]["stringmap_dependency"].update(count=22418,source_count=22416,source_sha256=STRINGMAP_SHA,
                                                        sha256=APPENDED_STRINGMAP_SHA,paired_file_required=True)
        manifest["files"].append({"path":"_baked/stringmap.txt","bytes":len(new_map),"output_sha256":sha(new_map),
                                  "required_existing_output_sha256":STRINGMAP_SHA,"source_count":22416,"output_count":22418,
                                  "kept_packed_hash":182510128,"projection":native_projection["stringmap"]})
        manifest["deployment_pair"] = {"files":[PATH,"_baked/stringmap.txt"],"policy":"Validate both accepted previous hashes and deploy the pair while the app is stopped; do not launch with either half alone."}
        manifest["limitations"].append("Only the original AdvancedBox/GeneralBox native prefab paths are restored; owner/stage arguments and runtime gameplay remain for native acceptance.")
        if artifacts is not None:
            artifacts.update({"_baked/stringmap.txt":new_map,"reference/_baked/stringmap.txt":original_map,
                              "reference/arguments-only/"+PATH:previous})
    # JSON persists declaration pairs as lists; use that same deterministic
    # in-memory shape so audit compares data rather than tuple/list spelling.
    return source,payload,json.loads(json.dumps(manifest,ensure_ascii=False))


def prepare(apk19,apk24,output,profile="arguments_only"):
    extras = {}
    source,payload,manifest = build(apk19,apk24,profile,extras)
    targets = {**extras,PATH:payload,"reference/"+PATH:source,
               "manifest.json":(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode("utf-8")}
    for path,data in targets.items():
        target = output/path
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError("Preserve existing changed output: " + str(target))
    for path,data in targets.items():
        target = output/path
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    return {"status":"explicit_prop_arguments_projection_exported" if profile == "arguments_only" else "paired_native_prop_path_projection_exported",
            "roots":421,"output":str(output.resolve()),
            "deployment_files":[row["path"] for row in manifest["files"]],"output_sha256":sha(payload),"manifest_sha256":file_sha(output/"manifest.json"),
            "bytes":len(payload),"runtime_compatibility":"unaccepted"}


def audit(apk19,apk24,output,profile="arguments_only"):
    extras = {}
    source,payload,manifest = build(apk19,apk24,profile,extras)
    if json.loads((output/"manifest.json").read_text(encoding="utf-8")) != manifest or (output/PATH).read_bytes() != payload or (output/"reference"/PATH).read_bytes() != source or any((output/path).read_bytes() != data for path,data in extras.items()):
        raise ValueError("Prop provenance or output bytes changed")
    return {"status":"source_projection_and_all421_retained_bytes_verified","output_sha256":sha(payload),
            "manifest_sha256":file_sha(output/"manifest.json"),"roots":421,"runtime_compatibility":"unaccepted"}


def self_test(apk19,apk24,profile="arguments_only"):
    if profile not in ("arguments_only","act101_native_props"):
        raise ValueError("Unsupported audited Prop profile")
    source,strings,provenance = load_sources(apk19,apk24)
    evidence = provenance["native_schema_evidence"]
    payload,projection = project_container(source,strings,evidence)
    signatures = [signature for _,signature in evidence["original_args"]]
    _,entries,_,packed = unpack_container(source)
    start = min(offset for _,offset in entries)
    end = sorted(offset for _,offset in entries)[1]
    first = packed[start:end]
    reader = MessagePackSpanReader(first)
    root = reader.node()
    args = root["children"][3]
    checks = {"all421_retained35_and_outer7_byte_exact":True,"all421_root8_and_arguments35":True,
              "entry_order_and_rebuilt_offsets":True}
    def rejects(label,call):
        try:
            call()
        except ValueError:
            checks[label] = True
        else:
            raise AssertionError("Missing rejection guard: " + label)
    rejects("unknown_new_field",lambda:check_field_mapping(evidence["original_args"],evidence["source_args"]+[("UnknownNewField","primitive:0x2")]))
    wrong = [tuple(row) for row in evidence["source_args"]]
    wrong[24] = (wrong[24][0],"primitive:0xe")
    rejects("retained_duration_type_changed",lambda:check_field_mapping(evidence["original_args"],wrong))
    def replaced(node,value):
        return first[:node["start"]]+value+first[node["end"]:]
    nature = replaced(args["children"][4],b"\x01")
    rejects("unaudited_nonnil_newer_nature",lambda:project_root(nature,0,len(nature),strings,signatures))
    duration = replaced(args["children"][24],b"\xcd\x00\x01")
    rejects("uint16_duration_rejected",lambda:project_root(duration,0,len(duration),strings,signatures))
    wrong_count = first[:args["start"]]+b"\xdc\x00\x29"+first[args["start"]+3:]
    rejects("wrong_arguments_count",lambda:project_root(wrong_count,0,len(wrong_count),strings,signatures))
    rejects("ninth_outer_field",lambda:project_root(b"\x99"+first[1:]+b"\xc0",0,len(first)+1,strings,signatures))
    rejects("truncated_root",lambda:project_root(first[:-1],0,len(first)-1,strings,signatures))
    nil = replaced(args,b"\xc0")
    unchanged,record = project_root(nil,0,len(nil),strings,signatures)
    if unchanged != nil or not record["arguments_nil"]:
        raise AssertionError("Nil PropArguments were not preserved")
    checks["nil_arguments_preserved"] = True
    counts = projection["removed_field_token_counts"]
    if counts != {"Nature":{"c0":421},"UseOwnerNature":{"c0":419,"c2":2},
                  "FollowOwnerTimeScale":{"c0":421},"CanAffectAvatars":{"c0":420,"c2":1},
                  "CantKillInLevel":{"c0":421},"ShowStateus":{"c0":420,"c3":1},
                  "DisplayName":{"c0":420,"cd35fd":1}}:
        raise AssertionError("Known actual newer-feature values changed")
    checks["all7_removed_value_population_exact"] = True
    if profile == "act101_native_props":
        assets = verify_native_prefabs(apk19)
        native_payload,new_map,native_projection = project_native_paths(payload,strings,assets)
        checks.update(original_native_gameobjects_and_components_verified=True,
                      unchanged419_roots_and_all421_arguments=True,only2_native_prefab_path_nodes_changed=True,
                      source22416_strings_and_byte_prefix_exact=True,appended22416_and22417_exact=True,
                      native_pair_uint16_length_and_offsets_verified=True)
        altered_strings = list(strings)
        altered_strings[1] += "?"
        rejects("altered_old_stringmap_prefix",lambda:appended_stringmap(altered_strings))
        changed_assets = json.loads(json.dumps(assets))
        changed_assets[0]["resource"]["path"] = "entities/propobject/level1/unverified"
        rejects("unverified_native_target_asset",lambda:project_native_paths(payload,strings,changed_assets))
        rejects("unknown_previous_prop_payload",lambda:project_native_paths(payload[:-1]+b"\x01",strings,assets))
        if sha(new_map) != APPENDED_STRINGMAP_SHA or len(native_payload) != len(payload):
            raise AssertionError("Native Prop pair differs from the inspected append plan")
        payload = native_payload
    return {"status":"passed","checks":checks,"output_sha256":sha(payload),"roots":421}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("prepare","audit","self-test"))
    parser.add_argument("--apk19",type=Path,default=resources.DEFAULT19)
    parser.add_argument("--apk24",type=Path,default=resources.DEFAULT24)
    parser.add_argument("--profile",choices=("arguments_only","act101_native_props"),default="arguments_only")
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    output = args.output or (NATIVE_OUTPUT if args.profile == "act101_native_props" else DEFAULT_OUTPUT)
    result = self_test(args.apk19,args.apk24,args.profile) if args.command == "self-test" else (prepare if args.command == "prepare" else audit)(args.apk19,args.apk24,output,args.profile)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
