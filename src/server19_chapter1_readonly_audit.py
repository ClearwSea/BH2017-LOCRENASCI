"""Independent source-only chapter audit. No device, server or save writes."""

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
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

import analyze19 as native
import server19_resources as resources
import server19_stage_resources as lua

ROOT = Path(__file__).resolve().parent
TABLES = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normal_point_literals(text):
    """Exclude barrier identifiers and explicitly Hell-only medic points."""
    tokens = lua.lua_tokens(text)
    excluded = set()
    expanded = []
    for i, token in enumerate(tokens):
        if token[0] == 'medic_box_point_for_hell' and tokens[i+1][0] == '=':
            depth = 0
            for j in range(i+2, len(tokens)):
                excluded.add(j)
                if tokens[j][0] == '{': depth += 1
                elif tokens[j][0] == '}':
                    depth -= 1
                    if depth == 0: break
        if token[3] != 'string': continue
        # A wave command head is executable syntax, not a scene waypoint.
        if i and tokens[i-1][0] == '{' and i+1 < len(tokens) and tokens[i+1][0] in (',','}'):
            if token[0][1:-1] in ('SpawnTreasure','SpawnBomb','SpawnDeadArcher','SpawnDeadCat','SpawnDeadWalker'):
                excluded.add(i)
        if i >= 3 and tokens[i-3][0] == '{' and tokens[i-2][0].strip(chr(34)+chr(39)) == 'Func' and tokens[i-1][0] == ',':
            if re.search(r'level\.'+re.escape(token[0][1:-1])+r'\s*=\s*function',text):excluded.add(i)
        if i >= 2 and tokens[i-1][0] == '=' and tokens[i-2][0] in ('name','target','target_monster','enterType'):
            excluded.add(i)
        # Exact bounded source loop: do not mistake the literal prefix Wall_
        # for a waypoint, and do not silently skip the actual generated names.
        loop = re.search(r'\bfor\s+(\w+)\s*=\s*(\d+)\s*,\s*(\d+)\s+do\s*\w+\s*=\s*$',text[:token[1]])
        if loop and re.match(r'\s*\.\.\s*tostring\s*\(\s*'+re.escape(loop[1])+r'\s*\)',text[token[2]:]):
            first,last = int(loop[2]),int(loop[3])
            if 0 <= last-first <= 256:
                expanded.extend(token[0][1:-1]+str(n) for n in range(first,last+1))
                excluded.add(i)
        if i >= 3 and tokens[i-1][0] == ',' and tokens[i-2][0].strip('\"\'') == 'remove_barrier' and tokens[i-3][0] == '{':
            excluded.add(i)
    return [t[0][1:-1] for i,t in enumerate(tokens) if t[3] == 'string' and i not in excluded] + expanded


