"""Prepare and sample the approved reference commission pool; no live I/O."""
from collections import defaultdict
import json
from pathlib import Path


class CommissionCatalog:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_bytes())
        self.quests = {r['questId']: r for r in self.data['quests']}
        if len(self.quests) != len(self.data['quests']):
            raise ValueError('Duplicate quest IDs')
        self.weights = {r['QuestLevel']: r['WeightGroup'] for r in self.data['rarity_weights']}
        if set(self.weights) != set(range(1, 31)):
            raise ValueError('Missing approved rarity levels')
        self.by_rarity = defaultdict(list)
        for row in self.quests.values():
            if (row['questType'], row['questArea']) != (1, 101) or row['weight'] <= 0:
                raise ValueError('Only normal positive-weight town quests are supported')
            if str(row['rewardId']) not in self.data['rewards']:
                raise ValueError('Missing original reward')
            self.by_rarity[row['rarity']].append(row)
        for group in self.weights.values():
            if any(r['item2'] <= 0 or r['item1'] not in self.by_rarity for r in group):
                raise ValueError('Rarity distribution cannot resolve to quests')

    @staticmethod
    def weighted(values, weights, rng):
        """Integer intervals preserve exact configured weights without rounding."""
        target = rng.randrange(sum(weights))
        for value, weight in zip(values, weights):
            if target < weight:
                return value
            target -= weight
        raise AssertionError('Invalid weight interval')

    def offers(self, level, count, rng, excluded=()):
        """Caller persists results; rereading a UI must not call this again."""
        if level not in self.weights or type(count) is not int or not 1 <= count <= 5:
            raise ValueError('Invalid offer request')
        excluded = set(excluded)
        results = []
        for _ in range(count):
            pools = {r: [q for q in qs if q['questId'] not in excluded]
                     for r, qs in self.by_rarity.items()}
            group = [g for g in self.weights[level] if pools[g['item1']]]
            if not group:
                raise ValueError('Eligible pool exhausted')
            rarity = self.weighted([g['item1'] for g in group], [g['item2'] for g in group], rng)
            row = self.weighted(pools[rarity], [q['weight'] for q in pools[rarity]], rng)
            results.append(row['questId'])
            excluded.add(row['questId'])
        return results
