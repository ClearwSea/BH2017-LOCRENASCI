"""Restore exact original prefab paths for the existing fire-area prop family."""

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
import zipfile
from pathlib import Path
import server19_avatar_battle_resources as batch
import server19_resources as resources
import server19_stage_monsters as monster
from server19_story_shield_bridge import ShieldClosure
from server19_story_goal_prepare import OUT


def repack(raw,changes):
    h,entries,overrides,data,refs,spans=batch.packed(raw)
    packed,offsets=bytearray(),{}
    for _,key in sorted(refs.items()):
        offsets[key]=len(packed);packed.extend(changes.get(key,data[slice(*spans[key])]))
    return monster.pack_container(h,[(k,offsets[k,None]) for k,_ in entries],
        [(k,v,offsets[k,v]) for k,v,_ in overrides],bytes(packed))


def prepare(version='prop-firearea-runtime-v1', *, all_models=False, ability_file=None, device_dir=None, exclude_props=()):
    folder=OUT/version;folder.mkdir(exist_ok=True);device=Path(device_dir or folder/'device')
    output=folder/'candidate';output.mkdir(exist_ok=False)
    string_raw=(device/'stringmap.txt').read_bytes()
    strings=string_raw.decode('utf-8').split('\x1f');before_strings=strings.copy()
    prop_raw=(device/'bakedpropdata').read_bytes()
    ability_raw=Path(ability_file or OUT/'mplevel-runtime-v3/bakedabilitydata').read_bytes()
    original_map={r['path']:r for r in resources.resource_map(resources.DEFAULT19)}
    aliases={};selected=[];missing=[]
    data,spans=batch.packed(prop_raw)[3::2]
    for identity,(left,right) in spans.items():
        if identity[0] in exclude_props:continue
        q=batch.baked.MessagePackSpanReader(data);q.pos=left;node=q.node()
        field=node['children'][1]
        if field['code']==0xc0:continue
        model=strings[batch.baked.decode_integer(data,field)].lower()
        if not all_models and 'firearea' not in model:continue
        if model in original_map:
            if not all_models:selected.append(identity[0])
            continue
        # Only original indexed prefabs with the exact same basename qualify.
        matches=[p for p in original_map if p.startswith('entities/propobject/') and p.rsplit('/',1)[-1]==model.rsplit('/',1)[-1]]
        if len(matches)!=1:
            missing.append(dict(identity=identity,model=model,matches=matches));continue
        aliases[model]=matches[0];selected.append(identity[0])
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        closure=ShieldClosure(source,strings,original_map,output)
        closure.schema.ui_custom_buff_ids=(1001,6005,6006)
        closure.schema.leader_restrict_roots=(7067,12631)
        import server19_equipment_battle_closure as eq
        closure.schema.equipment_prop_selectors={r['tag']:r['concrete'] for r in eq.prop_selector_evidence(closure.schema) if r['original']}
        from server19_story_poly_dispatch import evidence
        closure.schema.story_small_poly={}
        for name,mid in (('MoleMole.Config.BaseSpawnPropInitialPosSelect',58731),('MoleMole.Config.ConfigMonsterAttackHint',58775)):
            closure.schema.story_small_poly[name]={r['tag']:r['concrete'] for r in evidence(closure.schema,name,mid) if r['original']}
        closure.before=ability_raw;closure.data,closure.spans=batch.packed(ability_raw)[3::2]
        closure.prop_raw=prop_raw;closure.prop_data,closure.prop_spans=data,spans
        closure.model_path_aliases=aliases
        for key in selected:closure.prop(key)
        blocked=[dict(key=k,reason=v['blocker']) for k,v in closure.props.items() if 'blocker' in v]
        if blocked or closure.errors:
            report=dict(blocked=blocked,errors=[dict(identity=k,reason=v) for k,v in closure.errors.items()])
            report.update(selected_props=len(selected),changed_props=len(closure.prop_changes),selected_abilities=len(closure.records),changed_abilities=len(closure.changes))
            report.update(prop_records=list(closure.props.values()),ability_records=list(closure.records.values()))
            (output/'blocked.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            raise ValueError(report)
        # Assert every prop edit is exactly the Model field, with no other byte edit.
        for identity,new in closure.prop_changes.items():
            left,right=spans[identity];q=batch.baked.MessagePackSpanReader(data);q.pos=left;node=q.node();field=node['children'][1]
            q=batch.baked.MessagePackSpanReader(new);nn=q.node();nf=nn['children'][1]
            assert data[left:field['start']]==new[:nf['start']]
            assert data[field['end']:right]==new[nf['end']:]
        result_prop=repack(prop_raw,closure.prop_changes)
        result_ability=repack(ability_raw,closure.changes)
        result_strings='\x1f'.join(strings).encode('utf-8')
        assert strings[:len(before_strings)]==before_strings
        files=[]
        for name,before,after in (('bakedpropdata',prop_raw,result_prop),('bakedabilitydata',ability_raw,result_ability),('stringmap.txt',string_raw,result_strings)):
            if before==after:continue
            (output/name).write_bytes(after)
            files.append(dict(name=name,before_sha256=monster.sha(before),sha256=monster.sha(after),bytes=len(after)))
        report=dict(status='prepared_human_pending',selected_props=len(selected),changed_props=len(closure.prop_changes),
            selected_abilities=len(closure.records),changed_abilities=len(closure.changes),
            aliases=closure.model_aliases,prop_records=list(closure.props.values()),
            ability_records=list(closure.records.values()),missing_original_prefabs=missing,
            new_string_count=len(strings)-len(before_strings),old_string_indices_unchanged=True,
            files=files,native_unchanged=True,save_unchanged=True)
        report.update(excluded_props=list(exclude_props),device_input=str(device),all_models=all_models)
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report


if __name__=='__main__':
    r=prepare();print(json.dumps({k:r[k] for k in ('selected_props','changed_props','selected_abilities','changed_abilities','new_string_count','missing_original_prefabs')}))
