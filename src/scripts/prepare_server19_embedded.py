"""Build an immutable embedded resource pack from the accepted resource ledger."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def prepare(ledger, native, output, split_video=False,
            native_sha256='6f55e09f5a3cca2aaeccd9410fbce6079dc95594563819c8b57de8094e90cf6e'):
    output.mkdir(parents=True, exist_ok=False)
    raw = native.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == native_sha256
    assert raw.count(b'/sdcard/') >= 17
    assert raw.count(b'/sdcard/') == raw.count(b'/sdcard/bh3-server19-')
    patched = raw.replace(b'/sdcard/', b'./data//')
    (output / 'libil2cpp.so').write_bytes(patched)
    entries = []
    with zipfile.ZipFile(output / 'client-resources.zip', 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive, \
         zipfile.ZipFile(output / 'client-videos.zip', 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as videos:
        for item in json.loads(ledger.read_bytes()):
            remote = item['remote']
            if remote == 'installed ARM libil2cpp.so':
                continue
            if remote.startswith('/sdcard/bh3-server19-'):
                target = 'private/data/' + remote.removeprefix('/sdcard/')
            elif '/files/assets/Video/' in remote:
                target = 'external/assets/Video/' + remote.split('/files/assets/Video/', 1)[1]
            else:
                raise ValueError('Unmapped resource: ' + remote)
            source = Path(item['local'])
            payload = source.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == item['sha256'], source
            separate = split_video and target.startswith('external/')
            (videos if separate else archive).writestr(target, payload)
            entries.append(dict(path=target, size=len(payload), sha256=item['sha256'], pack='video' if separate else 'main'))
    assert len({e['path'] for e in entries}) == len(entries)
    manifest = dict(version='server19-integrated.1-private-v2', entries=entries)
    (output / 'client-resources.json').write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
    print(json.dumps(dict(files=len(entries), bytes=sum(e['size'] for e in entries), archive_bytes=(output/'client-resources.zip').stat().st_size)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ledger', 'native', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--split-video', action='store_true')
    parser.add_argument('--native-sha256', default='6f55e09f5a3cca2aaeccd9410fbce6079dc95594563819c8b57de8094e90cf6e')
    args = parser.parse_args()
    prepare(args.ledger, args.native, args.output, args.split_video, args.native_sha256)
