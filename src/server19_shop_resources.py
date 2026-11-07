"""Prepare the same offered goods rows for native UI and server purchases.

Offline only. Input is an exact client metadata capture; no synthetic items,
price substitutions, device operations or save changes are performed.
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
import server19_shop as shop


def prepare(client_metadata, output, *, prefix=''):
    client_metadata, output = Path(client_metadata), Path(output)
    output.mkdir(exist_ok=False)

    def read(name):
        return json.loads((client_metadata/(prefix+name+('.json' if prefix else ''))).read_bytes())

    before = read('shopgoodsdata')
    goods = {r['ID']: r for r in before}
    if len(goods) != len(before):
        raise ValueError('Duplicate client goods IDs')
    item_ids = {r['ID'] for name in ('materialdata', 'avatarfragmentdata', 'weapondata', 'stigmatadata')
                for r in read(name)}
    offered = {gid for config in shop.SHOPS_CONFIG for gid in config['goods_pool']}
    new_ids = sorted(offered-set(goods))
    fields = set(before[0])
    for gid in offered:
        row = shop.GOODS_METADATA[gid]
        if set(row) != fields or row['ItemID'] not in item_ids:
            raise ValueError('Offered goods schema or actual client item unavailable: '+str(gid))
        if any(type(v) is not int or v < 0 for v in row.values()):
            raise ValueError('Invalid native goods scalar: '+str(gid))
        goods[gid] = row.copy()
    raw = json.dumps(list(goods.values()), ensure_ascii=False, separators=(',', ':')).encode()
    (output/'shopgoodsdata').write_bytes(raw)
    report = {'offered_goods': len(offered), 'new_ids': new_ids,
              'client_shopgoods_sha256': hashlib.sha256(raw).hexdigest(),
              'all_offered_item_ids_in_device_tables': True,
              'all_offered_prices_and_quantities_match_server': True,
              'item_tables_changed': False, 'human_acceptance': 'pending'}
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('client_metadata')
    parser.add_argument('output')
    parser.add_argument('--prefix', default='')
    args = parser.parse_args()
    print(json.dumps(prepare(args.client_metadata, args.output, prefix=args.prefix)))
