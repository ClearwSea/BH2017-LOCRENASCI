"""Extend the existing story-bank guard to real Weekly dialogue events."""

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
import struct
import server19_arm_native as n
from server19_arm_resources import jump
from server19_story_goal_prepare import OUT,WORK

SITE = 0x3d98158
LOAD = 0x3d981d0
ORIGINAL = 0x3d98300
PREFIXES = ('VO_Dialog_', 'VO_Weekly_Dialog_')


def extend_trace_guards(image):
    old=json.loads((WORK/'act2-batch-failures-v1/voice-return-trace-v1/libil2cpp.so.json').read_bytes())
    records=[]
    for allocation in old['allocations']:
        if not allocation['name'].startswith('actual story '):continue
        va=allocation['va'];site=va+12
        assert image.read(site,4)==n.word(0xe3560000)
        instructions=image.disasm(va=va,size=180)
        original=int(next(x.op_str for x in instructions if x.mnemonic=='beq').removeprefix('#'),16)
        target=next(x.address for x in instructions if x.mnemonic=='ldr' and x.op_str.startswith('r5, [sp'))
        hook=image.allocate_code('Weekly '+allocation['name']+' guard',2048,unwind=n.unwind_for_push(0x41f0,144))
        c=n.ArmCode(hook);c.emit(0xe3560000);c.branch('original',cond='eq')
        for i,prefix in enumerate(PREFIXES):
            c.load(0,6,8);c.immediate(1,len(prefix));c.emit(0xe1500001);c.branch('next'+str(i),cond='lt')
            raw=prefix.encode('utf-16le')
            for off in range(0,len(raw),4):
                part=raw[off:off+4];offset=12+off
                if len(part)==4:c.load(0,6,offset)
                else:c.emit(0xe1d600b0|((offset&0xf0)<<4)|(offset&15))
                c.immediate(1,int.from_bytes(part,'little'));c.emit(0xe1500001);c.branch('next'+str(i),cond='ne')
            jump(c,target);c.label('next'+str(i))
        c.label('original');jump(c,original)
        body=c.finish();image.patch(hook,bytes(len(body)),body,'Extend existing audio evidence to Weekly without changing Post/returns')
        image.patch(site,image.read(site,12),n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-site-12),'Weekly diagnostic coverage')
        records.append({'site':site,'load':target,'original':original,'event_reg':6,'kind':allocation['name']})
    assert len(records)==2
    return records


def build():
    image=n.ArmImage(OUT/'native-shield-cap-v1/libil2cpp.so',expected_sha256=None)
    expected=bytes.fromhex('000051e36700000a080091e5')
    assert image.read(SITE,12)==expected
    # This guard runs after the existing hook's original 48-byte stack frame.
    hook=image.allocate_code('include Weekly dialogue in original story-bank loader',2048,
                             unwind=n.unwind_for_push(0x41f0,48))
    c=n.ArmCode(hook)
    c.emit(0xe3510000);c.branch('original',cond='eq')
    for i,prefix in enumerate(PREFIXES):
        c.load(0,1,8);c.immediate(2,len(prefix));c.emit(0xe1500002);c.branch('next'+str(i),cond='lt')
        raw=prefix.encode('utf-16le')
        for off in range(0,len(raw),4):
            part=raw[off:off+4];offset=12+off
            if len(part)==4:c.load(0,1,offset)
            else:
                assert len(part)==2 and offset<256
                c.emit(0xe1d100b0 | ((offset&0xf0)<<4) | (offset&15))
            c.immediate(2,int.from_bytes(part,'little'));c.emit(0xe1500002);c.branch('next'+str(i),cond='ne')
        jump(c,LOAD)
        c.label('next'+str(i))
    c.label('original');jump(c,ORIGINAL)
    code=c.finish();image.patch(hook,bytes(len(code)),code,'Only extend event guard; retain existing LoadBank state and original Post')
    image.patch(SITE,expected,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-SITE-12),'Weekly story event coverage')
    output=OUT/'native-weekly-voice-v1/libil2cpp.so';image.save(output)
    report={'status':'prepared_human_pending','site':SITE,'hook':hook,'load':LOAD,'original':ORIGINAL,
            'prefixes':PREFIXES,'existing_bank_once_state_unchanged':True,
            'original_Post_callbacks_and_return_unchanged':True,'shield_bridge_retained':True}
    (output.parent/'guard.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


if __name__=='__main__':print(json.dumps(build()))
