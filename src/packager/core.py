"""Explicit-input data preparation for the supported BH2017-LOCRENASCI build profile."""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import zipfile

from . import __version__

ROOT = Path(__file__).resolve().parents[1]
STAGES = ('inputs', 'extract', 'protocol', 'base_tables', 'material_navigation', 'validate')
CONFIG_KEYS = {'schema', 'client19', 'client24', 'work_dir', 'stage_ratios'}
TRACKED = ('extracted', 'generated', 'inputs.json', 'source-inputs.json')


class BuildError(ValueError):
    pass


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def load_config(path):
    value = read_json(path)
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise BuildError('Configuration schema must be 1')
    unknown = set(value) - CONFIG_KEYS
    if unknown:
        raise BuildError('Unknown configuration keys: ' + ', '.join(sorted(unknown)))
    result = {'schema': 1, 'stage_ratios': value.get('stage_ratios', 'baseline')}
    if result['stage_ratios'] not in ('baseline', 'repaired'):
        raise BuildError('stage_ratios must be baseline or repaired')
    for key in ('client19', 'client24', 'work_dir'):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise BuildError('Missing path: ' + key)
        result[key] = (path.resolve().parent / value[key]).resolve()
    work = result['work_dir']
    # Only work/ is a writable workspace inside the public source directory.
    if work == ROOT or (work.is_relative_to(ROOT) and not work.is_relative_to(ROOT / 'work')):
        raise BuildError('Output inside the source tree must be under work/')
    for key in ('client19', 'client24'):
        item = result[key]
        if work == item or item.is_relative_to(work) or work.is_relative_to(item.parent):
            raise BuildError('Output must be separate from input paths: ' + key)
    if result['client19'] == result['client24']:
        raise BuildError('The two client inputs must be different files')
    return result


def inspect_inputs(config):
    profile = read_json(ROOT / 'profiles/android-launcher-20261102.json')
    result = {}
    for key in ('client19', 'client24'):
        path = config[key]
        expected = profile[key]
        if not path.is_file():
            raise BuildError('Missing input: ' + str(path))
        actual = digest(path)
        matches = actual == expected['sha256'] and path.stat().st_size == expected['bytes']
        result[key] = {'bytes': path.stat().st_size, 'sha256': actual, 'reference_match': matches}
        if not matches:
            print('[inputs] ' + key + ': differs from the reference file; continuing with selected input', flush=True)
    return result


def source_inputs():
    # Pin actual implementation and rules; do not trust a stale source manifest.
    names = ['analyze19.py', 'server19_extract_protocol.py', 'server19_metadata_export.py',
             'server19_resources.py', 'server19_stage_reward_compat.py',
             'tools/extract_client19.py', 'tools/material_navigation.py',
             'rules/material-navigation.json', 'profiles/table-recipes.json',
             'rules/table-adaptations.json', 'rules/daily-missions.json',
             'profiles/android-launcher-20261102.json']
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'packager').glob('*.py'))]
    return [{'path': name, 'sha256': digest(ROOT / name)} for name in names]


def check_dependency():
    try:
        version = importlib.metadata.version('capstone')
    except importlib.metadata.PackageNotFoundError as error:
        raise BuildError('Install requirements-build.txt in the build environment') from error
    if version != '5.0.9':
        raise BuildError('This input profile requires Capstone 5.0.9; found ' + version)
    return version


def extract_inputs(config, work):
    from tools.extract_client19 import FILES
    output = work / 'extracted/client19'
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(config['client19']) as package:
        for entry, (name, expected) in FILES.items():
            if len([info for info in package.infolist() if info.filename == entry]) != 1:
                raise BuildError('Missing or duplicate APK member: ' + entry)
            raw = package.read(entry)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise BuildError('Unexpected native analysis input: ' + entry)
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)


def worker(stage, config, work):
    output = work / ('generated/protocol/server19_protocol_schema.json' if stage == 'protocol' else 'generated/base-tables')
    args = [sys.executable, '-B', '-m', 'packager.worker', stage,
            '--analysis-dir', str(work / 'extracted/client19'), '--output', str(output)]
    if stage == 'base_tables':
        args += ['--apk24', str(config['client24']), '--stage-ratios', config['stage_ratios']]
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env.pop('BH3_ENABLE_REFERENCE_RECIPES', None)
    logs = work / 'logs'
    logs.mkdir(exist_ok=True)
    with (logs / (stage + '.log')).open('w', encoding='utf-8') as stream:
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise BuildError(stage + ' failed; see logs/' + stage + '.log')


def safe_relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise BuildError('Unsafe artifact path: ' + name)
    return path


