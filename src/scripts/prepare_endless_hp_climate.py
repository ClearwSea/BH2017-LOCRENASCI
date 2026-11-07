"""Generate HP-only climate resources and execute isolated Lua/stat checks."""

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
import json,math,struct,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
from lupa import LuaRuntime
OUT=ROOT/'server19-run/endless-temperature-mapping-20261027/hp-only-delivery'
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def main():
 OUT.mkdir(exist_ok=True)
 source=ROOT/'server19-run/endless-20261026/candidate-v3-boss-rotation/lua/base/levelinfinitecommon.lua'
 meta=ROOT/'server19-run/endless-20261026/candidate-v2-33/metadata/_exceloutputasset/npclevellogic'
 catalog=ROOT/'server19-run/endless-20261026/candidate-v2-33/catalog.json'
 raw=source.read_text(encoding='utf-8-sig');original=json.loads(meta.read_bytes());rows={x['HardLevel']:x for x in original};cat=json.loads(catalog.read_bytes());anchors=[]
 shape=lambda t:.65+.85*(1-math.exp(-t/60000))
 factors=[max(.65,min(1.35,shape(t)/shape(35000))) for t in range(0,180001,1000)]
 for g in cat['groups']:
  anchors.append([max(1,math.floor(math.floor(g['baseHardLevel']+g['deltaHardLevel']*(floor-1))*.7+math.floor((8+6*(g['groupLevel']-1)+5)*floor*.03))) for floor in range(1,34)])
 generated=[]
 for anchor in sorted({x for a in anchors for x in a}):
  ref=rows[anchor]
  for slot,factor in enumerate(factors):
   key=10000+anchor*181+slot;assert key not in rows and key<32768
   item=dict(ref,HardLevel=key,HPRatio=f32(f32(ref['HPRatio'])*factor));generated.append(item);rows[key]=item
 table='{'+','.join('{'+','.join(map(str,a))+'}' for a in anchors)+'}'
 replacement='''InfiData.ClimateAnchors = TABLE
InfiData.SetNPChardlevel = function ()
 local group = LevelDesign:GetEndlessGroupLevel()
 local reference = InfiData.ClimateAnchors[group][Settings.Progress]
 local temperature = math.max(0, math.min(180000, LevelDesign:GetEndlessDynamicHardLevel()))
 local slot = math.floor(temperature / 1000)
 InfiData.ClimateReferenceHardLevel = reference
 LevelDesign:SetLevelNPCHardLevel(10000 + reference * 181 + slot)
end

'''.replace('TABLE',table)
 start=raw.index('InfiData.SetNPChardlevel =');end=raw.index('InfiData.getStageAndBornPoint =');patched=raw[:start]+replacement+raw[end:]
 old='LevelDesign:GetNPCHardLevel()*0.1*(1+0.2*Settings.GroupLevel)';new='InfiData.ClimateReferenceHardLevel*0.1*(1+0.2*Settings.GroupLevel)'
 assert patched.count(old)==1;patched=patched.replace(old,new)
 (OUT/'levelinfinitecommon.lua').write_text(patched,encoding='utf-8');(OUT/'npclevellogic').write_text(json.dumps(original+generated,separators=(',',':')),encoding='utf-8')
 cat['climate_version']=1;(OUT/'catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=2),encoding='utf-8')
 textmap=json.loads((ROOT/'server19-run/endless-baseline-20261027-v1/runtime/sdcard/bh3-server19-metadata/_exceloutputasset/textmap').read_bytes())
 overrides={r['ID']:r['Text'] for r in json.loads((ROOT/'data/endless-temperature-text-overrides.json').read_bytes())}
 assert sum(r['ID'] in overrides for r in textmap)==len(overrides)
 for row in textmap:
  if row['ID'] in overrides:row['Text']=overrides[row['ID']]
 (OUT/'textmap').write_text(json.dumps(textmap,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 calibration={'version':1,'reference_temperature':35000,'step':1000,'curves':[factors]*7,'proxy':'HP-only factor; attack, defense, resistance and bleed stay at reference'}
 (ROOT/'data/endless-climate-calibration.json').write_text(json.dumps(calibration,indent=2),encoding='utf-8')
 lua=LuaRuntime();lua.compile(patched);lua.execute('InfiData={};Settings={};LevelDesign={};');lua.execute(replacement);count=0;max_error=0
 for g in range(1,8):
  lua.globals().LevelDesign.GetEndlessGroupLevel=lambda self,g=g:g
  for floor in range(1,34):
   anchor=anchors[g-1][floor-1];ref=rows[anchor];lua.globals().Settings.Progress=floor
   for t in [-100,180001,1000000]+[x for k in range(0,180001,1000) for x in (k,k+.5,k+999.9)]:
    ld=lua.globals().LevelDesign;got=[];ld.GetEndlessDynamicHardLevel=lambda self,t=t:t;ld.SetLevelNPCHardLevel=lambda self,v:got.append(v)
    lua.globals().InfiData.SetNPChardlevel();slot=int(max(0,min(180000,t))//1000);assert got==[10000+anchor*181+slot]
    actual=rows[got[0]];assert lua.globals().InfiData.ClimateReferenceHardLevel==anchor
    assert all(actual[k]==v for k,v in ref.items() if k not in ('HardLevel','HPRatio'))
    error=abs(actual['HPRatio']/f32(ref['HPRatio'])-factors[slot]);assert error<1e-6;max_error=max(max_error,error)
    if slot==35:assert actual['HPRatio']==f32(ref['HPRatio'])
    for ratio in (.3,.5,1,1.2,1.5,2,3,4,5,10):
     assert .44*ratio*(anchor*.1*(1+.2*g))==.44*ratio*(lua.globals().InfiData.ClimateReferenceHardLevel*.1*(1+.2*g))
    count+=1
 assert json.loads((OUT/'npclevellogic').read_bytes())[:len(original)]==original
 report=dict(status='PASS',deployed=False,lua_calls=count,new_rows=len(generated),old_rows_unchanged=len(original),hp_range=[min(factors),max(factors)],max_float32_ratio_error=max_error,attack_defense_resistance_unchanged=True,bleed_all_10_stages_unchanged=True,reference_temperature=35000,files=[dict(local=str((OUT/name).relative_to(ROOT)),sha256=hashlib.sha256((OUT/name).read_bytes()).hexdigest()) for name in ('levelinfinitecommon.lua','npclevellogic','catalog.json','textmap')])
 (OUT/'check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
