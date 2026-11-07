"""Merge audited overlays into one candidate; no game or save operations."""

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
import shutil
import server19_avatar_battle_resources as batch
import server19_stage_monsters as baked
import server19_decode_trace as trace

ROOT = Path(__file__).resolve().parent
STORY = ROOT / '.local-baseline/server19-dev/story-chain-batch-ready/v4'
EQUIPMENT = ROOT / '.local-baseline/server19-dev/equipment-chain-batch-ready-v3'
OUT = ROOT / '.local-baseline/server19-dev/story-chain-unified-ready-v2'
BASE_ABILITY = ROOT / '.local-baseline/server19-dev/mixed-team-equipment-ready/bakedabilitydata'
BASE_WEAPON = ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/_baked/bakedweapondata'
BASE_AVATAR = ROOT / '.local-baseline/server19-dev/baked-fallback/_baked/bakedavatardata'
STRINGMAP = ROOT / '.local-baseline/server19-dev/act101-native-prop-resources/_baked/stringmap.txt'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def checked(path, expected):
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError('Candidate source changed: ' + str(path))
    return raw

def merge(raw, overlays):
    h, entries, variants, data, refs, spans = batch.packed(raw)
    selected = {}
    for row, value in overlays:
        identity = (row['key'], row['variant'])
        left, right = spans[identity]
        if sha(data[left:right]) != row['before_sha256'] or sha(value) != row['after_sha256']:
            raise ValueError('Root preimage/postimage mismatch: ' + str(identity))
        if identity in selected and selected[identity] != value:
            raise ValueError('Conflicting overlays: ' + str(identity))
        selected[identity] = value
    packed, offsets = bytearray(), {}
    for old_off in sorted(refs):
        identity = refs[old_off]
        left, right = spans[identity]
        offsets[identity] = len(packed)
        packed.extend(selected.get(identity, data[left:right]))
    result = baked.pack_container(h, [(key, offsets[key, None]) for key, _ in entries],
        [(key, variant, offsets[key, variant]) for key, variant, _ in variants], packed)
    _, new_entries, new_variants, new_data, _, new_spans = batch.packed(result)
    if [r[0] for r in entries] != [r[0] for r in new_entries] or [r[:2] for r in variants] != [r[:2] for r in new_variants]:
        raise ValueError('Root inventory/order changed')
    for identity, (left, right) in spans.items():
        new_left, new_right = new_spans[identity]
        expected = selected.get(identity, data[left:right])
        if new_data[new_left:new_right] != expected:
            raise ValueError('Merged root preservation failed')
    return result, {'changed_roots': len(selected), 'total_roots': len(spans),
        'unselected_roots_byte_preserved': True,
        'identities': [list(identity) for identity in selected]}

def build():
    if OUT.exists():
        raise ValueError('Existing unified candidate preserved')
    story = json.loads((STORY / 'manifest.json').read_bytes())
    equipment = json.loads((EQUIPMENT / 'manifest.json').read_bytes())
    checked(BASE_AVATAR, 'dfd331e7b89063be037e6cfbf930fc6f48a42a9189ca3a54307c73a43bfab6e2')
    checked(STRINGMAP, '297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1')
    overlays = [(row, checked(STORY / row['overlay']['path'], row['after_sha256']))
        for row in story['ability_root_overlay'] if 'overlay' in row]
    overlays.extend((row, checked(EQUIPMENT / row['after_path'], row['after_sha256']))
        for row in equipment['roots'])
    ability, preservation = merge(checked(BASE_ABILITY, equipment['base_sha256']), overlays)
    weapon_info = equipment['weapon_overlay']
    weapon, weapon_preservation = merge(checked(BASE_WEAPON, weapon_info['before_sha256']),
        [(row, checked(EQUIPMENT / row['after_path'], row['after_sha256'])) for row in weapon_info['roots']])
    if sha(weapon) != weapon_info['after_sha256']:
        raise ValueError('Weapon whole candidate differs from audited overlay')
    OUT.mkdir(parents=True)
    files = []
    for row in story['files']:
        if row['path'] == '_baked/bakedabilitydata':
            raw = ability
        else:
            raw = checked(STORY / row['path'], row['sha256'])
        target = OUT / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files.append({'path': row['path'], 'bytes': len(raw), 'sha256': sha(raw),
            'required_existing_sha256': row['required_existing_sha256'],
            'device_path': ('/sdcard/bh3-server19-baked/' if row['path'].startswith('_baked/')
                            else '/sdcard/bh3-server19-metadata/' if row['path'].startswith('_exceloutputasset/')
                            else '/sdcard/bh3-server19-resources/') + row['path']})
    target = OUT / '_baked/bakedweapondata'
    target.write_bytes(weapon)
    files.append({'path': '_baked/bakedweapondata', 'bytes': len(weapon), 'sha256': sha(weapon),
        'required_existing_sha256': weapon_info['before_sha256'],
        'device_path': '/sdcard/bh3-server19-baked/_baked/bakedweapondata'})
    # These two registry inputs are unchanged and are not deployment writes.
    checked(BASE_AVATAR, 'dfd331e7b89063be037e6cfbf930fc6f48a42a9189ca3a54307c73a43bfab6e2')
    checked(STRINGMAP, '297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1')
    shutil.copy2(BASE_AVATAR, OUT / '_baked/bakedavatardata')
    shutil.copy2(STRINGMAP, OUT / '_baked/stringmap.txt')
    lib = OUT / 'lib/lib-server19-decode-trace.so'
    native = trace.build(ROOT / 'server19-run/black3d-repair/gyro-verification-builds/candidate/lib-server19-resources.so', lib)
    files.append({'path': str(lib.relative_to(OUT)).replace('\\', '/'),
        'bytes': lib.stat().st_size, 'sha256': native['output_sha256'],
        'required_existing_sha256': native['input_sha256'], 'device_path': '@native-library'})
    manifest = {'schema': 1, 'status': 'candidate_human_pending', 'serial': 'REFERENCE_DEVICE',
        'story_manifest_sha256': sha((STORY / 'manifest.json').read_bytes()),
        'equipment_manifest_sha256': sha((EQUIPMENT / 'manifest.json').read_bytes()),
        'ready_stage_ids': story['ready_stage_ids'], 'files': files,
        'ability_preservation': preservation, 'weapon_preservation': weapon_preservation,
        'required_existing_shared_Lua_files': story['required_existing_shared_Lua_files'],
        'save_operation': 'none', 'device_operation': 'none', 'original_decode_exceptions_retained': True}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest

if __name__ == '__main__':
    report = build()
    print(json.dumps({'candidate': str(OUT), 'files': len(report['files']),
        'ready_stage_ids': report['ready_stage_ids'],
        'ability_roots': report['ability_preservation']['changed_roots'],
        'native_sha256': report['files'][-1]['sha256']}))
