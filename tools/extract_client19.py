"""Extract only the analysis inputs from the supported, user-supplied APK."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES={
 'assets/bin/Data/Managed/Metadata/global-metadata.dat':('global-metadata.dat','078e04275a2ce76a43fb3d5f1d803662f2a94881f571972fa03971f6fe54da8f'),
 'lib/x86/libil2cpp.so':('lib__x86__libil2cpp.so','dc8365244e56a9de670b326d40510cab688d6876107e6a9151372917963ada7d'),
 'lib/armeabi-v7a/libil2cpp.so':('armeabi-v7a/libil2cpp.so','32e27ed130ed3a2a8c23d81c6a043510ae6cd99bd34b4bea4da1d71abae6c7a6'),
}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'work/extracted/client19')
    args=parser.parse_args();profile=json.loads((ROOT/'profiles/android-launcher-20261102.json').read_bytes())['client19']
    if args.output.exists():raise ValueError('Output already exists; use a new extraction directory')
    with args.apk.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    matches=actual==profile['sha256'] and args.apk.stat().st_size==profile['bytes']
    if not matches:print('APK differs from the reference file; checking the required analysis members instead')
    payload={}
    with zipfile.ZipFile(args.apk) as package:
        for entry,(name,expected) in FILES.items():
            raw=package.read(entry)
            if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Unexpected original input: '+entry)
            payload[name]=raw
    args.output.mkdir(parents=True)
    for name,raw in payload.items():
        path=args.output/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    print(json.dumps({'files':len(payload),'source_sha256':actual}))
if __name__=='__main__':main()
