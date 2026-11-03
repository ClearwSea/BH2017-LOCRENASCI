"""Original area locks plus the explicitly approved commission-period reset."""
from copy import deepcopy
from server19_commissions import calendar


def state(account, catalog, now):
    runtime = account['openworld_runtime']
    if not catalog.get('fourth_cycle'):
        return []
    period = calendar(now)[1]
    if runtime.get('area_period') != period:
        runtime.update(area_period=period, area_teams=[])
    return runtime.setdefault('area_teams', [])


def enter(account, catalog, area_id, ids, now):
    areas = {r['areaId']: r for r in catalog['areas']}
    area = areas.get(area_id)
    finished = account['openworld_data']['finish_story_id_list']
    if area is None or (area['unlockStoryId'] and area['unlockStoryId'] not in finished):
        return False
    teams = state(account, catalog, now)
    # Before multiAreaStoryId the native client permits the story team.
    if area['multiAreaStoryId'] not in finished:
        return True
    avatars = [r for r in account['avatar_list'] if r['avatar_id'] in ids]
    weapons = [r['weapon_unique_id'] for r in avatars if r.get('weapon_unique_id')]
    stigmata = [r[key] for r in avatars for key in ('stigmata_unique_id_1', 'stigmata_unique_id_2', 'stigmata_unique_id_3') if r.get(key)]
    row = dict(area_id=area_id, avatar_list=list(ids), weapon_uid_list=weapons, stigmata_uid_list=stigmata)
    for other in teams:
        if other['area_id'] == area_id:
            continue
        if any(set(row[key]) & set(other[key]) for key in ('avatar_list', 'weapon_uid_list', 'stigmata_uid_list')):
            return False
    runtime = account['openworld_runtime']
    runtime['area_teams'] = [r for r in teams if r['area_id'] != area_id] + [deepcopy(row)]
    return True
