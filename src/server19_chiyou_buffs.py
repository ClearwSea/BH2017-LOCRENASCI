"""Project the normal Chiyou random buff pool without changing buff values."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib,json,zipfile
from pathlib import Path
import server19_chapter1_resources as ch
import server19_avatar_battle_resources as batch
import server19_resources as resources
import server19_story_batch_resources as story
ROOT=Path(__file__).resolve().parent
CATEGORIES={1,2,3,4,31}

def ability_name(row):
    if row['buffId'] == 10007:
        assert row['abilityName'] == 'ExtraStory_Elite_Spboost'
        return 'ExtraStory_Elite_SPboost'
    return row['abilityName']

def active_ability_seeds(strings, spans):
    """Conservative closure of the registered Rogue active-effect family."""
    seeds = [key for key in spans if strings[key[0]].startswith('RogueActive_')]
    assert len(seeds) == 13
    return seeds

def buff_rows(tables):
    goods=json.loads((tables/'roguegoodsdata').read_bytes())
    ids={r['SubID'] for r in goods if r['Type']==2 and r['Category'] in CATEGORIES}
    rows=[r for r in json.loads((tables/'teambuffdata').read_bytes()) if r['buffId'] in ids]
    assert {r['buffId'] for r in rows}==ids and len(rows)==38
    return rows

def build(current,table_before,output):
    current,output=Path(current),Path(output);output.mkdir(exist_ok=True)
    strings=(current/'_baked/stringmap.txt').read_text().split('\x1f')
    original=json.loads(Path(table_before).read_bytes());rows=buff_rows(batch.TABLES)
    assert all(r in original for r in rows)
    fixes=[]
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        closure=ch.AbilityClosure(source,strings,{r['path']:r for r in resources.resource_map(resources.DEFAULT19)},output)
        closure.before=(current/'_baked/bakedabilitydata').read_bytes()
        closure.data,closure.spans=batch.packed(closure.before)[3::2]
        closure.prop_raw=(current/'_baked/bakedpropdata').read_bytes()
        closure.prop_data,closure.prop_spans=batch.packed(closure.prop_raw)[3::2]
        for row in rows:
            name=row['abilityName']
            if row['buffId']==10007:
                assert name=='ExtraStory_Elite_Spboost'
                assert (strings.index(name),None) not in closure.spans
                name='ExtraStory_Elite_SPboost'
                assert (strings.index(name),None) in closure.spans
                target=next(r for r in original if r['buffId']==10007)
                fixes.append(dict(buff_id=10007,before=target['abilityName'],after=name))
                target['abilityName']=name
            closure.project((strings.index(name),None))
        for key in active_ability_seeds(strings, closure.spans):
            closure.project(key)
        assert not closure.errors,closure.errors
        assert not closure.prop_changes and not closure.monster_refs, (list(closure.prop_changes),list(closure.monster_refs))
        # Exact-root reassembly checks every unselected root byte-for-byte.
        after=story.reassemble(closure.before,closure.changes)
        data,spans=batch.packed(after)[3::2]
        for identity in closure.records:
            left,right=spans[identity]
            reader=ch.ChapterReader(data[left:right],strings,closure.schema,True)
            reader.class_value(batch.ability.ABILITY,'ability')
            assert reader.pos==right-left
        (output/'bakedabilitydata').write_bytes(after)
        (output/'teambuffdata').write_text(json.dumps(original,ensure_ascii=False,separators=(',',':')),encoding='utf8')
        result=dict(status='PASS',buff_ids=[r['buffId'] for r in rows],roots_checked=len(closure.records),roots_changed=len(closure.changes),name_corrections=fixes,records=list(closure.records.values()),ability_before_sha256=hashlib.sha256(closure.before).hexdigest(),ability_after_sha256=hashlib.sha256(after).hexdigest(),table_before_sha256=hashlib.sha256(Path(table_before).read_bytes()).hexdigest(),table_after_sha256=hashlib.sha256((output/'teambuffdata').read_bytes()).hexdigest(),unselected_roots_unchanged=True,gameplay_terminals_retained=True,deployed=False,human_acceptance='pending')
        (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        return result

if __name__=='__main__':
    out=ROOT/'server19-run/chiyou-20261025'
    result=build(out/'candidate-v7',out/'buff-fix/teambuffdata.before',out/'buff-fixed-candidate')
    print('PASS',result['roots_checked'],'roots checked;',result['roots_changed'],'projected; 38 buff entries')
