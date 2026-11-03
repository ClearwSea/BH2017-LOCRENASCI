"""手机正式运行入口；不执行测试或创建账户 / Imported-account Android host."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import traceback

SERVERS = None


def stop():
    """Drain the current transaction without changing gameplay or settling a battle."""
    global SERVERS
    if SERVERS is None:
        return
    import server19_portable as portable
    import server19_battle_session as sessions
    portable.stop(SERVERS)
    with sessions.LOCK:
        for session in sessions.OWNERS.values():
            session.retired = True
    SERVERS = None
    print('Integrated game task removed; server drained', flush=True)


def run(context):
    global SERVERS
    files = Path(str(context.getFilesDir().getAbsolutePath()))
    try:
        # Fail closed rather than silently booting a fresh or probe account.
        data = files / 'formal-data'
        account = data / 'account.json'
        receipt = json.loads((files / 'formal-import.json').read_bytes())
        raw = account.read_bytes()
        initial = json.loads(raw)
        if initial['uid'] != receipt['uid'] or initial['schema'] != 1:
            raise ValueError('Imported account identity/schema mismatch')
        from probe_entry import extract_runtime
        files, runtime, archive_sha = extract_runtime(context)
        os.environ['BH3_PACKAGED_NATIVE_LIBRARY'] = str(context.getApplicationInfo().nativeLibraryDir) + '/libil2cpp.so'
        log = (data / 'server-console.log').open('a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
        import server19_portable as portable
        server, verified = portable.configure(data)
        SERVERS = portable.start(server, 21018, 21019)
        report = dict(status='ready', mode='formal', pid=os.getpid(), uid=os.getuid(),
                      started=time.time(), ports=[21018,21019], verified_files=verified,
                      pointer_bits=struct.calcsize('P')*8, runtime_zip_sha256=archive_sha,
                      account_path=str(account), account_start_sha256=hashlib.sha256(raw).hexdigest())
        server.event('android_formal_ready', **report)
        (files / 'formal-ready.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return json.dumps(report)
    except BaseException:
        (files / 'formal-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
