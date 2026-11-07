"""Port sign-in fixes to the pinned Android integrated client / 签到补丁移植。

Instruction preimages, method mapping and exact input hash are checked.
No device or save operations.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'analysis-deps')]
import server19_arm_native as n
O=ROOT/'server19-run/nx-backport-20261102'
im=n.ArmImage(O/'client-before.so','f6d721fe4d4a75192a50b473426b52b344d84ef691be02f600c746a190433a9c')
# Reward itself was checked before each block. Keep its count even if the
# original storage factory cannot construct an unavailable item; never invent it.
sites=[0x10c2350,0x10c23fc,0x10c24a8,0x10c2554,0x10c2600]
for slot,site in enumerate(sites):
 count_offset=0x30+12*slot
 original=b''.join(n.word(x) for x in [0xe3500000,0x15911000|count_offset,0x15801020,0x15940014,0x13500000])+n.arm_branch(site+20,0x10c2630,cond='eq')+b''.join(n.word(x) for x in [0xe5900000|count_offset,0xe584001c,0xe8bd8c70])
 assert im.read(site,36)==original
 replacement=b''.join(n.word(x) for x in [0xe3500000,0xe5911000|count_offset,0x15801020,0xe584101c,0xe8bd8c70]+[0xe1a00000]*4)
 im.patch(site,original,replacement,'Preserve reward quantity for missing item slot '+str(slot+1))
# Null item: use original count renderer; skip only item-specific detail/badges.
# UIUtil returns null for missing icon; the original sprite setter accepts null.
site=0x10c184c
im.patch(site,n.arm_branch(site,0x10c1fdc,cond='eq'),n.arm_branch(site,0x10c1928,cond='eq'),'Missing item uses original quantity renderer')

# Keep sequential patch preimages explicit; later adapters reuse retired padding.
prior_changes=list(im.changes)
intermediate=O/'client-signin-items.so'
intermediate.write_bytes(bytes(im.data))
im=n.ArmImage(intermediate,hashlib.sha256(im.data).hexdigest())
# Use only verified unreachable padding following unconditional return from v1.
a,b,c=0x10c2364,0x10c2410,0x10c24bc
blocks={a:n.word(0xe3520000)+n.arm_branch(a+4,0x163d86c,cond='ne')+n.arm_branch(a+8,b)+n.word(0xe1a00000),b:n.word(0xe3510000)+n.word(0x012fff1e)+n.word(0xe1a00001)+n.arm_branch(b+12,c),c:n.word(0xe3a01000)+n.word(0xe3a02000)+n.arm_branch(c+8,im.method(29311))+n.word(0xe1a00000)}
for va,data in blocks.items():im.patch(va,n.word(0xe1a00000)*4,data,'Null-path sprite adapter in unreachable v1 padding')
site=0x10c1754;im.patch(site,n.arm_branch(site,0x163d86c,link=True),n.arm_branch(site,a,link=True),'Sign-in null icon bypasses string-path loader')

prior_changes += list(im.changes)
intermediate=O/"client-signin-icons.so"
intermediate.write_bytes(bytes(im.data))
im=n.ArmImage(intermediate,hashlib.sha256(im.data).hexdigest())
helper=im.allocate_code('Sign-in authorized coin reward conversion',128,unwind=0x8001b0b0)
c=n.ArmCode(helper);c.push(3);c.emit(0xe3570000);c.branch('done',cond='eq');c.load(0,7,8);c.immediate(1,1211);c.emit(0xe0400001);c.emit(0xe3500003);c.branch('done',cond='hi')
# Exact four IDs with original missing item; coins field and item slot only.
c.load(0,7,40);c.immediate(1,3122);c.emit(0xe1500001);c.branch('done',cond='ne');c.immediate(0,10000);c.store(0,7,16);c.immediate(0,0);c.store(0,7,40);c.store(0,7,44);c.store(0,7,48)
c.label('done');c.pop(3);c.store(7,5,20);c.emit(0xe12fff1e);raw=c.finish();im.patch(helper,bytes(len(raw)),raw,'Convert only sign-in missing-item rewards to 10000 scoin')
veneer=0x10c2568;raw=n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word((helper-veneer-12)&0xffffffff);im.patch(veneer,n.word(0xe1a00000)*3,raw,'Sign-in conversion veneer in unreachable padding')
site=0x10c13a4;im.patch(site,n.word(0xe5857014),n.arm_branch(site,veneer,link=True),'Normalize reward before original sign-in view')

im.finalize()
data=bytes(im.data)
(O/'client-signin.so').write_bytes(data)
r=dict(source_sha256=hashlib.sha256((O/"client-before.so").read_bytes()).hexdigest(),sha256=hashlib.sha256(data).hexdigest(),patches=prior_changes+im.changes,sites=sites,helper=helper,veneer=veneer,site=site,bytes=len(data))
(O/'signin-patch.json').write_text(json.dumps(r,indent=2))
print(r['sha256'])
