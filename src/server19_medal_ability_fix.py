"""Repair complete medal ability closures from observed Sony decoder evidence."""

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
    out=WORK/'medal-closure-v1';out.mkdir(exist_ok=True)
    strings=(WORK/'candidate-v7/_baked/stringmap.txt').read_text(encoding='utf-8').split('\x1f')
    before=(WORK/'stage10116-fix-v1/bakedabilitydata').read_bytes()
    with zipfile.ZipFile(r.DEFAULT24) as z:
        cl=c.AbilityClosure(z,strings,{v['path']:v for v in r.resource_map(r.DEFAULT19)},out)
        cl.before=before;cl.data,cl.spans=b.packed(before)[3::2]
        seeds=[k for k in cl.spans if strings[k[0]].startswith('MedalSkill_')]
        for k in seeds:cl.project(k)
        def reachable(seed):
            seen=set();pending=[seed]
            while pending:
                key=pending.pop()
                if key in seen:continue
                seen.add(key);pending.extend(cl.records.get(key,{}).get('dependencies',[]))
            return seen
        complete=[];blocked=[];selected=set()
        for seed in seeds:
            chain=reachable(seed);fail=chain&set(cl.errors)
            if fail:blocked.append({'seed':seed,'name':strings[seed[0]],'errors':[{'identity':k,'reason':cl.errors[k]} for k in fail]})
            else:complete.append(seed);selected.update(chain)
        changes={k:v for k,v in cl.changes.items() if k in selected}
        assert (15120,None) in changes
        assert not cl.prop_changes and not cl.monster_refs
        after=story.reassemble(before,changes)
        _,_,_,data,_,spans=b.packed(after)
        for key in cl.spans:
            old=cl.data[slice(*cl.spans[key])];new=data[slice(*spans[key])]
            assert new==(changes[key] if key in changes else old)
        # All selected roots must pass actual original custom tail layout.
        for key in selected:
            left,right=spans[key];reader=c.ChapterReader(data,strings,cl.schema,True);reader.pos=left
            reader.class_value(b.ability.ABILITY,'ability');assert reader.pos==right
        (out/'bakedabilitydata').write_bytes(after)
        report={'status':'prepared_not_deployed','observed':{'root':15120,'name':'MedalSkill_AllDamageUp','packed_offset':'0x930f1','formatter':'CustomConfigModifierFormatter','field':'configLocalID'},
            'complete_medal_seeds':complete,'blocked_medal_seeds':blocked,
            'selected_roots':len(selected),'changed_roots':len(changes),
            'changes':[v for k,v in cl.records.items() if k in changes],
            'original_consumer_and_boundaries':'PASS','unselected_roots_byte_identical':True,
            'source':'2.4 compatibility data projected to original1.9; not historical1.9 source',
            'human_acceptance':'pending','device_operations':0}
        (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('selected_roots','changed_roots','original_consumer_and_boundaries')}))

if __name__=='__main__':build()
