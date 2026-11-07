"""Explicit local-only batch readback/deployment after the human exits the game.

No force-stop, launch, server restart, save alteration or remote target writes.
All preimages and temporary postimages are verified before live file writes.
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
import argparse
import hashlib
import json
import shlex
import time
import server19_device as device
import server19_stage as stage
from server19_story_batch_delivery import OUT

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'server19-run/story-chain-batch'
READY = ROOT / '.local-baseline/server19-dev/story-chain-batch-ready/runtime-ready.json'
EXPECTED_READY_IDS = [10108, 10109, 10110]
RECEIPT_SCHEMA = 1
ADDITIONAL_RETAINED = []

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def file_hash(path):
    quoted = shlex.quote(path)
    line = device.shell('if [ -f ' + quoted + ' ]; then sha256sum ' + quoted + '; else printf ABSENT; fi', root=True).strip()
    return None if line == 'ABSENT' else line.split()[0]

def preflight():
    device.SERIAL = 'REFERENCE_DEVICE'
    info = device.identity()
    manifest = json.loads((OUT / 'manifest.json').read_bytes())
    if manifest['serial'] != device.SERIAL or manifest['ready_stage_ids'] != EXPECTED_READY_IDS:
        raise ValueError('Batch/target identity mismatch')
    rows = []
    for source in manifest['files']:
        row = dict(source)
        row['target'] = info['library'] if row['device_path'] == '@native-library' else row['device_path']
        if row['device_path'] != '@native-library' and not row['target'].startswith(('/sdcard/bh3-server19-baked/', '/sdcard/bh3-server19-resources/', '/sdcard/bh3-server19-metadata/')):
            raise ValueError('Target outside this experiment')
        if sha((OUT / row['path']).read_bytes()) != row['sha256']:
            raise ValueError('Unified candidate drift')
        row['actual_before_sha256'] = file_hash(row['target'])
        if row['actual_before_sha256'] != row['required_existing_sha256']:
            raise ValueError('Device preimage changed: ' + row['target'])
        rows.append(row)
    # The registry and Lua dependencies are retained, not rewritten.
    retained = []
    for row in manifest['required_existing_shared_Lua_files']:
        target = '/sdcard/bh3-server19-resources/' + row['path']
        actual = file_hash(target)
        if actual != row['required_existing_sha256']:
            raise ValueError('Shared Lua dependency drift: ' + target)
        retained.append({'target': target, 'sha256': actual})
    for path in ['_baked/bakedavatardata', '_baked/stringmap.txt']:
        if any(row['path'] == path for row in manifest['files']):
            continue  # A changed registry is already protected by its preimage.
        target = '/sdcard/bh3-server19-baked/' + path
        expected = sha((OUT / path).read_bytes())
        if file_hash(target) != expected:
            raise ValueError('Registry dependency drift')
        retained.append({'target': target, 'sha256': expected})
    for row in ADDITIONAL_RETAINED:
        target = info['library'] if row['target'] == '@native-library' else row['target']
        if file_hash(target) != row['sha256']:
            raise ValueError('Retained resource drift: ' + target)
        retained.append({'target': target, 'sha256': row['sha256']})
    realname = '/sdcard/bh3-server19-resources/data/channelsettings'
    expected = '73ed29729762189813e3e01be7ac2a54ab31a3f3237c6ee137b73babf7c188cf'
    if file_hash(realname) != expected:
        raise ValueError('Approved offline-channel override drift')
    retained.append({'target': realname, 'sha256': expected})
    report = {'time': time.time(), 'identity': info, 'files': rows, 'retained': retained,
        'candidate_manifest_sha256': sha((OUT / 'manifest.json').read_bytes()),
        'game_pid': device.shell('pidof ' + device.PKG + ' || true').strip(), 'operation': 'read_only'}
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / 'preflight.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report

def deploy():
    report = preflight()
    if report['game_pid']:
        raise ValueError('Human must exit the game before deployment; no automatic force-stop')
    backup = RUN / ('deployment-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir()
    account = ROOT / 'server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json'
    account_before = account.read_bytes()
    (backup / 'account-before.json').write_bytes(account_before)
    report['account_before_sha256'] = sha(account_before)
    for index, row in enumerate(report['files']):
        old = row['actual_before_sha256']
        if old is not None:
            destination = backup / ('before-' + str(index) + '.bin')
            device.adb('pull', row['target'], str(destination))
            if sha(destination.read_bytes()) != old:
                raise ValueError('Backup verification failed')
            row['backup'] = str(destination)
        row['temporary'] = '/data/local/tmp/bh3-story-batch-' + str(index) + '.next'
        device.adb('push', str(OUT / row['path']), row['temporary'])
        if file_hash(row['temporary']) != row['sha256']:
            raise ValueError('Temporary resource verification failed')
    (backup / 'before.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if device.shell('pidof ' + device.PKG + ' || true').strip():
        raise ValueError('Game reopened; prepared files kept, deployment stopped')
    for row in report['files']:
        target, temporary = shlex.quote(row['target']), shlex.quote(row['temporary'])
        commands = ['mkdir -p ' + shlex.quote(str(Path(row['target']).parent).replace('\\', '/')),
                    'cp ' + temporary + ' ' + target]
        if row['device_path'] == '@native-library':
            commands.extend(['chmod 755 ' + target, 'chown system:system ' + target])
        else:
            commands.append('chmod 644 ' + target)
        device.shell('\n'.join(commands), root=True)
        if file_hash(row['target']) != row['sha256']:
            raise ValueError('Installed readback failed: ' + row['target'])
    if account.read_bytes() != account_before:
        raise ValueError('Account changed during client deployment; inspect before activation')
    receipt = {'schema': RECEIPT_SCHEMA, 'audited_source_sha256':
        (stage.AUDITED_ACT102_INCREMENT_SHA256 if RECEIPT_SCHEMA == 1
         else stage.AUDITED_CHAPTER1_REMAINDER_SHA256),
        'ready_stage_ids': EXPECTED_READY_IDS, 'serial': device.SERIAL,
        'time': time.time(), 'candidate_manifest_sha256': report['candidate_manifest_sha256'],
        'deployment_receipt': str(backup / 'after.json'),
        'files': [{'target': row['target'], 'verified_sha256': row['sha256']} for row in report['files']]}
    if RECEIPT_SCHEMA == 2:
        receipt['act102_source_sha256'] = stage.AUDITED_ACT102_INCREMENT_SHA256
    READY.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    report.update(operation='deployed_readback_verified_human_pending', completed_at=time.time(),
        game_operation='none', server_operation='none', save_operation='none')
    (backup / 'after.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'deploy'])
    args = parser.parse_args()
    result = preflight() if args.action == 'preflight' else deploy()
    print(json.dumps({'operation': result['operation'], 'serial': result['identity']['serial'],
        'game_pid': result['game_pid'], 'verified_files': len(result['files']),
        'retained_dependencies': len(result['retained'])}))
