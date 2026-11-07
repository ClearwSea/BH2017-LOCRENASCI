"""Inventory all compatibility rows and evolution boundaries, never unlock items.

Presence in a table/packed registry is not consumer or gameplay acceptance.
Runtime growth uses the separately checked battle closure, not this inventory.
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
from pathlib import Path
import server19_stage as stage
import server19_equipment as equipment
from server19_batch_diagnostics import unpack_container

def build():
    levels = stage._table('equipmentleveldata')
    result = []
    ready = equipment._audited_growth_ids()
    for table, kind in [('weapondata', 'weapon'), ('stigmatadata', 'stigmata')]:
        rows = stage._table(table)
        by_id = {row['ID']: row for row in rows}
        for row in rows:
            issues = []
            cap, exp_type = row['maxLv'], row['expType']
            if not 1 <= cap <= len(levels) or not 0 < exp_type < len(levels[0]['Type1']):
                issues.append('unsupported_level_or_EXP_index')
            if 1 <= cap <= len(levels) and 0 < exp_type < len(levels[0]['Type1']):
                if any(value['Type1'][exp_type] <= 0 for value in levels[:cap]):
                    issues.append('nonpositive_EXP_threshold')
            chain, seen, current = [], set(), row
            while current['evoID']:
                target = current['evoID']
                if target in seen:
                    issues.append('evolution_cycle'); break
                seen.add(target)
                if target not in by_id:
                    issues.append('missing_evolution_target'); break
                next_row = by_id[target]
                chain.append(target)
                if next_row['baseType'] != current['baseType'] or next_row.get('setID') != current.get('setID'):
                    issues.append('category_or_set_conversion_requires_audit')
                if next_row['maxLv'] <= current['maxLv']:
                    issues.append('nonincreasing_level_branch_requires_audit')
                current = next_row
            result.append({'id': row['ID'], 'kind': kind, 'title_key': row['displayTitle'],
                'rarity': row['rarity'], 'max_rarity': row['maxRarity'],
                'sub_rarity': row['subRarity'], 'max_level': cap, 'exp_type': exp_type,
                'base_type': row['baseType'], 'set_id': row.get('setID'),
                'evolution_chain': chain, 'evolution_materials': row['evoMaterial'],
                'refine_flag': row.get('canRefine'), 'affix_tree': row.get('affixTreeId'),
                'growable_consumer_closure': row['ID'] in ready,
                'battle_unverified': row['ID'] not in ready, 'boundary_issues': sorted(set(issues))})
    return {'schema': 1, 'status': 'inventory_and_bounds_not_gameplay_acceptance',
        'tables': {name: hashlib.sha256((stage.TABLE_DIRECTORY / name).read_bytes()).hexdigest()
                   for name in ['weapondata', 'stigmatadata', 'equipmentleveldata', 'avatardata']},
        'equipment': result,
        'avatars': [{'id': row['avatarID'], 'base_avatar_id': row['baseAvatarID'],
            'skills': row['skillList'], 'fragment_material': row['avatarFragmentID'],
            'awakening_shared_rules_pending': bool(row['baseAvatarID'])}
            for row in stage._table('avatardata')],
        'limits': ['No ownership or source-table presence establishes playability',
            'Later weapon conversion / super-limit mechanics need original wire, UI and resource evidence',
            'Saint-relic weapon names are not automatically a distinct cultivation system',
            'Unknown recipes, categories, equipment sacrifices and affix/reforge behavior fail closed']}

if __name__ == '__main__':
    out = stage.ROOT / 'server19-run/cultivation-batch/catalog.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    report = build()
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'equipment_rows': len(report['equipment']),
        'checked_growth_models': sum(row['growable_consumer_closure'] for row in report['equipment']),
        'max_levels': sorted(set(row['max_level'] for row in report['equipment'])),
        'rarities': sorted(set(row['rarity'] for row in report['equipment'])),
        'boundary_issue_rows': sum(bool(row['boundary_issues']) for row in report['equipment'])}))
