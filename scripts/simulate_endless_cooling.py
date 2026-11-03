"""Standalone synthetic Endless calibration. Never imports or writes live server state."""

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
import argparse, json, hashlib, time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path('server19-run/endless-simulation-20261027/v2')
PARAMS=dict(population_per_tier=500,periods=400,seeds=[1731,20679,9405],temperature_bounds=[0,180000],difficulty_bounds=[0.65,1.5],target_success_time_ratio=[0.90,1.05],target_clear_rate=[0.78,0.94],attempt_cap=6,turnover=0.004,migration=0.01,growth=0.0008)
SCENARIOS=['normal','cold','hot','ceiling','power_shock','fixed_ceiling']

def difficulty(t): return .65+.85*(1-np.exp(-np.asarray(t)/60000))

def simulate(seed,scenario,periods=400,controller="baseline"):
 control_rng=np.random.default_rng(seed+900000)
 cooling=np.zeros(7,dtype=bool)
 rng=np.random.default_rng(seed)
 n=500; tier=(1+np.arange(7)*.12)[:,None]
 power=np.clip(rng.normal(1,.15,(7,n)),.55,1.35)*tier
 skill=np.clip(rng.normal(0,.16,(7,n)),-.4,.4)
 effort=rng.uniform(0,1,(7,n))
 if scenario in ('ceiling','fixed_ceiling'): power[:]=1.35*tier
 temp=np.full(7,35000. if scenario not in ('cold','hot') else (0. if scenario=='cold' else 180000.))
 records=[]
 for period in range(periods):
  if scenario=='power_shock' and period==200: power*=.7
  participating=rng.random((7,n))<.85
  attempts=1+np.floor(effort*6).astype(int)
  # Three reference floor classes. Common attempt quality keeps outcomes correlated.
  common=rng.normal(0,.20,(7,n,6,1))
  floor_noise=rng.normal(0,1,(7,n,6,3))*np.array([.10,.15,.22])
  ratio=difficulty(temp)[:,None,None,None]/(power/tier)[:,:,None,None]
  times=ratio*np.exp(.24-skill[:,:,None,None]+common+floor_noise)
  # One joint time model: exceeding the normalized deadline is failure.
  valid=np.arange(6)[None,None,:,None]<attempts[:,:,None,None]
  best=np.min(np.where(valid,times,np.inf),axis=2)
  passed=(best<=1.5)&participating[:,:,None]
  rate=passed.sum(axis=1)/np.maximum(1,participating.sum(axis=1))[:,None]
  med=np.array([[np.median(best[g,:,f][passed[g,:,f]]) if passed[g,:,f].any() else 1.5 for f in range(3)] for g in range(7)])
  # Failures included as timeout penalties; inactive players excluded explicitly.
  penalized=np.where(participating[:,:,None],np.minimum(best,1.5),np.nan)
  all_mean=np.nanmean(penalized,axis=1)
  r=rate.mean(axis=1); m=med.mean(axis=1)
  jitter=control_rng.uniform(-100,100,7)
  delta=np.zeros(7); reasons=[]
  for g in range(7):
   if controller=='fast':
    if r[g]<.78: cooling[g]=True
    elif r[g]>=.86 and m[g]<=1.03: cooling[g]=False
   if controller=='fast' and cooling[g]:
    # Hysteresis avoids toggling at the entry threshold. Work in bounded load space.
    reduction=min(.18,max(.015,.8*max(0,1-.98/m[g]),(.86-r[g])*.35))
    wanted=max(.65,float(difficulty(temp[g]))*(1-reduction))
    target=-60000*np.log(max(1e-9,1-(wanted-.65)/.85))
    delta[g]=max(-45000,target-temp[g]); reasons.append('emergency_cooling')
   elif r[g]<.78 or m[g]>1.05:
    severity=max((.78-r[g])*3,(m[g]-1.05)*2)
    delta[g]=max(-12000,-max(1000,temp[g]*.035)*(1+min(3,severity*5))); reasons.append('slow_or_low_clear')
   elif m[g]<.90 and r[g]>.94:
    delta[g]=max(3000,temp[g]*.04)*max(.08,1-(temp[g]/180000)**2); reasons.append('fast_high_clear')
   else:
    delta[g]=jitter[g]; reasons.append('target_hold')
  delta=np.clip(delta,-45000 if controller=="fast" else -12000,8000)
  records.append(dict(period=period,temperature=temp.tolist(),difficulty=difficulty(temp).tolist(),clear_rate=r.tolist(),success_time_ratio=m.tolist(),failure_inclusive_time_ratio=all_mean.mean(axis=1).tolist(),reference_clear_rates=rate.tolist(),reference_time_ratios=med.tolist(),participants=participating.sum(axis=1).tolist(),power_mean=(power/tier).mean(axis=1).tolist(),delta=delta.tolist(),reason=reasons))
  temp=np.clip(temp+delta,0,180000)
  if scenario=='fixed_ceiling': continue
  power=np.minimum(power+.0008*tier,1.35*tier)
  # Small cross-tier movement with persistent power, skill and effort.
  for g in range(6):
   up=np.argsort(power[g])[-5:]; down=np.argsort(power[g+1])[:5]
   for arr in (power,skill,effort):
    cache=arr[g,up].copy(); arr[g,up]=arr[g+1,down]; arr[g+1,down]=cache
  power=np.clip(power,.55*tier,1.35*tier)
  leaving=rng.random((7,n))<.004
  fresh=np.clip(rng.normal(.85,.12,(7,n)),.55,1.35)*tier
  power=np.where(leaving,fresh,power)
  skill=np.where(leaving,np.clip(rng.normal(0,.16,(7,n)),-.4,.4),skill)
  effort=np.where(leaving,rng.uniform(0,1,(7,n)),effort)
 return records


