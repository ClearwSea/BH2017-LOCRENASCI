"""Isolated mapped-climate checks; never writes the real account or device."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,copy,tempfile,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server19_endless_climate as c
import server19_endless as e
out=ROOT/'server19-run/endless-temperature-mapping-20261027/integration';out.mkdir(exist_ok=True)
start=1792958400;results=[];began=time.perf_counter()
for scenario in ['normal','cold','hot','ceiling','power_shock','fixed_ceiling']:
 for seed in [1731,20679,9405]:
  world=c.create(start,seed)
  if scenario=='cold':world['temperature']=[0]*7
  if scenario=='hot':world['temperature']=[180000]*7
  if scenario in ('ceiling','fixed_ceiling'):world['power']=(np.ones((7,500))*1.35*(1+np.arange(7)*.12)[:,None]).tolist()
  trace=[]
  for period in range(400):
   if scenario=='power_shock' and period==200:world['power']=(np.array(world['power'])*.7).tolist()
   p=c.project(world);trace.append({k:v for k,v in p.items() if k!='forecast'})
   c.advance(world)
   if scenario=='fixed_ceiling':world['power']=(np.ones((7,500))*1.35*(1+np.arange(7)*.12)[:,None]).tolist()
  t=np.array([x['temperature'] for x in trace]);r=np.array([x['clear_rate'] for x in trace]);m=np.array([x['success_time_ratio'] for x in trace]);offset=200 if scenario=='power_shock' else 0
  ok=((r>=.75)&(m>=.88)&(m<=1.08)).all(axis=1)
  recovery=next((i-offset for i in range(offset,391) if ok[i:i+10].all()),None)
  changes=np.diff(t,axis=0);rev=0
  for g in range(7):
   ids=np.flatnonzero(abs(changes[:,g])>500)
   rev+=sum(b-a<=5 and changes[a,g]*changes[b,g]<0 for a,b in zip(ids,ids[1:]))
  assert np.isfinite(t).all() and t.min()>=0 and t.max()<=180000
  row=dict(scenario=scenario,seed=seed,recovery=recovery,rapid_reversals=int(rev),tail_temperature=[float(t[-100:].min()),float(t[-100:].max())],tail_clear=[float(r[-100:].min()),float(r[-100:].max())],mapping_cap_events=sum(x['reason'].count('combat_mapping_cap') for x in trace))
  results.append(row);(out/f'{scenario}-{seed}.json').write_text(json.dumps(trace,separators=(',',':')),encoding='utf-8')
# JSON restart and skipped-period equivalence use the exact production functions.
a={};c.ensure(a,start);resumed=json.loads(json.dumps(a));assert c.ensure(resumed,start)==a['endless_climate']
boundaries=[];cursor=start
for _ in range(5):cursor=c.end_of(cursor);boundaries.append(cursor)
for b in boundaries:c.ensure(a,b)
c.ensure(resumed,boundaries[-1]);assert resumed==a
# Actual response transaction, unchanged progress/rewards, fixed period value and wire.
with tempfile.TemporaryDirectory() as td:
 cat=json.loads((ROOT/'server19-run/endless-20261026/candidate-v2-33/catalog.json').read_bytes());cat['climate_version']=1
 path=Path(td);(path/'catalog.json').write_text(json.dumps(cat));e.configure(path/'catalog.json')
 account=json.loads((ROOT/'server19-run/endless-baseline-20261027-v1/sony-account.json').read_bytes());s=account['endless_runtime'];now=s['begin']+100
 (path/'account.json').write_text(json.dumps(account));before=copy.deepcopy(s);balance=copy.deepcopy(account['main'])
 for tick in (now,now+21600,now+43200):
  _,response=e.response('GetEndlessDataReq',account,account_path=path/'account.json',now=tick);assert response['retcode']==0 and response['hard_level']==35000
 assert account['main']==balance and account['endless_runtime']['progress']==before['progress'] and account['endless_runtime']['claimed_floors']==before['claimed_floors']
 persisted=json.loads((path/'account.json').read_bytes());climate=copy.deepcopy(persisted['endless_climate']);e.response('GetEndlessDataReq',persisted,account_path=path/'account.json',now=now+43201);assert persisted['endless_climate']==climate
gate=all(x['recovery'] is not None and (x['scenario'] not in ('hot','power_shock') or x['recovery']<=4) and x['rapid_reversals']==0 for x in results)
report=dict(status='PASS' if gate else 'TECHNICAL_CHECKS_PASS_DEPLOYMENT_HOLD',deployment_gate=gate,production_restart_and_catchup=True,isolated_protocol_and_save_migration=True,seconds=time.perf_counter()-began,runs=results,proxy='HP table ratio only; not observed combat time')
(out/'check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for scene in ['normal','cold','hot','ceiling','power_shock','fixed_ceiling']:
 a=[x for x in results if x['scenario']==scene];print(scene,[(x['recovery'],x['rapid_reversals'],x['mapping_cap_events']) for x in a])
print('PASS',report['seconds'])
