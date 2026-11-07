"""Pause unsupported Type2 auto-accept without marking stories complete."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import hashlib, json, re
from lupa import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]

def sha(raw): return hashlib.sha256(raw).hexdigest()

def prepare():
    out=ROOT/'server19-run/sakura-deferred-branches-20261027'
    out.mkdir(parents=True,exist_ok=True)
    rows=json.loads((ROOT/'server19-run/common-baseline-20261027-v1/runtime-artifacts.json').read_bytes())
    marker=b'level.CheckBranchMissionState_Cycle4 = function ()'
    guard=(b'\n\t-- Type2 story support is deferred; keep data and progress unchanged.\n'
           b'\t-- Remove this explicit gate only after the matching server catalog is restored.\n'
           b'\tdo return end\n')
    records=[]
    for name in ('levelopenworld_sakura.lua','levelopenworld_sakura_castle_outside.lua'):
        remote='/sdcard/bh3-server19-resources/lua/levels/openworld/'+name
        row=next(x for x in rows if x['remote']==remote)
        before=(ROOT/row['local']).read_bytes();assert sha(before)==row['sha256']
        assert before.count(marker)==1
        after=before.replace(marker,marker+guard)
        assert after.replace(marker+guard,marker)==before
        lua=LuaRuntime()
        lua.eval('function(s) return assert((loadstring or load)(s)) end')(after.decode('utf-8'))
        # Exercise only the guarded function: an attempted native call would fail.
        start=after.index(marker)
        following=re.search(rb'\nlevel\.\w+\s*=\s*function',after[start+len(marker):])
        end=start+len(marker)+following.start() if following else len(after)
        lua.execute('level = {}')
        lua.execute(after[start:end].decode('utf-8'))
        lua.globals().level.CheckBranchMissionState_Cycle4()
        (out/name).write_bytes(after)
        records.append(dict(remote=remote,source=row['local'],local=(out/name).relative_to(ROOT).as_posix(),
                            before_sha256=sha(before),sha256=sha(after),native_calls=0))
    (out/'verification.json').write_text(json.dumps(dict(status='PASS',files=records,
        scope='Only unsupported Type2 branch auto-scan gated; original body and all other Lua bytes retained',
        human_acceptance='pending'),indent=2),encoding='utf-8')
    print('PASS: both Lua scripts compile; deferred branch scanners make no native calls')

if __name__=='__main__':prepare()
