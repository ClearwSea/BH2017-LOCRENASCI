"""Prepare remaining chapter1 native-resource closure without deployment or saves.

Pinned 2.4 Lua/data are compatibility inputs, not recovered historical 1.9.
Only same-concrete-type projections with retained byte checks are permitted.
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
import bisect
import csv
import io
import json
from pathlib import Path
import re
import struct
import zipfile

import server19_story_batch_resources as story
import server19_avatar_battle_resources as batch
import server19_equipment_battle_closure as equipment
import server19_stage_monsters as monsters
import server19_stage_resources as lua
import server19_stage_npc_levels as npc
import server19_resources as resources
from server19_metadata_export import SourceTypedDecoder, native_json
import analyze19 as native

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / '.local-baseline/server19-dev/chapter1-remaining-ready/final'
BASE = ROOT / '.local-baseline/server19-dev/cultivation-unified-ready'
STORY_BASE = ROOT / '.local-baseline/server19-dev/story-chain-batch-ready/v4'
ABILITY_SHA = '986606db6eb3a3eed10f86fecd991b4d48b3bbe22d302ed4140a5b8c8503af0b'
MONSTER_SHA = '3a8aa83ce0e8ddff025dc1eee5a0022121090525f8a89d4c0f72b5f115e3da72'
NPC_SHA = '6ae8a90da01248bfa359cfd74671c0c0339cdf594d3e1a1cacd7fce66c0bdd74'
WEAPON_SHA = 'e48edc01666f300524bdd023ce47cac2b11ca31b1b051a689420f3040c7efe84'
SCOPE = tuple(range(10111, 10137))
SUMMON_ITEM = 'MoleMole.Config.MixinSummonItem'
DEFEND_SHIELD = 'MoleMole.Config.DefendWithShieldMixin'


class ChapterSchema(batch.BattleSchema):
    def union(self, kind, tag, original):
        if not original and kind == batch.ability.MIXIN and getattr(self,'leader_restrict_roots',()):
            concrete, evidence = self.resolve_tag(kind,tag,False)
            if concrete == 'MoleMole.Config.ModifyDamageTakenWithRestrictMixin':
                target='MoleMole.Config.ModifyDamageTakenMixin'
                added={'FireDamageTakenRatio','IceDamageTakenRatio','ThunderDamageTakenRatio'}
                new=[(n,self.signature(p,False)) for n,p in self.members(concrete,False) if n not in added]
                old=[(n,self.signature(p,True)) for n,p in self.members(target,True)]
                if new!=old:raise ValueError('Leader physical reduction shared schema differs')
                self.checks[concrete]={'type':concrete,'source_fields':new,'original_fields':old,
                    'compatibility_target':target,'excluded_fields':sorted(added)}
                return concrete,self.original_tags[kind][target][0]
        return super().union(kind,tag,original)

    def check(self, name):
        if name == SUMMON_ITEM and name not in self.checks:
            old, new = self.members(name, True), self.members(name, False)
            os, ns = [(n, self.signature(p, True)) for n, p in old], [(n, self.signature(p, False)) for n, p in new]
            if len(os) != 10 or len(ns) != 10 or [n for n, _ in os] != [n for n, _ in ns]:
                raise ValueError('SummonItem declaration order changed')
            if [(n, s) for n, s in os if n != 'UniqueMonsterID'] != [(n, s) for n, s in ns if n != 'UniqueMonsterID'] or dict(os)['UniqueMonsterID'] != 'primitive:0x8' or dict(ns)['UniqueMonsterID'] != 'MoleMole.Config.DynamicInt':
                raise ValueError('Only proven fixed summon ID wrapper may differ')
            self.checks[name] = {'type': name, 'excluded_fields': [], 'only_fixed_UniqueMonsterID_wrapper_differs': True,
                'original_fields': os, 'source_fields': ns}
            return
        super().check(name)


class ChapterReader(equipment.ClosureReader):
    def class_value(self, name, path, depth=0):
        if name=='MoleMole.Config.ModifyDamageTakenWithRestrictMixin' and not self.original and getattr(self.schema,'leader_restrict_roots',()):
            root=self.leaves.get('ability.AbilityName')
            if not root:raise ValueError('Leader reduction requires a known root name')
            q=batch.baked.MessagePackSpanReader(self.data);q.pos=root['span'][0]
            root_key = scalar(self.data,q.node())
            if root_key not in self.schema.leader_restrict_roots:
                raise ValueError('Unreviewed restricted damage root')
            approximate_elemental = root_key == 10204 and root_key in getattr(self.schema, 'approved_trial_reduction_approximation', ())
            node=self.header('array');members=self.schema.members(name,False)
            if node['count']!=16:raise ValueError('Restricted leader reduction requires sixteen fields')
            seen={};children=[]
            added={'FireDamageTakenRatio','IceDamageTakenRatio','ThunderDamageTakenRatio'}
            for field,pointer in members:
                child=self.typed(pointer,path+'.'+field,depth+1);children.append(child)
                raw=self.data[child['start']:child['end']];seen[field]=raw
                if field in added:
                    if raw!=b'\xc0':raise ValueError('Active element-specific ratio needs a separate native backport')
                    self.edits.append((child['start'],child['end'],b''))
                    self.records.append(dict(operation='remove_later_field',path=path+'.'+field,
                        source_byte_span=[child['start'],child['end']],reason='Nil added element ratio retains constructor zero'))
                if field=='ModifyElemental':
                    if raw not in (b'\xc0',b'\xc2') and not (approximate_elemental and raw == b'\xc3'):
                        raise ValueError('Elemental leader reduction requires a separate native backport')
            if any(v!=b'\xc0' for f,v in seen.items() if f not in added|{'DamageTakenRatio','Predicates','ModifyElemental'}):
                raise ValueError('Only the reviewed pure physical-percent leader profile is supported')
            if seen['DamageTakenRatio']==b'\xc0':raise ValueError('Missing physical reduction ratio')
            self.edits.append((node['start'],node['header_end'],batch.ability.array_bytes(13)))
            self.records.append(dict(operation='approximate_trial_all_channel_reduction' if approximate_elemental else 'project_leader_physical_reduction',path=path,
                target_type='MoleMole.Config.ModifyDamageTakenMixin',
                reason='User-approved approximation: retain ratio, predicates and ModifyElemental; original handler applies shared ratio to enabled physical/fire/thunder/ice channels' if approximate_elemental else 'Preserve physical percentage and predicates; elemental dispatch remains disabled',
                version_difference='Later restricted per-channel pre-resolution handling becomes original post-hit shared-ratio handling; stacking, timing and elemental totals may differ' if approximate_elemental else 'Later per-channel pre-resolution ratio vs original physical post-hit percentage'))
            node.update(children=children,end=self.pos);return node
        if name in getattr(self.schema,'story_small_poly',{}) and self.data[self.pos]!=0xc0:
            node=self.header('array')
            if node['count']!=2:raise ValueError('Reviewed small polymorphic config must retain tag/payload pair')
            tag=self.node();value=scalar(self.data,tag)
            concrete=self.schema.story_small_poly[name].get(value)
            if concrete is None:raise ValueError('Unreviewed small polymorphic tag: '+name+'/'+str(value))
            node['children']=[tag,self.class_value(concrete,path+'<'+concrete+'>',depth+1)]
            node['end']=self.pos
            return node
        if name == DEFEND_SHIELD and not self.original and getattr(self.schema, 'native_shield_cap_bridge', False):
            self.schema.check(name)
            node = self.header('array')
            if node['count'] != 19:
                raise ValueError('Native shield bridge requires exact19 source fields')
            children = []
            for field, pointer in self.schema.members(name, False):
                child = self.typed(pointer, path+'.'+field, depth+1)
                children.append(child)
                if field != 'MaxShieldValue': continue
                if child['code'] != 0xc0:
                    if child['kind'] != 'array' or child['count'] != 3:
                        raise ValueError('Native cap requires fixed DynamicFloat')
                    dynamic, fixed, key = child['children']
                    if dynamic['code'] not in (0xc0, 0xc2) or key['code'] != 0xc0:
                        raise ValueError('Dynamic shield cap requires separate bridge support')
                    raw = self.data[fixed['start']:fixed['end']]
                    if len(raw) != 5 or raw[0] != 0xca:
                        raise ValueError('Native cap requires explicit Float32')
                    import struct, math
                    cap = struct.unpack('>f', raw[1:])[0]
                    if not math.isfinite(cap) or cap <= 0:
                        raise ValueError('Only finite positive source shield caps accepted')
                    self.records.append({'operation':'native_shield_cap_parameter',
                                         'path':path+'.'+field, 'cap':cap, 'float_hex':raw.hex()})
                    for suffix in ('isDynamic','fixedValue','dynamicKey'):
                        del self.leaves[path+'.'+field+'.'+suffix]
                else:
                    self.leaves.pop(path+'.'+field, None)
                self.edits.append((child['start'],child['end'],b''))
            self.edits.append((node['start'],node['header_end'],batch.ability.array_bytes(18)))
            node.update(children=children,end=self.pos)
            return node
        if name == 'MoleMole.Config.DynamicInt' and not self.original and path.endswith('.UniqueMonsterID'):
            members = self.schema.members(name, False)
            if [(n, self.schema.signature(p, False)) for n, p in members] != [('isDynamic', 'primitive:0x2'), ('fixedValue', 'primitive:0x8'), ('dynamicKey', 'primitive:0xe')]:
                raise ValueError('Exact source summon Int wrapper declaration changed')
            node = self.header('array')
            if node['count'] != 3: raise ValueError('Exact source DynamicInt requires3 fields')
            node['children'] = [self.typed(p, path + '.' + n, depth + 1) for n, p in members]
            node['end'] = self.pos
            return node
        if name == DEFEND_SHIELD and not self.original and getattr(self, 'bound_shield', False):
            self.schema.check(name)
            members = self.schema.members(name, False)
            node = self.header('array')
            if node['count'] != 19: raise ValueError('Exact bounded shield requires19 source fields')
            children = []
            for field, pointer in members:
                child = self.typed(pointer, path + '.' + field, depth + 1)
                ratio_hex = (getattr(self, 'bound_shield_evidence', None) or {}).get('ratio_source_hex', '93c0ca3e19999ac0')
                if field == 'ShieldHPRatio' and self.data[child['start']:child['end']] != bytes.fromhex(ratio_hex):
                    raise ValueError('Bounded shield ratio differs from reviewed source proof')
                if field == 'MaxShieldValue':
                    if self.data[child['start']:child['end']] != bytes.fromhex('93c0ca44e10000c0'):
                        raise ValueError('Only exact fixed1800 nonbinding chapter shield cap is permitted')
                    self.edits.append((child['start'], child['end'], b''))
                    self.records.append({'operation': 'remove_later_field', 'path': path + '.' + field,
                        'source_byte_span': [child['start'], child['end']], 'source_hex': '93c0ca44e10000c0',
                        'bounded_proof': getattr(self, 'bound_shield_evidence', None) or 'onlyUL040Normal10117HP1640*NPC7ratio1.15*ShieldHPRatio0.15<1800; no elite/unique/HP override'})
                    for suffix in ('isDynamic', 'fixedValue', 'dynamicKey'):
                        del self.leaves[path + '.' + field + '.' + suffix]
                children.append(child)
            self.edits.append((node['start'], node['header_end'], batch.ability.array_bytes(18)))
            node.update(children=children, end=self.pos)
            return node
        if name != SUMMON_ITEM or self.original or self.data[self.pos] == 0xc0:
            return super().class_value(name, path, depth)
        self.schema.check(name)
        members = self.schema.members(name, False)
        node = self.header('array')
        if node['count'] != 10: raise ValueError('Exact summon item must retain10 fields')
        children = []
        for field, pointer in members:
            child = self.typed(pointer, path + '.' + field, depth + 1)
            if field == 'UniqueMonsterID':
                if child['code'] == 0xc0:
                    # Both formatters skip a nil serialized member, keeping
                    # their constructor's zero/implicit-DynamicInt(0) default.
                    children.append(child)
                    self.records.append({'operation': 'retain_nil_summon_ID_default_zero', 'path': path + '.UniqueMonsterID',
                        'source_byte_span': [child['start'], child['end']]})
                    continue
                if child['kind'] != 'array' or child['count'] != 3:
                    raise ValueError('Summon ID requires a verified fixed wrapper')
                dynamic, fixed, key = child['children']
                if dynamic['code'] not in (0xc0, 0xc2) or fixed['code'] == 0xc0 or key['code'] != 0xc0:
                    raise ValueError('Dynamic summon ID cannot map to original Int32')
                number = scalar(self.data, fixed)
                if not 0 <= number < 1 << 31: raise ValueError('Summon ID outside nonnegative original Int32')
                raw = self.data[fixed['start']:fixed['end']]
                self.edits.append((child['start'], child['end'], raw))
                self.records.append({'operation': 'unwrap_fixed_summon_id', 'path': path + '.UniqueMonsterID',
                    'source_byte_span': [child['start'], child['end']], 'fixed_value': number,
                    'fixed_value_hex': raw.hex(), 'only_fixed_false_or_nil_dynamic_and_nil_key': True})
                for suffix in ('isDynamic', 'fixedValue', 'dynamicKey'):
                    del self.leaves[path + '.UniqueMonsterID.' + suffix]
                self.leaf(path + '.UniqueMonsterID', fixed)
            children.append(child)
        node.update(children=children, end=self.pos)
        return node


def scalar(data, node):
    return None if node['code'] == 0xc0 else monsters.decode_integer(data, node)


def native_evidence(schema, output):
    decoder = schema.source
    header = struct.unpack_from('<64I', decoder.metadata)
    methods = [struct.unpack_from('<12I4H', decoder.metadata, header[12] + i) for i in range(0, header[13], 56)]
    names = {i: decoder.name(m[1]) + '::' + decoder.string(m[0]) for i, m in enumerate(methods)}
    pointers = {i: struct.unpack_from('<I', decoder.binary, 0x418f6e0 + m[6] * 4)[0] for i, m in enumerate(methods) if m[6] != 0xffffffff}
    result = []
    for original, mids in ((False, (58143, 57898, 69709, 71026, 70769, 57107)), (True, (58095, 59189, 49134, 48394))):
        binary = native.E if original else decoder.binary
        lookup = native.ADDR if original else {p: names[i] for i, p in pointers.items()}
        starts = sorted(lookup)
        for mid in mids:
            start = native.pointer(native.M[mid]) if original else pointers[mid]
            end = starts[bisect.bisect_right(starts, start)]
            name = native.N[mid] if original else names[mid]
            lines = []
            for ins in native.MD.disasm(binary[start:end], start):
                target = lookup.get(int(ins.op_str, 16), '') if ins.mnemonic == 'call' and ins.op_str.startswith('0x') else ''
                lines.append(f'{ins.address:08x} {ins.mnemonic} {ins.op_str} {target}')
            result.append({'original': original, 'method_id': mid, 'name': name, 'rva': hex(start), 'end_rva': hex(end),
                'sha256': monsters.sha(binary[start:end]), 'asm': story.store(output, f'evidence/{"original" if original else "source"}-method-{mid}.asm', ('\n'.join(lines) + '\n').encode())})
    if decoder.binary[0x14a29be:0x14a29c8] != bytes.fromhex('807e08000f84a3000000') or decoder.binary[0x14a2a6b:0x14a2a70] != bytes.fromhex('8b460ceb41'):
        raise ValueError('Source fixed DynamicInt Evaluate branch changed')
    if decoder.binary[0x30d286b:0x30d2872] != bytes.fromhex('c7460c00000000'):
        raise ValueError('Source DynamicInt ZERO constructor default changed')
    return {'methods': result, 'fixed_DynamicInt_Evaluate': '58143@14a297a: false isDynamic(+8) returns fixedValue(+c) at14a2a6b',
        'nil_summon_id': 'source71026 ctor retains static default DynamicInt0; both member formatters skip IsNil and retain ctor default; original59189 primitive ID defaults0',
        'source_summon_consumer': '57898 reads UniqueMonsterID+10 and calls58143@26d92a4; nonzero unique lookup, zero evaluates literal MonsterName/TypeName',
        'original_summon_consumer': '49134 primitive UniqueMonsterID, otherwise same MonsterName/TypeName creation branch'}


class AbilityClosure:
    def __init__(self, package, strings, original_map, output):
        self.strings, self.original_map, self.output = strings, original_map, output
        self.before = story.checked(BASE / batch.ability.PATH, ABILITY_SHA)
        self.source = story.checked(ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/reference/source-ability', batch.ability.SOURCE_SHA)
        self.data, self.spans = batch.packed(self.before)[3::2]
        self.source_data, self.source_spans = batch.packed(self.source)[3::2]
        self.schema = ChapterSchema(package, strings)
        self.schema.equipment_attack_pattern_proof = monsters.attack_pattern_union_evidence(self.schema.source)
        self.schema.equipment_attack_patterns = {r['tag']: r['concrete'] for r in self.schema.equipment_attack_pattern_proof if r['original']}
        self.prop_raw = equipment.PROP_BASE.read_bytes()
        self.prop_data, self.prop_spans = batch.packed(self.prop_raw)[3::2]
        self.changes, self.records, self.errors, self.props = {}, {}, {}, {}
        self.monster_refs, self.prop_changes, self.model_aliases = set(), {}, []
        self.runtime_event_references=[]
        self.monster_rows = json.loads((batch.TABLES / 'monsterconfigdata').read_bytes())
        self.unique_rows = json.loads((batch.TABLES / 'uniquemonsterdata').read_bytes())

    def references(self, reader, data):
        identities, props = [], []
        for path, leaf in reader.leaves.items():
            is_ability = path != 'ability.AbilityName' and path.endswith('.AbilityName')
            if not (is_ability or '.PropAdditionalAbilities.key[' in path or path.endswith('.PropObjectName')):
                continue
            q = batch.baked.MessagePackSpanReader(data); q.pos = leaf['span'][0]
            key = scalar(data, q.node())
            if key is None: continue
            if path.endswith('.PropObjectName'):
                props.append(key); continue
            variant = None
            override = reader.leaves.get(path.removesuffix('AbilityName') + 'AbilityOverride') if is_ability else None
            if override:
                q.pos = override['span'][0]; variant = scalar(data, q.node())
                if variant is not None and self.strings[variant] == 'Default': variant = None
            if (is_ability and '<MoleMole.Config.TriggerAbility>.AbilityName' in path
                and self.strings[key] in getattr(self.schema,'event_only_missing_names',())
                and (key,variant) not in self.spans and (key,variant) not in self.source_spans
                and (key,None) not in self.spans and (key,None) not in self.source_spans):
                # Original TriggerAbility.Call53816 -> TriggerAbilityHandler49471
                # -> _TriggerAbilityCommon49469 creates EvtAbilityStart. It does
                # not read the global ConfigAbility registry. Keep the actual
                # action/name/argument bytes; do not invent an ability root.
                self.runtime_event_references.append({'path':path,'event':self.strings[key],
                    'global_config_present':False,'event_action_retained':True,
                    'consumer':'53816 ->49471 ->49469 ->EvtAbilityStart',
                    'handler_coverage':'unproven in supplied reference; human battle acceptance pending'})
                continue
            identities.append((key, variant))
        return list(dict.fromkeys(identities)), list(dict.fromkeys(props))

    def project(self, identity):
        if identity in self.records or identity in self.errors: return
        # Record before descending, so cyclic references remain bounded.
        record = {'identity': identity, 'name': self.strings[identity[0]], 'dependencies': [], 'props': []}
        self.records[identity] = record
        try:
            left, right = self.spans[identity]
            old = self.data[left:right]
            try:
                check = ChapterReader(old, self.strings, self.schema, True)
                checked_root = check.class_value(batch.ability.ABILITY, 'ability')
                if check.pos != len(old): raise ValueError('Existing root logical boundary differs')
                value, operation, adaptations = old, 'retain_existing_consumer_valid', []
            except (ValueError, KeyError):
                sl, sr = self.source_spans[identity]
                if old != self.source_data[sl:sr]:
                    raise ValueError('Existing modified root invalid; refuse overwrite')
                reader = ChapterReader(self.source_data, self.strings, self.schema)
                reader.bound_shield = (identity == (15671, None) and getattr(self, 'bound_shield_proof', None) is not None) or identity in getattr(self, 'bounded_shield_identities', {})
                reader.bound_shield_evidence = getattr(self, 'bounded_shield_identities', {}).get(identity)
                reader.pos = sl; reader.class_value(batch.ability.ABILITY, 'ability')
                if reader.pos != sr: raise ValueError('Source root logical boundary differs')
                value = batch.apply_edits(self.source_data, sl, sr, reader)
                check = ChapterReader(value, self.strings, self.schema, True)
                checked_root = check.class_value(batch.ability.ABILITY, 'ability')
                _, translated = batch.retained_terminals(reader)
                if check.pos != len(value) or set(translated) != set(check.leaves) or any(x['sha256'] != check.leaves[p]['sha256'] for p, x in translated.items()):
                    raise ValueError('Retained gameplay terminals or original consumer differ')
                self.changes[identity] = value
                operation, adaptations = 'project_exact_source_root', reader.records
            dependencies, props = self.references(check, value)
            summons = []
            specials = {}
            for item in checked_root['children'][4].get('custom_items', []):
                q = batch.baked.MessagePackSpanReader(value); q.pos = item['source_byte_span'][0]
                q.node(); dtype = scalar(value, q.node()); atom = q.node()
                if dtype == 4: specials[item['key']] = self.strings[scalar(value, atom)]
            for path, leaf in check.leaves.items():
                if not path.endswith('.UniqueMonsterID') or '.SummonMonsters[' not in path: continue
                prefix = path.removesuffix('.UniqueMonsterID')
                q = batch.baked.MessagePackSpanReader(value); q.pos = leaf['span'][0]; unique_id = scalar(value, q.node()) or 0
                if unique_id:
                    meta = next(r for r in self.unique_rows if r['uniqueID'] == unique_id)
                    name, variant = meta['monsterName'], meta['typeName']
                else:
                    literals = []
                    for field in ('MonsterName', 'TypeName'):
                        dynamic = check.leaves[prefix + '.' + field + '.isDynamic']; key = check.leaves[prefix + '.' + field + '.dynamicKey']; fixed = check.leaves[prefix + '.' + field + '.fixedValue']
                        if value[dynamic['span'][0]] == 0xc3:
                            q.pos = key['span'][0]; special_name = self.strings[scalar(value, q.node())]
                            if special_name not in specials: raise ValueError('Dynamic summon key has no pinned default literal')
                            literals.append(specials[special_name])
                        elif value[dynamic['span'][0]] in (0xc0, 0xc2) and value[key['span'][0]] == 0xc0:
                            q.pos = fixed['span'][0]; index = scalar(value, q.node()); literals.append(self.strings[index])
                        else: raise ValueError('Unbounded dynamic monster summon names')
                    name, variant = literals
                meta = next(r for r in self.monster_rows if r['monsterName'] == name and r['typeName'] == variant)
                mid = self.strings.index(meta['configFile']), None if meta['configType'] == 'Default' else self.strings.index(meta['configType'])
                self.monster_refs.add(mid)
                summons.append({'identity': mid, 'monster_row': meta, 'source_field': prefix, 'unique_id': unique_id,
                    'ability_specials_default_literals': specials,
                    'parent_override_policy': 'Pinned actual Monster primary DynamicArguments have no MonsterName0/1 or MonsterType0/1 replacements; no stage attr replaces SummonDG010 arguments'})
            record.update(before_sha256=monsters.sha(old), after_sha256=monsters.sha(value), operation=operation,
                original_consumer_valid=True, retained_terminals_equal=True, dependencies=dependencies, props=props,
                adaptations=adaptations, summoned_monsters=summons)
            if identity in self.changes:
                record['overlay'] = story.store(self.output, f'overlays/ability/{identity[0]}-{identity[1] if identity[1] is not None else "default"}.bin', value)
            for other in dependencies: self.project(other)
            for key in props: self.prop(key)
        except (ValueError, KeyError, IndexError) as error:
            self.errors[identity] = str(error)
            record['blocker'] = str(error)

    def prop(self, key):
        if key in self.props: return
        record = {'key': key, 'name': self.strings[key], 'dependencies': []}
        self.props[key] = record
        try:
            left, right = self.prop_spans[key, None]
            q = batch.baked.MessagePackSpanReader(self.prop_data); q.pos = left; node = q.node()
            model = self.strings[scalar(self.prop_data, node['children'][1])].lower()
            value = self.prop_data[left:right]
            alias = 'entities/propobject/level1/' + model.rsplit('/', 1)[-1]
            aliases = {'entities/propobject/invisibleprop': 'Entities/PropObject/Level1/InvisibleProp',
                'entities/propobject/trap_spike': 'Entities/PropObject/Level1/Trap_Spike',
                'entities/propobject/trap_fire': 'Entities/PropObject/Level1/Trap_Fire',
                'entities/propobject/jokeboxsimple': 'Entities/PropObject/Level1/JokeBoxSimple'}
            aliases.update(getattr(self, 'model_path_aliases', {}))
            if (model not in self.original_map and model not in aliases
                and getattr(self,'resolve_original_prop_basename',False)):
                matches=[p for p in self.original_map if p.startswith('entities/propobject/')
                         and p.rsplit('/',1)[-1]==model.rsplit('/',1)[-1]]
                if len(matches)==1:aliases[model]=matches[0]
            if model in aliases:
                alias = aliases[model].lower()
            if model not in self.original_map and alias in self.original_map and model in aliases:
                canonical = aliases[model]
                if canonical not in self.strings: self.strings.append(canonical)
                index = self.strings.index(canonical); field = node['children'][1]
                value = self.prop_data[left:field['start']] + batch.ability.integer_bytes(index) + self.prop_data[field['end']:right]
                self.prop_changes[key, None] = value
                self.model_aliases.append({'prop_key': key, 'before_model': model, 'after_model': alias, 'new_string_index': index,
                    'only_Model_field_changed': True, 'original_resource': self.original_map[alias]})
                model = alias
            if model not in self.original_map: raise ValueError('Original prop prefab absent: ' + model)
            reader = ChapterReader(value, self.strings, self.schema, True)
            reader.class_value('MoleMole.Config.ConfigPropObject', 'prop')
            if reader.pos != len(value): raise ValueError('Original prop logical boundary differs')
            deps, other_props = self.references(reader, value)
            abilities = node['children'][5]
            if abilities['code'] != 0xc0:
                for child in abilities['children']:
                    ak, av = [scalar(self.prop_data, n) for n in child['children']]
                    if av is not None and self.strings[av] == 'Default': av = None
                    deps.append((ak, av))
            deps = list(dict.fromkeys(deps))
            record.update(root_sha256=monsters.sha(self.prop_data[left:right]), original_full_root_consumed=True,
                model=model, dependencies=deps, after_sha256=monsters.sha(value))
            if (key, None) in self.prop_changes:
                record['overlay'] = story.store(self.output, f'overlays/prop/{key}-default.bin', value)
            for dep in deps: self.project(dep)
            for other in other_props: self.prop(other)
        except (ValueError, KeyError, IndexError) as error: record['blocker'] = str(error)

    def failure_chain(self, seeds):
        pending, seen, found = list(seeds), set(), []
        while pending:
            identity = pending.pop()
            if identity in seen: continue
            seen.add(identity)
            record = self.records.get(identity, {})
            if identity in self.errors: found.append({'identity': identity, 'reason': self.errors[identity]})
            pending.extend(record.get('dependencies', []))
            for key in record.get('props', []):
                prop = self.props[key]
                if 'blocker' in prop: found.append({'prop': key, 'reason': prop['blocker']})
                pending.extend(prop['dependencies'])
        return found


def project_monsters(before, identities, strings, output):
    _, _, _, data, _, spans = batch.packed(before)
    changes, records, failures = {}, {}, {}
    for identity in sorted(identities, key=lambda x: (x[0], -1 if x[1] is None else x[1])):
        record = {'identity': identity, 'config': strings[identity[0]], 'dependencies': []}
        records[identity] = record
        try:
            resolved = identity if identity in spans else (identity[0], None)
            left, right = spans[resolved]
            if resolved != identity:
                record['registry_fallback'] = {'requested': identity, 'resolved': resolved,
                    'consumer': 'MonsterData.GetConfigMonsterRaw59878 -> generic GetConfig; missing override resolves primary'}
            reader = monsters.MonsterReader(data); reader.pos = left
            count = reader.header('array')['count']
            if count == 19:
                reader.pos = left; root = reader.root(strings, 19)
                if reader.pos != right: raise ValueError('Retained original monster boundary differs')
                if any(n['count'] != 16 for n in root['children'][7]['children'][1::2]): raise ValueError('Existing monster skills not original16')
                monsters.anim_event_pattern_projection(data, root, strings, True)
                value, operation = data[left:right], 'retain_existing_consumer_valid'
            else:
                value, facts = monsters.project_root(data, left, right, strings, True)
                changes[resolved] = value
                record['projection'] = facts
                operation = 'project_exact_source_root'
                reader = monsters.MonsterReader(value); root = reader.root(strings, 19)
            # Read original logical ability entries from retained/projected bytes.
            reader = monsters.MonsterReader(value); root = reader.root(strings, 19)
            abilities = root['children'][6]
            dependencies = []
            for n in abilities['children'][1::2]:
                if n['kind'] != 'array' or n['count'] != 2: raise ValueError('Monster ability reference shape differs')
                ak, av = [scalar(value, c) for c in n['children']]
                if av is not None and strings[av] == 'Default': av = None
                dependencies.append((ak, av))
            record.update(operation=operation, before_sha256=monsters.sha(data[left:right]), after_sha256=monsters.sha(value),
                original_consumer_valid=True, dependencies=dependencies)
            if resolved in changes:
                record['overlay'] = story.store(output, f'overlays/monster/{identity[0]}-{identity[1] if identity[1] is not None else "default"}.bin', value)
        except (ValueError, KeyError, IndexError) as error:
            failures[identity] = str(error); record['blocker'] = str(error)
    return story.reassemble(before, changes), list(records.values()), failures


def build(output=OUTPUT, audit_path=None):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists(): raise ValueError('Use a new workspace candidate directory')
    if lua.file_sha(resources.DEFAULT19) != lua.ORIGINAL19_SHA or lua.file_sha(resources.DEFAULT24) != monsters.SOURCE24_SHA:
        raise ValueError('Pinned source package changed')
    strings = story.checked(batch.STRINGS, story.STRING_SHA).decode().split('\x1f')
    story.checked(BASE / '_baked/bakedweapondata', WEAPON_SHA)
    monster_before = story.checked(STORY_BASE / monsters.PATH, MONSTER_SHA)
    npc_before = story.checked(STORY_BASE / npc.PATH, NPC_SHA)
    tables = {n: json.loads((batch.TABLES / n).read_bytes()) for n in ('stagedata_main', 'monsterconfigdata', 'plotdata', 'dialogdata', 'tutorialstepdata', 'avatartrialdata', 'teambuffdata', 'uniquemonsterdata')}
    equipment_matrix = json.loads((ROOT / '.local-baseline/server19-dev/cultivation-full-equipment-ready/matrix.json').read_bytes())
    roster = json.loads((ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/manifest.json').read_bytes())
    stages = [r for r in tables['stagedata_main'] if r['levelId'] in SCOPE]
    if [r['levelId'] for r in stages] != list(SCOPE): raise ValueError('Actual26-stage catalog changed')
    original_map = {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}
    source_map = {r['path']: r for r in resources.resource_map(resources.DEFAULT24)}
    signatures, files, matrices, monster_ids = lua.method_signatures(), [], [], set()
    output.mkdir(parents=True)
    required_shared = []
    shared = json.loads((lua.DEFAULT_OUTPUT / 'manifest.json').read_bytes())
    for r in shared['files']:
        raw = story.checked(lua.DEFAULT_OUTPUT / r['path'], r['output_sha256'])
        required_shared.append({'path': r['path'], 'required_existing_sha256': monsters.sha(raw)})
    with zipfile.ZipFile(resources.DEFAULT19) as original, zipfile.ZipFile(resources.DEFAULT24) as source:
        closure = AbilityClosure(source, strings, original_map, output)
        consumer_evidence = native_evidence(closure.schema, output)
        monster_schema_evidence = monsters.schema_evidence(source, True)
        prop_dispatch = {'medic_box': 'GeneralBox', 'award_box': 'AdvancedBox', 'equip_box': 'JokeBox',
            'roguereward_box': 'JokeBoxSimple', 'witch_time_box': 'JokeBox', 'switch': 'Switch', 'barrel': 'Barrel',
            'pumpkin_box': 'PumpkinBox', 'AiBox': 'AiModelBox', 'slow_area': 'MPLevel_FrozenArea',
            'spike_trap': 'Trap_Spike', 'special_spike_trap': 'Trap_Spike_Special', 'fire_trap': 'Trap_Fire', 'laser_trap': 'Trap_Laser'}
        module_reports = {}
        def module(path):
            if path in {r['path'] for r in required_shared}: return []
            if path in module_reports: return module_reports[path]['blockers']
            report = {'path': path, 'blockers': []}; module_reports[path] = report
            p, m, v = (original, original_map, '1.9') if path in original_map else (source, source_map, '2.4')
            if path not in m:
                report['blockers'].append({'kind': 'Lua_require_missing', 'path': path}); return report['blockers']
            raw, provenance = lua.text_record(p, m[path], v)
            text = raw.decode('utf-8-sig'); calls = lua.calls(text)
            for c in calls:
                if c['static_argument_count'] is None or not any(o['minimum_args'] <= c['static_argument_count'] <= o['maximum_args'] for o in signatures.get(c['method'], [])):
                    report['blockers'].append({'kind': 'shared_native_API', 'path': path, 'call': c})
            report.update(source=provenance, native_calls=calls, requires=lua.requires(text))
            for dep in report['requires']: report['blockers'].extend(module(dep['path']))
            files.append({**story.store(output, path, raw), 'operation': 'add', 'required_existing_sha256': None, 'source_bytes_unchanged': True})
            return report['blockers']
        for stage in stages:
            path = stage['luaFile'].lower()
            package, mapping, version = (original, original_map, '1.9') if path in original_map else (source, source_map, '2.4')
            raw, provenance = lua.text_record(package, mapping[path], version)
            text = raw.decode('utf-8-sig')
            calls, waves = lua.calls(text), lua.normal_monster_waves(text, {r['monsterName'] for r in tables['monsterconfigdata']})
            missing = [c for c in calls if c['static_argument_count'] is None or not any(o['minimum_args'] <= c['static_argument_count'] <= o['maximum_args'] for o in signatures.get(c['method'], []))]
            matrix = {'stage_id': stage['levelId'], 'act_id': stage['actId'], 'lua': path, 'source': provenance,
                'original19_script_present': path in original_map, 'historical19_equivalence': path in original_map,
                'hard_level': stage['hardLevel'], 'pre_level_ids': stage['preLevelID'], 'native_calls': calls,
                'normal_monster_waves': waves, 'requires': lua.requires(text), 'monster_identities': [], 'ability_seeds': [], 'prop_seeds': [], 'blockers': []}
            if missing: matrix['blockers'].append({'kind': 'native_API', 'calls': missing})
            for dep in matrix['requires']: matrix['blockers'].extend(module(dep['path']))
            for wave in lua.normal_monster_waves(text, set(prop_dispatch)):
                if wave['monster'] not in prop_dispatch: continue
                prop_name = prop_dispatch[wave['monster']]
                key = strings.index(prop_name)
                matrix['prop_seeds'].append(key); closure.prop(key)
                matrix.setdefault('normal_prop_waves', []).append({**wave, 'native_config_name': prop_name, 'config_key': key})
            for wave in waves:
                matches = [r for r in tables['monsterconfigdata'] if r['monsterName'] == wave['monster'] and r['typeName'] == wave['configType']]
                if len(matches) != 1: raise ValueError('Exact monster row absent or ambiguous')
                row = matches[0]
                assets = []
                model = 'entities/monster/' + row['categoryName'].lower() + '/' + row['subTypeName'].lower() + '/' + row['subTypeName'].lower()
                ai = 'ai/monster/' + row['AIName'].lower()
                for asset in (model, ai):
                    if asset not in original_map:
                        matrix['blockers'].append({'kind': 'original_monster_asset_missing', 'monster': wave['monster'], 'path': asset})
                        continue
                    obj, payload = resources.object_bytes(original, original_map[asset])
                    assets.append({'path': asset, 'class': obj['class'], 'sha256': monsters.sha(payload), 'operation': 'retain_original_APK'})
                matrix.setdefault('original_monster_resources', []).extend(assets)
                identity = strings.index(row['configFile']), None if row['configType'] == 'Default' else strings.index(row['configType'])
                monster_ids.add(identity); matrix['monster_identities'].append(identity)
                attrs = set(wave['explicit_attributes']) | ({'Elite_EliteShield'} if wave['isElite'] else set())
                for name in sorted(attrs):
                    key, variant = strings.index(name), strings.index(wave['monster'])
                    # Native override lookup falls back to primary only when no
                    # named override exists in the unchanged source registry.
                    candidate = key, variant
                    if candidate not in closure.spans: candidate = key, None
                    matrix['ability_seeds'].append(candidate)
            for c in calls:
                if c['method'] in ('AddNewAbilityToAvatar', 'AddNewAbility'):
                    matrix['ability_seeds'].append((strings.index(c['arguments'][1].strip('"\'')), None))
                if c['method'] == 'AddTeamBuffById':
                    matches = [r for r in tables['teambuffdata'] if r['buffId'] == int(c['arguments'][0])]
                    if len(matches) != 1: raise ValueError('Native team buff row missing')
                    matrix.setdefault('team_buff_rows', []).extend(matches)
                    matrix['ability_seeds'].append((strings.index(matches[0]['abilityName']), None))
                if c['method'] == 'CreateTrialAdhocAvatar':
                    trial_id = int(c['arguments'][0])
                    trial = next(r for r in tables['avatartrialdata'] if r['ID'] == trial_id)
                    actor = next(r for r in roster['roster'] if r['avatar_id'] == trial['avatarID'])
                    bought = {r['skillID'] for r in trial['avatarSubSkills'] if r['skillLV'] > 0}
                    deps = [r for r in actor['dependencies'] if r['scope'] == 'base' or
                        r.get('evidence', {}).get('sub_skill_id') in bought or
                        r['scope'] == 'default_skill']
                    matrix['ability_seeds'].extend((r['key'], r['variant']) for r in deps)
                    gear = [trial['weaponID'], trial['stigmataID1'], trial['stigmataID2'], trial['stigmataID3']]
                    gear_reports = [next(r for r in equipment_matrix['items'] if r['item_id'] == item) for item in gear if item]
                    for item in gear_reports:
                        if item['blockers']: matrix['blockers'].append({'kind': 'trial_equipment', 'item_id': item['item_id'], 'details': item['blockers']})
                        matrix['ability_seeds'].extend((r['key'], r['variant']) for r in item['skills'])
                    matrix['trial_avatars'] = [{'row': trial, 'native_id_kind': 'trial_table_ID_not_avatar_ID',
                        'ability_gate_dependencies': deps, 'equipment_evidence': gear_reports,
                        'source_equipment_matrix_sha256': lua.file_sha(ROOT / '.local-baseline/server19-dev/cultivation-full-equipment-ready/matrix.json')}]
            matrix['monster_identities'] = list(dict.fromkeys(matrix['monster_identities']))
            matrix['ability_seeds'] = list(dict.fromkeys(matrix['ability_seeds']))
            matrices.append(matrix)
            files.append({**story.store(output, path, raw), 'operation': 'add', 'required_existing_sha256': None,
                'source_bytes_unchanged': True})
        shield_consumers = [(m, w) for m in matrices for w in m['normal_monster_waves'] if w['monster'] == 'UlyssesDefend']
        if len(shield_consumers) != 1 or shield_consumers[0][0]['stage_id'] != 10117 or shield_consumers[0][1]['isElite'] or shield_consumers[0][1]['configType'] != 'Default':
            raise ValueError('Bounded shield consumer scope changed')
        stage17 = next(r for r in stages if r['levelId'] == 10117)
        text17 = (output / stage17['luaFile'].lower()).read_text(encoding='utf-8-sig')
        tokens17 = lua.lua_tokens(text17)
        if stage17['UseDynamicHardLv'] or stage17['hardLevel'] != 7 or any(t[0] in ('hpRatio', 'global_attr', 'hard_level', 'SetMonsterHPRatio', 'SetMonsterMaxHP') for t in tokens17):
            raise ValueError('UL040 HP modifier violates bounded chapter shield proof')
        ul040 = next(r for r in tables['monsterconfigdata'] if r['monsterName'] == 'UlyssesDefend' and r['typeName'] == 'Default')
        if ul040['HP'] != 1640.0: raise ValueError('Bounded UL040 basic HP changed')
        old_start = native.pointer(native.M[48394])
        old_end = sorted(native.ADDR)[bisect.bisect_right(sorted(native.ADDR), old_start)]
        old_ins = list(native.MD.disasm(native.E[old_start:old_end], old_start))
        if not any(x.mnemonic == 'mulss' for x in old_ins) or any(x.mnemonic == 'call' and native.ADDR.get(int(x.op_str, 16), '').endswith('Mathf::Clamp') for x in old_ins if x.op_str.startswith('0x')):
            raise ValueError('Original shield must retain the uncapped HP*ratio calculation')
        closure.bound_shield_proof = {'scope_stage_ids': list(SCOPE), 'actual_consumer_stage': 10117,
            'actual_monster_name': 'UlyssesDefend', 'isElite': False, 'uniqueID': None, 'hard_level': 7,
            'source_stage_sha256': monsters.sha((output / stage17['luaFile'].lower()).read_bytes()),
            'source_stage_UseDynamicHardLv': 0, 'explicit_HP_or_hard_override_absent': True,
            'baseHP': 1640.0, 'NPC7_HPRatio': 1.15, 'fixed_ShieldHPRatio': 0.15, 'fixed_source_MaxShieldValue': 1800.0,
            'actual_uncapped_shield': 1640.0 * 1.15 * 0.15,
            'conservative_all_chapter_hard14_bound': 1640.0 * 1.757 * 0.15,
            'original_OnAdded_method_id': 48394, 'original_OnAdded_rva': hex(old_start), 'original_OnAdded_sha256': monsters.sha(native.E[old_start:old_end]),
            'original_calculation': 'SafeFloat monster HP times ActorAbility Evaluate ShieldHPRatio; no later Clamp/cap',
            'future_scope_guard': 'No generic nonnil exception; only15671 exact fixed1800 / current26 sources / UL040 Normal10117. Future HP buffs, elite, unique or hard>14 need cap support or new bounded proof.'}
        monster_after, monster_records, monster_errors = project_monsters(monster_before, monster_ids, strings, output)
        by_identity = {tuple(r['identity']): r for r in monster_records}
        for matrix in matrices:
            for identity in matrix['monster_identities']:
                if identity in monster_errors: matrix['blockers'].append({'kind': 'monster', 'identity': identity, 'reason': monster_errors[identity]})
                matrix['ability_seeds'].extend(by_identity[identity]['dependencies'])
            matrix['ability_seeds'] = list(dict.fromkeys(matrix['ability_seeds']))
            for identity in matrix['ability_seeds']: closure.project(identity)
            matrix['blockers'].extend({'kind': 'ability_closure', **r} for r in closure.failure_chain(matrix['ability_seeds']))
            for key in matrix['prop_seeds']:
                prop = closure.props[key]
                if 'blocker' in prop: matrix['blockers'].append({'kind': 'prop', 'key': key, 'reason': prop['blocker']})
                matrix['blockers'].extend({'kind': 'prop_ability_closure', **r} for r in closure.failure_chain(prop['dependencies']))
        # Actual summon defaults must remain part of the exact packed Monster
        # closure; refuse readiness if a newly discovered factory escapes it.
        missing_summon_roots = closure.monster_refs - monster_ids
        if missing_summon_roots:
            raise ValueError('Additional actual summoned Monster roots require closure: ' + str(sorted(missing_summon_roots)))
        files.append({**story.store(output, monsters.PATH, monster_after), 'operation': 'replace', 'required_existing_sha256': MONSTER_SHA})
        ability_after = story.reassemble(closure.before, closure.changes)
        files.append({**story.store(output, batch.ability.PATH, ability_after), 'operation': 'replace', 'required_existing_sha256': ABILITY_SHA})
        if closure.prop_changes:
            files.append({**story.store(output, '_baked/bakedpropdata', story.reassemble(closure.prop_raw, closure.prop_changes)),
                'operation': 'replace', 'required_existing_sha256': monsters.sha(closure.prop_raw)})
        if closure.model_aliases:
            for alias in closure.model_aliases:
                obj, raw = resources.object_bytes(original, alias['original_resource'])
                alias.update(original_object_class=obj['class'], original_object_bytes=len(raw), original_object_sha256=monsters.sha(raw),
                    original_prefab_bytes_unchanged=True)
            string_before = batch.STRINGS.read_bytes(); string_after = '\x1f'.join(strings).encode()
            if not string_after.startswith(string_before + b'\x1f') or strings[:len(string_before.decode().split('\x1f'))] != string_before.decode().split('\x1f'):
                raise ValueError('StringMap append changed prior bytes or indices')
            files.append({**story.store(output, '_baked/stringmap.txt', string_after), 'operation': 'replace', 'required_existing_sha256': story.STRING_SHA})
        _, raw = resources.object_bytes(source, source_map[npc.PATH])
        typed = SourceTypedDecoder(source).rows(raw, 'MoleMole.NPCLevelMetaData')
        _, raw = resources.object_bytes(source, source_map[npc.TEXT_PATH]); _, tsv = resources.text_asset(raw)
        if monsters.sha(tsv) != npc.SOURCE_TSV_SHA: raise ValueError('Pinned NPC source TSV changed')
        source_rows = list(csv.DictReader(io.StringIO(tsv.decode()), delimiter='\t'))
        increments = []
        for hard in sorted({s['hardLevel'] for s in stages}):
            matches, typed_matches = [r for r in source_rows if int(r['HardLevel']) == hard], [r for r in typed if r['HardLevel'] == hard]
            if len(matches) != 1 or len(typed_matches) != 1: raise ValueError('NPC source row absent or ambiguous')
            source_row, typed_row = matches[0], typed_matches[0]
            row = {f: int(source_row[f]) if f == 'HardLevel' else float(source_row[f]) for f in npc.FIELDS}
            if any(struct.pack('<f', row[f]) != struct.pack('<f', typed_row[f]) for f in npc.FIELDS[1:]):
                raise ValueError('NPC TSV/typed float32 disagreement')
            increments.append({'source_row': source_row, 'source_typed_row': typed_row, 'output_row': row,
                'float32_hex': {f: struct.pack('<f', row[f]).hex() for f in npc.FIELDS[1:]}})
        combined = json.loads(npc_before) + [r['output_row'] for r in increments]
        npc_after = (native_json(combined)[0] + '\n').encode()
        if json.loads(npc_after)[:4] != json.loads(npc_before): raise ValueError('NPC1..4 changed')
        files.append({**story.store(output, npc.PATH, npc_after), 'operation': 'replace', 'required_existing_sha256': NPC_SHA})
    # Scene/waypoint and CG checks are an independent pass. The native Act107
    # entrance remains a separate business deployment gate, preserving type2.
    independent = None
    if audit_path is not None:
        audit_path = Path(audit_path).resolve()
        independent = json.loads(audit_path.read_bytes())
        if not independent.get('complete_resource_audit'):
            raise ValueError('Independent resource audit is incomplete')
        if [r['stage_id'] for r in independent['stages']] != list(SCOPE):
            raise ValueError('Independent stage scope differs')
        by_stage = {r['stage_id']: r for r in independent['stages']}
    for matrix in matrices:
        if independent is None:
            matrix['blockers'].append({'kind': 'independent_scene_CG_entry_audit_pending'})
        else:
            other = by_stage[matrix['stage_id']]
            if other['source']['source_text_sha256'] != matrix['source']['source_text_sha256']:
                raise ValueError('Independent Lua source hash differs')
            matrix['independent_original_resource_audit'] = other
            matrix['blockers'].extend(other.get('resource_blockers', []))
        matrix['candidate_status'] = 'static_ready_human_pending' if not matrix['blockers'] else 'blocked'
    ready = [r['stage_id'] for r in matrices if not r['blockers']]
    manifest = {'format': 'server19-chapter1-remaining-resources-v1', 'scope_stage_ids': list(SCOPE),
        'ready_stage_ids': ready, 'blocked_stage_ids': [i for i in SCOPE if i not in ready], 'chapter1_remaining_inventory': matrices,
        'files': files, 'deployment_files': [r['path'] for r in files], 'ability_root_overlay': list(closure.records.values()),
        'ability_failures': [{'identity': k, 'reason': v} for k, v in closure.errors.items()], 'props': list(closure.props.values()),
        'monster_root_overlay': monster_records, 'npc_increments': increments,
        'new_shared_Lua_closure': list(module_reports.values()),
        'prop_root_overlay': list(closure.props.values()), 'exact_original_model_path_aliases': closure.model_aliases,
        'bounded_shield_compatibility_proof': closure.bound_shield_proof, 'native_consumer_evidence': consumer_evidence,
        'monster_schema_evidence': monster_schema_evidence,
        'independent_audit': None if independent is None else {'path': str(audit_path), 'sha256': lua.file_sha(audit_path)},
        'visual_missing_items': [{'id': 3108, 'status': 'original_sprite_missing_native_ItemEmpty_fallback'},
            {'id': 10603, 'status': 'original_sprite_missing_native_ItemEmpty_fallback'}],
        'required_existing_shared_Lua_files': required_shared,
        'accepted_preimages': {'ability': ABILITY_SHA, 'monster': MONSTER_SHA, 'npc': NPC_SHA, 'weapon': WEAPON_SHA, 'stringmap': story.STRING_SHA},
        'source19_sha256': lua.ORIGINAL19_SHA, 'source24_sha256': monsters.SOURCE24_SHA,
        'limits': ['No device, server, save, native library or human gameplay changes',
            'Later2.4 compatibility inputs; historical1.9 Lua and random DropSeq unavailable',
            '3108/10603 original icons unavailable; original SafeSetSprite ItemEmpty fallback is retained, no substitute sprite or reward deletion',
            'Static candidate only; each actual stage entrance, plot and battle still needs human acceptance']}
    story.store(output, 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
    return manifest


def verify(output):
    output = Path(output).resolve()
    manifest_raw = (output / 'manifest.json').read_bytes(); m = json.loads(manifest_raw)
    for file in m['files']:
        raw = (output / file['path']).read_bytes()
        if len(raw) != file['bytes'] or monsters.sha(raw) != file['sha256']:
            raise ValueError('Saved candidate changed: ' + file['path'])
    for path, base_path, digest, roots in (
        (batch.ability.PATH, BASE / batch.ability.PATH, ABILITY_SHA, m['ability_root_overlay']),
        (monsters.PATH, STORY_BASE / monsters.PATH, MONSTER_SHA, m['monster_root_overlay']),
        ('_baked/bakedpropdata', equipment.PROP_BASE, monsters.sha(equipment.PROP_BASE.read_bytes()), m['prop_root_overlay'])):
        if not (output / path).exists(): continue
        before = story.checked(base_path, digest)
        changes = {}
        for root in roots:
            if 'overlay' not in root: continue
            identity = tuple(root['identity']) if 'identity' in root else (root['key'], None)
            raw = (output / root['overlay']['path']).read_bytes()
            if monsters.sha(raw) != root['after_sha256']: raise ValueError('Saved overlay changed')
            changes[identity] = raw
        if story.reassemble(before, changes) != (output / path).read_bytes():
            raise ValueError('Saved registry no longer preserves unselected roots: ' + path)
    strings_before = batch.STRINGS.read_bytes()
    if (output / '_baked/stringmap.txt').exists():
        after = (output / '_baked/stringmap.txt').read_bytes()
        if not after.startswith(strings_before + b'\x1f'): raise ValueError('Saved StringMap changed prior bytes')
    previous = json.loads(story.checked(STORY_BASE / npc.PATH, NPC_SHA))
    current = json.loads((output / npc.PATH).read_bytes())
    if current[:4] != previous or [r['HardLevel'] for r in current] != list(range(1, 15)):
        raise ValueError('Saved NPC scope or previous rows changed')
    result = {'status': 'saved_candidate_roots_files_and_preservation_verified', 'files': len(m['files']),
        'ready_stage_ids': m['ready_stage_ids'], 'blocked_stage_ids': m['blocked_stage_ids'],
        'manifest_sha256': monsters.sha(manifest_raw), 'human_gameplay_acceptance': 'pending'}
    story.store(output, 'verification.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.output), ensure_ascii=False)); return
    m = build(args.output, args.audit)
    print(json.dumps({'output': str(args.output.resolve()), 'ready_stage_ids': m['ready_stage_ids'],
        'ability_changed_roots': sum('overlay' in r for r in m['ability_root_overlay']),
        'ability_failures': m['ability_failures'], 'monster_changed_roots': sum('overlay' in r for r in m['monster_root_overlay']),
        'stage_blockers': {r['stage_id']: r['blockers'] for r in m['chapter1_remaining_inventory']}}, ensure_ascii=False))


if __name__ == '__main__': main()
