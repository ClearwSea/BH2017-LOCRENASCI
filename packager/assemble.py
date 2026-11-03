"""Recompile and assemble an APK from explicitly supplied reference artifacts.

This development mode verifies assembly, not original-input regeneration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from .core import ROOT, BuildError, digest, read_json, safe_relative, write_json, now


READY_RECORDS = {
    'story': '.local-baseline/server19-dev/story-all-20261015/runtime-ready.json',
    'equipment': '.local-baseline/server19-dev/cultivation-full-equipment-ready/runtime-ready.json',
    'extra_story': 'server19-run/kallen-20261025/all-open-delivery/runtime-ready.json',
}
PATH_KEYS = ('client19', 'reference_runtime', 'resource_ledger', 'resource_root', 'native',
             'tools_root', 'zig', 'keystore', 'work_dir', 'supplements')


def load_config(path, resume=False):
    data = read_json(path)
    if data.get('schema') != 1 or data.get('mode') != 'reference-artifacts':
        raise BuildError('This command requires explicit mode=reference-artifacts')
    allowed = set(PATH_KEYS) | {'schema', 'mode', 'key_alias', 'resource_ledger_sha256', 'wheelhouse'}
    if set(data) - allowed:
        raise BuildError('Unknown assembly configuration keys')
    result = dict(data)
    for key in PATH_KEYS:
        if not isinstance(data.get(key), str) or not data[key]:
            raise BuildError('Missing assembly path: ' + key)
        lexical = path.resolve().parent / data[key]
        result[key] = Path(os.path.abspath(lexical)) if key == 'tools_root' else lexical.resolve()
    if result['work_dir'].exists() and not resume:
        raise BuildError('Choose a new assembly work_dir')
    if result['work_dir'] == ROOT or (result['work_dir'].is_relative_to(ROOT) and not result['work_dir'].is_relative_to(ROOT / 'work')):
        raise BuildError('Assembly output inside the source tree must be under work/')
    for key in PATH_KEYS:
        if key != 'work_dir' and (result[key] == result['work_dir'] or result[key].is_relative_to(result['work_dir'])):
            raise BuildError('Assembly output would contain an input')
    if not result.get('key_alias') or len(result.get('resource_ledger_sha256', '')) != 64:
        raise BuildError('Explicit signing alias and resource ledger fingerprint are required')
    if data.get('wheelhouse'):
        result['wheelhouse'] = (path.resolve().parent / data['wheelhouse']).resolve()
    return result


def run_command(args, work, name, env=None):
    with (work / 'logs' / (name + '.log')).open('w', encoding='utf-8') as log:
        result = subprocess.run([str(a) for a in args], cwd=work, env=env,
                                stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise BuildError(name + ' failed; inspect logs/' + name + '.log')


def preflight(config):
    profile = read_json(ROOT / 'profiles/android-launcher-20261102.json')
    checks = [('client19', profile['client19']['sha256']),
              ('reference_runtime', profile['runtime_sha256']),
              ('native', profile['native_sha256']),
              ('resource_ledger', config['resource_ledger_sha256'])]
    result = {}
    for key, expected in checks:
        actual = digest(config[key])
        if actual != expected:
            raise BuildError('Unsupported assembly input fingerprint: ' + key)
        result[key] = {'sha256': actual, 'bytes': config[key].stat().st_size}
    if not config['keystore'].is_file():
        raise BuildError('Signing keystore is missing')
    for name in ('BH3_KEYSTORE_PASSWORD', 'BH3_KEY_PASSWORD'):
        if not os.environ.get(name):
            raise BuildError('Set the signing password environment variable: ' + name)
    return result


def resource_packs(config, work):
    output = work / 'embedded'
    output.mkdir()
    entries = []
    with zipfile.ZipFile(output / 'client-resources.zip', 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as main, \
            zipfile.ZipFile(output / 'client-videos.zip', 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as videos:
        for item in read_json(config['resource_ledger']):
            remote = item['remote']
            if remote == 'installed ARM libil2cpp.so':
                continue
            if remote.startswith('/sdcard/bh3-server19-'):
                target = 'private/data/' + remote.removeprefix('/sdcard/')
            elif '/files/assets/Video/' in remote:
                target = 'external/assets/Video/' + remote.split('/files/assets/Video/', 1)[1]
            else:
                raise BuildError('Unknown reference resource destination: ' + remote)
            safe_relative(target)
            source = config['resource_root'] / str(safe_relative(item['local']))
            source = source.resolve()
            if not source.is_relative_to(config['resource_root']):
                raise BuildError('Resource input escaped its configured root')
            raw = source.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise BuildError('Reference resource changed: ' + item['local'])
            separate = target.startswith('external/')
            (videos if separate else main).writestr(target, raw)
            entries.append({'path': target, 'size': len(raw), 'sha256': item['sha256'],
                            'pack': 'video' if separate else 'main'})
    if len({e['path'] for e in entries}) != len(entries):
        raise BuildError('Duplicate resource destinations')
    write_json(output / 'client-resources.json', {'version': 'bh2017-locrenasci-reference-test-v1', 'entries': entries})
    return entries


def runtime_bundle(config, work):
    import server19_build_capabilities as capabilities
    output = work / 'runtime'
    output.mkdir()
    excluded = {'portable-manifest.json', 'server19_virtual_friend_profiles.json', 'account.json'}
    with zipfile.ZipFile(config['reference_runtime']) as package:
        for item in package.infolist():
            name = item.filename
            safe_relative(name)
            if item.is_dir() or name in excluded or name.endswith(('.py', '.pyc')) or '.bak-' in name:
                continue
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(package.read(item))
    manifest = read_json(ROOT / 'SOURCE-MANIFEST.json')
    names = {row['path'] for row in manifest['files'] if row['role'] == 'runtime'}
    names.update(('server19_portable.py', 'server19_build_capabilities.py'))
    # Local runtime imports, including modules newly added after the source snapshot.
    import ast
    pending = list(names)
    while pending:
        name = pending.pop()
        tree = ast.parse((ROOT / name).read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            modules = [a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import) else \
                [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else []
            for module in modules:
                relative = module + '.py'
                if (ROOT / relative).is_file() and relative not in names:
                    names.add(relative)
                    pending.append(relative)
    for name in names:
        shutil.copyfile(ROOT / name, output / name)
    records = {}
    native_caps = set()
    for scope, name in READY_RECORDS.items():
        path = output / name
        data = read_json(path)
        native_caps.update(data.get('required_native_capabilities', []))
        for key in ('device', 'serial', 'deployed', 'readback_verified', 'time', 'human_acceptance',
                    'native_library_delivery', 'backup', 'deployed_at', 'post_delivery_updates',
                    'deployment_receipt', 'voice_bank_path', 'files'):
            data.pop(key, None)
        data['build_proof'] = 'packaged-artifacts-v1'
        write_json(path, data)
        records[scope] = capabilities.canonical_sha(data)
    write_json(output / 'build-capabilities.json', {'schema': 1, 'evidence_kind': 'packaged-artifacts',
        'source_mode': 'reference-artifacts', 'human_gameplay_verified': False,
        'native_sha256': digest(config['native']),
        'resource_manifest_sha256': digest(work / 'embedded/client-resources.json'),
        'native_capabilities': sorted(native_caps), 'records': records})
    files = [{'path': p.relative_to(output).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(output.rglob('*')) if p.is_file()]
    write_json(output / 'portable-manifest.json', {'schema': 1, 'files': files, 'contains_save': False,
        'source_mode': 'reference-artifacts', 'business_modules': sorted(Path(n).stem for n in names)})
    archive = work / 'runtime.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                package.write(path, path.relative_to(output).as_posix())
    return len(files)


def compile_host(config, work):
    project = work / 'android-host'
    attempt = 1
    while project.exists():
        attempt += 1
        project = work / ('android-host-' + str(attempt))
    shutil.copytree(ROOT / 'android-server-probe', project)
    assets = project / 'app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work / 'runtime.zip', assets / 'runtime.zip')
    libraries = project / 'app/src/main/jniLibs/armeabi-v7a'
    libraries.mkdir(parents=True, exist_ok=True)
    run_command([config['zig'], 'cc', '-target', 'arm-linux-musleabi', '-shared', '-nostdlib',
        '-fPIC', '-Os', '-fomit-frame-pointer', '-fno-stack-protector', project / 'native/paths.c',
        '-o', libraries / 'libserver19paths.so'], work, 'native-path-bridge')
    tools = config['tools_root']
    jdks = list((tools / 'jdk').glob('*/bin/java.exe'))
    if len(jdks) != 1:
        raise BuildError('Expected one JDK under tools_root/jdk')
    env = os.environ.copy()
    env.update(JAVA_HOME=str(jdks[0].parents[1]), ANDROID_HOME=str(tools / 'sdk'),
        ANDROID_USER_HOME=str(tools / 'android-user'), GRADLE_USER_HOME=str(tools / 'gradle-user'),
        SERVER19_BUILD_PYTHON=str(tools / 'python311/tools/python.exe'), PYTHONDONTWRITEBYTECODE='1')
    if config.get('wheelhouse'):
        env['BH3_PYTHON_WHEELHOUSE'] = str(config['wheelhouse'])
        env['PIP_NO_INDEX'] = '1'
        env['PIP_FIND_LINKS'] = str(config['wheelhouse'])
    (project / 'local.properties').write_text('sdk.dir=' + str(tools / 'sdk').replace('\\', '/') + '\n', encoding='utf-8')
    gradle = tools / 'gradle/gradle-8.9/bin/gradle.bat'
    run_command([gradle, '-p', project, '--offline', '--no-daemon', '--console=plain', 'assembleDebug'], work, 'android-host', env)
    return project / 'app/build/outputs/apk/debug/app-debug.apk', jdks[0]


def announcement_prefab(config, work):
    # The stock picture container is adapted to the supplied 2172x547 banner.
    import UnityPy
    entry = 'assets/bin/Data/b753f392eb85c9b4e9a3255042f9064a'
    with zipfile.ZipFile(config['client19']) as package:
        raw = package.read(entry)
    if hashlib.sha256(raw).hexdigest() != '65dc6c7fff940b4bd9b7c9659dae1837b15d8692c7ce39bca8ae887f054d1ebb':
        raise BuildError('Unexpected original announcement prefab')
    env = UnityPy.load(raw)
    objects = {o.path_id: o for o in env.objects}
    height = 774.0 * 547 / 2172
    for identity, width, old, new in ((112, 774.0, 160.0, height), (118, 780.0, 166.0, height + 6)):
        tree = objects[identity].read_typetree()
        if tree['m_SizeDelta'] != {'x': width, 'y': old}:
            raise BuildError('Unexpected original picture container layout')
        tree['m_SizeDelta']['y'] = new
        objects[identity].save_typetree(tree)
    path = work / 'announcement.prefab'
    path.write_bytes(env.file.save())
    return path


def cached_resources(config, work):
    entries = read_json(work / 'embedded/client-resources.json')['entries']
    expected = {}
    for item in read_json(config['resource_ledger']):
        remote = item['remote']
        if remote == 'installed ARM libil2cpp.so':
            continue
        target = 'private/data/' + remote.removeprefix('/sdcard/') if remote.startswith('/sdcard/bh3-server19-') else \
            'external/assets/Video/' + remote.split('/files/assets/Video/', 1)[1]
        expected[target] = item['sha256']
    if {r['path']: r['sha256'] for r in entries} != expected:
        raise BuildError('Cached resource manifest differs from the pinned ledger')
    for name, kind in [('client-resources.zip', 'main'), ('client-videos.zip', 'video')]:
        wanted = {r['path']: r for r in entries if r['pack'] == kind}
        with zipfile.ZipFile(work / 'embedded' / name) as package:
            if len(package.namelist()) != len(wanted) or set(package.namelist()) != set(wanted):
                raise BuildError('Cached resource pack member mismatch')
            for path, row in wanted.items():
                with package.open(path) as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                if actual != row['sha256'] or package.getinfo(path).file_size != row['size']:
                    raise BuildError('Cached resource payload mismatch')
    return entries


def cached_runtime(config, work):
    runtime = work / 'runtime'
    manifest = read_json(runtime / 'portable-manifest.json')
    rows = {r['path']: r for r in manifest['files']}
    with zipfile.ZipFile(work / 'runtime.zip') as package:
        if len(package.namelist()) != len(rows) + 1 or set(package.namelist()) != set(rows) | {'portable-manifest.json'}:
            raise BuildError('Cached runtime member mismatch')
        for name, row in rows.items():
            if digest(runtime / name) != row['sha256'] or hashlib.sha256(package.read(name)).hexdigest() != row['sha256']:
                raise BuildError('Cached runtime payload mismatch')
            if name.endswith('.py') and digest(ROOT / name) != row['sha256']:
                raise BuildError('Runtime source changed; use a new assembly directory')
        if package.read('portable-manifest.json') != (runtime / 'portable-manifest.json').read_bytes():
            raise BuildError('Cached portable manifest mismatch')
    return len(rows)


def assemble(config, resume=False):
    inputs = preflight(config)
    work = config['work_dir']
    prior = None
    if resume:
        prior = read_json(work / 'assembly.json')
        if prior.get('status') != 'failed' or prior.get('inputs') != inputs:
            raise BuildError('Only a failed assembly with identical inputs can be resumed')
        index = len(list(work.glob('assembly-attempt-*.json'))) + 1
        shutil.copyfile(work / 'assembly.json', work / ('assembly-attempt-' + str(index) + '.json'))
    else:
        work.mkdir(parents=True, exist_ok=False)
        (work / 'logs').mkdir()
    receipt = {'schema': 1, 'mode': 'reference-artifacts', 'original_input_rebuild_verified': False,
               'started_utc': now(), 'status': 'running', 'inputs': inputs, 'stages': []}
    write_json(work / 'assembly.json', receipt)
    try:
        def stage(name, action):
            receipt['stages'].append({'name': name, 'status': 'running'})
            write_json(work / 'assembly.json', receipt)
            print('[' + name + '] running', flush=True)
            result = action()
            receipt['stages'][-1]['status'] = 'success'
            write_json(work / 'assembly.json', receipt)
            print('[' + name + '] PASS', flush=True)
            return result
        completed = {r['name'] for r in prior.get('stages', []) if r['status'] == 'success'} if prior else set()
        entries = stage('resource-packs', lambda: cached_resources(config, work) if 'resource-packs' in completed else resource_packs(config, work))
        count = stage('runtime-from-source', lambda: cached_runtime(config, work) if 'runtime-from-source' in completed else runtime_bundle(config, work))
        host, java = stage('compile-android-host', lambda: compile_host(config, work))
        prefab = stage('announcement-layout', lambda: announcement_prefab(config, work))
        from .apk_format import build
        from .supplements import load as load_supplements
        supplemental_root = load_supplements(config['supplements'], work / 'supplements')
        stage('compose-apk', lambda: build(config['client19'], host, config['native'],
            work / 'unsigned.apk', work / 'embedded', prefab, supplemental_root / 'images/launcher/app-icon.png'))
        tools = config['tools_root'] / 'sdk/build-tools/35.0.0'
        env = os.environ.copy()
        env['JAVA_HOME'] = str(java.parents[1])
        stage('zipalign', lambda: run_command([tools / 'zipalign.exe', '-f', '-p', '4',
            work / 'unsigned.apk', work / 'aligned.apk'], work, 'zipalign', env))
        stage('sign', lambda: run_command([tools / 'apksigner.bat', 'sign', '--ks', config['keystore'],
            '--ks-key-alias', config['key_alias'], '--ks-pass', 'env:BH3_KEYSTORE_PASSWORD',
            '--key-pass', 'env:BH3_KEY_PASSWORD', '--out', work / 'BH2017-LOCRENASCI-test.apk',
            work / 'aligned.apk'], work, 'sign', env))
        stage('verify-signature', lambda: run_command([tools / 'apksigner.bat', 'verify', '--verbose',
            '--print-certs', work / 'BH2017-LOCRENASCI-test.apk'], work, 'verify-signature', env))
        apk = work / 'BH2017-LOCRENASCI-test.apk'
        with zipfile.ZipFile(apk) as package:
            if package.testzip() is not None or digest(config['native']) != hashlib.sha256(package.read('lib/armeabi-v7a/libil2cpp.so')).hexdigest():
                raise BuildError('Final APK payload verification failed')
            if digest(work / 'runtime.zip') != hashlib.sha256(package.read('assets/runtime.zip')).hexdigest():
                raise BuildError('Runtime payload mismatch')
        receipt.update(status='success', finished_utc=now(), runtime_files=count,
            resource_files=len(entries), apk_sha256=digest(apk), apk_bytes=apk.stat().st_size,
            external_pack_sha256=digest(work / 'embedded/client-videos.zip'),
            device_operation='none', human_gameplay='pending')
        write_json(work / 'assembly.json', receipt)
        return receipt
    except Exception as error:
        receipt.update(status='failed', error=str(error), finished_utc=now())
        if receipt['stages']:
            receipt['stages'][-1]['status'] = 'failed'
        write_json(work / 'assembly.json', receipt)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Resume a failed assembly after rechecking cached artifacts')
    args = parser.parse_args(argv)
    try:
        result = assemble(load_config(args.config, args.resume), args.resume)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
