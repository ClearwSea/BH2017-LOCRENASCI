"""临时空引用定位探针 / Temporary null-reference location probe."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import struct
def install(a,b,edit):
 cave=0xa63bef;code=bytearray.fromhex('55 89 e5 53 57 56 83 e4 f0 81 ec 00 01 00 00')
 def call(p):
  q=cave+len(code);code.extend(b'\xe8'+struct.pack('<i',p-q-5))
 call(cave+len(code)+5);pic=cave+len(code);code+=b'\x5b'
 code+=b'\x81\xc3'+struct.pack('<i',0x33e39d8-pic)
 # sprintf(buffer, format, caller RVA, parent RVA).
 code+=bytes.fromhex('8d 83 28 c6 c1 fc 8b 55 04 29 c2 89 54 24 08 8b 55 00 8b 52 04 29 c2 89 54 24 0c')
 fmtpos=len(code);code+=b'\x8d\x83'+b'\0'*4
 code+=bytes.fromhex('89 44 24 04 8d 74 24 40 89 34 24 ff 93 f4 17 00 00 89 34 24')
 call(0x29549a0)
 code+=bytes.fromhex('89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00')
 call(0x222ec7e)
 code+=bytes.fromhex('8d 65 f4 5e 5f 5b 5d')
 pos=cave+len(code);code+=b'\xe9'+struct.pack('<i',0x298b180-pos-5)
 struct.pack_into('<i',code,fmtpos+2,cave+len(code)-0x33e39d8)
 code+=b'BH3NULL caller=%08x parent=%08x\0'
 assert len(code)<0xa649f4-cave
 edit(cave,bytes(b[cave:cave+len(code)]),code,'Temporary null trace in unused auto-test iterator')
 p=0x42d4d0;edit(p,bytes.fromhex('ff a3 44 00 00 00'),b'\xe9'+struct.pack('<i',cave-p-5)+b'\x90','Trace null throw caller without suppressing exception')

 # Validate the local profile before the independently blocked data stage.
 cave=0xa63eef
 code=bytearray.fromhex('55 89 e5 53 83 e4 f0 83 ec 10 c7 04 24 00 00 00 00 c7 44 24 04 00 00 00 00')
 pos=cave+len(code);code+=b'\xe8'+struct.pack('<i',a.pointer(a.M[72831])-pos-5)
 code+=bytes.fromhex('8d 65 fc 5b 5d')
 dest=a.pointer(a.M[74460]);pos=cave+len(code);code+=b'\xe9'+struct.pack('<i',dest-pos-5)
 edit(cave,bytes(b[cave:cave+len(code)]),code,'Preflight local profile parsing before basic-data initialization')
 p=0xe96e18;old=b'\xe8'+struct.pack('<i',dest-p-5);new=b'\xe8'+struct.pack('<i',cave-p-5)
 edit(p,old,new,'Run profile preflight before OnDataAssetReady')
