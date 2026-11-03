"""Prepare the next story batch from the latest accepted Sony resource lineage."""

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
import shutil
from pathlib import Path

import server19_story_all_resources as story
import server19_stage as stage
import server19_avatar_battle_resources as batch


def prepare(version='followup-candidate-v2'):
    work = story.WORK
    current = work/'followup-current'
    sources = {
        '_baked/bakedabilitydata': work/'tutorial-ability-fix-v1/bakedabilitydata',
        '_baked/bakedmonsterdata': work/'candidate-v7/_baked/bakedmonsterdata',
        '_baked/bakedpropdata': work/'candidate-v7/_baked/bakedpropdata',
        '_baked/stringmap.txt': work/'candidate-v7/_baked/stringmap.txt',
        '_exceloutputasset/npclevellogic': work/'candidate-v7/_exceloutputasset/npclevellogic'}
    for name, source in sources.items():
        destination = current/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    inventory = json.loads((work/'inventory.json').read_bytes())
    config = next(r['row'] for r in inventory if r['stage_id'] == 10205)
    unique = next(r for r in json.loads((batch.TABLES/'uniquemonsterdata').read_bytes()) if r['uniqueID'] == 32)
    npc = next(r for r in json.loads(sources['_exceloutputasset/npclevellogic'].read_bytes()) if r['HardLevel'] == config['hardLevel'])
    monster = next(r for r in json.loads((batch.TABLES/'monsterconfigdata').read_bytes()) if (r['monsterName'], r['typeName']) == ('UlyssesDefend', unique['typeName']))
    assert (config['hardLevel'], config['UseDynamicHardLv'], unique['configType']) == (14, 0, 'Unique01')
    assert (monster['HP'], npc['HPRatio'], unique['HPRatio']) == (1640, 1.757, 4)
    text = (work/'lua-source/lua/levels/mainline_stage02/level 2-5.lua').read_text(encoding='utf-8-sig')
    tokens = story.lua.lua_tokens(text)
    assert any(t[0] == 'uniqueID' and tokens[i+1][0] == '=' and tokens[i+2][0] == '32' for i,t in enumerate(tokens[:-2]))
    assert not any(t[0].strip('"\'') in ('set_monster_hp_ratio', 'hpRatio', 'HPRatio') for t in tokens)
    shield = monster['HP'] * npc['HPRatio'] * unique['HPRatio'] * .15
    assert shield < 1800
    proof = {'stage_id': 10205, 'unique_id': 32, 'base_hp': monster['HP'], 'npc_ratio': npc['HPRatio'],
             'unique_hp_ratio': unique['HPRatio'], 'shield_ratio': .15, 'shield_value': shield,
             'source_cap': 1800, 'cap_nonbinding': True, 'dynamic_hard_level': False,
             'source_lua_sha256': hashlib.sha256(text.encode()).hexdigest()}
    report = story.prepare(version, current=current, bounded_shields={(15671,21836): proof, (15671,7888): proof})
    out = work/version
    (out/'shield-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    ready = json.loads((work/'runtime-ready.json').read_bytes())
    ready.update(ready_stage_ids=report['ready_stage_ids'], deployed=False, followup_version=version)
    rows = [r for r in stage._table('stagedata_main') if r['levelId'] in ready['ready_stage_ids']]
    ready['source_rows_sha256'] = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    (work/'followup-runtime-ready.json').write_text(json.dumps(ready, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    result = prepare()
    print(json.dumps({'ready': len(result['ready_stage_ids']), 'blocked': len(result['blocked_stage_ids'])}))
