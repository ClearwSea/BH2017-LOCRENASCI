"""Opt-in native Sakura cooking; approved local coin prices and 04:00 reset."""
import json
from pathlib import Path
from server19_commissions import calendar

REQUESTS = frozenset({'EatOpenworldCookReq'})

class Cooking:
    def __init__(self, path):
        self.catalog = json.loads(Path(path).read_bytes())
        self.recipes = {r['CookID']: r for r in self.catalog['recipes']}

    def state(self, account, now):
        day = calendar(now)[0]
        state = account.setdefault('cooking_runtime', dict(day=day, buffs=[]))
        world = account['openworld_data']
        if state['day'] != day:
            state.update(day=day, buffs=[])
            world['cook_list'] = []
        world.setdefault('cook_list', [])
        return state

    def handle(self, account, values, now):
        state = self.state(account, now)
        recipe = self.recipes.get(values.get('cook_id'))
        world = account['openworld_data']
        if recipe is None or world['quest_data']['level'] < recipe['UnlockQuestLv']:
            return dict(retcode=1)
        used = next((r for r in world['cook_list'] if r['cook_id'] == recipe['CookID']), None)
        if used and used['eat_num'] >= recipe['DailyTimes']:
            return dict(retcode=1)
        cost = recipe['scoin_cost']
        if account['main'].get('scoin', 0) < cost:
            return dict(retcode=1)
        effect, params = recipe['EffectType'], recipe['EffectParam']
        runtime = account['openworld_runtime']
        if effect == 1:
            if values.get('avatar_id', 0) != 0 or recipe['CookID'] in state['buffs']:
                return dict(retcode=1)
        else:
            identity = values.get('avatar_id')
            owned = any(r['avatar_id'] == identity and r.get('star', 0) > 0
                        for r in account.get('avatar_list', []))
            if not owned:
                return dict(retcode=1)
            avatar = next((r for r in runtime['avatars'] if r['avatar_id'] == identity), None)
            new_avatar = avatar is None
            if new_avatar:
                # Native roster displays unvisited owned avatars at full HP/zero SP.
                # Persist only after a valid food use; never invent battle progress.
                avatar = dict(avatar_id=identity, hp_percent=100, sp_percent=0)
            hp, sp = avatar.get('hp_percent', 100), avatar.get('sp_percent', 0)
            if effect == 2:
                if hp != 0: return dict(retcode=1)
                avatar.update(hp_percent=params[0], sp_percent=params[1], revive_time=0)
            elif effect == 3:
                if hp == 0 or hp >= 100: return dict(retcode=1)
                avatar['hp_percent'] = min(100, hp + params[0])
            elif effect == 5:
                if hp == 0 or sp >= 100: return dict(retcode=1)
                avatar['sp_percent'] = min(100, sp + params[0])
            else:
                raise ValueError('Unreviewed cooking effect')
            if new_avatar:
                runtime['avatars'].append(avatar)
        account['main']['scoin'] -= cost
        if effect == 1:
            state['buffs'].append(recipe['CookID'])
        if used is None:
            used = dict(cook_id=recipe['CookID'], eat_num=0)
            world['cook_list'].append(used)
        used['eat_num'] += 1
        return dict(retcode=0)
