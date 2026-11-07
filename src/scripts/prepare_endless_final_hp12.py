"""Scoped final-floor HP tuning: clone rows, leave shared monsters unchanged."""

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
import json,re,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'server19-run/endless-base-audit-20261027/hp12-candidate'
def build():
 OUT.mkdir(exist_ok=True)
 source=ROOT/'server19-run/endless-temperature-mapping-20261027/hp-only-delivery/levelinfinitecommon.lua'
 original=ROOT/'server19-run/endless-20261026/candidate-v3-boss-rotation/metadata/_exceloutputasset/uniquemonsterdata'
 data=json.loads(original.read_bytes());byid={r['uniqueID']:r for r in data};mapping={430:434,431:435,432:436,433:437}
 for old,new in mapping.items():
  assert new not in byid and byid[old]['HPRatio']==22
  row=dict(byid[old],uniqueID=new,HPRatio=12.0)
  assert all(row[k]==v for k,v in byid[old].items() if k not in ('uniqueID','HPRatio'))
  data.append(row)
 raw=source.read_text(encoding='utf-8');pattern=re.compile(r'\{kind=6,lo=(\d+),hi=(\d+),name="([^"]+)",uniqueID=(430|431|432|433),configType="UniqueMonster",thread=0\}')
 matches=list(pattern.finditer(raw));assert len(matches)==7
 patched=pattern.sub(lambda m:m.group(0).replace('uniqueID='+m.group(4),'uniqueID='+str(mapping[int(m.group(4))])),raw)
 normalized=patched
 for old,new in mapping.items():normalized=normalized.replace('uniqueID='+str(new)+',','uniqueID='+str(old)+',')
 assert normalized==raw
 shutil.copytree(ROOT/'server19-run/endless-20261026/pool-fix/candidate/lua',OUT/'lua',dirs_exist_ok=True)
 (OUT/'lua/base/levelinfinitecommon.lua').write_text(patched,encoding='utf-8')
 meta=OUT/'metadata/_exceloutputasset';meta.mkdir(parents=True,exist_ok=True)
 (meta/'uniquemonsterdata').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 shutil.copy2(ROOT/'server19-run/endless-20261026/candidate-v3-boss-rotation/metadata/_exceloutputasset/monsterconfigdata',meta/'monsterconfigdata')
 shutil.copy2(ROOT/'server19-run/endless-temperature-mapping-20261027/hp-only-delivery/catalog.json',OUT/'catalog.json')
 rotation=[dict(group=int(m.group(1)),unique_id=mapping[int(m.group(4))],monster=m.group(3)) for m in matches]
 (OUT/'rotation.json').write_text(json.dumps({'rotation':rotation},indent=2),encoding='utf-8')
 report=dict(status='PASS',deployed=False,scope='kind6 final-floor bosses only',old_multiplier=22,new_multiplier=12,cloned_ids=mapping,old_rows_unchanged=len(data)-4,other_attributes_equal=True,other_lua_bytes_equal_after_reversing_ids=True,files=[dict(local=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [OUT/'lua/base/levelinfinitecommon.lua',meta/'uniquemonsterdata']])
 (OUT/'check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':build()
