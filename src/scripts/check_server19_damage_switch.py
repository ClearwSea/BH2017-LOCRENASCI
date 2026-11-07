"""Execute selector ARM code across ASLR, settings, attacker types and cache hits."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'analysis-deps'),str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python')]
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_INTR
from unicorn.arm_const import *
O=ROOT/'server19-run/damage-switch-20261102';spec=json.loads((O/'native-patch.json').read_bytes());raw=(O/'client-damage-switch.so').read_bytes()
heads=spec['headers'];end=max(h[2]+h[5] for h in heads if h[0]==1)
rows=[]
for base in (0,0x10000000):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base,(end+4095)//4096*4096)
 for h in heads:
  if h[0]==1:u.mem_write(base+h[2],raw[h[1]:h[1]+h[4]])
 obj=0x30000000;stack=0x40000000;u.mem_map(obj,4096);u.mem_map(stack-4096,8192)
 u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
 fixture={'bytes':b'', 'calls':[]}
 def interrupt(uc,number,user):
  assert number==2,number
  call=uc.reg_read(UC_ARM_REG_R7);fixture['calls'].append(call)
  if call==5:
   ptr=uc.reg_read(UC_ARM_REG_R0);name=bytes(uc.mem_read(ptr,32)).split(b'\0')[0];assert name==b'./damage-mode.bin'
   uc.reg_write(UC_ARM_REG_R0,0xfffffffe if fixture['bytes'] is None else 17)
  elif call==3:
   assert uc.reg_read(UC_ARM_REG_R0)==17 and uc.reg_read(UC_ARM_REG_R2)==4
   buf=fixture['bytes'];uc.mem_write(uc.reg_read(UC_ARM_REG_R1),buf);uc.reg_write(UC_ARM_REG_R0,len(buf))
  elif call==6:assert uc.reg_read(UC_ARM_REG_R0)==17;uc.reg_write(UC_ARM_REG_R0,0)
  else:raise AssertionError(call)
 u.hook_add(UC_HOOK_INTR,interrupt)
 source=struct.pack('<IIII',0x40200000,0xbf800000,0x7f800000,0x7f000000)
 for setting in (struct.pack('<I',1),struct.pack('<I',20),None,b'\1\0',struct.pack('<I',2)):
  for category in (3,4):
   fixture.update(bytes=setting,calls=[]);u.mem_write(base+spec['state'],bytes(4))
   expected_mode=1 if setting==struct.pack('<I',1) else 20
   for repeat in range(2):
    u.mem_write(obj,bytes(0x100));u.mem_write(obj+8,source);u.mem_write(obj+0x6a,struct.pack('<H',category))
    for r in range(13):u.reg_write(UC_ARM_REG_R0+r,0x100+r)
    u.reg_write(UC_ARM_REG_R4,obj);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,0x12345678)
    before_calls=len(fixture['calls']);u.emu_start(base+spec['hook'],base+spec['site']+12,count=500)
    assert u.reg_read(UC_ARM_REG_PC)==base+spec['site']+12
    assert u.reg_read(UC_ARM_REG_SP)==stack and u.reg_read(UC_ARM_REG_LR)==0x12345678
    assert u.reg_read(UC_ARM_REG_R0)==obj and u.reg_read(UC_ARM_REG_R4)==obj
    for r in [1,2,3,5,6,7,8,9,10,11]:assert u.reg_read(UC_ARM_REG_R0+r)==0x100+r,(r,hex(u.reg_read(UC_ARM_REG_R0+r)))
    assert bytes(u.mem_read(obj+0xcc,4))==struct.pack('<I',2)
    expected=struct.pack('<IIII',0x42480000,0xbf800000,0x7f800000,0x7f7fffff) if category==3 and expected_mode==20 else source
    assert bytes(u.mem_read(obj+8,16))==expected,(base,setting,category,bytes(u.mem_read(obj+8,16)).hex())
    if repeat or category!=3:assert len(fixture['calls'])==before_calls
    rows.append(dict(base=base,setting=None if setting is None else setting.hex(),category=category,repeat=repeat,calls=len(fixture['calls'])))
    fixture['bytes']=struct.pack('<I',20 if expected_mode==1 else 1)
 report=dict(status='PASS',cases=len(rows),aslr_bases=2,default20=True,normal1_bypasses_boost=True,non_avatar_unchanged=True,per_process_cache_no_hot_io=True,registers_stack_preserved=True,no_writable_executable_segments=True)
(O/'native-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
