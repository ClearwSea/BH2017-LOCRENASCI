"""Prepare first-cycle monster/ability dependencies over the accepted extra.3 data."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
from pathlib import Path
import re
import zipfile

import server19_resources as resources
import server19_avatar_battle_resources as batch
import server19_stage_resources as lua
import server19_chapter1_resources as chapter
from server19_story_movement_bridge import MovementClosure
from server19_story_wave_abilities import references
from server19_story_batch_resources import reassemble, store
from server19_sakura_prepare import ROOT, OUT, TABLES
from server19_sakura_equipment import prepare as prepare_equipment
from server19_equipment_battle_closure import integer


def prepare(base=None, output=None, story_ids=None, trial_ids=None, script_paths=None,
            extra_abilities=(), extra_unique_ids=(), extra_props=(), camera_union=False,
            monster_tables=None, ui_custom_buff_ids=()):
    base = Path(base) if base is not None else ROOT / 'server19-run/kallen-20261025/candidate-v4'
    output = Path(output) if output is not None else OUT / 'candidate-v1'
    story_ids = list(story_ids or range(101, 112))
    trial_ids = list(range(39, 43) if trial_ids is None else trial_ids)
    approved_items = prepare_equipment() if trial_ids else []
    strings = (base / '_baked/stringmap.txt').read_text(encoding='utf-8').split('\x1f')
    original = {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}
    monster_tables = Path(monster_tables) if monster_tables else TABLES
    meta = json.loads((monster_tables / 'monsterconfigdata').read_bytes())
    unique = {r['uniqueID']: r for r in json.loads((monster_tables / 'uniquemonsterdata').read_bytes())}
    declaration = json.loads((output / 'lua-declarations.json').read_bytes())
    selected_paths = script_paths if script_paths is not None else [f'lua/levels/owmission/{i}.lua' for i in story_ids]
    texts = [(output / path).read_text(encoding='utf-8-sig') for path in selected_paths]
    identities = set()
    pairs = {tuple(p) for p in declaration['area_monsters']}
    unique_ids = set(extra_unique_ids)
    seeds = {(strings.index(name), None) for name in extra_abilities}
    blockers = []
    files = []
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        closure = MovementClosure(source, strings, original, output)
        closure.schema.ui_custom_buff_ids = tuple(ui_custom_buff_ids)
        closure.before = (base / '_baked/bakedabilitydata').read_bytes()
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        closure.prop_raw = (base / '_baked/bakedpropdata').read_bytes()
        closure.prop_data, closure.prop_spans = batch.packed(closure.prop_raw)[3::2]
        closure.resolve_original_prop_basename = True
        if camera_union:
            from server19_story_poly_dispatch import evidence
            camera_type = 'MoleMole.Config.ConfigAvatarCameraAction'
            proof = evidence(closure.schema, camera_type, 58759)
            closure.schema.story_small_poly = {camera_type: {
                r['tag']: r['concrete'] for r in proof if r['original']}}
            (output / 'camera-union-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
        for text in texts:
            for wave in lua.normal_monster_waves(text, {r['monsterName'] for r in meta}):
                line = text.splitlines()[wave['line'] - 1]
                selected = re.search(r'\buniqueID\s*=\s*(\d+)', line)
                if selected:
                    row = unique[int(selected[1])]
                    pairs.add((row['monsterName'], row['typeName']))
                else:
                    pairs.add((wave['monster'], wave['configType']))
            unique_ids.update(map(int, re.findall(r'\buniqueID\s*=\s*(\d+)', text)))
            for ref in references(text, unresolved=[]):
                seeds.add((strings.index(ref['ability']), None))
        # Retain the first-cycle root's actual level buff; servant branches are
        # locked behind story405 and are not silently enabled in this candidate.
        for name in ('Level_OpenworldSakuraBuff', 'Level_OpenworldSakuraMeiAllAtkUp'):
            seeds.add((strings.index(name), None))
        unique_ids.discard(0)  # Ordinary monster declarations use zero for no unique override.
        for uid in sorted(unique_ids):
            row = unique[uid]
            pairs.add((row['monsterName'], row['typeName']))
            for ability in json.loads(row['abilities'] or '[]'):
                seeds.add((strings.index(ability['Name']), None))
        for name, variant in sorted(pairs):
            row = next(r for r in meta if (r['monsterName'], r['typeName']) == (name, variant))
            model = f"entities/monster/{row['categoryName']}/{row['subTypeName']}/{row['subTypeName']}".lower()
            if model not in original:
                blockers.append({'missing_original_model': model})
            variants = {row['configType']}
            for uid in unique_ids:
                u = unique[uid]
                if (u['monsterName'], u['typeName']) == (name, variant) and u['configType']:
                    variants.add(u['configType'])
            for value in variants:
                identities.add((strings.index(row['configFile']), None if value == 'Default' else strings.index(value)))
        # Source preload for the final boss must be audited separately from its
        # unique spawn override, as both paths are consumed by the native client.
        boss = next(r for r in meta if (r['monsterName'], r['typeName']) == ('DASakura', 'YS_Default'))
        identities.add((strings.index(boss['configFile']), None if boss['configType'] == 'Default' else strings.index(boss['configType'])))
        roster = json.loads((ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/manifest.json').read_bytes())['roster']
        matrix = json.loads((ROOT / '.local-baseline/server19-dev/cultivation-full-equipment-ready/matrix.json').read_bytes())
        equipment = list(matrix['items'])
        equip_raw = (ROOT / '.local-baseline/server19-dev/baked-fallback/_baked/bakedequipskilldata').read_bytes()
        _, entries, _, equip_data = batch.baked.unpack_container(equip_raw)
        offsets = dict(entries)
        for item in approved_items:
            skills = []
            for slot in (1, 2, 3):
                sid = item.get('prop%dID' % slot, 0)
                if not sid:
                    continue
                parser = batch.baked.MessagePackSpanReader(equip_data)
                parser.pos = offsets[sid]
                node = parser.node()
                assert node['kind'] == 'array' and node['count'] == 18
                assert integer(equip_data, node['children'][0]) == sid
                checker = batch.BattleReader(equip_data, strings, closure.schema, True)
                checker.pos = node['start']
                checker.class_value('MoleMole.Config.ConfigEquipmentSkillEntry', 'equipment_skill')
                assert checker.pos == node['end']
                key, variant = [integer(equip_data, node['children'][i]) for i in (1, 2)]
                if variant is not None and strings[variant] == 'Default':
                    variant = None
                skills.append(dict(skill_id=sid, key=key, variant=variant,
                                   original_full_root_consumed=True))
            equipment.append(dict(item_id=item['ID'], skills=skills, blockers=[], set_id=item['setID']))
        trials = [r for r in json.loads((TABLES / 'avatartrialdata').read_bytes()) if r['ID'] in trial_ids]
        assert len(trials) == len(trial_ids)
        for trial in trials:
            actor = next(r for r in roster if r['avatar_id'] == trial['avatarID'])
            bought = {r['skillID'] for r in trial['avatarSubSkills'] if r['skillLV'] > 0}
            seeds.update((r['key'], r['variant']) for r in actor['dependencies']
                         if r['scope'] in ('base', 'default_skill') or r.get('evidence', {}).get('sub_skill_id') in bought)
            for eid in (trial['weaponID'], trial['stigmataID1'], trial['stigmataID2'], trial['stigmataID3']):
                gear = next((r for r in equipment if r['item_id'] == eid), None)
                if gear is None:
                    blockers.append({'trial_equipment_missing': eid,
                                     'reason': 'Required trial equipment not resolved'})
                    continue
                if gear['blockers']:
                    blockers.append({'trial_equipment': eid, 'details': gear['blockers']})
                seeds.update((r['key'], r['variant']) for r in gear['skills'])
            counts = {}
            for eid in (trial['stigmataID1'], trial['stigmataID2'], trial['stigmataID3']):
                gear = next(r for r in equipment if r['item_id'] == eid)
                counts[gear['set_id']] = counts.get(gear['set_id'], 0) + 1
            for row in matrix['sets']:
                if row['set_id'] in counts:
                    assert not row['blockers']
                    seeds.update((r['key'], r['variant']) for r in row['skills']
                                 if r['required_pieces'] <= counts[row['set_id']])
        for name in ('NPC_Kallen', 'NPC_Kallen_Daodi', 'NPC_Sakura', 'NPC_Quest_Start', 'NPC_Quest_None', 'NPC_Quest_End', *extra_props):
            closure.prop(strings.index(name))
        before = (base / '_baked/bakedmonsterdata').read_bytes()
        for _ in range(12):
            after, monster_records, errors = chapter.project_monsters(before, identities, strings, output)
            blockers.extend({'monster': str(key), 'reason': value} for key, value in errors.items())
            for row in monster_records:
                seeds.update(tuple(r) for r in row['dependencies'])
            for identity in sorted(seeds, key=lambda value: (value[0], -1 if value[1] is None else value[1])):
                closure.project(closure.resolve(identity))
            additional = closure.monster_refs - identities
            if not additional:
                break
            identities.update(additional)
        else:
            raise ValueError('Summoned-monster closure did not converge')
        blockers.extend(closure.failure_chain(list(seeds)))
        blockers.extend(row for row in closure.props.values() if 'blocker' in row)
        if not blockers:
            for path, raw in (
                ('_baked/bakedmonsterdata', after),
                ('_baked/bakedabilitydata', reassemble(closure.before, closure.changes)),
                ('_baked/bakedpropdata', reassemble(closure.prop_raw, closure.prop_changes)),
                ('_baked/stringmap.txt', '\x1f'.join(strings).encode()),
            ):
                files.append(store(output, path, raw))
        report = dict(status='BLOCKED' if blockers else 'PASS_scoped_resources', blockers=blockers,
                      trials=trials, unique_ids=sorted(unique_ids), monster_pairs=sorted(pairs),
                      monsters=monster_records, abilities=list(closure.records.values()),
                      props=list(closure.props.values()), files=files,
                      gameplay_verified=False, deployed=False)
        (output / 'resource-closure.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(report['status'], len(monster_records), 'monsters', len(closure.records), 'abilities', len(blockers), 'blockers')
        return report


if __name__ == '__main__':
    prepare()