def validate_base(work):
    base = work / 'generated/base-tables'
    manifest = read_json(base / 'manifest.json')
    expected = {row['name'] for row in read_json(ROOT / 'profiles/table-recipes.json')['tables']}
    rows = manifest['files']
    names = [PurePosixPath(row['output_file']).name for row in rows if row.get('output_file')]
    if len(rows) != 251 or len(names) != 251 or set(names) != expected:
        raise BuildError('Base export does not contain all 251 configured tables')
    deployment = manifest['deployment_files']
    declared = []
    for row in rows:
        name = row['output_file']
        safe_relative(name)
        path = base / name
        if path.is_symlink() or digest(path) != row['output_sha256']:
            raise BuildError('Base table hash mismatch: ' + name)
        data = read_json(path)
        if not isinstance(data, list) or len(data) != row['output_rows']:
            raise BuildError('Base table row-count mismatch: ' + name)
        declared.append(name)
        if row.get('char_file'):
            char = row['char_file']
            safe_relative(char['output_file'])
            if digest(base / char['output_file']) != char['sha256']:
                raise BuildError('Character sidecar mismatch')
            declared.append(char['output_file'])
    if len(deployment) != len(set(deployment)) or set(deployment) != set(declared):
        raise BuildError('Deployment file list does not match table outputs')
    return manifest


