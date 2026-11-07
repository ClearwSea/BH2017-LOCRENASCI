"""Assemble a coherent offline story delivery plan without device/save writes."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import hashlib
import json
import re

from server19_story_all_resources import ROOT, WORK

OUT = WORK/'goal-six-chapters-20261016'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024*1024): h.update(block)
    return h.hexdigest()


def prepare(*, six_chapters=False):
    import server19_stage as stage
    import server19_story_mission_extension as missions
    folder = OUT/('delivery-six-chapters-v1' if six_chapters else 'delivery-through-chapter4-v1')
    folder.mkdir(exist_ok=False)
    manifests = [json.loads((OUT/name/'manifest.json').read_bytes())
                 for name in (('chapters5-6-closed-v1','final-all6-resources-v1') if six_chapters else ('chapter2-cap-v2', 'chapters3-4-cap-v3'))]
    assert all(not m['blocked_stage_ids'] for m in manifests)
    selected, ids, scripts = {}, set(), []
    for manifest in manifests:
        ids.update(manifest['ready_stage_ids'])
        records = manifest['files'] + [s['file'] for s in manifest['stages']]
        records += [m['file'] for m in manifest['modules']]
        for rec in records:
            local = Path(rec['local_absolute_path'])
            assert local.is_relative_to(OUT) and digest(local) == rec['sha256']
            prefix = ('/sdcard/bh3-server19-baked/' if rec['path'].startswith('_baked/')
                      else '/sdcard/bh3-server19-metadata/' if rec['path'].startswith('_exceloutputasset/')
                      else '/sdcard/bh3-server19-resources/')
            selected[rec['path']] = {**rec, 'remote': prefix+rec['path']}
        scripts.extend(Path(s['file']['local_absolute_path']).read_text(encoding='utf-8-sig')
                       for s in manifest['stages'])
    # This is the same source-table environment as the live wrapper, without
    # importing the wrapper, opening sockets or loading/mutating the account.
    stage.STORY_RUNTIME_READY_FILE = ROOT/'.local-baseline/server19-dev/chapter1-remaining-ready/runtime-ready.json'
    chapter = ROOT/'.local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset'
    stage.TABLE_OVERRIDES = {n:chapter/n for n in ('materialdata','avatarfragmentdata','constvaluesclient','textmap')}
    for name in ('materialdata','textmap'):stage.TABLE_OVERRIDES[name] = WORK/'metadata'/name
    available = ids | set(stage.supported_stage_ids())
    plan = missions.preview(available, digest_schema=2)
    rows = [r for r in stage._table('stagedata_main') if r['levelId'] in ids]
    assert len(rows) == len(ids)
    for row in rows:
        stage.first_clear_drop_plan(row)
        for challenge in row['challengeList']: stage._reward(challenge['rewardId'])
    ready = {'schema':2,'device':'REFERENCE_DEVICE','deployed':False,
             'ready_stage_ids':sorted(ids),'source_rows_sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
             'mission_source_sha256':plan['source_sha256'],'mission_digest_schema':2,
             'native_shield_cap_bridge_required':True,'required_native_capabilities':['shield_cap_v1']+(['weekly_voice_v1','lock_acceleration_v1'] if six_chapters else []),
             'deployed_native_capabilities':[], 'human_acceptance':'pending',
             'voice_bank_path':str(OUT/('voice-through-chapter6' if six_chapters else 'voice-through-chapter4')/'server19_story_voice.bnk')}
    prerequisites={r['levelId']:r['preLevelID'] for r in rows}
    assert all(p in available for values in prerequisites.values() for p in values if p), 'A stage prerequisite remains outside the resource-ready catalog'
    # Select original automatic and explicit Lua CG references, not the entire
    # media catalog. Built-in videos remain in the APK.
    cgrows = stage._table('cgdata')
    cgids = {int(i) for text in scripts for i in re.findall(r'\bvideoId\s*=\s*(\d+)',text)}
    cgids.update(r['CgID'] for r in cgrows if r['levelID'] in ids or any(
        r['levelIDBegin'] and r['levelIDBegin'] <= i <= r['levelIDEnd'] for i in ids))
    found = {r['CgID']:r for r in cgrows}
    assert not cgids-set(found), 'Unresolved CG metadata'
    media = json.loads((ROOT/'.local-baseline/server19-dev/cg-media/prepared-cg-icons-corrected/manifest.json').read_bytes())
    names = {found[i]['CgPath']+'.mp4' for i in cgids}
    videos = [r for r in media['resources'] if r['filename'] in names]
    assert {r['filename'] for r in videos} == names
    for rec in videos:
        if not rec['deploy_external']: continue
        path = ROOT/rec['prepared_path']
        assert path.stat().st_size == rec['size'] and digest(path) == rec['sha256']
        assert rec['decode']['full_decode_through_eof']
    result = {'status':'offline_candidate_device_acceptance_pending',
              'stage_count':len(ids),'total_normal_stage_count':len(available),'missions':len(plan['catalog']),
              'stage_prerequisites':prerequisites,'no_prerequisite_bypass':True,
              'files':list(selected.values()),'cg_ids':sorted(cgids),'cg_files':videos,
              'native_library':str(OUT/('native-lock-acceleration-v2' if six_chapters else 'native-shield-cap-v1')/'libil2cpp.so'),
              'voice_candidates':{'embedded':ready['voice_bank_path'],
                  'streaming':str(OUT/('voice-streaming-through-chapter6' if six_chapters else 'voice-streaming-through-chapter4')/'manifest.json'),
                  'streaming_native_IO':'pending'},
              'account_changes':False,'deployment_performed':False,
              'limits':['Two source camera points retain original random-point fallback; precise later framing unavailable.',
                        'Managed bridge calls and external voice streaming require human device acceptance.',
                        'Two Boss050 TriggerAbility event names have no global config in supplied2.4; original event actions retained, event-handler coverage unproven.',
                        'Later6005/6006 buff-panel registration is unavailable in original1.9; combat modifier actions/values retained.']}
    if six_chapters:
        result['required_existing_avatar_sha256']=manifests[0]['fake_avatar_dependency_proof'][0]['required_existing_avatar_container_sha256']
        result['required_native_capabilities']=ready['required_native_capabilities']
    for name,value in (('runtime-ready.json',ready),('delivery.json',result),('missions.json',plan)):
        (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--six-chapters',action='store_true');args=p.parse_args()
    r=prepare(six_chapters=args.six_chapters);print(json.dumps({k:r[k] for k in ('status','stage_count','missions','cg_ids')}))
