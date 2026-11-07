"""Prepare mode dependencies over the accepted fourth-cycle resources."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server19_sakura_resources as resources
p=ROOT/'server19-run/endless-20261026/candidate-v1'
d=json.loads((p/'lua-declarations.json').read_bytes())
items=json.loads((p/'catalog.json').read_bytes())['items']
report=resources.prepare(base=ROOT/'server19-run/sakura-cycle4-20261026/candidate-v1',output=p,
 trial_ids=[],script_paths=[x['path'] for x in d['scripts'] if 'infinite' in x['path']],
 extra_unique_ids=range(401,432),extra_abilities=['EndlessMiasma']+[x['paramStr'] for x in items if x['paramStr']],
 camera_union=True,monster_tables=p/'metadata/_exceloutputasset',ui_custom_buff_ids=(1001,6005,6006,9001))
assert not report['blockers'],report['blockers']
