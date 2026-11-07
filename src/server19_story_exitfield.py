"""Prepare the original MP_ExitField ability closure; never operate a device.

Stage 10514's recorded decoder offset 0xa8934 falls in ability 14706,
MP_Prop_ExitFieldDone_Effect, in the Act2 runtime. Preserve the prop, its
original prefab, StringMap, and every ability outside this dependency closure.
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
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import server19_avatar_battle_resources as batch
import server19_resources as resources
from server19_story_fire_prop_runtime import repack
from server19_story_shield_bridge import ShieldClosure


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(baked_dir, output):
    baked_dir, output = Path(baked_dir), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    inputs = {name: (baked_dir / name).read_bytes() for name in
              ('bakedabilitydata', 'bakedpropdata', 'stringmap.txt')}
    strings = inputs['stringmap.txt'].decode('utf8').split('\x1f')
    original_strings = strings.copy()
    original_map = {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}
    prefab = original_map['entities/propobject/mp/mp_exitfield']
    with zipfile.ZipFile(resources.DEFAULT19) as package:
        obj, raw = resources.object_bytes(package, prefab)
        if obj['class'] != 1 or not raw:
            raise ValueError('Original MP_ExitField is not a nonempty GameObject')
        prefab = dict(prefab, root_sha256=sha(raw))
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        closure = ShieldClosure(package, strings, original_map, output)
        closure.before = inputs['bakedabilitydata']
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        closure.prop_raw = inputs['bakedpropdata']
        closure.prop_data, closure.prop_spans = batch.packed(closure.prop_raw)[3::2]
        closure.prop(strings.index('MP_ExitField'))
        blockers = [r for r in closure.props.values() if 'blocker' in r]
        if blockers or closure.errors:
            raise ValueError(str((blockers, closure.errors)))
        if closure.prop_changes or strings != original_strings or closure.monster_refs:
            raise ValueError('Unexpected changes outside the exit-field ability closure')
        candidate = repack(closure.before, closure.changes)
        old, new = batch.packed(closure.before), batch.packed(candidate)
        if set(old[5]) != set(new[5]):
            raise ValueError('Ability registry identities changed')
        retained = 0
        for identity, span in old[5].items():
            if identity not in closure.changes:
                if old[3][slice(*span)] != new[3][slice(*new[5][identity])]:
                    raise ValueError('Unselected ability changed: ' + str(identity))
                retained += 1
        report = dict(status='technical_checks_passed_human_pending',
            original_prefab=prefab, prop_records=list(closure.props.values()),
            ability_records=list(closure.records.values()),
            checked_abilities=len(closure.records), changed_abilities=len(closure.changes),
            unchanged_abilities=retained, props_and_stringmap_unchanged=True,
            inputs={n: sha(v) for n, v in inputs.items()},
            output_sha256=sha(candidate), output_bytes=len(candidate),
            human_acceptance='pending', device_modified=False)
        (output / 'bakedabilitydata').write_bytes(candidate)
        (output / 'technical-check.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baked_dir')
    parser.add_argument('output')
    args = parser.parse_args()
    result = prepare(args.baked_dir, args.output)
    print(json.dumps({k: result[k] for k in ('status', 'checked_abilities',
        'changed_abilities', 'unchanged_abilities', 'output_sha256')}))
