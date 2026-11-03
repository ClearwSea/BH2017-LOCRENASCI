"""Bounded six-chapter Normal-story preparation against actual Sony resources.

No device writes, no fabricated stage completion and no removal of gameplay
fields to make unknown schemas pass. Historical1.9 Lua remains unavailable.
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
import json
import re
import zipfile
from pathlib import Path

import server19_chapter1_resources as ch
import server19_story_batch_resources as story
import server19_stage_resources as lua
import server19_stage_monsters as monsters
import server19_resources as resources
import server19_avatar_battle_resources as batch
from server19_metadata_export import SourceTypedDecoder, native_json

ROOT = Path(__file__).resolve().parent
WORK = ROOT / '.local-baseline/server19-dev/story-all-20261015'


class StoryClosure(ch.AbilityClosure):
    def resolve(self, identity):
        # Original registry override lookup falls back to the primary root.
        if identity not in self.spans and (identity[0], None) in self.spans:
            return identity[0], None
        return identity

    def references(self, reader, data):
        identities, props = super().references(reader, data)
        return list(dict.fromkeys(self.resolve(i) for i in identities)), props


def prepare(version='candidate-v7', *, current=None, bounded_shields=None, stage_ids=None, audit_path=None, bounded_area_shield_stages=(), voice_bank_path=None, native_shield_cap_bridge=False, native_weekly_voice=False, normal_openworld_scope=None, native_lock_acceleration=False, weapon_config_path=None, avatar_account_file=None, native_extra_voice=False, unavailable_voice_events=()):
    current = Path(current or WORK / 'current')
    output = WORK / version
    output.mkdir(exist_ok=False)
    inventory = json.loads((WORK / 'inventory.json').read_bytes())
    scope = json.loads(Path(normal_openworld_scope).read_bytes()) if normal_openworld_scope else None
    if scope:
        import hashlib
        assert scope['status']=='PASS_scoped_dependency_flow_only'
        assert stage_ids is not None and set(stage_ids)<=set(scope['stage_ids'])
        for rec in scope['stages']:
            assert hashlib.sha256((WORK/'lua-source'/rec['path']).read_bytes()).hexdigest()==rec['source_sha256']
        for name,expected in scope['tables_sha256'].items():
            assert hashlib.sha256((batch.TABLES/name).read_bytes()).hexdigest()==expected
    audit = json.loads(Path(audit_path or WORK / 'scene-audit/audit.json').read_bytes())
    scenes = {r['stage_id']: r for r in audit['stages']}
    import server19_story_voice_coverage as voice
    if voice_bank_path is None:
        ready = json.loads((WORK/'runtime-ready.json').read_bytes())
        voice_bank_path = ready.get('voice_bank_path', WORK/'progress-20261016/voice/server19_story_voice.bnk')
    voice_ids = voice.bank_events(voice_bank_path)
    tables = {n: json.loads((batch.TABLES / n).read_bytes()) for n in
              ('monsterconfigdata', 'uniquemonsterdata', 'avatartrialdata', 'teambuffdata', 'leveltrialdata')}
    strings_before = (current / '_baked/stringmap.txt').read_bytes()
    strings = strings_before.decode().split('\x1f')
    old = {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}
    later = {r['path']: r for r in resources.resource_map(resources.DEFAULT24)}
    monster_before = (current / monsters.PATH).read_bytes()
    roster = json.loads((ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/manifest.json').read_bytes())
    matrix = json.loads((ROOT / '.local-baseline/server19-dev/cultivation-full-equipment-ready/matrix.json').read_bytes())
    signatures = lua.method_signatures()
    mp_signatures = lua.method_signatures(include_mp=True)
    fake_records=[]
    if scope:
        from server19_story_fake_avatars import collect as collect_fake_avatars
        names=sorted({n for r in scope['stages'] for n in r.get('fake_avatar_registries_no_dress_override',[])})
        with zipfile.ZipFile(resources.DEFAULT19) as original:
            fake_records=collect_fake_avatars(names,strings,old,original)
    fake_by_name={r['registry']:r for r in fake_records}
    files, reports, modules = [], [], {}
    existing_modules = {r['path'] for r in json.loads((lua.DEFAULT_OUTPUT / 'manifest.json').read_bytes())['files']}
    prop_dispatch = {'medic_box':'GeneralBox','award_box':'AdvancedBox','equip_box':'JokeBox',
                     'roguereward_box':'JokeBoxSimple','witch_time_box':'JokeBox','switch':'Switch',
                     'barrel':'Barrel','pumpkin_box':'PumpkinBox','AiBox':'AiModelBox','slow_area':'MPLevel_FrozenArea',
                     'spike_trap':'Trap_Spike','special_spike_trap':'Trap_Spike_Special','fire_trap':'Trap_Fire','laser_trap':'Trap_Laser'}
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        if native_lock_acceleration:
            assert native_shield_cap_bridge
            from server19_story_movement_bridge import MovementClosure
            closure=MovementClosure(source,strings,old,output)
        elif native_shield_cap_bridge:
            from server19_story_shield_bridge import ShieldClosure
            closure = ShieldClosure(source, strings, old, output)
        else:
            closure = StoryClosure(source, strings, old, output)
        closure.schema.ui_custom_buff_ids=(1001,6005,6006)
        closure.schema.leader_restrict_roots=(7067,12631)
        from server19_equipment_battle_closure import prop_selector_evidence
        closure.schema.equipment_prop_selector_proof=prop_selector_evidence(closure.schema)
        closure.schema.equipment_prop_selectors={r['tag']:r['concrete'] for r in closure.schema.equipment_prop_selector_proof if r['original']}
        closure.schema.event_only_missing_names=('Boss_050_ATK03_Low_Bullet_L','Boss_050_ATK03_Low_Bullet_R')
        from server19_story_poly_dispatch import evidence as small_poly_evidence
        closure.schema.story_small_poly={};small_poly_records=[]
        for name,mid in (('MoleMole.Config.BaseSpawnPropInitialPosSelect',58731),
                         ('MoleMole.Config.ConfigMonsterAttackHint',58775),
                         ('MoleMole.Config.ConfigAvatarCameraAction',58759)):
            facts=small_poly_evidence(closure.schema,name,mid);small_poly_records.extend(facts)
            closure.schema.story_small_poly[name]={r['tag']:r['concrete'] for r in facts if r['original']}
        closure.bounded_shield_identities = bounded_shields or {}
        closure.before = (current / batch.ability.PATH).read_bytes()
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        # These are attached by original runtime handlers (pickups and defense
        # monster creation), not necessarily written as AddNewAbility in Lua.
        # Include their full families so literal-script scanning cannot miss
        # the same dependency again on the next stage or difficulty variant.
        runtime_ability_seeds = [k for k in closure.spans
                                 if strings[k[0]].startswith(('Goods_', 'DEF_', 'MP_Monster_', 'MPLevel_'))]
        from server19_story_avatar_runtime import selected_dependencies
        avatar_account=json.loads(Path(avatar_account_file).read_bytes()) if avatar_account_file else None
        avatar_seeds,avatar_selection=selected_dependencies(roster['roster'],avatar_account,include_leaders=True)
        runtime_ability_seeds.extend(avatar_seeds)
        from server19_story_weapon_runtime import dependencies as weapon_dependencies
        weapon_input = Path(weapon_config_path) if weapon_config_path else current/'_baked/bakedweapondata'
        if not weapon_input.exists(): weapon_input = batch.WEAPONS
        weapon_raw = weapon_input.read_bytes()
        runtime_weapon_proof = weapon_dependencies(weapon_raw, strings)
        import hashlib
        runtime_weapon_proof.update(input_path=str(weapon_input.resolve()),
                                   input_sha256=hashlib.sha256(weapon_raw).hexdigest())
        runtime_ability_seeds.extend(tuple(r['identity']) for r in runtime_weapon_proof['dependencies'])
        runtime_ability_seeds = list(dict.fromkeys(runtime_ability_seeds))
        closure.prop_raw = (current / '_baked/bakedpropdata').read_bytes()
        closure.resolve_original_prop_basename=True
        closure.prop_data, closure.prop_spans = batch.packed(closure.prop_raw)[3::2]
        closure.model_path_aliases = {
            'entities/propobject/switch':'Entities/PropObject/Level2/Switch',
            'entities/propobject/barrel':'Entities/PropObject/Level1/Barrel',
            'entities/propobject/trap_spike_special':'Entities/PropObject/Level1/Trap_Spike_Special',
            'entities/propobject/trap_laser':'Entities/PropObject/Level1/Trap_Laser',
            'entities/propobject/stage_jump/jumpstagedropcube':'Entities/PropObject/Jump1/JumpStageDropCube',
            'entities/propobject/stage_jump/fragilecube':'Entities/PropObject/Jump1/FragileCube',
            'entities/propobject/boss_050_firearea':'Entities/PropObject/Monster1/Boss_050_FireArea',
            **{'entities/propobject/'+name:'Entities/PropObject/Level2/'+name for name in (
                'level_fireareaball','level_fireareasmall','level_fireareasmall_ro_030',
                'level_firearea_ro_010_generate_01','level_firearea_ro_010_generate_02')},
            **{'entities/propobject/'+name:'Entities/PropObject/Level2/'+name for name in (
                'level_firearea','level_fallstoneonce','level_freezearea_ul_013_generate_01',
                'level_freezearea_ul_013_generate_02','level_freezearea_ul_032_generate_01')}}

        def missing_calls(text, path=None):
            errors = []
            for call in lua.calls(text):
                if (scope and path=='lua/base/levelfakeavatarcommon.lua'
                    and call['method'] in ('CreateFakeAdhocAvatarByPeer','CreateFakeAdhocAvatarWithDress')):
                    assert 'if LevelDesign:IsMPLevel() then' in text and 'if fake_avatar_config.dressDesc == nil then' in text
                    # Selected Normal roots have only literal registries and
                    # no dress override. Preserve both source branches, but
                    # audit the actually selected original SP API below.
                    continue
                from server19_story_lua_compat import PATH, GUARD
                if (path == PATH and GUARD in text and call['method']=='CreateCustomGoodsWithoutCallback'
                        and any(s['minimum_args'] <= call['static_argument_count'] <= s['maximum_args']
                                for s in mp_signatures.get(call['method'], []))):
                    continue
                # The existing lexical scanner splits commas in anonymous
                # function bodies. These two native methods take exactly one
                # function; verify that complete expression, not its body commas.
                if call['method'] in ('CreateCoroutine', 'CreateCoroutineNextFrame'):
                    expr = ','.join(call['arguments']).strip()
                    if expr.startswith('function') and expr.endswith('end'):
                        continue
                if call['static_argument_count'] is None or not any(
                        s['minimum_args'] <= call['static_argument_count'] <= s['maximum_args']
                        for s in signatures.get(call['method'], [])):
                    errors.append(call)
            return errors

        def module(path):
            if path in existing_modules:
                return []
            if path in modules:
                return modules[path]['blockers']
            report = {'path':path, 'blockers':[]}; modules[path] = report
            if path not in later:
                report['blockers'].append({'module_missing':path}); return report['blockers']
            raw, provenance = lua.text_record(source, later[path], '2.4')
            if scope and path in scope['module_source_sha256']:
                assert hashlib.sha256(raw).hexdigest()==scope['module_source_sha256'][path]
            from server19_story_lua_compat import transform
            raw, adaptation = transform(path, raw)
            text = raw.decode('utf-8-sig')
            from server19_story_wave_abilities import references as shared_ability_references, registered_references
            report['literal_ability_references'] = shared_ability_references(text, unresolved=[])+registered_references(text,{strings[k[0]] for k in closure.spans})
            excluded=None
            if (stage_ids and set(stage_ids)<=set(range(211101,211119))
                    and path=='lua/base/roguebase/roguedebufflist.lua'):
                from server19_chiyou_dependencies import unused_debuff_callback
                excluded=unused_debuff_callback(raw,(batch.TABLES/'roguestagedebuffdata').read_bytes())
                if excluded:report['unselected_callback_evidence']=excluded
            for reference in report['literal_ability_references']:
                if reference['ability'] not in strings:
                    if excluded and reference['ability']==excluded['ability']:
                        continue
                    # Cache the failure on the shared module too: otherwise an
                    # exception blocks only its first caller and later stages
                    # incorrectly reuse an empty successful module report.
                    report['blockers'].append({'module_ability_unresolved':reference})
                else:
                    runtime_ability_seeds.append((strings.index(reference['ability']),None))
            report.update(source=provenance, adaptation=adaptation, calls_missing=missing_calls(text,path))
            if report['calls_missing']:
                report['blockers'].append({'module_native_API':report['calls_missing']})
            try:
                if scope and path=='lua/base/openworldeventdesign.lua':
                    dependencies=[{'path':p} for p in scope['event_init_dependencies']]
                    report['scoped_dependency_evidence']='Actual source event_init run for all selected Normal roots; event/quest lists absent, all mapped stage missions included'
                elif scope and path=='lua/base/owmissioncommon.lua':
                    dependencies=[]
                    report['scoped_dependency_evidence']='Generic create_mission is only referenced by uncalled CreateMission forwarder; selected roots/shared closure verified'
                else:dependencies = lua.requires(text)
            except ValueError as err:
                dependencies = []
                report['blockers'].append({'module_dependency_scan':{'path':path,'reason':str(err)}})
            for dep in dependencies: report['blockers'].extend(module(dep['path']))
            report['file'] = story.store(output, path, raw)
            return report['blockers']

        wave_token_cache = {}
        for item in inventory:
            sid = item['stage_id']
            if stage_ids is not None and sid not in stage_ids:
                continue
            if sid <= 10136:
                # Keep already deployed first-chapter scripts/repairs exact.
                continue
            from server19_story_lua_compat import transform
            root_raw,root_adaptation = transform(item['lua'],(WORK/'lua-source'/item['lua']).read_bytes())
            text = root_raw.decode('utf-8-sig')
            rec = {'stage_id':sid, 'chapter':item['chapter'], 'source':item['source'],
                   'lua':item['lua'], 'blockers':list(scenes[sid]['resource_blockers']),
                   'monster_identities':[], 'ability_seeds':[], 'prop_seeds':[]}
            reports.append(rec)
            if root_adaptation:rec['lua_adaptation']=root_adaptation
            rec['voice_coverage'] = voice.coverage(scenes[sid], voice_ids,
                supported_prefixes=('VO_Dialog_',) + (('VO_Weekly_Dialog_',) if native_weekly_voice else ()) + (('VO_Extra_Dialog_',) if native_extra_voice else ()))
            missing_voice = set(rec['voice_coverage']['missing'])
            if missing_voice and missing_voice <= set(unavailable_voice_events) and not rec['voice_coverage']['loader_unsupported']:
                rec['presentation_limits'] = {'unavailable_original_voice_retained': sorted(missing_voice), 'no_replacement_or_silencing': True}
            elif rec['voice_coverage']['status'] != 'PASS':
                rec['blockers'].append({'story_voice': rec['voice_coverage']})
            if item['row']['battleType'] not in (1,2,3,101,102,104):
                rec['blockers'].append({'unsupported_battle_type':item['row']['battleType']})
            try:
                # Extra-story mode adds these roots outside the Lua AddNewAbility
                # calls. Audit the complete two-root family for this mode.
                if re.search(r'level\.special_type\s*=\s*["\']ExtraStory_01["\']',text):
                    rec['mode_ability_references']=[strings[k[0]] for k in closure.spans
                        if strings[k[0]].startswith('Level_ExtraStory')]
                    rec['ability_seeds'].extend(k for k in closure.spans
                        if strings[k[0]].startswith('Level_ExtraStory'))
                from server19_story_wave_abilities import references as wave_abilities
                if sid == 211114:
                    from server19_chiyou_dependencies import ability_references
                    rec['wave_ability_references'] = ability_references(sid,root_raw,text)
                else:
                    rec['wave_ability_references'] = wave_abilities(text)
                rec['ability_seeds'].extend((strings.index(r['ability']), None)
                    for r in rec['wave_ability_references'])
                if scope:
                    context=next(r for r in scope['stages'] if r['stage_id']==sid)
                    names=context.get('fake_avatar_registries_no_dress_override',[])
                    if names:
                        rec['fake_avatars']=[fake_by_name[n] for n in names]
                        rec['ability_seeds'].extend(tuple(d) for n in names for d in fake_by_name[n]['dependencies'])
                calls = lua.calls(text)
                missing = missing_calls(text)
                if missing: rec['blockers'].append({'native_API':missing})
                for dep in lua.requires(text): rec['blockers'].extend(module(dep['path']))
                waves = lua.normal_monster_waves(text, {r['monsterName'] for r in tables['monsterconfigdata']})
                if 211101 <= sid <= 211118:
                    from server19_chiyou_dependencies import shared_monster_waves
                    shared_raw={}
                    for path in modules:
                        if path.startswith('lua/base/roguebase/'):
                            shared_raw[path]=lua.text_record(source,later[path],'2.4')[0]
                    shared_waves,unresolved=shared_monster_waves(shared_raw,{r['monsterName'] for r in tables['monsterconfigdata']},text)
                    rec['shared_monster_audit']={'expanded_waves':len(shared_waves),'unresolved':unresolved,'scope':'conservative union of shared templates'}
                    rec['blockers'].extend({'shared_dynamic_monster':r} for r in unresolved)
                    waves.extend(shared_waves)
                if sid in (211116,211117):
                    from server19_chiyou_dependencies import expand_monster_waves
                    common_raw,_ = lua.text_record(source,later['lua/base/roguebase/roguecommon.lua'],'2.4')
                    waves = expand_monster_waves(sid,root_raw,text,waves,common_raw)
                if item['chapter'] in (5,6):
                    from server19_story_openworld_scope import area_monster_references
                    area_refs=area_monster_references(text,item['row']['hardLevel'])
                    rec['area_monster_references']=area_refs
                    waves.extend(area_refs)
                rec['normal_monster_waves'] = waves
                for wave in waves:
                    # Unique-monster IDs select their real typeName (e.g.
                    # DAKiana/PT_Default), not the wave's default string.
                    tail=wave.get('audit_source_tail') or ('{}' if wave.get('source')=='_custom_monster_config' else
                          '\n'.join(text.splitlines()[wave['line']-1:]))
                    if tail not in wave_token_cache:
                        wave_token_cache[tail]=lua.lua_tokens(tail)
                    tokens=wave_token_cache[tail];depth=0;unique_id=None
                    for index,token in enumerate(tokens):
                        if token[0]=='{':depth+=1
                        elif token[0]=='}':
                            depth-=1
                            if depth==0:break
                        elif depth==1 and token[0]=='uniqueID' and tokens[index+1][0]=='=':
                            atom=tokens[index+2][0]
                            if atom.isdecimal():
                                unique_id=int(atom)
                            elif 'audit_unique_id' in wave:
                                unique_id=wave['audit_unique_id']
                            else:
                                raise ValueError('Dynamic unique monster ID')
                    unique=next((r for r in tables['uniquemonsterdata'] if r['uniqueID']==unique_id),None)
                    # The shared source dispatcher replaces the placeholder
                    # wave name with GetUniqueMonsterName before spawning.
                    monster_name = unique['monsterName'] if unique is not None else wave['monster']
                    variant=unique['typeName'] if unique is not None else wave['configType']
                    meta = next((r for r in tables['monsterconfigdata'] if
                                (r['monsterName'],r['typeName']) == (monster_name,variant)), None)
                    if meta is None:
                        raise ValueError('Monster metadata row absent: '+repr((monster_name,variant)))
                    if unique is not None:
                        wave['resolved_unique_metadata']=unique
                        wave['resolved_monster_name']=monster_name
                        if unique['abilities']:
                            additions=json.loads(unique['abilities'])
                            for ability in additions:
                                if not set(ability)<= {'Name','Specials'} or not isinstance(ability['Name'],str):
                                    raise ValueError('Unknown unique-monster ability descriptor')
                                if any(type(v) not in (int,float) for v in ability.get('Specials',{}).values()):
                                    raise ValueError('Dynamic unique-monster Specials require audit')
                                rec['ability_seeds'].append((strings.index(ability['Name']),None))
                    model = 'entities/monster/'+meta['categoryName'].lower()+'/'+meta['subTypeName'].lower()+'/'+meta['subTypeName'].lower()
                    ai = 'ai/monster/'+(unique['AIName'] if unique is not None and unique['AIName'] else meta['AIName']).lower()
                    for asset in (model,ai):
                        if asset not in old: rec['blockers'].append({'original_monster_asset_missing':asset})
                    config_variant=unique['configType'] if unique is not None and unique['configType'] else meta['configType']
                    identity = (strings.index(meta['configFile']), None if config_variant=='Default' else strings.index(config_variant))
                    rec['monster_identities'].append(identity)
                    # Original MonsterData.GetMonsterConfig59879 also resolves
                    # the metadata's base configType when no override is supplied.
                    # Auditing only the unique override misses this runtime path.
                    base_variant = meta['configType']
                    rec['monster_identities'].append((strings.index(meta['configFile']),
                        None if base_variant == 'Default' else strings.index(base_variant)))
                    attrs = set(wave['explicit_attributes']) | ({'Elite_EliteShield'} if wave['isElite'] else set())
                    for attr in attrs:
                        key = strings.index(attr)
                        variant = strings.index(monster_name) if monster_name in strings else None
                        identity = key, variant
                        rec['ability_seeds'].append(identity if identity in closure.spans else (key,None))
                for wave in lua.normal_monster_waves(text,set(prop_dispatch)):
                    if wave['monster'] not in prop_dispatch:
                        continue
                    key = strings.index(prop_dispatch[wave['monster']]); rec['prop_seeds'].append(key);closure.prop(key)
                for call in calls:
                    name,args = call['method'],call['arguments']
                    if name in ('AddNewAbilityToAvatar','AddNewAbility'):
                        literal = args[1].strip()
                        if not re.fullmatch(r'''["'][A-Za-z0-9_]+["']''',literal):
                            raise ValueError('Dynamic direct ability name requires runtime audit')
                        rec['ability_seeds'].append((strings.index(literal[1:-1]),None))
                    elif name == 'CreatePropObject':
                        literal = args[0].strip()
                        if not re.fullmatch(r'''["'][A-Za-z0-9_]+["']''',literal):
                            raise ValueError('Dynamic direct prop name requires runtime audit')
                        key = strings.index(literal[1:-1]);rec['prop_seeds'].append(key);closure.prop(key)
                    elif name == 'AddTeamBuffById':
                        buff = next(r for r in tables['teambuffdata'] if r['buffId']==int(args[0]))
                        rec['ability_seeds'].append((strings.index(buff['abilityName']),None))
                trial_ids = {int(c['arguments'][0]) for c in calls if c['method'] == 'CreateTrialAdhocAvatar'}
                table_trials = [r for r in tables['leveltrialdata'] if r['stageID'] == sid]
                trial_ids.update(t for r in table_trials for t in r['avatarList'])
                if table_trials:
                    rec['level_trial_rows'] = table_trials
                for trial_id in sorted(trial_ids):
                    trial = next(r for r in tables['avatartrialdata'] if r['ID']==trial_id)
                    actor = next(r for r in roster['roster'] if r['avatar_id']==trial['avatarID'])
                    bought = {r['skillID'] for r in trial['avatarSubSkills'] if r['skillLV']>0}
                    rec['ability_seeds'].extend((r['key'],r['variant']) for r in actor['dependencies']
                        if r['scope'] in ('base','default_skill') or r.get('evidence',{}).get('sub_skill_id') in bought)
                    for eid in (trial['weaponID'],trial['stigmataID1'],trial['stigmataID2'],trial['stigmataID3']):
                        if not eid: continue
                        gear = next(r for r in matrix['items'] if r['item_id']==eid)
                        if gear['blockers']: rec['blockers'].append({'trial_equipment':eid,'details':gear['blockers']})
                        rec['ability_seeds'].extend((r['key'],r['variant']) for r in gear['skills'])
                    rec.setdefault('trials',[]).append(trial)
                if 211101 <= rec['stage_id'] <= 211118:
                    from server19_chiyou_buffs import buff_rows, ability_name, active_ability_seeds
                    pool = buff_rows(batch.TABLES)
                    rec['random_team_buff_ids'] = [r['buffId'] for r in pool]
                    rec['ability_seeds'].extend((strings.index(ability_name(r)), None) for r in pool)
                    rec['ability_seeds'].extend(active_ability_seeds(strings, closure.spans))
                for field in ('monster_identities','ability_seeds','prop_seeds'):
                    rec[field] = list(dict.fromkeys(rec[field]))
            except (ValueError,KeyError,IndexError,StopIteration) as err:
                rec['blockers'].append({'dependency_scan':repr(err)})
            rec['file'] = story.store(output,item['lua'],root_raw)

        all_monsters = {i for r in reports for i in r['monster_identities']}
        monster_after, monster_records, monster_errors = ch.project_monsters(monster_before,all_monsters,strings,output)
        by_monster = {tuple(r['identity']):r for r in monster_records}
        for rec in reports:
            if not native_shield_cap_bridge and (15599, None) in rec['ability_seeds'] and rec['stage_id'] not in bounded_area_shield_stages:
                rec['blockers'].append({'shield_cap_proof': 'Dynamic area shield requires a stage-specific HP and Specials bound'})
            for identity in rec['monster_identities']:
                if identity in monster_errors: rec['blockers'].append({'monster':identity,'reason':monster_errors[identity]})
                rec['ability_seeds'].extend(by_monster[identity]['dependencies'])
            rec['ability_seeds'] = list(dict.fromkeys(closure.resolve(i) for i in rec['ability_seeds']))
            rec['ability_seeds'].extend(runtime_ability_seeds)
            rec['ability_seeds'] = list(dict.fromkeys(rec['ability_seeds']))
            for identity in rec['ability_seeds']: closure.project(identity)
            for key in rec['prop_seeds']:
                prop = closure.props[key]
                if 'blocker' in prop: rec['blockers'].append({'prop':key,'reason':prop['blocker']})
                rec['ability_seeds'].extend(prop['dependencies'])
            rec['ability_seeds'] = list(dict.fromkeys(closure.resolve(i) for i in rec['ability_seeds']))
            for identity in rec['ability_seeds']: closure.project(identity)
        # Summons are a recursive part of the same monster/ability closure.
        for _ in range(12):
            extra = closure.monster_refs-all_monsters
            if not extra: break
            all_monsters |= extra
            monster_after,monster_records,monster_errors = ch.project_monsters(monster_before,all_monsters,strings,output)
            for monster in monster_records:
                for identity in monster['dependencies']: closure.project(identity)
        for rec in reports:
            # The nonbinding cap proof is scoped to stage10205, not later
            # variants with different HP multipliers or dynamic hard levels.
            if not native_shield_cap_bridge and rec['stage_id'] != 10205 and any(i in rec['ability_seeds'] for i in ((15671, 21836), (15671, 7888))):
                rec['blockers'].append({'shield_cap_proof': 'Unique01 only audited for10205'})
            rec['blockers'].extend({'ability':x} for x in closure.failure_chain(rec['ability_seeds']))
            # The old equipment matrix predates the explicit UI-only6006
            # projection. Reassess only that exact stale reason after its
            # complete ability dependency chain has passed again.
            if not closure.failure_chain(rec['ability_seeds']):
                stale=[b for b in rec['blockers'] if isinstance(b,dict) and 'trial_equipment' in b
                       and b.get('details') and all('CustomBuffID' in d.get('reason','')
                           and d.get('chain') and all(c.get('key')==10423 for c in d['chain']) for d in b['details'])]
                if stale:
                    rec['reassessed_previous_trial_equipment_audit']=stale
                    rec['blockers']=[b for b in rec['blockers'] if b not in stale]
                # The legacy matrix predates the now-proven prop attack union.
                # Require the exact historical reason and a fresh successful prop read.
                cross_prop = closure.props.get(8238, {})
                selector_stale = [b for b in rec['blockers']
                    if isinstance(b, dict) and b.get('trial_equipment') == 30547 and b.get('details')
                    and all(d.get('skill_id') == 3074 and d.get('chain')
                        and all(c.get('key') == 10248 for c in d['chain'])
                        and d.get('reason', '').startswith('Selected ability logical field count changed: MoleMole.Config.TriggerRefPropSelect/2/0 ')
                        for d in b['details'])]
                if selector_stale and closure.schema.equipment_prop_selector_proof:
                    rec.setdefault('reassessed_previous_trial_equipment_audit', []).extend(selector_stale)
                    rec['trial_prop_selector_dispatch_proof'] = closure.schema.equipment_prop_selector_proof
                    rec['blockers'] = [b for b in rec['blockers'] if b not in selector_stale]
                cross_stale = [b for b in rec['blockers']
                    if isinstance(b, dict) and b.get('trial_equipment') == 20464 and b.get('details')
                    and all(d.get('prop_key') == 8238
                        and d.get('reason', '').startswith('AttackPattern concrete dispatch unproven: 2 at ')
                        for d in b['details'])]
                if cross_stale and cross_prop and 'blocker' not in cross_prop and 2 in closure.schema.equipment_attack_patterns:
                    rec.setdefault('reassessed_previous_trial_equipment_audit', []).extend(cross_stale)
                    rec['trial_prop_attack_dispatch_proof'] = closure.schema.equipment_attack_pattern_proof
                    rec['blockers'] = [b for b in rec['blockers'] if b not in cross_stale]
            if closure.monster_refs-all_monsters:rec['blockers'].append('Unbounded summon closure')
            rec['status']='blocked' if rec['blockers'] else 'candidate_human_pending'
        # Deploy only reachable successful roots. Research of a blocked stage
        # must not change unrelated live roots or enable half-projected skills.
        by_monster={tuple(r['identity']):r for r in monster_records}
        selected_abilities,selected_monsters,selected_props=set(),set(),set()
        for rec in reports:
            if rec['blockers']:continue
            abilities=list(rec['ability_seeds']);mons=list(rec['monster_identities']);props=list(rec['prop_seeds'])
            aset,mset,pset=set(),set(),set();errors=[]
            while abilities or mons or props:
                while mons:
                    identity=tuple(mons.pop())
                    if identity in mset:continue
                    mset.add(identity)
                    if identity in monster_errors:errors.append({'summoned_monster':identity,'reason':monster_errors[identity]});continue
                    abilities.extend(by_monster[identity]['dependencies'])
                while abilities:
                    identity=closure.resolve(tuple(abilities.pop()))
                    if identity in aset:continue
                    aset.add(identity)
                    if identity in closure.errors:errors.append({'ability':identity,'reason':closure.errors[identity]});continue
                    root=closure.records[identity];abilities.extend(root['dependencies']);props.extend(root['props'])
                    mons.extend(r['identity'] for r in root.get('summoned_monsters',[]))
                while props:
                    key=props.pop()
                    if key in pset:continue
                    pset.add(key);prop=closure.props[key]
                    if 'blocker' in prop:errors.append({'prop':key,'reason':prop['blocker']});continue
                    abilities.extend(prop['dependencies'])
            if not native_shield_cap_bridge and (15599, None) in aset and rec['stage_id'] not in bounded_area_shield_stages:
                errors.append({'shield_cap_proof': 'Reachable area shield requires a stage-specific bound'})
            if errors:
                rec['blockers'].extend(errors);rec['status']='blocked'
            else:
                selected_abilities |= aset;selected_monsters |= mset;selected_props |= pset
        monster_after,selected_monster_records,errors=ch.project_monsters(monster_before,selected_monsters,strings,output)
        assert not errors
        for path,raw in ((batch.ability.PATH,story.reassemble(closure.before,{k:v for k,v in closure.changes.items() if k in selected_abilities})),
                         (monsters.PATH,monster_after),
                         ('_baked/bakedpropdata',story.reassemble(closure.prop_raw,{k:v for k,v in closure.prop_changes.items() if k[0] in selected_props})),
                         ('_baked/stringmap.txt','\x1f'.join(strings).encode())):
            files.append(story.store(output,path,raw))
        if any(211101 <= r['stage_id'] <= 211118 for r in reports):
            from server19_chiyou_buffs import ability_name
            buff_table = [dict(r) for r in tables['teambuffdata']]
            for row in buff_table:
                row['abilityName'] = ability_name(row)
            files.append(story.store(output, '_exceloutputasset/teambuffdata',
                json.dumps(buff_table,ensure_ascii=False,separators=(',',':')).encode('utf8')))
        # Keep all current NPC rows; append real source rows for future stages.
        npc_before=(current/'_exceloutputasset/npclevellogic').read_bytes()
        _,blob=resources.object_bytes(source,later['data/_exceloutput/npclevellogic'])
        import csv,io
        _,tsv=resources.text_asset(blob)
        source_rows=list(csv.DictReader(io.StringIO(tsv.decode()),delimiter='\t'))
        from server19_story_npc_level_closure import required_levels, append_rows
        npc_texts={r['lua']:(WORK/'lua-source'/r['lua']).read_text(encoding='utf-8-sig') for r in inventory}
        for path in set(modules) | (set(scope['module_source_sha256']) if scope else set()):
            if path in later:
                raw,_=lua.text_record(source,later[path],'2.4')
                npc_texts[path]=raw.decode('utf-8-sig')
        dynamic_path=current/'_exceloutputasset/dynamichardlvdata'
        if not dynamic_path.exists():dynamic_path=batch.TABLES/'dynamichardlvdata'
        dynamic_rows=json.loads(dynamic_path.read_bytes())
        npc_levels,npc_audit=required_levels(inventory,dynamic_rows,npc_texts)
        npc_after,npc_added=append_rows(npc_before,npc_levels,source_rows)
        npc_audit.update(required_levels=sorted(npc_levels),added_rows=npc_added,dynamic_table=str(dynamic_path))
        files.append(story.store(output,'_exceloutputasset/npclevellogic',npc_after))
    result={'schema':1,'scope':'six chapters Normal, real prerequisites preserved',
            'stages':reports,'ready_stage_ids':[r['stage_id'] for r in reports if not r['blockers']],
            'blocked_stage_ids':[r['stage_id'] for r in reports if r['blockers']],
            'files':files,'modules':list(modules.values()),'npc_level_closure':npc_audit,
            'ability_errors':[{'identity':k,'reason':v} for k,v in closure.errors.items()],
            'ability_reference_graph':[{'identity':k,'dependencies':r.get('dependencies',[]),'props':r.get('props',[])} for k,r in closure.records.items()],
            'monster_errors':[{'identity':k,'reason':v} for k,v in monster_errors.items()],
            'human_acceptance':'pending','native_shield_cap_bridge_required':native_shield_cap_bridge,
            'required_native_capabilities':(['shield_cap_v1'] if native_shield_cap_bridge else []) + (['weekly_voice_v1'] if native_weekly_voice else []) + (['lock_acceleration_v1'] if native_lock_acceleration else []),
            'shield_bridge_records':[r for r in closure.records.values() if r.get('native_shield_cap')],
            'small_polymorphic_dispatch_proof':small_poly_records,
            'fake_avatar_dependency_proof':fake_records,
            'runtime_weapon_dependency_proof':runtime_weapon_proof,
            'runtime_avatar_dependency_proof':avatar_selection,
            'runtime_event_targets_without_global_config':closure.runtime_event_references,
            'source_policy':'2.4 compatibility, not historical1.9 Lua'}
    (output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    result=prepare()
    print(json.dumps({'ready':len(result['ready_stage_ids']),'blocked':len(result['blocked_stage_ids']),
                      'ability_errors':len(result['ability_errors'])}))
