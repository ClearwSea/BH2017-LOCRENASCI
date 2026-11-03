"""Package reviewed launcher/native replacements; raw-copy unchanged ZIP members."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse,copy,hashlib,json,shutil,struct,zipfile
from pathlib import Path

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    a=argparse.ArgumentParser();a.add_argument('--source',type=Path,required=True);a.add_argument('--dex',type=Path,required=True);a.add_argument('--native',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--receipt',type=Path,required=True);args=a.parse_args()
    assert sha(args.source)=='d160f81d1873f81e187efda1c9e43c5ab7b2ebf7f17ae914e3aa14fa8e18a0c2'
    assert not args.output.exists();replacements={'classes4.dex':args.dex,'lib/armeabi-v7a/libil2cpp.so':args.native}
    zipfile.ZIP64_LIMIT=0xffffffff
    # Inputs use no data descriptors/encryption/ZIP64. Preserve compressed bytes,
    # recreate central offsets, and omit APK signing block and META-INF entries.
    with zipfile.ZipFile(args.source) as src,args.source.open('rb') as raw,zipfile.ZipFile(args.output,'w',allowZip64=False) as dst:
        for item in src.infolist():
            if item.filename.startswith('META-INF/'):continue
            info=copy.copy(item)
            if item.filename in replacements:dst.writestr(info,replacements[item.filename].read_bytes());continue
            assert info.flag_bits in (0,2048) and info.file_size<0xffffffff and info.compress_size<0xffffffff
            raw.seek(item.header_offset);header=raw.read(30);fields=struct.unpack('<4s5H3I2H',header);assert fields[0]==b'PK\3\4'
            assert fields[6:9]==(info.CRC,info.compress_size,info.file_size)
            length=30+fields[-2]+fields[-1]+info.compress_size;raw.seek(item.header_offset)
            info.header_offset=dst.fp.tell();remaining=length
            while remaining:
                block=raw.read(min(8*1024*1024,remaining));assert block;dst.fp.write(block);remaining-=len(block)
            dst.filelist.append(info);dst.NameToInfo[info.filename]=info;dst._didModify=True;dst.start_dir=dst.fp.tell()
    with zipfile.ZipFile(args.source) as src,zipfile.ZipFile(args.output) as dst:
        assert dst.testzip() is None
        for item in src.infolist():
            if item.filename.startswith('META-INF/'):continue
            result=dst.getinfo(item.filename)
            if item.filename not in replacements:assert (item.CRC,item.file_size,item.compress_size)==(result.CRC,result.file_size,result.compress_size)
        for name,path in replacements.items():assert hashlib.sha256(dst.read(name)).hexdigest()==sha(path)
    assert args.output.stat().st_size<2**31-16*1024*1024
    args.receipt.write_text(json.dumps(dict(source_sha256=sha(args.source),output_sha256=sha(args.output),changed_entries=list(replacements),unchanged_compressed_members_preserved=True,zip_crc_pass=True),indent=2));print('Package and CRC verification PASS',flush=True)
if __name__=='__main__':main()
