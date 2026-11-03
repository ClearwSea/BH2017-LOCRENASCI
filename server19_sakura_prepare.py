"""Prepare first-cycle source catalog and explicit Lua compatibility candidates.

Writes candidates only. No device, server or live account operations.
"""

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

from server19_achievement import _parse_reward

ROOT = Path(__file__).resolve().parent
TABLES = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
OUT = ROOT / 'server19-run/sakura-20261025'


def adapt(path, raw):
    replacements = {
        'lua/base/leveldesignopenworld.lua': {
            'if LevelDesign:IsAndroid() then': 'if true then -- target: native Android 1.9',
            'LevelDesign:UnloadUnusedEffectsAndMonsters(true)':
                '-- Approved 2026-10-25: native 1.9 has no later cache unload API.',
        },
        'lua/base/openworldareadesign.lua': {
            'LevelDesign:ClearReusePreloadMonsters()':
                '-- Approved 2026-10-25: keep ReleaseAsyncPreloadMonster above; no later reuse cache API.',
        },
    }
    text = raw.decode('utf-8-sig')
    edits = []
    for before, after in replacements.get(path, {}).items():
        if text.count(before) != 1:
            raise ValueError('Compatibility preimage changed: ' + before)
        text = text.replace(before, after)
        edits.append(before)
    return (text.encode('utf-8') if edits else raw), edits


def prepare(folder=None):
    folder = Path(folder or OUT / 'candidate-v1')
    folder.mkdir(parents=True, exist_ok=True)
    stories = [r for r in json.loads((TABLES / 'openworldstorydata').read_bytes())
               if 101 <= r['StoryID'] <= 111]
    ids = {r['HuntRewardItem'] for r in stories}
    rewards = {str(r['RewardID']): _parse_reward(r)
               for r in json.loads((TABLES / 'rewarddata').read_bytes()) if r['RewardID'] in ids}
    cycle = next(r for r in json.loads((TABLES / 'openworldcycledata').read_bytes()) if r['cycle'] == 1)
    cycle_reward = next(r for r in json.loads((TABLES / 'rewarddata').read_bytes()) if r['RewardID'] == cycle['finishreward'])
    catalog = {'source': '2.4 reference; native 1.9 protocol, historical economy unverified',
               'cycle': cycle, 'cycle_reward': _parse_reward(cycle_reward),
               'stories': stories, 'rewards': rewards,
               'source_sha256': {n: hashlib.sha256((TABLES / n).read_bytes()).hexdigest()
                                 for n in ('openworldstorydata', 'rewarddata', 'openworldcycledata')}}
    (folder / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    baseline = json.loads((ROOT / 'server19-run/extra-baseline-20261025-v3/runtime-artifacts.json').read_bytes())
    records = []
    for path in ('lua/base/leveldesignopenworld.lua', 'lua/base/openworldareadesign.lua'):
        accepted = next(r for r in baseline if r['remote'].endswith('/' + path))
        raw = (ROOT / accepted['local']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != accepted['sha256']:
            raise ValueError('Accepted shared Lua preimage changed: ' + path)
        transformed, edits = adapt(path, raw)
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(transformed)
        records.append({'path': path, 'accepted_preimage': accepted['local'], 'source_sha256': hashlib.sha256(raw).hexdigest(),
                        'sha256': hashlib.sha256(transformed).hexdigest(), 'edits': edits})
    (folder / 'compatibility.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    return folder


if __name__ == '__main__':
    print(prepare())
