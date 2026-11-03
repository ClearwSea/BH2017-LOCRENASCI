"""隔离量化NumPy迁移差异 / Quantify migration drift without running a server.

The stable candidate is compiled in memory only. No business source or save writes.
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
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--deps', type=Path)
    p.add_argument('--mode', choices=['original', 'stable'], default='original')
    p.add_argument('--periods', type=int, default=104)
    p.add_argument('--source', type=Path, help='Optional preserved pre-fix source for reproducing the original audit')
    a = p.parse_args()
    if a.deps:
        sys.path.insert(0, str(a.deps.resolve()))
    import numpy as np
    source_path = ROOT / 'server19_endless_climate.py'
    source = (a.source or source_path).read_text(encoding='utf-8')
    if a.mode == 'stable':
        for part in ('power[g]', 'power[g+1]'):
            old = 'np.argsort(' + part + ')'
            if old in source:
                assert source.count(old) == 1
                source = source.replace(old, 'np.argsort(' + part + ", kind='stable')")
            else:
                assert 'np.argsort(' + part + ",kind='stable')" in source
    climate = types.ModuleType('isolated_climate')
    climate.__file__ = str(source_path)
    exec(compile(source, str(source_path), 'exec'), climate.__dict__)
    inputs = json.loads(a.inputs.read_bytes())
    a.output.mkdir(parents=True, exist_ok=False)
    summary = {'python': sys.version, 'numpy': np.__version__, 'mode': a.mode,
               'periods': a.periods, 'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(), 'scenarios': []}
    for scenario in inputs['scenarios']:
        c = deepcopy(scenario['state']) if 'state' in scenario else climate.create(scenario['begin'], scenario['seed'])
        arrays = {key: [] for key in ('temperature', 'next_temperature', 'clear_rate', 'success_time_ratio',
                                      'participants', 'reason', 'ids', 'power', 'skill', 'effort', 'goals',
                                      'sample_ids', 'sample_goals', 'sample_pace')}
        for period in range(a.periods + 1):
            projection = c.get('projection') or climate.project(c)
            for key in ('temperature', 'next_temperature', 'clear_rate', 'success_time_ratio', 'participants', 'reason'):
                arrays[key].append(deepcopy(projection[key]))
            for key in ('ids', 'power', 'skill', 'effort'):
                arrays[key].append(deepcopy(c[key]))
            arrays['goals'].append(deepcopy(projection['forecast']['goals']))
            samples = {'sample_ids': [], 'sample_goals': [], 'sample_pace': []}
            for group in range(7):
                indices = np.random.default_rng(climate.seed(c['seed'], c['begin'], group + 1, 'group')).choice(500, 19, replace=False)
                for key, values in [('sample_ids', c['ids']), ('sample_goals', projection['forecast']['goals']),
                                    ('sample_pace', projection['forecast']['pace'])]:
                    samples[key].append([values[group][int(i)] for i in indices])
            # Same three fixed top-tier leaders as production's players().
            samples['sample_goals'][6][:3] = [33, 33, 33]
            for key in samples:
                arrays[key].append(samples[key])
            if period < a.periods:
                climate.advance(c)
        np.savez_compressed(a.output / (scenario['name'] + '.npz'), **{k: np.asarray(v) for k, v in arrays.items()})
        summary['scenarios'].append(scenario['name'])
        print(a.mode, np.__version__, scenario['name'], 'done', flush=True)
    (a.output / 'run.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
