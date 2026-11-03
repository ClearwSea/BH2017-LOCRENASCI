"""Bounded original-dialog deferral and native loading of the PCM story bank."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
import hashlib
import struct
from pathlib import Path
import server19_arm_native as n
from server19_arm_resources import module_base, jump
from server19_story_all_resources import WORK

OUT = WORK/'act2-batch-failures-v1'


def add_rw_page(path, va):
    data=bytearray(path.read_bytes());header=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    headers=[list(struct.unpack_from('<8I',data,header[5]+i*32)) for i in range(header[10])]
    assert va >= max(p[2]+p[5] for p in headers if p[0]==1)
    offset=n.align(len(data));data.extend(bytes(offset+4096-len(data)))
    table_offset=offset+2048;table_va=va+2048;count=len(headers)+1
    for p in headers:
        if p[0]==6:p[1:6]=[table_offset,table_va,table_va,count*32,count*32]
    headers.append([1,offset,va,va,4096,4096,6,4096])
    assert count*32 <= 2048
    for i,p in enumerate(headers):struct.pack_into('<8I',data,table_offset+i*32,*p)
    struct.pack_into('<I',data,28,table_offset);struct.pack_into('<H',data,44,count)
    path.write_bytes(data)
    return {'offset':offset,'va':va,'bytes':4096,'permissions':'RW, not executable','program_headers':count}


def build():
    params = n.metadata.M[44723]
    names = [n.metadata.string(struct.unpack_from('<4I', n.metadata.B, 7818260+(params[3]+i)*16)[0]) for i in range(params[15])]
    assert names == ['in_pszString','in_memPoolId','out_bankID']
    source=WORK/'ui-context-trace-v1/libil2cpp.so'
    image=n.ArmImage(source,expected_sha256=None)
    state_va=n.align(image.append_va+0x1000000)
    originals=n.ArmImage()
    def state(c,reg=4):
        module_base(c,reg);c.immediate(12,state_va);c.emit(0xe080000c|(reg<<16)|(reg<<12))
    def text(value):
        raw=value.encode()+b'\0';va=image.allocate_code('text '+value,len(raw),align_to=4)
        image.patch(va,bytes(len(raw)),raw,'Read-only log/path literal');return va
    def string(c,va):
        module_base(c,0);c.immediate(12,va);c.emit(0xe080000c);c.call(image.symbol('il2cpp_string_new'))
    def log(c,va):
        string(c,va);c.mov(1,0);c.immediate(0,0);c.immediate(2,0);c.call(image.method(18021))
    queued=text('BH3ARM_UI_DEFER queued GeneralDialogContext')
    replayed=text('BH3ARM_UI_DEFER replayed GeneralDialogContext')
    bank_path=text('/sdcard/bh3-server19-audio/')
    bank_name=text('server19_story_voice.bnk')
    loaded=text('BH3ARM_STORY_AUDIO original113 PCM bank loaded')
    failed=text('BH3ARM_STORY_AUDIO bank load failed; original playback retained')
    entry=image.method(66343);before=image.read(entry,12)
    assert before[:8]==n.word(0xe59fc000)+n.word(0xe08ff00c)
    previous=entry+12+struct.unpack('<i',before[8:12])[0]
    frame=n.unwind_for_push(0x41f0,24) # r0..r8,lr +8 locals =48 bytes
    hook=image.allocate_code('defer only evidenced GeneralDialogContext',2048,unwind=frame)
    c=n.ArmCode(hook);c.push(0x41ff);c.emit(0xe24dd008)
    c.emit(0xe3500000);c.branch('original',cond='eq')
    c.load(2,0,0x50);c.emit(0xe3520000);c.branch('original',cond='ne')
    c.emit(0xe3510000);c.branch('original',cond='eq')
    c.mov(0,1);c.call(image.symbol('il2cpp_object_get_class'));c.call(image.symbol('il2cpp_class_get_name'));c.mov(6,0)
    c.emit(0xe3560000);c.branch('original',cond='eq')
    for index,byte in enumerate(b'GeneralDialogContext\0'):
        c.load(0,6,index,byte=True);c.emit(0xe3500000|byte);c.branch('original',cond='ne')
    state(c);c.emit(0xe2845040);c.immediate(6,8)
    c.label('slot');c.load(0,5,0);c.emit(0xe3500000);c.branch('found',cond='eq')
    c.emit(0xe2855010);c.emit(0xe2566001);c.branch('slot',cond='ne');c.branch('original')
    c.label('found')
    c.load(0,13,8);c.immediate(1,0);c.call(image.symbol('il2cpp_gchandle_new'));c.store(0,5,0)
    c.load(0,13,12);c.immediate(1,0);c.call(image.symbol('il2cpp_gchandle_new'));c.store(0,5,4)
    c.load(0,13,16);c.store(0,5,8);c.load(0,13,20);c.store(0,5,12)
    log(c,queued);c.emit(0xe28dd008);c.pop(0x81ff)
    c.label('original');c.emit(0xe28dd008);c.pop(0x41ff);jump(c,previous)
    code=c.finish();assert len(code)<=2048;image.patch(hook,bytes(len(code)),code,'Root context until original canvas is ready; no UI suppression')
    image.patch(entry,before,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-entry-12),'Only defer GeneralDialogContext when SceneCanvas pointer is null')

    mid=66338;entry=image.method(mid);before=image.read(entry,12)
    assert before==originals.read(originals.method(mid),12)
    trampoline=image.allocate_code('SetMainCanvas original prologue',64,unwind=1)
    t=n.ArmCode(trampoline);t.emit(before);jump(t,entry+12);raw=t.finish();image.patch(trampoline,bytes(len(raw)),raw,'Original canvas initialization continuation')
    # At the relocated prologue, use the original function's unwind descriptor.
    old_unwind=next(r for r in originals.exidx if r['function_va']==originals.method(mid))
    image.unwinds=[r for r in image.unwinds if r[0]!=trampoline]
    if old_unwind['extab_va'] is None:image.register_unwind(trampoline,old_unwind['descriptor'])
    else:image.register_unwind_external(trampoline,old_unwind['extab_va'])
    hook=image.allocate_code('replay after original SetMainCanvas completes',2048,unwind=frame)
    c=n.ArmCode(hook);c.push(0x41ff);c.emit(0xe24dd008);c.call(trampoline)
    c.load(4,13,8);c.load(0,4,0x50);c.emit(0xe3500000);c.branch('done',cond='eq')
    state(c,5);c.emit(0xe2855040);c.immediate(6,8)
    c.label('next');c.load(7,5,0);c.emit(0xe3570000);c.branch('advance',cond='eq')
    c.mov(0,7);c.call(image.symbol('il2cpp_gchandle_get_target'));c.emit(0xe1500004);c.branch('advance',cond='ne')
    c.load(8,5,4);c.mov(0,8);c.call(image.symbol('il2cpp_gchandle_get_target'));c.mov(1,0)
    c.mov(0,4);c.load(2,5,8);c.load(3,5,12)
    c.immediate(12,0);c.store(12,5,0);c.store(12,5,4)
    c.call(image.method(66343))
    c.mov(0,7);c.call(image.symbol('il2cpp_gchandle_free'));c.mov(0,8);c.call(image.symbol('il2cpp_gchandle_free'));log(c,replayed)
    c.label('advance');c.emit(0xe2855010);c.emit(0xe2566001);c.branch('next',cond='ne')
    c.label('done');c.emit(0xe28dd008);c.pop(0x81ff)
    code=c.finish();image.patch(hook,bytes(len(code)),code,'Run original dialog/callbacks after actual canvas initialization')
    image.patch(entry,before,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-entry-12),'Preserve original SetMainCanvas, then drain bounded matching-manager queue')

    # Tail wrapper does not alter Post's callbacks, stack arguments, return value,
    # mute/stop/skip handling, or the original event name.
    entry=image.method(66659);before=image.read(entry,12);assert before==originals.read(originals.method(66659),12)
    hook=image.allocate_code('load PCM voice bank before native story Post',2048,unwind=frame)
    c=n.ArmCode(hook);c.push(0x41ff);c.emit(0xe24dd008)
    c.emit(0xe3510000);c.branch('original',cond='eq')
    c.load(0,1,8);c.emit(0xe350000a);c.branch('original',cond='lt')
    prefix='VO_Dialog_'.encode('utf-16le')
    for off in range(0,len(prefix),4):
        c.load(0,1,12+off);c.immediate(2,int.from_bytes(prefix[off:off+4],'little'));c.emit(0xe1500002);c.branch('original',cond='ne')
    state(c);c.load(0,4,16);c.emit(0xe3500000);c.branch('original',cond='ne')
    c.immediate(0,2);c.store(0,4,16)
    string(c,bank_path);c.mov(1,0);c.immediate(0,0);c.immediate(2,0);c.call(image.method(44877))
    string(c,bank_name);c.mov(1,0);c.immediate(0,0);c.store(0,13,0);c.emit(0xe28d3004);c.immediate(2,0xffffffff);c.call(image.method(44723))
    c.emit(0xe3500001);c.branch('failed',cond='ne')
    c.immediate(0,1);c.store(0,4,16);log(c,loaded);c.branch('original')
    c.label('failed');log(c,failed)
    c.label('original');c.emit(0xe28dd008);c.pop(0x41ff);c.emit(before);jump(c,entry+12)
    code=c.finish();image.patch(hook,bytes(len(code)),code,'Only load extra real-media bank; retain all native Post behavior')
    image.patch(entry,before,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-entry-12),'Native story-bank availability')
    path=OUT/'presentation-native-v3/libil2cpp.so';image.save(path)
    rw=add_rw_page(path,state_va)
    manifest_path=path.with_suffix(path.suffix+'.json')
    manifest=json.loads(manifest_path.read_bytes())
    manifest.update(output_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),output_bytes=path.stat().st_size,extra_rw_segment=rw)
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')

    # Re-read ELF to verify all registration and unwind invariants still parse.
    verified=n.ArmImage(path,expected_sha256=None)
    assert any(p[0]==1 and p[2]==state_va and p[6]==6 for p in verified.program_headers)
    assert not any(p[0]==1 and p[6]&3==3 for p in verified.program_headers)
    report={'status':'prepared_human_pending','dialog_scope':'GeneralDialogContext with null SceneCanvas only',
            'queue_slots':8,'strong_GC_handles':True,'replay':'after original SetMainCanvas; original ShowDialog and callbacks',
            'other_UI_untouched':True,'voice_path':'original AkSoundEngine AddBasePath/LoadBank, original WwiseAudioManager.Post',
            'RW_state':rw,'no_RWX':True,'native_playback_pending':True}
    (OUT/'presentation-native-v3/report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':build()
