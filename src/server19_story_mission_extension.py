"""Source-driven main/side mission graph, gated by delivered story resources."""
from copy import deepcopy
import hashlib
import json
import server19_stage as stage
import server19_missions as missions
import server19_duty as duty


def preview(available, *, digest_schema=1):
    """Build the source graph without changing the active mission catalog."""
    available = set(available)
    source = {r['id']: r for r in stage._table('missiondata')}
    linear = {r['MissionID']: r for r in stage._table('linearmissiondata')}
    catalog = missions.mission_catalog()
    pending = {i: r for i, r in source.items() if i not in catalog
               and r.get('type') == 1 and r.get('finishWay') == 180
               and r.get('finishParaInt') in available and i in linear}
    added = {}
    while pending:
        selected = [i for i in pending if linear[i]['PreMissionId'] in catalog]
        if not selected:
            break
        for identity in sorted(selected):
            row = pending.pop(identity)
            condition = linear[identity]
            sid = row['finishParaInt']
            if (row['totalProgress'] != 1 or row['isAutoReward']
                    or row['finishParaStr'] or row['LinkType'] != 1
                    or row['LinkParam'] != sid or row['LinkParams'] != [sid]
                    or condition['IsAchievement'] != 0):
                raise ValueError('Unsupported extended story condition')
            reward = duty._reward_of(row['rewardId'])
            reward.pop('_items')
            item = {'mission_id': identity, 'stage_id': sid,
                    'predecessor': condition['PreMissionId'],
                    'min_level': condition['MinLevel'], 'reward': reward}
            added[identity] = catalog[identity] = item
    # Bind complete reviewed source rows, including links, rewards and branches.
    if digest_schema not in (1, 2):
        raise ValueError('Unsupported mission source digest schema')
    reward_ids = {source[i]['rewardId'] for i in added}
    source_rows = {name: [r for r in stage._table(name)
                         if r[field] in (reward_ids if name == 'rewarddata' and digest_schema == 2 else added)]
                   for name, field in (('missiondata','id'), ('linearmissiondata','MissionID'), ('rewarddata','RewardID'))}
    digest = hashlib.sha256(json.dumps(source_rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'catalog': added, 'unavailable_prerequisites': sorted(pending),
            'source_sha256': digest, 'digest_schema': digest_schema}


def configure():
    if missions.EXTENDED_CATALOG:
        raise ValueError('Mission extension already configured')
    plan = preview(stage.supported_stage_ids(), digest_schema=getattr(stage, 'STORY_MISSION_DIGEST_SCHEMA', 1))
    added = plan['catalog']
    digest = plan['source_sha256']
    expected = getattr(stage, 'STORY_MISSION_SOURCE_SHA256',
                       'c8d2cc07f7ebbd7c18c1ea39f8954d022ce85d160024ac3b8c4102c7597e6688')
    if digest != expected:
        raise ValueError('Extended story source changed; review the new batch first')
    missions.EXTENDED_CATALOG = deepcopy(added)
    missions.SUPPORTED_MISSION_IDS = missions.BASE_MISSION_IDS + tuple(added)
    return {'added': list(added), 'unavailable_prerequisites': plan['unavailable_prerequisites']}
