"""Prepare the bounded third-cycle candidate without device or account writes."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
import re
import shutil
from pathlib import Path

from server19_sakura_prepare import ROOT, TABLES
from server19_achievement import _parse_reward
from scripts.check_sakura_lua import check as check_lua
from scripts.check_sakura_scene import check as check_scene
from server19_sakura_resources import prepare as prepare_resources

OUT = ROOT / 'server19-run/sakura-cycle3-20261026'


def prepare():
    candidate = OUT / 'candidate-v1'
    candidate.mkdir(parents=True, exist_ok=True)
    previous = ROOT / 'server19-run/sakura-cycle2-20261025/candidate-v1'
    catalog = json.loads((previous / 'catalog.json').read_bytes())
    stories = [r for r in json.loads((TABLES / 'openworldstorydata').read_bytes())
               if 301 <= r['StoryID'] <= 308]
    cycle = next(r for r in json.loads((TABLES / 'openworldcycledata').read_bytes()) if r['cycle'] == 3)
    rewards = {r['RewardID']: _parse_reward(r) for r in json.loads((TABLES / 'rewarddata').read_bytes())}
    catalog.update(third_cycle=cycle, third_cycle_reward=rewards[cycle['finishreward']])
    catalog['stories'].extend(stories)
    catalog['rewards'].update({str(r['HuntRewardItem']): rewards[r['HuntRewardItem']] for r in stories})
    (candidate / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copytree(previous / 'lua', candidate / 'lua', dirs_exist_ok=True)
    check_lua(candidate, cycle=3, story_ids=list(range(301, 309)))
    scenes = check_scene(list(range(301, 309)), 'third-cycle-scenes.json')
    assert all(not r['missing_candidates'] for r in scenes)
    prepare_resources(base=ROOT / 'server19-run/sakura-cooking-20261026/candidate-v1',
                      output=candidate, story_ids=list(range(301, 309)), trial_ids=[])
    texts = [(candidate / f'lua/levels/owmission/{i}.lua').read_text(encoding='utf-8-sig') for i in range(301, 309)]
    plots = {int(i) for text in texts for i in re.findall(r'"StoryMode"\s*,\s*(\d+)', text)}
    rows = [r for r in json.loads((TABLES / 'plotdata').read_bytes()) if r['plotID'] in plots]
    assert len(rows) == len(plots)
    ids = {i for r in rows for i in range(r['startDialogID'], r['endDialogID'] + 1)}
    dialogs = [r for r in json.loads((TABLES / 'dialogdata').read_bytes()) if r['dialogID'] in ids]
    assert len(dialogs) == len(ids)
    (OUT / 'presentation-audit.json').write_text(json.dumps(dict(plots=rows, dialogs=dialogs), ensure_ascii=False, indent=2), encoding='utf-8')
    voice = OUT / 'voice'
    voice.mkdir(exist_ok=True)
    (voice / 'all-voice-targets.json').write_text(json.dumps(dict(dialogs=dialogs), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Third cycle prepared:', len(stories), 'stories,', len(plots), 'plots,', len(dialogs), 'dialogs')


if __name__ == '__main__':
    prepare()
