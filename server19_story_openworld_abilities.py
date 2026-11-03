"""Project literal shared OpenWorld abilities without enabling unrelated gameplay.

Uses the established original-reader, same-concrete union mapping and nil-only
later-field projection. Unknown features remain blocked rather than replaced.
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
import hashlib
import json
import zipfile
import server19_resources as resources
import server19_stage_resources as lua
import server19_avatar_battle_resources as batch
from server19_story_shield_bridge import ShieldClosure
from server19_story_fire_prop_runtime import repack
from server19_story_wave_abilities import references, registered_references

ROOT = Path(__file__).resolve().parent
SCOPE = ROOT/'.local-baseline/server19-dev/story-all-20261015/goal-six-chapters-20261016/openworld-scope.json'


def prepare(ability_file, stringmap_file, output):
    ability_file, stringmap_file, output = map(Path, (ability_file, stringmap_file, output))
    output.mkdir(exist_ok=False)
    scope = json.loads(SCOPE.read_bytes())
    strings = stringmap_file.read_text(encoding='utf8').split('\x1f')
    before_strings = strings.copy()
    raw = ability_file.read_bytes()
    known_names={strings[k[0]] for k in batch.packed(raw)[5]}
    selected, proof = [], []
    maps = {r['path']: r for r in resources.resource_map(resources.DEFAULT24)}
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        for path, expected in scope['module_source_sha256'].items():
            data, _ = lua.text_record(package, maps[path], '2.4')
            assert hashlib.sha256(data).hexdigest() == expected
            text=data.decode('utf-8-sig')
            refs=references(text, unresolved=[])+registered_references(text,known_names)
            for ref in refs:
                key = strings.index(ref['ability'])
                selected.append((key, None))
                proof.append(dict(path=path, source_sha256=expected, **ref))
        selected = list(dict.fromkeys(selected))
        closure = ShieldClosure(package, strings,
            {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}, output)
        closure.before = raw
        closure.data, closure.spans = batch.packed(raw)[3::2]
        # ConfigAvatarCameraAction is a tag/payload union, not an empty base
        # class. Execute both original/source formatter branches and require
        # identical concrete types before reading the fishing camera actions.
        from server19_story_poly_dispatch import evidence
        camera_type = 'MoleMole.Config.ConfigAvatarCameraAction'
        camera_proof = evidence(closure.schema, camera_type, 58759)
        closure.schema.story_small_poly = {camera_type: {
            r['tag']: r['concrete'] for r in camera_proof if r['original']}}
        primary_keys = {identity[0] for identity in selected}
        selected.extend(identity for identity in closure.spans
                        if identity[0] in primary_keys and identity[1] is not None)
        selected = list(dict.fromkeys(selected))
        for identity in selected:
            closure.project(identity)
        if closure.errors:
            raise ValueError('Additional shared ability blockers: '+str(closure.errors))
        assert strings == before_strings
        required = {'LevelTag_OpenWorld', 'OpenWorld_Avatar_InteractOff',
                    'OpenWorld_Avatar_TriggerFastRun', 'Rogue_AvatarSelf_StoreBuyTrigger',
                    'OpenWorld_Time_Predicate', 'OpenWorld_Avatar_AreaPredicate'}
        passed = {r['name'] for k, r in closure.records.items() if k not in closure.errors}
        assert required <= passed
        candidate = repack(raw, closure.changes)
        old, new = batch.packed(raw), batch.packed(candidate)
        assert set(old[5]) == set(new[5])
        retained = 0
        for identity, span in old[5].items():
            if identity not in closure.changes:
                assert old[3][slice(*span)] == new[3][slice(*new[5][identity])]
                retained += 1
        (output/'bakedabilitydata').write_bytes(candidate)
        report = dict(status='PASS_scoped_fix_human_pending', seeds=len(selected),
            checked_roots=len(closure.records)-len(closure.errors),
            changed_roots=len(closure.changes), unchanged_roots=retained,
            StringMap_unchanged=True, selected_stage_ids=scope['stage_ids'],
            references=proof, camera_dispatch_proof=camera_proof,
            includes_registered_variants=True, records=list(closure.records.values()),
            remaining_blockers=[dict(identity=k, name=strings[k[0]], reason=v)
                                for k, v in closure.errors.items()],
            before_sha256=hashlib.sha256(raw).hexdigest(),
            after_sha256=hashlib.sha256(candidate).hexdigest(),
            human_acceptance='pending', enabled_new_gameplay=False)
        (output/'technical-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('ability_file')
    parser.add_argument('stringmap_file')
    parser.add_argument('output')
    args = parser.parse_args()
    result = prepare(args.ability_file, args.stringmap_file, args.output)
    print(json.dumps({k: result[k] for k in ('status', 'seeds', 'checked_roots', 'changed_roots', 'unchanged_roots', 'remaining_blockers')}))
