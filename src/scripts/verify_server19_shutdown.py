"""Bounded shutdown check on a copied account, never the phone or PC live save."""

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
import shutil
import socket
import sys
import threading
import urllib.request


def verify(runtime, account, output):
    output.mkdir(parents=True, exist_ok=False)
    copy = output / 'account.json'
    shutil.copy2(account, copy)
    sys.path.insert(0, str(runtime.resolve()))
    sys.path.insert(0, str(Path('android-server-probe/app/src/main/python').resolve()))
    import server19_portable as portable
    import server19_battle_session as sessions
    import server_entry as entry
    server, checked = portable.configure(output)
    before = copy.read_bytes()
    entry.SERVERS = portable.start(server)
    ports = [s.server_address[1] for s in entry.SERVERS]
    with urllib.request.urlopen(f'http://127.0.0.1:{ports[0]}/health') as response:
        assert response.status == 200
    done = threading.Event()
    failures = []
    def stop():
        try:
            entry.stop()
        except BaseException as error:
            failures.append(repr(error))
        finally:
            done.set()
    with sessions.LOCK:
        worker = threading.Thread(target=stop)
        worker.start()
        assert not done.wait(1.5), 'Shutdown failed to wait for the transaction lock'
    worker.join(5)
    assert done.is_set() and not failures, failures
    for port in ports:
        with socket.socket() as client:
            assert client.connect_ex(('127.0.0.1', port)) != 0
    assert copy.read_bytes() == before, 'Shutdown modified copied save'
    report = dict(status='PASS', verified_runtime_files=checked, ports_closed=True,
                  waited_for_transaction=True, copied_save_unchanged=True,
                  account_sha256=hashlib.sha256(before).hexdigest(), human_task_swipe='pending')
    (output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'account', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    verify(args.runtime, args.account, args.output)
