"""Prepare a bounded x86 event-image supplier; never operate a device/service."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

import analyze19 as native
import server19_resources as resources
from server19_arm_resources import zig_path

ROOT=Path(__file__).resolve().parent
HOOK=0x143ebd6


def align(n): return (n+4095)&~4095
def sha(b): return hashlib.sha256(b).hexdigest()


def elf(data):
    h=list(struct.unpack_from('<16sHHIIIIIHHHHHH',data))
    if h[0][:7]!=b'\x7fELF\x01\x01\x01' or h[2]!=3: raise ValueError('ELF32 x86 required')
    ps=[list(struct.unpack_from('<8I',data,h[5]+i*h[9])) for i in range(h[10])]
    ss=[list(struct.unpack_from('<10I',data,h[6]+i*h[11])) for i in range(h[12])]
    symbols={}
    for s in ss:
        if s[1] not in (2,11): continue
        ns=ss[s[6]]; names=data[ns[4]:ns[4]+ns[5]]
        for p in range(s[4],s[4]+s[5],s[9]):
            n,v,z,info,other,section=struct.unpack_from('<IIIBBH',data,p)
            name=names[n:names.index(0,n)].decode()
            if name: symbols[name]=(v,z,section)
    return h,ps,ss,symbols


def build(source,output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use workspace input and new candidate directory')
    before=source.read_bytes(); h,ps,_,exports=elf(before)
    expected=b'\xe8'+struct.pack('<i',0x268673e-HOOK-5)
    if before[HOOK:HOOK+5]!=expected: raise ValueError('Original event-image call must be present')
    api={'assembly_get_image':0x2952c20,'class_from_name':0x2952e00,'class_get_method_from_name':0x2952ff0,
         'domain_get':0x29538a0,'domain_get_assemblies':0x2953900,'object_new':0x2954530,
         'object_unbox':0x2954580,'resolve_icall':0x29529f0,'runtime_invoke':0x29547b0,'string_new':0x29549a0,
         'class_get_type':0x29532a0,'type_get_object':0x2954db0}
    for n,v in api.items():
        if exports['il2cpp_'+n][0]!=v: raise ValueError('Original runtime API changed: '+n)
    # Exact original callers resolve UnityEngine.UI.Image before this hook;
    # its extra argument comes from the unmodified EBP frame, not a guess.
    if before[0x143eb1d:0x143eb20]!=bytes.fromhex('55 89 e5'):
        raise ValueError('Original event-image EBP frame changed')
    checks={29248:0x21ec3eb,29317:0x21f4b1f,17612:0x22970c0,
            18164:0x224e0d2,29951:0x21dc594}
    for method,address in checks.items():
        if native.pointer(native.M[method])!=address or before[address:address+32]!=native.E[address:address+32]:
            raise ValueError('Original layout method changed')
    with zipfile.ZipFile(resources.DEFAULT19) as package:
        engine=package.read('lib/x86/libunity.so')
    registration=b'UnityEngine.Sprite::INTERNAL_CALL_Create\0'
    if engine[0xf79d83:0xf79d83+len(registration)]!=registration:
        raise ValueError('Stock Sprite Create registration changed')
    if struct.unpack_from('<I',engine,0x121a094)[0]!=0x8b4200 or engine[0x8b4452:0x8b4458]!=bytes.fromhex('8b4d20894c24'):
        raise ValueError('Stock seven-argument Sprite creation ABI changed')
    output.mkdir(parents=True)
    offset=align(len(before)); base=align(max(p[2]+p[5] for p in ps if p[0]==1))
    linked_base=base+256
    script=output/'link.ld'
    script.write_text('ENTRY(gacha_event_sprite)\nSECTIONS { . = '+hex(linked_base)+'; .text : { *(.text*) } .rodata : { *(.rodata*) } .got : { *(.got*) } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n','utf8')
    compiler=zig_path(); obj=output/'poster.o'; linked=output/'poster.elf'
    commands=[ [str(compiler),'cc','-target','x86-freestanding-none','-Os','-fPIC','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-fno-asynchronous-unwind-tables','-fvisibility=hidden','-c',str(ROOT/'server19_gacha_images.c'),'-o',str(obj)],
               [str(compiler),'build-exe',str(obj),'-target','x86-freestanding-none','-fno-compiler-rt','-fno-PIE',
                '-fno-strip','--script',str(script),'--name','poster','-femit-bin='+str(linked)] ]
    for i,cmd in enumerate(commands):
        run=subprocess.run(cmd,capture_output=True,text=True)
        (output/('compile.log' if i==0 else 'link.log')).write_text(run.stdout+run.stderr,'utf8')
        if run.returncode: raise ValueError('Poster helper compile/link failed: '+run.stderr[-2000:])
    data=linked.read_bytes(); _,_,sections,symbols=elf(data)
    undefined=[n for n,(v,z,s) in symbols.items() if s==0 and n!='_GLOBAL_OFFSET_TABLE_']
    if undefined: raise ValueError('Unresolved imports: '+repr(undefined))
    selected=[s for s in sections if s[2]&2 and s[5]]
    if any(s[1]==8 or s[1] in (4,9) for s in selected): raise ValueError('Writable/relocation storage unsupported')
    end=max(s[3]+s[5] for s in selected); blob=bytearray(end-linked_base)
    for s in selected: blob[s[3]-linked_base:s[3]-linked_base+s[5]]=data[s[4]:s[4]+s[5]]
    helper=symbols['gacha_event_sprite'][0]
    # Four original managed arguments become six helper arguments with module
    # base first and the calling TrySetupEventSprite's Image as the last one.
    # This caller uses an EBP frame: Image is [caller_ebp+0x0c].
    # All original callee-saved registers and stack alignment are kept.
    code=bytearray.fromhex('55 89 e5 53 56 57 83 e4 f0 83 ec 20 e8 00 00 00 00 58 2d')
    code+=struct.pack('<I',base+17)
    code+=bytes.fromhex('89 04 24 8b 45 08 89 44 24 04 8b 45 0c 89 44 24 08 8b 45 10 89 44 24 0c 8b 45 14 89 44 24 10')
    code+=bytes.fromhex('8b 45 00 8b 40 0c 89 44 24 14')
    code+=b'\xe8'+struct.pack('<i',helper-(base+len(code))-5)
    code+=bytes.fromhex('8d 65 f4 5f 5e 5b 5d c3')
    if len(code)>256: raise ValueError('Veneer exceeds reserved size')
    segment=code+bytes(256-len(code))+blob
    phpos=align(offset+len(segment)); phva=base+phpos-offset
    headers=[p[:] for p in ps]; size=phpos-offset+(len(headers)+1)*32
    for p in headers:
        if p[0]==6: p[1:6]=[phpos,phva,phva,(len(headers)+1)*32,(len(headers)+1)*32]
    headers.append([1,offset,base,base,size,size,5,4096])
    result=bytearray(before)+bytes(offset-len(before))+segment
    result+=bytes(phpos-len(result))+b''.join(struct.pack('<8I',*p) for p in headers)
    struct.pack_into('<I',result,28,phpos);struct.pack_into('<H',result,44,len(headers))
    result[HOOK:HOOK+5]=b'\xe8'+struct.pack('<i',base-HOOK-5)
    unchanged=bytearray(result[:len(before)])
    unchanged[28:32]=before[28:32];unchanged[44:46]=before[44:46];unchanged[HOOK:HOOK+5]=before[HOOK:HOOK+5]
    if bytes(unchanged)!=before: raise ValueError('Unrelated native bytes changed')
    (output/'libil2cpp.so').write_bytes(result)
    manifest={'status':'candidate_human_pending','architecture':'x86','source':str(source.relative_to(ROOT)),
              'preimage_sha256':sha(before),'after_sha256':sha(result),'hook':hex(HOOK),'veneer':hex(base),
              'helper':hex(helper),'runtime_api':api,'original_lookup_first':True,
              'event_layout':{'caller_image_offset':12,'size_delta':[0,0],
                              'preserve_aspect':True,'sprite_rect':'full_bitmap',
                              'stock_aspect_fitter_mode':4,'event_fitter_mode':0},
              'paths':{'Server19/Gacha/Ziyuan':'/sdcard/bh3-server19-resources/gacha/ziyuan.png',
                       'Server19/Gacha/Dracula':'/sdcard/bh3-server19-resources/gacha/dracula.png'},
              'stock_engine_create':{'registration_names_va':'0x121b01c','function_table_va':'0x121b094',
                                     'entry':'0x8b4200','arguments':7,'body_sha256':sha(engine[0x8b4200:0x8b44d0])},
              'unrelated_existing_bytes_preserved':True,'human_visual_acceptance':'pending','sony_changed':False}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf8')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); print(json.dumps(build(a.source,a.output),ensure_ascii=False))
