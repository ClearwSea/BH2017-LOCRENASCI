"""Prepare the missed five effect tags and a level80-safe trial48 Lua adapter.

Reads the captured Sony failure. No phone, service or live account writes.
Does not import the old probe, suppress effects, or replace the story avatar.
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
import zipfile

import server19_avatar_battle_resources as batch
import server19_chapter1_resources as chapter
import server19_resources as resources
import server19_story_batch_resources as story
import server19_stage_resources as lua

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'.local-baseline/server19-dev/story-all-20261015'
KEYS=(22078,22080,22081,22082,22083)


def prepare():
    output=WORK/'stage10116-fix-v1';output.mkdir(exist_ok=False)
    base=WORK/'candidate-v7/_baked/bakedabilitydata'
    before=base.read_bytes()
    strings=(WORK/'candidate-v7/_baked/stringmap.txt').read_text(encoding='utf-8').split('\x1f')
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        closure=chapter.AbilityClosure(package,strings,
            {r['path']:r for r in resources.resource_map(resources.DEFAULT19)},output)
        closure.before=before;closure.data,closure.spans=batch.packed(before)[3::2]
        records=[]
        for key in KEYS:
            identity=(key,None);closure.project(identity)
            assert identity not in closure.errors,closure.errors.get(identity)
            record=closure.records[identity]
            old=closure.data[slice(*closure.spans[identity])]
            new=closure.changes[identity]
            differences=[(i,a,b) for i,(a,b) in enumerate(zip(old,new)) if a!=b]
            assert len(old)==len(new) and differences==[(8,82,76)],(key,differences)
            assert record['original_consumer_valid'] and record['retained_terminals_equal']
            records.append(record)
        assert set(closure.changes)=={(k,None) for k in KEYS}
        after=story.reassemble(before,closure.changes)
    target=output/'bakedabilitydata';target.write_bytes(after)
    source=WORK/'failure-20261015-190524/level-1-16.lua'
    raw=source.read_bytes()
    anchor=b'\tsupporter_id = LevelDesign:CreateTrialAdhocAvatar(48,"AvatarSupporterBehavior_Claymore_BZ","Spawn06")'
    assert raw.count(anchor)==1
    # UInt32 is not pushed by the stock1.9 Lua binding on the established x86
    # path. Accept a real numeric return on ARM if available; otherwise match
    # the actual trial48 level75, never the highest level of the player team.
    replacement='''\tlocal created_id = LevelDesign:CreateTrialAdhocAvatar(48,"AvatarSupporterBehavior_Claymore_BZ","Spawn06")
\tif type(created_id) == "number" and created_id > 0 then
\t\tsupporter_id = created_id
\telse
\t\tlocal found, matches, seen, echoes = 0, 0, 0, 0
\t\tfor id = 1, 600 do
\t\t\tlocal ok, lv = pcall(function() return LevelDesign:GetAvatarLevel(id) end)
\t\t\tif ok and type(lv) == "number" then
\t\t\t\tseen = seen + 1
\t\t\t\tif lv == id then echoes = echoes + 1 end
\t\t\t\tif lv == 75 then found, matches = id, matches + 1 end
\t\t\tend
\t\tend
\t\tassert(seen > 0 and echoes * 10 < seen,
\t\t\t"Trial48: GetAvatarLevel binding did not return real levels")
\t\tassert(matches == 1,
\t\t\t"Trial48: expected exactly one level75 story supporter")
\t\tsupporter_id = found
\tend'''.encode('utf-8')
    projected=raw.replace(anchor,replacement)
    assert projected.split(replacement)==raw.split(anchor)
    signatures=lua.method_signatures()
    for call in lua.calls(projected.decode('utf-8-sig')):
        assert any(r['minimum_args']<=call['static_argument_count']<=r['maximum_args'] for r in signatures.get(call['method'],[])),call
    (output/'level-1-16.lua').write_bytes(projected)
    receipt={'status':'prepared_not_deployed','ability_keys':list(KEYS),'changed_effect_tag_bytes':5,
        'source_ability_sha256':hashlib.sha256(before).hexdigest(),
        'output_ability_sha256':hashlib.sha256(after).hexdigest(),
        'source_lua_sha256':hashlib.sha256(raw).hexdigest(),
        'output_lua_sha256':hashlib.sha256(projected).hexdigest(),
        'effect_records':records,'native_library_changed':False,'save_changed':False,
        'human_acceptance':'pending','trial48_level':75,'player_team_level':80,
        'lua_policy':'Use real numeric return or unique exact level75; ambiguity errors explicitly, no player-avatar substitution',
        'limits':'ARM runtime return behavior and actual stage win remain human-unverified'}
    (output/'manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


if __name__=='__main__':
    result=prepare()
    print(json.dumps({k:result[k] for k in ('status','changed_effect_tag_bytes','trial48_level','save_changed')}))
