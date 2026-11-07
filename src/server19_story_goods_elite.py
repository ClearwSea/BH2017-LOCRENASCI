"""Audit dynamic goods/elite roots with the original reader; no device writes."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
import zipfile
from pathlib import Path
import server19_chapter1_resources as chapter
import server19_avatar_battle_resources as batch
import server19_resources as resources
import server19_stage_monsters as monster


def prepare(current, output, *, prefixes=('Goods_', 'Elite_'), ability_file=None, runtime_schema=False):
    current, output = Path(current), Path(output)
    output.mkdir(exist_ok=False)
    strings = (current/'_baked/stringmap.txt').read_text(encoding='utf8').split('\x1f')
    original_strings=strings.copy()
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        from server19_story_shield_bridge import ShieldClosure
        closure_type=ShieldClosure if runtime_schema else chapter.AbilityClosure
        closure = closure_type(source, strings,
            {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}, output)
        if runtime_schema:
            import server19_equipment_battle_closure as equipment
            from server19_story_poly_dispatch import evidence
            closure.schema.ui_custom_buff_ids=(1001,6005,6006)
            closure.schema.leader_restrict_roots=(7067,12631)
            closure.schema.equipment_prop_selector_proof=equipment.prop_selector_evidence(closure.schema)
            closure.schema.equipment_prop_selectors={r['tag']:r['concrete'] for r in closure.schema.equipment_prop_selector_proof if r['original']}
            closure.schema.story_small_poly={}
            for name,mid in (('MoleMole.Config.BaseSpawnPropInitialPosSelect',58731),('MoleMole.Config.ConfigMonsterAttackHint',58775)):
                closure.schema.story_small_poly[name]={r['tag']:r['concrete'] for r in evidence(closure.schema,name,mid) if r['original']}
        closure.before = Path(ability_file or current/batch.ability.PATH).read_bytes()
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        selected = [k for k in closure.spans if strings[k[0]].startswith(tuple(prefixes))]
        for identity in selected:
            closure.project(identity)
        if strings!=original_strings:
            raise ValueError('StringMap changed; one-container delivery is insufficient')
        # Only proven projections enter the output. Unsupported real fields stay
        # unchanged and explicitly blocked, rather than being dropped.
        h, entries, overrides, data, refs, spans = batch.packed(closure.before)
        packed, offsets = bytearray(), {}
        for _, identity in sorted(refs.items()):
            offsets[identity] = len(packed)
            left, right = spans[identity]
            packed.extend(closure.changes.get(identity, data[left:right]))
        result = monster.pack_container(h,
            [(k, offsets[k, None]) for k, _ in entries],
            [(k, v, offsets[k, v]) for k, v, _ in overrides], bytes(packed))
        (output/'bakedabilitydata').write_bytes(result)
        report = {'prefixes': list(prefixes), 'selected': len(selected), 'changed': len(closure.changes),
            'records': list(closure.records.values()),
            'errors': [[list(k), strings[k[0]], v] for k, v in closure.errors.items()],
            'before_sha256': monster.sha(closure.before), 'after_sha256': monster.sha(result),
            'StringMap_unchanged':True,
            'human_acceptance': 'pending'}
        (output/'scan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('current')
    parser.add_argument('output')
    parser.add_argument('--ability-file')
    parser.add_argument('--prefixes', nargs='+', default=['Goods_', 'Elite_'])
    args = parser.parse_args()
    report = prepare(args.current, args.output, prefixes=args.prefixes, ability_file=args.ability_file)
    print(json.dumps({k: report[k] for k in ('selected', 'changed', 'errors')}))
