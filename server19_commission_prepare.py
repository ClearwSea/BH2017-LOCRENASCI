"""Reproducible commission candidate; no game/server/account operations."""

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
import shutil
import zipfile

from server19_sakura_prepare import ROOT, TABLES
from server19_achievement import _parse_reward
import server19_resources as resources
from server19_stage_resources import text_record
from server19_sakura_resources import prepare as dependencies
from scripts.check_sakura_lua import check as declarations

OUT = ROOT/'server19-run/sakura-commissions-20261025'
BASE = ROOT/'server19-run/sakura-cycle2-20261025/candidate-v1'
REFERENCE = ROOT/'7.0-HONKAI3-OFFLINE/BH3/启动器-old/BH3/Resources/ExcelOutputAsset/OpenWorldQuestRarity.json'


def prepare(folder=None):
    folder = Path(folder or OUT/'candidate-v3')
    folder.mkdir(parents=True,exist_ok=True)
    read = lambda name: json.loads((TABLES/name).read_bytes())
    quests = [r for r in read('openworldquestdata') if (r['questType'],r['questArea'])==(1,101) and r['weight']>0]
    keys = [r for r in read('openworldquestdata') if (r['questType'],r['questArea'])==(3,101)]
    levels = read('openworldquestlevel')
    reward_ids = {r['rewardId'] for r in quests}
    reward_ids.update(r[k] for r in levels for k in ('completeReward','monthlyReward','keyQuestReward') if r[k])
    catalog = dict(source='old compatibility tables; approved7.0 rarity distribution',
        quests=quests,key_quests=keys,levels=levels,slots=read('openworldquestslot'),
        rarity_weights=[r for r in json.loads(REFERENCE.read_bytes()) if r['MapId']==1],
        rewards={str(r['RewardID']):_parse_reward(r) for r in read('rewarddata') if r['RewardID'] in reward_ids},
        source_sha256={name:hashlib.sha256((TABLES/name).read_bytes()).hexdigest() for name in
            ('openworldquestdata','openworldquestlevel','openworldquestslot','openworldquestbuffdata','rewarddata')},
        rarity_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        compatibility_policy=dict(daily_free_refreshes=3,paid_refresh_hcoin=10,
            unclaimed_at_period_boundary='expire_without_reward',weekly_stars='subtract_starAfterSettlement',
            abandon_refund='none_user_approved',rarity='user-approved7.0 reference'),deployed=False)
    assert len(quests)==501 and len(keys)==20 and len(catalog['rewards'])==len(reward_ids)
    (folder/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copytree(BASE/'lua',folder/'lua',dirs_exist_ok=True)
    mapping={r['path']:r for r in resources.resource_map(resources.DEFAULT24)}
    paths=sorted({'lua/'+r['luaFileName'].lower()+'.lua' for r in quests})
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        for path in paths:
            raw,_=text_record(package,mapping[path],'2.4')
            target=folder/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    declarations(folder,cycle=2,story_ids=list(range(201,208)),selected_quests=quests[:4],key_quest=keys[0])
    modifiers={int(v) for r in quests+keys for f in ('buff','debuff') for v in r[f].split(',') if v}
    names=[r['buffNameStrId'] for r in read('openworldquestbuffdata') if r['buffId'] in modifiers]
    result=dependencies(base=BASE,output=folder,story_ids=list(range(201,208)),trial_ids=[],
        script_paths=paths,extra_abilities=names,extra_unique_ids=[r['luaPara'][0] for r in keys],
        extra_props=['OpenWorld_Quest_Point'])
    assert not result['blockers']
    prepare_rule_text(folder)
    return folder


def prepare_rule_text(folder):
    """Patch only the two approved economy lines over the read-back device map."""
    preimage=OUT/'textmap-device-preimage.json'
    rows=json.loads(preimage.read_bytes())
    row=next(r for r in rows if r['ID']=='Rule_Quest')
    before=row['Text']
    parts=before.split('\\n')
    assert parts[4].startswith('3)') and '7' in parts[4] and parts[5].startswith('4)')
    parts[4]='3)每天有3次<color=#00C3FFFF>免费刷新</color>次数，用完后每次消耗10水晶刷新；'
    parts[5]='4)接取后可以放弃委托，每天最多一次；放弃不返还体力或物品；'
    row['Text']='\\n'.join(parts)
    target=Path(folder)/'_exceloutputasset/textmap'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (Path(folder)/'rule-text-proof.json').write_text(json.dumps(dict(id='Rule_Quest',before=before,
        after=row['Text'],preimage_sha256=hashlib.sha256(preimage.read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    print(prepare())
