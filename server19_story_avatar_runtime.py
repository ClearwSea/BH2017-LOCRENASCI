"""Audit original roster base abilities independently of stage Lua and skill level.

The goal library must include shield_cap_v1. Buff1001 is presentation-only
registration, proved through the same original source handlers as6005/6006;
its gameplay modifier/actions/values remain. No conditional skill is enabled.
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
import json
import zipfile
from pathlib import Path
import server19_resources as resources
import server19_avatar_battle_resources as batch
import server19_stage_monsters as monster
from server19_story_shield_bridge import ShieldClosure


def selected_dependencies(roster, account=None, include_leaders=False):
    """Keep native gates; audit leaders and purchased skills without unlocking any."""
    actors = {a['avatar_id']: a for a in (account or {}).get('avatar_list', [])}
    selected, proof = [], []
    for actor in roster:
        live = actors.get(actor['avatar_id'])
        subs = {s['sub_skill_id']: s for skill in (live or {}).get('skill_list', [])
                for s in skill.get('sub_skill_list', [])}
        for dep in actor['dependencies']:
            scope, evidence = dep['scope'], dep.get('evidence', {})
            reason = None
            if scope in ('base', 'default_skill'):
                reason = scope
            elif include_leaders and scope == 'conditional_leader':
                reason = 'all original roster leader entries'
            elif live and scope == 'main_skill':
                gate = evidence.get('skill_gate') or {}
                if live['level'] >= gate.get('unlockLv', 999) and live['star'] >= gate.get('unlockStar', 999):
                    reason = 'owned avatar meets original main-skill level/star gates'
            elif live and scope == 'conditional_subskill':
                sub = subs.get(evidence.get('sub_skill_id'))
                if sub and sub.get('level', 0) > 0 and not sub.get('is_mask', False):
                    reason = 'purchased unmasked subskill in captured acceptance account'
            if reason:
                identity = (dep['key'], dep['variant'])
                selected.append(identity)
                proof.append(dict(avatar_id=actor['avatar_id'], identity=identity,
                                  name=dep['name'], scope=scope, reason=reason,
                                  sub_skill_id=evidence.get('sub_skill_id')))
    return list(dict.fromkeys(selected)), proof


def prepare(current, ability_file, output, *, account_file=None, include_leaders=False):
    current, ability_file, output = map(Path, (current, ability_file, output))
    output.mkdir(exist_ok=False)
    strings = (current/'_baked/stringmap.txt').read_text(encoding='utf8').split('\x1f')
    before_strings = strings.copy()
    roster = json.loads((batch.ROOT/'.local-baseline/server19-dev/avatar-battle-ready-final-v2/manifest.json').read_bytes())['roster']
    account = json.loads(Path(account_file).read_bytes()) if account_file else None
    selected, selection_proof = selected_dependencies(roster, account, include_leaders)
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        closure = ShieldClosure(source, strings,
            {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}, output)
        closure.schema.ui_custom_buff_ids = (1001, 6005, 6006)
        closure.schema.leader_restrict_roots = (7067,12631) if include_leaders else ()
        closure.before = ability_file.read_bytes()
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        for identity in selected: closure.project(identity)
        if closure.errors:
            (output/'blocked.json').write_text(json.dumps(dict(errors=[dict(identity=k,reason=v) for k,v in closure.errors.items()],
                selected=len(selected),selection_proof=selection_proof),ensure_ascii=False,indent=2),encoding='utf-8')
            raise ValueError('Original roster base ability remains blocked: '+str(closure.errors))
        if strings != before_strings:
            raise ValueError('A changed StringMap requires a separate reviewed delivery')
        h, entries, overrides, data, refs, spans = batch.packed(closure.before)
        packed, offsets = bytearray(), {}
        for _, identity in sorted(refs.items()):
            offsets[identity] = len(packed)
            left, right = spans[identity]
            packed.extend(closure.changes.get(identity, data[left:right]))
        result = monster.pack_container(h, [(k, offsets[k, None]) for k, _ in entries],
            [(k, v, offsets[k, v]) for k, v, _ in overrides], bytes(packed))
        (output/'bakedabilitydata').write_bytes(result)
        report = {'status': 'PASS_offline_human_pending', 'avatars': len(roster),
                  'selected': len(selected), 'changed': len(closure.changes),
                  'records': list(closure.records.values()), 'errors': [],
                  'selection_proof': selection_proof, 'include_all_roster_leaders': include_leaders,
                  'account_input': str(account_file) if account_file else None,
                  'required_native_capabilities': ['shield_cap_v1'],
                  'source_UI_registration_only_ids': [1001,6005,6006],
                  'StringMap_unchanged': True, 'conditional_skills_enabled': False,
                  'before_sha256': monster.sha(closure.before), 'after_sha256': monster.sha(result),
                  'human_acceptance': 'pending'}
        (output/'scan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('current')
    parser.add_argument('ability_file')
    parser.add_argument('output')
    parser.add_argument('--account-file')
    parser.add_argument('--include-leaders', action='store_true')
    args = parser.parse_args()
    report = prepare(args.current, args.ability_file, args.output,
                     account_file=args.account_file,include_leaders=args.include_leaders)
    print(json.dumps({k: report[k] for k in ('status','avatars','selected','changed','errors')}))
