"""Execute scoped cooking ARM adapters under two ASLR bases with native API stubs."""

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
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
from server19_arm_native import ArmImage
out=ROOT/'server19-run/sakura-cooking-20261026';r=json.loads((out/'native-currency-patch.json').read_bytes());im=ArmImage(out/'libil2cpp.cooking-coins.so',r['sha256']);cases=[]
for base in (0,0x10000000):
 for kind in ('balance','null_player','icon'):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(base,0x8000000)
  for segment in im.loads:u.mem_write(base+segment[2],im.read(segment[2],segment[4]))
  h=base+0x9000000;u.mem_map(h,0x10000)
  def put(p,v):u.mem_write(p,struct.pack('<I',v))
  for i,key in enumerate(('usage','klass','method')):
   cell=h+0x100+i*4;put(base+r[key],cell);put(cell,73 if key=='usage' else h+0x200 if key=='klass' else h+0x300)
  u.mem_write(h+0x200+0xb1,b'\x01');put(h+0x200+0x60,0);put(h+0x500+40,123456)
  for reg in range(4,12):u.reg_write(UC_ARM_REG_R0+reg,0xabc000+reg)
  u.reg_write(UC_ARM_REG_SP,h+0xf000);u.reg_write(UC_ARM_REG_LR,base+0x12340)
  calls=[]
  def hook(uc,address,size,data):
   pc=address-base
   if pc==0x12340:uc.emu_stop();return
   if pc in (0x42e020,0x42e02c,0x1d41440,im.method(70411),im.symbol('il2cpp_string_new')):
    calls.append(pc)
    if pc==0x42e020:assert uc.reg_read(UC_ARM_REG_R0)==73
    elif pc==0x42e02c:assert uc.reg_read(UC_ARM_REG_R0)==h+0x200
    elif pc==0x1d41440:
     assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R1)==h+0x300
     uc.reg_write(UC_ARM_REG_R0,h+0x400)
    elif pc==im.method(70411):uc.reg_write(UC_ARM_REG_R0,0 if kind=='null_player' else h+0x500)
    else:
     assert bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0),31)).split(b'\0')[0]==b'SpriteOutput/GeneralIcon/IconSC'
     uc.reg_write(UC_ARM_REG_R0,h+0x600)
    uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  purpose='cooking-icon-tail' if kind=='icon' else 'cooking-coin-tail'
  start=next(x['va'] for x in r['patches'] if purpose in x['purpose'])
  u.emu_start(base+start,0xffffffff,count=1000)
  assert u.reg_read(UC_ARM_REG_R0)==(h+0x600 if kind=='icon' else 0 if kind=='null_player' else 123456)
  assert u.reg_read(UC_ARM_REG_SP)==h+0xf000
  assert all(u.reg_read(UC_ARM_REG_R0+reg)==0xabc000+reg for reg in range(4,12))
  cases.append(dict(base=base,kind=kind,calls=calls))
(out/'native-emulation.json').write_text(json.dumps(dict(status='PASS',cases=cases),indent=2));print('PASS',len(cases),'ARM cooking adapter cases, ASLR, null player, managed icon string, stack and saved registers')
