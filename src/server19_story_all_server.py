"""Opt-in deployed Normal-story catalog; no automatic wins or unlock flags."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import server19_stage as stage
import server19_avatar_cultivation as cultivation
import server19_avatar_skills as skills
import server19_player_progression as progression
import server19_equipment as equipment

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'.local-baseline/server19-dev/story-all-20261015'
READY=WORK/'runtime-ready.json'
_configured=False


def validate_capabilities(ready):
    """Reject a resource/native mismatch before exposing any new stages."""
    if ready.get('build_proof'):
        from server19_build_capabilities import require
        require('story', ready)
        return
    required = set(ready.get('required_native_capabilities', []))
    if ready.get('native_shield_cap_bridge_required'):
        required.add('shield_cap_v1')
    delivered = set(ready.get('deployed_native_capabilities', []))
    if required - delivered:
        raise ValueError('Story native capabilities not delivered: ' + ', '.join(sorted(required-delivered)))
    if required:
        receipt = ready.get('native_library_delivery', {})
        digest = receipt.get('sha256', '')
        if (receipt.get('device') != ready.get('device') or receipt.get('readback_verified') is not True
                or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('Story native capability delivery lacks device readback evidence')


def configure(*, require_deployed=True):
    global _configured
    if _configured:raise ValueError('Story instance already configured')
    ready=json.loads(READY.read_bytes())
    if require_deployed and not ready.get('build_proof') and (ready.get('device')!='REFERENCE_DEVICE' or ready.get('deployed') is not True):
        raise ValueError('Story resources must be delivered first')
    validate_capabilities(ready)
    ids=ready['ready_stage_ids']
    for name in ('materialdata','textmap'):
        stage.TABLE_OVERRIDES[name]=WORK/'metadata'/name
    rows=stage._table('stagedata_main')
    canon={r['levelId']:r for r in rows}
    selected=[r for r in rows if r['levelId'] in ids]
    raw=json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    if len(selected)!=len(set(ids)) or hashlib.sha256(raw).hexdigest()!=ready['source_rows_sha256']:
        raise ValueError('Selected story source rows changed')
    for row in selected:
        if (row['type'],row['difficulty'],row['maxProgress'])!=(1,1,1) or row['battleType'] not in (1,2,3,101) or row['chapterId'] not in range(2,7):
            raise ValueError('Unexpected source story category')
        for challenge in row['challengeList']:stage._reward(challenge['rewardId'])
        stage.first_clear_drop_plan(row)
    old_config=stage.stage_config
    old_supported=stage.supported_stage_ids
    base_ids=frozenset(stage.STORY_CATALOG_STAGE_IDS)
    def config(identity=stage.STAGE_ID):
        if identity in base_ids:return old_config(identity)
        if identity not in ids:raise ValueError('Story dependencies unresolved for stage '+str(identity))
        return deepcopy(canon[identity])
    def supported():
        return tuple(sorted(set(old_supported())|set(ids)))
    stage.stage_config=config
    stage.supported_stage_ids=supported
    stage.STORY_CATALOG_STAGE_IDS=tuple(sorted(base_ids|set(ids)))
    # Bind fixture transactions to the already selected actual local tables.
    for module,attr in ((skills,'_TABLE_HASHES'),(cultivation,'_TABLE_HASHES'),(equipment,'_POWER_UP_TABLE_HASHES')):
        hashes=getattr(module,attr)
        for name in hashes:
            path=Path(stage.TABLE_OVERRIDES.get(name,stage.TABLE_DIRECTORY/name))
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    import server19_story_mission_extension as mission_extension
    import server19_account_maintenance as maintenance
    if ready.get('mission_source_sha256'):
        stage.STORY_MISSION_SOURCE_SHA256 = ready['mission_source_sha256']
    stage.STORY_MISSION_DIGEST_SCHEMA = ready.get('mission_digest_schema', 1)
    mission_extension.configure()
    stage.ACCOUNT_MAINTENANCE=maintenance.normalize
    progression.CAP_EXP_TO_SCOIN=True
    _configured=True
    return {'ready_stage_ids':ids,'automatic_completion':False,'cap_exp_policy':'1exp=1scoin'}
