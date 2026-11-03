"""Original ARM MonsterActor NPC-lookup null branch, controlled metadata API."""

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
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
import server19_arm_native as n


def main(folder):
    folder=Path(folder);out=folder/'npc-level-fix'
    report=json.loads((out/'technical-check.json').read_bytes())
    old=json.loads((folder/'npclevellogic').read_bytes());new=json.loads((out/'npclevellogic').read_bytes())
    im=n.ArmImage();cases=[]
    # The original lookup receives the unwrapped integer in r5 at this point.
    for label,rows in [('before',old),('after',new)]:
        for level in report['required_levels']:
            u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0,0x4000000)
            start,end=im.method_range(47863);u.mem_write(start,im.read(start,end-start))
            actor,base,npc=0x3800000,0x3801000,0x3802000
            u.mem_write(actor+0xf0,struct.pack('<I',base))
            u.reg_write(UC_ARM_REG_R10,actor);u.reg_write(UC_ARM_REG_R5,level)
            selected=[r for r in rows if r['HardLevel']==level];seen=[];outcome=[]
            def hook(uc,address,size,data):
                if address==0x12db434:
                    assert uc.reg_read(UC_ARM_REG_R1)==level
                    seen.append(level);uc.reg_write(UC_ARM_REG_R0,npc if selected else 0)
                    uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
                elif address in (0x1139a94,0x113a068):
                    outcome.append('continue' if address==0x1139a94 else 'null_throw');uc.emu_stop()
                elif not start<=address<end:raise AssertionError(hex(address))
            u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x1139a70,0xffffffff,count=100)
            assert seen==[level] and outcome==['continue' if selected else 'null_throw']
            if label=='after':assert selected
            cases.append(dict(table=label,level=level,result=outcome[0]))
    assert any(r['result']=='null_throw' for r in cases if r['table']=='before')
    report['native_check']=dict(status='PASS',cases=cases,
        method=47863,lookup=55215,original_null_return='0x113a06c',
        API_boundary='Controlled NPC reader result from actual before/after JSON; not a full managed JSON parser or gameplay test')
    (out/'technical-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS:',len(cases),'original ARM lookup/branch cases; all required candidate keys exist')


if __name__=='__main__':main(sys.argv[1])
