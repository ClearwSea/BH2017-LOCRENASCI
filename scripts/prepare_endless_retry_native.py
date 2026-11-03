"""恢复满层原生入口并钳制准备页楼层 / Native final-floor retry, no save edits."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server19_arm_native import ArmImage,ArmCode,arm_branch,word

def build(source,output):
    expected='31a80a791057c33a4ecd585f9537c2fd2fd24d1da3ee42d0f5153857bbd9b104'
    im=ArmImage(source,expected)
    old=json.loads((ROOT/'server19-run/endless-20261026/cap-balance-fix/native-patch.json').read_bytes())
    main=old['entries']['main']['target']
    candidates=[main+i for i in range(0,240,4) if im.read(main+i,4)==word(0xa3a01000)]
    assert len(candidates)==1
    im.patch(candidates[0],word(0xa3a01000),word(0xe1a00000),'Keep original preparation entrance visible after floor33')
    entry=old['entries']['prepare']['entry']
    previous=next(p for p in old['patches'] if p['va']==entry)
    im.patch(entry,bytes.fromhex(previous['after']),bytes.fromhex(previous['before']),'Restore original OnPrepareBtnClick entry')
    # Reuse the now-unreachable old prepare guard and its matching EHABI frame.
    helper=old['entries']['prepare']['target']
    guard=next(p for p in old['patches'] if p['va']==helper)
    code=ArmCode(helper);code.push(0x4070);code.call(im.method(68848));code.emit(0xe3500021);code.emit(0xa3a00020);code.pop(0x8070)
    raw=code.finish();assert len(raw)<=guard['size']
    raw+=word(0xe1a00000)*((guard['size']-len(raw))//4)
    im.patch(helper,bytes.fromhex(guard['after']),raw,'Clamp preparation display/drop lookup to floor33; ranking getter remains original')
    veneer=11511872
    assert next(p for p in old['patches'] if p['va']==veneer)['purpose'].startswith('endless-cap-prepare')
    sites=[]
    for mid in (78328,78330,78331):
        calls=[i for i in im.disasm(mid) if i.mnemonic=='bl' and int(i.op_str.lstrip('#'),16)==im.method(68848)]
        assert len(calls)==1,(mid,calls)
        ins=calls[0];im.patch(ins.address,bytes(ins.bytes),arm_branch(ins.address,veneer,link=True),'Preparation-only progress clamp')
        sites.append(dict(method=mid,site=ins.address))
    assert not output.exists()
    output.write_bytes(im.data)
    report=dict(source_sha256=expected,sha256=hashlib.sha256(im.data).hexdigest(),helper=helper,veneer=veneer,sites=sites,patches=im.changes,original_caps=old)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS',len(im.changes),'bounded patches; no ELF layout/unwind changes')

if __name__=='__main__':build(Path(sys.argv[1]),Path(sys.argv[2]))
