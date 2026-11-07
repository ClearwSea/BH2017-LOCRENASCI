"""Update only native and runtime payloads in the accepted integrated APK.

只替换已验收合包的原生库与运行包；资源、Java及存档边界保持原样。
Produces an unsigned candidate. Existing files are never overwritten.
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
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'server19-run/nx-backport-20261102'


def main():
    source = ROOT / 'server19-run/announcement-banner-20261027/candidate.apk'
    assert hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() == 'd560b57b5f94406160b0a3d07b7978fd81c8f90f6e18b4161c096a42dd92d123'
    target = OUT / 'candidate-unsigned.apk'
    assert not target.exists()
    replacements = {'assets/runtime.zip': OUT / 'runtime.zip',
                    'lib/armeabi-v7a/libil2cpp.so': OUT / 'client-signin.so'}
    zipfile.ZIP64_LIMIT = 0xffffffff
    changed = []
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, 'w', allowZip64=False) as dst:
        for info in src.infolist():
            if info.filename.startswith('META-INF/'):
                continue
            if info.filename in replacements:
                raw = replacements[info.filename].read_bytes()
                dst.writestr(info, raw)
                changed.append(info.filename)
            else:
                with src.open(info) as incoming, dst.open(info, 'w') as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
    assert set(changed) == set(replacements)
    assert target.stat().st_size < 2**31 - 16*1024*1024
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target) as dst:
        assert dst.testzip() is None
        for info in src.infolist():
            if info.filename.startswith('META-INF/'):
                continue
            result = dst.getinfo(info.filename)
            if info.filename not in replacements:
                assert (info.CRC, info.file_size) == (result.CRC, result.file_size), info.filename
        for name, path in replacements.items():
            assert hashlib.sha256(dst.read(name)).digest() == hashlib.sha256(path.read_bytes()).digest()
    receipt = {'source': str(source), 'output': str(target), 'changed_entries': changed,
               'sha256': hashlib.file_digest(target.open('rb'), 'sha256').hexdigest(),
               'bytes': target.stat().st_size, 'unchanged_entries_crc_size_verified': True}
    (OUT / 'packaging.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
