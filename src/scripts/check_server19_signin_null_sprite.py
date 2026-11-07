"""Execute the real sign-in call site and Image.set_sprite null branch."""

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
O=ROOT/'server19-run/nx-backport-20261102';spec=json.loads((O/'signin-patch.json').read_bytes());im=ArmImage(O/'client-signin.so',spec['sha256']);rows=[]
for base in (0,0x10000000):
 for path_present,image_present,old_sprite in [(False,True,0),(False,True,123),(False,False,0),(True,True,123),(True,False,0)]:
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base,0x8000000)
  for seg in im.loads:u.mem_write(base+seg[2],im.read(seg[2],seg[4]))
  h=base+0x9000000;u.mem_map(h,0x10000)
  def w(a,v):u.mem_write(a,struct.pack('<I',v))
  obj=h+0x100 if image_present else 0;path=h+0x200 if path_present else 0;stack=h+0xf000
  if obj:w(obj,h+0x300);w(obj+0x68,old_sprite)
  w(h+0x348,h+0x600);w(h+0x6a8,h+0x800);w(h+0x6ac,h+0x900)
  literal=lambda va:int.from_bytes(im.read(va,4),'little')
  slot=(base+0x250c7b4+literal(0x250c814)+literal(0x250c818))&0xffffffff;w(slot,h+0x400);w(h+0x400,h+0x500)
  u.reg_write(UC_ARM_REG_R0,path);u.reg_write(UC_ARM_REG_R7,obj);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_R4,0x444);u.reg_write(UC_ARM_REG_R5,0x555)
  calls=[]
  def hook(uc,a,size,data):
   pc=a-base
   if pc==0x10c1758:uc.emu_stop();return
   if pc==0x163d86c:
    assert path_present and [uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]==[0,obj,path,0];calls.append('original-path-loader');uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
   elif pc==0x250c75c:
    # Engine metadata initialization is outside the behavior under test.
    assert uc.reg_read(UC_ARM_REG_R1)==0;uc.reg_write(UC_ARM_REG_R5,0);uc.reg_write(UC_ARM_REG_PC,base+0x250c7a0);calls.append('Image.set_sprite(null)')
   elif pc==0x287e8f4:
    # Generic SetPropertyUtility compares and assigns the exact sprite field.
    addr=uc.reg_read(UC_ARM_REG_R1);value=uc.reg_read(UC_ARM_REG_R2);assert addr==obj+0x68 and value==0
    old=int.from_bytes(uc.mem_read(addr,4),'little');w(addr,value);uc.reg_write(UC_ARM_REG_R0,int(old!=value));uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
   elif a==h+0x800:calls.append('SetAllDirty');uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook);u.emu_start(base+0x10c1744,0xffffffff,count=150)
  assert u.reg_read(UC_ARM_REG_PC)==base+0x10c1758 and u.reg_read(UC_ARM_REG_SP)==stack
  assert u.reg_read(UC_ARM_REG_R4)==0x444 and u.reg_read(UC_ARM_REG_R5)==0x555 and u.reg_read(UC_ARM_REG_R7)==obj
  expected=['original-path-loader'] if path_present else (['Image.set_sprite(null)']+(['SetAllDirty'] if old_sprite else []) if image_present else [])
  assert calls==expected,(calls,expected)
  if image_present and not path_present:assert int.from_bytes(u.mem_read(obj+0x68,4),'little')==0
  rows.append(dict(base=base,path_present=path_present,image_present=image_present,old_sprite=old_sprite,calls=calls))
(O/'sprite-checks.json').write_text(json.dumps(dict(status='PASS',cases=rows),indent=2));print('PASS 10 caller/real setter cases, stale sprite cleared, dirty notification, normal loader and ABI preserved')
