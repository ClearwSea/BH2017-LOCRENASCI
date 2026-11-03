"""Build fourth-cycle candidate only; no live account, service or device writes."""

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
import os, shutil
ROOT=Path(__file__).resolve().parent

def fix_final_reward(script):
    """Report the completed final dialogue before claiming its original reward."""
    old = 'mission.mission_set_state  (411, 3)'
    progress = 'mission.mission_set_state(411, 2, 1)'
    if progress not in script:
        if script.count(old) != 1:
            raise ValueError('Expected one original fourth-cycle final reward call')
        script = script.replace(old, progress + '\n\t\t\t\t\t\t\t\t' + old)
    return script


def prepare():
    os.chdir(ROOT)
    candidate=ROOT/'server19-run/sakura-cycle4-20261026/candidate-v1'
    candidate.mkdir(parents=True,exist_ok=True)
    if not (candidate/'lua').exists():
        shutil.copytree(ROOT/'server19-run/sakura-cycle3-20261026/candidate-v1/lua',candidate/'lua')
    from scripts.check_sakura_lua import check
    check(candidate,cycle=4,story_ids=list(range(401,412)))
    check(candidate,cycle=4,story_ids=list(range(408,412)),root_module='Levels/OpenWorld/LevelOpenWorld_Sakura_Castle_Outside')
    for name in ('levelopenworld_sakura','levelopenworld_sakura_castle_outside'):
        path=candidate/f'lua/levels/openworld/{name}.lua'
        text=path.read_text(encoding='utf-8-sig')
        text=text.replace('LevelDesign:IsServantFightOn()', 'LevelDesign:IsServantUnlocked()')
        if name == 'levelopenworld_sakura_castle_outside':
            text = fix_final_reward(text)
        path.write_text(text,encoding='utf-8')
    from pathlib import Path
    import json,re
    from scripts.check_sakura_lua import check
    from scripts.check_sakura_scene import check as scene
    from server19_sakura_resources import prepare
    p=Path('server19-run/sakura-cycle4-20261026/candidate-v1');out=p.parent
    castle=p/'lua/levels/openworld/levelopenworld_sakura_castle_outside.lua';s=castle.read_text(encoding='utf-8-sig');s=s.replace('LevelDesign:IsServantFightOn()', 'LevelDesign:IsServantUnlocked()');castle.write_text(s,encoding='utf-8')
    reports=[]
    for root,ids,label in [('Levels/OpenWorld/LevelOpenWorld_Sakura',list(range(401,408)),'city'),('Levels/OpenWorld/LevelOpenWorld_Sakura_Castle_Outside',list(range(408,412)),'castle')]:
     r=check(p,cycle=4,story_ids=ids,root_module=root);reports.append(r)
     (out/(label+'-lua.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
     sr=scene(ids,'cycle4-'+label+'-scenes.json',scenes=tuple(r['scenes']));print(label,'missing in ALL scenes:',set.intersection(*(set(x['missing_candidates']) for x in sr)))
    merged=dict(reports[0]);merged['scripts']=list({r['path']:r for report in reports for r in report['scripts']}.values());merged['area_monsters']=sorted(set(tuple(x) for r in reports for x in r['area_monsters']))
    (p/'lua-declarations.json').write_text(json.dumps(merged,indent=2),encoding='utf-8')
    paths=[f'lua/levels/owmission/{i}.lua' for i in range(401,412)]+['lua/levels/openworld/levelopenworld_sakura.lua','lua/levels/openworld/levelopenworld_sakura_castle_outside.lua']
    props=set()
    for n in paths:props.update(re.findall(r'CreatePropObject\(\s*"([^"]+)"',(p/n).read_text(encoding='utf-8-sig')))
    skills=json.loads(Path('.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/servantskilldata').read_bytes())
    abilities={'Servant_Fox_Follow'}|{r['SkillPar'] for r in skills if r['SkillPar'].startswith('Servant_')}
    print('props',sorted(props),'abilities',sorted(abilities))
    prepare(base=Path('server19-run/sakura-cycle3-20261026/candidate-v1'),output=p,story_ids=list(range(401,412)),trial_ids=[],script_paths=paths,extra_props=sorted(props),extra_abilities=sorted(abilities),camera_union=True)

    import json,re
    from pathlib import Path
    from server19_sakura_prepare import TABLES
    from server19_achievement import _parse_reward
    p=Path('server19-run/sakura-cycle4-20261026/candidate-v1');out=p.parent
    c=json.loads(Path('server19-run/sakura-cycle3-20261026/candidate-v1/catalog.json').read_bytes())
    rows=[r for r in json.loads((TABLES/'openworldstorydata').read_bytes()) if 401<=r['StoryID']<=411]
    rewards={r['RewardID']:_parse_reward(r) for r in json.loads((TABLES/'rewarddata').read_bytes())}
    c['fourth_cycle']=next(r for r in json.loads((TABLES/'openworldcycledata').read_bytes()) if r['cycle']==4);c['fourth_cycle_reward']=rewards[965050];c['stories']+=rows;c['rewards'].update({str(r['HuntRewardItem']):rewards[r['HuntRewardItem']] for r in rows})
    for target,source in [('areas','openworldarea'),('servant_levels','servantleveldata'),('servant_skills','servantskilldata'),('chapters','openworldchapter')]:c[target]=json.loads((TABLES/source).read_bytes())
    c['servant_materials']=[r for r in json.loads((TABLES/'materialdata').read_bytes()) if r.get('ServantExpProvide',0)>0]
    (p/'catalog.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    plots=set()
    for i in range(401,412):
     text=(p/f'lua/levels/owmission/{i}.lua').read_text(encoding='utf-8-sig')
     for a,b in re.findall(r'"StoryMode"\s*,\s*(\d+)|(?:accept|finish)_dialogid\s*=\s*(\d+)',text):plots.add(int(a or b))
    pr=[r for r in json.loads((TABLES/'plotdata').read_bytes()) if r['plotID'] in plots];assert len(pr)==len(plots)
    ids={i for r in pr for i in range(r['startDialogID'],r['endDialogID']+1)};dialogs=[r for r in json.loads((TABLES/'dialogdata').read_bytes()) if r['dialogID'] in ids];assert len(dialogs)==len(ids)
    (out/'presentation-audit.json').write_text(json.dumps(dict(plots=pr,dialogs=dialogs),ensure_ascii=False,indent=2),encoding='utf-8');voice=out/'voice';voice.mkdir(exist_ok=True);(voice/'all-voice-targets.json').write_text(json.dumps(dict(dialogs=dialogs),ensure_ascii=False,indent=2),encoding='utf-8');print(len(rows),'stories',len(pr),'plots',len(dialogs),'dialogs')

if __name__=='__main__':
    prepare()
