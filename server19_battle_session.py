"""Offline session boundaries: abandon unfinished battles, never erase progress."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import secrets
import threading
import time

import server19_stage as stage

RUNTIMES = ('stage_runtime', 'openworld_runtime', 'endless_runtime')
LOCK = threading.RLock()
OWNERS = {}


def recover(account, path, reason):
    path = Path(path).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        cleared = {}
        for name in RUNTIMES:
            runtime = current.get(name)
            if isinstance(runtime, dict) and runtime.get('active') is not None:
                cleared[name] = deepcopy(runtime['active'])
                runtime['active'] = None
        backup = None
        if cleared:
            backup = path.with_name(f'{path.stem}-interrupted-{time.time_ns()}-{secrets.token_hex(3)}.json')
            with backup.open('xb') as out:
                out.write(path.read_bytes())
            # Existing atomic account transaction; no refunds or reward grants.
            stage._save(path, before, current)
        stage._sync(account, current)
        return dict(reason=reason, cleared=cleared, backup=str(backup) if backup else None)


class Session:
    def __init__(self):
        self.retired = False
        self.logged_in = False

    @contextmanager
    def frame(self, name, account, path, event):
        # A replacement login cannot interleave with an older request/settlement.
        with LOCK:
            key = str(Path(path).resolve())
            if self.retired:
                raise ConnectionAbortedError('Superseded offline login session')
            if name == 'PlayerLoginReq' and not self.logged_in:
                report = recover(account, path, 'client_login')
                previous = OWNERS.get(key)
                if previous is not None:
                    previous.retired = True
                OWNERS[key] = self
                self.logged_in = True
                event('battle_session_recovery', **report)
            elif name != 'GetPlayerTokenReq' and not self.logged_in:
                raise ConnectionAbortedError('Login required before account requests')
            yield
