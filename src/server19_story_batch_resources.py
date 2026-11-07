"""Prepare one Act102 closure and inventory all chapter1 Normal stages.

Reads pinned packages and existing accepted candidates. Writes only a separate
candidate directory. No device, account, service, unlock or native patch work.
This is explicit later-data compatibility, not recovered historical1.9 Lua.
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

import analyze19 as native
import server19_avatar_battle_resources as batch
import server19_resources as resources
import server19_stage_monsters as monsters
import server19_stage_npc_levels as npc
import server19_stage_resources as lua
from server19_metadata_export import SourceTypedDecoder, native_json

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / '.local-baseline/server19-dev/story-chain-batch-ready'
TABLES = batch.TABLES
ABILITY_BASE = ROOT / '.local-baseline/server19-dev/mixed-team-equipment-ready/bakedabilitydata'
ABILITY_SHA = '2e9e1bdfb7653840511013a39964f414e2a656f90b3d10197de671e66c23b7c0'
MONSTER_SHA = 'f4323d0e849200b518ee88cc9bbed53c46d1f8bdf87ec8bcbbef3e929a11adc7'
STRING_SHA = '297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1'
SCOPE = (10108, 10109, 10110)


def checked(path, digest):
    raw = Path(path).read_bytes()
    if batch.baked.sha(raw) != digest:
        raise ValueError('Accepted preimage differs: ' + str(path))
    return raw


def store(output, relative, raw):
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != raw:
        raise ValueError('Candidate path contains different bytes: ' + str(target))
    target.write_bytes(raw)
    return {'path': relative, 'local_absolute_path': str(target.resolve()),
            'bytes': len(raw), 'sha256': batch.baked.sha(raw)}


def reassemble(raw, changes):
    h, entries, overrides, data, refs, spans = batch.packed(raw)
    assembled, offsets = bytearray(), {}
    for offset in sorted(refs):
        identity = refs[offset]
        left, right = spans[identity]
        offsets[offset] = len(assembled)
        assembled.extend(changes.get(identity, data[left:right]))
    result = monsters.pack_container(h, [(k, offsets[o]) for k, o in entries],
        [(k, v, offsets[o]) for k, v, o in overrides], bytes(assembled))
    nh, ne, no, nd, nr, ns = batch.packed(result)
    if h != nh or [x[0] for x in entries] != [x[0] for x in ne] or [x[:2] for x in overrides] != [x[:2] for x in no]:
        raise ValueError('Registry identity/order changed')
    for identity, (left, right) in spans.items():
        a, b = ns[identity]
        if nd[a:b] != changes.get(identity, data[left:right]):
            raise ValueError('Unselected or selected root differs: ' + str(identity))
    return result


def video_proof(package, source_map, output):
    decoder = SourceTypedDecoder(package)
    header = struct.unpack_from('<64I', decoder.metadata)
    methods = [struct.unpack_from('<12I4H', decoder.metadata, header[12] + i)
               for i in range(0, header[13], 56)]
    names = {i: decoder.name(m[1]) + '::' + decoder.string(m[0]) for i, m in enumerate(methods)}
    pointers = {i: struct.unpack_from('<I', decoder.binary, 0x418f6e0 + m[6] * 4)[0]
                for i, m in enumerate(methods) if m[6] != 0xffffffff}
    lookup = {p: names[i] for i, p in pointers.items()}
    starts = sorted(lookup)
    selected = [80000, 99048, 94440, 94445, 94446, 94447] + [i for i, n in names.items()
        if n == 'MoleMole.InLevelMainPageContext::OnSkillTutorilaBtnCallBack']
    proofs = []
    for mid in selected:
        start = pointers[mid]
        end = starts[bisect.bisect_right(starts, start)]
        asm, calls = [], []
        for ins in native.MD.disasm(decoder.binary[start:end], start):
            name = lookup.get(int(ins.op_str, 16), '') if ins.mnemonic == 'call' and ins.op_str.startswith('0x') else ''
            asm.append(f'{ins.address:08x} {ins.mnemonic} {ins.op_str} {name}')
            if name:
                calls.append(name)
        filename = f'evidence/source-method-{mid}.asm'
        store(output, filename, ('\n'.join(asm) + '\n').encode())
        proofs.append({'method_id': mid, 'name': names[mid], 'rva': hex(start), 'end_rva': hex(end),
            'sha256': batch.baked.sha(decoder.binary[start:end]), 'calls': calls, 'asm_path': filename})
    _, raw = resources.object_bytes(package, source_map['data/_exceloutput/skilltutorialstep'])
    _, tsv = resources.text_asset(raw)
    rows = list(csv.DictReader(io.StringIO(tsv.decode()), delimiter='\t'))
    if len(rows) != 6 or any(row['GameVersionBegin'] != '2.0' for row in rows):
        raise ValueError('Later skill tutorial scope/version changed')
    original_names = {native.type_name(i) for i in range(len(native.T))}
    absent = ('MoleMole.SkillTutorialStepData', 'MoleMole.SkillTutorialLevelShowInfo',
              'MoleMole.InLevelVideoTutorialDialogContext', 'MoleMole.TutorialVideoMetaData')
    if any(name in original_names for name in absent) or any(name.endswith('::ShowSkillTutorial') for name in native.N.values()):
        raise ValueError('Do not exclude an original skill tutorial mechanism')
    if not any('0x1ca' in line for line in (output / proofs[0]['asm_path']).read_text().splitlines()):
        raise ValueError('Source ShowSkillTutorial notification changed')
    _, video_raw = resources.object_bytes(package, source_map['data/_exceloutput/tutorialvideo'])
    _, video_tsv = resources.text_asset(video_raw)
    video_rows = list(csv.DictReader(io.StringIO(video_tsv.decode()), delimiter='\t'))
    actual_video_groups = [r for r in video_rows if r['GroupId'] in ('1', '3')]
    if not actual_video_groups or any(r['GameVersionBegin'] != '2.0' for r in actual_video_groups):
        raise ValueError('Actual video groups1/3 are not the evidenced post1.9 additions')
    if not any('MoleMole.InLevelVideoTutorialDialogContext::.ctor' in r['calls'] for r in proofs):
        raise ValueError('Actual skill-video dialog consumption changed')
    if any('SetPlayerBehaviourDone' in name or 'RegisterLevelTeaching' in name for r in proofs for name in r['calls']):
        raise ValueError('Do not exclude a video callback that advances teaching completion')
    return {'source_methods': proofs, 'source_TSV_sha256': batch.baked.sha(tsv), 'source_rows': rows,
        'source_video_TSV_sha256': batch.baked.sha(video_tsv), 'actual_video_groups1_3': actual_video_groups,
        'original_types_absent': list(absent), 'original_ShowSkillTutorial_absent': True,
        'original_DoTutorialStep': {'method_id': 65650, 'name': native.N[65650], 'rva': hex(native.pointer(native.M[65650]))},
        'policy': 'Exclude only evidenced2.0+ extra video-tutorial overlay; retain native1.9 picture guides, teaching registration and completion branches',
        'historical19_Lua_equivalence': False}


def project_abilities(package, strings, identities, output):
    previous = checked(ABILITY_BASE, ABILITY_SHA)
    source = checked(ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/reference/source-ability', batch.ability.SOURCE_SHA)
    _, _, _, old_data, _, old_spans = batch.packed(previous)
    _, _, _, source_data, _, source_spans = batch.packed(source)
    schema = batch.BattleSchema(package, strings)
    changes, records, failures, seen = {}, [], {}, set()
    pending = list(sorted(identities, key=lambda x: (x[0], -1 if x[1] is None else x[1])))
    while pending:
        identity = pending.pop(0)
        if identity in seen:
            continue
        seen.add(identity)
        if identity not in old_spans or identity not in source_spans:
            failures[identity] = 'Ability registry identity absent'
            continue
        left, right = old_spans[identity]
        old_value = old_data[left:right]
        source_left, source_right = source_spans[identity]
        source_value = source_data[source_left:source_right]
        try:
            # Existing accepted roots are reused, never regenerated from source.
            check = batch.BattleReader(old_value, strings, schema, True)
            check.class_value(batch.ability.ABILITY, 'ability')
            if check.pos != len(old_value):
                raise ValueError('Existing root boundary differs')
            value, operation, reader = old_value, 'retain_existing_original_consumer_valid_root', check
        except (ValueError, KeyError):
            if old_value != source_value:
                failures[identity] = 'Existing changed root did not validate; refuse overwrite'
                continue
            try:
                reader = batch.BattleReader(source_data, strings, schema)
                reader.pos = source_left
                reader.class_value(batch.ability.ABILITY, 'ability')
                if reader.pos != source_right:
                    raise ValueError('Source root boundary differs')
                value = batch.apply_edits(source_data, source_left, source_right, reader)
                check = batch.BattleReader(value, strings, schema, True)
                check.class_value(batch.ability.ABILITY, 'ability')
                _, translated = batch.retained_terminals(reader)
                if check.pos != len(value) or set(translated) != set(check.leaves) or any(leaf['sha256'] != check.leaves[path]['sha256'] for path, leaf in translated.items()):
                    raise ValueError('Original consumer or retained terminals differ')
                operation = 'project_exact_source_root'
                changes[identity] = value
            except (ValueError, KeyError) as exc:
                failures[identity] = str(exc)
                continue
        leaves = check.leaves
        dependencies = []
        for path, leaf in leaves.items():
            if path == 'ability.AbilityName' or not path.endswith('.AbilityName'):
                continue
            q = batch.baked.MessagePackSpanReader(value)
            q.pos = leaf['span'][0]
            node = q.node()
            if node['code'] == 0xc0:
                continue
            key = monsters.decode_integer(value, node)
            override = leaves.get(path.removesuffix('AbilityName') + 'AbilityOverride')
            variant = None
            if override:
                q.pos = override['span'][0]; n = q.node()
                if n['code'] != 0xc0:
                    variant = monsters.decode_integer(value, n)
                    if strings[variant] == 'Default':
                        variant = None
            dependency = (key, variant)
            dependencies.append({'identity': dependency, 'name': strings[key], 'reference_field': path})
            pending.append(dependency)
        record = {'identity': identity, 'key': identity[0], 'variant': identity[1], 'name': strings[identity[0]],
            'before_sha256': batch.baked.sha(old_value), 'source_sha256': batch.baked.sha(source_value),
            'after_sha256': batch.baked.sha(value), 'operation': operation, 'nested_dependencies': dependencies,
            'original_consumer_valid': True, 'retained_terminals_equal': True}
        if identity in changes:
            record['overlay'] = store(output, f'overlays/ability/{identity[0]}-{identity[1] if identity[1] is not None else "default"}.bin', value)
            record['adaptations'] = reader.records
        records.append(record)
    result = reassemble(previous, changes)
    return result, records, [{'identity': key, 'reason': value} for key, value in failures.items()]


def build(output=OUTPUT):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError('Candidate output must be a child of the workspace')
    output.mkdir(parents=True, exist_ok=True)
    apk19, apk24 = resources.DEFAULT19, resources.DEFAULT24
    if lua.file_sha(apk19) != lua.ORIGINAL19_SHA or lua.file_sha(apk24) != monsters.SOURCE24_SHA:
        raise ValueError('Pinned source package changed')
    strings = checked(batch.STRINGS, STRING_SHA).decode().split('\x1f')
    old_map = {r['path']: r for r in resources.resource_map(apk19)}
    source_map = {r['path']: r for r in resources.resource_map(apk24)}
    tables = {n: json.loads((TABLES / n).read_bytes()) for n in ('stagedata_main', 'monsterconfigdata', 'tutorialstepdata', 'plotdata', 'dialogdata')}
    stages = [r for r in tables['stagedata_main'] if r['chapterId'] == 1 and r['difficulty'] == 1]
    if len(stages) != 36 or [r['levelId'] for r in stages] != list(range(10101, 10137)):
        raise ValueError('Expected actual36 Normal chapter1 rows')
    names = {row['monsterName'] for row in tables['monsterconfigdata']}
    signatures = lua.method_signatures()
    shared_manifest = json.loads((lua.DEFAULT_OUTPUT / 'manifest.json').read_bytes())
    required_shared = []
    for record in shared_manifest['files']:
        raw = checked(lua.DEFAULT_OUTPUT / record['path'], record['output_sha256'])
        required_shared.append({'path': record['path'], 'required_existing_sha256': batch.baked.sha(raw),
            'operation': 'retain_existing_shared_Lua_closure'})
    matrices, files, ability_ids, original_proofs = [], [], set(), {}
    with zipfile.ZipFile(apk19) as original, zipfile.ZipFile(apk24) as source:
        later_video = video_proof(source, source_map, output)
        for stage in stages:
            path = stage['luaFile'].lower()
            package, mapping, version = (original, old_map, '1.9') if path in old_map else (source, source_map, '2.4')
            if path not in mapping:
                matrices.append({'stage_id': stage['levelId'], 'lua': path, 'blockers': ['Source Lua missing'], 'checked_scope': 'inventory_only'})
                continue
            raw, provenance = lua.text_record(package, mapping[path], version)
            text = raw.decode('utf-8-sig')
            tokens = lua.lua_tokens(text)
            literals = [t[0][1:-1] for t in tokens if t[3] == 'string' and t[0][0] in ('"', "'")]
            calls = lua.calls(text)
            missing = [r for r in calls if r['static_argument_count'] is None or not any(o['minimum_args'] <= r['static_argument_count'] <= o['maximum_args'] for o in signatures.get(r['method'], []))]
            waves = lua.normal_monster_waves(text, names)
            requires = lua.requires(text)
            matrix = {'stage_id': stage['levelId'], 'act_id': stage['actId'], 'lua': path, 'source': provenance,
                'original19_script_present': path in old_map, 'historical19_equivalence': False,
                'hard_level': stage['hardLevel'], 'pre_level_ids': stage['preLevelID'],
                'max_num_list': stage['maxNumList'], 'restrict_list': stage['restrictList'],
                'native_calls': calls, 'native_calls_missing': missing, 'requires': requires,
                'normal_monster_waves': waves, 'script_trial_or_fixed_tokens': [x for x in literals if any(w in x.lower() for w in ('trial', 'avatar', 'fixed'))],
                'script_actor_control_calls': [r for r in calls if any(w in r['method'].lower() for w in ('trial', 'fixed', 'changeavatar', 'setavatar', 'switchavatar'))],
                'metadata_fixed_avatar': stage['restrictList'] != [0],
                'drop_source': 'Existing explicit2.4 firstDisplayDropList; user-authored repeat policy required, original random DropSeq unavailable',
                'checked_scope': 'full_static_candidate' if stage['levelId'] in SCOPE else 'inventory_only', 'blockers': []}
            matrices.append(matrix)
            if stage['levelId'] not in SCOPE:
                continue
            adaptations = []
            if stage['levelId'] in (10108, 10109):
                before = f'LevelDesign:ShowSkillTutorial("Tutorial_Academy_Hint_Title",{1 if stage["levelId"] == 10108 else 3})'.encode()
                if raw.count(before) != 1 or [c['method'] for c in missing] != ['ShowSkillTutorial']:
                    raise ValueError('Exact later overlay call scope changed')
                start = raw.index(before)
                # Statement return is unused. Only this call is replaced by a comment.
                # All source waits, picture tutorials and teaching completion remain.
                after = b'-- Later2.0 skill-tutorial overlay absent from original1.9'
                projected = raw[:start] + after + raw[start + len(before):]
                adaptations.append({'kind': 'exclude_proven_post19_overlay', 'source_byte_span': [start, start + len(before)],
                    'source_sha256': batch.baked.sha(before), 'before': before.decode(), 'after': after.decode(),
                    'call_result_unused': True, 'completion_condition_unchanged': True, 'evidence': later_video})
            else:
                projected = raw
            projected_calls = lua.calls(projected.decode('utf-8-sig'))
            if any(c['static_argument_count'] is None or not any(o['minimum_args'] <= c['static_argument_count'] <= o['maximum_args'] for o in signatures.get(c['method'], [])) for c in projected_calls):
                matrix['blockers'].append('Unresolved original Lua API')
            if [r['path'] for r in requires] != ['lua/base/leveldesignnormal.lua']:
                matrix['blockers'].append('Unexpected new Lua require closure')
            files.append({**store(output, path, projected), 'operation': 'add', 'required_existing_sha256': None,
                          'source_bytes_unchanged': not adaptations, 'adaptations': adaptations})
            store(output, 'reference/' + path, raw)
            for c in calls:
                if c['method'] == 'AddNewAbilityToAvatar':
                    name = c['arguments'][1].strip('"\'')
                    ability_ids.add((strings.index(name), None))
            if stage['levelId'] == 10109:
                ability_ids.add((strings.index('NewbieTutorial_MonsterMoveSpeedDown'), None))
            tutorial_ids = sorted({int(re.match(r'\d+', text[tokens[i + 2][1]:])[0]) for i in range(len(tokens) - 2)
                if tokens[i][3] == 'string' and tokens[i][0][1:-1] == 'tutorial' and tokens[i + 1][0] == ',' and tokens[i + 2][0].isdigit()})
            tutorial_rows = [row for row in tables['tutorialstepdata'] if row['id'] in tutorial_ids]
            if len(tutorial_rows) != len(tutorial_ids):
                matrix['blockers'].append('Referenced tutorial row missing')
            matrix['tutorial_rows'] = tutorial_rows
            for row in tutorial_rows:
                if row['targetUIPath'].startswith('SpriteOutput/'):
                    asset_path = row['targetUIPath'].lower()
                    if asset_path not in old_map:
                        matrix['blockers'].append('Original tutorial image missing: ' + asset_path)
                    else:
                        original_proofs[asset_path] = old_map[asset_path]
            # Plot20006 is genuinely called in Normal1-10 (comments do not count).
            plots = []
            for i, token in enumerate(tokens[:-2]):
                if token[3] == 'string' and token[0][1:-1] == 'StoryMode' and tokens[i + 1][0] == ',':
                    plot_id = int(re.match(r'\d+', text[tokens[i + 2][1]:])[0]); rows = [r for r in tables['plotdata'] if r['plotID'] == plot_id]
                    if len(rows) != 1:
                        matrix['blockers'].append('Plot row absent')
                        continue
                    plot = rows[0]; dialog_rows = [r for r in tables['dialogdata'] if plot['startDialogID'] <= r['dialogID'] <= plot['endDialogID']]
                    plots.append({'plot': plot, 'dialog_rows': dialog_rows, 'human_plot_play_pending': True})
            matrix['plots'] = plots
            for p in ('stage/data/stage_st_freyja', 'stage/stage_st_freyja/env/env_s02_11',
                'stage/stage_st_freyja/perpstage_s02_01', 'weather/stagerenderingdata/style_01/style01_day',
                'weather/stagerenderingdata/style_01/style01_nightly', 'ui/menus/dialog/newbie/newbiedialog'):
                if p in old_map:
                    original_proofs[p] = old_map[p]
                else:
                    matrix['blockers'].append('Original resource absent: ' + p)
        # Extend exact monster base by only the newly consumed UL030 primary root.
        monster_before = checked(monsters.STAGE2_OUTPUT / monsters.PATH, MONSTER_SHA)
        _, _, _, packed, _, spans = batch.packed(monster_before)
        monster_id = (strings.index('UL_030_Config'), None)
        left, right = spans[monster_id]
        monster_value, monster_record = monsters.project_root(packed, left, right, strings, True)
        q = monsters.MonsterReader(packed); q.pos = left; root = q.root(strings, 20)
        ability_map = root['children'][6]
        monster_abilities = []
        for name, val in zip(ability_map['children'][::2], ability_map['children'][1::2]):
            if val['kind'] != 'array' or val['count'] != 2:
                raise ValueError('Monster ability reference shape differs')
            key = monsters.decode_integer(packed, val['children'][0])
            variant = None if val['children'][1]['code'] == 0xc0 else monsters.decode_integer(packed, val['children'][1])
            identity = key, variant
            ability_ids.add(identity)
            monster_abilities.append({'identity': identity, 'name': strings[key]})
        ability_ids.add((strings.index('Elite_EliteShield'), strings.index('UlyssesRider')))
        monster_after = reassemble(monster_before, {monster_id: monster_value})
        files.append({**store(output, monsters.PATH, monster_after), 'operation': 'replace', 'required_existing_sha256': MONSTER_SHA})
        monster_record.update(identity=monster_id, before_sha256=batch.baked.sha(packed[left:right]),
            overlay=store(output, 'overlays/monster/20973-default.bin', monster_value), abilities=monster_abilities,
            other_roots_byte_identical=True)
        for p in old_map:
            if ('ul_030' in p or 'ulyssesrider' in p) and p.startswith(('ai/', 'auxobject/', 'effect/data/', 'entities/')):
                original_proofs[p] = old_map[p]
        ability_after, ability_records, ability_failures = project_abilities(source, strings, ability_ids, output)
        files.append({**store(output, batch.ability.PATH, ability_after), 'operation': 'replace', 'required_existing_sha256': ABILITY_SHA,
            'note': 'Root-overlay merge required if another batch also extends this exact preimage'})
        # Preserve actual hard-level1..3 rows and append source hard-level4.
        previous_npc = (npc.ACT101_OUTPUT / npc.PATH).read_bytes()
        if batch.baked.sha(previous_npc) != 'feaa7d9a17b6cab682df194beaccfd237eedabe62b7e9038474fe8bb8b41c3cd':
            raise ValueError('Accepted NPC1..3 preimage changed')
        _, raw = resources.object_bytes(source, source_map[npc.PATH])
        typed = SourceTypedDecoder(source).rows(raw, 'MoleMole.NPCLevelMetaData')
        _, text_raw = resources.object_bytes(source, source_map[npc.TEXT_PATH]); _, tsv = resources.text_asset(text_raw)
        source_rows = list(csv.DictReader(io.StringIO(tsv.decode()), delimiter='\t'))
        selected = [r for r in source_rows if r['HardLevel'] == '4']; selected_typed = [r for r in typed if r['HardLevel'] == 4]
        if len(selected) != 1 or len(selected_typed) != 1 or selected[0]['GameVersionBegin'] != '2.3':
            raise ValueError('Required exact source NPC4 row missing')
        row = {f: int(selected[0][f]) if f == 'HardLevel' else float(selected[0][f]) for f in npc.FIELDS}
        if any(struct.pack('<f', row[f]) != struct.pack('<f', selected_typed[0][f]) for f in npc.FIELDS[1:]):
            raise ValueError('NPC4 source TSV and typed float32 differ')
        combined_npc = json.loads(previous_npc) + [row]
        next_npc = (native_json(combined_npc)[0] + '\n').encode()
        if json.loads(next_npc)[:3] != json.loads(previous_npc):
            raise ValueError('Existing NPC rows changed')
        files.append({**store(output, npc.PATH, next_npc), 'operation': 'replace', 'required_existing_sha256': batch.baked.sha(previous_npc)})
        original_assets = []
        for path, record in sorted(original_proofs.items()):
            obj, raw = resources.object_bytes(original, record)
            original_assets.append({'path': path, 'class': obj['class'], 'object_sha256': batch.baked.sha(raw), 'object_bytes': len(raw), 'operation': 'retain_original_APK'})
        scene_path = 'stage/stage_st_freyja/env/env_s02_11'
        scene_file = original.read('assets/bin/Data/' + old_map[scene_path]['file'])
        parsed = resources.serialized(scene_file)
        gameobjects = []
        for obj in parsed['objects'].values():
            if obj['class'] != 1:
                continue
            q = resources.Reader(scene_file, obj['offset'])
            for _ in range(q.read('i')):
                q.read('iiq')
            q.read('I'); gameobjects.append(q.string())
        points = {
            10108: 'Exit3 Wall02 Wall01 Wall04 InnerWall02 Spawn64 Field04 Arrow02 InnerWall01 Center Spawn02 Spawn10 Spawn22 Spawn27'.split(),
            10109: 'Center InnerWall01 InnerWall02'.split(),
            10110: 'Spawn13 InnerWall01 Spawn61 Spawn32 Wall06 InnerWall02 Spawn11 Spawn07 Spawn21'.split()}
        for matrix in matrices:
            if matrix['stage_id'] not in SCOPE:
                continue
            required = points[matrix['stage_id']]
            if any(point not in gameobjects for point in required):
                matrix['blockers'].append('Original environment named waypoint missing')
            matrix['original_named_waypoints'] = {'serialized_file_sha256': batch.baked.sha(scene_file),
                'original_resource_path': scene_path, 'required_names': required, 'all_present': all(p in gameobjects for p in required)}
    for matrix in matrices:
        if matrix['stage_id'] in SCOPE:
            matrix['ability_failures'] = ability_failures
            if ability_failures:
                matrix['blockers'].append('Ability dependency closure contains unsupported roots')
            matrix['candidate_status'] = 'static_ready_human_pending' if not matrix['blockers'] else 'blocked'
    ready = [r['stage_id'] for r in matrices if r['stage_id'] in SCOPE and not r['blockers']]
    manifest = {'format': 'server19-story-chain-batch-resources-v1', 'scope_stage_ids': list(SCOPE),
        'ready_stage_ids': ready, 'blocked_stage_ids': [i for i in SCOPE if i not in ready],
        'chapter1_normal_inventory': matrices, 'chapter1_actual_normal_count': 36,
        'files': files, 'deployment_files': [r['path'] for r in files], 'ability_root_overlay': ability_records,
        'required_existing_shared_Lua_files': required_shared,
        'ability_failures': ability_failures, 'monster_projection': monster_record,
        'npc_increment': {'source_row': selected[0], 'source_typed_row': selected_typed[0], 'output_row': row,
            'source_float32_hex': {f: struct.pack('<f', row[f]).hex() for f in npc.FIELDS[1:]}, 'previous1_2_3_rows_preserved': True},
        'original_resources_retained': original_assets, 'later_video_overlay_evidence': later_video,
        'accepted_preimages': {'ability': ABILITY_SHA, 'monster': MONSTER_SHA, 'stringmap': STRING_SHA},
        'source19_sha256': lua.ORIGINAL19_SHA, 'source24_sha256': monsters.SOURCE24_SHA,
        'limits': ['No device/service/save/library changes or gameplay acceptance',
            'Actual2.4 compatibility inputs; historical1.9 scripts and original random drop sequence unavailable',
            'Inventory-only stages10111..10136 are not marked ready or opened',
            'Extra2.0 video-tutorial overlay excluded; original picture/teaching/wait/completion branches remain',
            'Original scene/GameObject behavior, plot presentation and human tutorials remain human acceptance pending']}
    store(output, 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=OUTPUT)
    args = p.parse_args()
    manifest = build(args.output)
    print(json.dumps({'output': str(args.output.resolve()), 'ready_stage_ids': manifest['ready_stage_ids'],
        'blocked_stage_ids': manifest['blocked_stage_ids'], 'ability_roots': len(manifest['ability_root_overlay']),
        'ability_failures': manifest['ability_failures'], 'files': [{k: r[k] for k in ('path', 'bytes', 'sha256')} for r in manifest['files']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
