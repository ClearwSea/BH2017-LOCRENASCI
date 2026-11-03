"""Build x86 local recharge on top of the accepted poster/black-screen library."""

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
import argparse
import json
import struct
import subprocess
import analyze19 as native
from server19_arm_resources import zig_path
from server19_gacha_images import elf, align, ROOT

HOOK = 0xfa29f9
SKIP = HOOK + 5
ICON_HOOK = 0xf80253


def build(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Workspace input and fresh candidate directory required')
    before = source.read_bytes()
    h, ps, _, exports = elf(before)
    expected = b'\xe8' + struct.pack('<i', 0x1167377 - HOOK - 5)
    if before[HOOK:HOOK+5] != expected or before[SKIP:SKIP+6] != native.E[SKIP:SKIP+6]:
        raise ValueError('Original purchase call/frame changed')
    if before[ICON_HOOK:ICON_HOOK+5] != b'\xe8'+struct.pack('<i',0xf804ae-ICON_HOOK-5):
        raise ValueError('Original recharge icon call changed')
    for name, address in {'domain_get':0x29538a0, 'domain_get_assemblies':0x2953900,
                          'assembly_get_image':0x2952c20, 'class_from_name':0x2952e00,
                          'class_get_method_from_name':0x2952ff0, 'runtime_invoke':0x29547b0,
                          'object_unbox':0x2954580, 'string_new':0x29549a0}.items():
        if exports['il2cpp_'+name][0] != address:
            raise ValueError('Runtime ABI changed')
    for method in (6608, 6615, 73293, 67762, 81315, 81322):
        address = native.pointer(native.M[method])
        if before[address:address+32] != native.E[address:address+32]:
            raise ValueError('Original Guid/network method changed')
    output.mkdir(parents=True)
    offset=align(len(before)); base=align(max(p[2]+p[5] for p in ps if p[0]==1))
    linked_base=base+256
    script=output/'link.ld'
    script.write_text('ENTRY(local_recharge_click)\nSECTIONS { . = '+hex(linked_base)+'; .text : { *(.text*) } .rodata : { *(.rodata*) } .got : { *(.got*) } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n',encoding='utf8')
    compiler=zig_path(); obj=output/'recharge.o'; linked=output/'recharge.elf'
    commands=[[str(compiler),'cc','-target','x86-freestanding-none','-Os','-fPIC','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fvisibility=hidden','-c',str(ROOT/'server19_recharge_client.c'),'-o',str(obj)],
              [str(compiler),'build-exe',str(obj),'-target','x86-freestanding-none','-fno-compiler-rt','-fno-PIE','-fno-strip','--script',str(script),'--name','recharge','-femit-bin='+str(linked)]]
    for i, cmd in enumerate(commands):
        run=subprocess.run(cmd,capture_output=True,text=True)
        (output/('compile.log' if not i else 'link.log')).write_text(run.stdout+run.stderr,encoding='utf8')
        if run.returncode: raise ValueError(run.stderr[-2000:])
    data=linked.read_bytes(); _,_,sections,symbols=elf(data)
    if any(s==0 and name!='_GLOBAL_OFFSET_TABLE_' for name,(v,z,s) in symbols.items()):
        raise ValueError('Unresolved imports')
    selected=[s for s in sections if s[2]&2 and s[5]]
    if any(s[1] in (4,8,9) for s in selected): raise ValueError('Unexpected storage/relocation')
    end=max(s[3]+s[5] for s in selected); blob=bytearray(end-linked_base)
    for s in selected: blob[s[3]-linked_base:s[3]-linked_base+s[5]]=data[s[4]:s[4]+s[5]]
    code=bytearray.fromhex('55 89 e5 53 56 57 83 e4 f0 83 ec 20 e8 00 00 00 00 58 2d')
    code+=struct.pack('<I',base+17)+bytes.fromhex('89 04 24')
    # base + five original args, preserving callee saved registers/alignment.
    for src,dest in ((8,4),(12,8),(16,12),(20,16),(24,20)):
        code+=bytes((0x8b,0x45,src,0x89,0x44,0x24,dest))
    code+=b'\xe8'+struct.pack('<i',symbols['local_recharge_click'][0]-(base+len(code))-5)
    code+=bytes.fromhex('8d 65 f4 5f 5e 5b 5d c3')
    icon=bytearray.fromhex('55 89 e5 53 56 57 83 e4 f0 83 ec 10 e8 00 00 00 00 58 2d')
    icon+=struct.pack('<I',base+128+17)+bytes.fromhex('89 04 24')
    for src,dest in ((8,4),(12,8),(16,12)):
        icon+=bytes((0x8b,0x45,src,0x89,0x44,0x24,dest))
    icon+=b'\xe8'+struct.pack('<i',symbols['local_recharge_icon'][0]-(base+128+len(icon))-5)
    icon+=bytes.fromhex('8d 65 f4 5f 5e 5b 5d c3')
    assert len(code)<=128 and len(icon)<=128
    segment=code+bytes(128-len(code))+icon+bytes(128-len(icon))+blob
    phpos=align(offset+len(segment)); phva=base+phpos-offset
    headers=[p[:] for p in ps]; size=phpos-offset+(len(headers)+1)*32
    for p in headers:
        if p[0]==6: p[1:6]=[phpos,phva,phva,(len(headers)+1)*32,(len(headers)+1)*32]
    headers.append([1,offset,base,base,size,size,5,4096])
    result=bytearray(before)+bytes(offset-len(before))+segment
    result+=bytes(phpos-len(result))+b''.join(struct.pack('<8I',*p) for p in headers)
    struct.pack_into('<I',result,28,phpos); struct.pack_into('<H',result,44,len(headers))
    result[HOOK:HOOK+5]=b'\xe8'+struct.pack('<i',base-HOOK-5)
    result[ICON_HOOK:ICON_HOOK+5]=b'\xe8'+struct.pack('<i',base+128-ICON_HOOK-5)
    # Return immediately after sending local request, bypassing SDK payment.
    result[SKIP:SKIP+6]=b'\xe9'+struct.pack('<i',0xfa2b93-SKIP-5)+b'\x90'
    # Products come exclusively from this offline server, not a channel SDK.
    result[0x8556e8:0x8556eb]=bytes.fromhex('31 c0 c3')
    # Local recharge does not consult real payment/account/monthly limits.
    # Keep the original request-list -> selected-item validation path intact.
    buy=0x123bbaa
    result[buy:buy+5]=b'\xe9'+struct.pack('<i',0x123c64a-buy-5)
    check=bytearray(result[:len(before)])
    for pos,size in ((28,4),(44,2),(HOOK,5),(ICON_HOOK,5),(SKIP,6),(0x8556e8,3),(buy,5)): check[pos:pos+size]=before[pos:pos+size]
    if check!=before: raise ValueError('Unrelated bytes changed')
    (output/'libil2cpp.so').write_bytes(result)
    (output/'manifest.json').write_text(json.dumps({'status':'candidate_human_pending','source':str(source),'hook':hex(HOOK),'sdk_bypass':hex(SKIP),'market_sdk_lookup':False,'buy_button':'original RequestToBuyHcoin; local only','veneer':hex(base),'wire':'Cmd761 product/CNY/UUIDv4','preserves_prior_library':True},indent=2)+'\n',encoding='utf8')
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(build(a.source,a.output))
