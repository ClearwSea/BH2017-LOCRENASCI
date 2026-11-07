"""Optional reference comparisons; results never authorize or block a build."""
import hashlib
import os
from pathlib import Path
from .core import ROOT, read_json

SCOPES = (('Audio/GeneratedSoundBanks/Windows', '*.pck'), ('Video', '*.usm'))


class ComparisonCancelled(Exception):
    pass


def references():
    return read_json(ROOT / 'profiles/input-references.json')


def hash_file(path, cancel, progress=lambda done, total: None):
    path = Path(path)
    before = path.stat()
    digest = hashlib.sha256()
    done = 0
    with path.open('rb') as stream:
        while True:
            if cancel.is_set():
                raise ComparisonCancelled()
            block = stream.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            done += len(block)
            progress(done, before.st_size)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('核对期间文件发生变化，请重新计算')
    return digest.hexdigest()


def compare_file(path, reference, cancel, progress=lambda done, total: None):
    actual = hash_file(path, cancel, progress)
    return {'actual_sha256': actual, 'reference_sha256': reference['sha256'],
            'matches_reference': actual == reference['sha256']}


def quick_directory(path, reference, cancel, progress=lambda done, total: None):
    root = Path(path)
    if not root.is_dir():
        raise ValueError('请选择有效的7.x资源目录')
    actual = {}
    for folder, pattern in SCOPES:
        directory = root / folder
        if not directory.is_dir():
            continue
        with os.scandir(directory) as entries:
            for entry in entries:
                if cancel.is_set():
                    raise ComparisonCancelled()
                if not entry.name.lower().endswith(pattern[1:]) or not entry.is_file(follow_symlinks=False):
                    continue
                name = folder + '/' + entry.name
                actual[name.casefold()] = (name, entry.stat(follow_symlinks=False).st_size)
                progress(len(actual), max(len(reference['files']), len(actual)))
    expected = {row['path'].casefold(): row for row in reference['files']}
    missing = [row['path'] for name, row in expected.items() if name not in actual]
    changed = [{'path': row['path'], 'reference_bytes': row['bytes'], 'actual_bytes': actual[name][1]}
               for name, row in expected.items() if name in actual and actual[name][1] != row['bytes']]
    additional = [name for key, (name, _) in actual.items() if key not in expected]
    return {'matches_reference': not (missing or changed or additional),
            'missing': sorted(missing), 'different_size': changed, 'additional': sorted(additional),
            'actual_file_count': len(actual), 'content_hashes_computed': False}
