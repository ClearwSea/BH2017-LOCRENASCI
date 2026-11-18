"""Atomic, identity-preserving save editor transactions."""
from pathlib import Path
import hashlib
import json
import os
import tempfile

def _lock(path):
    import server19_stage as stage
    return stage._transaction_lock(path)


def _account(raw, receipt):
    value = json.loads(raw)
    identity = json.loads(receipt)
    if not isinstance(value, dict) or value.get('schema') != 1 or \
            type(value.get('uid')) is not int or value['uid'] != identity.get('uid'):
        raise ValueError('存档身份或格式与导入记录不符')
    return value


def read(path, receipt_path):
    path, receipt_path = Path(path), Path(receipt_path)
    with _lock(path):
        raw, receipt = path.read_bytes(), receipt_path.read_bytes()
        value = _account(raw, receipt)
        return value, hashlib.sha256(raw).hexdigest()


def save(path, receipt_path, backup_dir, expected_hash, value):
    """Keep a verified copy, then replace only if the original is unchanged."""
    path, receipt_path = Path(path), Path(receipt_path)
    backup_dir = Path(backup_dir) if backup_dir else None
    with _lock(path):
        old, receipt = path.read_bytes(), receipt_path.read_bytes()
        previous = _account(old, receipt)
        if hashlib.sha256(old).hexdigest() != expected_hash:
            raise ValueError('存档在编辑期间发生变化，请重新读取')
        if value.get('schema') != 1 or value.get('uid') != previous['uid']:
            raise ValueError('不能更改存档身份或格式')
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        _account(raw, receipt)
        if backup_dir is not None:
            # Never expose a half-written account as a selectable history item.
            # Staging is a sibling of auto, on the same filesystem for rename.
            staging_parent = backup_dir.parent.parent if backup_dir.parent.name == 'auto' else backup_dir.parent
            staging_root = staging_parent / '.editor-backup-staging'
            staging_root.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix='backup-', dir=staging_root))
            for name, content in (('account.json', old), ('formal-import.json', receipt),
                                  ('metadata.json', b'{"source":"editor"}')):
                destination = staging / name
                with destination.open('xb') as out:
                    out.write(content)
                    out.flush()
                    os.fsync(out.fileno())
                if destination.read_bytes() != content:
                    raise OSError('备份校验失败，未保存')
            if backup_dir.exists():
                raise OSError('自动备份目标已存在，未保存')
            os.rename(staging, backup_dir)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.editor-', delete=False) as out:
                temporary = Path(out.name)
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return hashlib.sha256(raw).hexdigest()
