"""Add a per-process 1x/20x selector without changing the accepted damage helper."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,hashlib,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'analysis-deps')]
import server19_arm_native as n
from server19_arm_resources import module_base,jump
OUT=ROOT/'server19-run/damage-switch-20261102'
SOURCE_SHA='698a38e080033fe057d840f9f72d3ac3827d51f15896cd1d7079c70101c7fcd9'

def build():
    im=n.ArmImage(OUT/'client-before.so',SOURCE_SHA)
    site=0x9e1f64; old=0x61b7600
    assert im.read(site,12)==n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(old-site-12)
    assert im.read(old+20,8)==bytes.fromhex('000000e3a00144e3')
    state=im.append_va+0x200000
    hook=im.allocate_code('Process-fixed damage mode selector',512,unwind=n.unwind_for_push(0x40f0,28))
    path=hook+448
    c=n.ArmCode(hook);c.push(0x40f0);c.emit(0xe24dd01c)
    for r in range(4):c.store(r,13,8+4*r)
    c.emit(0xe1d406ba);c.emit(0xe3500003);c.branch('boost',cond='ne')
    module_base(c,6);c.immediate(12,state);c.emit(0xe086600c);c.load(5,6)
    c.emit(0xe3550000);c.branch('resolved',cond='ne')
    c.immediate(5,20)
    module_base(c,0);c.immediate(1,path);c.emit(0xe0800001);c.immediate(1,0);c.immediate(7,5);c.emit(0xef000000)
    c.emit(0xe3500000);c.branch('cache',cond='lt');c.mov(4,0)
    c.mov(1,13);c.immediate(2,4);c.immediate(7,3);c.emit(0xef000000);c.mov(3,0)
    c.mov(0,4);c.immediate(7,6);c.emit(0xef000000)
    c.emit(0xe3530004);c.branch('cache',cond='ne');c.load(0,13)
    c.emit(0xe3500001);c.branch('valid',cond='eq');c.emit(0xe3500014);c.branch('cache',cond='ne')
    c.label('valid');c.mov(5,0)
    c.label('cache');c.store(5,6)
    c.label('resolved');c.emit(0xe3550001);c.branch('boost',cond='ne')
    for r in range(4):c.load(r,13,8+4*r)
    c.emit(0xe28dd01c);c.pop(0x40f0)
    c.emit(0xe3a00002);c.emit(0xe58400cc);c.emit(0xe1a00004);jump(c,site+12)
    c.label('boost')
    for r in range(4):c.load(r,13,8+4*r)
    c.emit(0xe28dd01c);c.pop(0x40f0);jump(c,old)
    code=c.finish();assert len(code)<=448
    im.patch(hook,bytes(len(code)),code,'Read validated private mode once per process; preserve original 20x path')
    name=b'./damage-mode.bin\0';im.patch(path,bytes(len(name)),name,'Relative private startup setting; no save fields')
    im.patch(site,im.read(site,12),n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-site-12),'Select original finalization or accepted 20x helper')
    im.finalize();data=im.data;headers=[h[:] for h in im.final_program_headers];phoff=struct.unpack_from('<I',data,28)[0]
    data.extend(bytes(32));rw_off=n.align(len(data));assert im.append_va+len(data)-im.append_offset<state
    for h in headers:
        if h[0]==6:h[4]+=32;h[5]+=32
        if h[0]==1 and h[1]==im.append_offset:h[4]+=32;h[5]+=32
    headers.append([1,rw_off,state,state,4096,4096,6,4096])
    data[phoff:phoff+32*len(headers)]=b''.join(struct.pack('<8I',*h) for h in headers)
    struct.pack_into('<H',data,44,len(headers));data.extend(bytes(rw_off+4096-len(data)))
    assert not any(h[0]==1 and h[6]&3==3 for h in headers),'No writable executable segment'
    output=OUT/'client-damage-switch.so';assert not output.exists();output.write_bytes(data)
    report=dict(source_sha256=SOURCE_SHA,sha256=hashlib.sha256(data).hexdigest(),site=site,old_helper=old,hook=hook,state=state,path=path,code_bytes=len(code),rw_offset=rw_off,rw_va=state,default=20,modes=[1,20],read_policy='first avatar finalization once per process',source_manifest=im.manifest(),headers=headers)
    (OUT/'native-patch.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k not in ['source_manifest','headers']},indent=2))
if __name__=='__main__':build()
