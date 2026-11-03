"""Project team-composition and starter-set ability dependencies; no device/save operations."""

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
import json
import zipfile
import server19_avatar_battle_resources as batch
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
BASE = ROOT / '.local-baseline/server19-dev/avatar-battle-ready-final-v2'
OUTPUT = ROOT / '.local-baseline/server19-dev/mixed-team-equipment-ready'
IDENTITY = (13409, None)
PREIMAGE = 'd47a06aacdb0d7a23c63a2d79e5070e2e4dec1cf9b7b16b8b14c809a98fa356e'

def build(output=OUTPUT):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use a new output directory inside the workspace')
    strings = batch.STRINGS.read_text(encoding='utf-8').split('\x1f')
    old = (BASE / '_baked/bakedabilitydata').read_bytes()
    if batch.baked.sha(old) != PREIMAGE or strings[IDENTITY[0]] != 'Kiana_PT_ModifyDamageByLLL':
        raise ValueError('Audited input changed')
    h, entries, overrides, data, refs, spans = batch.packed(old)
    source = (BASE / 'reference/source-ability').read_bytes()
    if batch.baked.sha(source) != batch.ability.SOURCE_SHA:
        raise ValueError('Audited source ability container changed')
    _, _, _, source_data, _, source_spans = batch.packed(source)
    # Both currently owned starter sets contribute native equipment abilities.
    # Follow their baked skill references, rather than guessing ability names.
    equip_raw = (ROOT / '.local-baseline/server19-dev/baked-fallback/_baked/bakedequipskilldata').read_bytes()
    _, equip_entries, _, equip_data = batch.baked.unpack_container(equip_raw)
    identities = {IDENTITY}
    references = []
    for skill in (40, 44, 46, 65):
        q = batch.baked.MessagePackSpanReader(equip_data)
        q.pos = dict(equip_entries)[skill]
        node = q.node()
        if node['kind'] != 'array' or node['count'] != 18:
            raise ValueError('Audited equipment skill record changed')
        key = batch.baked.decode_integer(equip_data, node['children'][1])
        if not strings[key].startswith('Equip_'):
            raise ValueError('Equipment ability reference changed')
        identities.add((key, None))
        references.append({'skill_id': skill, 'ability_key': key, 'ability_name': strings[key]})
    changes, records = {}, []
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        schema = batch.BattleSchema(package, strings)
        for identity in sorted(identities):
            left, right = source_spans[identity]
            reader = batch.BattleReader(source_data, strings, schema)
            reader.pos = left
            reader.class_value(batch.ability.ABILITY, 'ability')
            if reader.pos != right:
                raise ValueError('Source root boundary mismatch')
            value = batch.apply_edits(source_data, left, right, reader)
            check = batch.BattleReader(value, strings, schema, True)
            check.class_value(batch.ability.ABILITY, 'ability')
            if check.pos != len(value):
                raise ValueError('Original root boundary mismatch')
            changes[identity] = value
            records.append({'identity': identity, 'name': strings[identity[0]], 'adaptations': reader.records})
    assembled, offsets = bytearray(), {}
    for offset in sorted(refs):
        identity = refs[offset]
        start, end = spans[identity]
        offsets[offset] = len(assembled)
        assembled.extend(changes.get(identity, data[start:end]))
    result = batch.baked.pack_container(h, [(key, offsets[offset]) for key, offset in entries],
        [(key, variant, offsets[offset]) for key, variant, offset in overrides], bytes(assembled))
    _, _, _, next_data, _, next_spans = batch.packed(result)
    for identity, (start, end) in spans.items():
        left, right = next_spans[identity]
        if next_data[left:right] != (changes.get(identity, data[start:end])):
            raise ValueError('Unrelated root changed')
    output.mkdir(parents=True)
    (output / 'bakedabilitydata').write_bytes(result)
    (output / 'manifest.json').write_text(json.dumps({'before_sha256': PREIMAGE,
        'after_sha256': batch.baked.sha(result), 'identity': IDENTITY,
        'name': strings[IDENTITY[0]], 'projected_roots': records, 'equipment_references': references,
        'other_roots_byte_identical': True, 'original_typed_root_consumed': True,
        'status': 'candidate_human_pending'}, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    build()
