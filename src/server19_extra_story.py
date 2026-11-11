"""Opt-in native Xuanyuan test catalog; unlock availability without fake clears."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import server19_stage as stage

_CONFIG=None

def configure(directory):
    global _CONFIG
    directory=Path(directory);ready=json.loads((directory/'runtime-ready.json').read_bytes())
    if ready.get('build_proof'):
        from server19_build_capabilities import require
        require('extra_story', ready)
    elif not ready.get('deployed') or ready.get('device')!='REFERENCE_DEVICE':raise ValueError('Xuanyuan resources require verified Phone2 deployment')
    for name,digest in ready['table_sha256'].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:raise ValueError('Extra table changed: '+name)
    rows=json.loads((directory/'stagedata_main').read_bytes());ids=set(ready['stage_ids']);selected={r['levelId']:r for r in rows if r['levelId'] in ids}
    assert len(selected)==len(ids) and all(r['type']==7 and r['difficulty']==1 and all(p == 0 or p in ids for p in r['preLevelID']) for r in selected.values())
    original_config,original_ids=stage.stage_config,stage.supported_stage_ids
    stage.stage_config=lambda identity=stage.STAGE_ID:deepcopy(selected[identity]) if identity in selected else original_config(identity)
    stage.supported_stage_ids=lambda:tuple(sorted(set(original_ids())|ids))
    for identity, avatars in ready.get('prescribed_trial_rosters', {}).items():
        identity = int(identity)
        assert identity in ids and avatars and all(type(a) is int and a > 0 for a in avatars)
        stage.STORY_TRIAL_AVATARS[identity] = tuple(avatars)
    stage.TABLE_OVERRIDES['stagedata_main']=directory/'stagedata_main'
    _CONFIG=dict(directory=directory,ids=ids,chapters=json.loads((directory/'extrastorychapter').read_bytes()),areas=json.loads((directory/'extrastoryarea').read_bytes()),acts=json.loads((directory/'extrastoryact').read_bytes()),groups=json.loads((directory/'extrastoryachievegroup').read_bytes()))
    # Every map zone needs a runtime area object, even with no available acts.
    # Native ExtraStoryAreaDataItem.IsUnlock returns false for an empty act list.
    if (directory/'extra-achievement-catalog.json').is_file():
        import server19_extra_achievements
        server19_extra_achievements.configure(directory)
    for row in selected.values():
        stage.first_clear_drop_plan(row)
        for challenge in row['challengeList']:stage._reward(challenge['rewardId'])
    return sorted(ids)


def achievement_snapshot(account, chapter_id=None):
    """Close zero-bonus groups only after every individual reward was taken.

    Native MissionModule70072 checks the group flag even for rewardID0.
    Closure derives only from individual receipts. Old marker-only group
    acknowledgements cannot hide rewards that have not actually been taken.
    Groups with real bonus rewards must not be marked taken by this rule.
    """
    if _CONFIG is None:
        return None
    from server19_extra_achievements import CATALOG
    runtime = account.get('extra_achievement_runtime', {})
    claimed = set(runtime.get('claimed_ids', []))
    rows = []
    for group in _CONFIG['groups']:
        if group['rewardID'] != 0 or chapter_id not in (None, 0, group['chapterID']):
            continue
        members = {mid for mid, row in CATALOG.items() if row['group_id'] == group['groupID']}
        if members:
            rows.append(dict(achieve_id=group['groupID'], is_take=members <= claimed))
    return 'GetExtraStoryAchieveDataRsp', dict(retcode=0, achieve_list=rows)

def claim_group_rewards(account, group_id, account_path=None):
    """Claim every outstanding individual reward in the completed group atomically."""
    from server19_extra_achievements import CATALOG, mission_rows, claim
    from server19_missions import _Rejected
    group = next((r for r in _CONFIG['groups'] if r['groupID'] == group_id), None)
    denied = dict(retcode=1, achieve_id=group_id)
    if group is None or group['rewardID'] != 0:
        return denied
    members = {mid for mid, row in CATALOG.items() if row['group_id'] == group_id}
    reward = dict(exp=0, scoin=0, hcoin=0, stamina=0, skill_point=0,
                  friends_point=0, duty_point=0, item_list=[])
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        statuses = {r['mission_id']: r['status'] for r in mission_rows(before)}
        if not members or any(statuses.get(mid) not in (3, 5) for mid in members):
            return denied
        current = deepcopy(before)
        items = {}
        try:
            for mid in sorted(members):
                if statuses[mid] == 5:
                    continue
                response = claim(current, mid)
                if response['retcode'] != 0:
                    return denied
                for individual in response['reward_list']:
                    for key in reward:
                        if key != 'item_list':
                            reward[key] += individual.get(key, 0)
                    for item in individual.get('item_list', []):
                        key = (item['id'], item['level'])
                        items[key] = items.get(key, 0) + item['num']
        except (_Rejected, ValueError):
            return denied
        reward['item_list'] = [dict(id=i, level=l, num=n) for (i, l), n in sorted(items.items())]
        if current != before:
            stage._save(path, before, current)
        stage._sync(account, current)
    # The first RewardData is the native dialog's complete displayed total.
    return dict(retcode=0, achieve_id=group_id, reward_list=[reward])


def response(name,account,values=None,*,account_path=None):
    if _CONFIG is None:return None
    c=_CONFIG;values=values or {};begin,end=1,1893456000
    if name=='SwitchDynamicHardLvReq':
        path=Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
        with stage._transaction_lock(path):
            before=stage._read(path,account);current=deepcopy(before)
            settings=current.setdefault('extra_story_settings',{})
            settings['is_dynamic_hard_lv']=not settings.get('is_dynamic_hard_lv',False)
            stage._save(path,before,current);stage._sync(account,current)
        return 'SwitchDynamicHardLvRsp',dict(retcode=0,is_dynamic_hard_lv=settings['is_dynamic_hard_lv'])
    def act(row):return dict(act_id=row['actId'],begin_time=begin,end_time=end)
    if name=='GetExtraStoryDataReq':
        chapters=[]
        for chapter in c['chapters']:
            areas=[]
            for area in c['areas']:
                if area['chapterId']!=chapter['chapterId']:continue
                acts=[act(r) for r in c['acts'] if r['areaId']==area['areaId']]
                areas.append(dict(area_id=area['areaId'],act_list=acts,begin_time=begin,end_time=end))
            chapters.append(dict(chapter_id=chapter['chapterId'],min_player_level=chapter['minPlayerLevel'],area_list=areas,begin_time=begin,end_time=end,is_need_key=False))
        return 'GetExtraStoryDataRsp',dict(retcode=0,chapter_list=chapters,is_dynamic_hard_lv=bool(account.get('extra_story_settings',{}).get('is_dynamic_hard_lv',False)),chapter_key_list=[])
    if name=='GetExtraStoryActivityActReq':
        ids={r['areaId'] for r in c['areas'] if r['chapterId']==values.get('chapter_id')}
        return 'GetExtraStoryActivityActRsp',dict(retcode=0,act_list=[act(r) for r in c['acts'] if r['areaId'] in ids])
    if name=='GetExtraStoryAchieveDataReq':
        return achievement_snapshot(account, values.get('chapter_id'))
    if name=='GetExtraStoryAchieveRewardReq':
        return 'GetExtraStoryAchieveRewardRsp', claim_group_rewards(account, values.get('achieve_id', 0), account_path)
    if name=='GetStageDropDisplayReq':
        requested=values.get('stage_id_list',[])
        if requested and any(i in c['ids'] for i in requested):
            if not all(i in stage.supported_stage_ids() for i in requested):return 'GetStageDropDisplayRsp',{'retcode':1}
            from server19_stage_display import _record
            return 'GetStageDropDisplayRsp',dict(retcode=0,stage_drop_list=[_record(stage.stage_config(i)) for i in dict.fromkeys(requested)])
    return None
