"""Build scoped601 native input/SP support on the current Sony library."""

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
import struct
import subprocess
from pathlib import Path
import server19_arm_native as native
import server19_arm_resources as resources

ROOT=Path(__file__).resolve().parent


def build(source,output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use current-device source and a fresh workspace output')
    output.mkdir(parents=True)
    image=native.ArmImage(source,expected_sha256=None)
    api=('object_get_class','class_get_field_from_name','field_get_value','string_new',
         'domain_get','domain_get_assemblies','assembly_get_image','class_from_name',
         'runtime_invoke','class_get_method_from_name','method_get_return_type','type_get_object')
    header=['#define API_'+n+' '+hex(image.symbol('il2cpp_'+n))+'U' for n in api]
    header+=['#define METHOD_'+str(mid)+' '+hex(image.method(mid))+'U' for mid in (513,49409,47585,18021)]
    (output/'fuka-api.h').write_text('\n'.join(header)+'\n',encoding='utf-8')
    base=image.allocate_code('Fuka601 compiled input SP and bounded resource support',16384)
    provide=('__aeabi_unwind_cpp_pr0','__aeabi_unwind_cpp_pr1','__aeabi_unwind_cpp_pr2')
    ld=output/'fuka.ld'
    ld.write_text('ENTRY(fuka_button_equal)\nSECTIONS { . = '+hex(base)+'; .text : { *(.text*) } .rodata : { *(.rodata*) } .ARM.extab : { *(.ARM.extab*) } .ARM.exidx : { *(.ARM.exidx*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.comment) *(.note*) } }\n'+
        '\n'.join('PROVIDE('+n+' = '+hex(image.symbol(n))+');' for n in provide),encoding='utf-8')
    zig=resources.zig_path();obj=output/'fuka.o';linked=output/'fuka.elf'
    commands=[
        [str(zig),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a8','-marm','-mfloat-abi=softfp',
         '-fPIC','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-jump-tables','-funwind-tables',
         '-fvisibility=hidden','-ffp-contract=off','-O1','-g0','-I',str(output),'-c',str(ROOT/'server19_fuka601_runtime.c'),'-o',str(obj)],
        [str(zig),'build-exe',str(obj),'-target','arm-freestanding-eabi','-mcpu','cortex_a8',
         '-fno-compiler-rt','-fno-PIE','-fno-strip','--no-gc-sections','--script',str(ld),
         '-fentry=fuka_button_equal','-femit-bin='+str(linked)]]
    for i,cmd in enumerate(commands):
        result=subprocess.run(cmd,capture_output=True,text=True)
        (output/('compile.log' if i==0 else 'link.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise ValueError(result.stderr[-1800:])
    elf=resources.Elf32(linked);blob=elf.payload(base)
    if len(blob)>16384:raise ValueError('Fuka payload exceeds reservation')
    reloc=resources.Elf32(obj)
    for section in reloc.named.values():
        if section[1] not in (4,9):continue
        for off in range(section[4],section[4]+section[5],section[9]):
            _,info=struct.unpack_from('<II',reloc.data,off)
            if info&255 not in (0,3,28,29,42):raise ValueError('Non-PIC relocation')
    image.patch(base,bytes(len(blob)),blob,'compiled scoped601 input/SP behavior')
    resources.import_unwind(image,elf)
    # Entry storage may already contain earlier resource/supply veneers.
    stock=native.ArmImage();start,end=image.method_range(72868)
    dirty=[i for i in range(end-start) if image.read(start+i,1)!=stock.read(start+i,1)]
    image.veneer_cursors[72868]=native.align(start+max(dirty,default=-1)+1,4)
    hooks=[]
    for name,site,target in (('update',0x10d22fc,513),('pointer_down',0x10d28c8,513),('sp_cost',0xabd2fc,49409)):
        mask=0x41f0;stack=8
        shim=image.allocate_code('601 '+name+' ABI shim',160,unwind=native.unwind_for_push(mask,stack))
        c=native.ArmCode(shim);c.push(mask);c.emit(0xe24dd008)
        if name!='sp_cost':
            c.mov(8,4) # Both actual callers retain MonoSkillButton in r4.
            c.mov(4,0);c.mov(5,1);c.mov(6,2);c.mov(7,3)
            c.store(7,13,0);c.store(8,13,4)
            symbol='fuka_button_equal'
        else:
            c.mov(4,0);c.mov(5,1);c.mov(6,2);c.mov(7,3)
            c.immediate(12,0);c.store(7,13,0);c.store(12,13,4)
            symbol='fuka_sp_cost'
        c.mov(1,4);c.mov(2,5);c.mov(3,6);resources.module_base(c)
        c.call(elf.symbols[symbol]['va']);c.emit(0xe28dd008)
        c.pop((mask & ~(1<<14)) | (1<<15))
        raw=c.finish();image.patch(shim,bytes(len(raw)),raw,'601 '+name+' real-frame wrapper')
        veneer=image.near_veneer(site,shim,name='601 '+name)
        image.patch(site,native.arm_branch(site,image.method(target),link=True),native.arm_branch(site,veneer,link=True),
                    '601 '+name+' scoped original call adapter')
        hooks.append({'name':name,'site':site,'shim':shim,'veneer':veneer})
    site=0x2a39378
    before=image.read(site,4);word=struct.unpack('<I',before)[0]
    if word & 0xff000000 != 0xea000000:
        raise ValueError('Current shared resource supplier entry must be its verified ARM B veneer')
    displacement=(word & 0xffffff)<<2
    if displacement & 0x2000000:displacement-=0x4000000
    previous_target=site+8+displacement
    shim=image.allocate_code('601 original-first six-asset bundle resource wrapper',256,
                             unwind=native.unwind_for_push(resources.SAVE_MASK,8))
    c=native.ArmCode(shim);c.push(resources.SAVE_MASK);c.emit(0xe24dd008)
    c.mov(4,1);c.mov(5,3);c.immediate(12,0);c.store(12,13,0)
    c.call(previous_target);c.emit(0xe3500000);c.branch('return',cond='ne')
    resources.module_base(c);c.mov(1,4);c.mov(2,5);c.mov(3,13)
    c.call(elf.symbols['fuka_resource_supply']['va'])
    c.label('return');resources.exception_or_return(c,image)
    raw=c.finish();image.patch(shim,bytes(len(raw)),raw,'original resource and existing supply first; bounded601 bundle only after null')
    veneer=image.near_veneer(site,shim,name='601 six-asset bundle wrapper')
    image.patch(site,before,native.arm_branch(site,veneer),'chain scoped601 bundle supply after existing original-first supplier')
    hooks.append({'name':'six_missing_assets','site':site,'shim':shim,'veneer':veneer,'previous_target':previous_target})
    report=image.save(output/'libil2cpp.so');report.update(hooks=hooks,human_acceptance='pending',
        source_behavior='2.0 skill-index2 hold routed to original TryHold; 2.4 cost-SP property formula')
    (output/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(build(args.source,args.output))
