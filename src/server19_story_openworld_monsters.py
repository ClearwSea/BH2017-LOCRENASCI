"""Repair named area-table monster variants and their actual ability closure."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import hashlib
import json
import zipfile
import server19_resources as resources
import server19_avatar_battle_resources as batch
import server19_chapter1_resources as ch
from server19_story_shield_bridge import ShieldClosure
from server19_story_fire_prop_runtime import repack
from server19_story_openworld_scope import area_monster_references

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'.local-baseline/server19-dev/story-all-20261015'


def prepare(monster_file,ability_file,stringmap_file,output):
    monster_file,ability_file,stringmap_file,output=map(Path,(monster_file,ability_file,stringmap_file,output))
    output.mkdir(exist_ok=False)
    strings=stringmap_file.read_text(encoding='utf8').split('\x1f');before_strings=strings.copy()
    scope=json.loads((WORK/'goal-six-chapters-20261016/openworld-scope.json').read_bytes())
    inventory={r['stage_id']:r for r in json.loads((WORK/'inventory.json').read_bytes())}
    rows=json.loads((batch.TABLES/'monsterconfigdata').read_bytes())
    refs=[];identities=set()
    for entry in scope['stages']:
        sid=entry['stage_id'];item=inventory[sid];raw=(WORK/'lua-source'/item['lua']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==entry['source_sha256']
        for ref in area_monster_references(raw.decode('utf-8-sig'),item['row']['hardLevel']):
            meta=next(r for r in rows if (r['monsterName'],r['typeName'])==(ref['monster'],ref['configType']))
            identity=(strings.index(meta['configFile']),None if meta['configType']=='Default' else strings.index(meta['configType']))
            base_identity=(strings.index(meta['configFile']),None)
            identities.add(identity);identities.add(base_identity)
            refs.append(dict(stage_id=sid,identity=identity,base_identity=base_identity,source_sha256=entry['source_sha256'],**ref))
    before=monster_file.read_bytes()
    candidate,records,errors=ch.project_monsters(before,identities,strings,output)
    assert not errors,errors
    ability_before=ability_file.read_bytes()
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        closure=ShieldClosure(package,strings,{r['path']:r for r in resources.resource_map(resources.DEFAULT19)},output)
        closure.before=ability_before;closure.data,closure.spans=batch.packed(ability_before)[3::2]
        for record in records:
            for identity in record['dependencies']:closure.project(tuple(identity))
        assert not closure.errors,closure.errors
        assert not closure.monster_refs, 'Additional summoned monsters require explicit closure'
        assert strings==before_strings
        ability_candidate=repack(ability_before,closure.changes)
        preserved={}
        for name,old,new in [('bakedmonsterdata',before,candidate),('bakedabilitydata',ability_before,ability_candidate)]:
            old_parts,new_parts=batch.packed(old),batch.packed(new)
            assert set(old_parts[5])==set(new_parts[5])
            changed=[];unchanged=0
            for identity,span in old_parts[5].items():
                if old_parts[3][slice(*span)]==new_parts[3][slice(*new_parts[5][identity])]:unchanged+=1
                else:changed.append(identity)
            preserved[name]=dict(changed=changed,unchanged_roots=unchanged,before_sha256=hashlib.sha256(old).hexdigest(),sha256=hashlib.sha256(new).hexdigest())
            (output/name).write_bytes(new)
        report=dict(status='PASS_area_monster_fix_human_pending',area_identities=len(identities),references=refs,
            monster_records=records,ability_records=list(closure.records.values()),preservation=preserved,
            StringMap_unchanged=True,human_acceptance='pending',gameplay_emulated=False)
        (output/'technical-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        return report


if __name__=='__main__':
    import sys
    r=prepare(*sys.argv[1:]);print(json.dumps(dict(status=r['status'],area_identities=r['area_identities'],ability_roots=len(r['ability_records']),preservation=r['preservation'])))
