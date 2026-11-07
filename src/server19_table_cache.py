"""Verified portable table indexes / 已校验运行表索引，返回独立对象。"""
from pathlib import Path
import hashlib
import json
import threading
from server19_fastcopy import deepcopy


def install_table_cache(stage, root, *, startup=False):
    # portable.configure has already completed its original full manifest check.
    manifest = json.loads((root / 'portable-manifest.json').read_bytes())
    expected = {str((root / row['path']).resolve()): row['sha256'] for row in manifest['files']}
    cache = {}
    stats = {'calls': 0, 'table_loads': 0, 'index_builds': 0}
    lock = threading.RLock()
    paths = {}
    stats['path_resolves'] = 0

    def finish_startup(validate=True):
        nonlocal startup
        with lock:
            try:
                if validate:
                    for source, resolved in paths.items():
                        stats['path_resolves'] += 1
                        if Path(source).resolve() != resolved:
                            raise ValueError('Runtime table path changed during startup: ' + source)
            finally:
                startup = False
                paths.clear()

    def table(name, *, field=None, identities=None):
        source = Path(stage.TABLE_OVERRIDES.get(name, stage.TABLE_DIRECTORY / name))
        with lock:
            key = str(source)
            if startup and key in paths:
                path = paths[key]
            else:
                path = source.resolve()
                stats['path_resolves'] += 1
                if startup:
                    paths[key] = path
            identity = str(path)
            if identity not in expected:
                raise ValueError('Table is not in the verified runtime: ' + name)
            stats['calls'] += 1
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
            if identity not in cache or cache[identity][0] != signature:
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != expected[identity]:
                    raise ValueError('Immutable runtime table changed: ' + name)
                rows = json.loads(raw)
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise ValueError('Malformed original-compatible table: ' + name)
                cache[identity] = signature, rows, {}
                stats['table_loads'] += 1
            _, rows, indexes = cache[identity]
            if field is None:
                if identities is not None:
                    raise ValueError('Table row selection requires a field')
                selected = rows
            else:
                if identities is None:
                    raise ValueError('Table row selection requires identities')
                allowed = frozenset(identities)
                if field not in indexes:
                    index = {}
                    for position, row in enumerate(rows):
                        index.setdefault(row.get(field), []).append(position)
                    indexes[field] = index
                    stats['index_builds'] += 1
                index = indexes[field]
                # Original scan order and duplicate rows must be retained.
                positions = sorted(position for value in allowed for position in index.get(value, ()))
                selected = [rows[position] for position in positions]
            # Existing tested C-backed copier, not shared mutable cached rows.
            return deepcopy(selected)

    stage._finish_startup_tables = finish_startup
    stage._table = table
    return stats
