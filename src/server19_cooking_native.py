"""Scoped ARM cooking currency adapter over widgets-fixed, no deployment."""

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
from server19_arm_native import ArmImage,ArmCode,arm_branch,word,unwind_for_push
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'server19-run/sakura-cooking-20261026'
SOURCE=ROOT/'server19-run/xuanyuan-20261025/followup/libil2cpp.widgets-fixed.so'
SHA='db849e6b8ca9cfa4ad7b4895916d7f1e8ed42524ef89c1c2411335eec2950da4'
def build():
    im=ArmImage(SOURCE,SHA)
    def u32(va):return struct.unpack('<I',im.read(va,4))[0]
    def slot(ldr_a,ldr_b,add):
        # Original A32 LDR literal pair + ADD pc + indexed GOT load.
        wa,wb=u32(ldr_a),u32(ldr_b)
        assert wa&0xfffff000==0xe59f0000 and wb&0xfffff000==0xe59f1000
        return (add+8+u32(ldr_a+8+(wa&4095))+u32(ldr_b+8+(wb&4095)))&0xffffffff
    usage=slot(0x13eb340,0x13eb344,0x13eb348)
    klass=slot(0x13eb364,0x13eb368,0x13eb36c)
    method=slot(0x13eb394,0x13eb398,0x13eb39c)
    target=im.allocate_code('cooking_scoin_balance',256,unwind=unwind_for_push(0x4010))
    c=ArmCode(target)
    c.push(0x4010)
    def indirect(reg,address):
        delta=(address-(c.pc+16))&0xffffffff
        c.movw(reg,delta&65535);c.movt(reg,delta>>16)
        c.emit(0xe08f0000|(reg<<12)|reg)
        c.load(reg,reg);c.load(reg,reg)
    indirect(0,usage);c.call(0x42e020)
    indirect(0,klass);c.load(1,0,0xb1,byte=True);c.emit(0xe3110001)
    c.branch('class_ready',cond='eq');c.load(1,0,0x60);c.emit(0xe3510000)
    c.branch('class_ready',cond='ne');c.call(0x42e02c)
    c.label('class_ready');indirect(1,method);c.immediate(0,0);c.call(0x1d41440)
    c.emit(0xe3500000);c.branch('done',cond='eq')
    c.immediate(1,0);c.call(im.method(70411));c.emit(0xe3500000);c.branch('done',cond='eq')
    c.load(0,0,im.field_offset('MoleMole.PlayerDataItem','scoin'))
    c.label('done');c.pop(0x8010)
    code=c.finish();im.patch(target,bytes(len(code)),code,'Read real player coin balance for cooking only')
    count=0
    for mid in (86130,78240):
        sites=[i.address for i in im.disasm(mid) if i.mnemonic=='bl' and i.op_str=='#'+hex(im.method(70891))]
        assert len(sites)==1
        va=sites[0]
        original=ArmImage();start,end=im.method_range(72869)
        if not count: assert im.read(start,end-start)==original.read(start,end-start)
        veneer=im.near_veneer(va,target,storage_mid=72869,name='cooking-coin-tail')
        im.patch(va,im.read(va,4),arm_branch(va,veneer,link=True),'Cooking currency balance');count+=1
    sites=[i.address for i in im.disasm(86130) if i.mnemonic=='bl' and i.op_str=='#'+hex(im.method(82449))]
    assert len(sites)==1
    icon=im.allocate_code('cooking_coin_icon_path',128,unwind=unwind_for_push(0x4010))
    ic=ArmCode(icon);ic.push(0x4010)
    text_va=icon+80
    delta=(text_va-(ic.pc+16))&0xffffffff
    ic.movw(0,delta&65535);ic.movt(0,delta>>16);ic.emit(0xe08f0000)
    ic.call(im.symbol('il2cpp_string_new'));ic.pop(0x8010)
    raw=ic.finish();im.patch(icon,bytes(len(raw)),raw,'Cooking icon returns managed string, not Sprite')
    raw=b'SpriteOutput/GeneralIcon/IconSC\x00';im.patch(text_va,bytes(len(raw)),raw,'Existing coin sprite path')
    va=sites[0];veneer=im.near_veneer(va,icon,storage_mid=72869,name='cooking-icon-tail')
    im.patch(va,im.read(va,4),arm_branch(va,veneer,link=True),'Cooking coin icon')
    im.finalize();dest=OUT/'libil2cpp.cooking-coins.so';dest.write_bytes(im.data)
    report=dict(source_sha256=SHA,sha256=hashlib.sha256(im.data).hexdigest(),patches=im.changes,allocations=im.allocations,usage=usage,klass=klass,method=method)
    (OUT/'native-currency-patch.json').write_text(json.dumps(report,indent=2))
    print('PASS built scoped cooking coin adapter',dest)
if __name__=='__main__':build()
