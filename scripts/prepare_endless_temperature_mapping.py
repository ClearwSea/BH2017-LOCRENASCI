"""Build/check an undeployed temperature-to-NPC-level lookup candidate."""

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
import json,math,hashlib,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
from lupa import LuaRuntime
OUT=ROOT/'server19-run/endless-temperature-mapping-20261027/candidate-v1'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 src=ROOT/'server19-run/endless-20261026/candidate-v3-boss-rotation/lua/base/levelinfinitecommon.lua'
 metadata=ROOT/'server19-run/endless-20261026/candidate-v2-33/metadata/_exceloutputasset/npclevellogic'
 cat=ROOT/'server19-run/endless-20261026/candidate-v2-33/catalog.json'
 raw=src.read_text(encoding='utf-8-sig');rows={x['HardLevel']:x for x in json.loads(metadata.read_bytes())};groups=json.loads(cat.read_bytes())['groups']
 shape=lambda t:.65+.85*(1-math.exp(-t/60000))
 temps=list(range(0,180001,1000)); tables=[]; evidence=[]
 for g in groups:
  level=g['groupLevel']; gt=[]
  for floor in range(1,34):
   base=math.floor(g['baseHardLevel']+g['deltaHardLevel']*(floor-1)); oldtemp=8+6*(level-1)+5
   anchor=max(1,math.floor(base*.7+math.floor(oldtemp*floor*.03))); ref=rows[anchor]
   allowed=[]
   for k,v in sorted(rows.items()):
    hp=v['HPRatio']/ref['HPRatio']; atk=v['ATKRatio']/ref['ATKRatio']; defense=v['DEFRatio']/ref['DEFRatio']; bleed=k/anchor
    if .65<=hp<=1.35 and .8<=atk<=1.2 and .8<=defense<=1.2 and .85<=bleed<=1.15 and abs(v['ElementalResistRatio']-ref['ElementalResistRatio'])<=.02+1e-9:allowed.append(k)
   assert anchor in allowed
   seq=[]
   for t in temps:
    target=max(.65,min(1.35,shape(t)/shape(35000)))
    chosen=min(allowed,key=lambda k:(abs(math.log(rows[k]['HPRatio']/ref['HPRatio']/target)),abs(k-anchor),k))
    if t==35000:chosen=anchor
    seq.append(chosen)
   assert all(a<=b for a,b in zip(seq,seq[1:]))
   gt.append(seq)
   evidence.append(dict(group=level,floor=floor,anchor=anchor,reference_old_temperature=oldtemp,levels=seq,low_hp_ratio=rows[seq[0]]['HPRatio']/ref['HPRatio'],high_hp_ratio=rows[seq[-1]]['HPRatio']/ref['HPRatio']))
  tables.append(gt)
 lua_table='{'+','.join('{'+','.join('{'+','.join(map(str,s))+'}' for s in gt)+'}' for gt in tables)+'}'
 replacement='''InfiData.TemperatureLevels = TABLE
InfiData.SetNPChardlevel = function ()
 local levels = InfiData.TemperatureLevels
 local group = LevelDesign:GetEndlessGroupLevel()
 local floor = Settings.Progress
 local temperature = math.max(0, math.min(180000, LevelDesign:GetEndlessDynamicHardLevel()))
 local slot = math.floor(temperature / 1000) + 1
 local hardlevel = levels[group][floor][slot]
 LevelDesign:SetLevelNPCHardLevel(hardlevel)
end

'''.replace('TABLE',lua_table)
 start=raw.index('InfiData.SetNPChardlevel =');end=raw.index('InfiData.getStageAndBornPoint =')
 patched=raw[:start]+replacement+raw[end:]
 (OUT/'levelinfinitecommon.lua').write_text(patched,encoding='utf-8')
 lua=LuaRuntime();lua.compile(patched);lua.execute('InfiData={};Settings={};LevelDesign={};');lua.execute(replacement)
 checks=0; ratios={k:[] for k in ['HPRatio','ATKRatio','DEFRatio','bleed','resistance_delta']}
 for e in evidence:
  ld=lua.globals().LevelDesign;ld.GetEndlessGroupLevel=lambda self,g=e['group']:g;lua.globals().Settings.Progress=e['floor'];ref=rows[e['anchor']]
  # All knot points, interval edges and out-of-range inputs use the actual Lua.
  for t in [-100,180001,1000000]+[x for k in temps for x in (k,k+.5,k+999.9)]:
   got=[];ld.GetEndlessDynamicHardLevel=lambda self,t=t:t;ld.SetLevelNPCHardLevel=lambda self,n:got.append(n)
   lua.globals().InfiData.SetNPChardlevel();expected=e['levels'][int(max(0,min(180000,t))//1000)]
   assert got==[expected] and expected in rows;checks+=1
  for chosen in e['levels']:
   for k in ('HPRatio','ATKRatio','DEFRatio'):ratios[k].append(rows[chosen][k]/ref[k])
   ratios['bleed'].append(chosen/e['anchor']);ratios['resistance_delta'].append(rows[chosen]['ElementalResistRatio']-ref['ElementalResistRatio'])
 report=dict(status='PASS',deployed=False,lua_cases=checks,group_floor_combinations=len(evidence),lookup_cells=7*33*len(temps),anchor_temperature=35000,temperature_step=1000,limits=dict(hp=[.65,1.35],attack=[.8,1.2],defense=[.8,1.2],bleed=[.85,1.15],elemental_resistance_absolute_delta=.02),realized_ranges={k:[min(v),max(v)] for k,v in ratios.items()},flat_group_floor_combinations=sum(len(set(e['levels']))==1 for e in evidence),source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [src,metadata,cat]},candidate_sha256=hashlib.sha256((OUT/'levelinfinitecommon.lua').read_bytes()).hexdigest(),adopted_controller='scripts/simulate_endless_cooling.py:fast',notes=['Existing NPC rows only; no metadata additions.','HP table ratio is not effective combat duration or physical EHP.','Same native hard-level setter/getter couples bleed to selected level.','Candidate expects display-scale temperature in hard_level; cannot deploy with current live 8..54 wire values.','Mapping is provisional; current simulated controller has not been revalidated against this quantized narrower response.'])
 (OUT/'mapping.json').write_text(json.dumps(evidence,separators=(',',':')),encoding='utf-8')
 (OUT/'check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
