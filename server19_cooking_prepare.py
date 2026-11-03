"""Prepare approved coin cooking tables and original ability dependencies."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,hashlib,shutil
from pathlib import Path
from server19_sakura_prepare import TABLES,ROOT
from server19_sakura_resources import prepare as closure
from server19_cooking_native import build as native
OUT=ROOT/'server19-run/sakura-cooking-20261026'
BASE=ROOT/'server19-run/sakura-commissions-20261025/candidate-v3'
PRICES={2:2000,3:5000,4:10000}
def prepare():
    out=OUT/'candidate-v1';out.mkdir(parents=True,exist_ok=True)
    recipes=json.loads((TABLES/'openworldcookdata').read_bytes())
    for row in recipes:
        row['original_materials']=row['CostMaterialsList']
        row['scoin_cost']=PRICES[row['DisplayStar']]
    catalog=dict(recipes=recipes,currency='scoin',prices_by_star=PRICES,policy_approved=True,
        daily_reset='04:00 Asia/Shanghai',buff_expiration='daily_reset',source_sha256=hashlib.sha256((TABLES/'openworldcookdata').read_bytes()).hexdigest())
    (OUT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    client=json.loads((TABLES/'openworldcookdata').read_bytes())
    for row in client:
        # Native metadata sentinel only: no material5500 is granted or consumed.
        # Scoped ARM cooking calls read main.scoin and draw the coin icon.
        row['CostMaterialsList']=[dict(item1=5500,item2=PRICES[row['DisplayStar']])]
    target=out/'_exceloutputasset/openworldcookdata';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(client,ensure_ascii=False,indent=2),encoding='utf-8')
    if not (out/'resource-closure.json').exists():
        shutil.copyfile(BASE/'lua-declarations.json',out/'lua-declarations.json')
        closure(base=BASE,output=out,story_ids=[201],trial_ids=[],script_paths=[],
            extra_abilities=[f'CookBuff_{r["CookID"]}' for r in recipes if r['EffectType']==1])
    native()
if __name__=='__main__':prepare()
