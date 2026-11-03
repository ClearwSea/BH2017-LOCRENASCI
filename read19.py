"""只读模拟器进程内存定位 / Read-only emulator process inspection."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import struct,subprocess,base64
import probe19 as p
pid=p.adb('shell','pidof '+p.PKG)
line=next(x for x in p.root('cat /proc/'+pid+'/maps').splitlines() if 'libil2cpp.so' in x)
base=int(line.split('-')[0],16)
def read(addr,n):
 cmd="su -c 'dd if=/proc/"+pid+'/mem bs=1 skip='+str(addr)+' count='+str(n)+" 2>/dev/null | base64'"
 return base64.b64decode(subprocess.run(p.ADB+['exec-out',cmd],capture_output=True,timeout=15).stdout)
def u(addr):return struct.unpack('<I',read(addr,4))[0]
def got(off):return u(u(base+0x33e39d8+off))
def string(obj):return read(obj+12,min(u(obj+8)*2,10000)).decode('utf16',errors='replace')
