"""模拟器限定的可回退原生探针 / Reversible emulator-only native probe."""

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
import sys,subprocess,struct,json,re,hashlib,shlex
ROOT=Path(__file__).resolve().parent;D=ROOT/'1.9.0-official';OUT=D/'bridge-probe';OUT.mkdir(exist_ok=True)
ADB=['adb','-s','REFERENCE_DEVICE'];PKG='com.miHoYo.enterprise.NGHSoD'
def adb(*args,timeout=30):
 p=subprocess.run(ADB+list(args),capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError((p.stdout+p.stderr).decode(errors='replace'))
 return p.stdout.decode('utf-8',errors='replace').strip()
def root(s):return adb('shell','su -c '+shlex.quote(s))
def identity():
 p=adb('shell','dumpsys package '+PKG)
 assert 'versionName=1.9.0' in p and 'primaryCpuAbi=x86' in p
 path=re.search(r'codePath=(\S+)',p).group(1)+'/lib/x86/libil2cpp.so'
 assert path.startswith('/data/app/'+PKG+'-') and '/lib/x86/' in path
 assert 'uid=0' in root('id')
 return path
def build():
 import analyze19 as a
 b=bytearray(a.E);changes=[]
 def edit(p,old,new,why):
  assert bytes(b[p:p+len(old)])==old,(hex(p),why)
  b[p:p+len(old)]=new;changes.append({'offset':hex(p),'before':old.hex(),'after':new.hex(),'purpose':why})
 edit(0x5471df,b'\xc6\x40\x01\x00',b'\xc6\x40\x01\x01','Enable existing DISABLE_NETWORK_DEBUG branch')
 # Reuse only an unused automatic-test helper as a PIC file-loader stub.
 cave=a.pointer(a.M[72868]);end=a.pointer(a.M[72869]);readall=a.pointer(a.M[2882])
 code=bytearray.fromhex('55 89 e5 53 83 e4 f0 83 ec 10')
 def call(target):
  pos=cave+len(code);code.extend(b'\xe8'+struct.pack('<i',target-pos-5))
 call(cave+len(code)+5);pic=cave+len(code);code+=b'\x5b'
 lea=len(code);code+=b'\x8d\x83'+b'\0'*4;code+=bytes.fromhex('89 04 24')
 call(0x29549a0)
 code+=bytes.fromhex('89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00')
 call(readall);code+=bytes.fromhex('8d 65 fc 5b 5d c3')
 path=b'/sdcard/bh3-19-profile.json\0';struct.pack_into('<i',code,lea+2,cave+len(code)-pic);code+=path
 assert len(code)<=end-cave
 edit(cave,bytes(b[cave:cave+len(code)]),bytes(code),'PIC local profile loader in unused AutoTestForAndroid helper')
 pos=0xa5ea37;old=b'\xe8'+struct.pack('<i',0xd1f511-pos-5);new=b'\xe8'+struct.pack('<i',cave-pos-5)
 edit(pos,old,new,'FakePacketHelper.LoadFromFile reads local profile instead of absent Resources TextAsset')
 import probe19_trace
 probe19_trace.install(a,b,edit)
 (OUT/'libil2cpp-probe.so').write_bytes(b)
 text=(ROOT/'2.4.0-demo/FakePacketRsp.json').read_text(encoding='utf-8')
 text=re.sub(r'//[^\n]*','',text);text=re.sub(r',\s*([}\]])',r'\1',text);text=re.sub(r'}\s*("[A-Za-z0-9]+Rsp"\s*:)',r'},\n\1',text)
 text=re.sub(r'"reward_list"\s*:\s*\[\s*"exp"\s*:\s*100\s*\]', '"reward_list": []',text)
 profile=json.loads(text);profile.pop('GetDormSnsDataRsp',None)
 profile['GetMainDataRsp']['nickname']='舰桥测试员';profile['GetMainDataRsp']['level']=80
 (OUT/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'patch-manifest.json').write_text(json.dumps({'original_sha256':hashlib.sha256(a.E).hexdigest(),'probe_sha256':hashlib.sha256(b).hexdigest(),'changes':changes,'scope':'emulator x86 only; original APK and source libraries preserved'},indent=2),encoding='utf-8')
 print('Prepared',len(changes),'native edits; profile templates',len(profile),flush=True)
def apply():
 path=identity();adb('shell','am force-stop '+PKG)
 rules=root('iptables -S BH3_LOCAL_ONLY; ip6tables -S BH3_LOCAL_ONLY')
 assert rules.count('-j REJECT')>=2
 adb('push',str(OUT/'libil2cpp-probe.so'),'/data/local/tmp/bh3-19-probe.so',timeout=60)
 adb('push',str(OUT/'profile.json'),'/sdcard/bh3-19-profile.json')
 print(root('cp /data/local/tmp/bh3-19-probe.so '+shlex.quote(path)+' && chmod 755 '+shlex.quote(path)+' && sha256sum '+shlex.quote(path)))
 (OUT/'installed-path.txt').write_text(path,encoding='utf-8')
 print(adb('shell','am start -n '+PKG+'/com.miHoYo.overridenativeactivity.OverrideNativeActivity'))
def capture(label):
 pid=adb('shell','pidof '+PKG).split()[0]
 (OUT/(label+'-logcat.txt')).write_text(adb('logcat','-d','--pid='+pid),encoding='utf-8')
 p=subprocess.run(ADB+['exec-out','screencap','-p'],capture_output=True,timeout=20);(OUT/(label+'.png')).write_bytes(p.stdout)
 print('Captured',label,pid)

def restore():
 path=identity();adb('shell','am force-stop '+PKG)
 original=D/'lib__x86__libil2cpp.so'
 expected=hashlib.sha256(original.read_bytes()).hexdigest()
 adb('push',str(original),'/data/local/tmp/bh3-19-original.so',timeout=60)
 result=root('cp /data/local/tmp/bh3-19-original.so '+shlex.quote(path)+' && chmod 755 '+shlex.quote(path)+' && sha256sum '+shlex.quote(path))
 assert result.split()[0]==expected,result
 (OUT/'restore-verification.txt').write_text(result+'\nApp stopped; original native library restored; network isolation retained.\n',encoding='utf-8')
 print(result)
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8')
 command=sys.argv[1]
 if command=='build':build()
 elif command=='apply':apply()
 elif command=='capture':capture(sys.argv[2])
 elif command=='restore':restore()
 elif command=='status':print(identity());print(root('mount | head -n 4'))
