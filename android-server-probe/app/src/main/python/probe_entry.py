"""Extract the save-free runtime into this probe's private sandbox."""
import hashlib
import json
from pathlib import Path
import sys
import traceback
import zipfile
import faulthandler


def extract_runtime(context):
    files = Path(str(context.getFilesDir().getAbsolutePath()))
    runtime = files / 'runtime'
    # Android AssetManager stream avoids all shared /sdcard paths.
    from java import jarray, jbyte
    stream = context.getAssets().open('runtime.zip')
    archive = files / 'runtime.zip'
    buffer = jarray(jbyte)(65536)
    with archive.open('wb') as out:
        while True:
            count = stream.read(buffer)
            if count < 0:
                break
            out.write(bytes(buffer)[:count])
    stream.close()
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            (runtime / name).resolve().relative_to(runtime.resolve())
        z.extractall(runtime)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime))
    return files, runtime, archive_sha


def run(context):
    files = Path(str(context.getFilesDir().getAbsolutePath()))
    try:
        files, runtime, archive_sha = extract_runtime(context)
        data = files / 'probe-data'
        trace = (files / 'probe-stacks.txt').open('w')
        faulthandler.dump_traceback_later(30, repeat=True, file=trace)
        import server19_portable_smoke
        report = server19_portable_smoke.run(data, 21118, 21119, keep_alive=True)
        # Isolated mathematical simulation: never advance a gameplay account.
        import audit_endless_numpy_portability as audit
        audit.ROOT = runtime
        inputs = files / 'parity-inputs.json'
        inputs.write_text(json.dumps({'scenarios': [dict(name='seed'+str(seed), begin=1792958400, seed=seed)
                                                   for seed in (1731, 42, 2026)]}), encoding='utf-8')
        parity_output = files / ('parity-' + str(__import__('os').getpid()))
        old_argv = sys.argv
        try:
            sys.argv = ['audit', '--inputs', str(inputs), '--output', str(parity_output), '--periods', '104']
            audit.main()
        finally:
            sys.argv = old_argv
        report['parity_output'] = str(parity_output)
        faulthandler.cancel_dump_traceback_later()
        trace.close()
        report['runtime_zip_sha256'] = archive_sha
        report['process_cmdline'] = Path('/proc/self/cmdline').read_bytes().replace(b'\0', b' ').decode().strip()
        report['uid'] = __import__('os').getuid()
        report['sandbox'] = str(files)
        (files / 'probe-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return json.dumps({'status': report['status'], 'pointer_bits': report['pointer_bits'], 'pid': report['pid']})
    except BaseException:
        (files / 'probe-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