def metrics(records,scenario):
 t=np.array([x['temperature'] for x in records]); m=np.array([x['success_time_ratio'] for x in records]); r=np.array([x['clear_rate'] for x in records])
 start=200 if scenario=='power_shock' else 0
 ok=((m>=.88)&(m<=1.08)&(r>=.75)).all(axis=1)
 recovery=next((i-start for i in range(start,len(records)-9) if ok[i:i+10].all()),None)
 d=np.diff(t,axis=0); reversals=0; tail_reversals=0
 for g in range(7):
  ids=np.flatnonzero(abs(d[:,g])>500)
  for a,b in zip(ids,ids[1:]):
   if b-a<=5 and d[a,g]*d[b,g]<0:
    reversals+=1
    if a>=300: tail_reversals+=1
 return dict(recovery=recovery,significant_reversals_within_5_periods=reversals,tail_reversals=tail_reversals,tail_temperature=[float(t[-100:].min()),float(t[-100:].max())],tail_clear=[float(r[-100:].min()),float(r[-100:].max())],tail_max_tier_span=float(np.ptp(t[-100:],axis=0).max()),tail_boundary_hits=int(((t[-100:]==0)|(t[-100:]==180000)).sum()),minimum_clear_after_shock=float(r[start:].min()))

def main():
 out=Path('server19-run/endless-simulation-20261027/fast-cooling-v1');out.mkdir(parents=True,exist_ok=True)
 begin=time.perf_counter(); rows=[]
 fig,axes=plt.subplots(2,2,figsize=(12,7))
 for scenario in SCENARIOS:
  for seed in PARAMS['seeds']:
   for controller in ('baseline','fast'):
    records=simulate(seed,scenario,controller=controller)
    raw=json.dumps(records,separators=(',',':')).encode()
    (out/f'{scenario}-{seed}-{controller}.json').write_bytes(raw)
    rows.append(dict(scenario=scenario,seed=seed,controller=controller,sha256=hashlib.sha256(raw).hexdigest(),**metrics(records,scenario)))
    if seed==1731 and scenario in ('hot','power_shock'):
     col=0 if scenario=='hot' else 1; start=0 if scenario=='hot' else 200
     segment=records[start:start+45]
     axes[0,col].plot([x['period']-start for x in segment],np.array([x['temperature'] for x in segment]).mean(axis=1),label=controller)
     axes[1,col].plot([x['period']-start for x in segment],np.array([x['clear_rate'] for x in segment]).mean(axis=1),label=controller)
 for col,title in enumerate(('Hot start','30% power loss')):
  axes[0,col].set_title(title);axes[0,col].set_ylabel('Mean temperature');axes[1,col].set_ylabel('Mean participant clear rate');axes[1,col].set_xlabel('Periods since event')
 for ax in axes.flat: ax.grid(alpha=.25);ax.legend()
 fig.tight_layout();fig.savefig(out/'comparison.png',dpi=150)
 replay=json.dumps(simulate(1731,'hot',controller='fast'),separators=(',',':')).encode()
 assert replay==(out/'hot-1731-fast.json').read_bytes()
 result=dict(runs=rows,elapsed_seconds=time.perf_counter()-begin,deterministic_replay=True,paired_population_rng=True,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 for scenario in SCENARIOS:
  print(scenario,[(c,[x['recovery'] for x in rows if x['scenario']==scenario and x['controller']==c],sum(x['tail_reversals'] for x in rows if x['scenario']==scenario and x['controller']==c)) for c in ('baseline','fast')])
 print('seconds',result['elapsed_seconds'])
if __name__=='__main__':main()
