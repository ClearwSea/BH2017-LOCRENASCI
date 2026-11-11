"""Build from original client inputs, project rules and explicit extra materials."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from .core import ROOT, BuildError, build as build_data, read_json, write_json, now

PATHS = ('client19', 'client24', 'resources7x', 'supplements', 'tools_root', 'zig', 'keystore',
         'ffmpeg', 'voice_decoder', 'work_dir')


def load_config(path):
    value = read_json(path)
    allowed = set(PATHS) | {'schema', 'mode', 'key_alias', 'wheelhouse', 'extra_videos'}
    if value.get('schema') != 1 or value.get('mode') != 'original-inputs' or set(value) - allowed:
        raise BuildError('Use mode=original-inputs with explicit input and tool paths')
    result = dict(value)
    for key in PATHS + tuple(k for k in ('wheelhouse', 'extra_videos') if value.get(k)):
        if not value.get(key):
            raise BuildError('Missing input/tool path: ' + key)
        result[key] = Path(os.path.abspath(path.resolve().parent / value[key]))
    work = result['work_dir'].resolve()
    if work == ROOT or (work.is_relative_to(ROOT) and not work.is_relative_to(ROOT / 'work')):
        raise BuildError('Build output must be separate from the source tree')
    for key in PATHS:
        if key != 'work_dir' and result[key].resolve().is_relative_to(work):
            raise BuildError('Build output cannot contain an input: ' + key)
    for name in ('BH3_KEYSTORE_PASSWORD', 'BH3_KEY_PASSWORD'):
        if not os.environ.get(name):
            raise BuildError('Set signing environment variable ' + name)
    return result


def build(config, reuse_data=None, resume=False):
    from . import native, runtime_data, resources, audio, video, supplements
    from .assemble import compile_host, announcement_prefab, run_command
    from .apk_format import build as compose
    work = config['work_dir']
    if resume:
        receipt = read_json(work / 'original-build.json')
        if receipt['status'] not in ('failed', 'incomplete'):
            raise BuildError('Only incomplete builds can be resumed')
    else:
        work.mkdir(parents=True, exist_ok=False)
        (work / 'logs').mkdir()
        receipt = {'schema': 1, 'mode': 'original-inputs', 'started_utc': now(),
                   'status': 'running', 'stages': [], 'gameplay': 'pending',
                   'uses_reference_runtime_or_native': False}
    completed = {r['name'] for r in receipt['stages'] if r['status'] == 'success'}
    def stage(name, action):
        if name in completed:
            print('[' + name + '] reuse completed stage', flush=True)
            return None
        print('[' + name + '] running', flush=True)
        row = {'name': name, 'status': 'running'}
        receipt['stages'].append(row)
        result = action()
        row['status'] = 'success'
        if result is not None:
            row['result'] = result
        write_json(work / 'original-build.json', receipt)
        return result
    try:
        info = stage('supplements', lambda: {'root': str(supplements.load(
            config['supplements'], work / 'supplements'))})
        if info is None:
            info = next(r['result'] for r in receipt['stages'] if r['name'] == 'supplements' and r['status'] == 'success')
        supplemental_root = Path(info['root'])
        receipt['external_supplements'] = str(config['supplements'])
        data = Path(reuse_data).resolve() if reuse_data else work / 'data'
        if reuse_data:
            previous = read_json(data / 'build.json')
            if previous['status'] != 'success' or previous['target'] != 'tables':
                raise BuildError('Reuse requires a successful original-input tables build')
            inputs = read_json(data / 'inputs.json')
            from .core import digest
            if any(config[k].stat().st_size != inputs[k]['bytes'] or digest(config[k]) != inputs[k]['sha256'] for k in ('client19', 'client24')):
                raise BuildError('Cached data belongs to different inputs; use a fresh data build')
            receipt['data_cache'] = str(data)
        else:
            stage('tables-from-originals', lambda: build_data({'schema': 1, 'client19': config['client19'],
                'client24': config['client24'], 'work_dir': data, 'stage_ratios': 'baseline'}, 'tables'))
        os.environ['BH3_CLIENT19_ANALYSIS_DIR'] = str(data / 'extracted/client19')
        stage('native-from-original', lambda: native.apply(config['client19'], work / 'native/libil2cpp.so'))
        stage('runtime-data-from-originals', lambda: runtime_data.prepare(config['client24'], data,
            work / 'runtime', work / 'client-tables'))
        stage('client-resources-from-originals', lambda: resources.prepare(config['client19'], config['client24'],
            work / 'client-tables', work / 'resources', work / 'extracted-resource-base', supplemental_root / 'images'))
        stage('voices-from-7x', lambda: audio.prepare(config['client19'], config['resources7x'], config['voice_decoder'],
            work / 'resources/private/data/bh3-server19-audio', work / 'voice-scratch'))
        stage('videos-from-7x-and-explicit-extras', lambda: video.prepare(config['resources7x'],
            work / 'client-tables', config['ffmpeg'], work / 'resources/external/assets/Video',
            work / 'logs/video', config.get('extra_videos') or supplemental_root / 'videos'))
        stage('resource-packs', lambda: resources.pack(work / 'resources', work / 'embedded'))
        stage('runtime-capabilities', lambda: runtime_data.finish(work / 'runtime', work / 'native/libil2cpp.so',
            work / 'embedded/client-resources.json', work / 'runtime.zip'))
        stage('android-compile', lambda: str(compile_host(config, work)[0]))
        hosts = sorted(work.glob('android-host*/app/build/outputs/apk/debug/app-debug.apk'))
        host = hosts[-1]
        prefab = work / 'announcement.prefab'
        stage('announcement-layout', lambda: str(announcement_prefab(config, work)))
        from . import shop_art
        stage('shop-artwork', lambda: shop_art.prepare(config['client19'], config['client24'], work / 'unity-overrides', supplemental_root / 'images'))
        stage('apk-compose', lambda: compose(config['client19'], host, work / 'native/libil2cpp.so',
            work / 'unsigned.apk', work / 'embedded', prefab, supplemental_root / 'images/launcher/app-icon.png',
            unity_overrides=work / 'unity-overrides'))
        tools = config['tools_root'] / 'sdk/build-tools/35.0.0'
        java = next((config['tools_root'] / 'jdk').glob('*/bin/java.exe'))
        env = os.environ.copy()
        env['JAVA_HOME'] = str(java.parents[1])
        stage('align', lambda: run_command([tools / 'zipalign.exe', '-f', '-p', '4', work / 'unsigned.apk', work / 'aligned.apk'], work, 'zipalign', env))
        stage('sign', lambda: run_command([tools / 'apksigner.bat', 'sign', '--ks', config['keystore'], '--ks-key-alias', config['key_alias'],
            '--ks-pass', 'env:BH3_KEYSTORE_PASSWORD', '--key-pass', 'env:BH3_KEY_PASSWORD', '--out', work / 'candidate.apk', work / 'aligned.apk'], work, 'sign', env))
        stage('verify-signature', lambda: run_command([tools / 'apksigner.bat', 'verify', work / 'candidate.apk'], work, 'verify-signature', env))
        receipt.update(status='success', finished_utc=now(), apk='candidate.apk')
        write_json(work / 'original-build.json', receipt)
        return receipt
    except Exception as error:
        receipt.update(status='failed', error=str(error), finished_utc=now())
        if receipt['stages'] and receipt['stages'][-1]['status'] == 'running':
            receipt['stages'][-1]['status'] = 'failed'
        write_json(work / 'original-build.json', receipt)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--reuse-data', type=Path, help='Reuse an explicitly selected successful raw-input data stage')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        result = build(load_config(args.config), args.reuse_data, args.resume)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
