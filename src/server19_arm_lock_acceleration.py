"""Preserve the source lock-forward speed ramp using original ability params."""

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
import server19_arm_native as n
from server19_arm_resources import module_base,jump
from server19_story_goal_prepare import OUT

KEY='Server19_DefaultAcceleration'
STATE='Server19_LockForwardCurrentSpeed'
SITE=0x92fee0
NEXT=0x92ff08


def build(version='native-lock-acceleration-v1',include_weekly_trace=False):
    image=n.ArmImage(OUT/'native-weekly-voice-v1/libil2cpp.so',expected_sha256=None)
    before=bytes.fromhex('c08ab5ee10faf1ee0600001a');assert image.read(SITE,12)==before
    texts={}
    for name in (KEY,STATE):
        raw=(name+'\0').encode();va=image.allocate_code(name,len(raw),align_to=4)
        image.patch(va,bytes(len(raw)),raw,'Original ability parameter name');texts[name]=va
    def string(c,key,reg):
        module_base(c,0);c.immediate(12,texts[key]);c.emit(0xe080000c)
        c.call(image.symbol('il2cpp_string_new'));c.mov(reg,0)
    def push(c):c.push(0x41ff);c.emit(0xed2d0b12);c.emit(0xe24dd020)
    def pop(c):c.emit(0xe28dd020);c.emit(0xecbd0b12);c.pop(0x41ff)
    def guard(c,missing):
        c.load(4,8,0x10);c.emit(0xe3540000);c.branch(missing,cond='eq')
        string(c,KEY,7)
        # Initialize the original closed Dictionary<string,object> MethodInfo.
        c.mov(0,4);c.mov(1,7);c.immediate(2,0);c.call(image.method(49382))
        c.load(0,4,0x60);c.emit(0xe3500000);c.branch(missing,cond='eq')
        c.load(0,0,0x18);c.emit(0xe3500000);c.branch(missing,cond='eq')
        module_base(c,2);c.immediate(12,0x3451680);c.emit(0xe082200c);c.load(2,2,0);c.load(2,2,0)
        c.mov(1,7);c.call(0x1a2e974);c.emit(0xe3500000);c.branch(missing,cond='eq')
        c.mov(0,4);c.mov(1,7);c.immediate(2,0);c.call(image.method(49383));c.mov(6,0)
        string(c,STATE,5)
    def set_state(c,value_reg):
        c.store(value_reg,13,20)
        c.mov(0,4);c.immediate(1,0);c.call(image.method(49388))
        c.mov(0,4);c.mov(1,5);c.load(2,13,20);c.immediate(3,0);c.call(image.method(49384))
    unwind=n.unwind_for_push(0x41f0,120)  # caller16 + VFP72 + locals32; then saved r4-r8/lr24
    hook=image.allocate_code('source lock-forward acceleration Core',4096,unwind=unwind)
    c=n.ArmCode(hook);push(c);guard(c,'unmarked')
    c.store(6,13,8)
    c.emit(0xed9d0a18);c.emit(0xeeb50ac0);c.emit(0xeef1fa10);c.branch('reset',cond='ne')
    c.load(0,13,124);c.load(0,0,8,byte=True);c.emit(0xe3500000);c.branch('reset',cond='eq')
    c.load(0,8,0x24);c.load(0,0,0x1c);c.store(0,13,16)
    c.mov(0,4);c.mov(1,5);c.immediate(2,0);c.call(image.method(49383));c.store(0,13,12)
    c.immediate(0,0);c.immediate(1,0);c.call(image.method(18442));c.store(0,13,4)
    c.load(0,8,0x34);c.immediate(1,0);c.call(image.method(61585));c.store(0,13,0)
    c.emit(0xed9d0a02);c.emit(0xeddd0a01);c.emit(0xee200a20)
    c.emit(0xeddd0a00);c.emit(0xee200a20);c.emit(0xeddd0a03);c.emit(0xee300a20)
    c.immediate(0,0);c.load(1,13,16);c.emit(0xee102a10);c.immediate(3,0);c.call(image.method(17431))
    set_state(c,0);c.load(0,13,20);c.store(0,13,96);c.branch('marked')
    c.label('reset');c.immediate(0,0);set_state(c,0)
    c.label('marked');pop(c);jump(c,NEXT)
    c.label('unmarked');pop(c);c.emit(before[:8]);c.branch('nonzero',cond='ne')
    jump(c,SITE+12);c.label('nonzero');jump(c,NEXT)
    code=c.finish();image.patch(hook,bytes(len(code)),code,'min(defaultSpeed,currentSpeed+acceleration*deltaTime*entityTimeScale); reset on other motion/input')
    image.patch(SITE,before,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-SITE-12),'Opt-in original lock-forward speed ramp')
    entry=image.method(48536);old=image.read(entry,12);assert old.hex()=='30482de908b08de20040a0e1'
    added=image.allocate_code('reset tagged acceleration state on actual mixin OnAdded',2048,unwind=unwind)
    c=n.ArmCode(added);push(c);c.mov(8,0);guard(c,'resume');c.immediate(0,0);set_state(c,0)
    c.label('resume');pop(c);c.emit(old);jump(c,entry+12)
    body=c.finish();image.patch(added,bytes(len(body)),body,'Use original ActorAbility override map lifecycle, no external object cache')
    image.patch(entry,old,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(added-entry-12),'Reset the marked state before original OnAdded')
    from server19_arm_weekly_voice import extend_trace_guards
    traces=extend_trace_guards(image) if include_weekly_trace else []
    output=OUT/version/'libil2cpp.so';image.save(output)
    report={'status':'prepared_human_pending','site':SITE,'next':NEXT,'hook':hook,'on_added_site':entry,'on_added_hook':added,
            'key':KEY,'state':STATE,'source_formula':'min(DefaultSpeed,currentSpeed+DefaultAcceleration*Time.deltaTime*avatar.TimeScale)',
            'source_evidence':'source-lock-forward-Core.asm 026c179b..026c1892',
            'state_storage':'Original ActorAbility override map; reset on original OnAdded; freed with ability',
            'unmarked_original_flow_retained':True,'frame_bytes':144,'saved_s16_offset':96,
            'native_methods':{str(i):image.method(i) for i in (49382,49383,49384,49388,18442,61585,17431)},
            'string_new':image.symbol('il2cpp_string_new'),'contains':0x1a2e974,'methodinfo_got':0x3451680,'weekly_trace_guards':traces}
    (output.parent/'bridge.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--version',default='native-lock-acceleration-v2');args=p.parse_args()
    print(json.dumps(build(args.version,include_weekly_trace=True)))
