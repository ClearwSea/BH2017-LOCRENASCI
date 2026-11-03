
import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,shutil,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server19_chiyou_catalog import prepare,OUT,BASE,read
prepare()
live=ROOT/'server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json'
raw=live.read_bytes();launcher=live.parent.parent/'run-comparison-server.py'
exec(launcher.read_text().split('s.load_account()')[0],{'__file__':str(launcher)})
import server19_extra_story as extra,server19_extra_achievements as ach,server19_stage as stage,server19_protocol as proto,server19_missions as missions
fixture=OUT/'catalog-check';fixture.mkdir(exist_ok=True)
for p in (OUT/'delivery').iterdir():shutil.copyfile(p,fixture/p.name)
p=fixture/'runtime-ready.json';ready=read(p);ready['deployed']=True;p.write_text(json.dumps(ready))
extra.configure(fixture)
for name in read(BASE/'runtime-ready.json')['table_sha256']:
 old=read(BASE/name);new=read(fixture/name)
 assert all(row in new for row in old),name
assert len(ach.CATALOG)==36
account=fixture/'simulated-account.json';a=json.loads(raw);a['stage_runtime']['active']=None;a['main']['stamina']=9999
old_claims=list(a.get('extra_achievement_runtime',{}).get('claimed_ids',[]))
account.write_text(json.dumps(a))
for name,values in [('GetExtraStoryDataReq',{}),('GetExtraStoryActivityActReq',{'chapter_id':2}),('GetExtraStoryAchieveDataReq',{'chapter_id':2}),('GetStageDropDisplayReq',{'stage_id_list':list(range(211101,211119))})]:
 result=extra.response(name,a,values);proto.decode_message(result[0],proto.encode_message(*result))
assert stage.response('StageBeginReq',a,{'stage_id':211102,'avatar_id_list':[101]},account_path=account)[1]['retcode']!=0
newmissions={r['stage_id']:mid for mid,r in ach.CATALOG.items() if r['stage_id']>=211101}
assert missions.response('GetMissionRewardReq',a,{'mission_id':newmissions[211101]},account_path=account)[1]['retcode']!=0
for sid in range(211101,211119):
 req={'stage_id':sid,'avatar_id_list':[101,0,0]};rsp=stage.response('StageBeginReq',a,req,account_path=account);assert rsp[1]['retcode']==0,(sid,rsp)
 same=account.read_bytes();assert stage.response('StageBeginReq',a,req,account_path=account)==rsp and account.read_bytes()==same
 body=proto.encode_message('StageEndReqBody',dict(stage_id=sid,end_status=1,stage_pass_time=60,challenge_index_list=[0,1,2],drop_item_list=rsp[1]['drop_item_list'],scoin_reward=0,avatar_exp_reward=0));req={'body':body,'sign':stage.stage_end_signature(body,rsp[1]['sign_key'])};end=stage.response('StageEndReq',a,req,account_path=account);assert end[1]['retcode']==0,(sid,end)
 same=account.read_bytes();assert stage.response('StageEndReq',a,req,account_path=account)==end and account.read_bytes()==same
 if sid in newmissions:
  mid=newmissions[sid];rsp=missions.response('GetMissionRewardReq',a,{'mission_id':mid},account_path=account);assert rsp[1]['retcode']==0,(mid,rsp)
  same=account.read_bytes();assert missions.response('GetMissionRewardReq',a,{'mission_id':mid},account_path=account)[1]['retcode']!=0 and account.read_bytes()==same
  a=read(account);assert next(r for r in ach.mission_rows(a) if r['mission_id']==mid)['status']==5
assert all(mid in a['extra_achievement_runtime']['claimed_ids'] for mid in old_claims)
assert live.read_bytes()==raw
result=dict(status='PASS',simulated_only=True,stages=18,claims=15,combined_catalog=36,original_prerequisite_enforced=True,duplicate_transactions_checked=True,unearned_claim_rejected=True,claimed_state_reload=True,old_rows_and_claims_preserved=True,live_account_sha256=hashlib.sha256(raw).hexdigest(),live_account_unchanged=True,human_acceptance='pending')
(OUT/'catalog-checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
