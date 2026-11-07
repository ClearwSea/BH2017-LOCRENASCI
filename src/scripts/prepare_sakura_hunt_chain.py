"""Validate the complete literal ability chain of the deployed hunt-mode Lua."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json, re, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server19_avatar_battle_resources as batch
import server19_resources as resources
from server19_story_shield_bridge import ShieldClosure
from server19_story_fire_prop_runtime import repack

def prepare():
    output = ROOT/'server19-run/sakura-hunt-chain-20261027/fix'
    output.mkdir(parents=True, exist_ok=True)
    raw = (output.parent/'bakedabilitydata.before').read_bytes()
    assert batch.baked.sha(raw) == '3aae4694ffc4f365d02ea48fd50472d2596fd550d630de6b1341e07ff6f36103'
    rows = json.loads((ROOT/'server19-run/common-baseline-20261027-v1/runtime-artifacts.json').read_bytes())
    mapping = {r['remote']: ROOT/r['local'] for r in rows}
    base = '/sdcard/bh3-server19-baked/_baked/'
    strings = mapping[base+'stringmap.txt'].read_text(encoding='utf-8').split('\x1f')
    old_strings = strings.copy()
    lua_path = mapping['/sdcard/bh3-server19-resources/lua/base/levelhuntmodecommon.lua']
    literals = set(re.findall(r'''["']([^"'\r\n]+)["']''', lua_path.read_text(encoding='utf-8')))
    old = batch.packed(raw)
    seeds = [key for key in old[5] if strings[key[0]] in literals]
    assert len(seeds) == 11
    assert old[5][14024,None][0] <= 0xedf19 < old[5][14024,None][1]
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        closure = ShieldClosure(package, strings,
            {r['path']:r for r in resources.resource_map(resources.DEFAULT19)}, output)
        closure.before=raw; closure.data,closure.spans=old[3::2]
        closure.prop_raw=mapping[base+'bakedpropdata'].read_bytes()
        closure.prop_data,closure.prop_spans=batch.packed(closure.prop_raw)[3::2]
        for identity in seeds: closure.project(identity)
        assert not closure.errors and not closure.prop_changes and not closure.monster_refs
        assert set(closure.changes)=={(n,None) for n in (14024,14025,14029,14030)}
        assert strings==old_strings
        for record in closure.records.values():
            assert record['original_consumer_valid'] and record['retained_terminals_equal']
            for change in record['adaptations']:
                assert change['operation']=='union_tag_same_type' or (
                    change['operation']=='remove_later_field' and change['source_hex']=='c0')
        candidate=repack(raw,closure.changes)
    new=batch.packed(candidate)
    assert set(old[5])==set(new[5])
    for key,span in old[5].items():
        if key not in closure.changes: assert old[3][slice(*span)]==new[3][slice(*new[5][key])]
    (output/'bakedabilitydata').write_bytes(candidate)
    report=dict(status='PASS',lua=str(lua_path.relative_to(ROOT)),lua_sha256=batch.baked.sha(lua_path.read_bytes()),
        seeds=[dict(identity=k,name=strings[k[0]]) for k in seeds],records=list(closure.records.values()),
        before_sha256=batch.baked.sha(raw),after_sha256=batch.baked.sha(candidate),
        changed_roots=4,unchanged_roots=len(old[5])-4,human_acceptance='pending')
    (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: 11 hunt-mode roots and references validated; 4 exact compatibility projections')

if __name__=='__main__': prepare()