def apply_navigation(work):
    from tools.material_navigation import apply
    manifest = validate_base(work)
    base = work / 'generated/base-tables'
    target = work / 'generated/tables'
    target.mkdir(exist_ok=False)
    for name in manifest['deployment_files']:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, path)
    name = '_exceloutputasset/materialdata'
    policy = read_json(ROOT / 'rules/material-navigation.json')
    rows = apply(read_json(base / name), policy)
    (target / name).write_bytes((json.dumps(rows, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8'))


def validate_stage_policy(rows, policy):
    by_id = {row['levelId']: row for row in rows}
    if len(by_id) != len(rows) or 900302 not in by_id:
        raise BuildError('Stage table is missing its native initialization dependency or has duplicate IDs')
    for identity in (10432, 10433, 10434, 20432, 20433, 20434):
        row = by_id.get(identity)
        ordinal = identity % 100 - 31
        expected = (0.0, 0.7) if policy == 'repaired' else (float(ordinal), ordinal + 0.7)
        if row is None or any(not isinstance(row.get(key), (int, float)) or
                not math.isclose(row[key], value, rel_tol=0, abs_tol=1e-6)
                for key, value in zip(('avatarExpInside', 'scoinInside'), expected)):
            raise BuildError('Stage ratio policy mismatch: ' + str(identity))


def validate_outputs(config, work):
    from tools.material_navigation import apply
    manifest = validate_base(work)
    if manifest.get('stage_ratio_policy') != config['stage_ratios']:
        raise BuildError('Exported stage ratio policy differs from the requested policy')
    protocol = read_json(work / 'generated/protocol/server19_protocol_schema.json')
    if len(protocol['commands']) != 706 or len(protocol['schemas']) != 2055:
        raise BuildError('Protocol extraction count differs from the supported profile')
    base = work / 'generated/base-tables'
    final = work / 'generated/tables'
    validate_stage_policy(read_json(base / '_exceloutputasset/stagedata_main'), config['stage_ratios'])
    for name in manifest['deployment_files']:
        if name != '_exceloutputasset/materialdata' and digest(base / name) != digest(final / name):
            raise BuildError('Unexpected table edit: ' + name)
    material = '_exceloutputasset/materialdata'
    expected = apply(read_json(base / material), read_json(ROOT / 'rules/material-navigation.json'))
    if read_json(final / material) != expected:
        raise BuildError('Material navigation result differs from the configured rule')
    return {'base_tables': 251, 'commands': 706, 'schemas': 2055, 'material_rows': len(expected),
            'stage_ratios': config['stage_ratios'], 'scope': 'base-tables-and-material-navigation',
            'complete_game_data': False, 'apk_built': False}


def artifact_inventory(work):
    result = []
    for name in TRACKED:
        path = work / name
        paths = sorted(path.rglob('*')) if path.is_dir() else [path]
        for item in paths:
            if item.is_symlink():
                raise BuildError('Symlink in generated artifacts')
            if item.is_file():
                result.append({'path': item.relative_to(work).as_posix(), 'bytes': item.stat().st_size,
                               'sha256': digest(item)})
    return sorted(result, key=lambda row: row['path'])


def verify(work):
    work = work.resolve()
    receipt = read_json(work / 'build.json')
    if receipt.get('schema') != 1 or receipt.get('status') != 'success' or receipt.get('target') not in ('data', 'tables'):
        raise BuildError('No successful data build receipt in this directory')
    artifacts = receipt.get('artifacts', [])
    if not artifacts or len({row['path'] for row in artifacts}) != len(artifacts):
        raise BuildError('Missing or repeated artifact records')
    for row in artifacts:
        safe_relative(row['path'])
        if not (work / row['path']).resolve().is_relative_to(work):
            raise BuildError('Artifact escaped its build directory')
    actual = artifact_inventory(work)
    if actual != artifacts:
        raise BuildError('Artifact verification failed: files were changed, removed or added')
    return {'status': 'PASS', 'target': receipt['target'], 'artifacts': len(artifacts), 'apk_built': False}


def build(config, target):
    if target not in ('data', 'tables'):
        raise BuildError('APK orchestration is not implemented in version ' + __version__ + '; use --target data')
    work = config['work_dir']
    if work.exists():
        raise BuildError('Output directory already exists; choose a new work_dir')
    inputs = inspect_inputs(config)
    dependency = check_dependency()
    sources = source_inputs()
    work.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 1, 'packager_version': __version__, 'target': target,
               'profile': 'android-launcher2-20261102', 'stage_ratios': config['stage_ratios'],
               'started_utc': now(), 'status': 'running', 'stages': [], 'capstone': dependency}
    write_json(work / 'build.json', receipt)
    try:
        stages = list(STAGES) + (['effective_tables'] if target == 'tables' else [])
        for stage in stages:
            row = {'name': stage, 'status': 'running', 'started_utc': now()}
            receipt['stages'].append(row)
            print('[' + stage + '] running', flush=True)
            if stage == 'inputs':
                write_json(work / 'inputs.json', inputs)
                write_json(work / 'source-inputs.json', sources)
            elif stage == 'extract':
                extract_inputs(config, work)
            elif stage in ('protocol', 'base_tables'):
                worker(stage, config, work)
            elif stage == 'material_navigation':
                apply_navigation(work)
            elif stage == 'effective_tables':
                args = [sys.executable, '-B', '-m', 'packager.worker', 'effective_tables',
                    '--analysis-dir', str(work / 'extracted/client19'),
                    '--output', str(work / 'generated/effective-tables'),
                    '--apk24', str(config['client24']), '--data-work', str(work)]
                env = os.environ.copy()
                env['PYTHONDONTWRITEBYTECODE'] = '1'
                with (work / 'logs/effective_tables.log').open('w', encoding='utf-8') as log:
                    result = subprocess.run(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode:
                    raise BuildError('effective_tables failed; see logs/effective_tables.log')
                receipt['summary'].update(effective_server_tables=251, material_rows=742,
                    scope='effective-server-tables', complete_game_data=False)
            else:
                receipt['summary'] = validate_outputs(config, work)
            row.update(status='success', finished_utc=now())
            print('[' + stage + '] PASS', flush=True)
        receipt.update(status='success', finished_utc=now(), artifacts=artifact_inventory(work))
        write_json(work / 'build.json', receipt)
    except Exception as error:
        row.update(status='failed', finished_utc=now())
        receipt.update(status='failed', finished_utc=now(), error=str(error))
        write_json(work / 'build.json', receipt)
        raise
    return {'status': 'PASS', 'target': target, 'summary': receipt['summary'], 'apk_built': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'inspect', 'build'):
        command = commands.add_parser(name)
        command.add_argument('--config', type=Path, required=True)
        if name != 'inspect':
            command.add_argument('--target', choices=('data', 'tables', 'apk'), required=True)
    command = commands.add_parser('verify')
    command.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build' and args.target == 'apk':
            from .original import build as build_apk, load_config as load_apk_config
            result = build_apk(load_apk_config(args.config))
        elif args.command == 'plan' and args.target == 'apk':
            config = read_json(args.config)
            if config.get('mode') != 'original-inputs':
                raise BuildError('APK builds use packager-original.example.json')
            result = {'version': __version__, 'target': 'apk', 'implemented': True,
                      'mode': 'original-inputs', 'stages': ['tables', 'native', 'runtime-data',
                      'client-resources', '7x-audio-video', 'resource-packs',
                      'android-compile', 'apk-compose', 'align', 'sign']}
        elif args.command == 'verify':
            result = verify(args.work_dir)
        else:
            config = load_config(args.config)
            if args.command == 'plan':
                result = {'version': __version__, 'target': args.target,
                          'implemented': args.target in ('data', 'tables'), 'stage_ratios': config['stage_ratios'],
                          'stages': list(STAGES), 'work_dir': str(config['work_dir'])}
                if args.target == 'apk':
                    result['pending_stages'] = ['remaining_data_rules', 'native_patch_chain',
                        'resource_conversion', 'android_compile', 'apk_assembly_and_signing']
            elif args.command == 'inspect':
                result = {'status': 'PASS', 'inputs': inspect_inputs(config)}
            else:
                result = build(config, args.target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BuildError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
