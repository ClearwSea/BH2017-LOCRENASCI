"""Bounded later-to-native1.9 ability projection for actual first-stage AI.

Use typed logical consumers, including custom fields outside MessagePack
arrays. Preserve source/reference bytes and every retained terminal value.
No device, service, native library, avatar or account operations are performed.
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
from collections import Counter
import csv
import io
import json
import re
from pathlib import Path
import struct
import zipfile

import analyze19 as a
import server19_resources as resources
import server19_stage_monsters as monster
from server19_metadata_export import SourceTypedDecoder, fields, type_info, type_pointer
from server19_baked import MessagePackSpanReader

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-ability-resources"
PATH = "_baked/bakedabilitydata"
SOURCE_SHA = "bedb4d54a65abda887ff4c5b946fe056c4bdfbecffe0e1162c6024de56960659"
ABILITY = "MoleMole.Config.ConfigAbility"
MODIFIER = "MoleMole.Config.ConfigAbilityModifier"
ACTION = "MoleMole.Config.ConfigAbilityAction"
MIXIN = "MoleMole.Config.ConfigAbilityMixin"
PREDICATE = "MoleMole.Config.ConfigAbilityPredicate"
STATE_OPTION = "MoleMole.Config.ConfigAbilityStateOption"
MIXIN_ARGUMENT = "MoleMole.Config.IMixinArgument"
DYNAMIC = "MoleMole.Config.ConfigDynamicArguments"
STATISTICS = "MoleMole.Config.CustomStatistics"
AVATAR_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-ability-avatar101-resources"
LEADER_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-ability-avatar101-leader-resources"
NEWBIE_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-ability-avatar101-newbie-resources"
ACT101_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-entry-ability-resources-v1"
PROP_BOX_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-prop-box-ability-resources"
PROP_BOX_KEY = (16458, None)
PROP_BOX_NAME = "PropLongRangeInvicible"
PROP_BOX_SOURCE_ROOT_SHA = "883591732471994c19901868194a7fb2cea9443e9ecef78fd86d97084f1c418b"
CULTIVATION_OUTPUT = ROOT / ".local-baseline/server19-dev/avatar-cultivation-ability-resources"
CULTIVATION_BOUNDED_OUTPUT = ROOT / ".local-baseline/server19-dev/avatar-cultivation-bounded-ability-resources-v2"
CULTIVATION_PREVIOUS_SHA = "0659301b89693c7d955abadf3caa6b805bc75419f5076897d5905e70c74f2338"
STAGE7_OUTPUT = ROOT / ".local-baseline/server19-dev/stage7-ready/abilities"
STAGE7_PREVIOUS_SHA = "371831cc8456a88860973c53fa825563be613225ccb3987f158e3374dcbb4f5e"
STAGE7_SELECTED = {(16013, None): "NewbieTutorial_EvadeSuccess",
                   (16016, None): "NewbieTutorial_NoEvadeSkill"}
ACT101_ACCEPTED_SHA = "caf007be98535a2262b90d9c01b9ee02c2b7aadbeb9748a7d5b77a7f58480dc6"
AVATAR_PROFILES = ("avatar101", "avatar101_leader", "avatar101_newbie", "act101_entry")
NEWBIE_PROFILES = ("avatar101_newbie", "act101_entry")
CAMERA_SHAKE = "MoleMole.Config.ConfigEntityCameraShake"
CAMERA_PATH = "_baked/bakedconfigentitycamerashake"
ARROW_ARGUMENT = "MoleMole.Config.HitExplodeTracingBulletMixinArgument"
LATER_BUFF_UI_ACTIONS = ('MoleMole.Config.AddCustomBuff','MoleMole.Config.RemoveCustomBuff')
ARROW_PATH = "_baked/bakedhitexplodetracingbulletmixinargument"
SELECTED = {(15668, None): "MonsterCommonAIAbility/default",
            (15668, 8956): "MonsterCommonAIAbility/DeadWalker",
            (15668, 21824): "MonsterCommonAIAbility/UlyssesWarrior"}
AVATAR_SELECTED = {**SELECTED, **{(key, None): name for key, name in (
    (13404, "Kiana_PT_DefaultAvatarAbility"), (13414, "Kiana_PT_UltraMode"),
    (13419, "Kiana_PT_WitchTime"), (16045, "Noop"), (13410, "Kiana_PT_SKL02_Invincible"),
    (13407, "Kiana_PT_HeavyHit_Invincible"), (13408, "Kiana_PT_HitShield"))}}
LEADER_SELECTED = {**AVATAR_SELECTED, (13402, None): "Kiana_PT_Captain_HPUp"}
NEWBIE_SELECTED = {**LEADER_SELECTED, (16004, None): "NewbieBattleBuff_EvadeCDReduceBuff",
                   (16007, None): "NewbieBattleBuff_SpecialSkillForEvade", (16006, None): "NewbieBattleBuff_SPBuff"}
ACT101_SELECTED = {**NEWBIE_SELECTED, **{
    (15668, 8938): "MonsterCommonAIAbility/DeadArcher", (15668, 21812): "MonsterCommonAIAbility/UlyssesFast",
    (15725, None): "Monster_DG_020_ShootArrow", (18987, None): "ShootArrowAttackID",
    (18987, 8508): "ShootArrowAttackID/DG_020", (9509, None): "Elite_EliteShield/default",
    (9509, 8956): "Elite_EliteShield/DeadWalker", (9509, 8938): "Elite_EliteShield/DeadArcher",
    (9509, 21812): "Elite_EliteShield/UlyssesFast", (15808, None): "Monster_Special_AttackRatio",
    (10824, None): "Equip_Pt2_AttackRatioUpSmall", (10859, None): "Equip_Pt2_DefenceRatioUpSmall",
    (13415, None): "Kiana_PT_UnlockBranchAttack", (13417, None): "Kiana_PT_UnlockSKL02Button"}}
PROFILE_ROOTS = {"ai": SELECTED, "avatar101": AVATAR_SELECTED, "avatar101_leader": LEADER_SELECTED,
                 "avatar101_newbie": NEWBIE_SELECTED, "act101_entry": ACT101_SELECTED,
                 "act101_prop_box": {**ACT101_SELECTED, PROP_BOX_KEY: PROP_BOX_NAME}}
PROFILE_OUTPUTS = {"ai": DEFAULT_OUTPUT, "avatar101": AVATAR_OUTPUT, "avatar101_leader": LEADER_OUTPUT,
                   "avatar101_newbie": NEWBIE_OUTPUT, "act101_entry": ACT101_OUTPUT,
                   "act101_prop_box": PROP_BOX_OUTPUT}
AVATAR_EXCLUSIONS = {
    "MoleMole.Config.SkillMoveToTargetMixin": ["MoveType"],
    "MoleMole.Config.HealSP": ["ConsumeWithProperty"],
    "MoleMole.Config.ModifyDamageMixin": ["ExtraNormalDamageMax", "ExtraFireDamageMax", "ExtraIceDamageMax", "ExtraThunderDamageMax"],
}
NEWBIE_EXCLUSIONS = {"MoleMole.Config.DamageByAttackValue": ["MaxHpValue"]}
ACT101_EXCLUSIONS = {
    "MoleMole.Config.HitExplodeBulletMixin": ["DestroyCloseToGround", "ForceRotate", "FollowOwnerTimeScale"],
    "MoleMole.Config.TriggerAbility": ["UseFloatArgument", "FloatArgument"],
    "MoleMole.Config.ShieldMixin": ["ShieldMaxValue"],
}


def array_bytes(count):
    if 0 <= count <= 15:
        return bytes([0x90 + count])
    if 0 <= count <= 65535:
        return b"\xdc" + struct.pack(">H", count)
    raise ValueError("Ability array outside bounded encoding")


def integer_bytes(number):
    if 0 <= number <= 127:
        return bytes([number])
    if 0 <= number <= 255:
        return b"\xcc" + bytes([number])
    if 0 <= number <= 65535:
        return b"\xcd" + struct.pack(">H", number)
    raise ValueError("Unsupported bounded union tag")


class Schema:
    def __init__(self, package, profile="ai"):
        if profile not in PROFILE_ROOTS:
            raise ValueError("Unsupported bounded ability profile")
        self.profile = profile
        self.package = package
        self.indexed_references = []
        self.camera_evidence = None
        self.arrow_evidence = None
        self.source = SourceTypedDecoder(package)
        self.original_names = {a.type_name(i): i for i in range(len(a.T))}
        self.checks, self.maps, self.mapping_checks = {}, {}, []
        self.original_usage = self.usage_map(a.B, a.E, 0x34a67e4)
        self.source_usage = self.usage_map(self.source.metadata, self.source.binary, 0x4252108)
        self.original_tags = {}
        unions = [(ACTION, 129), (MIXIN, 170), (PREDICATE, 66), (STATE_OPTION, 14)]
        if profile == "act101_entry":
            unions.append((MIXIN_ARGUMENT, 4))
        for kind, maximum in unions:
            tags = {}
            for tag in range(1, maximum + 1):
                try:
                    name, evidence = self.resolve_tag(kind, tag, True)
                except ValueError:
                    continue
                if name in tags:
                    raise ValueError("Duplicate original union concrete type")
                tags[name] = (tag, evidence)
            self.original_tags[kind] = tags

    @staticmethod
    def usage_map(metadata, binary, pair):
        header = struct.unpack_from("<64I", metadata)
        count, table = struct.unpack_from("<II", binary, pair)
        destinations = {struct.unpack_from("<I", binary, table + i * 4)[0]: i for i in range(count)}
        pairs = dict(struct.iter_unpack("<II", metadata[header[50]:header[50] + header[51]]))
        return {address: pairs[index] for address, index in destinations.items() if index in pairs}

    def resolve_tag(self, kind, tag, original):
        if original:
            base = 0x33e39d8
            maximum = {ACTION: 129, MIXIN: 170, PREDICATE: 66, STATE_OPTION: 14, MIXIN_ARGUMENT: 4}[kind]
            if not 1 <= tag <= maximum:
                raise ValueError("Unknown original union tag")
            if kind == MIXIN_ARGUMENT:
                table, ordinal = base - 0x8e5ed4, tag - 1
            elif kind == STATE_OPTION:
                table, ordinal = base - 0x8e3294, tag - 1
            elif tag <= 42:
                table = {ACTION: 0x2b00190, MIXIN: 0x2b00394, PREDICATE: 0x2b0063c}[kind]
                ordinal = tag - 1
            else:
                table = {ACTION: 0x2b00238, MIXIN: 0x2b0043c, PREDICATE: 0x2b006e4}[kind]
                ordinal = tag - 43
            binary, metadata, usage = a.E, a.B, self.original_usage
            spec_pair, inst_pair = 0x34a67cc, 0x34a67b4
        else:
            if not 1 <= tag <= {ACTION: 145, MIXIN: 179, PREDICATE: 68, STATE_OPTION: 14, MIXIN_ARGUMENT: 4}[kind]:
                raise ValueError("Unsupported source union tag")
            base, ordinal = 0x42531e4, tag - 1
            # Source70505@24e87a1 reads EBX+ecx*4-c44548;
            # Source70509@24ecff3 reads EBX+ecx*4-c44304.
            table = base - {ACTION: 0xc44548, MIXIN: 0xc44304, PREDICATE: 0xc44038, STATE_OPTION: 0xc43f28, MIXIN_ARGUMENT: 0xc5a008}[kind]
            binary, metadata, usage = self.source.binary, self.source.metadata, self.source_usage
            spec_pair, inst_pair = 0x42520f0, 0x42520d8
        branch = base + struct.unpack_from("<i", binary, table + ordinal * 4)[0]
        instructions = list(a.MD.disasm(binary[branch:branch + 16], branch))
        if not instructions:
            raise ValueError("Missing union switch branch")
        instruction = instructions[0]
        if original and kind == MIXIN_ARGUMENT:
            if instruction.mnemonic != "mov" or instruction.op_str != "dword ptr [esp + 0x20], edx":
                raise ValueError("Original MixinArgument case prefix changed")
            instruction = instructions[1]
        import re
        match = re.fullmatch(r"eax, \[ebx ([+-]) (0x[0-9a-f]+)\]", instruction.op_str.replace("dword ptr ", ""))
        if not match or instruction.mnemonic != ("mov" if original else "lea"):
            raise ValueError("Unrecognized union formatter branch")
        address = base + (1 if match[1] == "+" else -1) * int(match[2], 16)
        address = struct.unpack_from("<I", binary, address)[0] if original else address
        token = usage.get(address)
        if token is None or token >> 29 != 6:
            raise ValueError("Union branch lacks MethodRef usage")
        specs, spec_table = struct.unpack_from("<II", binary, spec_pair)
        index = token & 0x1fffffff
        if index >= specs:
            raise ValueError("Union MethodSpec outside registration")
        method, class_inst, method_inst = struct.unpack_from("<3i", binary, spec_table + index * 12)
        header = struct.unpack_from("<64I", metadata)
        method_data = a.M[method] if original else struct.unpack_from("<12I4H", metadata, header[12] + method * 56)
        name = a.string(method_data[0]) if original else self.source.string(method_data[0])
        if name != "GetFormatterWithVerify" or class_inst != -1 or method_inst < 0:
            raise ValueError("Union branch is not the concrete verified formatter")
        count, instances = struct.unpack_from("<II", binary, inst_pair)
        if method_inst >= count:
            raise ValueError("Union generic instance out of range")
        instance = struct.unpack_from("<I", binary, instances + method_inst * 4)[0]
        count, argv = struct.unpack_from("<II", binary, instance)
        if count != 1:
            raise ValueError("Union formatter has unexpected generic arguments")
        pointer = struct.unpack_from("<I", binary, argv)[0]
        data, flags = struct.unpack_from("<II", binary, pointer)
        if (flags >> 16) & 255 not in (17, 18):
            raise ValueError("Union generic argument is not a concrete class")
        concrete = a.type_name(data) if original else self.source.name(data)
        return concrete, {"tag": tag, "concrete": concrete, "switch_table": hex(table),
                          "branch": hex(branch), "branch_first16_sha256": monster.sha(binary[branch:branch + 16]),
                          "usage_address": hex(address), "method_spec_index": index}

    def union(self, kind, tag, original):
        concrete, evidence = self.resolve_tag(kind, tag, original)
        if not original and kind == ACTION and concrete in LATER_BUFF_UI_ACTIONS and getattr(self,'ui_custom_buff_ids',()):
            self.check(concrete)
            return concrete,None
        if self.profile in AVATAR_PROFILES and not original and kind == ACTION and concrete == STATISTICS:
            if concrete in self.original_names:
                raise ValueError("Preserve an original statistics action instead of excluding it")
            self.check(concrete)
            return concrete, None
        if concrete not in self.original_tags[kind]:
            raise ValueError("Source union type unavailable in original1.9: " + concrete)
        target_tag, target_evidence = self.original_tags[kind][concrete]
        self.check(concrete)
        if not original and (kind, tag) not in self.maps:
            self.maps[kind, tag] = target_tag
            self.mapping_checks.append({"base_type": kind, "source": evidence, "original": target_evidence,
                                        "same_concrete_type": True})
        return concrete, target_tag

    def info(self, pointer, original):
        if original:
            return type_info(pointer)
        data, flags = struct.unpack_from("<II", self.source.binary, pointer)
        return {"data": data, "kind": (flags >> 16) & 255, "attributes": flags & 65535}

    def signature(self, pointer, original):
        value = self.info(pointer, original)
        data, kind = value["data"], value["kind"]
        binary = a.E if original else self.source.binary
        if kind in (17, 18):
            return a.type_name(data) if original else self.source.name(data)
        if kind == 29:
            return self.signature(data, original) + "[]"
        if kind == 21:
            definition, inst = struct.unpack_from("<II", binary, data)
            count, argv = struct.unpack_from("<II", binary, inst)
            return (a.type_name(definition) if original else self.source.name(definition)) + "[" + ",".join(
                self.signature(struct.unpack_from("<I", binary, argv + i * 4)[0], original) for i in range(count)) + "]"
        return f"primitive:{kind:#x}"

    def members(self, name, original):
        index = (self.original_names if original else self.source.names)[name]
        binary = a.E if original else self.source.binary
        declared = fields(index) if original else self.source.fields(index)
        result = [(name, ptr) for name, ptr in declared if not self.info(ptr, original)["attributes"] & 0x80]
        parent = (a.T if original else self.source.types)[index][6]
        if parent != 0xffffffff:
            pointer = type_pointer(parent) if original else struct.unpack_from("<I", binary, 0x409d890 + parent * 4)[0]
            value = self.info(pointer, original)
            if value["kind"] in (17, 18):
                parent_name = a.type_name(value["data"]) if original else self.source.name(value["data"])
                result += self.members(parent_name, original)
        return result

    def camera_dependency(self, strings):
        if self.camera_evidence is not None:
            return self.camera_evidence
        self.check(CAMERA_SHAKE)
        local = ROOT / ".local-baseline/server19-dev/baked-fallback" / CAMERA_PATH
        existing = local.read_bytes()
        if monster.sha(existing) != "3e692765ff4d5fda680835b6fdb9fedce79fedd423001e33c4f07db5142e7534":
            raise ValueError("Preserve the accepted CameraShake indexed dependency")
        indexed, packed_hash, count = struct.unpack_from("<III", existing)
        if indexed != 1 or count != 563:
            raise ValueError("Accepted CameraShake indexed container changed")
        offsets = struct.unpack_from("<" + "i" * count, existing, 12)
        selected_indices = getattr(self, "camera_indices", (127, 188, 205) if self.profile == "act101_entry" else (127, 205))
        size = struct.unpack_from("<I", existing, 12 + count * 4)[0]
        packed = existing[16 + count * 4:]
        if len(packed) != size or any(not 0 <= offsets[index] < len(packed) for index in selected_indices):
            raise ValueError("Actual CameraShake offset outside accepted container")
        span_reader = MessagePackSpanReader(packed)
        boundaries = set()
        while span_reader.pos < len(packed):
            boundaries.add(span_reader.pos)
            span_reader.node()
        if span_reader.pos != len(packed) or any(offset not in boundaries for offset in offsets):
            raise ValueError("CameraShake index does not point to a complete accepted root")
        maps = {row["path"]: row for row in resources.resource_map(Path(self.package.filename))}
        obj, raw = resources.object_bytes(self.package, maps[CAMERA_PATH])
        if obj["class"] != 114:
            raise ValueError("CameraShake dependency source must be ScriptableObject")
        cursor = resources.Reader(raw, 28)
        source_name = cursor.string()
        source_count = cursor.read("I")
        if source_count != count:
            raise ValueError("Source CameraShake index count differs")
        source_offsets = cursor.data[cursor.pos:cursor.pos + count * 4]
        cursor.pos += count * 4
        source_size = cursor.read("I")
        source_packed = raw[cursor.pos:cursor.pos + source_size]
        cursor.pos += source_size; cursor.align()
        source_hash = cursor.read("I")
        normalized = struct.pack("<III", 1, source_hash, count) + source_offsets + struct.pack("<I", source_size) + source_packed
        if cursor.pos != len(raw) or normalized != existing or packed_hash != source_hash:
            raise ValueError("Accepted CameraShake dependency is not exact audited source")
        selected = []
        for index in selected_indices:
            source_reader = AbilityReader(packed, strings, self)
            source_reader.pos = offsets[index]
            node = source_reader.class_value(CAMERA_SHAKE, f"CameraShake{index}")
            original_reader = AbilityReader(packed, strings, self, True)
            original_reader.pos = offsets[index]
            original_reader.class_value(CAMERA_SHAKE, f"CameraShake{index}")
            if node["count"] != 6 or source_reader.pos != original_reader.pos or source_reader.leaves != original_reader.leaves or source_reader.edits:
                raise ValueError("CameraShake original/source field consumption differs")
            selected.append({"index": index, "packed_span": [offsets[index], source_reader.pos],
                             "node_sha256": monster.sha(packed[offsets[index]:source_reader.pos]), "field_count": 6})
        self.camera_evidence = {"type": CAMERA_SHAKE, "required_existing_path": CAMERA_PATH,
            "output_sha256": monster.sha(existing), "bytes": len(existing), "indexed": True,
            "source_resource": {**maps[CAMERA_PATH], "class": obj["class"], "name": source_name, "source_object_sha256": monster.sha(raw)},
            "index_count": count, "selected_roots": selected,
            "all_index_offsets_complete_boundaries": True,
            "field_names": [field for field, _ in self.members(CAMERA_SHAKE, True)],
            "original_custom_formatter": "60696@0x96d700 readWriteIndex=true: ReadInt32@0x96d790 -> IndexedConfig<ConfigEntityCameraShake>.Get@0x96d7cd (MethodSpec11744); false uses normal array6 formatter@0x692d71",
            "source_custom_formatter": "73033@0x24b1acf has the same indexed/inline distinction",
            "policy": "Preserve actual IndexedConfig scalar127/205 and accepted CameraShake resource bytes; not StringMap indices and not inline-array rewrites"}
        return self.camera_evidence

    def arrow_dependency(self, strings):
        """Validate every real indexed argument with both original/source readers."""
        if self.arrow_evidence is not None:
            return self.arrow_evidence
        self.check(ARROW_ARGUMENT)
        existing = (ROOT / ".local-baseline/server19-dev/baked-fallback" / ARROW_PATH).read_bytes()
        if monster.sha(existing) != "88700f678c0628cdfe2f60dbff15eccc03818068154f2da3d86c18ebc8dfe336":
            raise ValueError("Accepted arrow argument resource changed")
        mode, packed_hash, count = struct.unpack_from("<III", existing)
        if mode != 1 or count != 173:
            raise ValueError("Arrow argument indexed container changed")
        offsets = struct.unpack_from("<" + "i" * count, existing, 12)
        size = struct.unpack_from("<I", existing, 12 + count * 4)[0]
        packed = existing[16 + count * 4:]
        if len(packed) != size:
            raise ValueError("Arrow argument packed boundary changed")
        span = MessagePackSpanReader(packed)
        boundaries = set()
        while span.pos < len(packed):
            boundaries.add(span.pos)
            span.node()
        if any(offset not in boundaries for offset in offsets):
            raise ValueError("Arrow argument offsets are not full root boundaries")
        maps = {row["path"]: row for row in resources.resource_map(Path(self.package.filename))}
        obj, raw = resources.object_bytes(self.package, maps[ARROW_PATH])
        cursor = resources.Reader(raw, 28)
        source_name = cursor.string()
        source_count = cursor.read("I")
        source_offsets = raw[cursor.pos:cursor.pos + source_count * 4]
        cursor.pos += source_count * 4
        source_size = cursor.read("I")
        source_packed = raw[cursor.pos:cursor.pos + source_size]
        cursor.pos += source_size
        cursor.align()
        source_hash = cursor.read("I")
        normalized = struct.pack("<III", 1, source_hash, source_count) + source_offsets + struct.pack("<I", source_size) + source_packed
        if obj["class"] != 114 or cursor.pos != len(raw) or normalized != existing:
            raise ValueError("Arrow argument dependency is not exact real source")
        source_reader = AbilityReader(packed, strings, self)
        original_reader = AbilityReader(packed, strings, self, True)
        source_reader.pos = original_reader.pos = offsets[34]
        node = source_reader.class_value(ARROW_ARGUMENT, "ArrowArgument34")
        original_reader.class_value(ARROW_ARGUMENT, "ArrowArgument34")
        if node["count"] != 5 or source_reader.pos != original_reader.pos or source_reader.leaves != original_reader.leaves or source_reader.edits:
            raise ValueError("Arrow argument original/source5-field consumption differs")
        self.arrow_evidence = {"type": ARROW_ARGUMENT, "required_existing_path": ARROW_PATH,
            "output_sha256": monster.sha(existing), "bytes": len(existing), "index_count": count,
            "selected_index": 34, "selected_packed_span": [offsets[34], source_reader.pos],
            "selected_root_sha256": monster.sha(packed[offsets[34]:source_reader.pos]),
            "source_resource": {**maps[ARROW_PATH], "name": source_name, "class": 114, "source_object_sha256": monster.sha(raw)},
            "original_custom_formatter": "60708@96de3c: ReadInt32@96decc -> IndexedConfig.Get MethodSpec11746 @96df09; inline uses5-field formatter57971@6e7c26",
            "source_custom_formatter": "73045@24b21e8 has the same indexed/inline branch",
            "all_index_offsets_complete_boundaries": True,
            "policy": "Retain scalar index34 and all existing indexed resource bytes; no StringMap conversion or replaced projectile"}
        validated=[]
        for index,offset in enumerate(offsets):
            left=AbilityReader(packed,strings,self);right=AbilityReader(packed,strings,self,True)
            left.pos=right.pos=offset
            # Indexed argument records themselves must be inline or nil;
            # scalar indirection would need a separately bounded cycle proof.
            if packed[offset] not in (0xc0,*range(0x90,0xa0),0xdc,0xdd):continue
            node=left.class_value(ARROW_ARGUMENT,'ArrowArgument'+str(index))
            right.class_value(ARROW_ARGUMENT,'ArrowArgument'+str(index))
            if node['code']!=0xc0 and node.get('count')!=5:continue
            if left.pos!=right.pos or left.leaves!=right.leaves or left.edits:continue
            if left.pos != min((x for x in offsets if x>offset),default=len(packed)):continue
            validated.append(index)
        self.arrow_evidence['validated_indices']=validated
        self.arrow_evidence['policy']='Retain real scalar indices only where both original/source consumers match; keep all indexed resource bytes unchanged'
        return self.arrow_evidence

    def check(self, name):
        if name in self.checks:
            return
        if name in LATER_BUFF_UI_ACTIONS and getattr(self,'ui_custom_buff_ids',()):
            if name in self.original_names:raise ValueError('Original UI action must not be removed')
            old,new=self.members(ACTION,True),self.members(name,False)
            if [(f,self.signature(p,True)) for f,p in old] != [(f,self.signature(p,False)) for f,p in new]:
                raise ValueError('UI-only action must have no additional fields beyond original common action declaration')
            self.checks[name]={'type':name,'source_fields':[f for f,p in new],'excluded_fields':[],
                               'later_ui_only_action':True}
            return
        if self.profile in AVATAR_PROFILES and name == STATISTICS and name not in self.original_names:
            members = self.members(name, False)
            expected = [("StatisticsID", "MoleMole.Config.DynamicInt"), ("Value", "MoleMole.Config.DynamicFloat"),
                        ("Target", "MoleMole.Config.AbilityTargetting"), ("TargetOption", "MoleMole.Config.TargettingOption"),
                        ("Predicates", PREDICATE + "[]"), ("MPTotallyLocal", "primitive:0x2")]
            if [(field, self.signature(pointer, False)) for field, pointer in members] != expected:
                raise ValueError("Later-only statistics action shape changed")
            self.checks[name] = {"type": name, "original_type_absent": True,
                                 "source_fields": [field for field, _ in members], "later_only_type": True}
            return
        if name not in self.original_names or name not in self.source.names:
            raise ValueError("Retained ability class unavailable in original/source: " + name)
        old, new = self.members(name, True), self.members(name, False)
        excluded = []
        if name == MODIFIER:
            if len(old) != 29 or len(new) != 30 or new[15][0] != "CustomBuffID":
                raise ValueError("Modifier is not the audited original29/source30")
            excluded, retained = [new[15][0]], new[:15] + new[16:]
        elif (self.profile in NEWBIE_PROFILES and name in NEWBIE_EXCLUSIONS) or (self.profile in AVATAR_PROFILES and name in AVATAR_EXCLUSIONS) or (self.profile == "act101_entry" and name in ACT101_EXCLUSIONS):
            excluded = (ACT101_EXCLUSIONS if name in ACT101_EXCLUSIONS else NEWBIE_EXCLUSIONS if name in NEWBIE_EXCLUSIONS else AVATAR_EXCLUSIONS)[name]
            if any(sum(field == candidate for field, _ in new) != 1 for candidate in excluded):
                raise ValueError("Later avatar field missing or duplicated")
            retained = [(field, pointer) for field, pointer in new if field not in excluded]
        else:
            retained = new
        if self.profile == "act101_entry" and name == "MoleMole.Config.ShieldMixin":
            if [field for field, _ in new[6:9]] != ["ForceResumeRatio", "MinForceResumeCD", "UseLevelTimeScale"] or [field for field, _ in old[5:8]] != ["MinForceResumeCD", "UseLevelTimeScale", "ForceResumeRatio"]:
                raise ValueError("Only the evidenced three-field Shield reorder is supported")
            by_name = {field: pointer for field, pointer in retained}
            if len(by_name) != len(retained) or set(by_name) != {field for field, _ in old}:
                raise ValueError("Shield retained fields differ from original")
            retained = [(field, by_name[field]) for field, _ in old]
        if [(n, self.signature(p, True)) for n, p in old] != [(n, self.signature(p, False)) for n, p in retained]:
            raise ValueError("Retained ability class field type/order changed: " + name)
        self.checks[name] = {"type": name, "original_fields": [n for n, _ in old],
                             "source_fields": [n for n, _ in new], "excluded_fields": excluded,
                             "retained_type_signatures": [self.signature(p, True) for _, p in old],
                             "retained_declarations_equal": True}
        if self.profile == "act101_entry" and name == "MoleMole.Config.ShieldMixin":
            self.checks[name]["field_reorder"] = {"source_indices": [6, 7, 8], "original_field_order_from_source": [7, 8, 6]}


class CultivationSchema(Schema):
    """Separate bounded additions; original profiles keep their exact policy."""
    avatar_cultivation = True
    camera_indices = (127, 139, 188, 202, 205)

    def __init__(self, package):
        super().__init__(package, "act101_entry")

    def check(self, name):
        if name != "MoleMole.Config.AddGlobalValue":
            return super().check(name)
        if name in self.checks:
            return
        old, new = self.members(name, True), self.members(name, False)
        original = [(n, self.signature(p, True)) for n, p in old]
        source = [(n, self.signature(p, False)) for n, p in new]
        if len(original) != 9 or len(source) != 9 or original[1] != ("Key", "primitive:0xe") or source[1] != ("Key", "MoleMole.DynamicString") or original[:1] + original[2:] != source[:1] + source[2:]:
            raise ValueError("Only AddGlobalValue's proven fixed-string wrapper is supported")
        self.checks[name] = {"type": name, "original_fields": [n for n, _ in old],
            "source_fields": [n for n, _ in new], "excluded_fields": [],
            "retained_declarations_equal_except_fixed_key_wrapper": True,
            "fixed_key_wrapper_policy": "Only false/nil isDynamic, exact nonnil fixedValue and nil dynamicKey; preserve fixedValue encoding"}


class AbilityReader(monster.MonsterReader):
    def __init__(self, data, strings, schema, original=False):
        super().__init__(data)
        self.strings, self.schema, self.original = strings, schema, original
        self.edits, self.leaves, self.records = [], {}, []

    def leaf(self, path, node):
        if path in self.leaves:
            raise ValueError("Duplicate typed ability leaf path")
        self.leaves[path] = {"span": [node["start"], node["end"]],
                             "sha256": monster.sha(self.data[node["start"]:node["end"]])}
        return node

    def nullable(self, path):
        if self.data[self.pos:self.pos + 1] == b"\xc0":
            return self.leaf(path, self.node())
        return None

    def scalar(self, kind, path):
        node = self.node()
        if node["kind"] != "scalar":
            raise ValueError("Selected ability primitive is not scalar: " + path)
        if kind == 2:
            if node["code"] not in (0xc2, 0xc3):
                raise ValueError("Ability Boolean must match native ReadBoolean: " + path)
        elif kind in (12, 13):
            if node["code"] not in (0xca, 0xcb):
                raise ValueError("Ability float must match native floating reader: " + path)
        elif kind == 14:
            monster.string_index(self.data, node, self.strings)
        elif kind in range(4, 12):
            number = monster.decode_integer(self.data, node)
            width = {4: 8, 5: 8, 6: 16, 7: 16, 8: 32, 9: 32, 10: 64, 11: 64}[kind]
            lower = -(1 << (width - 1)) if kind % 2 == 0 else 0
            upper = 1 << (width - (kind % 2 == 0))
            if not lower <= number < upper:
                raise ValueError("Ability integer outside declared native range: " + path)
        else:
            raise ValueError(f"Unsupported selected primitive {kind}: {path}")
        return self.leaf(path, node)

    def typed(self, pointer, path, depth=0):
        if depth > 64:
            raise ValueError("Ability nesting exceeds bounded reader")
        nil = self.nullable(path)
        if nil:
            return nil
        value = self.schema.info(pointer, self.original)
        data, kind = value["data"], value["kind"]
        binary = a.E if self.original else self.schema.source.binary
        if kind == 29:
            node = self.header("array")
            node["children"] = [self.typed(data, path + f"[{i}]", depth + 1) for i in range(node["count"])]
            removed = [child for child in node["children"] if child.get("remove_from_array")]
            if removed:
                self.edits.append((node["start"], node["header_end"], array_bytes(node["count"] - len(removed))))
                for child in removed:
                    self.edits.append((child["start"], child["end"], b""))
            node["end"] = self.pos
            return node
        if kind == 21:
            definition, instance = struct.unpack_from("<II", binary, data)
            name = a.type_name(definition) if self.original else self.schema.source.name(definition)
            count, argv = struct.unpack_from("<II", binary, instance)
            args = [struct.unpack_from("<I", binary, argv + i * 4)[0] for i in range(count)]
            if name in ("System.Collections.Generic.Dictionary`2", "System.Collections.Generic.SortedList`2") and count == 2:
                node = self.header("map")
                node["children"] = []
                for index in range(node["count"]):
                    node["children"].append(self.typed(args[0], path + f".key[{index}]", depth + 1))
                    node["children"].append(self.typed(args[1], path + f".value[{index}]", depth + 1))
            elif name == "System.Collections.Generic.List`1" and count == 1:
                node = self.header("array")
                node["children"] = [self.typed(args[0], path + f"[{i}]", depth + 1) for i in range(node["count"])]
            elif name == "System.Nullable`1" and count == 1:
                return self.typed(args[0], path, depth + 1)
            else:
                raise ValueError("Unsupported selected ability generic: " + name)
            node["end"] = self.pos
            return node
        if kind in (17, 18):
            name = a.type_name(data) if self.original else self.schema.source.name(data)
            return self.class_value(name, path, depth + 1)
        return self.scalar(kind, path)

    def class_value(self, name, path, depth=0):
        nil = self.nullable(path)
        if nil:
            return nil
        if name == DYNAMIC:
            node = self.dynamic(self.strings)
            return self.leaf(path, node)
        if name == CAMERA_SHAKE and self.schema.profile in NEWBIE_PROFILES and self.data[self.pos] not in (*range(0x90, 0xa0), 0xdc, 0xdd):
            node = self.node()
            index = monster.decode_integer(self.data, node)
            accepted_indices = getattr(self.schema, "camera_indices", (127, 188, 205) if self.schema.profile == "act101_entry" else (127, 205))
            if node["kind"] != "scalar" or index not in accepted_indices:
                raise ValueError(f"Unaudited CameraShake index{index} at {path} / {node['start']}")
            self.schema.camera_dependency(self.strings)
            if not self.original:
                self.schema.indexed_references.append({"type": name, "path": path, "index": index, "source_byte_span": [node["start"], node["end"]]})
            return self.leaf(path, node)
        if name == ARROW_ARGUMENT and self.schema.profile == "act101_entry" and self.data[self.pos] not in (*range(0x90, 0xa0), 0xdc, 0xdd):
            node = self.node()
            index = monster.decode_integer(self.data, node)
            dependency=self.schema.arrow_dependency(self.strings)
            if node["kind"] != "scalar" or index not in dependency['validated_indices']:
                raise ValueError("Indexed projectile argument lacks matching original/source consumer proof: "+str(index))
            if not self.original:
                self.schema.indexed_references.append({"type": name, "path": path, "index": index,
                                                      "source_byte_span": [node["start"], node["end"]]})
            return self.leaf(path, node)
        if name in (ACTION, MIXIN, PREDICATE, STATE_OPTION) or (name == MIXIN_ARGUMENT and self.schema.profile == "act101_entry"):
            node = self.header("array")
            if node["count"] != 2:
                raise ValueError("Ability union must remain tag/payload array2")
            tag_node = self.node()
            source_tag = monster.decode_integer(self.data, tag_node)
            concrete, target_tag = self.schema.union(name, source_tag, self.original)
            if not self.original and target_tag is not None and source_tag != target_tag:
                self.edits.append((tag_node["start"], tag_node["end"], integer_bytes(target_tag)))
                self.records.append({"operation": "union_tag_same_type", "path": path,
                                     "source_tag": source_tag, "original_tag": target_tag, "concrete": concrete,
                                     "source_byte_span": [tag_node["start"], tag_node["end"]]})
            node["children"] = [tag_node, self.class_value(concrete, path + "<" + concrete + ">", depth + 1)]
            if name in (ACTION, MIXIN):
                tail = self.node()
                identity = monster.decode_integer(self.data, tail)
                if not 0 <= identity < 1 << 31:
                    raise ValueError("Custom action/mixin configLocalID must be nonnegative Int32")
                self.leaf(path + ".configLocalID", tail)
            node["end"] = self.pos
            if concrete == STATISTICS:
                prefix = path + "<" + STATISTICS + ">."
                expected = {"StatisticsID.isDynamic": "c0", "StatisticsID.fixedValue": "ce000c38f3", "StatisticsID.dynamicKey": "c0",
                            "Value.isDynamic": "c0", "Value.fixedValue": "ca3f800000", "Value.dynamicKey": "c0",
                            "Target": "c0", "TargetOption": "c0", "Predicates": "c0", "MPTotallyLocal": "c0"}
                actual = {key[len(prefix):]: self.data[leaf["span"][0]:leaf["span"][1]].hex()
                          for key, leaf in self.leaves.items() if key.startswith(prefix)}
                statistics_id = 801011
                if getattr(self.schema, "avatar_cultivation", False) and actual.get("StatisticsID.fixedValue") == "ce000c3cdb":
                    expected["StatisticsID.fixedValue"] = "ce000c3cdb"
                    statistics_id = 802011
                # Explicit batch profiles may supply independently checked
                # later2.2 Score IDs; legacy profiles retain their frozen bound.
                encoded_id = actual.get("StatisticsID.fixedValue", "")
                for candidate in getattr(self.schema, "later_score_ids", ()):
                    if encoded_id == (b"\xce" + struct.pack(">I", candidate)).hex():
                        expected["StatisticsID.fixedValue"] = encoded_id
                        statistics_id = candidate
                if getattr(self.schema, "batch_later_score", False):
                    # These are independently sourced post1.9 Score rows. The
                    # entire later statistics action (not a combat action) is
                    # unavailable in original1.9; preserve every other action.
                    candidates = getattr(self.schema, "later_score_ids", ())
                    ident = self.leaves.get(prefix + "StatisticsID.fixedValue")
                    dyn = actual.get("StatisticsID.isDynamic")
                    if ident and dyn in ("c0", "c2") and actual.get("StatisticsID.dynamicKey") == "c0":
                        q = MessagePackSpanReader(self.data); q.pos = ident["span"][0]
                        value = monster.decode_integer(self.data, q.node())
                        if value in candidates:
                            statistics_id = value
                            expected = actual
                if self.original or self.schema.profile not in AVATAR_PROFILES or actual != expected:
                    raise ValueError("Only the audited later2.2 StatisticsID801011/Value1 action may be excluded")
                node["remove_from_array"] = True
                self.records.append({"operation": "remove_later_statistics_action", "path": path,
                                     "source_byte_span": [node["start"], node["end"]], "StatisticsID": statistics_id,
                                     "Value": 1.0, "source_class": STATISTICS,
                                     "reason": "Later2.2 scoring framework unavailable in original1.9; no original action replaced"})
            if concrete in LATER_BUFF_UI_ACTIONS:
                match=re.fullmatch(r'(ability\.Modifiers\.value\[\d+\])\.(?:OnAdded|OnRemoved)\[\d+\]',path)
                leaf=self.leaves.get(match[1]+'.CustomBuffID') if match else None
                if self.original or not leaf:raise ValueError('UI-only action outside reviewed modifier lifecycle')
                q=MessagePackSpanReader(self.data);q.pos=leaf['span'][0]
                buff=monster.decode_integer(self.data,q.node())
                if buff not in getattr(self.schema,'ui_custom_buff_ids',()):raise ValueError('Unreviewed later UI buff ID')
                node['remove_from_array']=True
                self.records.append({'operation':'remove_later_ui_action','path':path,
                    'source_byte_span':[node['start'],node['end']],'CustomBuffID':buff,'source_class':concrete,
                    'reason':'Source Call only invokes Add/RemoveCustomBuffHandler, whose consumers are later buff-panel UI; original1.9 lacks this presentation feature. Combat actions retained.'})
            return node
        self.schema.check(name)
        members = self.schema.members(name, self.original)
        if any(field == "value__" for field, _ in members):
            return self.scalar(self.schema.info(members[0][1], self.original)["kind"], path)
        node = self.header("array")
        if node["count"] != len(members):
            raise ValueError(f"Selected ability logical field count changed: {name}/{node['count']}/{len(members)}")
        children = []
        for field, pointer in members:
            child = self.typed(pointer, path + "." + field, depth + 1)
            if not self.original and getattr(self.schema, "avatar_cultivation", False) and name in getattr(self.schema, "fixed_global_types", ("MoleMole.Config.AddGlobalValue",)) and field == "Key":
                if child["kind"] != "array" or child["count"] != 3:
                    raise ValueError("Fixed global key wrapper must be array3")
                dynamic, fixed, dynamic_key = child["children"]
                if dynamic["code"] not in (0xc0, 0xc2) or fixed["code"] == 0xc0 or dynamic_key["code"] != 0xc0:
                    raise ValueError("Dynamic global keys cannot be flattened")
                fixed_name = monster.string_index(self.data, fixed, self.strings)
                if fixed_name not in getattr(self.schema, "fixed_global_keys", ("_GLOBAL_CK_EVADE_ATK_CHARGE",)):
                    raise ValueError("Only the actual Mei507 fixed global key is supported")
                replacement = self.data[fixed["start"]:fixed["end"]]
                self.edits.append((child["start"], child["end"], replacement))
                self.records.append({"operation": "unwrap_fixed_string", "path": path + ".Key",
                    "source_byte_span": [child["start"], child["end"]], "fixed_value_span": [fixed["start"], fixed["end"]],
                    "fixed_value_hex": replacement.hex(), "fixed_value": fixed_name,
                    "reason": "Source Evaluate58144 returns fixedValue for false isDynamic; original AddGlobalValue reads primitive Key"})
                for suffix in ("isDynamic", "fixedValue", "dynamicKey"):
                    del self.leaves[path + ".Key." + suffix]
                self.leaf(path + ".Key", fixed)
            children.append(child)
            excluded = self.schema.checks[name].get("excluded_fields", [])
            if not self.original and field in excluded:
                ui_custom_buff = (name == MODIFIER and field == 'CustomBuffID'
                    and child['kind']=='scalar' and child['code']!=0xc0
                    and monster.decode_integer(self.data,child) in getattr(self.schema,'ui_custom_buff_ids',()))
                native_acceleration=(getattr(self.schema,'native_lock_acceleration_bridge',False)
                    and name=='MoleMole.Config.LockFaceForwardMixin' and field=='DefaultAcceleration'
                    and self.data[child['start']:child['end']]==bytes.fromhex('ca41800000'))
                if child["code"] != 0xc0 and not ui_custom_buff and not native_acceleration:
                    raise ValueError("Only audited nil later fields may be removed: " + path + "." + field)
                self.edits.append((child["start"], child["end"], b""))
                self.records.append({"operation": "remove_later_field", "path": path + "." + field,
                                     "source_byte_span": [child["start"], child["end"]],
                                     "source_hex": self.data[child["start"]:child["end"]].hex(),
                                     **({'reason':f'Later CustomBuff{monster.decode_integer(self.data,child)} presentation registry: Add/Remove handlers emit UI events; GetAllCustomBuffModifiers consumer is MonoInLevelBuffPanel.SetupBuffPanel. Original1.9 has no such field; all combat modifier fields/actions retained.'} if ui_custom_buff else {})})
                if native_acceleration:
                    self.records.append({'operation':'native_lock_acceleration_parameter','path':path+'.'+field,
                        'float_hex':'ca41800000','value':16.,'semantics':'Retained through tagged ARM speed-ramp bridge, not discarded'})
        excluded = self.schema.checks[name].get("excluded_fields", [])
        if excluded and not self.original:
            self.edits.append((node["start"], node["header_end"], array_bytes(len(members) - len(excluded))))
        if not self.original and self.schema.profile == "act101_entry" and name == "MoleMole.Config.ShieldMixin":
            left, right = children[6]["start"], children[8]["end"]
            value = b"".join(self.data[children[index]["start"]:children[index]["end"]] for index in (7, 8, 6))
            if any(left < end and start < right for start, end, _ in self.edits):
                raise ValueError("Shield reorder overlaps a nested adaptation")
            self.edits.append((left, right, value))
            self.records.append({"operation": "reorder_original_fields", "path": path,
                "source_byte_span": [left, right], "source_field_order": ["ForceResumeRatio", "MinForceResumeCD", "UseLevelTimeScale"],
                "original_field_order": ["MinForceResumeCD", "UseLevelTimeScale", "ForceResumeRatio"],
                "source_hex": self.data[left:right].hex(), "output_hex": value.hex(),
                "retained_field_encodings_unchanged": True})
        node["children"] = children
        node["base_end"] = self.pos
        if name == MODIFIER:
            tail = self.node()
            identity = monster.decode_integer(self.data, tail)
            if not 0 <= identity < 1 << 31:
                raise ValueError("Custom modifier configLocalID must be nonnegative Int32")
            self.leaf(path + ".configLocalID", tail)
            tail = self.node()
            if tail["code"] != 0xc0:
                monster.string_index(self.data, tail, self.strings)
            self.leaf(path + ".ModifierName", tail)
            tail = self.node()
            mode = monster.decode_integer(self.data, tail)
            if not 0 <= mode <= 255:
                raise ValueError("Custom modifier mpBehavior must be Byte")
            self.leaf(path + ".mpBehavior", tail)
        elif name == ABILITY:
            tail = self.node()
            if tail["code"] != 0xc0:
                monster.string_index(self.data, tail, self.strings)
            self.leaf(path + ".OverrideName", tail)
        node["end"] = self.pos
        return node


def project(payload, strings, schema):
    selected = PROFILE_ROOTS[schema.profile]
    if monster.sha(payload) != SOURCE_SHA:
        raise ValueError("Only exact audited later ability container accepted")
    packed_hash, entries, overrides, packed = monster.unpack_container(payload)
    references = {offset: (key, None) for key, offset in entries}
    references.update({offset: (key, variant) for key, variant, offset in overrides})
    if set(selected) - set(references.values()):
        raise ValueError("Actual first-stage AI identities missing")
    if strings[15668] != "MonsterCommonAIAbility" or strings[8956] != "DeadWalker" or strings[21824] != "UlyssesWarrior":
        raise ValueError("Actual stage AI source string identities changed")
    boundaries = sorted(references) + [len(packed)]
    output, new_offsets, records = bytearray(), {}, []
    for start, end in zip(boundaries, boundaries[1:]):
        new_offsets[start] = len(output)
        identity = references[start]
        if identity not in selected:
            output.extend(packed[start:end])
            continue
        reader = AbilityReader(packed, strings, schema)
        reader.pos = start
        reader.class_value(ABILITY, "ability")
        if reader.pos != end:
            raise ValueError(f"Source custom ability root boundary mismatch: {selected[identity]}/{reader.pos}/{end}")
        value, cursor = bytearray(), start
        for left, right, replacement in sorted(reader.edits):
            if not cursor <= left < right <= end:
                raise ValueError("Overlapping or unbounded ability projection edits")
            value.extend(packed[cursor:left]); value.extend(replacement); cursor = right
        value.extend(packed[cursor:end])
        check = AbilityReader(bytes(value), strings, schema, True)
        check.class_value(ABILITY, "ability")
        if check.pos != len(value):
            raise ValueError("Projected original custom AI consumer boundary mismatch")
        removed_fields = {item["path"] for item in reader.records if item["operation"] == "remove_later_field"}
        removed_actions = [item["path"] for item in reader.records if item["operation"] == "remove_later_statistics_action"]
        retained = {path: leaf for path, leaf in reader.leaves.items()
                    if path not in removed_fields and not any(path.startswith(prefix + "<") or path.startswith(prefix + ".") for prefix in removed_actions)}
        if set(retained) != set(check.leaves) or any(leaf["sha256"] != check.leaves[path]["sha256"] for path, leaf in retained.items()):
            raise ValueError("Retained ability terminal field value changed")
        records.append({"identity": selected[identity], "key": identity[0], "variant": identity[1],
                        "source_byte_span": [start, end], "output_byte_span": [len(output), len(output) + len(value)],
                        "source_sha256": monster.sha(packed[start:end]), "output_sha256": monster.sha(value),
                        "adaptations": reader.records, "retained_terminal_value_count": len(retained),
                        "retained_terminal_values_byte_identical": True,
                        "retained_terminal_values": [{"path": path, "source": leaf, "output": check.leaves[path]} for path, leaf in retained.items()]})
        output.extend(value)
    new_entries = [(key, new_offsets[offset]) for key, offset in entries]
    new_overrides = [(key, variant, new_offsets[offset]) for key, variant, offset in overrides]
    final = monster.pack_container(packed_hash, new_entries, new_overrides, bytes(output))
    if schema.profile == "act101_entry":
        previous = (NEWBIE_OUTPUT / PATH).read_bytes()
        if monster.sha(previous) != "a94ae1f6fe79b96d5abba82f46fc27e73a0e2a112e0bae7aa061d76fbe179b4e":
            raise ValueError("Preserve frozen fourteen-root ability baseline")
        _, previous_entries, previous_overrides, previous_packed = monster.unpack_container(previous)
        previous_refs = {offset: (key, None) for key, offset in previous_entries}
        previous_refs.update({offset: (key, variant) for key, variant, offset in previous_overrides})
        previous_spans = {previous_refs[left]: (left, right) for left, right in zip(sorted(previous_refs), sorted(previous_refs)[1:] + [len(previous_packed)])}
        for left, right in zip(boundaries, boundaries[1:]):
            identity = references[left]
            if identity in NEWBIE_SELECTED:
                before, after = previous_spans[identity]
                if output[new_offsets[left]:new_offsets.get(right, len(output))] != previous_packed[before:after]:
                    raise ValueError("Previous accepted ability root changed: " + NEWBIE_SELECTED[identity])
    # Verify every unselected root using old/new exact offset mapping.
    unchanged = 0
    for start, end in zip(boundaries, boundaries[1:]):
        if references[start] not in selected:
            new_start = new_offsets[start]
            new_end = new_offsets.get(end, len(output))
            if packed[start:end] != output[new_start:new_end]:
                raise ValueError("Unselected ability bytes changed")
            unchanged += 1
    return final, {"roots": records, "selected_roots": len(records), "unselected_roots": unchanged,
                   "unselected_roots_byte_identical": True, "all_keys_and_order_preserved": True,
                   "all_offsets_recomputed": True, "source_counts": [len(entries), len(overrides), len(packed)],
                   "output_counts": [len(entries), len(overrides), len(output)], "source_packed_hash_preserved": packed_hash,
                   "union_mapping_evidence": schema.mapping_checks, "declaration_checks": list(schema.checks.values())}


def leader_reference_evidence(package, maps, schema, avatar_root, avatar_packed, strings):
    """Evidence for the single observed level1/star1 team leader dependency."""
    unlock_members = [name for name, _ in schema.members("MoleMole.Config.ConfigAvatarAbilityUnlock", True)]
    if unlock_members[:6] != ["IsUnlockBySkill", "UnlockBySkillID", "UnlockBySubSkillID", "AbilityName", "AbilityOverride", "AbilityReplaceID"] or len(unlock_members) != 12:
        raise ValueError("Original Avatar unlock field order changed")
    unlocks = avatar_root["children"][8]
    if unlocks["kind"] != "array" or unlocks["count"] != 17:
        raise ValueError("Accepted Avatar101 unlock references changed")
    metadata_path = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/avatarskilldata"
    metadata_bytes = metadata_path.read_bytes()
    if monster.sha(metadata_bytes) != "b461ecfd851450c586d065aac6a38cc659d07a7767c7b1304f4a4c818dcddea3":
        raise ValueError("Accepted skill unlock metadata changed")
    metadata_rows = json.loads(metadata_bytes)
    skill_record = maps["data/_exceloutput/avatarskilldata"]
    skill_object, skill_raw = resources.object_bytes(package, skill_record)
    if skill_object["class"] != 49:
        raise ValueError("Unlock source must be an actual TextAsset")
    _, skill_text = resources.text_asset(skill_raw)
    source_rows = list(csv.DictReader(io.StringIO(skill_text.decode("utf-8")), delimiter="\t"))
    expected = [(12, 13415, 4, 2), (14, 13417, 2, 4), (15, 13402, 1, 5)]
    actual = []
    for node, (skill_id, ability_key, unlock_level, show_order) in zip(unlocks["children"][:3], expected):
        if node["kind"] != "array" or node["count"] != 12:
            raise ValueError("Actual default unlock shape changed")
        values = node["children"]
        if values[0]["code"] != 0xc3 or monster.decode_integer(avatar_packed, values[1]) != skill_id or monster.decode_integer(avatar_packed, values[3]) != ability_key or values[2]["code"] != 0xc0 or values[4]["code"] != 0xc0:
            raise ValueError("Project only the evidenced Avatar101 skill unlock references")
        replace = None if values[5]["code"] == 0xc0 else monster.string_index(avatar_packed, values[5], strings)
        if replace != ("CAPTAIN_SKILL" if skill_id == 15 else None):
            raise ValueError("Leader skill replacement ID changed")
        rows = [row for row in metadata_rows if row["skillId"] == skill_id]
        source = [row for row in source_rows if row["skillId"] == str(skill_id)]
        if len(rows) != 1 or len(source) != 1:
            raise ValueError("Default unlock metadata row missing or duplicated")
        row, source_row = rows[0], source[0]
        if (row["unlockLv"], row["unlockStar"], row["showOrder"]) != (unlock_level, 1, show_order) or any(int(source_row[field]) != row[field] for field in ("unlockLv", "unlockStar", "showOrder")) or source_row["GameVersionBegin"] != "1.4":
            raise ValueError("Default level/star/leader eligibility changed")
        actual.append({"skill_id": skill_id, "ability_key": ability_key, "ability_name": strings[ability_key],
                       "override": None, "AbilityReplaceID": replace, "accepted_avatar_span": [node["start"], node["end"]],
                       "skill_metadata_row": row, "source_version_begin": source_row["GameVersionBegin"],
                       "level1_star1_unlocked": unlock_level <= 1, "selected": skill_id == 15})
    native = []
    for method, address in ((51659, 0x133e8c0), (51660, 0x1343c40), (51792, 0x14cd9f3),
                            (51665, 0x13441fe), (51794, 0x14ce33b), (51795, 0x14ce36e),
                            (51797, 0x14ce3d4), (59455, 0x133cdc0), (47467, 0x131f218),
                            (59454, 0x131fd33), (65050, 0x1360e34), (65039, 0x135eab9)):
        if a.pointer(a.M[method]) != address:
            raise ValueError("Original default unlock/leader consumer address changed")
        native.append({"method_index": method, "method": a.N[method], "address": hex(address),
                       "first16_sha256": monster.sha(a.E[address:address + 16])})
    trace_path = ROOT / "server19-run/diagnostics/stage-20261011-1629/offset2-after-begin.log"
    trace_bytes = trace_path.read_bytes()
    if monster.sha(trace_bytes) != "450628b22e24650878c231ca14ce01ba526366969759fd15348e67fc6b9a5219":
        raise ValueError("Observed leader failure trace changed")
    trace_lines = [line.strip() for line in trace_bytes.decode("utf-8").splitlines() if "root=0004c856 modifier=0004c86b failed=0004c894" in line]
    if len(trace_lines) != 1 or "1791712074.851  6523" not in trace_lines[0] or "source2=006b4200" not in trace_lines[0]:
        raise ValueError("Leader dependency requires the exact observed original consumer failure")
    previous = (AVATAR_OUTPUT / PATH).read_bytes()
    if monster.sha(previous) != "315adf66850f10a605d4fb96a58d8b31f109d7238a5f9bec7a34cba9f0e120f1":
        raise ValueError("Preserve the frozen ten-root baseline")
    _, entries, overrides, packed = monster.unpack_container(previous)
    captain_start = dict(entries)[13402]
    bounds = sorted([offset for _, offset in entries] + [offset for _, _, offset in overrides] + [len(packed)])
    captain_end = min(offset for offset in bounds if offset > captain_start)
    if (captain_start, captain_end) != (313430, 313519) or packed[313492:313494] != b"\xc0\x00":
        raise ValueError("Observed packed offset does not identify Captain_HPUp")
    restore_path = ROOT / "server19-run/diagnostics/stage-20261011-1629/offset-library-restore-1791712091829746300/receipt.json"
    restore_bytes = restore_path.read_bytes()
    restore = json.loads(restore_bytes)
    if monster.sha(restore_bytes) != "d509416012bd28ed2daf247ec3ad662439f003cc62d971278b7a741dfb79a9c6" or restore["status"] != "verified" or restore["after_sha256"] != "74fd781c88e82853dcce6a7dd2a9654bf863b0ed6776c22f8641f6b6fb801c72":
        raise ValueError("Temporary offset diagnostic was not verifiably restored")
    return {"fixture": {"avatar_id": 101, "level": 1, "star": 1, "team_index": 0, "proto_skill_list_present": False},
            "first_three_skill_unlocks": actual,
            "skill_metadata_dependency": {"required_existing_path": "_exceloutputasset/avatarskilldata", "output_sha256": monster.sha(metadata_bytes)},
            "source_skill_metadata": {**skill_record, "class": skill_object["class"], "source_object_sha256": monster.sha(skill_raw), "text_sha256": monster.sha(skill_text)},
            "original_native_sha256": monster.NATIVE19_SHA, "original_methods": native,
            "original_default_unlock_chain": [
                "AvatarDataItem.Init calls SetupDefaultSkillList@0x133e9d0, even without proto skill_list",
                "SetupDefaultSkillList constructs every metadata skill@0x1343da1; ctor starts isUnlocked=false",
                "UpdateSkillInfo@0x13442b6..0x13442e9 compares level>=unlockLv AND star>=unlockStar, writes isUnlocked@0x1344278",
                "IsLeaderSkill@0x14ce3f4 checks showOrder==5; CheckUnlockBySkillID requires isUnlocked and (!IsLeaderSkill OR includeLeader)",
                "CreateTeamAvatars@0x136174a..0x136179e sets both isLeader and leaderSkillOn for team index0",
                "CreateAvatar forwards both; InitAvatarDataItem@0x131f624..0x131f639 passes isLeader OR leaderSkillOn to UnlockAvatarAbilities"],
            "observed_runtime_dependency": {"trace_path": str(trace_path.relative_to(ROOT)), "trace_sha256": monster.sha(trace_bytes),
                "line": trace_lines[0], "container_sha256": monster.sha(previous), "offset_unit": "packedBytes payload-relative",
                "ability_key": 13402, "ability_name": "Kiana_PT_Captain_HPUp", "root_span": [captain_start, captain_end],
                "modifier_start": 313451, "nil_read_as_configLocalID": 313492, "actual_configLocalID": 313493,
                "temporary_diagnostic_library_restored": {"receipt_path": str(restore_path.relative_to(ROOT)), "receipt_sha256": monster.sha(restore_bytes), "after_sha256": restore["after_sha256"]}},
            "scope": "Add only the observed unlocked first-team leader Captain_HPUp root; locked skills12/14 and all other dynamic abilities remain exact source bytes"}


def newbie_reference_evidence(package, maps, schema, strings):
    metadata_path = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/newbiebattlebuff"
    metadata_bytes = metadata_path.read_bytes()
    if monster.sha(metadata_bytes) != "561a985ca2c94a3071b1d6681cd0e2efd67c637ae80e2fe27b984429fb8307ec":
        raise ValueError("Accepted Newbie level/parameter metadata changed")
    rows = [row for row in json.loads(metadata_bytes) if row["minLevel"] <= 15 <= row["maxLevel"]]
    expected = {"minLevel": 10, "maxLevel": 19, "evadeEffectCDReduce": 0.8, "extraEvadePropID": 301999,
                "evadePropParam1": 8.0, "evadePropParam2": 0.4, "evadePropParam3": 0.2, "spBuffPropID": 3,
                "spBuffPropParam1": 0.8, "spBuffPropParam2": 0.0}
    if len(rows) != 1 or any(rows[0][key] != value for key, value in expected.items()):
        raise ValueError("Only the actual account-level15 Newbie row is selected")
    meta_obj, meta_raw = resources.object_bytes(package, maps["data/_exceloutput/newbiebattlebuff"])
    if meta_obj["class"] != 49:
        raise ValueError("Newbie version evidence requires real source TextAsset")
    _, meta_text = resources.text_asset(meta_raw)
    source_rows = [row for row in csv.DictReader(io.StringIO(meta_text.decode("utf-8")), delimiter="\t") if row["minLevel"] == "10" and row["maxLevel"] == "19"]
    if len(source_rows) != 1 or source_rows[0]["GameVersionBegin"] != "1.8" or any(float(source_rows[0][key]) != value for key, value in expected.items()):
        raise ValueError("Actual source Newbie row differs from accepted original-schema metadata")
    registry_path = "_baked/bakednewbiebattlebuffdata"
    registry_bytes = (ROOT / ".local-baseline/server19-dev/baked-fallback" / registry_path).read_bytes()
    if monster.sha(registry_bytes) != "d8a0e2241bb5138d5b4695a4773f7ecb04a10ba33f1442147b29c09e990a5ab1":
        raise ValueError("Actual Newbie ability registry changed")
    schema.check("MoleMole.Config.ConfigNewbieBattleBuffEntry")
    _, registry_entries, registry_overrides, packed = monster.unpack_container(registry_bytes)
    if len(registry_entries) != 4 or registry_overrides:
        raise ValueError("Actual Newbie registry wrapper changed")
    refs = []
    for buff_id, key in ((1, 16004), (301999, 16007), (3, 16006)):
        reader = MessagePackSpanReader(packed)
        reader.pos = dict(registry_entries)[buff_id]
        node = reader.node()
        if node["kind"] != "array" or node["count"] != 9 or monster.decode_integer(packed, node["children"][0]) != buff_id or monster.decode_integer(packed, node["children"][1]) != key or node["children"][2]["code"] != 0xc0:
            raise ValueError("Preserve exact original Newbie registry references and overrides")
        refs.append({"buff_id": buff_id, "ability_key": key, "ability_name": strings[key], "override": None,
                     "registry_span": [node["start"], node["end"]], "registry_entry_sha256": monster.sha(packed[node["start"]:node["end"]])})
    count, table = struct.unpack_from("<II", a.E, 0x34a67d4)
    if count != len(a.T):
        raise ValueError("Original field offset registration changed")
    field_checks = []
    for owner, name, expected_offset in (("MoleMole.LevelScoreManager", "LevelType", 0x1c),
                                        ("MoleMole.LevelScoreManager", "isDebugLevel", 0x64),
                                        ("MoleMole.LevelActor", "levelMode", 0xe4),
                                        ("MoleMole.PlayerDataItem", "teamLevel", 0x18)):
        index = schema.original_names[owner]
        definition = a.T[index]
        offset_pointer = struct.unpack_from("<I", a.E, table + index * 4)[0]
        offsets = {a.string(struct.unpack_from("<4I", a.B, 9233316 + field * 16)[0]): struct.unpack_from("<i", a.E, offset_pointer + ordinal * 4)[0]
                   for ordinal, field in enumerate(range(definition[16], definition[16] + definition[26]))}
        if offsets.get(name) != expected_offset:
            raise ValueError("Original Newbie gate field offset changed")
        field_checks.append({"type": owner, "field": name, "offset": hex(expected_offset)})
    if a.E[0x116d908:0x116d90d] != b"\xb8\x01\x00\x00\x00":
        raise ValueError("Original evadeCDReducePropID no longer returns1")
    trace_path = ROOT / "server19-run/diagnostics/stage-20261011-1629/offset3-after-begin.log"
    trace_bytes = trace_path.read_bytes()
    if monster.sha(trace_bytes) != "ee51b0a488b429dc158990d823e06e3da04f913ded80b73785f15cdfcfa4c9c8":
        raise ValueError("Observed Newbie failure trace changed")
    trace_lines = [line.strip() for line in trace_bytes.decode("utf-8").splitlines() if "root=000edc83 modifier=000edc98 failed=000edcc1" in line]
    if len(trace_lines) != 1 or "1791712685.688  8116" not in trace_lines[0] or "source2=006b4200" not in trace_lines[0]:
        raise ValueError("Newbie profile requires the observed original consumer failure")
    previous = (LEADER_OUTPUT / PATH).read_bytes()
    if monster.sha(previous) != "df9864e76dd7fdb86325815e8af6bbd797cf20dc8c10297ff7768d710b7294d7":
        raise ValueError("Preserve the frozen eleven-root baseline")
    _, entries, overrides, previous_packed = monster.unpack_container(previous)
    start = dict(entries)[16004]
    end = min(offset for offset in [item[1] for item in entries] + [item[2] for item in overrides] + [len(previous_packed)] if offset > start)
    if start != 973955 or previous_packed[974017:974019] != b"\xc0\x00":
        raise ValueError("Observed packed offset does not identify Newbie EvadeCDReduce")
    restore_path = ROOT / "server19-run/diagnostics/stage-20261011-1629/offset-library-restore-1791712703518929700/receipt.json"
    restore_bytes = restore_path.read_bytes()
    restore = json.loads(restore_bytes)
    if monster.sha(restore_bytes) != "2ea73d9e8335fb66be991b7f71e032bde1719365aae5a72ebc4a34495d07162a" or restore["status"] != "verified" or restore["after_sha256"] != "74fd781c88e82853dcce6a7dd2a9654bf863b0ed6776c22f8641f6b6fb801c72":
        raise ValueError("Newbie temporary offset diagnostic was not verifiably restored")
    return {"fixture": {"account_team_level": 15, "avatar_level": 1, "avatar_star": 1, "Begin_battle_buff": [], "Begin_equip_buff": []},
            "metadata_row": rows[0], "source_metadata_version_begin": source_rows[0]["GameVersionBegin"],
            "source_metadata": {**maps["data/_exceloutput/newbiebattlebuff"], "source_object_sha256": monster.sha(meta_raw), "text_sha256": monster.sha(meta_text)},
            "metadata_dependency": {"required_existing_path": "_exceloutputasset/newbiebattlebuff", "output_sha256": monster.sha(metadata_bytes)},
            "registry_dependency": {"required_existing_path": registry_path, "output_sha256": monster.sha(registry_bytes)},
            "original_gate_field_offsets": field_checks, "original_native_sha256": monster.NATIVE19_SHA,
            "original_execution_chain": ["InitAvatarDataItem47467 invokes InitNewbieBattleBuff47469@0x131f747 after leader abilities",
                "InitNewbie47469@0x1320d0a requires LevelType1/2, levelMode!=3, !isDebugLevel; these are not isTryLevel or avatar-level gates",
                "HasNewbieBattleBuffForPlayer60574@0x116fe41 checks PlayerDataItem.teamLevel against accepted metadata min/max",
                "TryGetNewbieBattleBuffDataItemForPlayer60573@0x116fa3f selects matching account-level row",
                "get_evadeCDReducePropID68535@0x116d902 returns1; InitNewbie Apply calls0x1320eed/0x1320f35/0x1320f72 load ID1/extraEvadePropID/spBuffPropID in that order",
                "ApplyNewbieBattleBuffEntry59897@0x116e430 loads original AbilityName/override with GetAbilityConfig@0x116e4cf; Begin buff lists are not required"],
            "actual_ability_refs_in_execution_order": refs,
            "observed_runtime_dependency": {"trace_path": str(trace_path.relative_to(ROOT)), "trace_sha256": monster.sha(trace_bytes), "line": trace_lines[0],
                "container_sha256": monster.sha(previous), "offset_unit": "packedBytes payload-relative", "ability_key": 16004,
                "root_span": [start, end], "modifier_start": 973976, "nil_read_as_configLocalID": 974017, "actual_configLocalID": 974018,
                "temporary_diagnostic_library_restored": {"receipt_path": str(restore_path.relative_to(ROOT)), "receipt_sha256": monster.sha(restore_bytes), "after_sha256": restore["after_sha256"]}},
            "scope": "Add only all three actual consecutive native Newbie dependencies; preserve metadata parameters, HP/SP/damage values and native loading conditions"}


def act101_reference_evidence(package, maps, schema, strings, actor_evidence, projection):
    """Bound the new roots to Normal10101..10106 and actual set2/unlock refs."""
    lua_path = ROOT / ".local-baseline/server19-dev/act101-entry-lua-resources/manifest.json"
    lua_bytes = lua_path.read_bytes()
    if monster.sha(lua_bytes) != "afe248c042625ca5df6e419473418605839e6da20721f7a43a824f765fa5a9d3":
        raise ValueError("Actual six-stage Lua closure changed")
    lua = json.loads(lua_bytes)
    if lua["stage_ids"] != list(range(10101, 10107)) or lua["mode"] != "Normal":
        raise ValueError("Only six Normal stage entries are supported")
    elite_names = {wave["monster"] for stage in lua["stage_evidence"] for wave in stage["normal_monster_waves"] if wave["isElite"]}
    if elite_names != {"DeadWalker", "DeadArcher", "UlyssesFast"}:
        raise ValueError("Actual Normal Elite override set changed")
    base_path = ROOT / ".local-baseline/server19-dev/stage10101-with-tutorial-resources/lua/base/leveldesignnormal.lua"
    base_bytes = base_path.read_bytes()
    expected_base = next(row["output_sha256"] for row in lua["required_existing_files"] if row["path"] == "lua/base/leveldesignnormal.lua")
    if monster.sha(base_bytes) != expected_base:
        raise ValueError("Preserve accepted native-signature base Lua")
    base_lines = base_bytes.decode("utf-8").splitlines()
    snippets = []
    for fragment in ("wave.attr.Monster_Special_AttackRatio = {AttackRatio = -0.2}", "if not abilityTable.Elite_EliteShield then", "abilityDetail.OverrideName = name"):
        matches = [{"line": i + 1, "text": line.strip()} for i, line in enumerate(base_lines) if fragment in line]
        if not matches:
            raise ValueError("Real base Lua implicit monster dependency changed")
        snippets.extend(matches)
    monster_path = ROOT / ".local-baseline/server19-dev/act101-entry-monster-resources/_baked/bakedmonsterdata"
    monster_bytes = monster_path.read_bytes()
    if monster.sha(monster_bytes) != "6608058b07fc8229daab5355b1ea59a841ee5f802d13aa81d3d889f01fa38b51":
        raise ValueError("Actual two added monster projections changed")
    _, entries, _, packed = monster.unpack_container(monster_bytes)
    actual_monster_refs = []
    for key, name in ((8522, "DG_020_Config"), (20957, "UL_020_Config")):
        if strings[key] != name:
            raise ValueError("New Normal monster config identity changed")
        reader = monster.MonsterReader(packed)
        reader.pos = dict(entries)[key]
        root = reader.root(strings, 19)
        abilities = root["children"][6]
        if abilities["kind"] != "map":
            raise ValueError("Actual monster ability references must be a map")
        for entry, value in zip(abilities["children"][::2], abilities["children"][1::2]):
            if value["kind"] != "array" or value["count"] != 2:
                raise ValueError("Actual monster ability reference changed")
            ability_key = monster.decode_integer(packed, value["children"][0])
            override = None if value["children"][1]["code"] == 0xc0 else monster.decode_integer(packed, value["children"][1])
            actual_monster_refs.append({"config_key": key, "config_name": name,
                "entry_name": monster.string_index(packed, entry, strings), "ability_key": ability_key,
                "ability_name": strings[ability_key], "override_key": override,
                "override_name": None if override is None else strings[override], "reference_span": [value["start"], value["end"]]})
    if {(row["ability_key"], row["override_key"]) for row in actual_monster_refs} != {(15668, 8938), (15668, 21812), (15725, None), (18987, 8508)}:
        raise ValueError("New Normal monster ability closure changed")
    set_path = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/equipmentsetdata"
    set_bytes = set_path.read_bytes()
    set_rows = [row for row in json.loads(set_bytes) if row["ID"] == 2]
    if len(set_rows) != 1 or any(set_rows[0][field] != value for field, value in {"prop1ID": 40, "spellEffectNum1": 2, "prop1Param1": 0.08, "prop2ID": 44, "spellEffectNum2": 3, "prop2Param1": 0.2}.items()):
        raise ValueError("Actual set2 thresholds/parameters changed")
    source_obj, source_raw = resources.object_bytes(package, maps["data/_exceloutput/equipmentsetdata"])
    _, source_text = resources.text_asset(source_raw)
    source_rows = [row for row in csv.DictReader(io.StringIO(source_text.decode("utf-8")), delimiter="\t") if row["ID"] == "2"]
    if source_obj["class"] != 49 or len(source_rows) != 1 or any(float(source_rows[0][field]) != set_rows[0][field] for field in ("prop1ID", "spellEffectNum1", "prop1Param1", "prop2ID", "spellEffectNum2", "prop2Param1")):
        raise ValueError("Set2 accepted values differ from real source")
    equip_path = "_baked/bakedequipskilldata"
    equip_bytes = (ROOT / ".local-baseline/server19-dev/baked-fallback" / equip_path).read_bytes()
    schema.check("MoleMole.Config.ConfigEquipmentSkillEntry")
    _, equip_entries, _, equip_packed = monster.unpack_container(equip_bytes)
    equip_refs = []
    for prop, ability_key, parameter in ((40, 10824, "AttackRatioUp"), (44, 10859, "DefenceRatioUp")):
        reader = MessagePackSpanReader(equip_packed)
        reader.pos = dict(equip_entries)[prop]
        node = reader.node()
        if node["kind"] != "array" or node["count"] != 18 or monster.decode_integer(equip_packed, node["children"][0]) != prop or monster.decode_integer(equip_packed, node["children"][1]) != ability_key or node["children"][2]["code"] != 0xc0 or monster.string_index(equip_packed, node["children"][10], strings) != parameter:
            raise ValueError("Actual original18-field equip skill dependency changed")
        equip_refs.append({"prop_id": prop, "ability_key": ability_key, "ability_name": strings[ability_key], "override": None,
            "ParamSpecial1": parameter, "registry_span": [node["start"], node["end"]], "registry_root_sha256": monster.sha(equip_packed[node["start"]:node["end"]])})
    unlocks = actor_evidence["leader_unlock_evidence"]["first_three_skill_unlocks"]
    unlocked = [{**row, "selected": True, "current_avatar_level5_star1_eligible": row["skill_metadata_row"]["unlockLv"] <= 5} for row in unlocks]
    if {(row["skill_id"], row["ability_key"]) for row in unlocked} != {(12, 13415), (14, 13417), (15, 13402)} or not all(row["current_avatar_level5_star1_eligible"] for row in unlocked):
        raise ValueError("Only real eligible skill12/14 and prior leader references may be selected")
    camera188 = [item for item in schema.indexed_references if item["type"] == CAMERA_SHAKE and item["index"] == 188]
    arrow34 = [item for item in schema.indexed_references if item["type"] == ARROW_ARGUMENT]
    if len(camera188) != 4 or len(arrow34) != 1 or arrow34[0]["index"] != 34 or schema.arrow_evidence is None:
        raise ValueError("Actual Elite/arrow indexed dependency count changed")
    if projection["selected_roots"] != 28 or set(ACT101_SELECTED) - set(NEWBIE_SELECTED) != {(15668, 8938), (15668, 21812), (15725, None), (18987, None), (18987, 8508), (9509, None), (9509, 8956), (9509, 8938), (9509, 21812), (15808, None), (10824, None), (10859, None), (13415, None), (13417, None)}:
        raise ValueError("Preserve exact bounded fourteen-root extension")
    old_bytes = (NEWBIE_OUTPUT / PATH).read_bytes()
    if monster.sha(old_bytes) != "a94ae1f6fe79b96d5abba82f46fc27e73a0e2a112e0bae7aa061d76fbe179b4e":
        raise ValueError("Frozen fourteen-root accepted ability baseline changed")
    return {"stage_ids": list(range(10101, 10107)), "mode": "Normal", "lua_manifest_path": str(lua_path.relative_to(ROOT)),
        "lua_manifest_sha256": monster.sha(lua_bytes), "stage_evidence": lua["stage_evidence"],
        "monster_dependency": {"required_existing_path": "_baked/bakedmonsterdata", "output_sha256": monster.sha(monster_bytes)},
        "new_monster_actual_ability_refs": actual_monster_refs,
        "implicit_base_lua_evidence": {"required_existing_path": "lua/base/leveldesignnormal.lua", "output_sha256": expected_base, "source_lines": snippets,
            "Normal_automatic_attack_ratio": -0.2, "elite_override_names": sorted(elite_names), "primary_fallback": ["Monster_Special_AttackRatio", "ShootArrowAttackID", "Elite_EliteShield"]},
        "current_unlock_evidence": {"fixture_source": "Parent observed chain account Avatar101 LV5 exp8/star1 after real and authorized simulated first clears", "skills": unlocked,
            "original_default_unlock_chain": actor_evidence["leader_unlock_evidence"]["original_default_unlock_chain"]},
        "equipment_set2": {"metadata_dependency": {"required_existing_path": "_exceloutputasset/equipmentsetdata", "output_sha256": monster.sha(set_bytes)},
            "metadata_row": set_rows[0], "source_row": source_rows[0], "source_object_sha256": monster.sha(source_raw), "source_text_sha256": monster.sha(source_text),
            "registry_dependency": {"required_existing_path": equip_path, "output_sha256": monster.sha(equip_bytes)}, "actual_ability_refs": equip_refs,
            "original_native_chain": "AddAvatarSetEquipSkillAbilities59787@9cbbc9 -> GetOwnSetSkills -> GetSkillParam1(1)@9cbd48 -> ApplyEquipSkillEntry59784@9cb440 -> GetAbilityConfig/CreateAppliedAbility -> SetupParamSpecial@9cb5ae",
            "scope": "Real stigmata30004/30057/30110 set2 only; weapon20041 and each individual reward have prop1/2/3ID0; set1 with one piece cannot trigger"},
        "required_previous_ability_sha256": monster.sha(old_bytes), "new_roots": [{"key": key, "variant": variant, "identity": ACT101_SELECTED[key, variant]} for key, variant in sorted(set(ACT101_SELECTED) - set(NEWBIE_SELECTED), key=lambda x: (x[0], -1 if x[1] is None else x[1]))]}


def build_prop_box(apk19, apk24):
    """Add only the actual GeneralBox ability dependency to frozen Act101 data.

    Keep the original profiles and their manifests unchanged. This independent
    profile has one extra same-concrete union discriminator conversion; it
    does not extend the gameplay/account gate or alter prop balance fields.
    """
    source, previous, baseline = build(apk19, apk24, "act101_entry")
    accepted = (ACT101_OUTPUT / PATH).read_bytes()
    if monster.sha(previous) != ACT101_ACCEPTED_SHA or previous != accepted:
        raise ValueError("Preserve the accepted twenty-eight-root Act101 ability baseline")
    strings_path = ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/stringmap.txt"
    string_bytes = strings_path.read_bytes()
    if monster.sha(string_bytes) != monster.STRINGMAP_SHA:
        raise ValueError("Preserve the original accepted StringMap identity")
    strings = string_bytes.decode("utf-8").split("\x1f")
    if strings[PROP_BOX_KEY[0]] != PROP_BOX_NAME:
        raise ValueError("Actual GeneralBox ability identity changed")
    prop_path = ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/bakedpropdata"
    prop_bytes = prop_path.read_bytes()
    if monster.sha(prop_bytes) != "82b6189b92368e407a246b133eb82f88806d447c86be64c9857062e0198c65f3":
        raise ValueError("GeneralBox reference evidence must use the exact inspected source prop container")
    _, prop_entries, prop_overrides, prop_packed = monster.unpack_container(prop_bytes)
    if prop_overrides or strings[12099] != "GeneralBox":
        raise ValueError("GeneralBox source registry identity changed")
    prop_reader = MessagePackSpanReader(prop_packed)
    prop_reader.pos = dict(prop_entries)[12099]
    prop = prop_reader.node()
    if (prop["count"] != 8 or monster.sha(prop_packed[prop["start"]:prop["end"]]) !=
            "508d5dca61e443d0bada3087431c063965e84b99b7b2a9000a36ecbc2dc6db46"):
        raise ValueError("Actual GeneralBox baked eight-field root changed")
    refs = prop["children"][5]
    if (refs["kind"] != "array" or refs["count"] != 1 or refs["children"][0]["count"] != 2 or
            monster.decode_integer(prop_packed, refs["children"][0]["children"][0]) != PROP_BOX_KEY[0] or
            refs["children"][0]["children"][1]["code"] != 0xc0):
        raise ValueError("Only the actual GeneralBox nil-override ability dependency is supported")

    def roots(payload):
        packed_hash, entries, overrides, packed = monster.unpack_container(payload)
        refs = {offset: (key, None) for key, offset in entries}
        refs.update({offset: (key, variant) for key, variant, offset in overrides})
        spans = {refs[left]: (left, right) for left, right in
                 zip(sorted(refs), sorted(refs)[1:] + [len(packed)])}
        return packed_hash, entries, overrides, packed, refs, spans

    _, _, _, packed, _, source_spans = roots(source)
    start, end = source_spans[PROP_BOX_KEY]
    if monster.sha(packed[start:end]) != PROP_BOX_SOURCE_ROOT_SHA:
        raise ValueError("Only the exact inspected GeneralBox ability root is projected")
    with zipfile.ZipFile(apk24) as package:
        schema = Schema(package, "act101_entry")
        reader = AbilityReader(packed, strings, schema)
        reader.pos = start
        reader.class_value(ABILITY, "ability")
        if reader.pos != end or len(reader.records) != 1 or len(reader.edits) != 1:
            raise ValueError("Unexpected extra GeneralBox ability adaptation or root tail")
        operation = reader.records[0]
        expected = {"operation": "union_tag_same_type", "path": "ability.AbilityMixins[0]",
                    "source_tag": 134, "original_tag": 126,
                    "concrete": "MoleMole.Config.MonsterBlurDistanceBeyondMixin"}
        if any(operation.get(key) != value for key, value in expected.items()):
            raise ValueError("Only the evidenced same-concrete GeneralBox mixin tag is supported")
        left, right, replacement = reader.edits[0]
        if packed[left:right] != b"\xcc\x86" or replacement != b"\x7e":
            raise ValueError("Actual GeneralBox tag encoding changed")
        value = packed[start:left] + replacement + packed[right:end]
        check = AbilityReader(value, strings, schema, True)
        check.class_value(ABILITY, "ability")
        if check.pos != len(value) or set(reader.leaves) != set(check.leaves) or any(
                leaf["sha256"] != check.leaves[path]["sha256"] for path, leaf in reader.leaves.items()):
            raise ValueError("Original GeneralBox consumer boundary or retained terminal values differ")
        additional_checks = list(schema.checks.values())
        mapping_evidence = schema.mapping_checks
        terminals = [{"path": path, "source": leaf, "output": check.leaves[path]}
                     for path, leaf in reader.leaves.items()]

    packed_hash, entries, overrides, old_packed, old_refs, old_spans = roots(previous)
    old_start, old_end = old_spans[PROP_BOX_KEY]
    if old_packed[old_start:old_end] != packed[start:end]:
        raise ValueError("Previously unselected GeneralBox root is no longer source exact")
    output = bytearray()
    new_offsets = {}
    for before, after in zip(sorted(old_refs), sorted(old_refs)[1:] + [len(old_packed)]):
        new_offsets[before] = len(output)
        output.extend(value if old_refs[before] == PROP_BOX_KEY else old_packed[before:after])
    payload = monster.pack_container(packed_hash, [(key, new_offsets[offset]) for key, offset in entries],
                                    [(key, variant, new_offsets[offset]) for key, variant, offset in overrides], bytes(output))
    _, new_entries, new_overrides, new_packed, _, new_spans = roots(payload)
    if ([key for key, _ in entries] != [key for key, _ in new_entries] or
            [row[:2] for row in overrides] != [row[:2] for row in new_overrides]):
        raise ValueError("GeneralBox projection must preserve all registry identities and order")
    for identity, (before, after) in old_spans.items():
        begin, finish = new_spans[identity]
        expected_bytes = value if identity == PROP_BOX_KEY else old_packed[before:after]
        if new_packed[begin:finish] != expected_bytes:
            raise ValueError("Previously accepted/unselected ability root changed unexpectedly")

    manifest = copy.deepcopy(baseline)
    projection = manifest["files"][0]["projection"]
    for row in projection["roots"]:
        row["output_byte_span"] = list(new_spans[row["key"], row["variant"]])
    projection["roots"].append({"identity": PROP_BOX_NAME, "key": PROP_BOX_KEY[0], "variant": None,
        "source_byte_span": [start, end], "output_byte_span": list(new_spans[PROP_BOX_KEY]),
        "source_sha256": monster.sha(packed[start:end]), "output_sha256": monster.sha(value),
        "adaptations": reader.records, "retained_terminal_value_count": len(terminals),
        "retained_terminal_values_byte_identical": True, "retained_terminal_values": terminals})
    projection["roots"].sort(key=lambda row: row["source_byte_span"][0])
    projection["selected_roots"] = 29
    projection["unselected_roots"] -= 1
    projection["output_counts"][-1] = len(new_packed)
    for record in mapping_evidence:
        if record not in projection["union_mapping_evidence"]:
            projection["union_mapping_evidence"].append(record)
    existing_checks = {row["type"] for row in projection["declaration_checks"]}
    projection["declaration_checks"].extend(row for row in additional_checks if row["type"] not in existing_checks)
    manifest["files"][0].update(output_sha256=monster.sha(payload), bytes=len(payload), required_existing_sha256=ACT101_ACCEPTED_SHA)
    manifest["format"] = "server19-act101-prop-box-ability-explicit-projection-v1"
    manifest["profile"] = "act101_prop_box"
    manifest.pop("stage_id", None)
    manifest["stage_ids"] = list(range(10101, 10107))
    manifest["actual_prop_box_reference_evidence"] = {
        "source_prop_path": str(prop_path.relative_to(ROOT)), "source_prop_sha256": monster.sha(prop_bytes),
        "prop_key": 12099, "prop_name": "GeneralBox", "root_span": [prop["start"], prop["end"]],
        "ability_key": PROP_BOX_KEY[0], "ability_name": PROP_BOX_NAME, "override": None,
        "reference_span": [refs["start"], refs["end"]],
        "same_concrete_union_evidence": mapping_evidence,
        "source_root_sha256": PROP_BOX_SOURCE_ROOT_SHA, "original_consumer_consumes_entire_projected_root": True,
        "previous_28_projected_roots_byte_identical": True,
        "other_4956_unselected_roots_byte_identical": projection["unselected_roots"] == 4956,
        "current_live_requested_prop_key": "not captured; do not infer a live exact key from this static dependency"}
    manifest["limits"][0] = "Only previous28 Act101 ability roots and GeneralBox's actual PropLongRangeInvicible nil-override root are selected"
    manifest["limits"][4] = "All previous28 projected roots and other4956 source roots remain byte identical; same registry keys/order and recomputed exact offsets"
    manifest["limits"].insert(1, "This dependency repair changes only same-concrete mixin tag134 to original126; no attack, health, timing or prop behavior parameter is changed")
    return source, payload, manifest


def build_avatar_cultivation(apk19, apk24, *, exclude114=False):
    """Project actual 101/201 unlock references atop the frozen29-root file.

    Old profiles/outputs are untouched. All new roots must parse with original
    concrete types and preserve retained terminal bytes before being exported.
    """
    source, previous, baseline = build_prop_box(apk19, apk24)
    if monster.sha(previous) != CULTIVATION_PREVIOUS_SHA or previous != (PROP_BOX_OUTPUT / PATH).read_bytes():
        raise ValueError("Preserve the frozen29-root deployed ability baseline")
    strings_bytes = (ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/stringmap.txt").read_bytes()
    strings = strings_bytes.decode("utf-8").split("\x1f")
    avatar_bytes = (ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/bakedavatardata").read_bytes()
    if monster.sha(avatar_bytes) != "dfd331e7b89063be037e6cfbf930fc6f48a42a9189ca3a54307c73a43bfab6e2":
        raise ValueError("Preserve the accepted 101/201 avatar reference container")
    _, avatar_entries, _, avatar_packed = monster.unpack_container(avatar_bytes)
    from server19_avatar_skills import skill_catalog, SUPPORTED_AVATARS
    _, subs, _ = skill_catalog()
    desired, actor_evidence, exclusions = {}, [], []
    for avatar_id, registry in ((101, "Kiana_C2_PT"), (201, "Mei_C2_CK")):
        reader = MessagePackSpanReader(avatar_packed)
        reader.pos = dict(avatar_entries)[strings.index(registry)]
        node = reader.node()
        if node["count"] != 25 or node["children"][8]["kind"] != "array" or node["children"][9]["kind"] != "map":
            raise ValueError("Actual avatar unlock/constant fields changed")
        evidence = {"avatar_id": avatar_id, "registry": registry, "unlock_refs": [], "constant_refs": []}
        for unlock in node["children"][8]["children"]:
            if unlock["count"] != 12:
                raise ValueError("Original avatar unlock must have twelve fields")
            values = unlock["children"]
            skill = None if values[1]["code"] == 0xc0 else monster.decode_integer(avatar_packed, values[1])
            sub = None if values[2]["code"] == 0xc0 else monster.decode_integer(avatar_packed, values[2])
            if not (skill in SUPPORTED_AVATARS[avatar_id] or sub in subs and subs[sub]["skillId"] in SUPPORTED_AVATARS[avatar_id]):
                continue
            key = monster.decode_integer(avatar_packed, values[3])
            if values[4]["code"] != 0xc0:
                raise ValueError("Unaudited avatar ability variant")
            if exclude114 and sub == 114:
                if avatar_id != 101 or key != 13413 or strings[key] != "Kiana_PT_StunCharge":
                    raise ValueError("Only the exact unsupported white-comet114 may be excluded")
                exclusions.append({"avatar_id": 101, "sub_skill_id": 114, "ability_key": key,
                    "ability_name": strings[key], "reason": "Real nonnil CustomBuffID1002 has no original1.9 field; do not delete or replace its behavior",
                    "policy": "Keep this ability root and avatar unlock reference exact source bytes; server must reject114 purchase"})
                continue
            desired[key, None] = strings[key]
            evidence["unlock_refs"].append({"skill_id": skill, "sub_skill_id": sub, "ability_key": key,
                "ability_name": strings[key], "override": None, "parameter_keys": [
                    None if values[index]["code"] == 0xc0 else monster.string_index(avatar_packed, values[index], strings)
                    for index in (6, 8, 10)], "avatar_span": [unlock["start"], unlock["end"]]})
        constant = node["children"][9]
        for name, value in zip(constant["children"][::2], constant["children"][1::2]):
            if value["count"] != 2 or value["children"][1]["code"] != 0xc0:
                raise ValueError("Unaudited constant avatar ability override")
            key = monster.decode_integer(avatar_packed, value["children"][0])
            desired[key, None] = strings[key]
            evidence["constant_refs"].append({"entry": monster.string_index(avatar_packed, name, strings),
                "ability_key": key, "ability_name": strings[key], "override": None})
        actor_evidence.append(evidence)
    if sum(row["sub_skill_id"] is not None for actor in actor_evidence for row in actor["unlock_refs"]) != (22 if exclude114 else 23):
        raise ValueError("Only the audited thirteen101/ten201 subskills are supported")

    def container(payload):
        packed_hash, entries, overrides, packed = monster.unpack_container(payload)
        references = {offset: (key, None) for key, offset in entries}
        references.update({offset: (key, variant) for key, variant, offset in overrides})
        order = sorted(references)
        return packed_hash, entries, overrides, packed, references, {
            references[left]: (left, right) for left, right in zip(order, order[1:] + [len(packed)])}

    _, _, _, packed, _, source_spans = container(source)
    packed_hash, entries, overrides, old_packed, old_refs, old_spans = container(previous)
    previous_roots = {(row["key"], row["variant"]) for row in baseline["files"][0]["projection"]["roots"]}
    additional = {identity: name for identity, name in desired.items() if identity not in previous_roots}
    changes, records, nested = {}, [], []
    with zipfile.ZipFile(apk24) as package:
        schema = CultivationSchema(package)
        if struct.unpack_from("<II", schema.source.binary, 0x4252098) != (108659, 68744928) or \
                schema.source.binary[0x14a0675:0x14a067f] != bytes.fromhex("807e08000f84d3000000") or \
                schema.source.binary[0x14a0752:0x14a075a] != bytes.fromhex("8b460ce988000000"):
            raise ValueError("Source DynamicString Evaluate false->fixedValue consumer changed")
        # Later score metadata must be from the exact source resource; the
        # original client lacks the entire scoring type, not a substituted skill.
        maps = {row["path"]: row for row in resources.resource_map(apk24)}
        _, stat_raw = resources.object_bytes(package, maps["data/_exceloutput/levelstatistics"])
        _, stat_text = resources.text_asset(stat_raw)
        stat_rows = [row for row in csv.DictReader(io.StringIO(stat_text.decode("utf-8")), delimiter="\t")
                     if row["statisticsID"] in ("801011", "802011")]
        if len(stat_rows) != 2 or any(row["GameVersionBegin"] != "2.2" or row["type"] != "Score" or
                row["overrideList"] != "TargetNum:2,AddScoreRatio:0.1" for row in stat_rows) or STATISTICS in schema.original_names:
            raise ValueError("Only original-absent later2.2 score actions are removable")
        pending = list(additional)
        while pending:
            identity = pending.pop(0)
            if identity in changes:
                continue
            if identity not in source_spans or identity not in old_spans:
                raise ValueError("Missing actual cultivation ability resource")
            start, end = source_spans[identity]
            old_start, old_end = old_spans[identity]
            if old_packed[old_start:old_end] != packed[start:end]:
                raise ValueError("Previously unselected ability differs from exact source")
            reader = AbilityReader(packed, strings, schema)
            reader.pos = start
            try:
                reader.class_value(ABILITY, "ability")
            except ValueError as error:
                raise ValueError("Cultivation root " + additional[identity] + ": " + str(error)) from error
            if reader.pos != end:
                raise ValueError("Cultivation source root boundary mismatch")
            value, cursor = bytearray(), start
            for left, right, replacement in sorted(reader.edits):
                if not cursor <= left < right <= end:
                    raise ValueError("Overlapping cultivation root adaptation")
                value.extend(packed[cursor:left]); value.extend(replacement); cursor = right
            value.extend(packed[cursor:end])
            check = AbilityReader(bytes(value), strings, schema, True)
            check.class_value(ABILITY, "ability")
            removed_fields = {row["path"] for row in reader.records if row["operation"] == "remove_later_field"}
            removed_actions = [row["path"] for row in reader.records if row["operation"] == "remove_later_statistics_action"]
            retained = {path: leaf for path, leaf in reader.leaves.items() if path not in removed_fields and
                not any(path.startswith(prefix + "<") or path.startswith(prefix + ".") for prefix in removed_actions)}
            if check.pos != len(value) or set(retained) != set(check.leaves) or any(
                    leaf["sha256"] != check.leaves[path]["sha256"] for path, leaf in retained.items()):
                raise ValueError("Original cultivation root or retained terminal encoding mismatch")
            changes[identity] = bytes(value)
            records.append({"identity": additional[identity], "key": identity[0], "variant": identity[1],
                "source_byte_span": [start, end], "source_sha256": monster.sha(packed[start:end]),
                "output_sha256": monster.sha(value), "adaptations": reader.records,
                "retained_terminal_values_byte_identical": True, "original_full_root_consumed": True,
                "retained_terminal_value_count": len(retained)})
            # Concrete AddAbility/TriggerAbility fields reference genuine baked
            # roots. Follow static AbilityName strings; reject missing targets.
            for path, leaf in retained.items():
                if path == "ability.AbilityName" or not path.endswith(".AbilityName"):
                    continue
                span = MessagePackSpanReader(packed); span.pos = leaf["span"][0]; ref_node = span.node()
                if ref_node["code"] == 0xc0:
                    continue
                key = monster.decode_integer(packed, ref_node)
                target = key, None
                if target not in source_spans:
                    raise ValueError("Missing nested ability reference: " + strings[key])
                nested.append({"from_key": identity[0], "path": path, "ability_key": key, "ability_name": strings[key]})
                if target not in previous_roots and target not in additional:
                    additional[target] = strings[key]; pending.append(target)
        camera = schema.camera_dependency(strings)
        mappings, checks = schema.mapping_checks, list(schema.checks.values())
        indexed_refs = schema.indexed_references
    output, new_offsets = bytearray(), {}
    for left, right in zip(sorted(old_refs), sorted(old_refs)[1:] + [len(old_packed)]):
        new_offsets[left] = len(output)
        output.extend(changes.get(old_refs[left], old_packed[left:right]))
    payload = monster.pack_container(packed_hash, [(key, new_offsets[offset]) for key, offset in entries],
        [(key, variant, new_offsets[offset]) for key, variant, offset in overrides], bytes(output))
    _, new_entries, new_overrides, new_packed, _, new_spans = container(payload)
    if [key for key, _ in entries] != [key for key, _ in new_entries] or [(key, variant) for key, variant, _ in overrides] != [(key, variant) for key, variant, _ in new_overrides]:
        raise ValueError("Original registry keys/order changed")
    for identity, (left, right) in old_spans.items():
        after, end = new_spans[identity]
        if identity not in changes and old_packed[left:right] != new_packed[after:end]:
            raise ValueError("Previously accepted or unselected root changed")
    manifest = copy.deepcopy(baseline)
    manifest["format"] = "server19-avatar101-201-cultivation-ability-explicit-projection-v1"
    manifest["profile"] = "avatar_cultivation_bounded" if exclude114 else "avatar_cultivation"
    item = manifest["files"][0]
    item.update(output_sha256=monster.sha(payload), bytes=len(payload), required_existing_sha256=CULTIVATION_PREVIOUS_SHA)
    for row in records:
        row["output_byte_span"] = list(new_spans[row["key"], row["variant"]])
    retained_previous_records = copy.deepcopy(baseline["files"][0]["projection"]["roots"])
    for row in retained_previous_records:
        row["output_byte_span"] = list(new_spans[row["key"], row["variant"]])
    item["projection"] = {"selected_roots": len(previous_roots) + len(changes), "previous29_roots_byte_identical": True,
        "roots": sorted(retained_previous_records + records, key=lambda row: row["output_byte_span"][0]),
        "new_projected_roots": records, "new_projected_count": len(changes), "all_other_roots_byte_identical": True,
        "all_keys_and_order_preserved": True, "all_offsets_recomputed": True,
        "union_mapping_evidence": mappings, "declaration_checks": checks}
    item["indexed_resource_dependencies"] = [camera, baseline["files"][0]["indexed_resource_dependencies"][1]]
    manifest["actual_avatar_cultivation_references"] = actor_evidence
    manifest["excluded_subskills"] = exclusions
    if exclude114:
        if len(exclusions) != 1 or (13413, None) in changes:
            raise ValueError("Bounded114 exclusion lost its exact source-preservation boundary")
        before, end = source_spans[13413, None]
        after, after_end = new_spans[13413, None]
        if packed[before:end] != new_packed[after:after_end]:
            raise ValueError("Unsupported114 root changed")
        manifest["excluded114_source_root_sha256"] = monster.sha(packed[before:end])
        camera_bytes = (ROOT / ".local-baseline/server19-dev/baked-fallback" / CAMERA_PATH).read_bytes()
        manifest["deployment_files"].append(CAMERA_PATH)
        manifest["files"].append({"path": CAMERA_PATH, "output_sha256": monster.sha(camera_bytes),
            "bytes": len(camera_bytes), "source_version": "Exact accepted source2.4 indexed resource bytes; indexes139/202 newly audited against original6-field consumer",
            "source_equals_output": True, "all_indexed_offsets_unchanged": True})
    manifest["actual_nested_ability_references"] = nested
    manifest["actual_indexed_references"] = indexed_refs
    manifest["cultivation_statistics_evidence"] = {"rows": stat_rows, "source_text_sha256": monster.sha(stat_text),
        "original_type_absent": True, "original_scoring_not_replaced": True}
    manifest["fixed_global_key_consumer_evidence"] = {"source_method": "ActorAbility.Evaluate58144@14a0631",
        "source_false_branch": "cmp byte [esi+8],0 ->14a0752 mov eax,[esi+c] (fixedValue) ->return",
        "source_call": "AddGlobalValueHandler58210@14d2c53 reads Key+20 then calls Evaluate@14d2ccd",
        "original_handler": "AddGlobalValueHandler49443@a37e23 consumes primitive String Key",
        "retained_fixed_string": "_GLOBAL_CK_EVADE_ATK_CHARGE", "dynamic_keys_rejected": True}
    manifest["limits"] = [("Only actual101/201 constants/default skills and twenty-two sourced subskills;114 excluded" if exclude114 else
        "Only actual101/201 constants/default skills and twenty-three sourced subskills") + " plus explicit static nested AbilityName references",
        "Previous29 accepted roots and all unselected source roots remain byte identical; no registry renumbering",
        "Original concrete unions, retained terminal bytes and custom IDs are preserved; only audited absent later score actions/nil fields and static string wrappers adapted",
        "Source2.4 is later compatibility data, not independently recovered historical1.9 economy",
        "Static typed closure is not actual skill/battle acceptance; skill page currently has original1-7 guide gate",
        "No10107 content, device, service, native-library, account, progress or stamina operation"]
    return source, payload, manifest


def build_stage7(apk19, apk24):
    """Add two actual Normal1-7 tutorial roots atop the accepted56, never rebuild it."""
    if monster.file_sha(apk19) != monster.ORIGINAL19_SHA or monster.file_sha(apk24) != monster.SOURCE24_SHA:
        raise ValueError("Pinned stage7 input APK changed")
    source_path = ROOT / ".local-baseline/server19-dev/baked-fallback" / PATH
    source = source_path.read_bytes()
    previous = (CULTIVATION_BOUNDED_OUTPUT / PATH).read_bytes()
    baseline = json.loads((CULTIVATION_BOUNDED_OUTPUT / "manifest.json").read_bytes())
    if monster.sha(source) != SOURCE_SHA or monster.sha(previous) != STAGE7_PREVIOUS_SHA:
        raise ValueError("Preserve exact source and accepted56 ability containers")
    if baseline["files"][0]["projection"]["selected_roots"] != 56:
        raise ValueError("Stage7 must extend accepted56 ability roots")
    strings_raw = (ROOT / ".local-baseline/server19-dev/act101-native-prop-resources/_baked/stringmap.txt").read_bytes()
    if monster.sha(strings_raw) != "297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1":
        raise ValueError("Preserve accepted extended StringMap")
    strings = strings_raw.decode("utf-8").split("\x1f")

    def container(raw):
        h, entries, overrides, packed = monster.unpack_container(raw)
        refs = {off: (key, None) for key, off in entries}
        refs.update({off: (key, variant) for key, variant, off in overrides})
        if len(refs) != len(entries) + len(overrides):
            raise ValueError("Ability registry aliases need independent proof")
        ends = dict(zip(sorted(refs), sorted(refs)[1:] + [len(packed)]))
        return h, entries, overrides, packed, refs, {identity: (off, ends[off]) for off, identity in refs.items()}

    _, _, _, packed, _, source_spans = container(source)
    packed_hash, entries, overrides, old_packed, old_refs, old_spans = container(previous)
    changes, records = {}, []
    with zipfile.ZipFile(apk24) as package:
        schema = Schema(package, "act101_entry")
        for identity, name in STAGE7_SELECTED.items():
            if strings[identity[0]] != name or identity not in source_spans:
                raise ValueError("Actual tutorial ability identity changed")
            left, right = source_spans[identity]
            before, end = old_spans[identity]
            if old_packed[before:end] != packed[left:right]:
                raise ValueError("New tutorial root was already changed; preserve it")
            reader = AbilityReader(packed, strings, schema)
            reader.pos = left
            reader.class_value(ABILITY, "ability")
            if reader.pos != right:
                raise ValueError("Source tutorial root boundary changed")
            output, cursor = bytearray(), left
            for start, finish, replacement in sorted(reader.edits):
                if not cursor <= start < finish <= right:
                    raise ValueError("Overlapping tutorial edits")
                output.extend(packed[cursor:start]); output.extend(replacement); cursor = finish
            output.extend(packed[cursor:right])
            check = AbilityReader(bytes(output), strings, schema, True)
            check.class_value(ABILITY, "ability")
            removed = {row["path"] for row in reader.records if row["operation"] == "remove_later_field"}
            # This profile permits only existing schema-proven nil deletions and
            # same-concrete union translations; no statistics or semantic keys.
            if any(row["operation"] not in ("remove_later_field", "union_tag_same_type") for row in reader.records):
                raise ValueError("Unexpected stage7 semantic adaptation")
            retained = {path: leaf for path, leaf in reader.leaves.items() if path not in removed}
            if check.pos != len(output) or set(retained) != set(check.leaves) or any(
                    leaf["sha256"] != check.leaves[path]["sha256"] for path, leaf in retained.items()):
                raise ValueError("Original reader or exact retained tutorial values differ")
            changes[identity] = bytes(output)
            records.append({"key": identity[0], "variant": identity[1], "identity": name,
                "source_byte_span": [left, right], "source_sha256": monster.sha(packed[left:right]),
                "output_sha256": monster.sha(output), "adaptations": reader.records,
                "original_full_root_consumed": True, "retained_terminal_values_byte_identical": True,
                "retained_terminal_value_count": len(retained)})
        if schema.indexed_references:
            raise ValueError("New stage7 indexed references require a separate audited dependency")
        mappings, checks = schema.mapping_checks, list(schema.checks.values())
    output, offsets = bytearray(), {}
    for start, end in zip(sorted(old_refs), sorted(old_refs)[1:] + [len(old_packed)]):
        offsets[start] = len(output)
        output.extend(changes.get(old_refs[start], old_packed[start:end]))
    payload = monster.pack_container(packed_hash, [(key, offsets[off]) for key, off in entries],
        [(key, variant, offsets[off]) for key, variant, off in overrides], bytes(output))
    _, next_entries, next_overrides, next_packed, _, next_spans = container(payload)
    if [key for key, _ in entries] != [key for key, _ in next_entries] or [(key, variant) for key, variant, _ in overrides] != [(key, variant) for key, variant, _ in next_overrides]:
        raise ValueError("Stage7 registry/order changed")
    for identity, (left, right) in old_spans.items():
        after, end = next_spans[identity]
        if identity not in changes and old_packed[left:right] != next_packed[after:end]:
            raise ValueError("Previous ability root changed unexpectedly")
    previous_roots = copy.deepcopy(baseline["files"][0]["projection"]["roots"])
    for row in previous_roots + records:
        row["output_byte_span"] = list(next_spans[row["key"], row["variant"]])
    manifest = {"format": "server19-stage10107-two-tutorial-roots-v1", "profile": "stage10107",
        "stage_id": 10107, "mode": "Normal", "source19": {"sha256": monster.ORIGINAL19_SHA},
        "source24": {"sha256": monster.SOURCE24_SHA}, "deployment_files": [PATH],
        "base56_manifest_sha256": monster.file_sha(CULTIVATION_BOUNDED_OUTPUT / "manifest.json"),
        "files": [{"path": PATH, "bytes": len(payload), "output_sha256": monster.sha(payload),
            "source_container_sha256": SOURCE_SHA, "required_existing_sha256": STAGE7_PREVIOUS_SHA,
            "reference_path": "reference/" + PATH,
            "stringmap_dependency": {"required_existing_path": "_baked/stringmap.txt",
                "output_sha256": monster.sha(strings_raw), "all22416_base_indices_preserved": True,
                "policy": "Retain existing22418-entry map; do not deploy a replacement"},
            "projection": {"selected_roots": 58, "new_projected_count": 2,
                "roots": sorted(previous_roots + records, key=lambda row: row["output_byte_span"][0]),
                "new_projected_roots": records, "previous56_roots_byte_identical": True,
                "all_other_roots_byte_identical": True, "all_keys_and_order_preserved": True,
                "all_offsets_recomputed": True, "union_mapping_evidence": mappings, "declaration_checks": checks}}],
        "limits": ["Only two actual Normal1-7 tutorial references are added to accepted56 roots",
            "Retain modifier values, evade event QueueKey and ApplyLevelBuff effect name; no behavior substitutes",
            "Later2.4 compatibility; historical1.9 tutorial behavior equivalence unproven",
            "No device, native library, account, progress, tutorial-completion or service changes; human play pending"]}
    return source, payload, manifest


def build(apk19, apk24, profile="ai"):
    if profile == "stage10107":
        return build_stage7(apk19, apk24)
    if profile == "avatar_cultivation":
        return build_avatar_cultivation(apk19, apk24)
    if profile == "avatar_cultivation_bounded":
        return build_avatar_cultivation(apk19, apk24, exclude114=True)
    if profile == "act101_prop_box":
        return build_prop_box(apk19, apk24)
    if monster.file_sha(apk19) != monster.ORIGINAL19_SHA or monster.sha(a.E) != monster.NATIVE19_SHA or monster.file_sha(apk24) != monster.SOURCE24_SHA:
        raise ValueError("Original/later baseline identity changed")
    if PATH in {row["path"] for row in resources.resource_map(apk19)}:
        raise ValueError("Preserve original ability resource instead of later replacement")
    maps = {row["path"]: row for row in resources.resource_map(apk24)}
    with zipfile.ZipFile(apk24) as package:
        obj, raw = resources.object_bytes(package, maps[PATH])
        if obj["class"] != 114:
            raise ValueError("Ability source is not a ScriptableObject")
        cursor = resources.Reader(raw, 28); name = cursor.string(); arrays = []
        for size in (8, 12, 1):
            count = cursor.read("I"); length = count * size
            if cursor.pos + length > len(raw):
                raise ValueError("Ability source array exceeds Unity object")
            arrays.append((count, raw[cursor.pos:cursor.pos + length])); cursor.pos += length; cursor.align()
        packed_hash = cursor.read("I")
        if cursor.pos != len(raw):
            raise ValueError("Ability source boundary changed")
        source = struct.pack("<II", 0, packed_hash) + b"".join(struct.pack("<I", n) + data for n, data in arrays)
        strings_path = ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/stringmap.txt"
        string_bytes = strings_path.read_bytes()
        if monster.sha(string_bytes) != monster.STRINGMAP_SHA:
            raise ValueError("Actual AI requires unchanged accepted source string map")
        strings = string_bytes.decode("utf-8").split("\x1f")
        schema = Schema(package, profile)
        statistics_evidence = None
        actor_evidence = None
        if profile in AVATAR_PROFILES:
            avatar_path = ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/bakedavatardata"
            avatar_payload = avatar_path.read_bytes()
            if monster.sha(avatar_payload) != "dfd331e7b89063be037e6cfbf930fc6f48a42a9189ca3a54307c73a43bfab6e2":
                raise ValueError("Preserve the already accepted Avatar projection baseline")
            _, avatar_entries, _, avatar_packed = monster.unpack_container(avatar_payload)
            avatar_reader = MessagePackSpanReader(avatar_packed)
            avatar_reader.pos = dict(avatar_entries)[strings.index("Kiana_C2_PT")]
            avatar_root = avatar_reader.node()
            if avatar_root["count"] != 25 or avatar_root["children"][9]["kind"] != "map":
                raise ValueError("Accepted Avatar101 actual constant ability field changed")
            actual_refs = []
            ability_map = avatar_root["children"][9]
            for key, value in zip(ability_map["children"][::2], ability_map["children"][1::2]):
                if value["kind"] != "array" or value["count"] != 2 or value["children"][1]["code"] != 0xc0:
                    raise ValueError("Avatar101 constant ability override is not the audited nil")
                ability_key = monster.decode_integer(avatar_packed, value["children"][0])
                actual_refs.append({"entry": monster.string_index(avatar_packed, key, strings),
                                    "ability_key": ability_key, "ability_name": strings[ability_key], "override": None})
            if {(row["ability_key"], None) for row in actual_refs} != set(AVATAR_SELECTED) - set(SELECTED):
                raise ValueError("Project only actual seven constant Avatar101 ability references")
            avatar_record = maps["data/_exceloutput/avatardata"]
            avatar_meta_obj, avatar_meta_raw = resources.object_bytes(package, avatar_record)
            if avatar_meta_obj["class"] != 49:
                raise ValueError("Avatar101 identity requires actual source TextAsset metadata")
            _, avatar_meta_text = resources.text_asset(avatar_meta_raw)
            avatar_rows = [row for row in csv.DictReader(io.StringIO(avatar_meta_text.decode("utf-8")), delimiter="\t") if row["avatarID"] == "101"]
            if len(avatar_rows) != 1 or avatar_rows[0]["avatarRegistryKey"] != "Kiana_C2_PT" or avatar_rows[0]["initialWeapon"] != "20001":
                raise ValueError("Source actual Avatar101/Weapon20001 identity changed")
            weapon_payload = (ROOT / ".local-baseline/server19-dev/baked-fallback/_baked/bakedweapondata").read_bytes()
            if monster.sha(weapon_payload) != "efc4e1bf0c27d2a6fd67f77410763a8cd2e370cf4f79a794d381c2d85ba8fe5f":
                raise ValueError("Accepted Weapon baseline changed")
            _, weapon_entries, _, weapon_packed = monster.unpack_container(weapon_payload)
            weapon_reader = MessagePackSpanReader(weapon_packed); weapon_reader.pos = dict(weapon_entries)[20001]
            weapon_root = weapon_reader.node()
            if weapon_root["count"] != 10 or weapon_root["children"][3]["code"] != 0xc0:
                raise ValueError("Actual Weapon20001 must have no extra Ability refs")
            actor_evidence = {"avatar_id": 101, "registry_key": "Kiana_C2_PT", "weapon_id": 20001,
                              "source_avatar_metadata": {**avatar_record, "source_object_sha256": monster.sha(avatar_meta_raw)},
                              "constant_ability_refs": actual_refs,
                              "unchanged_avatar_dependency": {"required_existing_path": "_baked/bakedavatardata", "output_sha256": monster.sha(avatar_payload)},
                              "unchanged_weapon_dependency": {"required_existing_path": "_baked/bakedweapondata", "output_sha256": monster.sha(weapon_payload), "AdditionalAbilities": None}}
            if profile in ("avatar101_leader", "avatar101_newbie", "act101_entry"):
                actor_evidence["leader_unlock_evidence"] = leader_reference_evidence(package, maps, schema, avatar_root, avatar_packed, strings)
            if profile in NEWBIE_PROFILES:
                actor_evidence["newbie_implicit_ability_evidence"] = newbie_reference_evidence(package, maps, schema, strings)
            path = "data/_exceloutput/levelstatistics"
            stat_object, stat_raw = resources.object_bytes(package, maps[path])
            if stat_object["class"] != 49:
                raise ValueError("Later statistics version evidence must be a real TextAsset")
            stat_reader = resources.Reader(stat_raw)
            stat_name, stat_text = stat_reader.string(), stat_reader.string()
            rows = [row for row in csv.DictReader(io.StringIO(stat_text), delimiter="\t") if row["statisticsID"] == "801011"]
            if len(rows) != 1 or rows[0]["GameVersionBegin"] != "2.2" or rows[0]["type"] != "Score" or rows[0]["overrideList"] != "TargetNum:2,AddScoreRatio:0.1":
                raise ValueError("Only exact audited later2.2 scoring extension accepted")
            absent = ["MoleMole.Config.CustomStatistics", "MoleMole.EvtCustomStatistics",
                      "MoleMole.CustomActionLevelStastics", "MoleMole.BaseLevelStastics",
                      "MoleMole.LevelStasticsPlugin", "MoleMole.LevelStatisticsMetaData"]
            if any(name in schema.original_names for name in absent):
                raise ValueError("Do not remove a statistics feature present in original1.9")
            statistics_evidence = {"source_resource": {**maps[path], "name": stat_name, "class": stat_object["class"],
                                     "source_object_sha256": monster.sha(stat_raw), "text_sha256": monster.sha(stat_text.encode("utf-8"))},
                                   "source_row": rows[0], "original_types_absent": absent,
                                   "source_handler": "CustomStatistics Execute70635@0x30c6cd6 -> handler58257@0x14d821c -> EvtCustomStatistics56762@0x2e53d19",
                                   "source_scoring_listener": "CustomActionLevelStastics.Listen59640@0x24b0a60 accumulates ID/value and later CalculateScoreMultiplier",
                                   "original_statistics_preserved": "Original Avatar/Player/LevelDamage/LevelMission statistics independently consume original combat events; no native code altered",
                                   "classification": "Later2.2 statistics/scoring extension, not merely telemetry; excluded only because this entire later framework is absent in original1.9"}
        payload, projection = project(source, strings, schema)
        if profile in AVATAR_PROFILES:
            stat_actions = [item for root in projection["roots"] for item in root["adaptations"] if item["operation"] == "remove_later_statistics_action"]
            if len(stat_actions) != 1 or stat_actions[0]["path"] != "ability.Modifiers.value[3].OnAdded[0]":
                raise ValueError("Only one evidenced Avatar101 extra statistics action may be removed")
        if profile in NEWBIE_PROFILES:
            expected_camera_refs = [(127, "ability.Modifiers.value[4].OnAttackLanded[1]<MoleMole.Config.ActCameraShake>.CameraShake"),
                                    (205, "ability.Modifiers.value[4].OnAttackLanded[4]<MoleMole.Config.ActCameraShake>.CameraShake")]
            camera_refs = schema.indexed_references if profile != "act101_entry" else [item for item in schema.indexed_references if item["type"] == CAMERA_SHAKE and item["index"] != 188]
            if [(item["index"], item["path"]) for item in camera_refs] != expected_camera_refs or schema.camera_evidence is None:
                raise ValueError("Only the actual two Newbie CameraShake indexed references are retained")
        act101_evidence = act101_reference_evidence(package, maps, schema, strings, actor_evidence, projection) if profile == "act101_entry" else None
    manifest = {"format": "server19-stage10101-ability-explicit-projection-v1", "stage_id": 10101,
                "source19": {"path": str(apk19.resolve()), "sha256": monster.ORIGINAL19_SHA},
                "source24": {"path": str(apk24.resolve()), "sha256": monster.SOURCE24_SHA},
                "deployment_files": [PATH], "files": [{**maps[PATH], "path": PATH, "name": name,
                    "class": obj["class"], "source_object_bytes": len(raw), "source_object_sha256": monster.sha(raw),
                    "source_container_sha256": monster.sha(source), "output_sha256": monster.sha(payload),
                    "bytes": len(payload), "reference_path": "reference/" + PATH,
                    "source_version": "2.4 later compatibility, not historical1.9 data",
                    "stringmap_dependency": {"required_existing_path": "_baked/stringmap.txt", "output_sha256": monster.STRINGMAP_SHA},
                    "projection": projection}],
                "limits": ["Only actual MonsterCommonAIAbility primary/DeadWalker/UlyssesWarrior roots are projected",
                           "Other ability roots including Avatar remain exact source bytes; their gameplay compatibility is not inferred",
                           "Only source CustomBuffID and same-concrete union discriminator differences are adapted",
                           "Custom IDs, names, MP behavior and retained terminal gameplay values remain byte identical",
                           "Original formatter evidence covers custom tails; typed declarations do not prove every runtime behavior",
                           "No device/service/library/account/progress/stamina operations; actual play remains acceptance gate"]}
    if profile in AVATAR_PROFILES:
        manifest["format"] = "server19-stage10101-ability-avatar101-explicit-projection-v1"
        manifest["profile"] = profile
        manifest["later_statistics_evidence"] = statistics_evidence
        manifest["actual_actor_reference_evidence"] = actor_evidence
        manifest["original_avatar_consumer_evidence"] = {
            "SkillMoveToTargetMixin": "58615@0x75477f original6/source7; source MoveType absent in original, actual nil only",
            "HealSP": "57931@0x6d3368 original11/source12; source ConsumeWithProperty absent in original, actual nil only",
            "ModifyDamageMixin": "58111@0x7103ed original33/source37; four source Extra*DamageMax absent in original, actual nil only",
            "StateOption": "58751@0x1552f35/source70517@0x24f5706 Poly tag11 both ShieldedOption; no CustomID tail",
            "TargettingOption": "58675@0x75b1ee normal array1 Range:DynamicFloat, no Poly or tail"}
        manifest["limits"] = [
            "Only three actual first-stage MonsterCommonAIAbility roots and seven constant Avatar101 Kiana_C2_PT roots are selected",
            "All seven Avatar101 constant ability refs use nil override; Weapon20001 AdditionalAbilities is nil",
            "AbilitiesUnlock/subskill runtime references beyond these seven are not claimed compatible",
            "Original/native library, accepted Avatar container, HP/SP/damage/movement/skill values and retained custom IDs remain unchanged",
            "Only audited nil later fields, same-concrete union tags and one evidenced later2.2 scoring action are adapted",
            "Later scoring extension is intentionally unavailable in original1.9; original combat/mission statistics remain intact",
            "All unselected ability roots remain byte identical; source2.4 data is later compatibility, not historical1.9 data",
            "Runtime entrance/combat/exit/settlement still requires actual device acceptance",
            "No device/service/library/account/progress/stamina operations"]
        if profile in ("avatar101_leader", "avatar101_newbie", "act101_entry"):
            manifest["format"] = "server19-stage10101-ability-avatar101-leader-explicit-projection-v1"
            manifest["limits"][0] = "Only three actual first-stage AI roots, seven constant Avatar101 roots and the observed default-unlocked Captain_HPUp leader root are selected"
            manifest["limits"][2] = "Locked skill12/14 abilities and all other unlock/subskill/buff references remain unselected; their compatibility is not inferred"
        if profile in NEWBIE_PROFILES:
            manifest["format"] = "server19-stage10101-ability-avatar101-newbie-explicit-projection-v1"
            manifest["files"][0]["indexed_resource_dependencies"] = [schema.camera_evidence]
            manifest["actual_indexed_references"] = schema.indexed_references
            manifest["original_avatar_consumer_evidence"]["DamageByAttackValue"] = (
                "57751@0x6b65f4 original24/source25, source69317@0x17b029b adds MaxHpValue at index1; "
                "original SwitchType store+1c@0x6b67eb immediately followed by DamagePercentage+20@0x6b690e, "
                "last MPTotallyLocal@0x6b8068 then return0x6b807b without tail skip; actual two MaxHpValue nodes nil only")
            manifest["limits"][0] = "Only the previous eleven AI/Avatar/leader roots and three native consecutive Newbie buff roots are selected"
            manifest["limits"][2] = "Locked skill12/14, GalTouch, GrandKey and all other dynamic references remain unselected; their compatibility is not inferred"
            manifest["limits"].insert(3, "Account-level15 Newbie parameters and CameraShake indices127/205/resources remain exact; two nil source MaxHpValue fields are removed for original24-field damage consumers")
    if profile == "act101_entry":
        manifest["format"] = "server19-act101-entry-ability-explicit-projection-v1"
        manifest["stage_ids"] = list(range(10101, 10107))
        manifest["mode"] = "Normal"
        manifest["actual_stage_equipment_unlock_reference_evidence"] = act101_evidence
        camera_evidence = {**schema.camera_evidence, "policy": "Preserve actual IndexedConfig127/188/205 and accepted CameraShake bytes; no StringMap or inline conversion"}
        manifest["files"][0]["indexed_resource_dependencies"] = [camera_evidence, schema.arrow_evidence]
        manifest["files"][0]["required_existing_sha256"] = act101_evidence["required_previous_ability_sha256"]
        manifest["original_act101_consumer_evidence"] = {
            "HitExplodeBulletMixin": "57939@6d465a original44/source47; only nil DestroyCloseToGround/ForceRotate/FollowOwnerTimeScale removed; last HitGroundActions store+a0@6d6cfc then OnRuntimeLoaded@6d6d1a and return6d6d28, no tail skip",
            "TriggerAbility": "58691@75bec8 original8/source10; only nil UseFloatArgument/FloatArgument removed; last MPTotallyLocal ReadBoolean@75c6d4/store+18@75c6e1 then return75c6f4, no tail skip",
            "ShieldMixin": "58591@74fcbe original32/source33; nil ShieldMaxValue removed; source ForceResumeRatio/MinForceResumeCD/UseLevelTimeScale reordered by original ReadSingle@75023b/ReadBoolean@7502da/ReadSingle@75036d; exact retained values preserved; last MPTotallyLocal then return75176f, no tail skip",
            "IMixinArgument": "58783@6ef823/source70565@17f2dcd both four-tag Poly, no CustomID tail; each concrete verified through native switch -> MethodRef -> GetFormatterWithVerify<T>",
            "ConfigEquipmentSkillEntry": "57539@693feb consumes18 fields; set2 registry40/44 selects actual ability and ParamSpecial1, external0.08/0.2 loaded through original equipment skill chain"}
        manifest["limits"] = [
            "Only Normal10101..10106 closure, previous fourteen accepted roots plus fourteen actual monster/Elite/arrow/eligibleAvatar/set2 dependencies are selected",
            "No10107 onward, Hard/Hell, extra avatar, set1, GalTouch or other dynamic ability compatibility is claimed",
            "Original schema projection removes only audited nil later fields and one previously evidenced later2.2 scoring action; same concrete union identities and exact Shield field values retained",
            "Custom IDs, HP/SP/damage/movement/skill parameters and accepted indexed CameraShake/arrow argument bytes remain unchanged",
            "All previous fourteen projected roots and all other unselected source roots remain byte identical; offsets recomputed without ID renumbering",
            "All source2.4 contents are explicit later compatibility, not historical original1.9 data",
            "Static closure and ABI consumption passed; actual stage entry/combat/equipment behavior remains a device acceptance gate",
            "No device/service/library/account/progress/stamina operations"]
    return source, payload, manifest


def run(command, apk19, apk24, output, profile="ai"):
    source, payload, manifest = build(apk19, apk24, profile)
    targets = {PATH: payload, "reference/" + PATH: source,
               "manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")}
    if profile == "avatar_cultivation_bounded":
        targets[CAMERA_PATH] = (ROOT / ".local-baseline/server19-dev/baked-fallback" / CAMERA_PATH).read_bytes()
    for path, data in targets.items():
        target = output / path
        if command == "audit":
            if not target.is_file() or target.read_bytes() != data:
                raise ValueError("Ability export provenance/bytes changed: " + path)
        elif target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError("Preserve existing changed output: " + str(target))
    if command == "prepare":
        for path, data in targets.items():
            target = output / path; target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
    projection = manifest["files"][0]["projection"]
    return {"status": "exported" if command == "prepare" else "source_projection_verified",
            "output": str(output.resolve()), "selected_roots": projection["selected_roots"],
            "adaptations": dict(Counter(x["operation"] for root in projection.get("roots", projection.get("new_projected_roots", [])) for x in root["adaptations"])),
            "output_sha256": monster.sha(payload), "manifest_sha256": monster.file_sha(output / "manifest.json"),
            "runtime_compatibility": "unaccepted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "audit"))
    parser.add_argument("--apk19", type=Path, default=resources.DEFAULT19)
    parser.add_argument("--apk24", type=Path, default=resources.DEFAULT24)
    parser.add_argument("--profile", choices=(*PROFILE_ROOTS, "avatar_cultivation", "avatar_cultivation_bounded", "stage10107"), default="ai")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (STAGE7_OUTPUT if args.profile == "stage10107" else CULTIVATION_OUTPUT if args.profile == "avatar_cultivation" else
        CULTIVATION_BOUNDED_OUTPUT if args.profile == "avatar_cultivation_bounded" else PROFILE_OUTPUTS[args.profile])
    print(json.dumps(run(args.command, args.apk19, args.apk24, output, args.profile), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
