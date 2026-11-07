"""Build a bounded equipment/character battle dependency overlay, never deploy it.

Inventory, sourced normal 10101..10110 drops, their evolution chains and the
25 original-scope avatars' starter weapons are included. Later source tables
remain compatibility inputs, not a claim of historical original balancing.
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
import json
import struct
from pathlib import Path
import zipfile

import server19_avatar_battle_resources as batch
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
BASE = ROOT / '.local-baseline/server19-dev/mixed-team-equipment-ready/bakedabilitydata'
BASE_SHA = '2e9e1bdfb7653840511013a39964f414e2a656f90b3d10197de671e66c23b7c0'
ROSTER = ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2'
DEFAULT_ACCOUNT = ROOT / 'server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json'
DEFAULT_OUTPUT = ROOT / '.local-baseline/server19-dev/equipment-chain-batch-ready'
PROP_BASE = ROOT / '.local-baseline/server19-dev/act101-native-prop-resources/_baked/bakedpropdata'


class ClosureReader(batch.BattleReader):
    """Also follow original Prop animation's polymorphic AttackPattern union."""
    def class_value(self, name, path, depth=0):
        if name == 'MoleMole.Config.TriggerRefPropSelect' and self.data[self.pos] != 0xc0:
            node = self.header('array')
            if node['count'] != 2:
                raise ValueError('Prop selector must preserve tag/payload union')
            tag = self.node(); value = integer(self.data, tag)
            concrete = self.schema.equipment_prop_selectors.get(value)
            if concrete is None:
                raise ValueError('Prop selector dispatch unproven: ' + str(value))
            node['children'] = [tag, self.class_value(concrete, path + '<' + concrete + '>', depth + 1)]
            node['end'] = self.pos
            return node
        if name == 'MoleMole.Config.ConfigEntityAttackPattern' and self.data[self.pos] != 0xc0:
            node = self.header('array')
            if node['count'] != 2:
                raise ValueError('AttackPattern must preserve tag/payload union')
            tag = self.node(); value = integer(self.data, tag)
            concrete = self.schema.equipment_attack_patterns.get(value)
            if concrete is None:
                raise ValueError('AttackPattern concrete dispatch unproven: ' + str(value))
            node['children'] = [tag, self.class_value(concrete, path + '<' + concrete + '>', depth + 1)]
            node['end'] = self.pos
            return node
        return super().class_value(name, path, depth)


def prop_selector_evidence(schema):
    """Resolve both clients' actual selector formatter generic arguments."""
    result = []
    for original in (True, False):
        binary = batch.baked.native.E if original else schema.source.binary
        metadata = batch.baked.native.B if original else schema.source.metadata
        base = 0x33e39d8 if original else 0x42531e4
        usage = schema.original_usage if original else schema.source_usage
        spec_pair, inst_pair = (0x34a67cc, 0x34a67b4) if original else (0x42520f0, 0x42520d8)
        branches = ((1,0x7601eb,-0x65a4c),(2,0x760179,-0x65a54)) if original else ((1,0x241eab7,0x103b64),(2,0x241ea45,0x103b68))
        header = struct.unpack_from('<64I', metadata)
        for tag, branch, displacement in branches:
            ins = next(batch.baked.native.MD.disasm(binary[branch:branch+8],branch))
            expected = ('mov' if original else 'lea', 'eax, '+('dword ptr ' if original else '')+'[ebx '+('-' if displacement < 0 else '+')+' '+hex(abs(displacement))+']')
            if (ins.mnemonic, ins.op_str) != expected:
                raise ValueError('Prop selector native dispatch changed')
            address = base + displacement
            if original: address = struct.unpack_from('<I',binary,address)[0]
            token = usage[address]
            if token >> 29 != 6: raise ValueError('Selector lacks MethodRef')
            count, specs = struct.unpack_from('<II',binary,spec_pair)
            index = token & 0x1fffffff
            if index >= count: raise ValueError('Selector MethodSpec outside registration')
            method, class_inst, method_inst = struct.unpack_from('<3i',binary,specs+index*12)
            md = batch.baked.native.M[method] if original else struct.unpack_from('<12I4H',metadata,header[12]+method*56)
            name = batch.baked.native.string(md[0]) if original else schema.source.string(md[0])
            if name != 'GetFormatterWithVerify' or class_inst != -1 or method_inst < 0:
                raise ValueError('Selector concrete formatter unproven')
            count, instances = struct.unpack_from('<II',binary,inst_pair)
            if method_inst >= count: raise ValueError('Selector generic instance out of range')
            instance = struct.unpack_from('<I',binary,instances+method_inst*4)[0]
            argc, argv = struct.unpack_from('<II',binary,instance)
            if argc != 1: raise ValueError('Selector generic arguments changed')
            pointer = struct.unpack_from('<I',binary,argv)[0]
            type_index, flags = struct.unpack_from('<II',binary,pointer)
            if flags >> 16 & 255 not in (17,18): raise ValueError('Selector is not a class')
            concrete = batch.baked.native.type_name(type_index) if original else schema.source.name(type_index)
            result.append({'original':original,'tag':tag,'concrete':concrete,'branch':hex(branch),'method_spec_index':index})
    old = {r['tag']:r['concrete'] for r in result if r['original']}
    new = {r['tag']:r['concrete'] for r in result if not r['original']}
    if old != new: raise ValueError('Selector original/source dispatch differs')
    return result


