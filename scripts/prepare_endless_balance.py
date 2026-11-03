"""Prepare a scoped Endless balance update; no device/save modifications."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,math,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
from lupa import LuaRuntime
p=ROOT/'server19-run/endless-20261026/candidate-v2-33';out=p.parent/'cap-balance-fix'
source=p/'lua/base/levelinfinitecommon.lua';raw=source.read_text(encoding='utf-8-sig')
old='LevelDesign:GetNPCHardLevel() + math.floor(LevelDesign:GetEndlessDynamicHardLevel() * Settings.Progress * 0.1)'
new='math.max(1, math.floor(LevelDesign:GetNPCHardLevel() * 0.7 + math.floor(LevelDesign:GetEndlessDynamicHardLevel() * Settings.Progress * 0.03)))'
assert raw.count(old)==1;raw=raw.replace(old,new)
(out/'levelinfinitecommon.lua').write_text(raw,encoding='utf-8')
cat=json.loads((p/'catalog.json').read_bytes());rows={r['HardLevel']:r for r in json.loads((p/'metadata/_exceloutputasset/npclevellogic').read_bytes())}
lua=LuaRuntime();lua.execute('InfiData={}; Settings={}; LevelDesign={};');lua.execute(raw[raw.index('InfiData.SetNPChardlevel ='):raw.index('InfiData.getStageAndBornPoint =')]);cases=[]
for g in cat['groups']:
 for f in range(1,34):
  base=math.floor(g['baseHardLevel']+g['deltaHardLevel']*(f-1))
  for d in range(11):
   t=8+6*(g['groupLevel']-1)+d;got=[];ld=lua.globals().LevelDesign
   ld.GetNPCHardLevel=lambda self:base;ld.GetEndlessDynamicHardLevel=lambda self:t;ld.SetLevelNPCHardLevel=lambda self,n:got.append(n);lua.globals().Settings.Progress=f
   lua.globals().InfiData.SetNPChardlevel();n=got[0];old_n=base+math.floor(t*f*.1)
   assert n in rows and 1<=n<=old_n
   cases.append(dict(group=g['groupLevel'],floor=f,temperature=t,old=old_n,new=n))
case=next(c for c in cases if c['group']==2 and c['floor']==33 and c['temperature']==17)
case['hp_ratio']=rows[case['new']]['HPRatio']/rows[case['old']]['HPRatio'];case['def_ratio']=rows[case['new']]['DEFRatio']/rows[case['old']]['DEFRatio']
report=dict(status='PASS',cases=len(cases),formula=new,example=case,sha256=hashlib.sha256((out/'levelinfinitecommon.lua').read_bytes()).hexdigest(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),deployed=False)
(out/'balance-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
