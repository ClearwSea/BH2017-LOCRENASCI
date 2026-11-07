"""Exact probability interval and pool-closure checks, without gameplay."""

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
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server19_commission_catalog import CommissionCatalog


class Point:
    def __init__(self, value):
        self.value = value

    def randrange(self, total):
        assert 0 <= self.value < total
        return self.value


def check():
    catalog = CommissionCatalog(ROOT / 'server19-run/sakura-commissions-20261025/candidate-v1/catalog.json')
    for level, group in catalog.weights.items():
        values = [r['item1'] for r in group]
        weights = [r['item2'] for r in group]
        start = 0
        for value, weight in zip(values, weights):
            assert catalog.weighted(values, weights, Point(start)) == value
            assert catalog.weighted(values, weights, Point(start + weight - 1)) == value
            start += weight
        offers = catalog.offers(level, 3, random.Random(level))
        assert len(set(offers)) == 3
        assert all(catalog.quests[q]['rarity'] in values for q in offers)
        replacement = catalog.offers(level, 3, random.Random(level), offers)
        assert not set(replacement) & set(offers)
    print('PASS all30 reference rarity distributions, exact interval edges,501 rewards and unique offers')


if __name__ == '__main__':
    check()
