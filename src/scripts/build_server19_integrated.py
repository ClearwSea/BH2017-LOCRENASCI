"""Merge accepted game + shared Python host without rebuilding game resources.

Prototype: existing verified external game resources and explicit save import remain required.
Outputs an unsigned APK; signing and technical deployment are separate steps.
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
import argparse, hashlib, json, re, struct as st, zipfile

NONE = 0xffffffff
ANDROID = 'http://schemas.android.com/apk/res/android'
OLD = 'com.miHoYo.enterprise.NGHSoD'
NEW = 'com.miHoYo.enterprise.NGHSoI'

def u32(b, offset): return st.unpack_from('<I', b, offset)[0]

class Manifest:
    def __init__(self, raw):
        assert raw[:4] == b'\x03\x00\x08\x00'
        self.chunks = []; offset = 8
        while offset < len(raw):
            size = u32(raw, offset + 4); assert size >= 8
            self.chunks.append(bytearray(raw[offset:offset+size])); offset += size
        pool = next(c for c in self.chunks if st.unpack_from('<H',c)[0] == 1)
        count, styles, flags, start = st.unpack_from('<4I',pool,8)
        assert styles == 0, 'Styled manifest pool not supported'
        self.strings = []
        def length(pos, wide):
            n = st.unpack_from('<H' if wide else '<B',pool,pos)[0]; pos += 2 if wide else 1
            mask = 0x8000 if wide else 0x80
            if n & mask:
                second = st.unpack_from('<H' if wide else '<B',pool,pos)[0]; pos += 2 if wide else 1
                n = ((n & (mask-1)) << (16 if wide else 8)) | second
            return n,pos
        for i in range(count):
            pos = start + u32(pool,28+i*4)
            n,pos = length(pos,not(flags & 0x100))
            if flags & 0x100:
                n,pos = length(pos,False); self.strings.append(bytes(pool[pos:pos+n]).decode('utf-8'))
            else: self.strings.append(bytes(pool[pos:pos+2*n]).decode('utf-16-le'))
        resource = next(c for c in self.chunks if st.unpack_from('<H',c)[0] == 0x180)
        self.ids = list(st.unpack_from('<'+'I'*((len(resource)-8)//4),resource,8))

    def index(self, value, rid=0):
        if value not in self.strings: self.strings.append(value)
        index = self.strings.index(value)
        if rid:
            self.ids.extend([0]*max(0,index+1-len(self.ids)))
            assert self.ids[index] in (0,rid); self.ids[index] = rid
        return index

    def text(self, index): return None if index == NONE else self.strings[index]

    def attrs(self, chunk):
        start,size,count = st.unpack_from('<3H',chunk,24)
        assert size == 20
        return [16+start+i*size for i in range(count)]

    def attribute(self, name, value, rid, kind=3):
        ni = self.index(name,rid)
        data = self.index(value) if kind == 3 else value
        return st.pack('<IIIHBBI',self.index(ANDROID),ni,data if kind==3 else NONE,8,0,kind,data)

    def element(self, name, attributes, children=()):
        attrs = b''.join(sorted(attributes,key=lambda b:self.ids[u32(b,4)]))
        ni = self.index(name)
        start = st.pack('<HHIII',0x102,16,36+len(attrs),1,NONE)
        start += st.pack('<II6H',NONE,ni,20,20,len(attributes),0,0,0)+attrs
        end = st.pack('<HHIIIII',0x103,16,24,1,NONE,NONE,ni)
        return [bytearray(start),*children,bytearray(end)]

    def patch(self):
        chunks=[]; skip=0; intent_start=None
        for c in self.chunks:
            typ=st.unpack_from('<H',c)[0]
            name=self.text(u32(c,20)) if typ in (0x102,0x103) else None
            if typ==0x102:
                if skip: skip+=1; continue
                if name=='intent-filter': intent_start=len(chunks)
                game_activity = name == 'activity' and any(
                    self.text(u32(c,p+4)) == 'name' and c[p+15] == 3 and
                    self.text(u32(c,p+16)) == 'com.miHoYo.overridenativeactivity.OverrideNativeActivity'
                    for p in self.attrs(c))
                for pos in self.attrs(c):
                    key=self.text(u32(c,pos+4)); kind=c[pos+15]; val=u32(c,pos+16)
                    text=self.text(val) if kind==3 else None
                    replacement=None
                    if name=='manifest' and key=='package': replacement=NEW
                    if (name=='application' or game_activity) and key=='label':
                        replacement='崩坏3·2017 独立版'; c[pos+15]=3
                    if key=='authorities' and text: replacement=text.replace(OLD,NEW)
                    if name=='uses-sdk' and key=='minSdkVersion': st.pack_into('<I',c,pos+16,24)
                    if name=='application' and key=='debuggable': st.pack_into('<I',c,pos+16,NONE)
                    if replacement is not None:
                        index=self.index(replacement); st.pack_into('<I',c,pos+8,index); st.pack_into('<I',c,pos+16,index)
                    if name=='action' and key=='name' and text=='android.intent.action.MAIN':
                        assert intent_start is not None
                        chunks=chunks[:intent_start];skip=2;break
                if skip: continue
            elif typ==0x103:
                if skip: skip-=1;continue
                if name=='application':
                    a=self.attribute
                    launcher=self.element('intent-filter',[],
                        self.element('action',[a('name','android.intent.action.MAIN',0x01010003)])+
                        self.element('category',[a('name','android.intent.category.LAUNCHER',0x01010003)]))
                    chunks += self.element('activity',[
                        a('name','local.bh3.server19probe.IntegratedActivity',0x01010003),
                        # Rotate the existing preparation view without recreating its import worker.
                        a('screenOrientation',10,0x0101001e,0x10),
                        a('configChanges',0x0d80,0x0101001f,0x11),
                        a('exported',NONE,0x01010010,0x12)],launcher)
                    chunks += self.element('service',[
                        a('name','local.bh3.server19probe.IntegratedService',0x01010003),
                        a('process',':server',0x01010011),a('exported',0,0x01010010,0x12)])
                if name=='manifest':
                    chunks += self.element('uses-permission',[self.attribute('name','android.permission.FOREGROUND_SERVICE',0x01010003)])
            chunks.append(c)
        assert skip==0
        self.chunks=chunks

    def encode(self):
        data=bytearray();offsets=[]
        def length(n):
            return st.pack('<H',n) if n<0x8000 else st.pack('<HH',0x8000|(n>>16),n&65535)
        for s in self.strings:
            offsets.append(len(data)); b=s.encode('utf-16-le'); data+=length(len(b)//2)+b+b'\0\0'
        data+=b'\0'*((-len(data))%4)
        pool=st.pack('<HHI5I',1,28,28+4*len(offsets)+len(data),len(offsets),0,0,28+4*len(offsets),0)
        pool+=st.pack('<'+'I'*len(offsets),*offsets)+data
        resources=st.pack('<HHI',0x180,8,8+4*len(self.ids))+st.pack('<'+'I'*len(self.ids),*self.ids)
        body=b''.join(pool if st.unpack_from('<H',c)[0]==1 else resources if st.unpack_from('<H',c)[0]==0x180 else c for c in self.chunks)
        return st.pack('<HHI',3,8,len(body)+8)+body

def build(game, host, native, output, embedded=None, announcement_prefab=None):
    # APK readers reject ZIP64; Python's conservative default switches at 2 GiB.
    zipfile.ZIP64_LIMIT = 0xFFFFFFFF
    assert not output.exists(), 'Do not overwrite a candidate'
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(game) as src, zipfile.ZipFile(host) as wrapper, zipfile.ZipFile(output,'w',allowZip64=False) as dst:
        assert 'lib/armeabi-v7a/libil2cpp.so' in src.namelist()
        manifest=Manifest(src.read('AndroidManifest.xml'));manifest.patch();raw=manifest.encode()
        # Round-trip parser validates the reconstructed string pool before packaging.
        parsed=Manifest(raw);assert NEW in parsed.strings
        dex=[n for n in src.namelist() if re.fullmatch(r'classes\d*\.dex',n)]
        next_dex=max(int(re.search(r'\d+',n)[0]) if re.search(r'\d+',n) else 1 for n in dex)+1
        written=set();added=[]
        for entry in src.infolist():
            n=entry.filename
            if n.startswith('META-INF/') or entry.is_dir():continue
            payload=raw if n=='AndroidManifest.xml' else native.read_bytes() if n=='lib/armeabi-v7a/libil2cpp.so' else src.read(entry)
            if announcement_prefab and n=='assets/bin/Data/b753f392eb85c9b4e9a3255042f9064a':
                assert hashlib.sha256(payload).hexdigest()=='65dc6c7fff940b4bd9b7c9659dae1837b15d8692c7ce39bca8ae887f054d1ebb'
                payload=announcement_prefab.read_bytes()
            dst.writestr(entry,payload);written.add(n)
        for entry in wrapper.infolist():
            n=entry.filename
            if re.fullmatch(r'classes\d*\.dex',n): n=f'classes{next_dex}.dex';next_dex+=1
            elif not n.startswith(('lib/armeabi-v7a/','assets/')):continue
            if entry.is_dir():continue
            payload=wrapper.read(entry)
            if n in written:
                assert src.read(n)==payload,'Collision: '+n
                continue
            dst.writestr(n,payload,compress_type=zipfile.ZIP_DEFLATED,compresslevel=1);written.add(n);added.append(n)
        if embedded:
            for name in ('client-resources.json', 'client-resources.zip'):
                dst.write(embedded/name, 'assets/'+name, compress_type=zipfile.ZIP_STORED)
    assert output.stat().st_size < 2**31 - 16*1024*1024, 'ARM32 Android 9 asset reader requires APK below 2 GiB; use --split-video resource preparation'
    report=dict(package=NEW,core='server19-common.1',game=str(game),host=str(host),native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
        apk=str(output),sha256=hashlib.file_digest(output.open('rb'),'sha256').hexdigest(),added_entries=added,
        limitations=['Unsigned until signing step', 'Embedded resources; first-run extraction required' if embedded else 'Existing external resources required',
            'User save import required on fresh install','Human gameplay not tested','Original SDK Application retained; server-process initialization must be verified'])
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='added_entries'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('game','host','native','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--embedded',type=Path)
    p.add_argument('--announcement-prefab',type=Path)
    a=p.parse_args();build(a.game,a.host,a.native,a.output,a.embedded,a.announcement_prefab)
