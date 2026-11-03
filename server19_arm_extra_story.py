"""Extend the accepted ARM runtime with Extra dialogue and requested20x damage."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib,json,struct
from pathlib import Path
import server19_arm_native as n
from server19_arm_resources import jump,module_base
from server19_arm_weekly_voice import SITE,LOAD,ORIGINAL
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'.local-baseline/server19-dev/story-all-20261015/goal-six-chapters-20261016'

def build(source,output,expected_sha256):
    image=n.ArmImage(source,expected_sha256=expected_sha256)
    spec=json.loads((BASE/'native-dialog-seek-damage10-v3/report.json').read_bytes())
    damage=spec['damage']
    def immediate(reg,value):
        c=n.ArmCode(0);c.immediate(reg,value);return c.finish()
    start=damage+20
    image.patch(start,immediate(0,0x41200000),immediate(0,0x41a00000),'Requested avatar test damage10x to20x')
    before=immediate(1,0x7dcccccb);after=immediate(1,0x7d4ccccb)
    block=image.read(damage,0x150);positions=[i for i in range(0,len(block)-7,4) if block[i:i+8]==before]
    assert len(positions)==4
    for off in positions:image.patch(damage+off,before,after,'Retain finite float saturation for20x')
    hook=image.allocate_code('Extra story-bank event guard',2048,unwind=n.unwind_for_push(0x41f0,48))
    c=n.ArmCode(hook);c.emit(0xe3510000);c.branch('original',cond='eq')
    for i,prefix in enumerate(('VO_Dialog_','VO_Weekly_Dialog_','VO_Extra_Dialog_')):
        c.load(0,1,8);c.immediate(2,len(prefix));c.emit(0xe1500002);c.branch('next'+str(i),cond='lt')
        raw=prefix.encode('utf-16le')
        for off in range(0,len(raw),4):
            part=raw[off:off+4];offset=12+off
            if len(part)==4:c.load(0,1,offset)
            else:c.emit(0xe1d100b0|((offset&0xf0)<<4)|(offset&15))
            c.immediate(2,int.from_bytes(part,'little'));c.emit(0xe1500002);c.branch('next'+str(i),cond='ne')
        jump(c,LOAD);c.label('next'+str(i))
    c.label('original');jump(c,ORIGINAL);raw=c.finish();image.patch(hook,bytes(len(raw)),raw,'Preserve existing loader state and Post behavior')
    old=image.read(SITE,12);assert old[:8]==n.word(0xe59fc000)+n.word(0xe08ff00c)
    image.patch(SITE,old,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-SITE-12),'Recognize original Extra event family')
    capture=json.loads((BASE/'native-dialog-interrupt-v2/report.json').read_bytes());site=capture['capture_site'];old=image.read(site,12)
    previous=site+12+struct.unpack('<i',old[8:])[0]
    hook2=image.allocate_code('Capture Extra dialogue playing ID',1024,unwind=n.unwind_for_push(0x41f0,16))
    c=n.ArmCode(hook2);c.push(0x41ff);c.emit(0xe3500000);c.branch('restore',cond='eq');c.emit(0xe3540000);c.branch('restore',cond='eq')
    prefix='VO_Extra_Dialog_';c.load(0,4,8);c.immediate(1,len(prefix));c.emit(0xe1500001);c.branch('restore',cond='lt')
    raw=prefix.encode('utf-16le')
    for off in range(0,len(raw),4):
        part=raw[off:off+4];offset=12+off
        if len(part)==4:c.load(0,4,offset)
        else:c.emit(0xe1d400b0|((offset&0xf0)<<4)|(offset&15))
        c.immediate(1,int.from_bytes(part,'little'));c.emit(0xe1500001);c.branch('restore',cond='ne')
    module_base(c,5);c.immediate(12,capture['state_va']);c.emit(0xe085500c);c.load(0,13,0);c.store(0,5,0)
    c.label('restore');c.pop(0x41ff);jump(c,previous);raw=c.finish();image.patch(hook2,bytes(len(raw)),raw,'Reuse original skip/close voice lifecycle')
    image.patch(site,old,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook2-site-12),'Capture Extra without changing prior callbacks')
    image.save(output)
    report=dict(damage=damage,multiplier=20,avatar_category=3,loader_hook=hook,capture_hook=hook2,sha256=hashlib.sha256(Path(output).read_bytes()).hexdigest(),source_sha256=expected_sha256,human_acceptance='pending')
    Path(output).with_suffix('.report.json').write_text(json.dumps(report,indent=2));return report
