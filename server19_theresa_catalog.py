"""Prepare additive Theresa metadata; never deploy or write a player account."""

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
from server19_extra_story_prepare import ROOT, TABLES
from server19_achievement import _parse_reward
OUT = ROOT / 'server19-run/theresa-20261025'
BASE = ROOT / 'server19-run/chiyou-20261025/all-open-delivery'

def read(path):
    return json.loads(path.read_bytes())

def prepare(folder=None, *, unlock_for_testing=False):
    manifest = read(OUT / 'candidate-v4/manifest.json')
    ids = {r['stage_id'] for r in read(OUT / 'inventory.json')}
    assert set(manifest['ready_stage_ids']) == ids and not manifest['blocked_stage_ids']
    folder = Path(folder or OUT / 'delivery')
    if (folder / 'runtime-ready.json').exists() and read(folder / 'runtime-ready.json').get('deployed'):
        raise ValueError('Prepare in a new candidate directory; do not overwrite a deployed catalog')
    folder.mkdir(exist_ok=True)
    old = read(BASE / 'runtime-ready.json')
    data = {n: read(BASE / n) for n in old['table_sha256']}
    def source(name): return read(TABLES / name)
    # Preserve original prerequisites and all previously delivered chapter edits.
    assert [r for r in data['stagedata_main'] if r['levelId'] in ids] == [r for r in source('stagedata_main') if r['levelId'] in ids]
    if unlock_for_testing:
        for row in data['stagedata_main']:
            if row['levelId'] in ids:
                row.update(preLevelID=[0], unlockStarNum=0)
    acts = []
    for row in source('extrastoryact'):
        selected = [sid for sid in row['stageIdList'] if sid in ids]
        if selected:
            acts.append(dict(row, stageIdList=selected))
    areas = {r['areaId'] for r in acts}
    # Keep all chapter area metadata for original map initialization.
    # Keep its metadata; availability is independently scoped to selected acts.
    for name, rows in [('extrastorychapter', [r for r in source('extrastorychapter') if r['chapterId'] == 4]), ('extrastoryarea', [r for r in source('extrastoryarea') if r['chapterId'] == 4])]:
        for row in rows:
            row.update(beginTime='2020-01-01 00:00:00', endTime='2030-01-01 00:00:00')
        data[name].extend(rows)
    data['extrastoryact'].extend(acts)
    rewards = {r['RewardID']: r for r in source('rewarddata')}
    missions = [r for r in source('missiondata') if 60000 <= r['id'] < 70000 and r['finishWay'] == 5 and r['finishParaInt'] in ids]
    assert len(missions) == 16
    for area in sorted(areas):
        group = area * 100 + 1
        data['extrastoryachievegroup'].append(dict(groupID=group, rewardID=0, groupType=1, areaID=area, difficulty=1, chapterID=4))
        stages = {sid for a in acts if a['areaId'] == area for sid in a['stageIdList']}
        for index, mission in enumerate(m for m in missions if m['finishParaInt'] in stages):
            mid = mission['id']
            assert not any(r['MissionID'] == mid for r in data['linearmissiondata'])
            data['linearmissiondata'].append(dict(MissionID=mid, PreMissionId=0, MinLevel=20, IsAchievement=1))
            data['extrastoryachieve'].append(dict(missionId=mid, groupId=group, achieveLocation=index))
            data['extra-achievement-catalog.json'].append(dict(mission_id=mid, stage_id=mission['finishParaInt'], group_id=group, reward=_parse_reward(rewards[mission['rewardId']])))
    for row in source('extrastoryachievedisplay'):
        if row['chapterID'] == 4 and row['areaID'] in areas:
            groups = [g for g in row['groupIDList'] if g in {a * 100 + 1 for a in areas}]
            if groups:
                data['extrastoryachievedisplay'].append(dict(row, groupIDList=groups))
    for name, rows in data.items():
        (folder / name).write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    ready = dict(old, deployed=False, stage_ids=sorted(set(old['stage_ids']) | ids), human_acceptance='pending', test_unlock='Existing chapters unchanged; original Theresa sequential prerequisites retained', table_sha256={n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in data}, missing_clear_achievement_stage_ids=old.get('missing_clear_achievement_stage_ids', []), group_bonus='source configuration unavailable; no invented payout')
    ready.pop('deployment_receipt', None)
    if unlock_for_testing:
        ready['test_unlock'] = 'User-approved Theresa16 prerequisite removal for sampling; no save, clear or reward grants'
    ready['catalog_area_ids'] = sorted({r['areaId'] for r in data['extrastoryarea']})
    ready['areas_with_available_acts'] = sorted({r['areaId'] for r in data['extrastoryact']})
    ready['unavailable_voice_events'] = old['unavailable_voice_events']
    from server19_story_trial_policy import prescribed_rosters
    trial_rows = [r for r in source('leveltrialdata') if r['stageID'] in ids]
    assert all(r['allowedPlayerAvatar'] == 0 and not r['fakeAvatarID'] for r in trial_rows)
    ready['prescribed_trial_rosters'] = prescribed_rosters(trial_rows, source('avatartrialdata'), ids)
    (folder / 'runtime-ready.json').write_text(json.dumps(ready, ensure_ascii=False, indent=2), encoding='utf8')
    return ready

if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
