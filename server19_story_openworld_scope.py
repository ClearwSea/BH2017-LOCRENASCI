"""Execute source metadata/init flow to bound Normal-story dynamic imports.

No gameplay emulation: required modules are recorded, not substituted in game.
Unknown native calls fail. The emitted proof is tied to all source hashes.
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
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from server19_story_all_resources import ROOT, WORK, batch
import server19_resources as resources
from server19_stage_resources import text_record


def sha(raw):return hashlib.sha256(raw).hexdigest()


def area_monster_references(text, hard_level):
    """Read literal named area tables and shared openworld_areaconfigcommon branches."""
    sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
    from lupa import LuaRuntime
    package={r['path']:r for r in resources.resource_map(resources.DEFAULT24)}
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        common_raw,_=text_record(source,package['lua/base/openworld_areaconfigcommon.lua'],'2.4')
        common_text=common_raw.decode('utf-8-sig')
    prelude=(
        'level={}; mobile_defend={}; OWCommonConfig={bgm_config={}}; LevelDesign={}; '
        'function require(x) return {} end; function print(...) end; '
        'function inspect(x) return "metadata inspection" end; '
        'function table_copy_table(t) if type(t)~="table" then return t end '
        'local r={} for k,v in pairs(t) do r[k]=table_copy_table(v) end return r end'
    )
    custom_found=set()
    common_found=set()
    def visit(table,target):
        if not hasattr(table,'items'):return
        name,variant=table['name'],table['configType']
        if isinstance(name,str) and isinstance(variant,str):target.add((name,variant))
        for _,value in table.items():
            if hasattr(value,'items'):visit(value,target)
    for cycle in (1,2,3,4):
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute(prelude)
        lua.globals().LevelDesign.GetNPCHardLevel=lambda self:hard_level
        def set_cycle(self,target,c=cycle):
            target['Cycle']=c
        lua.globals().LevelDesign.GetOpenWorldParam=set_cycle
        lua.execute(text)
        visit(lua.globals()['_custom_monster_config'],custom_found)
        lua.execute(common_text)
        visit(lua.globals().OWCommonConfig['area_config'],common_found)
    result=[{'monster':name,'configType':variant,
             'source':'_custom_monster_config' if (name,variant) in custom_found else 'openworld_areaconfigcommon'}
            for name,variant in sorted(custom_found|common_found)]
    return result


def prepare(output):
    sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
    from lupa import LuaRuntime
    inventory=[r for r in json.loads((WORK/'inventory.json').read_bytes()) if r['chapter'] in (5,6)]
    mapped=json.loads((batch.TABLES/'stagedata_storymapped').read_bytes())
    story=json.loads((batch.TABLES/'stagedata_story').read_bytes())
    metadata={r['StoryID']:r for r in story}
    package={r['path']:r for r in resources.resource_map(resources.DEFAULT24)}
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        event_raw,_=text_record(source,package['lua/base/openworldeventdesign.lua'],'2.4')
        mission_raw,_=text_record(source,package['lua/base/owmissioncommon.lua'],'2.4')
        records=[];all_imports=set()
        for item in inventory:
            raw=(WORK/'lua-source'/item['lua']).read_bytes();text=raw.decode('utf-8-sig')
            lua=LuaRuntime(unpack_returned_tuples=True)
            lua.execute('level={}; mobile_defend={}; OWCommonConfig={bgm_config={}}; LevelDesign={}; function require(x) return {} end; function print(...) end; function inspect(x) return "metadata inspection" end')
            # These are the only native reads permitted during root-table
            # construction. This does not verify combat or dynamic HP scaling.
            lua.globals().LevelDesign.GetNPCHardLevel=lambda self:item['row']['hardLevel']
            lua.execute(text)
            data=lua.globals().level['leveldata']
            assert data is not None and data['area_eventID_list'] is None and data['area_questID_list'] is None,item['stage_id']
            questids=next((r['questID'] for r in mapped if r['levelID']==item['stage_id']),[])
            assert set(questids)<=set(metadata)
            def stage_missions(self,target):
                # Both empty and populated native lists must resolve safely;
                # use all mapped source missions, without assuming save status.
                for i,q in enumerate(questids,1):target[i]=lua.table_from({'metaData':lua.table_from(metadata[q])})
            lua.globals().LevelDesign.GetStageStoryMissionList=stage_missions
            lua.execute(event_raw.decode('utf-8-sig'))
            imported=[]
            def record(name):
                assert isinstance(name,str)
                path='lua/'+name.lower()+'.lua';assert path in package,path
                imported.append(path);return lua.table()
            lua.globals().require=record
            lua.globals().level['event_init']()
            all_imports.update(imported)
            assert not re.search(r'mission\s*(?:\.|:)\s*create_mission\s*\(',text)
            assert 'CreateMission' not in text
            fake_names=re.findall(r'\bavatarRegistry\s*=\s*[\'"]([A-Za-z0-9_]+)[\'"]',text)
            if fake_names:
                assert 'dressDesc' not in text
            records.append({'stage_id':item['stage_id'],'path':item['lua'],'source_sha256':sha(raw),
                            'area_event_and_quest_lists':None,'mapped_missions':questids,
                            'fake_avatar_registries_no_dress_override':fake_names,
                            'actual_event_init_imports':imported,
                            'area_monster_references':area_monster_references(text,item['row']['hardLevel'])})
        # Shared modules must not introduce new quest/event list assignments or
        # call the deferred generic mission loader from another function.
        previous=json.loads((Path(output).parent/'chapters5-6-audit-v4/manifest.json').read_bytes())
        module_hashes={}
        proof_modules={r['path']:r for r in previous['modules']}
        proof_modules.update({p:{'path':p} for p in all_imports})
        for module in proof_modules.values():
            if module['path'] not in package:continue
            raw,_=text_record(source,package[module['path']],'2.4');text=raw.decode('utf-8-sig')
            assert not re.search(r'\barea_(?:event|quest)ID_list\s*=',text),module['path']
            if module['path']=='lua/base/leveldesignopenworld.lua':
                forwarder=r'level\["CreateMission"\]\s*=\s*function\(par\)\s*mission\.create_mission\(par\.id\)\s*end'
                text,count=re.subn(forwarder,'',text)
                assert count==1
            assert not re.search(r'mission\s*(?:\.|:)\s*create_mission\s*\(',text),module['path']
            assert 'CreateMission' not in text,module['path']
            module_hashes[module['path']]=sha(raw)
    report={'status':'PASS_scoped_dependency_flow_only','stage_ids':[r['stage_id'] for r in records],
            'stages':records,'module_source_sha256':module_hashes,
            'event_module_sha256':sha(event_raw),'mission_module_sha256':sha(mission_raw),
            'event_init_dependencies':sorted(all_imports),
            'generic_mission_loader':'defined but no source calls in selected roots/shared closure',
            'gameplay_verified':False,'native_calls_mocked':['GetNPCHardLevel','GetStageStoryMissionList','GetOpenWorldParam'],
            'tables_sha256':{n:sha((batch.TABLES/n).read_bytes()) for n in ('stagedata_story','stagedata_storymapped')}}
    Path(output).write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    out=WORK/'goal-six-chapters-20261016/openworld-scope.json'
    r=prepare(out);print(json.dumps({'status':r['status'],'stages':len(r['stages']),'dependencies':r['event_init_dependencies']}))
