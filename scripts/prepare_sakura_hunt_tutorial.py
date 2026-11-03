"""Project the original HealSP teaching action without changing its effect."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server19_avatar_battle_resources as batch
import server19_resources as resources
from server19_story_shield_bridge import ShieldClosure
from server19_story_fire_prop_runtime import repack

def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    rows = json.loads((ROOT / 'server19-run/common-baseline-20261027-v1/runtime-artifacts.json').read_bytes())
    mapping = {r['remote']: ROOT / r['local'] for r in rows}
    base = '/sdcard/bh3-server19-baked/_baked/'
    raw = mapping[base+'bakedabilitydata'].read_bytes()
    props = mapping[base+'bakedpropdata'].read_bytes()
    strings = mapping[base+'stringmap.txt'].read_text(encoding='utf-8').split('\x1f')
    original_strings = strings.copy()
    old = batch.packed(raw)
    identity = (14032, None)
    assert strings[14032] == 'Level_OpenWorldHuntmodeTutorialHealSp'
    assert old[5][identity][0] <= 0xee066 < old[5][identity][1]
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        closure = ShieldClosure(package, strings,
            {r['path']: r for r in resources.resource_map(resources.DEFAULT19)}, output)
        closure.before = raw
        closure.data, closure.spans = old[3::2]
        closure.prop_raw = props
        closure.prop_data, closure.prop_spans = batch.packed(props)[3::2]
        closure.project(identity)
        assert not closure.errors and set(closure.changes) == {identity}
        assert not closure.prop_changes and not closure.monster_refs
        assert strings == original_strings
        record = closure.records[identity]
        assert record['original_consumer_valid'] and record['retained_terminals_equal']
        assert [(a['operation'], a.get('concrete'), a.get('source_hex')) for a in record['adaptations']] == [
            ('union_tag_same_type', 'MoleMole.Config.HealSP', None),
            ('remove_later_field', None, 'c0')]
        candidate = repack(raw, closure.changes)
    new = batch.packed(candidate)
    assert set(new[5]) == set(old[5])
    for key, span in old[5].items():
        if key != identity: assert old[3][slice(*span)] == new[3][slice(*new[5][key])]
    (output/'bakedabilitydata').write_bytes(candidate)
    (output/'verification.json').write_text(json.dumps(dict(status='PASS', record=record,
        unchanged_roots=len(old[5])-1, unchanged_strings=True,
        before_sha256=batch.baked.sha(raw), after_sha256=batch.baked.sha(candidate),
        human_gameplay='pending'), ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: one HealSP root projected; all other roots and retained gameplay values unchanged')

if __name__ == '__main__':
    prepare(ROOT/'server19-run/integrated-sakura-error-20261027/fix')
