"""Original ARM/A32 resource suppliers; offline compilation and shared-image hooks.

No device operations. Source calls, metadata declarations, array layout, relocation
and EHABI tables must pass before these hooks can be installed. The root agent
owns image finalization and human Bridge acceptance.
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
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import subprocess

import analyze19 as a
import server19_arm_native as n

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'server19_arm_resources.c'
DEFAULT_OUTPUT = ROOT / '.local-baseline/server19-dev/sony-arm-resources/v1'
TOOLS = ROOT / '.local-baseline/server19-dev/sony-arm-tools/zig-0.15.2'
VENEER_MID = 72854
BLOCK_BYTES = 65536
SAVE_MASK = 0x41f0  # r4..r8,lr;24 bytes followed by8 bytes stack locals.
ASYNC_JSON = (
    {'selector':0,'name':'effect-name registries','method':59769,'call':0xa0f96c,'coroutine_reg':4,
     'field':'<effectPatternNamesRegistryPathes>__1','field_offset':12,'index_field':'<ix>__8','index_offset':48},
    {'selector':1,'name':'volatile graphics registry','method':60266,'call':0xb976bc,'coroutine_reg':4,
     'field':'<asyncRequest>__0','field_offset':12},
    {'selector':2,'name':'graphics registries','method':60266,'call':0xb97af4,'coroutine_reg':4,
     'field':'<configFilePath>__6','field_offset':40},
    {'selector':3,'name':'AI grid registries','method':58807,'call':0xe91a4c,'coroutine_reg':5,
     'field':'<gridFilePath>__7','field_offset':44},
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Elf32:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.header = struct.unpack_from('<16sHHIIIIIHHHHHH', self.data)
        h = self.header
        if h[0][:7] != b'\x7fELF\x01\x01\x01' or h[2] != 40:
            raise ValueError('Compiler did not produce little-endian ELF32 ARM')
        self.sections = [list(struct.unpack_from('<10I', self.data, h[6]+i*h[11])) for i in range(h[12])]
        strings = self.bytes(self.sections[h[13]])
        self.named = {self.cstr(strings, s[0]): s for s in self.sections}
        self.symbols = {}
        self.undefined = []
        for s in self.sections:
            if s[1] != 2:
                continue
            names = self.bytes(self.sections[s[6]])
            for pos in range(s[4], s[4]+s[5], s[9]):
                name, va, size, info, other, section = struct.unpack_from('<IIIBBH',self.data,pos)
                name = self.cstr(names,name)
                if name and section == 0:
                    self.undefined.append(name)
                if name and section:
                    self.symbols[name] = {'va':va,'size':size,'type':info&15,'section':section}

    @staticmethod
    def cstr(data, pos):
        return data[pos:data.index(0,pos)].decode('utf8')

    def bytes(self, section):
        return self.data[section[4]:section[4]+section[5]]

    def mapped(self, va, size):
        for s in self.sections:
            if s[2]&2 and s[1] != 8 and s[3] <= va and va+size <= s[3]+s[5]:
                p=s[4]+va-s[3]
                return self.data[p:p+size]
        raise ValueError(f'Compiler VA {va:#x} is not mapped')

    def payload(self, base):
        allocated = [s for s in self.sections if s[2]&2 and s[5]]
        if self.undefined:
            raise ValueError('Unresolved compiled helper imports: '+repr(self.undefined))
        for name,s in self.named.items():
            if s[5] and ((s[2]&3)==3 or (s[2]&2 and s[1]==8)):
                raise ValueError('RX helper cannot contain writable storage: '+name)
            if s[1] in (4,9) and s[5]:
                raise ValueError('Linked helper retains relocation section: '+name)
        if not allocated or min(s[3] for s in allocated)!=base:
            raise ValueError('Compiled allocation base differs')
        end=max(s[3]+s[5] for s in allocated)
        if end-base>BLOCK_BYTES:
            raise ValueError('ARM C supplier exceeds reserved RX block')
        result=bytearray(end-base)
        for s in allocated:
            result[s[3]-base:s[3]-base+s[5]]=self.bytes(s)
        return bytes(result)


def methods_of(owner, name, count):
    return [i for i,m in enumerate(a.M) if a.type_name(m[1])==owner and a.string(m[0])==name and m[15]==count]


def validate_abi(image):
    proof={}
    for owner,method,count,expected in (
        ('FullSerializer.fsJsonParser','Parse',2,30453),
        ('FullSerializer.fsSerializer','TryDeserialize',3,30520),
    ):
        got=methods_of(owner,method,count)
        if got!=[expected]:
            raise ValueError('runtime_invoke name/arity is ambiguous: '+repr(got))
        proof[owner+'::'+method]={'method':expected,'arity':count,'boxed_return':'FullSerializer.fsResult'}
    va=image.symbol('_ZN6il2cpp2vm5Array22GetFirstElementAddressEP11Il2CppArray')
    if image.read(va,8)!=bytes.fromhex('100080e21eff2fe1'):
        raise ValueError('Actual ARM array data layout changed')
    proof['array']={'first_element_method':hex(va),'bytes':image.read(va,8).hex(),'data_offset':16,
                    'evidence':'original add r0,r0,#0x10; bx lr'}
    fields={}
    for owner, names in {
        'MoleMole.Bake.PackedStringMap':['strings','packedHash'],
        'MoleMole.Bake.PackedConfigContainer':['indices','overrideIndices','packedBytes','packedHash'],
        'MoleMole.Bake.PackedIndexConfigContainer':['offsets','packedBytes','packedHash'],
        'FullSerializer.fsResult':['_success'],
    }.items():
        fields[owner]={name:image.field_offset(owner,name) for name in names}
    proof['fields_checked_from_ARM_registration']=fields
    for va,expected in (
        (0x2c71aa0,'043091e50c1091e5011080e00300a0e10030a0e30dffffea'),
        (0x2c717ec,'010056e300509505005088e5'),
        (0x2c71850,'0000a0e3000055e300009515000088e5'),
        (0x2c7188c,'0000a0e3000055e3b000d511b000c8e1'),
    ):
        # Source bytes distinguish old API object-direct references from value
        # addresses; no inference from a different IL2CPP version's API names.
        got=image.read(va,len(bytes.fromhex(expected)))
        if got!=bytes.fromhex(expected):
            raise ValueError('Original ARM Field.SetValueRaw source contract differs at '+hex(va))
    proof['field_set_value_contract']={
        'entry_va':'0x2c71aa0','raw_va':'0x2c716f0','dereference_argument':0,
        'reference_branch':'0x2c717ec cmp r6,#1; ldreq r5,[r5]; 0x2c717f4 str r5,[r8]',
        'reference_value':'direct managed object, not address of object variable',
        'primitive_value':'address of actual UInt32/UInt16 data; original ldr/ldrh then store',
        'runtime_guard':'every managed reference write reads the original field back and requires pointer identity',
        'failure_evidence':'Sony first startup capacity exception followed StringMap supply; pre-fix source deterministically wrote &value stack address through the verified object-direct API',
    }
    proof['direct_call_methods']={str(i):{'name':a.N[i],'va':hex(image.method(i)),'argc':a.M[i][15],
                                          'first_instructions':[f'{x.mnemonic} {x.op_str}' for x in image.disasm(i)[:10]]}
                                  for i in (458,475,391,16691,87740,18021)}
    proof['direct_static_ABI']='Original IL2CPP1.9 dummy receiver in r0; actual static parameters r1 onward, checked native prologues and callers'
    return proof


def generate_header(image, output):
    text=SOURCE.read_text(encoding='utf8')
    apis=sorted(set(re.findall(r'FN\((\w+),',text)) - {'n'})
    mids=sorted(set(int(x) for x in re.findall(r'MF\((\d+),',text)))
    header=['/* Pinned original ARM ELF export and method addresses, module relative. */']
    for api in apis:
        header.append(f'#define ARMAPI_{api} 0x{image.symbol("il2cpp_"+api):x}U')
    for mid in mids:
        header.append(f'#define ARMM_{mid} 0x{image.method(mid):x}U')
    # Packed containers and original StringMap retain the same original hash.
    baked=ROOT/'.local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-baked/_baked/stringmap.txt'
    manifest=ROOT/'.local-baseline/server19-dev/baked-fallback/manifest.json'
    doc=json.loads(manifest.read_text(encoding='utf8'))
    maps=[rec for rec in doc['resources'] if rec['name']=='StringMap']
    if len(maps)!=1 or maps[0]['packed_hash']!=182510128 or not baked.exists():
        raise ValueError('Original StringMap hash provenance/source supply is unavailable')
    packed_hash=maps[0]['packed_hash']
    # Root StringMap hash is constrained again by actual binary payload supplier.
    header += ['#define ARM_ARRAY_DATA_OFFSET 16U',f'#define ARM_STRINGMAP_HASH {packed_hash}U']
    p=output/'arm-resource-api.h';p.write_text('\n'.join(header)+'\n',encoding='utf8')
    return {'header_sha256':sha(p),'apis':apis,'methods':mids,'stringmap_packed_hash':packed_hash,
            'stringmap_source_sha256':sha(baked),'provenance_manifest_sha256':sha(manifest)}


def zig_path(explicit=None):
    if explicit:
        p=Path(explicit)
    else:
        choices=list(TOOLS.rglob('zig.exe')) if TOOLS.exists() else []
        if len(choices)!=1:
            raise ValueError('Authorized portable Zig compiler not ready; no download attempted')
        p=choices[0]
    if not p.exists() or not p.resolve().is_relative_to(TOOLS.resolve()):
        raise ValueError('Use only the explicitly authorized workspace Zig0.15.2')
    return p


def compile_payload(image, output, base, zig=None):
    compiler=zig_path(zig)
    obj=output/'resources.o';elf=output/'resources.elf';script=output/'resources.ld'
    script.write_text('ENTRY(arm_text_supply)\nSECTIONS {\n . = '+hex(base)+';\n'
                      ' .text : { *(.text*) }\n .rodata : { *(.rodata*) }\n'
                      ' .ARM.extab : { *(.ARM.extab*) }\n .ARM.exidx : { *(.ARM.exidx*) }\n'
                      ' .data : { *(.data*) *(.got*) }\n .bss : { *(.bss*) *(COMMON) }\n'
                      ' /DISCARD/ : { *(.comment) *(.note*) }\n}\n'+
                      '\n'.join(f'PROVIDE({name} = {hex(image.symbol(name))});' for name in
                                ('__aeabi_unwind_cpp_pr0','__aeabi_unwind_cpp_pr1','__aeabi_unwind_cpp_pr2'))+'\n',encoding='utf8')
    compile_cmd=[str(compiler),'cc','-target','arm-freestanding-eabi','-mcpu=cortex_a8','-marm','-mfloat-abi=soft',
                 '-fPIC','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-jump-tables','-funwind-tables',
                 '-fvisibility=hidden','-O1','-g0','-I',str(output),'-c',str(SOURCE),'-o',str(obj)]
    link_cmd=[str(compiler),'build-exe',str(obj),'-target','arm-freestanding-eabi','-mcpu','cortex_a8',
              '-fno-compiler-rt','-fno-PIE','-fno-strip','--no-gc-sections','--script',str(script),
              '-fentry=arm_text_supply','-femit-bin='+str(elf)]
    for cmd in (compile_cmd,link_cmd):
        import os
        env=dict(os.environ)
        env['ZIG_LOCAL_CACHE_DIR']=str(output/'zig-local-cache')
        env['ZIG_GLOBAL_CACHE_DIR']=str(output/'zig-global-cache')
        run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env)
        (output/('compile.log' if cmd is compile_cmd else 'link.log')).write_text(run.stdout,encoding='utf8')
        if run.returncode:
            raise ValueError('Authorized ARM compiler failed; see '+str(output)+' logs: '+run.stdout[-3000:])
    parsed=Elf32(elf)
    blob=parsed.payload(base)
    # PIC linked results alone are insufficient: reject absolute pointers in the
    # relocatable object even when the linker has resolved them at the fixed VA.
    reloc=Elf32(obj)
    for name,s in reloc.named.items():
        if s[1] not in (4,9):continue
        for off in range(s[4],s[4]+s[5],s[9]):
            at,info=struct.unpack_from('<II',reloc.data,off)
            kind=info&255
            if kind not in (0,3,28,29,42):
                raise ValueError(f'Unsupported ASLR relocation {kind} in {name} at {at:#x}')
    (output/'resources.bin').write_bytes(blob)
    return parsed,blob,{'compiler':str(compiler),'compile_command':compile_cmd,'link_command':link_cmd,
                        'source_sha256':sha(SOURCE),'object_sha256':sha(obj),'elf_sha256':sha(elf),
                        'blob_sha256':sha(output/'resources.bin'),'bytes':len(blob),
                        'writable_storage':'none','unresolved_relocations':'none'}


def import_unwind(image, elf):
    entries=[]
    section=elf.named.get('.ARM.exidx')
    if not section or not section[5]:raise ValueError('Compiled helper has no EHABI table')
    for off in range(0,section[5],8):
        va=section[3]+off; first,desc=struct.unpack('<II',elf.mapped(va,8))
        target=va+n.signed_prel31(first)
        extab=None if desc==1 or desc&0x80000000 else va+4+n.signed_prel31(desc)
        if desc==1:
            # Linker terminal cantunwind sentinel is outside .text. Actual C
            # callable functions must have unwind code, never cantunwind.
            text=elf.named['.text']
            if text[3]<=target<text[3]+text[5]:raise ValueError('C helper inside text is cantunwind')
            continue
        if extab is None:image.register_unwind(target,desc)
        else:image.register_unwind_external(target,extab)
        entries.append({'function_va':target,'descriptor':hex(desc),'extab_va':extab})
    return entries


def module_base(c, register=0):
    captured=c.pc+8
    c.mov(register,15)
    c.immediate(12,captured)
    c.emit(0xe040000c | (register<<16) | (register<<12))  # sub rD,rD,ip


def jump(c, target):
    try:c.branch(target)
    except ValueError:c.emit(n.arm_pic_jump(c.pc,target))


def finish_frame(c, *, pc=True):
    c.emit(0xe28dd008)
    c.pop((SAVE_MASK & ~(1<<14)) | (1<<(15 if pc else 14)))


def exception_or_return(c, image):
    c.load(1,13,0);c.emit(0xe3510000);c.branch('raise',cond='ne')
    finish_frame(c)
    c.label('raise');c.mov(0,1);finish_frame(c,pc=False)
    jump(c,image.symbol('il2cpp_raise_exception'))


def install_async_json(image, elf):
    result=[]
    for item in ASYNC_JSON:
        target=elf.symbols['arm_async_json_supply']['va']
        owner=a.type_name(a.M[item['method']][1])
        if image.field_offset(owner,item['field'])!=item['field_offset']:
            raise ValueError('Async original field layout changed')
        if 'index_field' in item and image.field_offset(owner,item['index_field'])!=item['index_offset']:
            raise ValueError('Effect registry index layout changed')
        va=image.allocate_code('ARM '+item['name']+' original-first input wrapper',256,
                               unwind=n.unwind_for_push(SAVE_MASK,8))
        c=n.ArmCode(va);c.push(SAVE_MASK);c.emit(0xe24dd008)
        c.immediate(2,0);c.store(2,13,0)
        c.call(image.method(87691))  # Original request/get_asset runs first.
        c.emit(0xe3500000);c.branch('return',cond='ne')
        module_base(c);c.mov(1,item['coroutine_reg']);c.immediate(2,item['selector']);c.mov(3,13)
        c.call(target);c.label('return');exception_or_return(c,image)
        payload=c.finish()
        if len(payload)>256:raise ValueError('Async wrapper allocation exceeded')
        image.patch(va,bytes(len(payload)),payload,item['name']+' wrapper; real32B frame, original get_asset first')
        call=item['call'];before=n.arm_branch(call,image.method(87691),link=True)
        if image.read(call,4)!=before:raise ValueError('Original async get_asset call differs')
        veneer=image.near_veneer(call,va,storage_mid=VENEER_MID,name='resource '+item['name'])
        image.patch(call,before,n.arm_branch(call,veneer,link=True),item['name']+' original JSON consumer supplier')
        result.append({**item,'wrapper_va':va,'veneer_va':veneer,'frame_bytes':32,
                       'error_semantics':'runtime_invoke exception tail-raised after restoring actual shim frame; native exceptions use exact EHABI',
                       'flow':'original async yield/get_asset, missing-only disk string, original Object.ToString and parser'})
    return result


def install_text(image, elf):
    hook=0xe0f77c;before=bytes.fromhex('0040a0e1')  # mov r4,r0
    if image.read(hook,12)!=bytes.fromhex('0040a0e1000054e30900000a'):
        raise ValueError('Original ARM text loader mov/cmp/missing branch differs')
    va=image.allocate_code('ARM original Text/Lua missing supplier shim',256,unwind=0x80b0b0b0)
    c=n.ArmCode(va)
    c.emit(0xe3500000);c.branch('missing',cond='eq')
    c.mov(4,0);jump(c,0xe0f788)
    c.label('missing');frame=c.pc
    c.push(SAVE_MASK);c.emit(0xe24dd008);c.immediate(2,0);c.store(2,13,0)
    module_base(c);c.mov(1,4);c.mov(2,13);c.call(elf.symbols['arm_text_supply']['va'])
    c.load(1,13,0);c.emit(0xe3510000);c.branch('raise',cond='ne')
    c.emit(0xe3500000);c.branch('not_found',cond='eq')
    finish_frame(c,pc=False);jump(c,0xe0f7ac)
    c.label('not_found');finish_frame(c,pc=False);c.immediate(4,0);jump(c,0xe0f7b0)
    c.label('raise');c.mov(0,1);finish_frame(c,pc=False);jump(c,image.symbol('il2cpp_raise_exception'))
    payload=c.finish();image.register_unwind(frame,n.unwind_for_push(SAVE_MASK,8))
    image.patch(va,bytes(len(payload)),payload,'ARM Text/Lua supplier; original lookup/get_text/unload or missing errors retained')
    veneer=image.near_veneer(hook,va,storage_mid=VENEER_MID,name='resource original Text/Lua')
    image.patch(hook,before,n.arm_branch(hook,veneer),'original Text/Lua missing-only input hook')
    return {'hook_va':hook,'wrapper_va':va,'frame_va':frame,'veneer_va':veneer,
            'original_present':0xe0f788,'original_return':0xe0f7ac,'original_missing':0xe0f7b0,
            'displaced_semantics':'mov r4,r0; cmp r4,#0; beq missing, explicit branches replayed; remaining original8B untouched'}


def install_original_first_factory(image, elf, *, name, hook, original_target, symbol, owner_mid):
    start,end=image.method_range(owner_mid)
    if not start<=hook<end:raise ValueError('Factory hook outside pinned original consumer')
    va=image.allocate_code('ARM '+name+' missing-only original object supplier',256,
                           unwind=n.unwind_for_push(SAVE_MASK,8))
    c=n.ArmCode(va);c.push(SAVE_MASK);c.emit(0xe24dd008)
    # Keep all original native argument registers except unused ip untouched.
    c.immediate(12,0);c.store(12,13,0);c.call(original_target)
    c.emit(0xe3500000);c.branch('return',cond='ne')
    module_base(c);c.mov(1,13);c.call(elf.symbols[symbol]['va'])
    c.label('return');exception_or_return(c,image)
    payload=c.finish();image.patch(va,bytes(len(payload)),payload,name+' factory; original source object wins')
    before=n.arm_branch(hook,original_target,link=True)
    if image.read(hook,4)!=before:raise ValueError('Original '+name+' consumer call changed')
    veneer=image.near_veneer(hook,va,storage_mid=VENEER_MID,name='resource '+name)
    image.patch(hook,before,n.arm_branch(hook,veneer,link=True),name+' original missing-only supplier')
    return {'name':name,'owner_method':owner_mid,'original_target':original_target,'hook_va':hook,
            'wrapper_va':va,'veneer_va':veneer,'frame_bytes':32,'fallback':'original missing/error behavior retained when disk source absent'}


def install_factories(image,elf):
    return [install_original_first_factory(image,elf,name='StringMap',hook=0xb833b0,
                                         original_target=0x2a39378,symbol='arm_stringmap_supply',owner_mid=60532),
            install_original_first_factory(image,elf,name='synchronous MetaConfig',hook=0xb84090,
                                         original_target=0x2a37e30,symbol='arm_metaconfig_supply',owner_mid=60518),
            install_original_first_factory(image,elf,name='async MetaConfig',hook=0xb88958,
                                         original_target=image.method(87691),symbol='arm_metaconfig_supply',owner_mid=60549)]


def install_generic(image,elf):
    hook=0x2a39378;before=bytes.fromhex('f04f2de9')
    if image.read(hook,16)!=bytes.fromhex('f04f2de91cb08de204d04de2f4029fe5'):
        raise ValueError('Original shared LoadResource A32 prologue differs')
    # Only the source first push is displaced. All PC-relative loads and original
    # branch/yield/class-initialization instructions execute at their old VA.
    trampoline=image.allocate_code('ARM original shared LoadResource first-push replay',32,
                                   unwind=n.unwind_for_push(0x4ff0))
    t=n.ArmCode(trampoline);t.emit(before);jump(t,hook+4)
    raw=t.finish();image.patch(trampoline,bytes(len(raw)),raw,'replay only original36B push then exact original+4; no PC-relative relocation')
    va=image.allocate_code('ARM shared original-first Baked/typed supply wrapper',256,
                           unwind=n.unwind_for_push(SAVE_MASK,8))
    c=n.ArmCode(va);c.push(SAVE_MASK);c.emit(0xe24dd008)
    c.mov(4,1);c.mov(5,3);c.immediate(12,0);c.store(12,13,0)
    c.call(trampoline);c.emit(0xe3500000);c.branch('return',cond='ne')
    module_base(c);c.mov(1,4);c.mov(2,5);c.mov(3,13)
    c.call(elf.symbols['arm_generic_supply']['va'])
    c.label('return');exception_or_return(c,image)
    raw=c.finish();image.patch(va,bytes(len(raw)),raw,'real32B frame; native resource body returns first; exact return-class gated disk supply')
    veneer=image.near_veneer(hook,va,storage_mid=VENEER_MID,name='resource shared Baked/typed')
    image.patch(hook,before,n.arm_branch(hook,veneer),'shared original LoadResource missing-only input wrapper entry')
    return {'hook_va':hook,'wrapper_va':va,'veneer_va':veneer,'trampoline_va':trampoline,
            'original_resume':hook+4,'original_registers':{'path':'r1','assetMode':'r2','MethodInfo':'r3','dummy':'r0'},
            'return_type_gate':'actual inflated MethodInfo return-class itemList or exact original Packed(Config/Index)Container',
            'fallback':'original resource object wins; all original branch/tailcall/error behavior retained; absent disk remains null',
            'relocated_original_bytes':before.hex(),'PC_relative_relocation':'none; only push replayed'}


def prepare(image, output=DEFAULT_OUTPUT, zig=None):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT):raise ValueError('ARM resource outputs must stay in workspace')
    output.mkdir(parents=True,exist_ok=True)
    abi=validate_abi(image);header=generate_header(image,output)
    base=image.allocate_code('original ARM C resource suppliers RX-only',BLOCK_BYTES)
    elf,blob,build=compile_payload(image,output,base,zig)
    image.patch(base,bytes(len(blob)),blob,'compiled original ARM resource input suppliers; PIC/no writable state')
    unwind=import_unwind(image,elf)
    report={'schema':1,'source_sha256':image.source_sha256,'ABI':abi,'header':header,'build':build,
            'base':base,'symbols':elf.symbols,'unwind':unwind,'device_operation':'none',
            'human_Bridge_acceptance':'pending','suppliers':['Text/Lua','StringMap','MetaConfig','Baked','typed metadata','4 async JSON']}
    (output/'build-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return elf,report


def install(image, output_directory=DEFAULT_OUTPUT, zig=None):
    if image.finalized:raise ValueError('Resource install requires the shared, unfinalized ARM image')
    elf,report=prepare(image,output_directory,zig)
    hooks={'text_lua':install_text(image,elf),'async_json':install_async_json(image,elf),
           'stringmap_and_metaconfig':install_factories(image,elf),'baked_and_typed':install_generic(image,elf)}
    report['hooks']=hooks
    report['supplier_scope']=['text_lua','stringmap','metaconfig','baked','typed_metadata','async_json']
    report['all_six_suppliers_installed']=True
    report['finalization_owner']='root only; this component does not finalize or save the image'
    report['validation']={'compiled_PIC_no_writable_state':True,'exact_ARM_preimages':True,
                           'actual_array_layout_and_fields':True,'real_EHABI_per_function':True,
                           'human_Bridge_acceptance':'pending'}
    (Path(output_directory)/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=DEFAULT_OUTPUT);p.add_argument('--zig')
    args=p.parse_args();image=n.ArmImage();elf,report=prepare(image,args.output,args.zig)
    print(json.dumps({'build_manifest':str(args.output/'build-manifest.json'),'bytes':report['build']['bytes'],
                      'compiled_only':True,'device_operations':'none','human_acceptance':'pending'}))
