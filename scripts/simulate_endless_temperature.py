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

def simulate(seed,scenario,periods=400):
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
  delta=np.zeros(7); reasons=[]
  for g in range(7):
   if r[g]<.78 or m[g]>1.05:
    severity=max((.78-r[g])*3,(m[g]-1.05)*2)
    delta[g]=-max(1000,temp[g]*.035)*(1+min(3,severity*5)); reasons.append('slow_or_low_clear')
   elif m[g]<.90 and r[g]>.94:
    delta[g]=max(3000,temp[g]*.04)*max(.08,1-(temp[g]/180000)**2); reasons.append('fast_high_clear')
   else:
    delta[g]=rng.uniform(-100,100); reasons.append('target_hold')
  delta=np.clip(delta,-12000,8000)
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

def main():
 OUT.mkdir(parents=True,exist_ok=True); started=time.perf_counter(); summaries=[]
 fig,axes=plt.subplots(3,1,figsize=(11,10),sharex=True)
 for scenario in SCENARIOS:
  for seed in PARAMS['seeds']:
   records=simulate(seed,scenario)
   raw=json.dumps(records,separators=(',',':')).encode()
   (OUT/f'{scenario}-{seed}.json').write_bytes(raw)
   ts=np.array([x['temperature'] for x in records]); ds=np.array([x['difficulty'] for x in records]); rs=np.array([x['clear_rate'] for x in records]); ms=np.array([x['success_time_ratio'] for x in records])
   tail=ts[-100:]; slopes=np.array([np.polyfit(np.arange(100),tail[:,g],1)[0] for g in range(7)])
   row=dict(scenario=scenario,seed=seed,sha256=hashlib.sha256(raw).hexdigest(),tail_temperature_range=[float(tail.min()),float(tail.max())],tail_difficulty_range=[float(ds[-100:].min()),float(ds[-100:].max())],tail_clear_rate_range=[float(rs[-100:].min()),float(rs[-100:].max())],tail_time_ratio_range=[float(ms[-100:].min()),float(ms[-100:].max())],max_abs_tail_slope=float(abs(slopes).max()),boundary_period_tiers=int(((ts[-100:]==0)|(ts[-100:]==180000)).sum()),final_temperature=ts[-1].tolist())
   acceptable=((ms>=.88)&(ms<=1.08)&(rs>=.75)).all(axis=1)
   start=200 if scenario=='power_shock' else 0
   row['first_10_period_recovery']=next((i-start for i in range(start,len(records)-9) if acceptable[i:i+10].all()),None)
   row['max_tail_single_tier_span']=float(np.ptp(tail,axis=0).max())
   row['heuristic_stable']=row['max_abs_tail_slope']<150 and row['boundary_period_tiers']==0 and row['tail_clear_rate_range'][0]>.7
   summaries.append(row)
   if seed==1731:
    axes[0].plot(ts.mean(axis=1),label=scenario); axes[1].plot(ds.mean(axis=1)); axes[2].plot(rs.mean(axis=1))
 # Exact replay verifies fixed RNG seeds, not yet a production restart implementation.
 replay=simulate(1731,'normal'); replay_bytes=json.dumps(replay,separators=(',',':')).encode()
 assert replay_bytes==(OUT/'normal-1731.json').read_bytes()
 axes[0].set_ylabel('Display temperature'); axes[0].legend(); axes[1].set_ylabel('Difficulty multiplier'); axes[2].set_ylabel('Participant clear rate'); axes[2].set_xlabel('Period')
 for ax in axes: ax.grid(alpha=.25)
 fig.tight_layout(); fig.savefig(OUT/'trajectories.png',dpi=150)
 report=dict(parameters=PARAMS,scenarios=SCENARIOS,runs=summaries,deterministic_replay=True,elapsed_seconds=time.perf_counter()-started,scope='synthetic only; no live service, account or client access')
 (OUT/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__': main()
