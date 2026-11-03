"""Endless-only floor33 UI guards over the accepted cooking/20x ARM library."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,struct,hashlib
from pathlib import Path
from server19_arm_native import ArmImage,ArmCode,arm_branch,arm_pic_jump,unwind_for_push
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'server19-run/endless-20261026/cap-balance-fix'
SOURCE=ROOT/'server19-run/sakura-cooking-20261026/libil2cpp.cooking-coins.so'
SHA='1cba5fb29bfb8080c17882a133f9eaa41849da98d632a5d54e8f8afb797c32bf'
def build():
 im=ArmImage(SOURCE,SHA);OUT.mkdir(exist_ok=True)
 u=lambda p:struct.unpack('<I',im.read(p,4))[0]
 def slot(a,b,c):return (c+8+u(a+8+(u(a)&4095))+u(b+8+(u(b)&4095)))&0xffffffff
 slots=dict(usage=slot(0xa2daa8,0xa2daac,0xa2dab0),klass=slot(0xa2dacc,0xa2dad0,0xa2dad4),method=slot(0xa2dafc,0xa2db00,0xa2db04))
 def indirect(c,r,p):
  d=(p-(c.pc+16))&0xffffffff;c.movw(r,d&65535);c.movt(r,d>>16);c.emit(0xe08f0000|(r<<12)|r);c.load(r,r);c.load(r,r)
 def save(c,p,description):
  raw=c.finish();im.patch(p,bytes(len(raw)),raw,description)
 progress=im.allocate_code('endless_current_progress',256,unwind=unwind_for_push(0x4010))
 c=ArmCode(progress);c.push(0x4010);indirect(c,0,slots['usage']);c.call(0x42e020)
 indirect(c,0,slots['klass']);c.load(1,0,0xb1,byte=True);c.emit(0xe3110001);c.branch('ready',cond='eq');c.load(1,0,0x60);c.emit(0xe3510000);c.branch('ready',cond='ne');c.call(0x42e02c)
 c.label('ready');indirect(c,1,slots['method']);c.immediate(0,0);c.call(0x1d41440);c.emit(0xe3500000);c.branch('done',cond='eq');c.immediate(1,0);c.call(im.method(68848));c.label('done');c.pop(0x8010);save(c,progress,'Read original Endless progress without changing state')
 # Previous cooking patch uses first 48 bytes; preserve its veneers exactly.
 start,end=im.method_range(72869);im.veneer_cursors[72869]=start+48
 original=ArmImage();assert im.read(start+48,end-start-48)==original.read(start+48,end-start-48)
 entries={}
 for mid,kind in ((78306,'main'),(78287,'prepare'),(78263,'continue')):
  entry=im.method(mid);first=im.read(entry,8)
  assert list(im.disasm(mid))[0].mnemonic=='push' and list(im.disasm(mid))[1].op_str.startswith('fp, sp,')
  tramp=im.allocate_code('endless_original_'+kind,32)
  raw=first+arm_pic_jump(tramp+8,entry+8);im.patch(tramp,bytes(len(raw)),raw,'Replay PC-independent original prologue')
  target=im.allocate_code('endless_cap_'+kind,512,unwind=unwind_for_push(0x4070));c=ArmCode(target);c.push(0x4070);c.mov(4,0);c.mov(5,1)
  if kind=='main':
   c.call(tramp);c.call(progress);c.mov(6,0)
   c.mov(0,4);c.immediate(1,0);c.call(0x7ac6a4);c.emit(0xe3500000);c.branch('done',cond='eq')
   c.immediate(1,0);c.call(0x25838f8);c.emit(0xe3500000);c.branch('done',cond='eq');c.mov(4,0)
   # Path verified from original BindViewCallbacks metadata literal.
   p=target+448;d=(p-(c.pc+16))&0xffffffff;c.movw(0,d&65535);c.movt(0,d>>16);c.emit(0xe08f0000);c.call(im.symbol('il2cpp_string_new'));c.mov(1,0);c.mov(0,4);c.immediate(2,0);c.call(0x25f1568);c.emit(0xe3500000);c.branch('done',cond='eq')
   c.immediate(1,0);c.call(0x2575b4c);c.emit(0xe3500000);c.branch('done',cond='eq');c.immediate(1,1);c.emit(0xe3560021);c.emit(0xa3a01000);c.immediate(2,0);c.call(0x2583c00)
   raw=b'ActionBtns/Prepare\0';im.patch(p,bytes(len(raw)),raw,'Only hide the capped battle entrance, not tools or shop')
  else:
   c.call(progress);c.emit(0xe3500021);c.branch('normal',cond='lt')
   if kind=='continue':c.mov(0,4);c.immediate(1,0);c.call(im.method(78262))
   c.branch('done');c.label('normal');c.mov(0,4);c.mov(1,5);c.call(tramp)
  c.label('done');c.pop(0x8070);save(c,target,'Floor33 boundary '+kind)
  veneer=im.near_veneer(entry,target,storage_mid=72869,name='endless-cap-'+kind)
  im.patch(entry,first[:4],arm_branch(entry,veneer),'Guard original '+kind+' entry')
  entries[kind]=dict(entry=entry,target=target,trampoline=tramp)
 im.finalize();dest=OUT/'libil2cpp.endless-cap.so';dest.write_bytes(im.data)
 report=dict(source_sha256=SHA,sha256=hashlib.sha256(im.data).hexdigest(),slots=slots,progress=progress,entries=entries,patches=im.changes)
 (OUT/'native-patch.json').write_text(json.dumps(report,indent=2));print('PASS built',dest)
if __name__=='__main__':build()
