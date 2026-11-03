"""Deploy the approved601 candidate to Sony, with changed-file backups only.

Requires an already exited game, idle Sony server ports and explicit user
authorization for the30-fragment fixture. Does not launch/stop the game.
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
from copy import deepcopy
import hashlib
import json
import shutil
import socket
import subprocess
import time
import server19_fuka601_server as fuka
import server19_stage as stage
import server19_avatar_fragments as fragments

ROOT = Path(__file__).resolve().parent
READY = fuka.DEFAULT_READY
WORK = READY.parent
_TARGET_FILE = ROOT / 'server19-run/sony-adb-target.txt'
SERIAL = _TARGET_FILE.read_text(encoding='utf8').strip() if _TARGET_FILE.exists() else 'REFERENCE_DEVICE'
PACKAGE = 'com.miHoYo.enterprise.NGHSoD'
ADB = Path.home() / 'AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe'
WRAPPER = ROOT / 'server19-run/black3d-repair/local-comparison-1791780361/run-comparison-server.py'
ACCOUNT = WRAPPER.parent / 'scratch-server/account.json'


def adb(*args, check=True):
    result = subprocess.run([str(ADB), '-s', SERIAL, *args], capture_output=True, text=True, timeout=90)
    if check and result.returncode:
        raise RuntimeError((result.stdout + result.stderr)[-2000:])
    return result.stdout.strip()


def shell(command, root=False):
    return adb('shell', "su -c '" + command + "'" if root else command)


def main():
    if (READY / 'deployment.json').exists():
        raise ValueError('Candidate already deployed; do not reapply the fragment fixture')
    if adb('get-state') != 'device' or adb('shell', 'pidof', PACKAGE, check=False):
        raise ValueError('Sony must be connected with the game already exited')
    for port in (21028, 21029):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise ValueError('Sony service is running; stop only the verified owned service first')
    library = (WORK / 'source/device-library-path.txt').read_text(encoding='utf-8').strip()
    code_path = adb('shell', 'pm', 'path', PACKAGE).removeprefix('package:').rsplit('/', 1)[0]
    if library != code_path + '/lib/arm/libil2cpp.so':
        raise ValueError('Installed Sony package changed')
    native = json.loads((WORK / 'native-v3/manifest.json').read_bytes())
    if shell('sha256sum ' + library, root=True).split()[0] != native['source_sha256']:
        raise ValueError('Sony library changed since the scoped candidate build')
    check = json.loads((READY / 'technical-check.json').read_bytes())
    if check.get('status') != 'PASS':
        raise ValueError('Scoped offline checks did not pass')
    backup = READY / 'backup'; backup.mkdir()
    shutil.copyfile(ACCOUNT, backup / 'account.json')
    shutil.copyfile(WRAPPER, backup / 'run-comparison-server.py')
    source = WRAPPER.read_text(encoding='utf-8')
    anchor = 's.load_account()'
    if source.count(anchor) != 1 or 'server19_fuka601_server' in source:
        raise ValueError('Unexpected existing Sony wrapper')
    replacement = 'import server19_fuka601_server\nserver19_fuka601_server.configure()\n\n' + anchor
    # Ensure configuration and the authorized grant both validate before writes.
    base = ROOT / '.local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset'
    stage.TABLE_OVERRIDES = {name: base / name for name in ('materialdata', 'avatarfragmentdata', 'constvaluesclient', 'textmap')}
    stage.TABLE_OVERRIDES['textmap'] = ROOT / '.local-baseline/server19-dev/sony-human-fixes-v1/textmap'
    fuka.configure(require_deployed=False)
    before = json.loads(ACCOUNT.read_bytes()); current = deepcopy(before)
    if any(a['avatar_id'] == 601 for a in current['avatar_list']):
        raise ValueError('Existing601 state needs review before adding the authorized fixture')
    fragments.grant(current, 10601, 0, 30)
    stamp = str(int(time.time()))
    remote_backup = '/data/local/tmp/server19-fuka601-before-' + stamp + '.so'
    shell('cp ' + library + ' ' + remote_backup, root=True)
    files = [(READY / '_baked/bakedabilitydata', '/sdcard/bh3-server19-baked/_baked/bakedabilitydata'),
             (READY / 'metaconfig.txt', '/sdcard/bh3-server19-baked/metaconfig.txt'),
             (READY / 'fuka601-models.unity3d', '/sdcard/bh3-server19-fuka601/fuka601-models.unity3d')]
    files += [(path, '/sdcard/bh3-server19-metadata/_exceloutputasset/' + path.name)
              for path in (READY / '_exceloutputasset').iterdir()]
    updated = []
    for index, (local, remote) in enumerate(files):
        probe = subprocess.run([str(ADB), '-s', SERIAL, 'shell', 'test', '-f', remote], capture_output=True)
        if probe.returncode == 0:
            adb('pull', remote, str(backup / f'{index}-{Path(remote).name}'))
        shell('mkdir -p ' + remote.rsplit('/', 1)[0])
        adb('push', str(local), remote)
        if int(shell('stat -c %s ' + remote)) != local.stat().st_size:
            raise ValueError('Changed resource delivery size differs: ' + remote)
        updated.append(remote)
    if adb('shell', 'pidof', PACKAGE, check=False):
        raise ValueError('Game was opened during preparation; do not replace the running native library')
    staging = '/data/local/tmp/server19-fuka601-candidate-' + stamp + '.so'
    adb('push', str(READY / 'libil2cpp.so'), staging)
    shell('cp ' + staging + ' ' + library, root=True)
    actual = shell('sha256sum ' + library, root=True).split()[0]
    if actual != native['output_sha256']:
        raise ValueError('Native changed-file readback differs')
    stage._save(ACCOUNT, before, current)
    WRAPPER.write_text(source.replace(anchor, replacement), encoding='utf-8')
    record = {'serial': SERIAL, 'time': time.time(), 'files_updated': True,
              'updated_resources': updated, 'library': library, 'library_sha256': actual,
              'previous_library_backup': remote_backup, 'previous_library_local_source': str(WORK / 'source/libil2cpp.so'),
              'backup': str(backup), 'fragment_fixture': {'id': 10601, 'added': 30},
              'save_other_content_preserved': True, 'game_started': False, 'human_acceptance': 'pending'}
    (READY / 'deployment.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
