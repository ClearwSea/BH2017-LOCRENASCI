"""Bind packaged capabilities to actual native/data artifacts, not device receipts."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_verified_native = None


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def manifest():
    value = json.loads((ROOT / 'build-capabilities.json').read_bytes())
    if value.get('schema') != 1 or value.get('evidence_kind') != 'packaged-artifacts':
        raise ValueError('Invalid packaged build capabilities')
    return value


def verify_native():
    global _verified_native
    value = manifest()
    name = os.environ.get('BH3_PACKAGED_NATIVE_LIBRARY')
    if not name:
        raise ValueError('The installed game native library must be explicitly bound')
    path = Path(name)
    info = path.stat()
    key = (str(path.resolve()), info.st_ino, info.st_size, info.st_mtime_ns, value['native_sha256'])
    if _verified_native == key:
        return value['native_sha256']
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != value['native_sha256']:
        raise ValueError('Installed native library does not match this runtime')
    _verified_native = key
    return actual


def require(scope, ready):
    value = manifest()
    if ready.get('build_proof') != 'packaged-artifacts-v1' or value['records'].get(scope) != canonical_sha(ready):
        raise ValueError('Packaged capability record does not match: ' + scope)
    required = set(ready.get('required_native_capabilities', []))
    if ready.get('native_shield_cap_bridge_required'):
        required.add('shield_cap_v1')
    if required - set(value['native_capabilities']):
        raise ValueError('Required native capabilities are absent')
    verify_native()