def audit(output, *, stage_ids=None, include_native_evidence=True):
    scope = frozenset(range(10111, 10137) if stage_ids is None else stage_ids)
    tables = {p.name: json.loads(p.read_bytes()) for p in TABLES.iterdir() if p.is_file() and p.name in
              ('stagedata_main', 'actdata', 'plotdata', 'dialogdata', 'tutorialstepdata',
               'missiondata', 'rewarddata', 'playerleveldata', 'constvaluesclient', 'plotavatardata', 'avatardata')}
    old = {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}
    later = {r['path']: r for r in resources.resource_map(resources.DEFAULT24)}
    report = {'schema': 1, 'static_only': True, 'stages': [], 'native_methods': []}
    with zipfile.ZipFile(resources.DEFAULT19) as z19, zipfile.ZipFile(resources.DEFAULT24) as z24:
        data = z19.read('assets/bin/Data/globalgamemanagers')
        parsed = resources.serialized(data)
        build = next(r for r in parsed['objects'].values() if r['class'] == 141)
        q = resources.Reader(data, build['offset'])
        scene_names = [q.string() for _ in range(q.read('i'))]
        configurations = {}
        for path in (('stage/data/stage_spaceship', 'stage/data/stage_st_freyja') if stage_ids is None
                     else sorted(p for p in old if p.startswith('stage/data/stage_'))):
            _, raw = resources.object_bytes(z19, old[path])
            configurations[path] = raw
        gameobjects_cache = {}
        for row in tables['stagedata_main']:
            if row['levelId'] not in scope:
                continue
            path = row['luaFile'].lower()
            pkg, mp = (z19, old) if path in old else (z24, later)
            raw, source = lua.text_record(pkg, mp[path], '1.9' if path in old else '2.4')
            text = raw.decode('utf-8-sig')
            tokens = lua.lua_tokens(text)
            # Superset includes non-Normal branches deliberately. Missing findings
            # need branch review rather than claiming an unavailable Normal asset.
            literals = [t[0][1:-1] for t in tokens if t[3] == 'string']
            point_names = sorted({s for s in normal_point_literals(text) if re.fullmatch(r'(?:Spawn|Wall|InnerWall|Field|Exit|Born|Box|Arrow|Center|Trigger)[\w]*', s)})
            stages = sorted(set(re.findall(r'\bstage\s*=\s*"([^"]+)"', text)))
            rogue_bindings=None
            if 211101 <= row['levelId'] <= 211118:
                from server19_chiyou_rooms import bindings
                common_raw,_=lua.text_record(z24,later['lua/base/roguebase/roguecommon.lua'],'2.4')
                preset_raw,_=lua.text_record(z24,later['lua/base/roguebase/roguepreset.lua'],'2.4')
                rogue_bindings=bindings(text,common_raw,preset_raw)
                bases={tokens[i+2][0][1:-1] for i,t in enumerate(tokens[:-2])
                       if t[0]=='base_stage' and tokens[i+1][0]=='=' and tokens[i+2][3]=='string'}
                stages=sorted({r['scene'] for r in rogue_bindings}|bases)
            records = []
            blockers = []
            for scene in stages:
                matching = [(i, s) for i, s in enumerate(scene_names) if s.endswith('/' + scene + '.unity')]
                cfgmatches = []
                for cfgpath, cfg in configurations.items():
                    needle = scene.encode()
                    for m in re.finditer(re.escape(needle), cfg):
                        pos = m.start() - 4
                        if pos < 0 or struct.unpack_from('<I', cfg, pos)[0] != len(needle):
                            continue
                        q = resources.Reader(cfg, pos)
                        selected = [q.string() for _ in range(10)]
                        streaming = q.read('B')
                        if streaming not in (0,1): raise ValueError('Invalid original streaming flag')
                        cfgmatches.append({'path': cfgpath, 'sha256': digest(cfg), 'byte_offset': pos,
                                           'stage': selected[0], 'prefab': selected[1], 'environment': selected[2],
                                           'location_point':selected[3], 'waypoint_prefab':selected[4],
                                           'openworld_asset':selected[9], 'enable_streaming':bool(streaming)})
                if len(matching) > 1 or len(cfgmatches) != 1:
                    blockers.append('Original navigation/configuration missing or ambiguous: ' + scene)
                    continue
                cfg = cfgmatches[0]
                envpath = 'stage/' + cfg['environment'].lower()
                prefabpath = 'stage/' + cfg['prefab'].lower()
                # Original StageManager switches to OpenWorld.LoadWorldAsset
                # when EnableStreaming is true; an empty PerpStage path is
                # intentional in those original entries, not a missing asset.
                required_paths = [envpath]
                if cfg['enable_streaming']:
                    required_paths.append(cfg['openworld_asset'].lower())
                else:
                    required_paths.append(prefabpath)
                missing_paths = [p for p in required_paths if p not in old]
                if missing_paths:
                    blockers.extend('Original prefab absent: ' + p for p in missing_paths)
                    continue
                if envpath not in gameobjects_cache:
                    full = z19.read('assets/bin/Data/' + old[envpath]['file'])
                    names = []
                    for obj in resources.serialized(full)['objects'].values():
                        if obj['class'] != 1:
                            continue
                        q = resources.Reader(full, obj['offset'])
                        for _ in range(q.read('i')):
                            q.read('iiq')
                        q.read('I')
                        names.append(q.string())
                    gameobjects_cache[envpath] = (digest(full), names)
                sha, names = gameobjects_cache[envpath]
                # Separate section scopes rather than applying both sections'
                # waypoints to both environments. Section headers have a fixed
                # source indentation in these pinned scripts.
                section_starts = list(re.finditer(r'^[ \t]*(section_\d+)\s*=\s*\{', text, re.M))
                if not section_starts:
                    # Most headers put the opening brace on the following line.
                    section_starts = list(re.finditer(r'^[ \t]*(section_\d+)\s*=\s*\n\s*\{', text, re.M))
                selected_points = []
                section_records = []
                for si, sh in enumerate(section_starts):
                    section_text = text[sh.start():section_starts[si + 1].start() if si + 1 < len(section_starts) else len(text)]
                    if not re.search(r'\bstage\s*=\s*"' + re.escape(scene) + r'"', section_text):
                        continue
                    ss = normal_point_literals(section_text)
                    section_points = sorted({s for s in ss if s in point_names})
                    selected_points.extend(section_points)
                    section_records.append({'section_name': sh[1], 'point_names_all_branches': section_points})
                if not section_records:
                    if rogue_bindings is not None:
                        section_records=[r for r in rogue_bindings if r['scene']==scene]
                        if scene in bases:
                            section_records.append({'section_name':'rogue_base','point_names_all_branches':[],
                                'scope':'Base resource only; generated room locators checked on each room'})
                        selected_points.extend(p for r in section_records for p in r['point_names_all_branches'])
                    if not section_records:
                        blockers.append('Section audit cannot prove stage scope: ' + path)
                absent = [s for s in sorted(set(selected_points)) if s not in names]
                camera_only = []
                for point in absent:
                    uses = []
                    for si, sh in enumerate(section_starts):
                        section_text = text[sh.start():section_starts[si+1].start() if si+1<len(section_starts) else len(text)]
                        if not re.search(r'\bstage\s*=\s*"'+re.escape(scene)+r'"',section_text): continue
                        ts = lua.lua_tokens(section_text)
                        for j,t in enumerate(ts):
                            if t[3]=='string' and t[0][1:-1]==point:
                                uses.append(j>=3 and ts[j-3][0]=='{' and ts[j-2][0].strip('\"\'')=='look_at' and ts[j-1][0]==',')
                    if uses and all(uses):camera_only.append(point)
                if camera_only:
                    assert native.pointer(native.M[65411])==0xba45b5
                    assert native.pointer(native.M[66037])==0xbe30ff
                records.append({'original_stage_configuration': cfg, 'navigation': matching[0] if matching else None,
                                'navigation_sha256': digest(z19.read('assets/bin/Data/level' + str(matching[0][0]))) if matching else None,
                                'navigation_unlisted_original_behavior': 'Original DetourManager.LoadNavMeshRelatedLevel returns without loading if the name is absent from its registered list' if not matching else None,
                                'original_loaded_stage_paths':required_paths,
                                'environment_resource_path': envpath, 'serialized_file_sha256': sha,
                                'section_records': section_records,
                                'candidate_point_names_all_branches': sorted(set(selected_points)), 'point_names_absent': absent,
                                'blocking_point_names_absent':[p for p in absent if p not in camera_only],
                                'camera_only_missing_original_fallback':camera_only,
                                'camera_fidelity_limit':'Missing camera-only point retains original GetSpawnPoint negative-index -> Random.Range fallback; precise later camera framing is not restored' if camera_only else None})
            plot_ids, tutorial_ids, wave_commands, camera_names = [], [], [], []
            for i, tok in enumerate(tokens[:-2]):
                if tok[0] != '{' or tokens[i + 1][3] != 'string':
                    continue
                command = tokens[i + 1][0][1:-1]
                wave_commands.append(command)
                if command == 'CameraAni' and tokens[i + 2][0] == ',' and tokens[i + 3][3] == 'string':
                    camera_names.append(tokens[i + 3][0][1:-1])
                if command in ('StoryMode', 'tutorial') and i + 4 < len(tokens) and tokens[i + 2][0] == ',':
                    atom = re.match(r'\d+', text[tokens[i + 3][1]:])
                    if atom:
                        (plot_ids if command == 'StoryMode' else tutorial_ids).append(int(atom[0]))
            plot_rows = [r for r in tables['plotdata'] if r['plotID'] in plot_ids]
            tutorials = [r for r in tables['tutorialstepdata'] if r['id'] in tutorial_ids]
            dialog_rows = [r for p in plot_rows for r in tables['dialogdata'] if p['startDialogID'] <= r['dialogID'] <= p['endDialogID']]
            tutorial_assets = [{'path': r['targetUIPath'].lower(), 'original_present': r['targetUIPath'].lower() in old}
                               for r in tutorials if r['targetUIPath'].startswith('SpriteOutput/')]
            retained_paths = []
            for camera in sorted(set(camera_names)):
                matches = [p for p in old if p.startswith('auxobject/cameraanim/') and p.rsplit('/', 1)[-1] == camera.lower()]
                if len(matches) != 1:
                    blockers.append('Original camera animation missing/ambiguous: ' + camera)
                else:
                    retained_paths.append(matches[0])
            weather_names = sorted({s for s in literals if re.fullmatch(r'Style\d+_[A-Za-z_]+', s)})
            for weather in weather_names:
                suffix = weather.lower()
                matches = [p for p in old if p.startswith('weather/stageweather/') and p.endswith('/' + suffix)]
                if len(matches) != 1:
                    blockers.append('Original stage weather metadata missing/ambiguous: ' + weather)
                else:
                    retained_paths.append(matches[0])
            if row['levelId'] == 10116:
                retained_paths.append('ai/avatar/avatarsupporterbehavior_claymore_bz')
            plot_actor_rows = [p for p in tables['plotavatardata'] if p['avatarID'] in {r['avatarID'] for r in dialog_rows}]
            for actor in plot_actor_rows:
                if actor['path']:
                    retained_paths.append(actor['path'].lower())
            normal_actors = [a for a in tables['avatardata'] if a['avatarID'] in {r['avatarID'] for r in dialog_rows}]
            retained = []
            for asset in sorted(set(retained_paths)):
                if asset not in old:
                    blockers.append('Original actor/resource absent: ' + asset)
                    continue
                obj, blob = resources.object_bytes(z19, old[asset])
                retained.append({'path': asset, 'resource': old[asset], 'object_class': obj['class'],
                                 'object_sha256': digest(blob), 'operation': 'retain_original'})
            missing_points = [r['blocking_point_names_absent'] for r in records if r['blocking_point_names_absent']]
            resource_blockers = blockers + (['Original section waypoint missing'] if missing_points else [])
            resource_blockers += ['Plot metadata absent: ' + str(i) for i in set(plot_ids) - {r['plotID'] for r in plot_rows}]
            resource_blockers += ['Tutorial metadata absent: ' + str(i) for i in set(tutorial_ids) - {r['id'] for r in tutorials}]
            resource_blockers += ['Tutorial image absent: ' + p['path'] for p in tutorial_assets if not p['original_present']]
            report['stages'].append({'stage_id': row['levelId'], 'act_id': row['actId'], 'source': source,
                'original_script_present': path in old, 'row': row, 'requires': lua.requires(text),
                'native_direct_calls': lua.calls(text), 'wave_commands_all_branches': sorted(set(wave_commands)),
                'original_scene_records': records, 'scene_blockers': blockers,
                'plot_ids_all_branches': sorted(set(plot_ids)), 'plot_rows': plot_rows, 'dialog_rows': dialog_rows,
                'plot_ids_absent': sorted(set(plot_ids) - {r['plotID'] for r in plot_rows}),
                'tutorial_ids_all_branches': sorted(set(tutorial_ids)), 'tutorial_rows': tutorials,
                'tutorial_ids_absent': sorted(set(tutorial_ids) - {r['id'] for r in tutorials}),
                'tutorial_assets': tutorial_assets, 'resource_blockers': resource_blockers,
                'original_resources_retained': retained, 'camera_names': sorted(set(camera_names)),
                'weather_names': weather_names, 'plot_actor_rows': plot_actor_rows,
                'normal_plot_actor_metadata': normal_actors,
                'bgm_cues': sorted(set(re.findall(r'\bbgm\s*=\s*"([^"]+)"', text))),
                'audio_limits': 'BGM/voice source cues retained unchanged; Wwise cue playback requires human acceptance, not a proved missing resource',
                'human_presentation_pending': True})
        report['act107'] = next(r for r in tables['actdata'] if r['actId'] == 107)
        report['constvalues'] = [r for r in tables['constvaluesclient'] if r['name'] in ('IsExtraActHide', 'MainStoryOnlyShowNextAct')]
        report['source_missions_by_stage'] = {str(s): [r for r in tables['missiondata'] if r.get('finishParaInt') == s and r.get('finishWay') == 180]
                                              for s in sorted(scope)}
        for mid in ((80138, 60443, 65070, 66012, 82360, 82362, 68117, 68124, 80121, 65566, 65567, 65570, 65571, 88091) if include_native_evidence else ()):
            dis = native.disasm(mid, 18000)
            filename = 'native-' + str(mid) + '.asm'
            (output / filename).write_text(dis + '\n', encoding='utf-8')
            report['native_methods'].append({'method_id': mid, 'name': native.N[mid], 'rva': hex(native.pointer(native.M[mid])), 'asm': filename})
    report['complete_resource_audit'] = not any(r['resource_blockers'] for r in report['stages'])
    report['complete_resource_audit_scope'] = 'Original navigation/configuration/env waypoints by section, CameraAni objects, weather metadata, plot/dialog/tutorial rows and direct source actor assets; binary actor/monster/ability/prop/trial closure is separate resource-agent manifest'
    report['known_visual_missing'] = ['MaterialIcons/5606 and MaterialFigures/5606 for item3108', 'AvatarFragmentIcons/10603 and AvatarFragmentFigures/10603 for fragment10603 (白夜执事)']
    (output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = audit(args.output)
    print(json.dumps({'stages': len(report['stages']), 'scene_blockers': [(r['stage_id'], r['scene_blockers']) for r in report['stages'] if r['scene_blockers']],
                      'absent_points': [(r['stage_id'], s['point_names_absent']) for r in report['stages'] for s in r['original_scene_records'] if s['point_names_absent']],
                      'missing_tutorials': [(r['stage_id'], r['tutorial_ids_absent']) for r in report['stages'] if r['tutorial_ids_absent']]}, ensure_ascii=False))
