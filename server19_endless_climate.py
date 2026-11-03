"""Persisted offline Endless population. State is committed by the account transaction."""
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import json,hashlib
import numpy as np
CALIBRATION=json.loads((Path(__file__).parent/'data/endless-climate-calibration.json').read_bytes())
CURVES=np.array(CALIBRATION['curves']); SCALE=.65+.85*(1-np.exp(-35000/60000))

def seed(*values):return int(hashlib.sha256(':'.join(map(str,values)).encode()).hexdigest()[:15],16)
def end_of(begin):
 d=datetime.fromtimestamp(begin,ZoneInfo('Asia/Shanghai'))
 return int((d+timedelta(days=3 if d.weekday()==0 else 4)).timestamp())
def load_at(temperature):
 return CURVES[np.arange(7),np.clip(np.asarray(temperature,dtype=int)//1000,0,180)]*SCALE

def create(begin,world_seed=1731):
 rng=np.random.default_rng(world_seed);tier=(1+np.arange(7)*.12)[:,None]
 return dict(version=1,sort_policy='stable-v1',seed=world_seed,begin=begin,end=end_of(begin),temperature=[35000]*7,cooling=[False]*7,power=(np.clip(rng.normal(1,.15,(7,500)),.55,1.35)*tier).tolist(),skill=np.clip(rng.normal(0,.16,(7,500)),-.4,.4).tolist(),effort=rng.uniform(0,1,(7,500)).tolist(),ids=np.arange(3500).reshape(7,500).tolist(),next_id=3500,history=[])

def project(c):
 rng=np.random.default_rng(seed(c['seed'],c['begin'],'population'));control=np.random.default_rng(seed(c['seed'],c['begin'],'control'))
 tier=(1+np.arange(7)*.12)[:,None];power=np.array(c['power']);skill=np.array(c['skill']);effort=np.array(c['effort']);temp=np.array(c['temperature'],dtype=float)
 participation=rng.random((7,500))<.85; attempts=1+np.floor(effort*6).astype(int)
 noise=rng.normal(0,.20,(7,500,6,1))+rng.normal(0,1,(7,500,6,3))*np.array([.10,.15,.22])
 times=load_at(temp)[:,None,None,None]/(power/tier)[:,:,None,None]*np.exp(.24-skill[:,:,None,None]+noise)
 best=np.min(np.where(np.arange(6)[None,None,:,None]<attempts[:,:,None,None],times,np.inf),axis=2)
 passed=(best<=1.5)&participation[:,:,None]
 rate=passed.sum(axis=1)/np.maximum(1,participation.sum(axis=1))[:,None]
 med=np.array([[np.median(best[g,:,f][passed[g,:,f]]) if passed[g,:,f].any() else 1.5 for f in range(3)] for g in range(7)])
 r=rate.mean(axis=1);m=med.mean(axis=1);jitter=control.uniform(-100,100,7);next_temp=[];cooling=list(c['cooling']);reasons=[]
 for g in range(7):
  if r[g]<.78:cooling[g]=True
  elif r[g]>=.86 and m[g]<=1.03:cooling[g]=False
  if cooling[g]:
   reduction=min(.18,max(.015,.8*max(0,1-.98/m[g]),(.86-r[g])*.35))
   target=load_at(temp)[g]*(1-reduction)
   choices=np.arange(min(180,int(temp[g]//1000))+1)
   index=min(choices,key=lambda i:(abs(CURVES[g,i]*SCALE-target),-i))
   delta=max(-45000,index*1000-temp[g]);reason='emergency_cooling'
  elif r[g]<.78 or m[g]>1.05:
   severity=max((.78-r[g])*3,(m[g]-1.05)*2)
   delta=max(-12000,-max(1000,temp[g]*.035)*(1+min(3,severity*5)));reason='slow_or_low_clear'
  elif m[g]<.90 and r[g]>.94:
   delta=min(8000,max(3000,temp[g]*.04)*max(.08,1-(temp[g]/180000)**2));reason='fast_high_clear'
  else:delta=jitter[g];reason='target_hold'
  # Do not keep increasing the display when the bounded NPC mapping is saturated.
  ceiling=int(np.flatnonzero(CURVES[g]>=CURVES[g].max()-1e-12)[0])*1000
  target=max(0,min(180000,temp[g]+delta))
  if delta>0 and target>ceiling:
   target=ceiling if temp[g]<=ceiling else temp[g]
   reason='combat_mapping_cap'
  next_temp.append(int(round(target)));reasons.append(reason)
 # UI opponents are sampled from this same population, excluding special fixed leaders.
 goals=np.zeros((7,500),dtype=int)
 for floor in range(1,34):
  kind=2 if floor==33 else 1 if floor%10==0 else 0
  clear=(best[:,:,kind]*(.45+.55*floor/33)<=1.5)&participation
  goals+=((goals==floor-1)&clear)
 forecast=dict(goals=goals.tolist(),pace=rng.uniform(.35,.95,(7,500)).tolist())
 c['projection']=dict(temperature=temp.tolist(),next_temperature=next_temp,next_cooling=cooling,clear_rate=r.tolist(),success_time_ratio=m.tolist(),failure_inclusive_time_ratio=np.nanmean(np.where(participation[:,:,None],np.minimum(best,1.5),np.nan),axis=(1,2)).tolist(),participants=participation.sum(axis=1).tolist(),reason=reasons,forecast=forecast)
 return c['projection']

def advance(c):
 if c.get('sort_policy') not in (None,'stable-v1'):raise ValueError('Unsupported climate sort policy')
 p=c.get('projection') or project(c)
 c['history'].append(dict(begin=c['begin'],end=c['end'],**{k:v for k,v in p.items() if k!='forecast'}))
 rng=np.random.default_rng(seed(c['seed'],c['begin'],'growth'));tier=(1+np.arange(7)*.12)[:,None]
 power=np.minimum(np.array(c['power'])+.0008*tier,1.35*tier);skill=np.array(c['skill']);effort=np.array(c['effort']);ids=np.array(c['ids'])
 for g in range(6):
  # Preserve population order for ties on both NumPy 1.26 (ARM32) and 2.x.
  up=np.argsort(power[g],kind='stable')[-5:];down=np.argsort(power[g+1],kind='stable')[:5]
  for arr in (power,skill,effort,ids):
   cache=arr[g,up].copy();arr[g,up]=arr[g+1,down];arr[g+1,down]=cache
 power=np.clip(power,.55*tier,1.35*tier);leaving=rng.random((7,500))<.004
 power=np.where(leaving,np.clip(rng.normal(.85,.12,(7,500)),.55,1.35)*tier,power)
 skill=np.where(leaving,np.clip(rng.normal(0,.16,(7,500)),-.4,.4),skill);effort=np.where(leaving,rng.uniform(0,1,(7,500)),effort)
 count=int(leaving.sum());ids[leaving]=np.arange(c['next_id'],c['next_id']+count);c['next_id']+=count
 for key,value in [('power',power),('skill',skill),('effort',effort),('ids',ids)]:c[key]=value.tolist()
 c['temperature']=p['next_temperature'];c['cooling']=p['next_cooling'];c['begin']=c['end'];c['end']=end_of(c['begin']);c.pop('projection',None)
 # Legacy current-period projections remain untouched until this transition.
 c['sort_policy']='stable-v1'

def ensure(account,begin):
 c=account.get('endless_climate')
 if c is None:c=account['endless_climate']=create(begin)
 if c['version']!=1 or c['begin']>begin:raise ValueError('Unsupported climate version or clock rollback')
 while c['begin']<begin:advance(c)
 if 'projection' not in c:project(c)
 return c

def bind(account,s):
 c=ensure(account,s['begin']);s['display_temperature']=c['temperature'][s['group']-1]
 indices=np.random.default_rng(seed(c['seed'],s['begin'],s['group'],'group')).choice(500,19,replace=False)
 f=c['projection']['forecast'];g=s['group']-1
 s['climate_opponents']=[dict(goal=f['goals'][g][int(i)],pace=f['pace'][g][int(i)],population_id=c['ids'][g][int(i)]) for i in indices]
