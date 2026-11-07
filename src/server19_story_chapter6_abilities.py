"""Audit White Comet and literal Chapter6 ability dependencies without unlocking skills.

Buff1002 uses the same later UI-only lifecycle as the reviewed1001/6005/6006.
Only Kiana_PT_StunCharge may use this additional exception. Actual combat
actions, predicates and modifier values must pass retained-terminal checks.
The later buff-panel presentation remains unavailable in original1.9.
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
import csv
import io
from collections import Counter

import server19_avatar_battle_resources as batch
import server19_resources as resources
from server19_story_fire_prop_runtime import repack
from server19_story_shield_bridge import ShieldClosure
from server19_story_wave_abilities import registered_references

ROOT = Path(__file__).resolve().parent
PROOF = ROOT / '.local-baseline/server19-dev/story-all-20261015/goal-six-chapters-20261016'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Chapter6Closure(ShieldClosure):
    def project(self, identity):
        prior = getattr(self.schema, 'ui_custom_buff_ids', ())
        self.schema.ui_custom_buff_ids = (1001, 6005, 6006) + ((1002,) if identity == (13413, None) else ())
        try:
            return super().project(identity)
        finally:
            self.schema.ui_custom_buff_ids = prior


def consumer_evidence(source):
    """Match the saved consumer disassembly to the pinned actual source binary."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    records = []
    for name in ('58258-custombuff.asm', '58259-custombuff.asm',
                 '70637-custombuff-action.asm', '70639-custombuff-action.asm'):
        raw = (PROOF / name).read_bytes()
        lines = raw.decode().splitlines()
        count = 0
        for line in lines:
            parts = line.split(maxsplit=1)
            if not parts or len(parts[0]) != 8:
                continue
            address = int(parts[0], 16)
            ins = next(md.disasm(source.binary[address:address+16], address, count=1))
            expected = (ins.mnemonic + ' ' + ins.op_str).strip()
            if not parts[1].startswith(expected):
                raise ValueError('Saved UI consumer proof differs from source at ' + hex(address))
            count += 1
        if not count:
            raise ValueError('Empty UI consumer proof')
        records.append(dict(path=str(PROOF / name), sha256=sha(raw), verified_instructions=count))
    xrefs = json.loads((PROOF / 'custombuff-consumer-xrefs.json').read_bytes())
    return dict(disassembly=records, saved_consumer_xrefs=xrefs,
                limitation='Later buff-panel UI absent; not restored by this compatibility projection')


