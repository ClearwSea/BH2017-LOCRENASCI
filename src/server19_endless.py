"""User-approved offline Endless simulation; opt-in catalog, native 1.9 wire."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib,json,random,time
import server19_stage as stage
import server19_protocol as proto

CATALOG=None
INFINITE_LEADERS=('第二名别凹了？','差一秒你不凹？','没第一我睡不着啊！！')
REQUESTS=frozenset(('GetEndlessDataReq','EndlessStageBeginReq','EndlessStageEndReq',
 'GetLastEndlessRewardDataReq','UseEndlessItemReq','GetEndlessAvatarHpReq','GetEndlessTopGroupReq'))

def configure(path):
 global CATALOG
 CATALOG=json.loads(Path(path).read_bytes())
 assert CATALOG['floors'] in (25,33) and len(CATALOG['groups'])==7

def calendar(now):
 d=datetime.fromtimestamp(now,ZoneInfo('Asia/Shanghai'))
 anchors=[]
 for back in range(8):
  x=(d-timedelta(days=back)).replace(hour=4,minute=0,second=0,microsecond=0)
  if x.weekday() in (0,3) and x<=d:anchors.append(x)
 start=max(anchors);end=start+timedelta(days=3 if start.weekday()==0 else 4)
 return int(start.timestamp()),int(end.timestamp())

def seed(*parts):return int(hashlib.sha256(':'.join(map(str,parts)).encode()).hexdigest()[:12],16)

def best_floor_time(s):
 value=s.get('best_floor33_seconds')
 if value is None:
  # Recover an actually recorded pre-upgrade clear, never invent an old time.
  old=(s.get('last_end') or {}).get('response',{})
  if old.get('progress')==33 and old.get('end_status')==1:value=old.get('stage_pass_time')
 return value if type(value) is int and 0<value<2**32-s['begin'] else None

def players(a,s,now):
 best=best_floor_time(s)
 rank_time=(s['begin']+best if best else s['end']) if s['progress']==33 else s['progress_time']
 result=[dict(uid=a['uid'],progress=s['progress'],max_progress=s['max_progress'],progress_time=rank_time,
 hidden_expire_time=s['hidden_until'],hidden_item_id=s.get('hidden_item',0),wait_effect_item_list=deepcopy(s['effects']),
 wait_burst_bomb_list=[])]
 fraction=min(1,max(0,(now-s['begin'])/(s['end']-s['begin'])))
 for i in range(19):
  rng=random.Random(seed(s['begin'],s['group'],a['uid'],i))
  if 'climate_opponents' in s:
   opponent=s['climate_opponents'][i];goal=opponent['goal'];pace=min(1,fraction/opponent['pace'])
  else:goal=rng.randint(4,CATALOG['floors']);pace=min(1,fraction/rng.uniform(.35,.95))
  floor=max(0,int(goal*pace)-s['bot_penalties'].get(str(i),0))
  result.append(dict(uid=900000000+i,progress=floor,max_progress=floor,
   progress_time=s['begin']+int((s['end']-s['begin'])*min(fraction,.9)),hidden_expire_time=0,wait_effect_item_list=[],
   wait_burst_bomb_list=[dict(item_id=b['item_id'],burst_time=b['burst_time']) for b in s['bombs'] if b['bot']==i]))
  if floor==33:
   # Existing simulated pace is the deterministic proxy for a 180-second run.
   simulated_pace=s['climate_opponents'][i]['pace'] if 'climate_opponents' in s else rng.uniform(.35,.95)
   result[-1]['progress_time']=s['begin']+max(1,int(round(180*simulated_pace)))
 if s['group']==7:
  # User-requested fixed leaders: capped floors and earlier tie-break times.
  earliest=s['begin']  # Real settlements cannot precede the period start.
  for i in range(3):
   result[i+1]['progress']=result[i+1]['max_progress']=CATALOG['floors']
   result[i+1]['progress_time']=earliest-3+i
 return sorted(result,key=lambda r:(-r['progress'],r['progress_time'],r['uid']))

def brief(a):
 s=a.get('endless_runtime',{})
 pool=CATALOG.get('bot_names',[])
 names=random.Random(seed(a['uid'],s.get('begin'),s.get('group'),'names')).sample(pool,19) if len(pool)>=19 else ['模拟舰长%02d'%(i+1) for i in range(19)]
 if s.get('group')==7:names[:3]=INFINITE_LEADERS
 return [dict(uid=900000000+i,nickname=names[i],level=a['main']['level'],avatar_id=101,avatar_star=1,
 avatar_level=a['main']['level'],avatar_combat=1000+i*50,last_login_time=0) for i in range(19)]+[
 dict(uid=a['uid'],nickname=a['main'].get('nickname','TEST1'),level=a['main']['level'],avatar_id=101,avatar_star=1,avatar_level=a['main']['level'])]

def refresh_simulated_wars(a,s,now):
 # Presentation-only bot activity; player inventory/combat/rank remain untouched.
 first='simulated_war_sequence' not in s
 sequence=s.get('simulated_war_sequence',0)
 rng=random.Random(seed(a['uid'],s['begin'],s['group'],'war',sequence))
 for _ in range(3 if first else 1):
  actor=rng.randrange(19);item=rng.choice(CATALOG['items'])
  target=actor if item['type'] in (1,3,5) else rng.choice([i for i in range(19) if i!=actor])
  s['wars'].append(dict(uid=900000000+actor,target_uid=900000000+target,item_id=item['ID'],type=1))
 s['wars']=s['wars'][-30:]
 s['entry_war_count']=3 if first else 1
 s['simulated_war_sequence']=sequence+1
 s.pop('next_simulated_war',None)


def state(a,now):
 begin,end=calendar(now);s=a.get('endless_runtime')
 if s and s['begin']!=begin:
  if s['active']:
   # Period expiry cancels an old battle; it cannot settle into the new period.
   s['active']=None
  rank=next(i+1 for i,p in enumerate(players(a,s,s['end'])) if p['uid']==a['uid'])
  old=s['group'];new=(7 if rank<=5 else 6) if old==7 else (old+1 if rank<=5 else max(1,old-1) if rank>15 else old)
  reward=dict(exp=0,scoin=10000*old,hcoin=40+20*old+(20 if new>old else 0),item_list=[])
  if s['max_progress']:
   a.setdefault('endless_rewards',[]).append(dict(begin_time=s['begin'],group_level=old,rank=rank,
    progress=s['progress'],reward_type=1 if new>old else 3 if new<old else 2,
    reward_id=980000+old*10+(1 if new>old else 3 if new<old else 2),reward_list=[reward],cur_group_level=new,claimed=False))
  group=new
 else:group=s['group'] if s else 1
 if s is None or s['begin']!=begin:
  s=dict(begin=begin,end=end,group=group,progress=0,max_progress=0,progress_time=begin,active=None,
   hp=[],items={str(i):1 for i in CATALOG['item_ids']},effects=[],hidden_until=0,bot_penalties={},bombs=[],
   cooldowns={},wars=[],claimed_floors=[],last_end=None)
  a['endless_runtime']=s
 if CATALOG.get('climate_version')==1 and 'display_temperature' not in s:
  import server19_endless_climate
  server19_endless_climate.bind(a,s)
 # User-scoped effects: only the two self potions remain functional.
 s['bombs']=[];s['bot_penalties']={};s['hidden_until']=0;s.pop('hidden_item',None)
 s['effects']=[x for x in s['effects'] if x['item_id'] in (70001,70016) and (x['expire_time']==0 or x['expire_time']>now)]
 for h in s['hp']:
  if h['next_recover_time'] and now>=h['next_recover_time']:
   ticks=1+(now-h['next_recover_time'])//3600;h['hp_percent']=min(100,h['hp_percent']+20*ticks)
   h['is_die']=h['hp_percent']==0;h['next_recover_time']=now+3600 if h['hp_percent']<100 else 0
 return s

def data(a,s,now):
 return dict(retcode=0,group_id=seed(a['uid'],s['begin'])%100000+1,group_level=s['group'],begin_time=s['begin'],
 end_time=s['end'],close_time=s['end'],endless_data_list=players(a,s,now),brief_data_list=brief(a),uid=a['uid'],
 item_list=[dict(item_id=int(k),num=v) for k,v in s['items'].items()],item_frozen_list=[dict(target_uid=int(k),frozen_time=v) for k,v in s['cooldowns'].items()],
 war_info_list=[],is_just_join=False,cur_progress_avatar_id_list=s['active']['team'] if s['active'] else [],
 cur_progress_item_id_list=[],random_seed=seed(s['begin'],s['group'])%2147483647,cur_top_group_level=7,top_group_player_num=20,
 top_group_promote_unlock_player_num=20,sin_type=1,burst_bomb_num=0,bombed_num=0,avg_player_level=a['main']['level'],hard_level=temperature(s,now))

def temperature(s,now):return s.get('display_temperature',8+6*(s['group']-1)+min(10,max(0,int((now-s['begin'])/21600))))

def avatar_hp_snapshot(a):
 owned={r['avatar_id'] for r in a['avatar_list'] if r.get('star',0)>0}
 stored={r['avatar_id']:r for r in a.get('endless_runtime',{}).get('hp',[])}
 return dict(retcode=0,avatar_hp_list=[deepcopy(stored.get(i,dict(avatar_id=i,hp_percent=100,sp_percent=0,next_recover_time=0,is_die=False))) for i in sorted(owned)])

def notification_snapshot(name,a,retcode):
 # Native startup initializes every avatar to full HP; opening the Endless
 # page does not request HP. Supply its original HP packet after the data
 # response, and refresh stale preparation state on a rejected begin.
 if CATALOG is None or 'endless_runtime' not in a:return []
 if name=='UseEndlessItemReq' and retcode==0:
  return [('EndlessWarInfoNotify',{'war_info':deepcopy(a['endless_runtime']['wars'][-1])})]
 if (name=='GetEndlessDataReq' and retcode==0) or (name=='EndlessStageBeginReq' and retcode!=0):
  packets=[('GetEndlessAvatarHpRsp',avatar_hp_snapshot(a))]
  if name=='GetEndlessDataReq':
   packets.extend(('EndlessWarInfoNotify',{'war_info':deepcopy(row)}) for row in a['endless_runtime']['wars'][-a['endless_runtime'].get('entry_war_count',1):])
  return packets
 return []

def _handle(name,a,v,now):
 if a['main']['level']<25:return {'retcode':3 if name=='GetEndlessDataReq' else 1}
 s=state(a,now)
 if name=='GetEndlessDataReq':refresh_simulated_wars(a,s,now)
 if name=='GetEndlessDataReq':return data(a,s,now)
 if name=='GetEndlessTopGroupReq':
  return dict(retcode=0,endless_data_list=players(a,s,now),brief_data_list=brief(a),war_info_list=[],hard_level=temperature(s,now))
 if name=='GetEndlessAvatarHpReq':
  return avatar_hp_snapshot(a)
 if name=='GetLastEndlessRewardDataReq':
  rows=a.get('endless_rewards',[])
  if not rows:return {'retcode':1}
  r=rows[-1]
  # Deliver all earned missed-period rewards once, but show the latest record.
  for reward in rows:
   if not reward['claimed']:
    for x in reward['reward_list']:
     for key in ('scoin','hcoin'):a['main'][key]=stage._u32(a['main'].get(key,0)+x[key],key)
    reward['claimed']=True
  return dict(retcode=0,**{k:deepcopy(x) for k,x in r.items() if k!='claimed'})
 if name=='EndlessStageBeginReq':
  team=v.get('avatar_id_list',[]);owned={r['avatar_id'] for r in a['avatar_list'] if r.get('star',0)>0}
  if not 1<=len(team)<=3 or len(set(team))!=len(team) or not set(team)<=owned or s['progress']>CATALOG['floors']:return {'retcode':1}
  if any(h['avatar_id'] in team and h['is_die'] for h in s['hp']):return {'retcode':1}
  if s['active']:
   if s['active']['team']!=team:return {'retcode':1}
   return deepcopy(s['active']['response'])
  buffs=[x['item_id'] for x in s['effects'] if x['effect_times']>0]
  begin_progress=min(s['progress'],CATALOG['floors']-1)
  best=best_floor_time(s)
  if best is not None:s['best_floor33_seconds']=best
  result=dict(retcode=0,progress=begin_progress,group_level=s['group'],drop_item_list=[],effect_item_id_list=buffs,
   is_re_begin=False,max_progress=s['max_progress'],is_collect_cheat_data=False,sum_sin_value=0,is_angry_burst=False,sin_type=1,ntr_avatar_list=[],hard_level=temperature(s,now))
  s['hidden_until']=0;s['active']=dict(floor=begin_progress+1,team=team,started=now,response=deepcopy(result));s['last_end']=None
  return result
 if name=='EndlessStageEndReq':
  digest=hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
  if not s['active']:
   return deepcopy(s['last_end']['response']) if s['last_end'] and s['last_end']['digest']==digest else {'retcode':1}
  active=s['active'];status=v.get('end_status');hps=v.get('avatar_hp_list',[])
  if status not in (1,2,3) or len({h['avatar_id'] for h in hps})!=len(hps):return {'retcode':1}
  seconds=v.get('stage_pass_time',0)
  if status==1 and active['floor']==33 and (type(seconds) is not int or not 0<seconds<2**32-s['begin']):return {'retcode':1}
  if any(h['avatar_id'] not in active['team'] or not 0<=h.get('hp_percent',0)<=100 or not 0<=h.get('sp_percent',0)<=100 for h in hps):return {'retcode':1}
  for h in hps:
   s['hp']=[x for x in s['hp'] if x['avatar_id']!=h['avatar_id']]
   s['hp'].append(dict(avatar_id=h['avatar_id'],hp_percent=h.get('hp_percent',0),sp_percent=h.get('sp_percent',0),
    is_die=h.get('hp_percent',0)==0,next_recover_time=now+3600 if h.get('hp_percent',0)<100 else 0))
  if status==1:
   floor=active['floor'];previous=s['progress'];s['progress']=floor;s['max_progress']=max(s['max_progress'],floor)
   if floor>previous:s['progress_time']=now
   if floor==33:
    best=best_floor_time(s);s['best_floor33_seconds']=min(best,seconds) if best is not None else seconds
   if floor not in s['claimed_floors']:
    a['main']['scoin']=stage._u32(a['main'].get('scoin',0)+1000*s['group'],'scoin')
    a['main']['hcoin']=stage._u32(a['main'].get('hcoin',0)+(5 if floor%5==0 else 0),'hcoin')
    item=CATALOG['item_ids'][(floor-1)%len(CATALOG['item_ids'])];s['items'][str(item)]+=1;s['claimed_floors'].append(floor)
   for effect in s['effects']:effect['effect_times']=max(0,effect['effect_times']-1)
   s['effects']=[x for x in s['effects'] if x['effect_times']]
  result=dict(retcode=0,progress=s['progress'],end_status=status,drop_item_list=[],group_level=s['group'],stage_pass_time=v.get('stage_pass_time',0))
  s['active']=None;s['last_end']=dict(digest=digest,response=deepcopy(result));return result
 if name=='UseEndlessItemReq':
  iid=v.get('item_id');target=v.get('target_uid');cfg=next((r for r in CATALOG['items'] if r['ID']==iid),None)
  if not cfg or not s['items'].get(str(iid),0) or s['active']:return {'retcode':1}
  kind=cfg['type']
  if kind in (1,3,5) and target in (None,0):target=a['uid']
  own=target==a['uid'];bot=target-900000000 if type(target) is int else -1
  if (kind in (1,3,5) and not own) or (kind in (2,4) and not 0<=bot<19):return {'retcode':1}
  if not own and s['cooldowns'].get(str(target),0)>now:return {'retcode':1}
  # Only strength and resist potions affect gameplay; other items are cosmetic.
  if iid in (70001,70016):
   s['effects']=[x for x in s['effects'] if x['item_id']!=iid]
   s['effects'].append(dict(item_id=iid,effect_times=max(1,cfg['paramIntMin']),expire_time=0))
  frozen=0 if own else now+60
  s['items'][str(iid)]-=1;s['cooldowns'][str(target)]=frozen;s['wars'].append(dict(uid=a['uid'],target_uid=target,item_id=iid,type=1))
  return dict(retcode=0,target_uid=target,item_frozen_time=frozen,item_id=iid,group_level=s['group'])
 raise ValueError(name)

def response(name,account,values=None,*,account_path=None,now=None):
 if CATALOG is None or name not in REQUESTS:return None
 path=Path(account_path or stage.DEFAULT_ACCOUNT).resolve();now=int(time.time() if now is None else now)
 with stage._transaction_lock(path):
  before=stage._read(path,account);current=stage.copy_account(before)
  try:
   result=_handle(name,current,values or {},now);proto.encode_message(name[:-3]+'Rsp',result)
  except (ValueError,TypeError,KeyError,OverflowError):result={'retcode':1}
  if result['retcode']==0:stage._save(path,before,current);stage._sync(account,current)
 return name[:-3]+'Rsp',result
