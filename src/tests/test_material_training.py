import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from contextlib import nullcontext
from types import ModuleType
import unittest
from unittest.mock import patch

import server19_material_training as training


class MaterialTrainingTests(unittest.TestCase):
    def setUp(self):
        self.stage = ModuleType('server19_stage')
        self.stage._item_metadata = lambda item_id: ('material', {'rarity': 2, 'quantityLimit': 9999})
        self.stage._u32 = lambda value, name: value
        self.module = patch.dict(sys.modules, {'server19_stage': self.stage})
        self.module.start()
        self.addCleanup(self.module.stop)

    def test_approved_fivefold_rewards_keep_native_twelve_positions(self):
        for identity, expected in ((45001, {1002: 70, 1003: 50}),
                                   (45033, {1003: 55, 1006: 60})):
            plan = training.drop_plan(identity)
            totals = {}
            for item in plan:
                totals[item['item_id']] = totals.get(item['item_id'], 0) + item['num']
            self.assertEqual(len(plan), 12)
            self.assertTrue(all(type(row['num']) is int and row['num'] > 0 for row in plan))
            self.assertEqual(totals, expected)

    def test_retry_plan_is_bound_to_stage_and_unchanged_rewards(self):
        plan = training.drop_plan(45001)
        active = {'drop_policy': training.DROP_POLICY, 'stage_id': 45001,
                  'drop_plan': copy.deepcopy(plan),
                  'begin_response': {'stage_id': 45001, 'drop_item_list': copy.deepcopy(plan)}}
        self.assertTrue(training.validate_active(active, {'levelId': 45001}))
        changed = copy.deepcopy(active)
        changed['drop_plan'][0]['num'] += 1
        self.assertFalse(training.validate_active(changed, {'levelId': 45001}))
        self.assertFalse(training.validate_active(active, {'levelId': 45002}))

    def test_tuesday_schedule_and_four_am_rollover(self):
        china = timezone(timedelta(hours=8))
        before = datetime(2026, 11, 17, 3, 59, tzinfo=china)
        after = datetime(2026, 11, 17, 4, 0, tzinfo=china)
        self.assertFalse(training.is_open(1501, before))
        self.assertTrue(training.is_open(1501, after))
        account = {'material_training_runtime': {'day': '2026-11-16', 'wins': {'1501': 1}}}
        self.assertEqual(training.completed_today(account, 1501, before), 1)
        self.assertEqual(training.completed_today(account, 1501, after), 0)
        training.record_win(account, 45001, after)
        self.assertEqual(account['material_training_runtime'], {'day': '2026-11-17', 'wins': {'1501': 1}, 'opened': {}, 'exchanges': {}})

    def test_weekly_schedule_and_temporary_open_expiry(self):
        china = timezone(timedelta(hours=8))
        monday = datetime(2026, 11, 16, 12, tzinfo=china)
        expected = ({1541}, {1501}, {1531}, {1511}, {1541}, {1531}, {1521})
        for offset, identities in enumerate(expected):
            date = monday + timedelta(days=offset)
            self.assertEqual({i for i in training.MATERIAL_IDS if training.is_open(i, date)}, identities)
        account = {'material_training_runtime': {'day': '2026-11-17', 'opened': {'1511': 1}}}
        self.assertTrue(training.is_open(1511, monday + timedelta(days=1), account))
        self.assertFalse(training.is_open(1511, monday + timedelta(days=2), account))

    def test_all_rewards_match_approved_counts(self):
        self.assertEqual(len(training.STAGE_ACTIVITY), 84)
        for sid, identity in training.STAGE_ACTIVITY.items():
            if identity in training.THEME_IDS or identity == training.REDPACKET_ID:
                continue
            number = sid - training.ACTIVITIES[identity][0]
            tier, slot = (number - 1) // 10, (number - 1) % 10
            items = training.ITEMS[identity][0 if tier == 0 else 1]
            amounts = training.BASE_AMOUNTS['avatar' if identity < 1531 else 'equipment'][tier * 3 + slot]
            plan = training.drop_plan(sid)
            totals = {item: sum(row['num'] for row in plan if row['item_id'] == item) for item in items}
            self.assertEqual(totals, dict(zip(items, (n * 5 for n in amounts))))
            self.assertEqual(len(plan), 2 if identity == 1531 else 12)

    def test_theme_rewards_follow_preview_rarity_for_every_difficulty(self):
        previews = ((1, 0), (2, 1), (2, 3), (3, 2))
        for index, activity in enumerate(training.THEME_IDS):
            base_item = 5005 + index * 4
            for tier, pair in enumerate(previews, 1):
                sid = training.ACTIVITIES[activity][0] + tier
                items = [base_item + i for i in pair]
                self.stage.stage_config = lambda stage_id, items=items: {'displayDropList': items}
                self.stage._item_metadata = lambda item_id, base=base_item: (
                    'material', {'rarity': item_id - base + 1, 'quantityLimit': 9999})
                plan = training.drop_plan(sid)
                totals = {item: sum(row['num'] for row in plan if row['item_id'] == item)
                          for item in items}
                self.assertEqual(totals, {min(items): 30, max(items): 15})
                self.assertEqual(len(plan), 6)

    def test_themes_open_weekdays_and_have_two_daily_attempts(self):
        monday = datetime(2026, 11, 16, 12, tzinfo=timezone(timedelta(hours=8)))
        for day in range(7):
            opened = {i for i in training.THEME_IDS if training.is_open(i, monday + timedelta(days=day))}
            self.assertEqual(opened, {1001 + day} if day < 5 else set())
        self.assertTrue(all(training.daily_limit(i) == 2 for i in training.THEME_IDS))
        self.assertTrue(all(training.daily_limit(i) == 1 for i in training.MATERIAL_IDS))

    def test_theme_open_uses_source_cost_and_does_not_change_material_cost(self):
        now = datetime(2026, 11, 17, 12, tzinfo=timezone(timedelta(hours=8)))
        self.stage._table = lambda name, **kwargs: [dict(weekDayActivityID=i, minPlayerLevel=15,
            activityCoinCost=6 if i in training.THEME_IDS else 12,
            activityCoinID=7034, openScoinCost=3000) for i in training.ACTIVITY_IDS]
        self.stage._transaction_lock = lambda path: nullcontext()
        self.stage._read = lambda path, account: json.loads(path.read_text())
        self.stage._save = lambda path, before, current: path.write_text(json.dumps(current))
        self.stage._sync = lambda target, current: (target.clear(), target.update(copy.deepcopy(current)))
        proto = ModuleType('server19_protocol')
        proto.encode_message = lambda *args: b''
        account = {'main': {'level': 80, 'scoin': 4000}, 'material_list': [{'id': 7034, 'num': 6}]}
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {'server19_protocol': proto}):
            path = Path(d) / 'account.json'
            path.write_text(json.dumps(account))
            req = {'activity_id': 1001}
            self.assertEqual(training.response('OpenWeekDayActivityReq', account, req, account_path=path, now=now)[1]['retcode'], 0)
            self.assertEqual((account['main']['scoin'], account['material_list'][0]['num']), (1000, 0))
            self.assertTrue(training.is_open(1001, now, json.loads(path.read_text())))

    def test_temporary_open_charges_once_and_survives_reload(self):
        now = datetime(2026, 11, 17, 12, tzinfo=timezone(timedelta(hours=8)))
        self.stage._table = lambda name, **kwargs: [dict(weekDayActivityID=i, minPlayerLevel=15,
            activityCoinCost=12, activityCoinID=7034, openScoinCost=3000) for i in training.ACTIVITY_IDS]
        self.stage._transaction_lock = lambda path: nullcontext()
        self.stage._read = lambda path, account: json.loads(path.read_text())
        self.stage._save = lambda path, before, current: path.write_text(json.dumps(current))
        self.stage._sync = lambda target, current: (target.clear(), target.update(copy.deepcopy(current)))
        proto = ModuleType('server19_protocol')
        proto.encode_message = lambda *args: b''
        account = {'main': {'level': 80, 'scoin': 4000}, 'material_list': [{'id': 7034, 'num': 12}]}
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {'server19_protocol': proto}):
            path = Path(d) / 'account.json'
            path.write_text(json.dumps(account))
            req = {'activity_id': 1511}
            self.assertEqual(training.response('OpenWeekDayActivityReq', account, req, account_path=path, now=now)[1]['retcode'], 0)
            self.assertEqual((account['main']['scoin'], account['material_list'][0]['num']), (1000, 0))
            self.assertTrue(training.is_open(1511, now, json.loads(path.read_text())))
            self.assertNotEqual(training.response('OpenWeekDayActivityReq', account, req, account_path=path, now=now)[1]['retcode'], 0)
            self.assertEqual((account['main']['scoin'], account['material_list'][0]['num']), (1000, 0))

    def test_exchange_attempts_charges_badges_and_resets_with_day(self):
        now = datetime(2026, 11, 17, 12, tzinfo=timezone(timedelta(hours=8)))
        self.stage._table = lambda name, **kwargs: [dict(weekDayActivityID=i, minPlayerLevel=15,
            activityCoinCost=12, activityCoinID=7034, openScoinCost=3000) for i in training.ACTIVITY_IDS]
        self.stage._transaction_lock = lambda path: nullcontext()
        self.stage._read = lambda path, account: json.loads(path.read_text())
        self.stage._save = lambda path, before, current: path.write_text(json.dumps(current))
        self.stage._sync = lambda target, current: (target.clear(), target.update(copy.deepcopy(current)))
        proto = ModuleType('server19_protocol')
        proto.encode_message = lambda *args: b''
        account = {'main': {'level': 80, 'scoin': 4000}, 'material_list': [{'id': 7034, 'num': 12}],
                   'material_training_runtime': {'day': '2026-11-17', 'wins': {'1501': 1}}}
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {'server19_protocol': proto}):
            path = Path(d) / 'account.json'
            path.write_text(json.dumps(account))
            req = {'activity_id': 1501, 'activity_times': 1}
            self.assertEqual(training.response('ExchangeWeekDayActivityTimesReq', account, req, account_path=path, now=now)[1],
                             {'retcode': 0, 'coin_cost': 12})
            self.assertEqual((account['main']['scoin'], account['material_list'][0]['num']), (4000, 0))
            self.assertEqual(training.exchanged_today(account, 1501, now), 1)
            self.assertEqual(training.exchanged_today(account, 1501, now + timedelta(days=1)), 0)
            self.assertNotEqual(training.response('ExchangeWeekDayActivityTimesReq', account, req, account_path=path, now=now)[1]['retcode'], 0)

    def test_activity_visibility_preserves_unrelated_entries(self):
        self.stage._table = lambda name, **kwargs: [{
            'weekDayActivityID': identity, 'minPlayerLevel': 15,
            'levelIDList': [s for s, activity in training.STAGE_ACTIVITY.items() if activity == identity],
        } for identity in training.ACTIVITY_IDS]
        now = datetime(2026, 11, 17, 12, tzinfo=timezone(timedelta(hours=8)))
        unrelated = {'activity_id': 1601, 'stage_id_list': [55001]}
        payload = {'activity_list': [unrelated]}
        training.update_activity_list(payload, {'main': {'level': 80}}, now)
        self.assertEqual(payload['activity_list'][0], unrelated)
        by_id = {r['activity_id']: r for r in payload['activity_list']}
        self.assertEqual(len(by_id[1501]['stage_id_list']), 12)
        self.assertEqual(len(by_id[1002]['stage_id_list']), 4)
        low = {'activity_list': [unrelated]}
        training.update_activity_list(low, {'main': {'level': 14}}, now)
        self.assertEqual(low['activity_list'], [unrelated])


if __name__ == '__main__':
    unittest.main()