def trial_dependencies(metadata_dir, baked_dir, strings, package):
    """Include forced trial loadouts, even when absent from the owned account."""
    from server19_stage_resources import text_record
    from server19_story_weapon_runtime import dependencies
    from server19_chapter1_resources import scalar
    metadata_dir = Path(metadata_dir)
    levels = json.loads((metadata_dir / 'leveltrialdata').read_bytes())
    levels = [r for r in levels if 10601 <= r['stageID'] <= 10615]
    trials = {r['ID']: r for r in json.loads((metadata_dir / 'avatartrialdata').read_bytes())}
    roster = json.loads((ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2/manifest.json').read_bytes())['roster']
    maps = {r['path']: r for r in resources.resource_map(resources.DEFAULT24)}
    tables = {}
    table_proof = {}
    for name in ('weapondata', 'stigmatadata', 'equipmentsetdata'):
        raw, _ = text_record(package, maps['data/_exceloutput/' + name], '2.4')
        tables[name] = {int(r['ID']): r for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter='\t')}
        table_proof[name] = sha(raw)
    registry = batch.packed((baked_dir / 'bakedequipskilldata').read_bytes())
    weapon_refs = dependencies((baked_dir / 'bakedweapondata').read_bytes(), strings)['dependencies']
    selected, proof = set(), []
    for tid in sorted({tid for row in levels for tid in row['avatarList']}):
        trial = trials[tid]
        actor = next(r for r in roster if r['avatar_id'] == trial['avatarID'])
        granted = {r['skillID'] for r in trial['avatarSubSkills'] if r['skillLV'] > 0}
        for dep in actor['dependencies']:
            evidence = dep.get('evidence', {})
            gate = evidence.get('skill_gate') or {}
            use = dep['scope'] in ('base', 'default_skill', 'conditional_leader')
            use |= dep['scope'] == 'conditional_subskill' and evidence.get('sub_skill_id') in granted
            use |= dep['scope'] == 'main_skill' and trial['avatarLV'] >= gate.get('unlockLv', 999) and trial['avatarStar'] >= gate.get('unlockStar', 999)
            if use:
                selected.add((dep['key'], dep['variant']))
        items = [tables['weapondata'][trial['weaponID']]]
        stigmas = [tables['stigmatadata'][trial['stigmataID' + str(i)]] for i in (1, 2, 3) if trial['stigmataID' + str(i)]]
        items.extend(stigmas)
        skills = {int(row['prop' + str(i) + 'ID']) for row in items for i in (1, 2, 3)} - {0}
        for set_id, count in Counter(int(r['setID']) for r in stigmas if int(r['setID'])).items():
            row = tables['equipmentsetdata'][set_id]
            for i in (1, 2, 3):
                skill = int(row['prop' + str(i) + 'ID'])
                if skill and count >= int(row['spellEffectNum' + str(i)]):
                    skills.add(skill)
        resolved = []
        for skill in sorted(skills):
            left, right = registry[5][skill, None]
            q = batch.baked.MessagePackSpanReader(registry[3]); q.pos = left
            node = q.node()
            assert node['count'] == 18 and q.pos == right
            key, variant = [scalar(registry[3], n) for n in node['children'][1:3]]
            if variant is not None and strings[variant] == 'Default':
                variant = None
            selected.add((key, variant)); resolved.append(dict(skill_id=skill, identity=(key, variant), name=strings[key]))
        for dep in weapon_refs:
            if any(r['weapon_id'] == trial['weaponID'] for r in dep['weapons']):
                selected.add(tuple(dep['identity']))
        proof.append(dict(trial=trial, equipment_skills=resolved))
    return selected, dict(levels=levels, trials=proof, source_table_sha256=table_proof,
        metadata_sha256={n: sha((metadata_dir / n).read_bytes()) for n in ('leveltrialdata', 'avatartrialdata')})


def prepare(ability_file, baked_dir, chapter6_lua_dir, output, metadata_dir=None, approximate_trial_reduction=False):
    ability_file, baked_dir, chapter6_lua_dir, output = map(Path,
        (ability_file, baked_dir, chapter6_lua_dir, output))
    output.mkdir(parents=True, exist_ok=False)
    raw = ability_file.read_bytes()
    string_raw = (baked_dir / 'stringmap.txt').read_bytes()
    strings = string_raw.decode('utf8').split('\x1f')
    old_strings = strings.copy()
    props = (baked_dir / 'bakedpropdata').read_bytes()
    old = batch.packed(raw)
    names = {strings[k[0]] for k in old[5]}
    selected = {k for k in old[5] if strings[k[0]].startswith('Kiana_PT_')}
    # Native revival applies this shared ability dynamically, outside Lua refs.
    selected.update(k for k in old[5] if strings[k[0]] == 'Level_AvatarReviveInvincible')
    proof = [dict(identity=k, reason='White Comet ability family; no skill gate changes')
             for k in sorted(selected, key=str)]
    files = []
    for path in sorted(chapter6_lua_dir.glob('*.lua')):
        content = path.read_bytes()
        refs = registered_references(content.decode('utf-8-sig'), names)
        files.append(dict(path=str(path), sha256=sha(content), references=refs))
        for ref in refs:
            selected.update(k for k in old[5] if strings[k[0]] == ref['ability'])
    if not files or (13413, None) not in selected:
        raise ValueError('Missing Chapter6 scripts or the observed failing root')
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        trial_proof = None
        if metadata_dir:
            trial_seeds, trial_proof = trial_dependencies(metadata_dir, baked_dir, strings, package)
            selected.update(trial_seeds)
        closure = Chapter6Closure(package, strings,
            {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}, output)
        consumers = consumer_evidence(closure.schema.source)
        if approximate_trial_reduction:
            if not metadata_dir:
                raise ValueError('Trial approximation requires actual trial selection evidence')
            closure.schema.leader_restrict_roots = (10204,)
            closure.schema.approved_trial_reduction_approximation = (10204,)
        closure.before = raw
        closure.data, closure.spans = old[3::2]
        closure.prop_raw = props
        closure.prop_data, closure.prop_spans = batch.packed(props)[3::2]
        for identity in sorted(selected, key=str):
            closure.project(identity)
        if closure.errors or any('blocker' in r for r in closure.props.values()):
            (output / 'blocked.json').write_text(json.dumps(dict(
                trial_dependencies=trial_proof, checked_abilities=len(closure.records),
                records=list(closure.records.values()), props=list(closure.props.values()),
                errors=[dict(identity=k, reason=v) for k, v in closure.errors.items()],
                deployed=False), ensure_ascii=False, indent=2), encoding='utf8')
            raise ValueError(str((closure.errors, closure.props)))
        if closure.prop_changes or strings != old_strings or closure.monster_refs:
            raise ValueError('Unexpected non-ability changes or monster dependency')
        candidate = repack(raw, closure.changes)
        new = batch.packed(candidate)
        assert set(old[5]) == set(new[5])
        retained = 0
        for identity, span in old[5].items():
            if identity not in closure.changes:
                assert old[3][slice(*span)] == new[3][slice(*new[5][identity])]
                retained += 1
        report = dict(status='technical_checks_passed_human_pending',
            before_sha256=sha(raw), after_sha256=sha(candidate),
            prop_sha256=sha(props), stringmap_sha256=sha(string_raw),
            seed_count=len(selected), checked_abilities=len(closure.records),
            changed_abilities=len(closure.changes), unchanged_abilities=retained,
            selection=proof, chapter6_scripts=files, consumer_evidence=consumers, trial_dependencies=trial_proof,
            records=list(closure.records.values()),
            user_approved_trial_reduction_approximation=approximate_trial_reduction,
            scope_limit='White Comet family and literal registered Chapter6 references plus dependencies; dynamic names and full gameplay unverified',
            skill_gates_changed=False, human_acceptance='pending')
        (output / 'bakedabilitydata').write_bytes(candidate)
        (output / 'technical-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ability_file', 'baked_dir', 'chapter6_lua_dir', 'output'):
        parser.add_argument(name)
    parser.add_argument('--metadata-dir')
    parser.add_argument('--approximate-trial-reduction', action='store_true')
    result = prepare(**vars(parser.parse_args()))
    print(json.dumps({k: result[k] for k in ('status', 'checked_abilities',
        'changed_abilities', 'unchanged_abilities', 'after_sha256')}))
