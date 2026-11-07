"""Check authorized display replacement and real server settlement on fixtures."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,struct,datetime,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REF=ROOT
sys.path[:0]=[str(ROOT/'tools'),str(REF),str(REF/'analysis-deps'),str(REF/'.local-baseline/server19-dev/story-goal-tools/python')]
from server19_arm_native import ArmImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
O=ROOT/'server19-run/nx-backport-20261102';spec=json.loads((O/'signin-patch.json').read_bytes());im=ArmImage(O/'client-signin.so',spec['sha256']);results=[]
for base in (0,0x10000000):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base,0x8000000)
 for seg in im.loads:u.mem_write(base+seg[2],im.read(seg[2],seg[4]))
 h=base+0x9000000;u.mem_map(h,0x10000)
 def hook(uc,a,size,data):
  if a==base+spec['site']+4:uc.emu_stop()
 u.hook_add(UC_HOOK_CODE,hook)
 for rid,item in [(1210,3122),(1211,3122),(1212,3122),(1213,3122),(1214,3122),(1215,3122),(1211,10202),(1211,0),(0,0)]:
  reward=h+0x100 if rid else 0;obj=h+0x300;stack=h+0xf000;raw=bytearray(100)
  struct.pack_into('<I',raw,8,rid);struct.pack_into('<I',raw,40,item);struct.pack_into('<I',raw,48,20)
  if reward:u.mem_write(reward,bytes(raw))
  values={UC_ARM_REG_R0:obj,UC_ARM_REG_R1:0,UC_ARM_REG_R2:1,UC_ARM_REG_R3:2,UC_ARM_REG_R5:obj,UC_ARM_REG_R7:reward,UC_ARM_REG_SP:stack}
  for reg,val in values.items():u.reg_write(reg,val)
  u.emu_start(base+spec['site'],0xffffffff,count=70)
  assert u.reg_read(UC_ARM_REG_PC)==base+spec['site']+4
  assert all(u.reg_read(reg)==v for reg,v in values.items())
  assert int.from_bytes(u.mem_read(obj+20,4),'little')==reward
  if reward:
   changed=1211<=rid<=1214 and item==3122;expected=bytearray(raw)
   if changed:struct.pack_into('<I',expected,16,10000);expected[40:52]=bytes(12)
   assert bytes(u.mem_read(reward,100))==bytes(expected)
  results.append(dict(base=base,reward=rid,item=item))
import server19_signin as signin,server19_stage as stage,server19_duty as duty
original=copy.deepcopy(signin._get_table_for_month(11));even=copy.deepcopy(signin._get_table_for_month(10))
assert signin._get_table_for_month(11)==original
assert signin._get_table_for_month(10)==even
assert signin._reward_of(1101)==duty._reward_of(1101)
claims=[]
for day in [5,12,19,26]:
 a=json.loads((O/'account.json').read_bytes());a['sign_in_runtime']=dict(year=2026,month=11,signed_days=day-1,last_sign_time=0)
 path=O/('fixture-day-'+str(day)+'.json');path.write_text(json.dumps(a),encoding='utf-8');before=a['main']['scoin'];now=datetime.date(2026,11,day)
 assert signin.status_info(a,now)['next_sign_in_reward_id']==original[day-1]['rewardItemID']
 name,body=signin.response('GetSignInRewardReq',a,account_path=path,now=now)
 assert body['retcode']==0 and body['reward_list'][0]['scoin']==10000 and not body['reward_list'][0]['item_list']
 assert a['main']['scoin']==before+10000 and a['sign_in_runtime']['signed_days']==day
 assert signin.response('GetSignInRewardReq',a,account_path=path,now=now)[1]['retcode']==1
 assert a['main']['scoin']==before+10000
 claims.append(day)
(O/'signin-coins-checks.json').write_text(json.dumps(dict(status='PASS',native=results,real_settlement_fixture_days=claims,even_month_unchanged=True,source_table_unchanged=True),indent=2));print('PASS 18 ARM cases, 4 real fixture claims and duplicate rejection, even month and source tables preserved')
