"""NPC rows required by static stages, original dynamic mapping and Lua setters.

Later-package rows remain explicit compatibility data, not historical balancing.
Only metadata is inspected; no gameplay functions are run.
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
import json
import re
from pathlib import Path


def required_levels(inventory, dynamic_rows, texts):
    levels={int(r['row']['hardLevel']) for r in inventory}
    dynamic_stages=[r['stage_id'] for r in inventory if r['row']['UseDynamicHardLv']]
    if dynamic_stages:levels.update(int(r['hardLv']) for r in dynamic_rows)
    setters=[];unresolved=[]
    for path,text in texts.items():
        # Strip comments before inspecting source expressions, not quoted data.
        active=re.sub(r'--\[\[.*?\]\]|--[^\n]*','',text,flags=re.S)
        for match in re.finditer(r'SetLevelNPCHardLevel\s*\(([^()]*)\)',active):
            arg=match[1].strip()
            if arg.isdecimal():
                levels.add(int(arg));setters.append(dict(path=path,level=int(arg)))
            else:unresolved.append(dict(path=path,expression=arg))
        for match in re.finditer(r'[\'"]set_npc_hardlevel[\'"]\s*,\s*(\d+)\b',active):
            levels.add(int(match[1]));setters.append(dict(path=path,level=int(match[1])))
    return levels,dict(dynamic_stage_ids=dynamic_stages,literal_setters=setters,
                      nonliteral_setters=unresolved,
                      limit='Dynamic quest difficulty and arbitrary runtime Lua are not simulated')


def append_rows(before, levels, source_rows):
    from server19_metadata_export import native_json
    rows=json.loads(before);have={r['HardLevel'] for r in rows}
    assert len(have)==len(rows)
    fields=('HardLevel','HPRatio','ATKRatio','DEFRatio','ElementalResistRatio')
    added=[]
    for level in sorted(levels-have):
        matches=[r for r in source_rows if int(r['HardLevel'])==level]
        assert len(matches)==1,(level,len(matches))
        row={f:int(matches[0][f]) if f=='HardLevel' else float(matches[0][f]) for f in fields}
        added.append(row)
    # Preserve every preexisting row's exact bytes, including numbers/order.
    end=before.rfind(b']');assert end>=0 and not before[end+1:].strip()
    suffix=','.join(native_json(r)[0] for r in added).encode()
    after=before[:end]+(b',' if rows and added else b'')+suffix+before[end:]
    assert json.loads(after)==rows+added
    return after,added


def prepare(folder):
    import csv,io,struct,zipfile
    import server19_resources as resources
    import server19_metadata_export as metadata
    from server19_stage_resources import text_record
    root=Path(__file__).resolve().parent
    work=root/'.local-baseline/server19-dev/story-all-20261015'
    folder=Path(folder);out=folder/'npc-level-fix';out.mkdir(exist_ok=False)
    inventory=json.loads((work/'inventory.json').read_bytes())
    scope=json.loads((work/'goal-six-chapters-20261016/openworld-scope.json').read_bytes())
    texts={};proof={}
    for item in inventory:
        raw=(work/'lua-source'/item['lua']).read_bytes()
        texts[item['lua']]=raw.decode('utf-8-sig');proof[item['lua']]=hashlib.sha256(raw).hexdigest()
    mapped={r['path']:r for r in resources.resource_map(resources.DEFAULT24)}
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        for path,expected in scope['module_source_sha256'].items():
            raw,_=text_record(package,mapped[path],'2.4')
            assert hashlib.sha256(raw).hexdigest()==expected
            texts[path]=raw.decode('utf-8-sig');proof[path]=expected
        levels,audit=required_levels(inventory,json.loads((folder/'dynamichardlvdata').read_bytes()),texts)
        _,blob=resources.object_bytes(package,mapped['data/_exceloutput/npclevellogic'])
        _,tsv=resources.text_asset(blob)
        source=list(csv.DictReader(io.StringIO(tsv.decode()),delimiter='\t'))
        _,raw=resources.object_bytes(package,mapped['_exceloutputasset/npclevellogic'])
        typed=metadata.SourceTypedDecoder(package).rows(raw,'MoleMole.NPCLevelMetaData')
        before=(folder/'npclevellogic').read_bytes()
        after,added=append_rows(before,levels,source)
        for row in added:
            real=next(r for r in typed if r['HardLevel']==row['HardLevel'])
            for name,value in row.items():
                assert (value==real[name] if name=='HardLevel' else struct.pack('<f',value)==struct.pack('<f',real[name]))
        (out/'npclevellogic').write_bytes(after)
        (out/'source-npclevellogic.tsv').write_bytes(tsv)
    report=dict(status='PASS_metadata_closure_human_pending',required_levels=sorted(levels),added_rows=added,
        before_sha256=hashlib.sha256(before).hexdigest(),sha256=hashlib.sha256(after).hexdigest(),
        preexisting_row_bytes_unchanged=True,source_tsv_typed_float32_equal=True,
        root_scripts=len(inventory),module_count=len(scope['module_source_sha256']),source_hashes=proof,
        audit=audit,source_policy='Real 2.4 rows, explicit later compatibility; not historical 1.9 balance',
        human_acceptance='pending')
    (out/'technical-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_hashes','audit')}))
    return report


if __name__=='__main__':
    import sys
    prepare(sys.argv[1])
