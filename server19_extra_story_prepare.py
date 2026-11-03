"""Prepare the explicit Phone2 Xuanyuan batch; no device or account writes."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'server19-run/xuanyuan-20261025'
TABLES=ROOT/'.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'

def prepare(version="candidate-v4", folder=None):
    report=json.loads((OUT/version/'manifest.json').read_bytes());ids=set(report['ready_stage_ids']);assert len(ids)==21 and 210117 in ids
    folder=Path(folder or OUT/'followup/delivery');folder.mkdir(parents=True,exist_ok=True)
    def save(name,value):
        (folder/name).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    rows=json.loads((TABLES/'stagedata_main').read_bytes())
    for row in rows:
        if row['levelId'] in ids:
            row.update(preLevelID=[0],unlockStarNum=0)
            if 210117 <= row['levelId'] <= 210121:
                for item in row['firstDisplayDropList']:
                    if item['num']==0:item['num']=1
    save('stagedata_main',rows)
    chapters=[r for r in json.loads((TABLES/'extrastorychapter').read_bytes()) if r['chapterId']==1]
    areas=[r for r in json.loads((TABLES/'extrastoryarea').read_bytes()) if r['chapterId']==1]
    for row in chapters+areas:row.update(beginTime='2020-01-01 00:00:00',endTime='2030-01-01 00:00:00')
    acts=[]
    for row in json.loads((TABLES/'extrastoryact').read_bytes()):
        selected=[i for i in row['stageIdList'] if i in ids]
        if selected:row['stageIdList']=selected;acts.append(row)
    for name,rows in [('extrastorychapter',chapters),('extrastoryarea',areas),('extrastoryact',acts)]:save(name,rows)
    (folder/'plotavatardata').write_bytes((OUT/'metadata/plotavatardata').read_bytes())
    names=['stagedata_main','extrastorychapter','extrastoryarea','extrastoryact','plotavatardata']
    # The old mission/reward records survive, but later exports omit their links.
    missions=json.loads((TABLES/'missiondata').read_bytes())
    linear=json.loads((TABLES/'linearmissiondata').read_bytes())
    rewards={r['RewardID']:r for r in json.loads((TABLES/'rewarddata').read_bytes())}
    from server19_achievement import _parse_reward
    links=[];catalog=[];groups=[]
    for area in (101,102,103,104):
        group=area*100+1
        groups.append(dict(groupID=group,rewardID=0,groupType=1,areaID=area,difficulty=1,chapterID=1))
        stage_ids={i for a in acts if a['areaId']==area for i in a['stageIdList']}
        for index,m in enumerate(r for r in missions if r['id']>=60000 and r['finishWay']==5 and r['finishParaInt'] in stage_ids):
            links.append(dict(missionId=m['id'],groupId=group,achieveLocation=index))
            assert not any(r['MissionID']==m['id'] for r in linear)
            linear.append(dict(MissionID=m['id'],PreMissionId=0,MinLevel=20,IsAchievement=1))
            catalog.append(dict(mission_id=m['id'],stage_id=m['finishParaInt'],group_id=group,reward=_parse_reward(rewards[m['rewardId']])))
    assert len(catalog)==21
    displays=[r for r in json.loads((TABLES/'extrastoryachievedisplay').read_bytes()) if r['chapterID']==1 and r['type']==1]
    for r in displays:r['groupIDList']=[r['areaID']*100+1]
    # No group-bonus values survive: a zero reward row prevents null metadata.
    # Individual original mission rewards remain claimable; no invented group payout.
    rewards[0]={k:0 for k in next(iter(rewards.values()))}
    for name,value in [('extrastoryachieve',links),('extrastoryachievegroup',groups),('extrastoryachievedisplay',displays),('linearmissiondata',linear),('rewarddata',list(rewards.values())),('extra-achievement-catalog.json',catalog)]:
        save(name,value);names.append(name)
    ready=dict(deployed=False,device='REFERENCE_DEVICE',stage_ids=sorted(ids),table_sha256={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in names},test_unlock='Only prerequisites for selected21 stages removed, no save or completion grants',human_acceptance='pending',blocked_stage_ids=[],unavailable_voice_events=json.loads((OUT/'voice/unavailable-events.json').read_bytes()))
    save('runtime-ready.json',ready)
    return ready
if __name__=='__main__':print(json.dumps(prepare()))
