"""Build in a child process; passwords arrive on stdin, never in command lines."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from .core import write_json
from .desktop_runtime import check


def main():
    settings = json.load(sys.stdin)
    paths = check(settings)
    if '--probe' in sys.argv:
        import importlib.metadata, UnityPy, tkinter
        from .original import build
        print(json.dumps({'status': 'PASS', 'python': sys.version.split()[0],
                          'capstone': importlib.metadata.version('capstone'), 'UnityPy': UnityPy.__version__,
                          'tk': tkinter.TkVersion, 'checks': 'local paths and imports; no build performed'}))
        return 0
    base = Path(settings['base']).resolve()
    job = paths['output'] / datetime.now().strftime('%Y%m%d-%H%M%S')
    job.mkdir(parents=True, exist_ok=False)
    print('@@BUILDER ' + json.dumps({'job': str(job)}, ensure_ascii=False), flush=True)
    key = Path(settings['keystore']) if settings.get('keystore') else base / 'user-data/keys/local-build.jks'
    alias = settings.get('key_alias') or 'builder'
    store_password = settings.get('store_password') or 'android'
    key_password = settings.get('key_password') or store_password
    os.environ.update(BH3_KEYSTORE_PASSWORD=store_password, BH3_KEY_PASSWORD=key_password,
                      PIP_NO_INDEX='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                      ZIG_GLOBAL_CACHE_DIR=str(base / 'user-data/cache/zig'))
    if not key.exists():
        key.parent.mkdir(parents=True, exist_ok=True)
        keytool = next((paths['tools_root'] / 'jdk').glob('*/bin/keytool.exe'))
        subprocess.run([str(keytool), '-genkeypair', '-noprompt', '-storetype', 'JKS',
            '-keystore', str(key), '-alias', alias, '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '10000', '-dname', 'CN=Offline Local Build',
            '-storepass:env', 'BH3_KEYSTORE_PASSWORD', '-keypass:env', 'BH3_KEY_PASSWORD'],
            check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    config = {k: str(paths[k]) for k in ('client19', 'client24', 'resources7x', 'supplements',
              'tools_root', 'zig', 'ffmpeg', 'voice_decoder', 'wheelhouse')}
    config.update(schema=1, mode='original-inputs', work_dir=str(job / 'work'),
                  keystore=str(key), key_alias=alias)
    config_path = job / 'build-config.local.json'
    write_json(config_path, config)
    from .original import build, load_config
    build(load_config(config_path))
    apk = job / '崩坏3·2017 独立版.apk'
    videos = job / 'client-videos.zip'
    shutil.move(job / 'work/candidate.apk', apk)
    shutil.move(job / 'work/embedded/client-videos.zip', videos)
    receipt_path = job / 'work/original-build.json'
    receipt = json.loads(receipt_path.read_bytes())
    receipt.update(apk='../' + apk.name, external_pack='../' + videos.name)
    write_json(receipt_path, receipt)
    write_json(job / 'build-result.json', {'status': 'success', 'apk': apk.name,
        'external_pack': videos.name, 'mode': 'original-inputs', 'human_gameplay': 'pending',
        'uses_reference_runtime_or_patched_library_as_input': False})
    print('@@BUILDER ' + json.dumps({'success': True, 'job': str(job)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('构建失败：' + str(error), flush=True)
        traceback.print_exc()
        raise SystemExit(1)
