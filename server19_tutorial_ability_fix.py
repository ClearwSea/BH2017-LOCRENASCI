"""Project observed mainline tutorial abilities without changing the save."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,zipfile
from pathlib import Path
import server19_chapter1_resources as c
import server19_avatar_battle_resources as b
import server19_resources as r
import server19_story_batch_resources as story

WORK=Path(__file__).resolve().parent/'.local-baseline/server19-dev/story-all-20261015'

def build():
    out=WORK/'tutorial-ability-fix-v1';out.mkdir(exist_ok=True)
    before=(WORK/'medal-closure-v1/bakedabilitydata').read_bytes()
    strings=(WORK/'candidate-v7/_baked/stringmap.txt').read_text(encoding='utf-8').split('\x1f')
    with zipfile.ZipFile(r.DEFAULT24) as package:
        cl=c.AbilityClosure(package,strings,{v['path']:v for v in r.resource_map(r.DEFAULT19)},out)
        cl.before=before;cl.data,cl.spans=b.packed(before)[3::2]
        seeds=[k for k in cl.spans if strings[k[0]].startswith('NewbieTutorial_')]
        for key in seeds:cl.project(key)
        assert len(seeds)==11 and not cl.errors and not cl.prop_changes and not cl.monster_refs
        assert (16012,None) in cl.changes
        after=story.reassemble(before,cl.changes)
        _,_,_,data,_,spans=b.packed(after)
        for key in cl.spans:
            old=cl.data[slice(*cl.spans[key])];new=data[slice(*spans[key])]
            assert new==cl.changes.get(key,old)
        for key in cl.records:
            left,right=spans[key];rd=c.ChapterReader(data,strings,cl.schema,True);rd.pos=left
            rd.class_value(b.ability.ABILITY,'ability');assert rd.pos==right
        (out/'bakedabilitydata').write_bytes(after)
        report={'status':'prepared_not_deployed','tutorial_roots':len(seeds),'changed_roots':len(cl.changes),
            'changes':[record for key,record in cl.records.items() if key in cl.changes],
            'observed':{'stage':10121,'team':[101,504,402],'key':16012,'name':'NewbieTutorial_EliteLimbo','offset':'0xec9ad','first_failure':'DynamicFloatFormatter reading a scalar event ID as an array'},
            'checks':'PASS: original consumer, exact boundaries, retained gameplay terminals, all unselected roots byte-identical',
            'save_changed':False,'native_library_changed':False,'shared_animation_changed':False,'human_acceptance':'pending'}
        (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'tutorial_roots':len(seeds),'changed_roots':len(cl.changes),'names':[strings[k[0]] for k in cl.changes]}))

if __name__=='__main__':build()
