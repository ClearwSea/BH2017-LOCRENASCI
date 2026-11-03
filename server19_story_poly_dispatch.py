"""Resolve small native polymorphic formatters through actual switch execution."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import re
import struct
import sys
import analyze19 as a
from server19_story_all_resources import ROOT


def evidence(schema, base_type, original_mid, tags=(1,2,3)):
    sys.path.insert(0,str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_ESP,UC_X86_REG_EIP
    result=[]
    for original in (True,False):
        binary=a.E if original else schema.source.binary
        metadata=a.B if original else schema.source.metadata
        header=struct.unpack_from('<64I',metadata)
        if original:
            methods=a.M;names=a.N;pointers={i:a.pointer(m) for i,m in enumerate(methods) if a.pointer(m)}
        else:
            methods=[struct.unpack_from('<12I4H',metadata,p) for p in range(header[12],header[12]+header[13],56)]
            names={i:schema.source.name(m[1])+'::'+schema.source.string(m[0]) for i,m in enumerate(methods)}
            pointers={i:struct.unpack_from('<I',binary,0x418f6e0+m[6]*4)[0] for i,m in enumerate(methods) if m[6]!=0xffffffff}
        mid=original_mid if original else next(i for i,n in names.items() if n==a.N[original_mid])
        start=pointers[mid];end=min(p for p in pointers.values() if p>start)
        lookup={p:names[i] for i,p in pointers.items()}
        instructions=list(a.MD.disasm(binary[start:end],start))
        read=next(x for x in instructions if x.mnemonic=='call' and x.op_str.startswith('0x') and lookup.get(int(x.op_str,16),'').endswith('MessagePackBinary::ReadInt32'))
        base=0x33e39d8 if original else 0x42531e4
        usage=schema.original_usage if original else schema.source_usage
        spec_pair,inst_pair=(0x34a67cc,0x34a67b4) if original else (0x42520f0,0x42520d8)
        candidates={}
        for ins in instructions:
            m=re.fullmatch(r'eax, \[ebx ([+-]) (0x[0-9a-f]+)\]',ins.op_str.replace('dword ptr ',''))
            if not m or ins.mnemonic!=('mov' if original else 'lea'):continue
            address=base+(1 if m[1]=='+' else -1)*int(m[2],16)
            if original:address=struct.unpack_from('<I',binary,address)[0]
            token=usage.get(address)
            if token is None or token>>29!=6:continue
            count,specs=struct.unpack_from('<II',binary,spec_pair);index=token&0x1fffffff
            assert index<count
            method,ci,mi=struct.unpack_from('<3i',binary,specs+index*12)
            name=a.string(methods[method][0]) if original else schema.source.string(methods[method][0])
            if name!='GetFormatterWithVerify' or ci!=-1 or mi<0:continue
            count,instances=struct.unpack_from('<II',binary,inst_pair);assert mi<count
            inst=struct.unpack_from('<I',binary,instances+mi*4)[0];argc,argv=struct.unpack_from('<II',binary,inst)
            if argc!=1:continue
            ptr=struct.unpack_from('<I',binary,argv)[0];ti,flags=struct.unpack_from('<II',binary,ptr)
            if flags>>16&255 not in (17,18):continue
            concrete=a.type_name(ti) if original else schema.source.name(ti)
            candidates[ins.address]=(concrete,index)
        for tag in tags:
            u=Uc(UC_ARCH_X86,UC_MODE_32)
            u.mem_map(0,0x6000000);u.mem_write(0,binary)
            u.mem_map(0x7000000,0x20000);u.reg_write(UC_X86_REG_ESP,0x7008000)
            u.reg_write(UC_X86_REG_ESI,0x7010000);u.reg_write(UC_X86_REG_EBX,base);u.reg_write(UC_X86_REG_EAX,tag)
            selected=[]
            def stop(uc,address,size,data):
                if address in candidates:selected.append((address,candidates[address]));uc.emu_stop()
            u.hook_add(UC_HOOK_CODE,stop)
            try:u.emu_start(read.address+read.size,end,count=100)
            except Exception as err:
                raise ValueError(str((base_type,original,tag,hex(u.reg_read(UC_X86_REG_EIP)),candidates))) from err
            assert len(selected)==1,(base_type,original,tag)
            address,(concrete,index)=selected[0]
            result.append({'original':original,'base_type':base_type,'tag':tag,'concrete':concrete,
                           'method_id':mid,'branch':hex(address),'method_spec_index':index,
                           'actual_x86_switch_execution':True})
    old={r['tag']:r['concrete'] for r in result if r['original']}
    new={r['tag']:r['concrete'] for r in result if not r['original']}
    assert old==new,'Original/source concrete dispatch differs'
    return result
