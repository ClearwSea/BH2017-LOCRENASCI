"""Project ConfigWeapon.AdditionalAbilities, including non-initial loadouts.

Equipment skill tables alone do not describe weapon-type runtime triggers.
Only existing source abilities are projected; no equipment/save changes.
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
import hashlib
import json
import zipfile
from pathlib import Path
import server19_resources as resources
import server19_avatar_battle_resources as batch
import server19_chapter1_resources as chapter
import server19_stage_monsters as monster
from server19_story_shield_bridge import ShieldClosure


def dependencies(payload, strings):
    _, _, _, data, _, spans = batch.packed(payload)
    selected = {}
    disabled = []
    for identity, (left, right) in spans.items():
        reader = batch.baked.MessagePackSpanReader(data)
        reader.pos = left
        root = reader.node()
        if root['count'] != 10 or reader.pos != right:
            raise ValueError('Actual weapon ten-field boundary changed: '+str(identity))
        additional = root['children'][3]
        if additional['code'] == 0xc0: continue
        if additional['kind'] not in ('array', 'map'):
            raise ValueError('Unknown additional-ability dictionary')
        values = additional['children'] if additional['kind'] == 'array' else additional['children'][1::2]
        for entry in values:
            if entry['count'] != 3:
                raise ValueError('Unknown weapon trigger shape')
            trigger, key, variant = [chapter.scalar(data, n) for n in entry['children']]
            if key is None:
                disabled.append(list(identity)); continue
            if not 0 <= key < len(strings) or variant is not None and not 0 <= variant < len(strings):
                raise ValueError('Weapon ability StringMap index out of bounds')
            selected.setdefault((key, variant), []).append({
                'weapon_id': identity[0], 'trigger': None if trigger is None else strings[trigger]})
    return {'weapon_roots': len(spans), 'dependencies': [
        {'identity': list(k), 'name': strings[k[0]], 'weapons': v} for k, v in selected.items()],
        'nil_ability_entries': disabled}


def prepare(current, ability_file, weapon_file, output):
    current, ability_file, weapon_file, output = map(Path, (current, ability_file, weapon_file, output))
    output.mkdir(exist_ok=False)
    strings = (current/'_baked/stringmap.txt').read_text(encoding='utf8').split('\x1f')
    before_strings = strings.copy()
    dependency_report = dependencies(weapon_file.read_bytes(), strings)
    (output/'weapon-dependencies.json').write_text(json.dumps(dependency_report, indent=2), encoding='utf8')
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        closure = ShieldClosure(source, strings,
            {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}, output)
        closure.schema.ui_custom_buff_ids = (1001,6005,6006)
        closure.before = ability_file.read_bytes()
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        seeds = [closure.resolve(tuple(r['identity'])) for r in dependency_report['dependencies']]
        for identity in seeds: closure.project(identity)
        if closure.errors: raise ValueError('Weapon runtime ability closure blocked: '+str(closure.errors))
        if strings != before_strings: raise ValueError('StringMap update needs a separate delivery')
        h, entries, overrides, data, refs, spans = batch.packed(closure.before)
        packed, offsets = bytearray(), {}
        for _, identity in sorted(refs.items()):
            offsets[identity] = len(packed)
            left, right = spans[identity]
            packed.extend(closure.changes.get(identity, data[left:right]))
        result = monster.pack_container(h, [(k, offsets[k, None]) for k, _ in entries],
            [(k, v, offsets[k, v]) for k, v, _ in overrides], bytes(packed))
        (output/'bakedabilitydata').write_bytes(result)
        report = {'status':'PASS_offline_human_pending', 'weapon_roots':dependency_report['weapon_roots'],
            'selected':len(seeds), 'changed':len(closure.changes), 'errors':[],
            'records':list(closure.records.values()), 'required_native_capabilities':['shield_cap_v1'],
            'weapon_file':str(weapon_file.resolve()), 'weapon_sha256':hashlib.sha256(weapon_file.read_bytes()).hexdigest(),
            'before_sha256':monster.sha(closure.before), 'after_sha256':monster.sha(result),
            'weapon_and_StringMap_unchanged':True, 'human_acceptance':'pending'}
        (output/'scan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    for arg in ('current','ability_file','weapon_file','output'): parser.add_argument(arg)
    args = parser.parse_args()
    report = prepare(args.current,args.ability_file,args.weapon_file,args.output)
    print(json.dumps({k:report[k] for k in ('status','weapon_roots','selected','changed','errors')}))
