"""Unify reviewed remaining Chapter1 resources and real item metadata.

Build and read-only preflight do not activate a gate. Deploy requires an exited
local game, preserves preimages, verifies device readback, and activates only
the reviewed local gate. No launch, force-stop, server restart or save edits.
"""

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
import argparse
import json

import server19_story_batch_resources as files
import server19_story_batch_deploy as deployer
import server19_batch_diagnostics as diagnostics
import server19_stage as stage
import server19_chapter1_metadata as metadata

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '.local-baseline/server19-dev/chapter1-unified-ready/v1'
RESOURCE = ROOT / '.local-baseline/server19-dev/chapter1-remaining-ready/v7'
META = metadata.OUT
NATIVE_SHA = '63237c69a5e8adf2384c74eb12a9fe1ba96dc1f896d3fd2740eeb8718d5d0789'
WEAPON = ROOT / '.local-baseline/server19-dev/cultivation-unified-ready/_baked/bakedweapondata'
AVATAR = ROOT / '.local-baseline/server19-dev/baked-fallback/_baked/bakedavatardata'
WEAPON_SHA = 'e48edc01666f300524bdd023ce47cac2b11ca31b1b051a689420f3040c7efe84'
AVATAR_SHA = 'dfd331e7b89063be037e6cfbf930fc6f48a42a9189ca3a54307c73a43bfab6e2'
MATRIX = ROOT / '.local-baseline/server19-dev/cultivation-full-equipment-ready/matrix.json'
READY = ROOT / '.local-baseline/server19-dev/chapter1-remaining-ready/runtime-ready.json'
RUN = ROOT / 'server19-run/chapter1-batch'


def build(resource=RESOURCE, meta=META, output=OUT):
    resource, meta, output = map(Path, (resource, meta, output))
    if output.exists() or not output.resolve().is_relative_to(ROOT):
        raise ValueError('Preserve existing candidates; use a fresh workspace directory')
    manifest = json.loads((resource / 'manifest.json').read_bytes())
    if manifest['ready_stage_ids'] != list(range(10111, 10137)) or manifest['blocked_stage_ids']:
        raise ValueError('Whole remaining chapter mechanical closure is not ready')
    meta_manifest = json.loads((meta / 'manifest.json').read_bytes())
    result = {'schema': 2, 'serial': 'REFERENCE_DEVICE',
        'status': 'technical_candidate_human_pending', 'files': [],
        'ready_stage_ids': list(range(10108, 10137)),
        'chapter1_remaining_inventory': manifest['chapter1_remaining_inventory'],
        'source_manifests': [
            {'path': str(resource / 'manifest.json'), 'sha256': files.batch.baked.sha((resource / 'manifest.json').read_bytes())},
            {'path': str(meta / 'manifest.json'), 'sha256': files.batch.baked.sha((meta / 'manifest.json').read_bytes())}],
        'required_existing_shared_Lua_files': manifest['required_existing_shared_Lua_files'],
        'save_operation': 'none', 'native_library_operation': 'none',
        'visual_missing': ['material3108: original MaterialIcons/5606 and MaterialFigures/5606 absent',
                          'avatarfragment10603: original Icons/Figures10603 absent'],
        'visual_behavior': 'Retain genuine paths; original SafeSetSprite/ItemEmpty fallback. No fabricated replacement.',
        'historical19_data_recovered': False, 'human_gameplay': 'pending'}
    output.mkdir(parents=True)
    for folder, rows in ((resource, manifest['files']), (meta, meta_manifest['files'])):
        for row in rows:
            raw = files.checked(folder / row['path'], row['sha256'])
            if any(old['path'] == row['path'] for old in result['files']):
                raise ValueError('Overlapping candidate files')
            stored = files.store(output, row['path'], raw)
            stored['required_existing_sha256'] = row['required_existing_sha256']
            stored['device_path'] = (
                '/sdcard/bh3-server19-baked/' if row['path'].startswith('_baked/') else
                '/sdcard/bh3-server19-metadata/' if row['path'].startswith('_exceloutputasset/') else
                '/sdcard/bh3-server19-resources/') + row['path']
            result['files'].append(stored)
    for source, digest in ((AVATAR, AVATAR_SHA), (WEAPON, WEAPON_SHA)):
        files.store(output, '_baked/' + source.name, files.checked(source, digest))
    # Bind the already accepted1-8..1-10 Lua; gate expansion does not rewrite it.
    earlier = ROOT / '.local-baseline/server19-dev/story-chain-batch-ready/v4'
    old_manifest = json.loads((earlier / 'manifest.json').read_bytes())
    for row in old_manifest['files']:
        if row['path'].startswith('lua/levels/'):
            result['required_existing_shared_Lua_files'].append({
                'path': row['path'], 'required_existing_sha256': row['sha256']})
    index = diagnostics.build_index(
        {1: output / '_baked/bakedabilitydata', 2: output / '_baked/bakedmonsterdata',
         3: output / '_baked/bakedavatardata', 4: output / '_baked/bakedweapondata'},
        output / '_baked/stringmap.txt', MATRIX, resource / 'manifest.json')
    diagnostics.write_report(output / 'diagnostic-index.json', index)
    result['diagnostic_index_sha256'] = files.batch.baked.sha((output / 'diagnostic-index.json').read_bytes())
    diagnostics.write_report(output / 'manifest.json', result)
    return result


def configure(output=OUT):
    deployer.OUT = Path(output)
    deployer.RUN = RUN
    deployer.READY = READY
    deployer.EXPECTED_READY_IDS = list(range(10108, 10137))
    deployer.RECEIPT_SCHEMA = 2
    deployer.ADDITIONAL_RETAINED = [
        {'target': '@native-library', 'sha256': NATIVE_SHA},
        {'target': '/sdcard/bh3-server19-baked/_baked/bakedweapondata', 'sha256': WEAPON_SHA}]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'preflight', 'deploy'))
    parser.add_argument('--resource', type=Path, default=RESOURCE)
    parser.add_argument('--metadata', type=Path, default=META)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    if args.action == 'build':
        result = build(args.resource, args.metadata, args.output)
        print(json.dumps({'candidate': str(args.output), 'files': len(result['files']),
                          'ready_stage_ids': result['ready_stage_ids'], 'human': 'pending'}))
    else:
        configure(args.output)
        result = deployer.preflight() if args.action == 'preflight' else deployer.deploy()
        print(json.dumps({'operation': result['operation'], 'files': len(result['files']),
                          'game_pid': result['game_pid'], 'save_operation': 'none'}))
