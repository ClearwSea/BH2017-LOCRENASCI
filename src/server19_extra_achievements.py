"""Xuanyuan original clear missions, using confirmed settlements and atomic claims."""
from copy import deepcopy
import json
import time
from pathlib import Path
import server19_stage as stage

CATALOG = {}


def configure(directory):
    global CATALOG
    rows = json.loads((Path(directory) / 'extra-achievement-catalog.json').read_bytes())
    catalog = {r['mission_id']: r for r in rows}
    ready = json.loads((Path(directory) / 'runtime-ready.json').read_bytes())
    assert catalog and len(catalog) == len(rows)
    assert all(r['stage_id'] in ready['stage_ids'] for r in rows)
    CATALOG = catalog


def mission_rows(account):
    if not CATALOG:
        return []
    from server19_missions import _confirmed_wins
    won = _confirmed_wins(account)
    claimed = account.get('extra_achievement_runtime', {}).get('claimed_ids', [])
    return [dict(mission_id=mid, status=5 if mid in claimed else 3 if r['stage_id'] in won else 2,
                 progress=int(r['stage_id'] in won)) for mid, r in CATALOG.items()]


def claim(account, mission_id):
    if mission_id not in CATALOG:
        return None
    from server19_missions import _confirmed_wins, _preflight
    row = CATALOG[mission_id]
    runtime = account.setdefault('extra_achievement_runtime', dict(claimed_ids=[], receipts=[]))
    if mission_id in runtime['claimed_ids'] or row['stage_id'] not in _confirmed_wins(account):
        return {'retcode': 3}
    reward = row['reward']
    _preflight(account, reward)
    # These pinned original rewards contain coins and inventory only.
    assert not any(reward[k] for k in ('exp','hcoin','stamina','skill_point','friends_point','duty_point'))
    account['main']['scoin'] = stage._u32(account['main'].get('scoin', 0) + reward['scoin'], 'Extra achievement coins')
    stage._grant_drops(account, {(i['id'], i['level']): i['num'] for i in reward['item_list']})
    response = dict(retcode=0, reward_list=[deepcopy(reward)])
    runtime['claimed_ids'].append(mission_id)
    runtime['receipts'].append(dict(mission_id=mission_id,stage_id=row['stage_id'],response=deepcopy(response),claimed_at=time.time()))
    return response
