"""Close native base difficulty plus Lua temperature levels for all Endless floors."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import csv,json,math,hashlib,sys,struct,zipfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server19_resources as resources
import server19_metadata_export as metadata
from server19_story_npc_level_closure import append_rows
out=ROOT/'server19-run/endless-20261026/error-224010'
candidate=ROOT/'server19-run/endless-20261026/candidate-v2-33'
catalog=json.loads((candidate/'catalog.json').read_bytes());required=set();cases=[]
for group in catalog['groups']:
 for floor in range(1,catalog['floors']+1):
  base=math.floor(group['baseHardLevel']+group['deltaHardLevel']*(floor-1))
  required.add(base)
  for delta in range(11):
   temperature=8+6*(group['groupLevel']-1)+delta
   level=base+math.floor(temperature*floor*.1)
   required.add(level);cases.append(dict(group=group['groupLevel'],floor=floor,temperature=temperature,level=level))
before=(out/'npclevellogic-before.json').read_bytes()
mapping={r['path']:r for r in resources.resource_map(resources.DEFAULT24)}
with zipfile.ZipFile(resources.DEFAULT24) as z:
 _,blob=resources.object_bytes(z,mapping['data/_exceloutput/npclevellogic']);_,tsv=resources.text_asset(blob)
 source=list(csv.DictReader(io.StringIO(tsv.decode('utf-8-sig')),delimiter='\t'))
 _,raw=resources.object_bytes(z,mapping['_exceloutputasset/npclevellogic'])
 typed={r['HardLevel']:r for r in metadata.SourceTypedDecoder(z).rows(raw,'MoleMole.NPCLevelMetaData')}
 after,added=append_rows(before,required,source)
 for row in added:
  for key,value in row.items():
   assert value==typed[row['HardLevel']][key] if key=='HardLevel' else struct.pack('<f',value)==struct.pack('<f',typed[row['HardLevel']][key])
rows=json.loads(after);assert required<={r['HardLevel'] for r in rows}
assert next(r for r in cases if r['group']==1 and r['floor']==33 and r['temperature']==11)['level']==76
target=candidate/'metadata/_exceloutputasset/npclevellogic';target.write_bytes(after)
report=dict(status='PASS',cases=len(cases),required_levels=sorted(required),added_rows=len(added),
 source='2.4 reference, matching previously approved NPC compatibility; preexisting rows unchanged',
 before_sha256=hashlib.sha256(before).hexdigest(),sha256=hashlib.sha256(after).hexdigest(),
 failing_case=dict(group=1,floor=33,temperature=11,base=40,level=76),human_acceptance='pending')
(out/'npc-level-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS',len(cases),'difficulty combinations;',len(added),'missing rows added; max',max(required))
