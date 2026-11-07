"""Isolated six-stage Kallen catalog checks; never write the live account."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server19_kallen_catalog import prepare,read,OUT,BASE
prepare();live=ROOT/'server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json';raw=live.read_bytes();launcher=live.parent.parent/'run-comparison-server.py'
exec(launcher.read_text().split('s.load_account()')[0],{'__file__':str(launcher)})
import server19_extra_story as extra,server19_extra_achievements as ach,server19_stage as stage,server19_protocol as proto
fixture=OUT/'catalog-check';fixture.mkdir(exist_ok=True)
for p in (OUT/'all-open-delivery').iterdir():shutil.copyfile(p,fixture/p.name)
p=fixture/'runtime-ready.json';ready=read(p);ready['deployed']=True;p.write_text(json.dumps(ready));extra.configure(fixture)
assert len(ach.CATALOG)==52
for name in read(BASE/'runtime-ready.json')['table_sha256']:
 old=read(BASE/name);new=read(fixture/name)
 assert all(row in new for row in old if name!='stagedata_main' or row['levelId'] not in range(217101,217107)),name
account=fixture/'simulated-account.json';a=json.loads(raw);a['stage_runtime']['active']=None;a['main']['stamina']=9999;account.write_text(json.dumps(a))
for sid in range(217101,217107):
 assert stage.STORY_TRIAL_AVATARS[sid]==(112,)
 assert stage.response('StageBeginReq',a,{'stage_id':sid,'avatar_id_list':[101,0,0]},account_path=account)[1]['retcode']!=0
 req={'stage_id':sid,'avatar_id_list':[112,0,0]};rsp=stage.response('StageBeginReq',a,req,account_path=account);assert rsp[1]['retcode']==0
 same=account.read_bytes();assert stage.response('StageBeginReq',a,req,account_path=account)==rsp and account.read_bytes()==same
 body=proto.encode_message('StageEndReqBody',dict(stage_id=sid,end_status=1,stage_pass_time=60,challenge_index_list=[0,1,2],drop_item_list=rsp[1]['drop_item_list'],scoin_reward=0,avatar_exp_reward=0));req={'body':body,'sign':stage.stage_end_signature(body,rsp[1]['sign_key'])};end=stage.response('StageEndReq',a,req,account_path=account);assert end[1]['retcode']==0
 same=account.read_bytes();assert stage.response('StageEndReq',a,req,account_path=account)==end and account.read_bytes()==same
for name,values in [('GetExtraStoryDataReq',{}),('GetExtraStoryActivityActReq',{'chapter_id':7})]:
 rsp=extra.response(name,a,values);proto.decode_message(rsp[0],proto.encode_message(*rsp))
assert extra.response('GetExtraStoryActivityActReq',a,{'chapter_id':8})[1]['act_list']==[]
assert live.read_bytes()==raw
result=dict(status='PASS',simulated_only=True,stages=6,trial_roster=112,combined_catalog=52,challenge_acts=0,duplicate_transactions_checked=True,live_account_unchanged=True,human_acceptance='pending')
(OUT/'catalog-checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
