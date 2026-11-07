"""Run original and fixed ARM snippets for valid/missing sign-in items."""

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
ROOT=Path(__file__).resolve().parents[1];REF=ROOT
sys.path[:0]=[str(REF),str(REF/'analysis-deps'),str(REF/'.local-baseline/server19-dev/story-goal-tools/python')]
from server19_arm_native import ArmImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
O=ROOT/'server19-run/nx-backport-20261102';spec=json.loads((O/'signin-patch.json').read_bytes());results=[]
for fixed in (False,True):
 im=ArmImage(O/'client-signin.so' if fixed else O/'client-before.so',spec['sha256'] if fixed else 'f6d721fe4d4a75192a50b473426b52b344d84ef691be02f600c746a190433a9c')
 for base in (0,0x10000000):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base+0x10c0000,0x10000);u.mem_write(base+0x10c0000,im.read(0x10c0000,0x10000));h=base+0x9000000;u.mem_map(h,0x10000)
  stop=base+0x10cff00
  def hook(uc,addr,size,data):
   if addr in (stop,base+0x42e0a4,base+0x10c1928,base+0x10c1850,base+0x10c1fdc):uc.emu_stop()
  u.mem_map(base+0x42e000,0x1000);u.hook_add(UC_HOOK_CODE,hook)
  for slot,site in enumerate(spec['sites']):
   for present in (False,True):
    obj=h+0x100;reward=h+0x200;item=h+0x300 if present else 0;stack=h+0xf000;quantity=20+slot
    u.mem_write(obj,bytes(128));u.mem_write(reward,bytes(128));u.mem_write(obj+0x14,struct.pack('<I',reward));u.mem_write(reward+0x30+12*slot,struct.pack('<I',quantity))
    saved=[0x111,0x222,0x333,0x444,0x555,stop];u.mem_write(stack,struct.pack('<6I',*saved));u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_R4,obj);u.reg_write(UC_ARM_REG_R0,item)
    u.emu_start(base+site-16,0xffffffff,count=40);pc=u.reg_read(UC_ARM_REG_PC)
    if present or fixed:
     assert pc==stop and u.reg_read(UC_ARM_REG_SP)==stack+24
     assert [u.reg_read(x) for x in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R10,UC_ARM_REG_R11]]==saved[:5]
     assert int.from_bytes(u.mem_read(obj+0x1c,4),'little')==quantity
     if present:assert int.from_bytes(u.mem_read(item+0x20,4),'little')==quantity
    else:assert pc==base+0x42e0a4
    results.append(dict(fixed=fixed,base=base,slot=slot+1,present=present,throws=pc==base+0x42e0a4))
  for present in (False,True):
   u.mem_write(h+0x118,struct.pack('<I',h+0x300 if present else 0));u.reg_write(UC_ARM_REG_R4,h+0x100);u.reg_write(UC_ARM_REG_R8,8)
   u.emu_start(base+0x10c183c,0xffffffff,count=10)
   assert u.reg_read(UC_ARM_REG_PC)==base+(0x10c1850 if present else (0x10c1928 if fixed else 0x10c1fdc))
(O/'signin-data-checks.json').write_text(json.dumps(dict(status='PASS',cases=results,icon_cases=8),indent=2));print('PASS: 40 data cases + 8 icon routing cases; baseline null failure reproduced; saved registers/stack/quantities checked')
