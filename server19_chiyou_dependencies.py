"""Bounded, read-only expansion of pinned Chiyou dynamic Lua references.

Only the audit representation expands; delivered Lua and random selection stay
byte-identical. Changed sources require a fresh call-site review.
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
import re
from copy import deepcopy

STAGES = {
    211114: '91a6783f45668c1bd86ef9f2ebba248f10319b149bd2f5ebb901cbb442624fae',
    211116: 'c7da958d8e06287569ece5913d3f84de1861e7c90c100538defb68f4006e1687',
    211117: '472619c73b7248474d521cf38b10a0f7734a3c5aff13e549a386bf7fc102e24c',
}
COMMON_SHA = 'de4863cb91e4e3a6e07f326c5f37e382aa860288cd4da76ad57a97fc97abe8b3'
EXPRESSION = 'roguecommon.uniquemonsters[math.random(#roguecommon.uniquemonsters)]'


def unused_debuff_callback(module_raw, table_raw):
    """Evidence for the supplied metadata, not a global missing-name allowlist.

    GetRogueTeamDebuffList65753 reads LevelScoreManager.rogueDebuffList;
    SetRogueLevelBeginIntent69227 receives it from Armada preparation callers.
    RogueModule.GetCurrentDebuffList70493 selects metadata table entries.
    The supplied table contains only triggerType1, so the Lua callback branch
    in LevelDesignRogue cannot select this callback from that table.
    """
    import json
    if hashlib.sha256(module_raw).hexdigest() != '84333cb7f2fdbca6fb285a6e31a62fd9a1361b79d0cd9f5f471034d87ae9bf11':
        return None
    if hashlib.sha256(table_raw).hexdigest() != '1f3e13b80bc933f55fe5ea56ae6da1477545a95d00edd7d7b15d7be779f6f32a':
        return None
    rows=json.loads(table_raw)
    assert len(rows)==16 and all(r['triggerType']==1 for r in rows)
    return dict(ability='RogueDebuff_ClearSP',reason='No Lua callback selection in pinned metadata',
                native_methods=[65753,69227,70493],native_callers=[77511,77553,77544],
                metadata_sha256=hashlib.sha256(table_raw).hexdigest(),
                original_script_retained=True,scope='Chiyou Normal211101–211118 only')


def check_source(stage_id, raw):
    if hashlib.sha256(raw).hexdigest() != STAGES[stage_id]:
        raise ValueError('Chiyou bounded source changed; review required')


def ability_references(stage_id, raw, text):
    from server19_story_wave_abilities import references
    if stage_id != 211114:
        return references(text)
    check_source(stage_id, raw)
    unresolved = []
    result = references(text, unresolved=unresolved)
    assert len(unresolved) == 3 and all(r['command']=='add_ability' and
        r['expression']=='par' for r in unresolved)
    names = re.findall(r'\{"Func", "addability_to_others", par = "([A-Za-z0-9_]+)"\}', text)
    assert names == ['RogueBattle_ElementFire','RogueBattle_ElementIce','Elite_ElementThunder']
    result.extend(dict(ability=name, source='pinned_Func_parameter_call_sites',
                       line=text[:text.index('par = "'+name+'"')].count('\n')+1)
                  for name in names)
    return result


def expand_monster_waves(stage_id, raw, text, waves, common_raw):
    if stage_id not in (211116,211117):
        return waves
    check_source(stage_id, raw)
    if hashlib.sha256(common_raw).hexdigest() != COMMON_SHA:
        raise ValueError('Chiyou random pool changed; review required')
    common = common_raw.decode('utf-8-sig')
    match = re.search(r'roguecommon.uniquemonsters\s*=\s*\{([0-9,]+)\}', common)
    pool = [int(x) for x in match[1].split(',')]
    assert len(pool)==len(set(pool))==34
    result=[];expanded=0
    for wave in waves:
        if 'audit_source_module' in wave:
            result.append(wave);continue
        line=text.splitlines()[wave['line']-1]
        if 'uniqueID = '+EXPRESSION not in line:
            result.append(wave);continue
        expanded+=1
        for identity in pool:
            item=deepcopy(wave)
            item['audit_unique_id']=identity
            item['audit_dynamic_expression']=EXPRESSION
            result.append(item)
    assert expanded==3, 'Random wave count changed'
    return result


def shared_monster_waves(modules, monster_names, stage_text=None):
    """Conservative union of shared wave templates; never execute Lua."""
    import server19_stage_resources as lua
    if stage_text is not None:
        for name,digest in {
            'roguebattleextend':'b6f63aed0c7a6a75edce2bacc8e13d757f043a0d49386e83b4ab740649951369',
            'roguebattle':'a1dcf88edf8671686e5364d3593ac83b0e962d95838c8e80d12f4237d60eadfc',
            'roguepreset':'7176148a82ffe6d223ecf4c2aafe83972ee9e94db9dfcb365c5a77e996a182e5',
        }.items():
            if hashlib.sha256(modules['lua/base/roguebase/'+name+'.lua']).hexdigest()!=digest:
                raise ValueError('Rogue dispatcher evidence changed')
    common=modules['lua/base/roguebase/roguecommon.lua'].decode('utf-8-sig')
    pool=[int(x) for x in re.search(r'roguecommon.uniquemonsters\s*=\s*\{([0-9,]+)\}',common)[1].split(',')]
    result=[];unresolved=[]
    for path,raw in modules.items():
        text=raw.decode('utf-8-sig')
        for wave in lua.normal_monster_waves(text,monster_names):
            if stage_text is not None and path.endswith('/roguebattleextend.lua'):
                prefix='\n'.join(text.splitlines()[:wave['line']])
                functions=re.findall(r'^function\s+(\w+)\(',prefix,re.M)
                # These two dispatch entries are601/610; the Normal source has
                # neither entry nor the endless/override path that adds them.
                atoms={t[0] for t in lua.lua_tokens(stage_text)}
                if (functions and functions[-1] in ('rogue_Hell_DA','rogue_Hell_DAwithElite')
                        and not atoms & {'601','610','endlessmode','override_name'}):
                    continue
            tail='\n'.join(text.splitlines()[wave['line']-1:])
            wave.update(audit_source_tail=tail,audit_source_module=path)
            line=tail.splitlines()[0]
            dynamic=re.search(r'uniqueID\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\[math.random\(#\1\)\]',line)
            if not dynamic:
                result.append(wave);continue
            name=dynamic[1]
            literals=re.findall(r'\b'+re.escape(name)+r'\s*=\s*\{\s*([0-9,\s]+)\}',text)
            values={int(x) for value in literals for x in re.findall(r'\d+',value)}
            if re.search(r'\b'+re.escape(name)+r'\s*=\s*roguecommon.uniquemonsters\b',text):
                values.update(pool)
            if not values:
                unresolved.append(dict(path=path,line=wave['line'],expression=dynamic[0]));continue
            for identity in sorted(values):
                item=deepcopy(wave);item['audit_unique_id']=identity
                result.append(item)
    return result,unresolved
