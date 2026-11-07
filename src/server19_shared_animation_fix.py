"""Project the observed shared-animation nested14/13 mismatch, offline only.

Do not pad indexed tables: failing index247 is the next CameraShake field,
misread as AttackEffect after an extra later-only nil inside AttackPattern.
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
import json,zipfile,struct
from pathlib import Path
import server19_avatar_battle_resources as batch
import server19_chapter1_resources as chapter
import server19_resources as resources
import server19_story_batch_resources as story

WORK=Path(__file__).resolve().parent/'.local-baseline/server19-dev/story-all-20261015'

def build():
    out=WORK/'shared-animation-layout-v1';out.mkdir(exist_ok=True)
    before=(WORK/'index-caller-v1/device-bakedsharedanimeventdata').read_bytes()
    assert before==(resources.ROOT/'.local-baseline/server19-dev/baked-fallback/_baked/bakedsharedanimeventdata').read_bytes()
    strings=(WORK/'candidate-v7/_baked/stringmap.txt').read_text(encoding='utf-8').split('\x1f')
    _,_,_,data,_,spans=batch.packed(before)
    counts={}
    for field,name in [('AttackProperty','bakedconfigentityattackproperty'),('CameraShake','bakedconfigentitycamerashake'),('AttackEffect','bakedconfigentityattackeffect')]:
        p=WORK/'index-caller-v1'/('device-'+name)
        if not p.exists():p=WORK/'range-caller-v1'/('device-'+name)
        flag,hash_value,count=struct.unpack_from('<III',p.read_bytes());assert flag==1
        counts[field]=count
    changes={};records=[];consumption=[]
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        schema=chapter.ChapterSchema(package,strings)
        name='MoleMole.Config.TargetLockedAnimatedColliderDetect'
        old=schema.members(name,True);new=schema.members(name,False)
        assert len(old)==13 and len(new)==14 and new[12][0]=='FollowOwnerTimeScale' and new[13][0]=='Scale'
        assert [(k,schema.signature(p,True)) for k,p in old]==[(k,schema.signature(p,False)) for k,p in new[:12]+new[13:]]
        for key,(left,right) in spans.items():
            q=batch.baked.MessagePackSpanReader(data);q.pos=left;root=q.node();assert q.pos==right
            tag=batch.baked.decode_integer(data,root['children'][0]);event=root['children'][1]
            typename={1:'ConfigAvatarAnimEvent',2:'ConfigMonsterAnimEvent'}[tag]
            fields=[k for k,p in schema.members('MoleMole.Config.'+typename,False)]
            assert event['count']==len(fields)
            i=fields.index('AttackPattern');pattern=event['children'][i]
            if pattern['code']==0xc0:continue
            if batch.baked.decode_integer(data,pattern['children'][0])!=10:continue
            payload=pattern['children'][1];assert payload['count']==14
            extra=payload['children'][12];assert data[extra['start']:extra['end']]==b'\xc0'
            # Keep every retained child encoding, including the real Scale nil.
            projected=b'\x9d'+b''.join(data[n['start']:n['end']] for n in payload['children'][:12]+payload['children'][13:])
            value=data[left:payload['start']]+projected+data[payload['end']:right]
            changes[key]=value
            records.append({'identity':key,'name':strings[key[0]],'operation':'remove_later_nil_field',
                'field':'AttackPattern<TargetLockedAnimatedColliderDetect>.FollowOwnerTimeScale',
                'source_payload_fields':14,'target_payload_fields':13,'retained_child_encodings_equal':True})
            # Model the original fixed13-field reader, which does not skip
            # later entries just because the serialized header says14.
            for label,raw,base in [('before',data,left),('after',value,0)]:
                rd=batch.baked.MessagePackSpanReader(raw);rd.pos=base
                # Generic node locates header boundaries without consuming them.
                rd.pos=base;top=rd.node();evt=top['children'][1]
                rd.pos=evt['header_end'] if 'header_end' in evt else evt['start']+(3 if evt['code']==0xdc else 1)
                refs={}
                for index,field in enumerate(fields):
                    if field=='AttackPattern':
                        union=rd.node();body=union['children'][1]
                        rd.pos=body['start']+(3 if body['code']==0xdc else 1)
                        for _ in range(13):rd.node()
                    else:
                        node=rd.node()
                        if field in counts:refs[field]=None if node['code']==0xc0 else batch.baked.decode_integer(raw,node)
                end=rd.pos
                invalid={k:v for k,v in refs.items() if v is not None and not 0<=v<counts[k]}
                if label=='after':assert end==len(value) and not invalid,(key,refs,invalid)
                consumption.append({'identity':key,'name':strings[key[0]],'version':label,'references':refs,'outside_tables':invalid,'root_end_matches':end==(right if label=='before' else len(value))})
    assert len(changes)==11
    after=story.reassemble(before,changes)
    _,_,_,check_data,_,check_spans=batch.packed(after)
    for key,(l,r) in spans.items():
        cl,cr=check_spans[key]
        assert check_data[cl:cr]==changes.get(key,data[l:r])
    observed=next(x for x in consumption if x['identity']==(382,None) and x['version']=='before')
    assert observed['references']=={'AttackProperty':None,'CameraShake':140,'AttackEffect':247}
    (out/'bakedsharedanimeventdata').write_bytes(after)
    report={'status':'prepared_not_deployed','changed_roots':len(changes),'all_roots':len(spans),
        'unselected_roots_byte_identical':True,'records':records,'original_fixed_field_consumption':consumption,
        'table_counts':counts,'indexed_tables_changed':False,'native_library_changed':False,'save_changed':False,
        'checks':'PASS: exact same-type13/14 declaration projection; retained values; original field consumption and root boundaries; indexed ranges',
        'limits':'Scoped nested-layout check; human weapon activation, dialogue and WIN remain pending'}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'changed_roots':len(changes),'all_roots':len(spans),'observed_before':observed['references'],'observed_after':next(x['references'] for x in consumption if x['identity']==(382,None) and x['version']=='after')}))

if __name__=='__main__':build()
