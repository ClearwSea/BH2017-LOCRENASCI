"""Read-only packed-root index and epoch log correlation for batch acceptance.

Supply the *actual deployed* four containers and their StringMap. Root offsets
refer to the packed byte[] payload, never to the enclosing file. A decoder error
without a same-PID/TID trace is unmapped, even if its stack resembles an old error.
Static matrix associations describe references, not proven runtime activation.
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
from pathlib import Path
import argparse
from collections import defaultdict
import hashlib
import json
import re
import struct

KINDS = {1:'bakedabilitydata', 2:'bakedmonsterdata', 3:'bakedavatardata', 4:'bakedweapondata'}
EPOCH = re.compile(r'^\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^:]+):\s*(.*)$')
TRACE = re.compile(r'BH3SERVER19_DECODE kind=(\d+) offset=(\d+) length=(\d+) header=([0-9a-fA-F]+) caller=([0-9a-fA-F]+)')
OTHER_ERROR = re.compile(r'Exception|\b(?:LuaError|LuaException|ERROR|FATAL)\b|(?:resource|asset|file).*(?:missing|not found)|(?:missing|not found).*(?:resource|asset|file)', re.I)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def input_record(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}


def unpack_container(raw):
    """Exact existing non-indexed packed container layout, no generic serializer."""
    if len(raw)<20:raise ValueError('Truncated packed container')
    indexed,packed_hash=struct.unpack_from('<II',raw)
    if indexed!=0:raise ValueError('Only original non-indexed root containers are supported')
    pos=8;arrays=[]
    for size in (8,12,1):
        if pos+4>len(raw):raise ValueError('Truncated array count')
        count=struct.unpack_from('<I',raw,pos)[0];pos+=4;end=pos+count*size
        if end>len(raw):raise ValueError('Array exceeds container')
        arrays.append(raw[pos:end]);pos=end
    if pos!=len(raw):raise ValueError('Unexpected container trailing bytes')
    entries=list(struct.iter_unpack('<II',arrays[0]))
    overrides=list(struct.iter_unpack('<III',arrays[1]))
    roots=[(key,None,offset) for key,offset in entries]+[(key,variant,offset) for key,variant,offset in overrides]
    offsets=[x[2] for x in roots]
    if not offsets or min(offsets)!=0 or len(set(offsets))!=len(offsets) or max(offsets)>=len(arrays[2]):
        raise ValueError('Root offsets must be distinct and bounded, beginning at zero')
    if len(set((x[0],x[1]) for x in roots))!=len(roots):raise ValueError('Duplicate root identity')
    return packed_hash,roots,arrays[2]


def matrix_associations(matrix):
    result=defaultdict(list)
    for section,identity in (('items','item_id'),('sets','set_id'),('avatars','avatar_id'),('props','key')):
        for owner in matrix.get(section,[]):
            owner_ref={'source':'equipment_matrix','section':section,'id':owner.get(identity)}
            if section=='items' and owner.get('kind')=='weapon':
                result[(4,owner['item_id'],None)].append(owner_ref)
            if section=='avatars':result[(3,owner['avatar_id'],None)].append(owner_ref)
            for field in ('skills','dependencies','abilities'):
                for dependency in owner.get(field,[]):
                    if not isinstance(dependency.get('key'),int):continue
                    ref={**owner_ref,'field':field}
                    for key in ('skill_id','required_pieces','scope','slot','registry_root_sha256'):
                        if key in dependency:ref[key]=dependency[key]
                    result[(1,dependency['key'],dependency.get('variant'))].append(ref)
    return result


def build_index(containers,string_map,equipment_matrix=None,stage_manifest=None):
    """containers maps kind 1..4 to explicit candidate/deployed file paths."""
    if set(containers)!=set(KINDS):raise ValueError('Register all four explicit root containers')
    string_path=Path(string_map);strings=string_path.read_text(encoding='utf-8').split('\x1f')
    inputs={'string_map':input_record(string_path)};assoc=defaultdict(list)
    if equipment_matrix:
        inputs['equipment_matrix']=input_record(equipment_matrix)
        assoc.update(matrix_associations(read_json(equipment_matrix)))
    stage_refs=[]
    if stage_manifest:
        inputs['stage_manifest']=input_record(stage_manifest)
        manifest=read_json(stage_manifest)
        for stage in manifest.get('chapter1_normal_inventory',[]) + manifest.get('chapter1_remaining_inventory',[]):
            for kind,field in ((2,'monster_identities'),(1,'ability_seeds')):
                for key,variant in stage.get(field,[]):
                    assoc[(kind,key,variant)].append({'source':'stage_manifest',
                        'stage_id':stage['stage_id'],'field':field})
            for wave in stage.get('normal_monster_waves',[]):
                stage_refs.append((2,wave['monster'],{'source':'stage_manifest','stage_id':stage['stage_id'],
                    'field':'normal_monster_waves','config_type':wave.get('configType'),'line':wave.get('line')}))
                for ability in wave.get('explicit_attributes',[]):
                    stage_refs.append((1,ability,{'source':'stage_manifest','stage_id':stage['stage_id'],
                        'field':'explicit_attributes','line':wave.get('line')}))
            for call in stage.get('native_calls',[]):
                if call.get('method') not in ('HasAbility','SetAbilitySpecials','ApplyAbility','AddAbility'):continue
                args=call.get('arguments',[])
                if args and re.fullmatch(r'["\'][^"\']+["\']',args[0].strip()):
                    stage_refs.append((1,args[0].strip()[1:-1],{'source':'stage_manifest','stage_id':stage['stage_id'],
                        'field':'native_calls','method':call['method'],'line':call.get('line')}))
    named=defaultdict(list)
    for kind,name,ref in stage_refs:named[(kind,name)].append(ref)
    registered=[]
    for kind,path in sorted(containers.items()):
        path=Path(path).resolve()
        if path.name!=KINDS[kind]:raise ValueError('Container name disagrees with registered native kind')
        raw=path.read_bytes();packed_hash,roots,packed=unpack_container(raw)
        ordered=sorted(roots,key=lambda row:row[2]);rows=[]
        for index,(key,variant,start) in enumerate(ordered):
            end=ordered[index+1][2] if index+1<len(ordered) else len(packed)
            if kind in (1,2):
                name=strings[key] if 0<=key<len(strings) else 'unresolved_stringmap_key:'+str(key)
            else:name=('avatar:' if kind==3 else 'weapon:')+str(key)
            refs=assoc.get((kind,key,variant),[])+named.get((kind,name),[])
            # Multiple waves may reference one root: collapse only identical references.
            refs=list({json.dumps(ref,sort_keys=True):ref for ref in refs}.values())
            root_hash=sha(packed[start:end])
            refs=[{**ref,'matrix_root_hash_matches':ref['registry_root_sha256']==root_hash}
                  if 'registry_root_sha256' in ref else ref for ref in refs]
            rows.append({'key':key,'variant':variant,'name':name,'packed_span':[start,end],
                         'root_sha256':root_hash,'associations':refs})
        registered.append({'kind':kind,'container':KINDS[kind],'path':str(path),
            'container_bytes':len(raw),'container_sha256':sha(raw),'source_packed_hash':packed_hash,
            'packed_length':len(packed),'packed_sha256':sha(packed),'roots':rows})
    return {'format':'server19-packed-root-diagnostic-index-v1','inputs':inputs,'containers':registered,
            'association_scope':'Static explicit references only; not runtime activation or historical equivalence',
            'mapping_contract':'same PID/TID preceding trace + exact registered packed length + bounded root span'}


def parse_line(raw,line_number):
    found=EPOCH.match(raw)
    if not found:return None
    epoch,pid,tid,level,tag,message=found.groups()
    return {'epoch':float(epoch),'pid':int(pid),'tid':int(tid),'level':level,'tag':tag.strip(),
            'message':message,'line':line_number,'raw':raw.rstrip('\r\n')}


def map_trace(index,event):
    containers=[x for x in index['containers'] if x['kind']==event['kind']]
    if len(containers)!=1:return None,'unknown_or_ambiguous_kind'
    container=containers[0]
    if event['length']!=container['packed_length']:return None,'packed_length_mismatch'
    roots=[row for row in container['roots'] if row['packed_span'][0]<=event['offset']<row['packed_span'][1]]
    if len(roots)!=1:return None,'offset_outside_root_span'
    return {'kind':event['kind'],'container':container['container'],
            'container_sha256':container['container_sha256'],'packed_sha256':container['packed_sha256'],
            'root':roots[0]},None


def analyze_lines(index,lines,*,trace_window_seconds=5.0,context_limit=40):
    latest={};traces=[];errors=[];other=[];other_total=0
    for number,raw in enumerate(lines,1):
        event=parse_line(raw,number)
        if event is None:
            if 'BH3SERVER19_MSGPACK' in raw:
                errors.append({'line':number,'raw':raw.rstrip(),'status':'unmapped','reason':'missing_epoch_pid_tid'})
            elif OTHER_ERROR.search(raw):
                other_total+=1
                if len(other)<context_limit:other.append({'line':number,'raw':raw.rstrip(),'context':'no_epoch_pid_tid'})
            continue
        identity=(event['pid'],event['tid']);found=TRACE.search(event['message'])
        if found:
            kind,offset,length,header,caller=found.groups()
            trace={**event,'kind':int(kind),'offset':int(offset),'length':int(length),
                   'header':int(header,16),'caller':caller.lower()}
            latest[identity]=trace;traces.append(trace)
        elif 'BH3SERVER19_MSGPACK' in event['message']:
            trace=latest.pop(identity,None)
            row={**event,'status':'unmapped','reason':'missing_same_pid_tid_trace'}
            if trace:
                row['trace']=trace;age=event['epoch']-trace['epoch'];row['trace_age_seconds']=age
                if not 0<=age<=trace_window_seconds:row['reason']='trace_outside_time_window'
                else:
                    mapping,reason=map_trace(index,trace)
                    if mapping:row.update(status='mapped',mapping=mapping);row.pop('reason',None)
                    else:row['reason']=reason
            errors.append(row)
        elif OTHER_ERROR.search(event['message']):
            other_total+=1
            if len(other)<context_limit:other.append(event)
    groups=defaultdict(list)
    for error in errors:
        mapping=error.get('mapping')
        identity=(mapping['kind'],mapping['root']['key'],mapping['root']['variant']) if mapping else None
        key=json.dumps([error.get('pid'),error.get('tid'),identity,error.get('reason')])
        groups[key].append(error)
    return {'format':'server19-batch-error-report-v1','trace_window_seconds':trace_window_seconds,
        'trace_count':len(traces),'traces':traces,'decoder_error_count':len(errors),
        'mapped_count':sum(x['status']=='mapped' for x in errors),'errors':errors,
        'groups':[{'pid':rows[0].get('pid'),'tid':rows[0].get('tid'),'status':rows[0]['status'],
                   'count':len(rows),'error_lines':[x['line'] for x in rows],
                   'root':rows[0].get('mapping',{}).get('root'),'reason':rows[0].get('reason')} for rows in groups.values()],
        'other_error_line_count':other_total,'other_error_lines':other,
        'other_lines_truncated':max(0,other_total-len(other)),
        'limits':['No trace means unmapped; old native source addresses never substitute for a root trace',
                  'Each trace is consumed by the first subsequent same-PID/TID MsgPack diagnostic',
                  'Length binds to the supplied registry; log does not itself carry a container hash',
                  'Root localization is diagnostic evidence, not proof of the precise failing field']}


def write_report(path,report):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def self_check(index,legacy_log,output):
    """Small combined regression using a real registry root plus explicit synthetic log."""
    legacy_path=Path(legacy_log)
    legacy=analyze_lines(index,legacy_path.read_text(encoding='utf-8',errors='replace').splitlines())
    assert legacy['decoder_error_count'] and legacy['trace_count']==0 and legacy['mapped_count']==0
    ability=next(x for x in index['containers'] if x['kind']==1)
    root=next(x for x in ability['roots'] if x['key']==10880 and x['variant'] is None)
    assert any(x.get('skill_id')==65 for x in root['associations'])
    offset=root['packed_span'][0];length=ability['packed_length'];lines=[]
    for pid,tid,delta in ((100,11,0),(100,12,1),(101,11,2)):
        lines.extend([f'1791795687.{delta} {pid} {tid} I Unity : BH3SERVER19_DECODE kind=1 offset={offset} length={length} header=96 caller=0154e58c',
                      f'1791795687.{delta+1} {pid} {tid} I Unity : BH3SERVER19_MSGPACK source0=00518de0'])
    lines.extend(['1791795687.5 100 11 I Unity : BH3SERVER19_MSGPACK source0=00518de0',
        f'1791795687.6 100 12 I Unity : BH3SERVER19_DECODE kind=1 offset={offset} length={length+1} header=96 caller=0154e58c',
        '1791795687.7 100 12 I Unity : BH3SERVER19_MSGPACK source0=00518de0',
        f'1791795687.8 100 13 I Unity : BH3SERVER19_DECODE kind=1 offset={length} length={length} header=ff caller=0154e58c',
        '1791795687.9 100 13 I Unity : BH3SERVER19_MSGPACK source0=00518de0',
        '1791795688.0 100 14 E Unity : LuaException missing resource foo'])
    synthetic=analyze_lines(index,lines)
    assert synthetic['mapped_count']==3 and len(synthetic['groups'])==6 and synthetic['other_error_line_count']==1
    assert {x['reason'] for x in synthetic['errors'] if x['status']=='unmapped'}=={
        'missing_same_pid_tid_trace','packed_length_mismatch','offset_outside_root_span'}
    assert all(any(a.get('skill_id')==65 for a in e['mapping']['root']['associations'])
               for e in synthetic['errors'] if e['status']=='mapped')
    output=Path(output);write_report(output/'legacy-unmapped.json',legacy)
    write_report(output/'synthetic-threads.json',synthetic)
    (output/'synthetic-threads.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    report={'status':'PASS','legacy_log':input_record(legacy_path),'legacy_mapped':legacy['mapped_count'],
            'synthetic_mapped':synthetic['mapped_count'],'synthetic_groups':len(synthetic['groups']),
            'actual_root65':root,'no_device_account_server_operations':True}
    write_report(output/'verification.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    index=commands.add_parser('index')
    for option in ('ability','monster','avatar','weapon','string-map'):index.add_argument('--'+option,type=Path,required=True)
    index.add_argument('--equipment-matrix',type=Path);index.add_argument('--stage-manifest',type=Path)
    index.add_argument('--output',type=Path,required=True)
    analysis=commands.add_parser('analyze');analysis.add_argument('--index',type=Path,required=True)
    analysis.add_argument('--log',type=Path,required=True);analysis.add_argument('--output',type=Path,required=True)
    analysis.add_argument('--trace-window-seconds',type=float,default=5.0)
    analysis.add_argument('--context-limit',type=int,default=40)
    check=commands.add_parser('self-check');check.add_argument('--index',type=Path,required=True)
    check.add_argument('--legacy-log',type=Path,required=True);check.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='index':
        report=build_index({1:args.ability,2:args.monster,3:args.avatar,4:args.weapon},args.string_map,
                           args.equipment_matrix,args.stage_manifest)
        summary={'containers':len(report['containers']),'roots':sum(len(x['roots']) for x in report['containers'])}
    elif args.command=='analyze':
        if args.trace_window_seconds<=0 or args.context_limit<0:parser.error('Use positive trace window and nonnegative context limit')
        with args.log.open(encoding='utf-8',errors='replace') as lines:
            report=analyze_lines(read_json(args.index),lines,trace_window_seconds=args.trace_window_seconds,context_limit=args.context_limit)
        report['log_input']=input_record(args.log);report['index_input']=input_record(args.index)
        summary={key:report[key] for key in ('trace_count','decoder_error_count','mapped_count')}
    else:
        report=self_check(read_json(args.index),args.legacy_log,args.output)
        print(json.dumps({'status':report['status'],'synthetic_mapped':report['synthetic_mapped']}));return
    write_report(args.output,report);print(json.dumps(summary))


if __name__=='__main__':main()
