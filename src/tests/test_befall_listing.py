import unittest
from copy import deepcopy
from unittest.mock import patch
import importlib.util
import sys
from types import ModuleType
from pathlib import Path
spec = importlib.util.spec_from_file_location('befall_listing_tested', Path(__file__).resolve().parents[1]/'server19_befall.py')
b = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'server19_stage': ModuleType('server19_stage')}):
    spec.loader.exec_module(b)

class BefallListingTests(unittest.TestCase):
    def setUp(self):
        meta = [dict(weekDayActivityID=i, minPlayerLevel=20,
                     levelIDList=[55001+n*100]) for n,i in enumerate(b.ACTIVITY_IDS)]
        self.mock = patch.object(b, 'activities', return_value=meta)
        self.mock.start()
        rotation = patch.object(b, 'rotation_window', return_value=((1601,1611),0,604800))
        rotation.start()
        self.addCleanup(rotation.stop)
        self.addCleanup(self.mock.stop)

    def test_visibility_uses_daily_wins_and_preserves_other_activities(self):
        original = dict(activity_list=[dict(activity_id=1601, stage_id_list=[],
                        enter_times=1, exchange_times=2), dict(activity_id=9000, stage_id_list=[])])
        for level, count in [(19,0),(20,2),(80,2)]:
            data = deepcopy(original)
            b.update_activity_list(data, dict(main=dict(level=level)))
            rows = [r for r in data['activity_list'] if r['activity_id'] in b.ACTIVITY_IDS]
            self.assertEqual(len(rows), count)
            self.assertIn(original['activity_list'][1], data['activity_list'])
            if rows:
                self.assertEqual(rows[0]['enter_times'],0)
                from server19_business_clock import day_bounds
                self.assertEqual((rows[0]['begin_time'], rows[0]['end_time']), day_bounds())
                self.assertEqual(rows[0]['exchange_times'],2)
                self.assertEqual(rows[0]['stage_id_list'],[55001])

    def test_snapshots_preserve_progress_without_mutating_account(self):
        account = dict(main=dict(level=20), stage_list=[dict(id=55001, progress=1,
                            enter_times=1, challenge_index_list=[0])])
        before = deepcopy(account)
        rows = b.stage_snapshots(account)
        self.assertEqual(rows[0],account['stage_list'][0])
        self.assertEqual(rows[1]['progress'],0)
        rows[0]['challenge_index_list'].append(1)
        self.assertEqual(account,before)
        account['main']['level']=19
        self.assertEqual(b.stage_snapshots(account),[])

    def test_approved_drop_probability_boundaries(self):
        def metadata(identity):
            return ('weapon' if identity == 25041 else 'material', {'rarity': 3})
        with patch.object(b.stage, '_item_metadata', side_effect=metadata, create=True):
            for roll, count in ((0, 2), (9, 2), (10, 1), (99, 1)):
                with patch('secrets.randbelow', return_value=roll):
                    first, _ = b.draw(0)
                    plan, audit = b.draw(1)
                self.assertEqual(len(first), 2)
                self.assertEqual(len(plan), count)
                active = dict(stage_id=55001, drop_plan=plan, drop_audit=audit,
                              begin_response=dict(stage_id=55001, progress=1, drop_item_list=plan))
                self.assertTrue(b.validate_active(active, {'levelId': 55001}))
                changed = deepcopy(active)
                changed['drop_plan'][0]['num'] += 1
                self.assertFalse(b.validate_active(changed, {'levelId': 55001}))

    def test_quota_resets_at_beijing_four_without_erasing_saved_receipt(self):
        from datetime import datetime, timezone, timedelta
        clock = timezone(timedelta(hours=8))
        account = {'befall_runtime': {'day': '2026-11-10', 'wins': {'1601': 1}}}
        before = deepcopy(account)
        self.assertEqual(b.completed_today(account, datetime(2026, 11, 11, 3, 59, tzinfo=clock)), 1)
        self.assertEqual(b.completed_today(account, datetime(2026, 11, 11, 4, 0, tzinfo=clock)), 0)
        self.assertEqual(account, before)

    def test_gluttony_tiers_and_shared_daily_display(self):
        def metadata(identity):
            return ('material' if identity == 7032 else 'weapon', {'rarity': 4 if identity != 25041 else 3})
        with patch.object(b.stage, '_item_metadata', side_effect=metadata, create=True):
            for tier, prefix in enumerate((55000, 55010, 55020, 55030)):
                for slot in (1, 2, 3):
                    sid = prefix + slot
                    weapon = 25041 if tier < 2 else 25051
                    with patch('secrets.randbelow', return_value=99):
                        first, _ = b.draw(0, sid)
                    self.assertEqual([(x['item_id'], x['num']) for x in first], [(7032, tier + 1), (weapon, 1)])
                    probability = (10, 15, 10, 15)[tier]
                    for roll, count in ((probability - 1, 2), (probability, 1)):
                        with patch('secrets.randbelow', return_value=roll):
                            plan, audit = b.draw(1, sid)
                        self.assertEqual(len(plan), count)
                        active = dict(stage_id=sid, drop_plan=plan, drop_audit=audit,
                                      begin_response=dict(stage_id=sid, progress=1, drop_item_list=plan))
                        self.assertTrue(b.validate_active(active, {'levelId': sid}))
                        self.assertFalse(b.validate_active(active, {'levelId': sid + 1}))
        from server19_business_clock import day_key
        account = dict(main=dict(level=80), befall_runtime=dict(day=day_key(), wins={'1601': 1}))
        activity = dict(activity_list=[])
        b.update_activity_list(activity, account)
        self.assertEqual(next(x for x in activity['activity_list'] if x['activity_id'] == 1601)['enter_times'], 1)

    def test_bronya_quota_independent_from_gluttony(self):
        from server19_business_clock import day_key
        account = dict(main=dict(level=80), befall_runtime=dict(day=day_key(), wins={'1601': 1}))
        self.assertEqual(b.completed_today(account, activity_id=1611), 0)
        b.record_win(account, 55133)
        self.assertEqual(account['befall_runtime']['wins'], {'1601': 1, '1611': 1})
        activity = dict(activity_list=[])
        b.update_activity_list(activity, account)
        self.assertEqual([r['enter_times'] for r in activity['activity_list'][:2]], [1, 1])

    def test_bronya_approved_tiers_and_probabilities(self):
        with patch.object(b.stage, '_item_metadata', return_value=('weapon', {'rarity': 4}), create=True):
            for tier in range(4):
                for slot in (1, 2, 3):
                    sid = 55100 + tier * 10 + slot
                    first, _ = b.draw(0, sid)
                    self.assertEqual([(r['item_id'], r['num']) for r in first],
                                     [(7032, tier + 1), (25081 if tier < 2 else 25091, 1)])
                    probability = (10, 15, 10, 15)[tier]
                    for roll, count in ((probability - 1, 2), (probability, 1)):
                        with patch('secrets.randbelow', return_value=roll):
                            drops, _ = b.draw(1, sid)
                        self.assertEqual(len(drops), count)

    def test_wendy_quota_independent_from_gluttony(self):
        from server19_business_clock import day_key
        account = dict(main=dict(level=80), befall_runtime=dict(day=day_key(), wins={'1601': 1}))
        self.assertEqual(b.completed_today(account, activity_id=1621), 0)
        b.record_win(account, 55233)
        self.assertEqual(account['befall_runtime']['wins'], {'1601': 1, '1621': 1})
        activity = dict(activity_list=[])
        b.update_activity_list(activity, account)
        self.assertEqual([r['enter_times'] for r in activity['activity_list']], [1, 0])
        with patch.object(b, 'rotation_window', return_value=((1621,1631),604800,1209600)):
            b.update_activity_list(activity, account)
        self.assertEqual([r['activity_id'] for r in activity['activity_list']], [1621,1631])
        self.assertEqual([r['enter_times'] for r in activity['activity_list']], [1,0])

    def test_wendy_approved_tiers_and_probabilities(self):
        with patch.object(b.stage, '_item_metadata', return_value=('weapon', {'rarity': 4}), create=True):
            for tier in range(4):
                for slot in (1, 2, 3):
                    sid = 55200 + tier * 10 + slot
                    first, _ = b.draw(0, sid)
                    self.assertEqual([(r['item_id'], r['num']) for r in first],
                                     [(7032, tier + 1), (25061 if tier < 2 else 25071, 1)])
                    probability = (10, 15, 10, 15)[tier]
                    for roll, count in ((probability - 1, 2), (probability, 1)):
                        with patch('secrets.randbelow', return_value=roll):
                            drops, _ = b.draw(1, sid)
                        self.assertEqual(len(drops), count)
