"""Apply navigation-only edits to base material rows; no game data is bundled."""
from pathlib import Path
import argparse
import copy
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
def navigation_digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def apply(rows,policy):
    if not isinstance(rows,list) or len(rows)!=policy['expected_rows']:
        raise ValueError('Expected the configured base material export before source additions')
    if any(not isinstance(r,dict) or type(r.get('ID')) is not int or not isinstance(r.get('comeFromList'),list) for r in rows):
        raise ValueError('Malformed material row')
    result=copy.deepcopy(rows);byid={r['ID']:r for r in result}
    if len(byid)!=len(result):raise ValueError('Duplicate material ID')
    for row in result:
        if policy['common_entry'] not in row['comeFromList']:
            row['comeFromList'].insert(0,policy['common_entry'])
    seen=set()
    for patch in policy['patches']:
        identity=patch['material_id']
        if identity in seen or identity not in byid:raise ValueError('Missing or repeated patched material: '+str(identity))
        seen.add(identity);navigation=byid[identity]['comeFromList']
        if navigation_digest(navigation)!=patch['preimage_sha256']:
            raise ValueError('Navigation source changed for material '+str(identity))
        for operation in patch['operations']:
            index,count=operation['index'],operation['delete_count'];insert=operation['insert']
            if type(index) is not int or type(count) is not int or index<0 or count<0 or index+count>len(navigation):
                raise ValueError('Invalid navigation list edit')
            if not isinstance(insert,list) or any(not isinstance(x,str) for x in insert):raise ValueError('Invalid inserted navigation')
            navigation[index:index+count]=insert
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rules',type=Path,default=ROOT/'rules/material-navigation.json')
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Output already exists')
    if args.input.resolve()==args.output.resolve():raise ValueError('Keep the source input unchanged')
    result=apply(json.loads(args.input.read_bytes()),json.loads(args.rules.read_bytes()))
    encoded=(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('xb') as stream:stream.write(encoded)
    print(json.dumps({'rows':len(result),'sha256':hashlib.sha256(encoded).hexdigest()}))

if __name__=='__main__':main()
