"""Prepare six Kallen story entries; retain authored short-story association."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,hashlib
from pathlib import Path
from server19_extra_story_prepare import ROOT,TABLES
from server19_story_trial_policy import prescribed_rosters
OUT=ROOT/'server19-run/kallen-20261025'
BASE=ROOT/'server19-run/theresa-20261025/progress-fixed-delivery'
def read(p):return json.loads(Path(p).read_bytes())
def prepare(folder=None):
    folder=Path(folder or OUT/'all-open-delivery');folder.mkdir(exist_ok=True)
    if (folder/'runtime-ready.json').exists() and read(folder/'runtime-ready.json').get('deployed'):raise ValueError('Do not overwrite deployed catalog')
    ids=set(range(217101,217107));manifest=read(OUT/'candidate-v4/manifest.json')
    assert set(manifest['ready_stage_ids'])==ids and not manifest['blocked_stage_ids']
    old=read(BASE/'runtime-ready.json');data={n:read(BASE/n) for n in old['table_sha256']}
    source=lambda n:read(TABLES/n)
    for row in data['stagedata_main']:
        if row['levelId'] in ids:row.update(preLevelID=[0],unlockStarNum=0)
    # Preserve the registered challenge metadata, but grant no challenge acts.
    for n in ['extrastorychapter','extrastoryarea']:
        rows=[r for r in source(n) if r['chapterId'] in (7,8)]
        for r in rows:r.update(beginTime='2020-01-01 00:00:00',endTime='2030-01-01 00:00:00')
        data[n].extend(rows)
    acts=[r for r in source('extrastoryact') if r['areaId']==701]
    assert {i for r in acts for i in r['stageIdList']}==ids
    data['extrastoryact'].extend(acts)
    for n,rows in data.items():(folder/n).write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    trials=[r for r in source('leveltrialdata') if r['stageID'] in ids]
    assert len(trials)==6 and all(r['allowedPlayerAvatar']==0 and r['avatarList']==[1156] for r in trials)
    rosters=dict(old.get('prescribed_trial_rosters',{}));rosters.update(prescribed_rosters(trials,source('avatartrialdata'),ids))
    ready=dict(old,deployed=False,stage_ids=sorted(set(old['stage_ids'])|ids),human_acceptance='pending',
        prescribed_trial_rosters=rosters,test_unlock='User-approved six Kallen story prerequisites removed; no save or clear grants',
        table_sha256={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in data},
        catalog_area_ids=sorted({r['areaId'] for r in data['extrastoryarea']}),areas_with_available_acts=sorted({r['areaId'] for r in data['extrastoryact']}))
    ready.pop('deployment_receipt',None)
    ready['kallen_boundary']={'story_only':True,'challenge_chapter':8,'challenge_acts_open':False,'new_achievements':'no authenticated chapter achievement mapping; retain existing52','short_story_registration':102}
    (folder/'runtime-ready.json').write_text(json.dumps(ready,ensure_ascii=False,indent=2),encoding='utf-8');return ready
if __name__=='__main__':print(json.dumps(prepare()['kallen_boundary']))
