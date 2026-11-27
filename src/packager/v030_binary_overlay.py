"""Apply a reviewed supplemental Unity/native/audio overlay with strict preimages.

Use stages `native` before runtime capabilities, `unity` after shop-artwork,
and `audio` as an explicit assets override during APK composition. No historical
APK is read: --game is the original 1.9 input; pre-existing stage outputs provide
the effective prior content, if any. Importable by the official build pipeline.
"""
import argparse,hashlib,json,zipfile
from pathlib import Path

PREFIX='fuka601/v1/'
BUNDLE_SHA256='8a39942e61f83e72089c4bc6ff804419c4f2c9830b756fbbd246d68f4a837026'
def digest(b):return hashlib.sha256(b).hexdigest()
def load(bundle):
    with Path(bundle).open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=BUNDLE_SHA256:raise ValueError('Unrecognized V0.3.0 binary bundle')
    z=zipfile.ZipFile(bundle); names=z.namelist()
    if len(names)!=len(set(names)):raise ValueError('Duplicate member')
    m=json.loads(z.read(PREFIX+'manifest.json'))
    if m.get('schema')!=1 or m.get('purpose')!='reviewed-v030-unity-native-audio-overlay':raise ValueError('Wrong overlay manifest')
    return z,m
def blob(z,name,expected,size=None):
    if not name.startswith(PREFIX) or '..' in Path(name).parts:raise ValueError('Invalid member')
    v=z.read(name)
    if digest(v)!=expected or (size is not None and len(v)!=size):raise ValueError('Payload mismatch '+name)
    return v
def apply_native(bundle,native):
    z,m=load(bundle)
    with z:
        spec=m['native'];before=native.read_bytes()
        if len(before)!=spec['before_size'] or digest(before)!=spec['before_sha256']:raise ValueError('Native preimage mismatch')
        after=bytearray(before);end=0
        for row in spec['ranges']:
            off=row['offset'];x=bytes.fromhex(row['before_hex']);y=bytes.fromhex(row['after_hex'])
            if off<end or len(x)!=len(y) or after[off:off+len(x)]!=x:raise ValueError('Native patch preimage mismatch')
            after[off:off+len(x)]=y;end=off+len(x)
        after.extend(blob(z,spec['tail_member'],spec['tail_sha256']))
        if len(after)!=spec['after_size'] or digest(after)!=spec['after_sha256']:raise ValueError('Native output mismatch')
        native.write_bytes(after)
    return spec['after_sha256']
def apply_unity(bundle,game,overrides):
    z,m=load(bundle);overrides=Path(overrides)
    with z,zipfile.ZipFile(game) as apk:
        apk_names=set(apk.namelist());pending=[];seen=set()
        for row in m['unity']:
            target=row['target'];prefix='assets/bin/Data/'
            if not target.startswith(prefix):raise ValueError('Wrong Unity target')
            name=target[len(prefix):]
            if not name or '/' in name or '\\' in name or name in seen:raise ValueError('Unsafe or duplicate Unity target')
            seen.add(name);stage=overrides/name
            current=stage.read_bytes() if stage.exists() else apk.read(target) if target in apk_names else None
            if (digest(current) if current is not None else None)!=row['before']:raise ValueError('Unity preimage mismatch '+target)
            pending.append((stage,blob(z,row['member'],row['after'],row['size'])))
        overrides.mkdir(parents=True,exist_ok=True)
        for stage,payload in pending:stage.write_bytes(payload)
    return len(pending)
def apply_audio(bundle,game,output):
    z,m=load(bundle)
    with z,zipfile.ZipFile(game) as apk:
        spec=m['audio'];prior=apk.read(spec['target'])
        if digest(prior)!=spec['before_sha256']:raise ValueError('Audio preimage mismatch')
        after=blob(z,spec['member'],spec['after_sha256'],spec['size'])
        output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(after)
    return {'target':spec['target'],'path':str(output),'sha256':spec['after_sha256']}
def main():
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['native','unity','audio']);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--game',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.kind=='native':result=apply_native(a.bundle,a.output)
    elif a.kind=='unity':result=apply_unity(a.bundle,a.game,a.output)
    else:result=apply_audio(a.bundle,a.game,a.output)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
