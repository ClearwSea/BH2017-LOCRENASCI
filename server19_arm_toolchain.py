"""Pinned portable compiler acquisition; run only after explicit authorization.

No global installation, environment change or deletion. A bad download/archive
is preserved for diagnosis and never extracted. Existing installations remain.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import stat
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / '.local-baseline/server19-dev/sony-arm-tools'
DESTINATION = TOOLS / 'zig-0.15.2'
URL = 'https://ziglang.org/download/0.15.2/zig-x86_64-windows-0.15.2.zip'
SHA256 = '3a0ed1e8799a2f8ce2a6e6290a9ff22e6906f8227865911fb7ddedc3cc14cb0c'
SIZE = 92614574
PREFIX = 'zig-x86_64-windows-0.15.2'


def acquire():
    if DESTINATION.exists():
        raise ValueError('Existing tool directory preserved; inspect before retry')
    TOOLS.mkdir(parents=True, exist_ok=True)
    archive = TOOLS / (PREFIX + '.zip')
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=30) as response, archive.open('xb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != SHA256 or archive.stat().st_size != SIZE:
        raise ValueError('Official pinned package checksum/size mismatch; preserved without extraction')
    with zipfile.ZipFile(archive) as package:
        members = []
        for entry in package.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or not path.parts or path.parts[0] != PREFIX or \
                    any(part in ('..', '.') or ':' in part or '\\' in part for part in path.parts) or \
                    stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('Unsafe or unexpected archive member')
            relative = Path(*path.parts[1:])
            target = (DESTINATION / relative).resolve()
            if not target.is_relative_to(DESTINATION.resolve()):
                raise ValueError('Extraction leaves the approved tool directory')
            members.append((entry, target))
        if sum(entry.file_size for entry, _ in members) > 1024 * 1024 * 1024:
            raise ValueError('Unexpected expanded compiler size')
        DESTINATION.mkdir()
        for entry, target in members:
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as source, target.open('xb') as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
    executable = DESTINATION / 'zig.exe'
    if not executable.is_file():
        raise ValueError('Official compiler executable absent')
    report = {'source': URL, 'source_sha256': digest, 'download_bytes': SIZE,
              'destination': str(DESTINATION), 'executable': str(executable),
              'version': '0.15.2', 'global_environment_operation': 'none',
              'automatic_execution': 'none'}
    (TOOLS / 'zig-0.15.2-acquisition.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-acquisition', action='store_true',
                        help='Operator acknowledgement of explicit human dependency authorization')
    args = parser.parse_args()
    if not args.authorized_acquisition:
        parser.error('Explicit human dependency authorization is required before acquisition')
    print(json.dumps(acquire()))
