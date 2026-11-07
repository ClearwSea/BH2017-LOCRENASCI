"""Candidate ordinary commission transactions. Not enabled by default.

Caller owns the existing account transaction; offers and receipts are persisted.
Calendar compatibility rules are explicitly user-approved; gameplay is native.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import random
from zoneinfo import ZoneInfo

from server19_commission_catalog import CommissionCatalog
import server19_stage as stage
import server19_missions as missions
import server19_player_progression as progression

REQUESTS = frozenset(('OpenOpenworldQuestReq', 'GetOpenworldSelectQuestReq',
    'ChooseOpenworldQuestReq', 'RefreshOpenworldQuestReq', 'FinishOpenworldQuestReq',
    'TakeOpenworldQuestRewardReq', 'AbandonOpenworldQuestReq', 'TakeOpenworldKeyQuestRewardReq'))
PAID_REFRESH_HCOIN = 10  # User-authorized local price; not historical1.9 pricing.


def calendar(now):
    local = datetime.fromtimestamp(now, ZoneInfo('Asia/Shanghai'))
    day = (local - timedelta(hours=4)).date()
    period = day
    while period.weekday() not in (0, 3, 5):
        period -= timedelta(days=1)
    return day.isoformat(), period.isoformat()


class Commissions:
    def __init__(self, catalog_path):
        self.catalog = CommissionCatalog(catalog_path)

    def state(self, account, now):
        world = account['openworld_data']
        data = world['quest_data']
        day, period = calendar(now)
        next_day = datetime.fromisoformat(day).date()+timedelta(days=1)
        while next_day.weekday() not in (0,3,5):
            next_day += timedelta(days=1)
        world['next_refresh_time'] = int(datetime.combine(next_day, datetime.min.time(),
            tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())+4*3600
        runtime = account.setdefault('commission_runtime', dict(schema=1, period=period,
            day=day, offers={}, receipts={}, refresh_used=0, abandoned=False))
        monday = (datetime.fromisoformat(day).date() -
                  timedelta(days=datetime.fromisoformat(day).weekday())).isoformat()
        runtime.setdefault('week', monday)
        data.setdefault('star', 0)
        data.setdefault('max_quest_level', data['level'])
        if runtime['week'] != monday:
            levels = {r['questLevel']: r for r in self.catalog.data['levels']}
            old_level, old_star = data['level'], data['star']
            config = levels[old_level]
            rewards = []
            if runtime.get('week_completed_round'):
                reward = deepcopy(self.catalog.data['rewards'][str(config['monthlyReward'])])
                self.grant(account, reward)
                rewards.append(reward)
            # Approved reference interpretation: subtract configured stars
            # from total rating, borrowing across level boundaries.
            weeks = (datetime.fromisoformat(monday)-datetime.fromisoformat(runtime['week'])).days//7
            level, remaining = old_level, old_star
            sub_star = 0
            for _ in range(weeks):
                available = sum(levels[i]['levelupNeedStar'] for i in range(1,level))+remaining
                loss = min(available, levels[level]['starAfterSettlement'])
                sub_star += loss
                remaining = available-loss
                previous_level, level = level, 1
                while level < previous_level and remaining >= levels[level]['levelupNeedStar']:
                    remaining -= levels[level]['levelupNeedStar']
                    level += 1
            data.update(level=level, star=remaining)
            # Recreate a pending emergency at its level when rating recovers.
            # Completed emergency receipts survive the weekly downgrade.
            if level != old_level:
                data.pop('key_quest', None)
            notice = dict(old_level=old_level, old_star=old_star,
                cur_level=level, cur_star=remaining,
                sub_star=sub_star, reward_list=rewards)
            runtime.setdefault('pending_settlements', []).append(notice)
            runtime['last_settlement'] = dict(week=runtime['week'], settled_at=now, **notice)
            runtime.update(week=monday, week_completed_round=False)
        if runtime['period'] != period:
            # Explicitly approved offline rule: even FINISH-but-unclaimed
            # ordinary commissions expire. Never grant their rewards here.
            runtime['last_expiration'] = dict(period=runtime['period'], at=now,
                quests=deepcopy(data.get('quest_list', [])))
            runtime.update(period=period, offers={}, receipts={})
            runtime.pop('complete_receipt', None)
            data.update(quest_list=[], is_open=False, day_open_times=0)
            # Adventure rating and emergency-quest receipts are independent
            # of these ordinary slots and must not be fabricated/reset here.
        if runtime['day'] != day:
            runtime.update(day=day, refresh_used=0, abandoned=False)
        data.update(refresh_left_times=max(0, 3-runtime['refresh_used']),
                    next_refresh_cost=0 if runtime['refresh_used'] < 3 else PAID_REFRESH_HCOIN,
                    is_can_abandon=not runtime['abandoned'])
        data.setdefault('key_quest', dict(id=0, status=0))
        return world, data, runtime

    def slots(self, world):
        done = set(world['finish_story_id_list'])
        # NetworkManager converts UI indices to one-based protocol slots.
        # RequestGetOpenworldSelectQuest and RequestTake...Reward add one.
        return {r['SlotPosition']: r for r in self.catalog.data['slots']
                if r['UnlockStoryID'] in done}

    def advance(self, data, runtime):
        levels = {r['questLevel']: r for r in self.catalog.data['levels']}
        while data['level'] < max(levels):
            config = levels[data['level']]
            if data['star'] < config['levelupNeedStar']:
                break
            key = config['keyQuestID']
            if key and str(key) not in runtime.get('key_receipts', {}):
                if data.get('key_quest', {}).get('id') != key:
                    config_quest = next(r for r in self.catalog.data['key_quests'] if r['questId'] == key)
                    debuffs = [int(v) for v in config_quest['debuff'].split(',') if v]
                    data['key_quest'] = dict(index=0, id=key, status=1, position=0,
                        buff_id=0, debuff_id=debuffs[0] if debuffs else 0)
                break
            data['star'] -= config['levelupNeedStar']
            data['level'] += 1
            data.pop('key_quest', None)
        data['max_quest_level'] = max(data.get('max_quest_level', 1), data['level'])

    @staticmethod
    def grant(account, reward):
        missions._preflight(account, reward)
        if reward['exp']:
            progression.grant_player_exp(account['main'], reward['exp'])
        for field in ('scoin', 'hcoin', 'stamina'):
            account['main'][field] = stage._u32(account['main'].get(field, 0)+reward[field], field)
        totals = {}
        for item in reward['item_list']:
            pair = item['id'], item['level']
            totals[pair] = totals.get(pair, 0)+item['num']
        stage._grant_drops(account, totals)

    def generate(self, data, runtime, index, rng):
        excluded = [r['id'] for r in data['quest_list']]
        ids = self.catalog.offers(data['level'], 3, rng, excluded)
        result = []
        for select_index, identity in enumerate(ids, start=1):
            row = self.catalog.quests[identity]
            # Position0 uses native GetQuestLocation's Fail fallback and the
            # original Lua random area allocator, including collision avoidance.
            value = dict(index=select_index, id=identity, status=0, position=0)
            for field in ('buff', 'debuff'):
                values = [int(i) for i in row[field].split(',') if i]
                value[field+'_id'] = rng.choice(values) if values else 0
            result.append(value)
        runtime['offers'][str(index)] = result
        return deepcopy(result)

    def handle(self, name, account, values, now, rng=None):
        if name not in REQUESTS:
            return None
        rng = rng or random.SystemRandom()
        world, data, runtime = self.state(account, now)
        slots = self.slots(world)
        if not slots:
            return dict(retcode=1)
        if name == 'OpenOpenworldQuestReq':
            if not data['is_open']:
                data['is_open'] = True
                data['day_open_times'] = 1
            return dict(retcode=0)
        if not data['is_open'] and name not in ('FinishOpenworldQuestReq', 'TakeOpenworldKeyQuestRewardReq'):
            return dict(retcode=1)
        if name == 'FinishOpenworldQuestReq':
            row = next((r for r in data['quest_list'] if r['id'] == values.get('id')), None)
            if data.get('key_quest', {}).get('id') == values.get('id'):
                row = data['key_quest']
            active = account.get('openworld_runtime', {}).get('active')
            if row is None or row['status'] not in (1, 2) or not active or active['area_id'] != 101:
                return dict(retcode=1)
            row['status'] = 2
            return dict(retcode=0)
        if name == 'TakeOpenworldKeyQuestRewardReq':
            row = data.get('key_quest')
            if row is None or row['status'] != 2:
                return dict(retcode=1)
            if str(row['id']) in runtime.get('key_receipts', {}):
                return dict(retcode=0, reward_list=[], level=data['level'], star=data['star'])
            config = next(r for r in self.catalog.data['levels'] if r['questLevel'] == data['level'])
            if config['keyQuestID'] != row['id']:
                return dict(retcode=1)
            reward = deepcopy(self.catalog.data['rewards'][str(config['keyQuestReward'])])
            self.grant(account, reward)
            runtime.setdefault('key_receipts', {})[str(row['id'])] = dict(reward=reward, claimed_at=now)
            data.pop('key_quest', None)
            self.advance(data, runtime)
            return dict(retcode=0, reward_list=[reward], level=data['level'], star=data['star'])
        index = values.get('index')
        if type(index) is not int or index not in slots:
            return dict(retcode=1)
        row = next((r for r in data['quest_list'] if r['index'] == index), None)
        if name in ('GetOpenworldSelectQuestReq', 'RefreshOpenworldQuestReq'):
            if row is not None:
                return dict(retcode=1)
            if name == 'RefreshOpenworldQuestReq':
                cost = 0 if runtime['refresh_used'] < 3 else PAID_REFRESH_HCOIN
                if account['main'].get('hcoin', 0) < cost:
                    return dict(retcode=1)
                result = self.generate(data, runtime, index, rng)
                account['main']['hcoin'] = account['main'].get('hcoin', 0)-cost
                runtime['refresh_used'] += 1
                data['refresh_left_times'] = max(0, 3-runtime['refresh_used'])
                data['next_refresh_cost'] = 0 if runtime['refresh_used'] < 3 else PAID_REFRESH_HCOIN
                return dict(retcode=0, quest_list=result, refresh_left_times=data['refresh_left_times'],
                            next_refresh_cost=data['next_refresh_cost'])
            if str(index) not in runtime['offers']:
                self.generate(data, runtime, index, rng)
            return dict(retcode=0, index=index, quest_list=deepcopy(runtime['offers'][str(index)]))
        if name == 'ChooseOpenworldQuestReq':
            candidates = runtime['offers'].get(str(index), [])
            # Selection is the one-based display ordinal, not an offer ID.
            # Existing offers from the initial candidate used 0-based index
            # fields; preserve their order and identities without rewriting saves.
            choice = values.get('select_index')
            selected = candidates[choice-1] if type(choice) is int and 1 <= choice <= len(candidates) else None
            if selected is None:
                return dict(retcode=1)
            if row is not None:
                return dict(retcode=0, quest=deepcopy(row)) if row['id'] == selected['id'] else dict(retcode=1)
            config = self.catalog.quests[selected['id']]
            if any(r['id'] == selected['id'] for r in data['quest_list']):
                return dict(retcode=1)
            if account['main'].get('stamina', 0) < config['staminaCost']:
                return dict(retcode=1)
            account['main']['stamina'] -= config['staminaCost']
            row = dict(selected, index=index, status=1)
            data['quest_list'].append(row)
            return dict(retcode=0, quest=deepcopy(row))
        if row is None:
            return dict(retcode=1)
        if name == 'AbandonOpenworldQuestReq':
            if row['status'] != 1 or runtime['abandoned']:
                return dict(retcode=1)
            data['quest_list'].remove(row)
            # User-approved offline exception: no stamina or item refund.
            runtime['offers'].pop(str(index), None)
            runtime['abandoned'] = True
            data['is_can_abandon'] = False
            return dict(retcode=0)
        if name == 'TakeOpenworldQuestRewardReq':
            key = str(index)
            if key in runtime['receipts']:
                return dict(retcode=0, reward_list=[], day_reward_list=[], add_star=0)
            if row['status'] != 2:
                return dict(retcode=1)
            reward = deepcopy(self.catalog.data['rewards'][str(self.catalog.quests[row['id']]['rewardId'])])
            self.grant(account, reward)
            stars = slots[index]['StarReward']
            data['star'] += stars
            row['status'] = 3
            runtime['receipts'][key] = dict(id=row['id'], reward=reward, add_star=stars, claimed_at=now)
            self.advance(data, runtime)
            day_rewards = []
            if all(any(q['index'] == slot and q['status'] == 3 for q in data['quest_list']) for slot in slots) and not runtime.get('complete_receipt'):
                config = next(r for r in self.catalog.data['levels'] if r['questLevel'] == data['level'])
                daily = deepcopy(self.catalog.data['rewards'][str(config['completeReward'])])
                self.grant(account, daily)
                runtime['complete_receipt'] = dict(reward=daily, claimed_at=now)
                runtime['week_completed_round'] = True
                day_rewards.append(daily)
            return dict(retcode=0, reward_list=[reward], day_reward_list=day_rewards, add_star=stars)
        raise AssertionError(name)
