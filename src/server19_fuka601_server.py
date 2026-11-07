"""Explicit per-instance601 metadata/cultivation activation, no save mutation."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import hashlib
import json
import server19_stage as stage
import server19_avatar_skills as skills
import server19_avatar_cultivation as cultivation
import server19_avatar_fragments as fragments
import server19_equipment as equipment

ROOT = Path(__file__).resolve().parent
DEFAULT_READY = ROOT / '.local-baseline/server19-dev/fuka601-recovery-20261015/ready-v5'
EXPECTED_KEYS = {
    'avatardata': ('avatarID', {601}),
    'avatarskilldata': ('skillId', set(range(281, 287))),
    'avatarsubskilldata': ('avatarSubSkillId', set(range(2801, 2816))),
    'avatarstardata': ('avatarID', {601}),
    'weapondata': ('ID', {20611, 20612, 20613}),
    'avatarfragmentdata': ('ID', {10601}),
    'classdata': ('classID', {6}),
    'avatarcarddata': ('ID', {60601}),
}


def configure(ready=DEFAULT_READY, *, require_deployed=True):
    ready = Path(ready).resolve()
    if not ready.is_relative_to(ROOT):
        raise ValueError('Use a reviewed workspace601 overlay')
    manifest = json.loads((ready / 'manifest.json').read_bytes())
    if manifest.get('schema') != 1 or manifest.get('avatar_id') != 601 or manifest.get('ability_roots') != 29:
        raise ValueError('Unexpected601 overlay')
    if require_deployed:
        deployed = json.loads((ready / 'deployment.json').read_bytes())
        if deployed.get('serial') != 'REFERENCE_DEVICE' or deployed.get('files_updated') is not True:
            raise ValueError('Sony601 candidate has not been deployed')
    for name, entry in manifest['tables'].items():
        path = ready / entry['file']; raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Reviewed table changed: ' + name)
        source = Path(entry['base_path']).read_bytes()
        if hashlib.sha256(source).hexdigest() != entry['base_sha256']:
            raise ValueError('Original source table changed: ' + name)
        rows, before = json.loads(raw), json.loads(source)
        if 'char_sidecar' in entry:
            side = entry['char_sidecar']; chars = (ready / side['file']).read_bytes()
            if len(chars) != len(rows) * 6 or hashlib.sha256(chars).hexdigest() != side['sha256']:
                raise ValueError('Character sidecar is inconsistent: ' + name)
            if any(field in row for row in rows for field in side['fields']):
                raise ValueError('Native Char fields must not pass through JSON strings')
        if rows[:len(before)] != before:
            raise ValueError('Existing rows were altered: ' + name)
        added = rows[len(before):]
        if name in EXPECTED_KEYS:
            field, expected = EXPECTED_KEYS[name]
            if any(row[field] not in expected for row in added):
                raise ValueError('Unrelated new metadata: ' + name)
        elif name != 'textmap':
            raise ValueError('Unreviewed metadata category')
        stage.TABLE_OVERRIDES[name] = path
    # Transactions bind to these reviewed actual per-instance tables. Other
    # instances retain their existing hash policy and metadata configuration.
    for module, attribute in ((skills, '_TABLE_HASHES'), (cultivation, '_TABLE_HASHES'),
                              (equipment, '_POWER_UP_TABLE_HASHES')):
        hashes = getattr(module, attribute)
        for name in hashes:
            path = Path(stage.TABLE_OVERRIDES.get(name, stage.TABLE_DIRECTORY / name))
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    skills.SUPPORTED_AVATARS[601] = tuple(range(281, 287))
    cultivation.FUKA_FRAGMENT_UNLOCK_ENABLED = True
    fragments.AUDITED_IDS[10601] = 601
    equipment.EXTRA_AUDITED_GROWTH_IDS = frozenset((20611, 20612, 20613))
    return {'avatar_id': 601, 'tables': list(manifest['tables']), 'save_mutated': False}
