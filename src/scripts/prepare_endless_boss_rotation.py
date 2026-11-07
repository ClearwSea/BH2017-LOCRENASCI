"""Prepare final-floor rotation over deployed floor33/balance resources; never deploy."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,copy,hashlib,shutil,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
base=ROOT/'server19-run/endless-20261026/candidate-v2-33'
patch=base.parent/'cap-balance-fix';out=base.parent/'candidate-v3-boss-rotation'
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def build():
 out.mkdir(exist_ok=True);shutil.copytree(base/'lua',out/'lua',dirs_exist_ok=True)
 for name in ('catalog.json','metadata/_exceloutputasset/uniquemonsterdata','metadata/_exceloutputasset/monsterconfigdata','metadata/_exceloutputasset/npclevellogic'):
  target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/name,target)
 rows=json.loads((base/'metadata/_exceloutputasset/uniquemonsterdata').read_bytes());byid={r['uniqueID']:r for r in rows}
 for uid,ref in ((432,427),(433,428)):
  assert uid not in byid
  r=copy.deepcopy(byid[431]);r['uniqueID']=uid
  for key in ('name','monsterName','typeName','configType','AIName','attackCDNames','attackCDs','abilities'):r[key]=copy.deepcopy(byid[ref][key])
  rows.append(r)
 save(out/'metadata/_exceloutputasset/uniquemonsterdata',rows)
 raw=(patch/'levelinfinitecommon.lua').read_text(encoding='utf-8-sig')
 entry=re.compile(r'\{kind=6,lo=\d+,hi=\d+,name="[^"]+",uniqueID=\d+,configType="UniqueMonster",thread=0\}')
 assert len(entry.findall(raw))==2
 rotation=[432,433,430,432,433,431,432];allrows={r['uniqueID']:r for r in rows}
 new=','.join('{kind=6,lo=%d,hi=%d,name="%s",uniqueID=%d,configType="UniqueMonster",thread=0}'%(g,g,allrows[uid]['monsterName'],uid) for g,uid in enumerate(rotation,1))
 matches=list(entry.finditer(raw));raw=raw[:matches[0].start()]+new+raw[matches[-1].end():]
 (out/'lua/base/levelinfinitecommon.lua').write_text(raw,encoding='utf-8')
 p=out/'lua/base/globalluafunctions.lua';raw=p.read_text(encoding='utf-8-sig');assert raw.startswith('local compatible_nature=')
 from server19_endless_pool_fix import patch as fix_pool
 raw=fix_pool(raw)
 raw=raw.replace('local compatible_nature={','local compatible_nature={[432]=0,[433]=0,',1);p.write_text(raw,encoding='utf-8')
 manifest=[]
 for relative,remote in [('lua/base/levelinfinitecommon.lua','/sdcard/bh3-server19-resources/lua/base/levelinfinitecommon.lua'),('lua/base/globalluafunctions.lua','/sdcard/bh3-server19-resources/lua/base/globalluafunctions.lua'),('metadata/_exceloutputasset/uniquemonsterdata','/sdcard/bh3-server19-metadata/_exceloutputasset/uniquemonsterdata')]:
  manifest.append(dict(local=relative,remote=remote,sha256=hashlib.sha256((out/relative).read_bytes()).hexdigest()))
 save(out/'rotation.json',dict(deployed=False,rotation=[dict(group=g,unique_id=uid,monster=allrows[uid]['monsterName']) for g,uid in enumerate(rotation,1)],files=manifest,source='User-approved rank rotation; existing BossUlysses/BossBronya/Wendy resources; current final-floor ratios retained'))
 print('Prepared 3-file rotation candidate',out)
if __name__=='__main__':build()
