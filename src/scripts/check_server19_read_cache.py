"""Exact-content account cache checks / 账号解析复用检查。"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server19_stage as stage


def main():
    source = ROOT / 'server19-run/nx-backport-20261102/account.json'
    raw = source.read_bytes()
    account = json.loads(raw)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'account.json'
        path.write_bytes(raw)
        first = stage._read(path, account)
        second = stage._read(path, account)
        assert first == second == account
        first['main']['nickname'] = 'isolated'
        assert stage._read(path, account) == account
        # Make a guaranteed same-size content change, restoring timestamps.
        value = copy.deepcopy(account)
        old = value['main']['hcoin']
        value['main']['hcoin'] = old + (1 if old % 10 != 9 else -1)
        encoded = json.dumps(account, ensure_ascii=False).encode()
        path.write_bytes(encoded)
        stage._read(path, account)
        stamp = path.stat()
        replacement = json.dumps(value, ensure_ascii=False).encode()
        assert len(encoded) == len(replacement)
        path.write_bytes(replacement)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        assert stage._read(path, account) == value
        for invalid in ({**value, 'uid': account['uid'] + 1}, {**value, 'schema': 2}):
            path.write_text(json.dumps(invalid), encoding='utf8')
            for _ in range(2):
                try:
                    stage._read(path, account)
                except ValueError:
                    pass
                else:
                    raise AssertionError('identity accepted')
        path.write_bytes(b'broken')
        try:
            stage._read(path, account)
        except ValueError:
            pass
        else:
            raise AssertionError('corrupt file accepted')
        path.write_bytes(raw)
        assert stage._read(path, account) == account
        # Real successful save must become visible without a manual invalidation.
        before = stage._read(path, account)
        current = copy.deepcopy(before)
        current['main']['nickname'] = 'cache-save-check'
        with stage._transaction_lock(path):
            stage._save(path, before, current)
        assert stage._read(path, account) == current
        # A failed atomic install must leave both disk and subsequent reads old.
        before = stage._read(path, account)
        current = copy.deepcopy(before)
        current['main']['nickname'] = 'failed-save'
        replace = stage.os.replace
        stage.os.replace = lambda *args: (_ for _ in ()).throw(OSError('injected'))
        try:
            try:
                with stage._transaction_lock(path):
                    stage._save(path, before, current)
            except OSError:
                pass
            else:
                raise AssertionError('injected save succeeded')
        finally:
            stage.os.replace = replace
        assert stage._read(path, account) == before
    assert source.read_bytes() == raw
    print('PASS: independent trees, exact content updates, identity on cache hits, corruption recovery, successful/failed atomic save visibility; source unchanged')


if __name__ == '__main__':
    main()
