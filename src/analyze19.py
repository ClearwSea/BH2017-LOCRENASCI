"""只读解析 1.9 元数据与原生入口 / Read-only 1.9 metadata and native analysis."""
from pathlib import Path
import struct,json,sys,re,os
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis-deps'))
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
D=Path(os.environ.get('BH3_CLIENT19_ANALYSIS_DIR',ROOT/'work/extracted/client19'));B=(D/'global-metadata.dat').read_bytes();E=(D/'lib__x86__libil2cpp.so').read_bytes()
def string(i):return B[596312+i:B.index(0,596312+i)].decode('utf-8',errors='replace')
T=[struct.unpack_from('<24I8H2I',B,10937744+i*120) for i in range(12645)]
M=[struct.unpack_from('<12I4H',B,2471292+i*56) for i in range(89054)]
def type_name(i):
 t=T[i];return '.'.join(x for x in (string(t[1]),string(t[0])) if x)
def pointer(m):return struct.unpack_from('<I',E,0x34a67ec+m[6]*4)[0] if m[6]!=0xffffffff else 0
N={i:type_name(m[1])+'::'+string(m[0]) for i,m in enumerate(M)}
ADDR={pointer(m):N[i] for i,m in enumerate(M) if pointer(m)}
H=struct.unpack_from('<16sHHIIIIIHHHHHH',E);SECTIONS=[struct.unpack_from('<10I',E,H[6]+i*H[11]) for i in range(H[12])]
S=SECTIONS[2];ST=SECTIONS[S[6]];STR=E[ST[4]:ST[4]+ST[5]]
for p in range(S[4],S[4]+S[5],16):
 idx,val,size,info,other,sec=struct.unpack_from('<IIIBBH',E,p)
 if val:ADDR[val]=STR[idx:STR.index(0,idx)].decode(errors='replace')
MD=Cs(CS_ARCH_X86,CS_MODE_32)
def disasm(i,limit=2200):
 m=M[i];p=pointer(m);out=[f'{i} {N[i]} native_index={m[6]} address={p:#x} flags={m[12]:#x} params={m[15]}']
 if not p:return '\n'.join(out)
 end=min((q for q in ADDR if q>p),default=p+limit);end=min(end,p+limit)
 for ins in MD.disasm(E[p:end],p):
  note=''
  if ins.mnemonic in ('call','jmp') and ins.op_str.startswith('0x'):
   dest=int(ins.op_str,16);note=ADDR.get(dest,'')
  out.append(f'{ins.address:08x}  {ins.mnemonic:8} {ins.op_str:36} {note}')
 return '\n'.join(out)
def describe(ti):
 t=T[ti];out=[f'TYPE {ti} {type_name(ti)} fields={t[26]} methods={t[24]}']
 for i in range(t[16],t[16]+t[26]):
  f=struct.unpack_from('<4I',B,9233316+i*16);out.append(f'FIELD {i} {string(f[0])} type={f[1]} attr={f[2]}')
 for i in range(t[17],t[17]+t[24]):out.append(f'METHOD {i} {N[i]} @{pointer(M[i]):x} argc={M[i][15]}')
 return '\n'.join(out)
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8')
 if len(sys.argv)>1 and sys.argv[1]=='disasm':
  print('\n\n'.join(disasm(int(i)) for i in sys.argv[2:]));sys.exit()
 pattern=sys.argv[1] if len(sys.argv)>1 else 'FakePacketHelper|NetworkManager|MonoGameEntry|GlobalVars|MonoDistribute|GlobalConfig|ClientSetting'
 text='\n\n'.join(describe(i) for i in range(len(T)) if re.search(pattern,type_name(i)))
 (D/'entry-type-analysis.txt').write_text(text,encoding='utf-8');print(text)
