"""Migrate accepted x86 supply visuals/offline recharge to current Sony ARM.

Build only. Keep current ARM resource/black-screen repairs and EHABI intact.
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
import argparse
import json
import re
import struct
import subprocess
from pathlib import Path
import analyze19 as a
import server19_arm_native as n
import server19_arm_resources as resources

ROOT=Path(__file__).resolve().parent


def build(source,output, *, poster_only=False):
    source,output=Path(source).resolve(),Path(output).resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use current-device source and a fresh workspace output')
    original=n.ArmImage();image=n.ArmImage(source,expected_sha256=None)
    output.mkdir(parents=True)
    api_names=('assembly_get_image','class_from_name','class_get_method_from_name','domain_get',
               'domain_get_assemblies','object_new','object_unbox','resolve_icall','runtime_invoke',
               'string_new','class_get_type','type_get_object')
    mapping={a_export:image.symbol('il2cpp_'+name) for name,a_export in zip(api_names,
        (0x2952c20,0x2952e00,0x2952ff0,0x29538a0,0x2953900,0x2954530,0x2954580,
         0x29529f0,0x29547b0,0x29549a0,0x29532a0,0x2954db0))}
    mapping.update({0x268673e:0x2a39378,0xf804ae:image.method(86666),0x1167377:image.method(73293)})
    for x86,mid in ((0x224e0d2,18164),(0x22970c0,17612),(0x21ec3eb,29248),
                    (0x21f4b1f,29317),(0x21dc594,29951)):
        mapping[x86]=image.method(mid)
    text=(ROOT/'server19_gacha_images.c').read_text(encoding='utf8')
    if not poster_only:
        text+='\n'+(ROOT/'server19_recharge_client.c').read_text(encoding='utf8').replace('equal(', 'recharge_equal(')
    def replace(m):
        v=int(m.group(1),16)
        if v not in mapping:raise ValueError('Unmapped x86 API '+hex(v))
        return 'API('+hex(mapping[v])+','
    text=re.sub(r'API\((0x[0-9a-f]+),',replace,text)
    text+='''
__attribute__((visibility("hidden"),noinline))
O* arm_event_sprite(U b,O* unused,O* path,U flag,O* info,O* transform) {
 O* image=0;
 if(equal(path,"Server19/Gacha/Ziyuan") || equal(path,"Server19/Gacha/Dracula") ||
    equal(path,"Server19/Bridge/Github") || equal(path,"Server19/Bridge/Celebration") ||
    equal(path,"Server19/Announcement/TeaParty") || equal(path,"Server19/Announcement/Update")) {
  O* k=klass(b,"UnityEngine.UI","Image");
  if(k && transform) {
   O* type=API(CLASS_TYPE,O*(*)(O*))(k);
   O* object=API(TYPE_OBJECT,O*(*)(O*))(type);
   image=API(GET_COMPONENT,O*(*)(O*,O*,O*))(transform,object,0);
  }
 }
 return gacha_event_sprite(b,unused,path,flag,info,image);
}
'''.replace('CLASS_TYPE',hex(image.symbol('il2cpp_class_get_type'))).replace(
        'TYPE_OBJECT',hex(image.symbol('il2cpp_type_get_object'))).replace('GET_COMPONENT',hex(image.method(18164)))
    cfile=output/'arm-supply.c';cfile.write_text(text,encoding='utf8')
    # Original registered methods and call-site preimages constrain the ARM ABI.
    sites={'poster':(0x15ea904,0x2a39378),'purchase':(0x10b5c4c,image.method(73293)),
           'icon':(0x10925e4,image.method(86666))}
    if poster_only:
        # Replace just the existing event-sprite call, preserving every later
        # recharge, story, audio and test-damage patch in the supplied library.
        sites={'poster':sites['poster']}
    preimages={name:image.read(site,4) for name,(site,_) in sites.items()}
    for name,(site,target) in sites.items():
        if poster_only:
            if int.from_bytes(preimages[name],'little') >> 24 != 0xeb:
                raise ValueError('Existing poster site must remain an ARM BL')
        elif image.read(site,4)!=n.arm_branch(site,target,link=True):raise ValueError('Call site changed: '+name)
    for mid in ((18164,17612,29248,29317,29951) if poster_only else (6608,6615,18164,17612,29248,29317,29951,67762,81315,81322)):
        va=image.method(mid)
        if image.read(va,16)!=original.read(va,16):raise ValueError('Original ABI entry changed: '+str(mid))
    reservation=16384;base=image.allocate_code('ARM compiled supply/recharge helpers',reservation)
    script=output/'supply.ld'
    provide=['__aeabi_unwind_cpp_pr0','__aeabi_unwind_cpp_pr1','__aeabi_unwind_cpp_pr2','__aeabi_i2f','__aeabi_ui2f']
    provided={name:image.symbol(name) for name in provide}
    if poster_only:
        # Later story patches place this helper beyond the A32 BL range of
        # the original numeric routines. Explicit PIC tail veneers avoid
        # linker-generated absolute thunks without EHABI descriptors.
        for name in ('__aeabi_i2f','__aeabi_ui2f'):
            va=image.allocate_code('bridge '+name+' PIC tail',16,unwind=0x80b0b0b0)
            code=n.arm_pic_jump(va,provided[name])
            image.patch(va,bytes(len(code)),code,'bridge numeric PIC tail')
            provided[name]=va
    script.write_text('ENTRY(arm_event_sprite)\nSECTIONS { . = '+hex(base)+'; .text : { *(.text*) } .rodata : { *(.rodata*) } .ARM.extab : { *(.ARM.extab*) } .ARM.exidx : { *(.ARM.exidx*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.comment) *(.note*) } }\n'+
        '\n'.join('PROVIDE('+name+' = '+hex(provided[name])+');' for name in provide)+'\n',encoding='utf8')
    zig=resources.zig_path();obj=output/'supply.o';linked=output/'supply.elf'
    commands=[[str(zig),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a8','-marm',
               '-mfloat-abi=soft','-fPIC','-ffreestanding','-fno-builtin','-fno-stack-protector',
               '-fno-jump-tables','-funwind-tables','-fvisibility=hidden','-O1','-g0','-c',str(cfile),'-o',str(obj)],
              [str(zig),'build-exe',str(obj),'-target','arm-freestanding-eabi','-mcpu','cortex_a8',
               '-fno-compiler-rt','-fno-PIE','-fno-strip','--no-gc-sections','--script',str(script),
               '-fentry=arm_event_sprite','-femit-bin='+str(linked)]]
    for i,cmd in enumerate(commands):
        run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (output/('compile.log' if not i else 'link.log')).write_text(run.stdout,encoding='utf8')
        if run.returncode:raise ValueError(run.stdout[-2000:])
    elf=resources.Elf32(linked);blob=elf.payload(base)
    if len(blob)>reservation:raise ValueError('Compiled helper exceeds reservation')
    reloc=resources.Elf32(obj)
    for name,s in reloc.named.items():
        if s[1] not in (4,9):continue
        for off in range(s[4],s[4]+s[5],s[9]):
            at,info=struct.unpack_from('<II',reloc.data,off)
            if info&255 not in (0,3,28,29,42):raise ValueError('ASLR-unsafe relocation')
    image.patch(base,bytes(len(blob)),blob,'compiled ARM native supply visuals and local purchases')
    resources.import_unwind(image,elf)
    # Current ARM resource suppliers already use the first 16 bytes here.
    start,end=image.method_range(72868)
    dirty=[i for i in range(end-start) if image.read(start+i,1)!=original.read(start+i,1)]
    cursor=n.align(start+max(dirty,default=-1)+1,4)
    image.veneer_cursors[72868]=cursor
    hooks={}
    for name,(site,target) in sites.items():
        mask=0x41f0 if name!='icon' else 0x4070
        stack=8 if name!='icon' else 0
        shim=image.allocate_code('ARM '+name+' call ABI shim',160,unwind=n.unwind_for_push(mask,stack))
        c=n.ArmCode(shim);c.push(mask)
        if stack:c.emit(0xe24dd008)
        if name=='poster':
            c.mov(8,5);c.mov(4,0);c.mov(5,1);c.mov(6,2);c.mov(7,3)
            c.store(7,13,0);c.store(8,13,4)
            c.mov(1,4);c.mov(2,5);c.mov(3,6)
            symbol='arm_event_sprite'
        elif name=='purchase':
            c.mov(4,0);c.mov(5,1);c.mov(6,2);c.store(3,13,0)
            c.immediate(12,0);c.store(12,13,4)
            c.mov(1,4);c.mov(2,5);c.mov(3,6);symbol='local_recharge_click'
        else:
            c.mov(3,2);c.mov(2,1);c.mov(1,0);symbol='local_recharge_icon'
        resources.module_base(c)
        c.call(elf.symbols[symbol]['va'])
        if stack:c.emit(0xe28dd008)
        c.pop((mask & ~(1<<14)) | (1<<15))
        code=c.finish();image.patch(shim,bytes(len(code)),code,name+' ABI shim')
        veneer=image.near_veneer(site,shim,name='ARM '+name+' tail veneer')
        image.patch(site,preimages[name],n.arm_branch(site,veneer,link=True),name+' scoped native hook')
        hooks[name]={'site':site,'shim':shim,'veneer':veneer}
    if not poster_only:
        skip=0x10b5c50
        image.patch(skip,original.read(skip,4),n.arm_branch(skip,0x10b5e28),'return through original integer/VFP epilogue after local purchase')
        market=image.method(67762)
        image.patch(market,original.read(market,8),n.word(0xe3a00000)+n.word(0xe12fff1e),'offline catalog does not query SDK market')
        buy=image.method(81315)
        image.patch(buy,original.read(buy,4),n.arm_branch(buy,image.method(81322)),'offline buy button uses native product refresh without payment limits')
    report=image.save(output/'libil2cpp.so')
    report.update(hooks=hooks,address_mapping={hex(k):hex(v) for k,v in mapping.items()},
                  scope='bridge poster supplier only' if poster_only else 'current Sony ARM preimage plus accepted supply/poster/recharge/welfare',
                  device_operation='none',human_acceptance='pending')
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    v=p.parse_args();print(build(v.source,v.output))