def integer(data, node):
    return None if node['code'] == 0xc0 else batch.baked.decode_integer(data, node)


def assemble(raw, changes):
    h, entries, overrides, data, refs, spans = batch.packed(raw)
    out, offsets = bytearray(), {}
    for offset in sorted(refs):
        identity = refs[offset]
        left, right = spans[identity]
        offsets[offset] = len(out)
        out.extend(changes.get(identity, data[left:right]))
    result = batch.baked.pack_container(h, [(k, offsets[o]) for k, o in entries],
        [(k, v, offsets[o]) for k, v, o in overrides], bytes(out))
    _, ne, no, nd, _, ns = batch.packed(result)
    if [k for k, _ in entries] != [k for k, _ in ne] or [(k, v) for k, v, _ in overrides] != [(k, v) for k, v, _ in no]:
        raise ValueError('Registry identities/order changed')
    for identity, (left, right) in spans.items():
        nl, nr = ns[identity]
        if nd[nl:nr] != changes.get(identity, data[left:right]):
            raise ValueError('Changed or unrelated root differs: ' + str(identity))
    return result


def build(output=DEFAULT_OUTPUT, account_path=DEFAULT_ACCOUNT, all_catalog=False, prop_model_aliases=None):
    output, account_path = Path(output).resolve(), Path(account_path).resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use a new candidate directory inside this workspace')
    base = BASE.read_bytes()
    if batch.baked.sha(base) != BASE_SHA:
        raise ValueError('Preserve deployed mixed-team/equipment ability resource')
    strings_raw = batch.STRINGS.read_bytes()
    if batch.baked.sha(strings_raw) != '297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1':
        raise ValueError('StringMap changed')
    strings = strings_raw.decode('utf-8').split('\x1f')
    prop_model_aliases = prop_model_aliases or {}
    alias_indices = {}
    for before_path, after_path in prop_model_aliases.items():
        if before_path not in strings or after_path.lower() not in {r['path'] for r in resources.resource_map(resources.DEFAULT19)}:
            raise ValueError('Prop alias must link an existing source string to an actual original prefab')
        if after_path not in strings: strings.append(after_path)
        alias_indices[strings.index(before_path)] = strings.index(after_path)
    source = (ROSTER / 'reference/source-ability').read_bytes()
    if batch.baked.sha(source) != batch.ability.SOURCE_SHA:
        raise ValueError('Pinned source ability changed')
    _, _, _, data, _, spans = batch.packed(base)
    _, _, _, sd, _, ss = batch.packed(source)
    roster_raw = (ROSTER / 'manifest.json').read_bytes()
    roster = json.loads(roster_raw)
    verified_raw = (ROSTER / 'verification.json').read_bytes()
    mixed_raw = (BASE.parent / 'manifest.json').read_bytes()
    mixed = json.loads(mixed_raw)
    if mixed['after_sha256'] != BASE_SHA or not mixed['original_typed_root_consumed']:
        raise ValueError('Deployed mixed-team resource receipt mismatch')
    # Reuse only roots matching previous consumer-checked hashes exactly.
    known, nested = {}, {}
    for row in roster['projection']['preserved58_records'] + roster['projection']['projected_roots']:
        identity = row['key'], row['variant']
        left, right = spans[identity]
        if batch.baked.sha(data[left:right]) == row['output_sha256']:
            known[identity] = {'sha256': row['output_sha256'], 'evidence': 'final-v2 consumer verification',
                'evidence_sha256': batch.baked.sha(verified_raw)}
            nested[identity] = [tuple(x) for x in row.get('nested_refs', [])]
    for row in mixed['projected_roots']:
        identity = tuple(row['identity']); left, right = spans[identity]
        known[identity] = {'sha256': batch.baked.sha(data[left:right]),
            'evidence': 'deployed mixed-team original-consumer check', 'evidence_sha256': batch.baked.sha(mixed_raw)}
    tables_raw = {n: (batch.TABLES / n).read_bytes() for n in
        ('weapondata', 'stigmatadata', 'equipmentsetdata', 'stagedata_main')}
    tables = {n: json.loads(raw) for n, raw in tables_raw.items()}
    weapons = {r['ID']: r for r in tables['weapondata']}
    stigmas = {r['ID']: r for r in tables['stigmatadata']}
    sets = {r['ID']: r for r in tables['equipmentsetdata']}
    inventory_raw = account_path.read_bytes()
    account = json.loads(inventory_raw)
    origins = {}
    def select(item, origin):
        if item in weapons or item in stigmas:
            origins.setdefault(item, []).append(origin)
    for kind in ('weapon_list', 'stigmata_list'):
        for item in account[kind]:
            select(item['id'], {'kind': 'owned_inventory', 'unique_id': item['unique_id']})
    for stage in tables['stagedata_main']:
        if 10101 <= stage['levelId'] <= 10110:
            for item in stage['displayDropList'] + [r['id'] for r in stage['firstDisplayDropList']]:
                select(item, {'kind': 'sourced_stage_display', 'stage_id': stage['levelId']})
    for actor in roster['roster']:
        if 'initial_weapon' in actor:
            select(actor['initial_weapon']['id'], {'kind': 'original_scope_starter_weapon', 'avatar_id': actor['avatar_id']})
    if all_catalog:
        for item in list(weapons) + list(stigmas):
            select(item, {'kind': 'full_compatibility_catalog_inventory_not_ownership'})
    queue = list(origins)
    for item in queue:
        row = weapons.get(item, stigmas.get(item))
        next_item = row.get('evoID', 0)
        if next_item:
            if next_item not in weapons and next_item not in stigmas:
                raise ValueError('Evolution target missing: ' + str(next_item))
            if next_item not in origins:
                queue.append(next_item)
            select(next_item, {'kind': 'equipment_evolution', 'from_id': item})
    equip_raw = (ROOT / '.local-baseline/server19-dev/baked-fallback/_baked/bakedequipskilldata').read_bytes()
    _, equip_entries, _, equip_data = batch.baked.unpack_container(equip_raw)
    equip_offsets = dict(equip_entries)
    weapon_base = (ROSTER / '_baked/bakedweapondata').read_bytes()
    expected_weapon = [r['output_sha256'] for r in roster['files'] if r['path'] == '_baked/bakedweapondata'][0]
    if batch.baked.sha(weapon_base) != expected_weapon:
        raise ValueError('Deployed weapon receipt mismatch')
    _, _, _, wd, _, ws = batch.packed(weapon_base)
    changes, errors, records, weapon_changes, item_matrix, set_matrix, registry = {}, {}, [], {}, [], [], {}
    prop_raw = PROP_BASE.read_bytes()
    _, _, _, prop_data, _, prop_spans = batch.packed(prop_raw)
    props, root_props, scanned_known = {}, {}, set()
    prop_changes = {}
    if batch.baked.file_sha(resources.DEFAULT19) != batch.baked.ORIGINAL19_SHA:
        raise ValueError('Original asset package identity changed')
    original_map = {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}
    proved_weapons = {r['weapon_id']: r for r in roster['weapon_roots'] if r.get('original_full_root_consumed')}

    with zipfile.ZipFile(resources.DEFAULT24) as package:
        schema = batch.BattleSchema(package, strings)
        schema.equipment_attack_pattern_proof = batch.baked.attack_pattern_union_evidence(schema.source)
        schema.equipment_attack_patterns = {r['tag']: r['concrete'] for r in schema.equipment_attack_pattern_proof if r['original']}
        schema.equipment_prop_selector_proof = prop_selector_evidence(schema)
        schema.equipment_prop_selectors = {r['tag']:r['concrete'] for r in schema.equipment_prop_selector_proof if r['original']}
        def references(reader, packed):
            found, prop_refs = [], []
            for path, leaf in reader.leaves.items():
                is_extra = '.PropAdditionalAbilities.key[' in path
                is_name = path != 'ability.AbilityName' and path.endswith('.AbilityName')
                is_prop = path.endswith('.PropObjectName')
                if not (is_extra or is_name or is_prop): continue
                q = batch.baked.MessagePackSpanReader(packed); q.pos = leaf['span'][0]
                key = integer(packed, q.node())
                if key is None: continue
                if is_prop:
                    prop_refs.append(key); continue
                variant = None
                other = reader.leaves.get(path.removesuffix('AbilityName') + 'AbilityOverride') if is_name else None
                if other:
                    q.pos = other['span'][0]; variant = integer(packed, q.node())
                    if variant is not None and strings[variant] == 'Default': variant = None
                found.append((key, variant))
            return list(dict.fromkeys(found)), list(dict.fromkeys(prop_refs))

        def prop(key):
            if key in props: return
            report = {'key': key, 'name': strings[key], 'abilities': [], 'blockers': []}
            props[key] = report
            if (key, None) not in prop_spans:
                report['blockers'].append({'reason': 'Actual Prop registry missing'}); return
            left, right = prop_spans[key, None]
            raw = prop_data[left:right]
            q = batch.baked.MessagePackSpanReader(raw); node = q.node()
            model_token = node['children'][1]; model_key = integer(raw,model_token)
            if model_key in alias_indices:
                target = alias_indices[model_key]
                replacement = b'\xcd'+struct.pack('>H',target) if target <= 65535 else b'\xce'+struct.pack('>I',target)
                changed = raw[:model_token['start']]+replacement+raw[model_token['end']:]
                report['model_alias']={'from':strings[model_key],'to':strings[target],
                    'before_sha256':batch.baked.sha(raw),'after_sha256':batch.baked.sha(changed),
                    'only_model_string_index_changed':True}
                raw=changed; prop_changes[key,None]=raw
            report['root_sha256'] = batch.baked.sha(raw)
            reader = ClosureReader(raw, strings, schema, True)
            try:
                reader.class_value('MoleMole.Config.ConfigPropObject', 'prop')
                if reader.pos != len(raw): raise ValueError('Original Prop root boundary mismatch')
                q = batch.baked.MessagePackSpanReader(raw); node = q.node()
                model_key = integer(raw, node['children'][1]); model = strings[model_key].lower()
                report['model'] = {'path': model, 'original_APK_present': model in original_map}
                if model not in original_map:
                    report['blockers'].append({'reason': 'Original Prop prefab absent', 'path': model})
                report['original_full_root_consumed'] = True
                actual = node['children'][5]
                if actual['code'] != 0xc0:
                    for entry in actual['children']:
                        if entry['kind'] != 'array' or entry['count'] != 2:
                            raise ValueError('Original Prop ability entry must have2 fields')
                        ak, av = integer(raw, entry['children'][0]), integer(raw, entry['children'][1])
                        if av is not None and strings[av] == 'Default': av = None
                        report['abilities'].append({'key': ak, 'variant': av, 'name': strings[ak]})
                        project((ak, av))
            except (ValueError, KeyError, IndexError) as error:
                report['blockers'].append({'reason': str(error), 'field': 'ConfigPropObject'})

        def project(identity):
            if identity in known:
                if identity in scanned_known: return
                scanned_known.add(identity)
                # Prior root consumer validation is reused by exact hash.
                # Traversal here inventories the newly discovered additional
                # Prop dictionary and prefab reference types, not a repeat test.
                left, right = spans[identity]
                reader = ClosureReader(data, strings, schema, True); reader.pos = left
                try:
                    reader.class_value(batch.ability.ABILITY, 'ability')
                    found, prop_refs = references(reader, data)
                    nested[identity] = list(dict.fromkeys(nested.get(identity, []) + found))
                    root_props[identity] = prop_refs
                    for child in nested[identity]: project(child)
                    for key in prop_refs: prop(key)
                except (ValueError, KeyError, IndexError) as error:
                    errors[identity] = 'New cross-reference traversal: ' + str(error)
                return
            if identity in changes or identity in errors:
                return
            if identity not in ss or identity not in spans:
                errors[identity] = 'Actual ability registry root missing'
                return
            left, right = ss[identity]; bl, br = spans[identity]
            if data[bl:br] != sd[left:right]:
                errors[identity] = 'Unproven changed preimage; do not overwrite'
                return
            reader = ClosureReader(sd, strings, schema); reader.pos = left
            before_index = len(schema.indexed_references)
            try:
                reader.class_value(batch.ability.ABILITY, 'ability')
                if reader.pos != right:
                    raise ValueError('Source root boundary mismatch')
                value = batch.apply_edits(sd, left, right, reader)
                check = ClosureReader(value, strings, schema, True)
                check.class_value(batch.ability.ABILITY, 'ability')
                retained, translated = batch.retained_terminals(reader)
                if check.pos != len(value) or set(translated) != set(check.leaves) or any(
                        r['sha256'] != check.leaves[p]['sha256'] for p, r in translated.items()):
                    raise ValueError('Original consumer/retained gameplay values mismatch')
                check.leaves = translated
                # Read retained source tokens so excluded later actions cannot
                # introduce spurious dependency references.
                reader.leaves = retained
                dependencies, prop_refs = references(reader, sd)
                root_props[identity] = prop_refs
                changes[identity], nested[identity] = value, dependencies
                records.append({'key': identity[0], 'variant': identity[1], 'name': strings[identity[0]],
                    'before_sha256': batch.baked.sha(data[bl:br]), 'source_sha256': batch.baked.sha(sd[left:right]),
                    'after_sha256': batch.baked.sha(value), 'adaptations': reader.records,
                    'retained_terminal_values_byte_identical': True, 'original_full_root_consumed': True,
                    'nested_refs': [list(r) for r in dependencies]})
                for child in dependencies:
                    project(child)
                for key in prop_refs: prop(key)
            except (ValueError, KeyError, IndexError) as error:
                errors[identity] = str(error)
                del schema.indexed_references[before_index:]

        def skill(skill_id):
            if skill_id not in registry:
                if skill_id not in equip_offsets:
                    registry[skill_id] = {'skill_id': skill_id, 'error': 'Equipment skill registry missing'}
                else:
                    q = batch.baked.MessagePackSpanReader(equip_data); q.pos = equip_offsets[skill_id]; n = q.node()
                    try:
                        if n['kind'] != 'array' or n['count'] != 18 or integer(equip_data, n['children'][0]) != skill_id:
                            raise ValueError('Original equipment skill record must have 18 fields')
                        checker = batch.BattleReader(equip_data, strings, schema, True); checker.pos = n['start']
                        checker.class_value('MoleMole.Config.ConfigEquipmentSkillEntry', 'equipment_skill')
                        if checker.pos != n['end']:
                            raise ValueError('Original skill root not fully consumed')
                        key, variant = integer(equip_data, n['children'][1]), integer(equip_data, n['children'][2])
                        if variant is not None and strings[variant] == 'Default':
                            variant = None
                        identity = key, variant
                        registry[skill_id] = {'skill_id': skill_id, 'key': key, 'variant': variant,
                            'name': strings[key], 'registry_root_sha256': batch.baked.sha(equip_data[n['start']:n['end']]),
                            'original_full_root_consumed': True}
                        project(identity)
                    except (ValueError, KeyError, IndexError) as error:
                        registry[skill_id] = {'skill_id': skill_id, 'error': str(error)}
            return copy.deepcopy(registry[skill_id])

        for item in sorted(origins):
            row = weapons.get(item, stigmas.get(item)); is_weapon = item in weapons
            report = {'item_id': item, 'kind': 'weapon' if is_weapon else 'stigmata',
                'origins': origins[item], 'evo_id': row.get('evoID', 0), 'skills': [], 'blockers': []}
            for i in (1, 2, 3):
                if row.get('prop%dID' % i, 0):
                    report['skills'].append({'slot': i, **skill(row['prop%dID' % i])})
            if is_weapon:
                model = row['bodyMod'].lower()
                report['model'] = {'path': model, 'original_APK_present': model in original_map}
                if model not in original_map:
                    report['blockers'].append({'reason': 'Actual original weapon model missing', 'path': model})
                if (item, None) not in ws:
                    report['blockers'].append({'reason': 'Weapon config missing'})
                else:
                    left, right = ws[item, None]
                    reader = batch.BattleReader(wd, strings, schema); reader.pos = left
                    try:
                        reused = proved_weapons.get(item)
                        existing_sha = batch.baked.sha(wd[left:right])
                        if reused and reused.get('output_root_sha256', reused['root_sha256']) == existing_sha:
                            # Already projected Theresa tag7 must not be fed to
                            # source dispatch, where tag7 means later Rita.
                            value = wd[left:right]
                            reader.records = reused['adaptations']
                        else:
                            reader.class_value('MoleMole.Config.ConfigWeapon', 'weapon')
                            if reader.pos != right:
                                raise ValueError('Weapon source boundary mismatch')
                            value = batch.apply_edits(wd, left, right, reader)
                            check = batch.BattleReader(value, strings, schema, True)
                            check.class_value('MoleMole.Config.ConfigWeapon', 'weapon')
                            if check.pos != len(value):
                                raise ValueError('Original weapon consumer boundary mismatch')
                        if value != wd[left:right]:
                            weapon_changes[item, None] = value
                        report['config'] = {'before_sha256': batch.baked.sha(wd[left:right]), 'after_sha256': batch.baked.sha(value),
                            'original_full_root_consumed': True, 'adaptations': reader.records,
                            'reused_exact_root_evidence': bool(reused and reused.get('output_root_sha256', reused['root_sha256']) == existing_sha)}
                        q = batch.baked.MessagePackSpanReader(wd); q.pos = left; wn = q.node()
                        # ConfigWeapon AdditionalAbilities is its actual field9.
                        if wn['count'] != 10:
                            raise ValueError('ConfigWeapon field count changed')
                        additional = wn['children'][9]
                        if additional['code'] != 0xc0:
                            refs = additional['children'] if additional['kind'] == 'array' else additional['children'][1::2]
                            report['config']['additional_abilities'] = []
                            for ref in refs:
                                key, variant = integer(wd, ref['children'][1]), integer(wd, ref['children'][2])
                                if variant is not None and strings[variant] == 'Default': variant = None
                                report['config']['additional_abilities'].append({'key': key, 'variant': variant, 'name': strings[key]})
                                project((key, variant))
                    except (ValueError, KeyError, IndexError) as error:
                        report['blockers'].append({'reason': str(error), 'field': 'ConfigWeapon'})
            else:
                report['set_id'] = row['setID']
            item_matrix.append(report)
        for set_id in sorted({r['set_id'] for r in item_matrix if r.get('set_id')}):
            row = sets.get(set_id)
            if row is None:
                set_matrix.append({'set_id': set_id, 'blockers': [{'reason': 'Equipment set metadata absent'}], 'skills': []})
                continue
            set_matrix.append({'set_id': set_id, 'skills': [{'required_pieces': row['spellEffectNum%d' % i],
                **skill(row['prop%dID' % i])} for i in (1, 2, 3) if row['prop%dID' % i]], 'blockers': []})
        # Complete all source-scope actor gate branches in the same matrix.
        for actor in roster['roster']:
            for dependency in actor['dependencies']:
                project((dependency['key'], dependency['variant']))
        schema_evidence = copy.deepcopy(list(schema.checks.values()))
        indexed = copy.deepcopy(schema.indexed_references)
        indexed_proofs = [{'type': name, 'path': row['path'], 'sha256': row['sha256'],
            'original_consumer_checked_roots': list(row['checked'].values())} for name, row in schema.batch_indexed.items()]
        pattern_proof = copy.deepcopy(schema.equipment_attack_pattern_proof)
        selector_proof = copy.deepcopy(schema.equipment_prop_selector_proof)

    def failures(identity, path=(), seen=None):
        seen = set() if seen is None else set(seen)
        if identity in seen: return []
        seen.add(identity); chain = path + (identity,)
        if identity in errors:
            return [{'chain': [{'key': k, 'variant': v, 'name': strings[k]} for k, v in chain], 'reason': errors[identity]}]
        out = [f for child in nested.get(identity, []) for f in failures(child, chain, seen)]
        for prop_key in root_props.get(identity, []):
            report = props[prop_key]
            out.extend({'chain': [{'key': k, 'variant': v, 'name': strings[k]} for k, v in chain],
                'prop_key': prop_key, 'prop_name': strings[prop_key], **blocker} for blocker in report['blockers'])
            out.extend(f for child in report['abilities'] for f in failures((child['key'], child['variant']), chain, seen))
        return out
    ready = {identity: value for identity, value in changes.items() if not failures(identity)}
    for report in item_matrix + set_matrix:
        for dependency in report['skills'] + report.get('config', {}).get('additional_abilities', []):
            if 'error' in dependency:
                report['blockers'].append({'skill_id': dependency['skill_id'], 'reason': dependency['error']})
            else:
                report['blockers'].extend({'skill_id': dependency.get('skill_id'), **f} for f in failures((dependency['key'], dependency['variant'])))
        report['status'] = 'blocked' if report['blockers'] else 'candidate_human_pending'
    actor_matrix = []
    for actor in roster['roster']:
        report = {'avatar_id': actor['avatar_id'], 'base_status': actor['base_closure_status'],
            'original_model_evidence': actor['original_resources'], 'dependencies': [], 'blockers': copy.deepcopy(actor['blockers'])}
        for dependency in actor['dependencies']:
            fs = failures((dependency['key'], dependency['variant']))
            report['dependencies'].append({**dependency, 'status': 'blocked' if fs else 'consumer_checked_candidate', 'failure_chains': fs})
        actor_matrix.append(report)
    result = assemble(base, ready)
    next_weapon = assemble(weapon_base, weapon_changes)
    output.mkdir(parents=True)
    overlay_records = []
    for identity, value in ready.items():
        left, right = spans[identity]
        if value == data[left:right]: continue
        filename = '%s-%s.bin' % (identity[0], 'default' if identity[1] is None else identity[1])
        for prefix, content in (('before-roots', data[left:right]), ('roots', value)):
            p = output / prefix / filename; p.parent.mkdir(exist_ok=True); p.write_bytes(content)
        overlay_records.append({'key': identity[0], 'variant': identity[1], 'name': strings[identity[0]],
            'before_path': 'before-roots/' + filename, 'after_path': 'roots/' + filename,
            'before_sha256': batch.baked.sha(data[left:right]), 'after_sha256': batch.baked.sha(value)})
    (output / '_baked').mkdir()
    (output / '_baked/bakedabilitydata').write_bytes(result)
    if prop_changes:
        (output / '_baked/bakedpropdata').write_bytes(assemble(prop_raw,prop_changes))
        (output / '_baked/stringmap.txt').write_bytes('\x1f'.join(strings).encode('utf8'))
    if weapon_changes: (output / '_baked/bakedweapondata').write_bytes(next_weapon)
    weapon_overlay_records = []
    for identity, value in weapon_changes.items():
        left, right = ws[identity]
        filename = '%s-default.bin' % identity[0]
        for prefix, content in (('before-weapon-roots', wd[left:right]), ('weapon-roots', value)):
            p = output / prefix / filename; p.parent.mkdir(exist_ok=True); p.write_bytes(content)
        weapon_overlay_records.append({'key': identity[0], 'variant': identity[1],
            'before_path': 'before-weapon-roots/' + filename, 'after_path': 'weapon-roots/' + filename,
            'before_sha256': batch.baked.sha(wd[left:right]), 'after_sha256': batch.baked.sha(value)})
    matrix = {'items': item_matrix, 'sets': set_matrix, 'avatars': actor_matrix, 'props': list(props.values())}
    (output / 'matrix.json').write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {'format': 'server19-equipment-battle-closure-overlay-v1', 'status': 'candidate_human_pending',
        'base_sha256': BASE_SHA, 'after_sha256': batch.baked.sha(result), 'source_sha256': batch.ability.SOURCE_SHA,
        'source_original_APK_sha256': batch.baked.ORIGINAL19_SHA, 'source_reference_APK_sha256': batch.baked.SOURCE24_SHA,
        'account_readonly_snapshot_sha256': batch.baked.sha(inventory_raw), 'inventory_selection_is_not_unlock_or_save_edit': True,
        'range': {'normal_stages': list(range(10101, 10111)), 'avatars': len(actor_matrix), 'equipment': len(item_matrix), 'sets': len(set_matrix)},
        'roots': overlay_records, 'projected_roots': records, 'known_root_receipts_reused': [
            {'key': k, 'variant': v, **r} for (k, v), r in known.items()],
        'unsupported_roots': [{'key': k, 'variant': v, 'name': strings[k], 'reason': reason} for (k, v), reason in errors.items()],
        'schema_evidence': schema_evidence, 'indexed_references': indexed, 'indexed_dependency_proofs': indexed_proofs,
        'new_reference_types': ['SpawnPropObject.PropObjectName', 'SpawnPropObject.PropAdditionalAbilities dictionary keys', 'ConfigPropObject.Abilities'],
        'prop_dependency_sha256': batch.baked.sha(prop_raw), 'attack_pattern_dispatch_proof': pattern_proof,
        'prop_selector_dispatch_proof':selector_proof,'prop_model_aliases':prop_model_aliases,
        'preservation': {'all_unselected_roots_byte_identical': True, 'registry_order_identical': True,
            'deployed_team_combination_and_set40_44_46_65_preserved': True, 'StringMap_sha256': batch.baked.sha(strings_raw)},
        'table_inputs': [{'name': n, 'sha256': batch.baked.sha(raw)} for n, raw in tables_raw.items()],
        'evidence_inputs': {'roster_manifest_sha256': batch.baked.sha(roster_raw), 'roster_verification_sha256': batch.baked.sha(verified_raw),
            'mixed_team_manifest_sha256': batch.baked.sha(mixed_raw), 'equipment_registry_sha256': batch.baked.sha(equip_raw)},
        'weapon_overlay': {'before_sha256': expected_weapon, 'after_sha256': batch.baked.sha(next_weapon),
            'changed_roots': len(weapon_changes), 'roots': weapon_overlay_records},
        'limits': ['Source2.4 compatibility data; no recovered historical1.9 economy claim',
            'No device/library/server/account/ownership/skill-unlock mutation', 'Nonempty absent gameplay effects remain blocked',
            'Static consumer checks are not human battle acceptance']}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if account_path.read_bytes() != inventory_raw: raise ValueError('Inventory changed during readonly build; rerun with stable snapshot')
    receipt = {'status': 'PASS', 'source_account_unchanged': True, 'original_consumer_new_roots_checked': len(records),
        'root_overlay_count': len(overlay_records), 'unselected_roots_byte_identical': True, 'registry_order_preserved': True,
        'candidate_after_sha256': batch.baked.sha(result), 'blocked_items': [r['item_id'] for r in item_matrix if r['blockers']],
        'blocked_sets': [r['set_id'] for r in set_matrix if r['blockers']], 'human_acceptance': 'pending'}
    (output / 'verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return {'output': str(output), 'range': manifest['range'], **receipt}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--account', type=Path, default=DEFAULT_ACCOUNT)
    parser.add_argument('--all-catalog', action='store_true', help='Audit full compatibility inventory, without granting anything')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.account, args.all_catalog), ensure_ascii=False))
