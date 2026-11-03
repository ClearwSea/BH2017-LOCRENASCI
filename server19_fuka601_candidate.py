"""Prepare an isolated601 compatibility candidate; never deploy or edit accounts.

2.4 version columns are provenance, not authoritative CN release dates.
Only601 and its actual table references are added; the global filter stays intact.
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
import csv
import argparse
import io
import json
import zipfile
from pathlib import Path

import server19_resources as res
import server19_metadata_export as meta

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '.local-baseline/server19-dev/fuka601-candidate'
BASE = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    maps = {r['path']: r for r in res.resource_map(res.DEFAULT24)}
    original = {r['path']: r for r in res.resource_map(res.DEFAULT19)}
    report = {'avatar_id':601, 'deployment':'not_deployed',
              'historical_19_table_values_verified':False,
              'source_version_columns_preserved':True, 'tables':{}, 'blockers':[]}
    known = meta.asset_types()
    with zipfile.ZipFile(res.DEFAULT24) as z:
        objects = meta.PackageObjects(z)
        decoder = meta.SourceTypedDecoder(z)
        cache = {}

        def table(name):
            if name not in cache:
                _, raw = objects.object(maps['data/_exceloutput/'+name])
                _, text = res.text_asset(raw)
                tsv = list(csv.DictReader(io.StringIO(text.decode('utf-8-sig')), delimiter='\t'))
                rec = maps['_exceloutputasset/'+name]
                _, typed_raw = objects.object(rec)
                typ = known[objects.script_type(rec, typed_raw)]
                typed = decoder.rows(typed_raw, typ['row_type'])
                cache[name] = (tsv, typed, typ)
            return cache[name]

        tsv, typed, typ = table('avatardata')
        avatars = {r['avatarID']:r for r in typed}
        a = avatars[601]
        assert (a['avatarRegistryKey'],a['avatarCardID'],a['avatarFragmentID'],a['initialWeapon']) == ('Fuka_C1_FK',60601,10601,20611)
        missing = []
        present = {r['avatarID'] for r in json.loads((BASE/'avatardata').read_text('utf-8'))}
        for row in tsv:
            aid = int(row['avatarID'])
            if aid not in present:
                reg = avatars[aid]['avatarRegistryKey'].lower()
                model = 'entities/avatar/'+reg+'/avatar_'+reg
                missing.append({'avatar_id':aid, 'registry':avatars[aid]['avatarRegistryKey'],
                    'source_version_begin':row.get('GameVersionBegin'),
                    'source_region':row.get('EffectRegionList'),
                    'excluded_by_version':not meta.in_version(row,(1,9)),
                    'original_model_exists':model in original,
                    'original_model':model if model in original else None})
        report['other_filtered_avatars'] = missing
        skills = set(a['skillList']) | {a['captainSkillID']}
        report['avatar_source'] = [r for r in tsv if r['avatarID']=='601']
        weapon_rows=table('weapondata')[1]
        weapon_ids={20611}
        while True:
            more={r['evoID'] for r in weapon_rows if r['ID'] in weapon_ids and r.get('evoID')}
            if more <= weapon_ids: break
            weapon_ids.update(more)
        selections = {'avatardata':lambda r:r['avatarID']==601,
            'avatarskilldata':lambda r:r['skillId'] in skills,
            'avatarsubskilldata':lambda r:r.get('avatarSkillID',r.get('avatarSkillId',r.get('skillId'))) in skills,
            'avatarfragmentdata':lambda r:r['ID']==10601,
            'weapondata':lambda r:r['ID'] in weapon_ids,
            'avatarstardata':lambda r:r.get('avatarID')==601}
        selected = {}
        for name, predicate in selections.items():
            source, rows, typ = table(name)
            fields = meta.serialized_fields(typ['row_type_index'])
            picked = [r for r in rows if predicate(r)]
            converted = [{k:meta.project_typed(r[k],ptr) for k,ptr in fields} for r in picked]
            for row in converted:
                for k,ptr in fields:
                    if meta.type_info(ptr)['kind']==3:
                        row[k]=chr(row[k])
            selected[name] = converted
            if not converted:
                report['blockers'].append('No selected rows: '+name)
            key = fields[0][0]
            current = json.loads((BASE/name).read_text('utf-8'))
            ids = {r[key] for r in converted}
            conflicts = [r[key] for r in current if r[key] in ids and r not in converted]
            if conflicts:
                report['blockers'].append({'conflicting_existing_rows':name,'keys':conflicts})
            merged = current + [r for r in converted if r[key] not in {v[key] for v in current}]
            target = OUT/'_exceloutputasset'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(meta.native_json(merged)[0],encoding='utf-8')
            report['tables'][name]={'selected_rows':len(converted),'added_rows':len(merged)-len(current),
                'key':key,'keys':[r[key] for r in converted],
                'source_version_rows':[r for r in source if str(r.get(key,'')) in {str(v[key]) for v in converted}]}
        report['skill_ids']=sorted(skills)
        report['subskill_ids']=[r['avatarSubSkillId'] for r in selected['avatarsubskilldata']]
        report['selected_rows']=selected
        report['card_identity']='60601 is AvatarData.avatarCardID; no materialdata row is required by original card storage'
        # Required text keys, including source typed TextMap contributions.
        text_keys=set()
        text_fields={'fullName','shortName','desc','name','info','skillStep','firstName','lastName','enFirstName','enLastName','displayTitle','displayDescription'}
        for name, rows in selected.items():
            for row in rows:
                text_keys.update(str(v) for k,v in row.items() if k in text_fields and not (name=='avatarfragmentdata' and k=='name') and isinstance(v,(str,int)) and str(v) not in ('','0'))
        rec=maps['_exceloutputasset/textmap']; _,raw=objects.object(rec)
        rows,_=meta.text_map_sources(objects,list(maps.values()),raw)
        texts={r['ID']:r for r in rows if r['ID'] in text_keys}
        current_path=ROOT/'.local-baseline/server19-dev/sony-human-fixes-v1/textmap'
        current=json.loads(current_path.read_text('utf-8'))
        ids={r['ID'] for r in current}
        added=[]
        for key in sorted(text_keys-ids):
            row=texts.get(key)
            if row is None:
                report.setdefault('missing_source_text_keys',[]).append(key); continue
            value=row['Text']
            import re
            value=re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),value)
            added.append({'ID':key,'Text':value})
        (OUT/'_exceloutputasset/textmap').write_text(meta.native_json(current+added)[0],encoding='utf-8')
        report['textmap']={'required_keys':sorted(text_keys),'added_keys':[r['ID'] for r in added]}
    proofs=[]
    with zipfile.ZipFile(res.DEFAULT19) as z:
        for path,rec in original.items():
            if 'fuka' in path or path.endswith('/20611') or path.endswith('/10601'):
                obj,raw=res.object_bytes(z,rec)
                proofs.append({'path':path,'resource':rec,'class':obj['class'],'bytes':len(raw),'exists':True})
    report['original_resource_objects']=proofs
    report['resource_reference_limit']='Name inventory and object existence; not a full texture/PPtr or render proof'
    (OUT/'tables-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'tables':{k:{f:v[f] for f in ('selected_rows','added_rows')} for k,v in report['tables'].items()},'omitted_avatars':missing,'blockers':report['blockers'],'resource_objects':len(proofs)},ensure_ascii=False))
    return report


def prepare_battle():
    """Reuse the audited reader for601 only; do not recheck the whole roster."""
    import server19_avatar_battle_resources as battle
    scoped=OUT/'battle-tables'; scoped.mkdir(exist_ok=True)
    for name in ('avatardata','avatarskilldata','avatarsubskilldata','weapondata'):
        rows=json.loads((OUT/'_exceloutputasset'/name).read_text('utf-8'))
        if name=='avatardata': rows=[r for r in rows if r['avatarID']==601]
        (scoped/name).write_text(meta.native_json(rows)[0],encoding='utf-8')
    previous=battle.TABLES
    try:
        battle.TABLES=scoped
        files,manifest=battle.build(res.DEFAULT19,res.DEFAULT24)
    finally:
        battle.TABLES=previous
    for relative,raw in files.items():
        target=OUT/'battle-projection'/relative
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    row=manifest['roster'][0]
    assert row['avatar_id']==601
    receipt={'status':'BLOCKED' if row['blockers'] else 'HUMAN_ACCEPTANCE_PENDING',
             'deployment_allowed':False, 'roster':row,
             'unsupported_roots':manifest['unsupported_roots'],
             'projected_roots':len(manifest['projection']['projected_roots']),
             'limits':['Do not deploy the stage7-based projection over the current unified container',
                       'Texture/PPtr dependencies and rendered model still need complete verification',
                       'Current cultivation ready-file identity needs an explicit601 extension before deployment',
                       'No live service, account or device changes performed']}
    (OUT/'compatibility-status.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ('status','deployment_allowed','projected_roots','unsupported_roots')},ensure_ascii=False))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:
        target=args.output.resolve()
        if not target.is_relative_to(ROOT) or target.exists():
            raise ValueError('Use a fresh candidate directory inside the workspace')
        OUT=target
    prepare()
    prepare_battle()
