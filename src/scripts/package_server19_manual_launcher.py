"""Add the launcher notice to the accepted optimized APK / 启动页说明。

仅替换启动承载DEX；已验收业务运行包、原生库和游戏资源保持。
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
OUT = ROOT / 'server19-run/manual-launcher-20261102'
LOCAL = ROOT / 'work/reference/manual-launcher'


def main():
    source = LOCAL.parent / 'launcher-notice-countdown/candidate.apk'
    assert hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() == '6ee0a882109eafa8128cd488e9760d911d0163970c8a07db36e61291ae9788c2'
    target = LOCAL / 'candidate-unsigned.apk'
    assert not target.exists()
    replacements = {'classes4.dex': OUT / 'classes4.dex'}
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
