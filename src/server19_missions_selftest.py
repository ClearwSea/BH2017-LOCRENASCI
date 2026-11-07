"""Independent account fixtures; never access the device or running save.

Run with Python from the project root. The synthetic WIN receipts below test
transaction invariants; they are not recorded as original/native evidence.
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
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import server19_missions as missions
import server19_protocol as proto
import server19_stage as stage


def fixture(*, wins=()):
    return {"schema": 1, "uid": 1024, "main": {"level": 15, "exp": 36,
                "scoin": 4500, "hcoin": 90, "stamina": 24, "equipment_size_limit": 100},
            "avatar_list": [{"avatar_id": 101, "star": 1, "level": 5, "exp": 34,
                             "fragment": 0, "weapon_unique_id": 1}],
            "weapon_list": [{"unique_id": 1, "id": 20001, "level": 1, "exp": 0,
                             "is_protected": False},
                            {"unique_id": 2, "id": 20041, "level": 1, "exp": 0,
                             "is_protected": False}],
            "stigmata_list": [], "material_list": [],
            "stage_list": [{"id": identity, "progress": 1, "is_done": True,
                            "challenge_index_list": [0, 1, 2]} for identity in wins],
            "stage_runtime": {"schema": 1, "active": None, "settlements": [
                {"stage_id": identity, "end_status": 1,
                 "response": {"retcode": 0, "progress": 1},
                 "accepted_drops": [{"item_id": 20041, "level": 1, "num": 1}]}
                for identity in wins]}}


class MissionTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="server19-mission-test-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "account.json"
        self.account = fixture(wins=range(10101, 10107))
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.account, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    def call(self, name, values=None, account=None):
        return missions.response(name, account if account is not None else self.account,
                                 values, account_path=self.path)

    def claim(self, identity):
        return self.call("GetMissionRewardReq", {"mission_id": identity})

    def claim_prefix(self, end=10004):
        for identity in range(10001, end + 1):
            self.assertEqual(self.claim(identity)[1]["retcode"], 0)

    def test_backfill_only_changes_mission_state_and_is_idempotent(self):
        before = deepcopy(self.account)
        result = self.call("GetMissionDataReq")
        self.assertEqual(result[1]["mission_list"], [
            {"mission_id": 10001, "status": 3, "progress": 1}])
        for key, value in before.items():
            self.assertEqual(self.account[key], value, key)
        saved = self.path.read_bytes()
        self.assertEqual(self.call("GetMissionDataReq"), result)
        self.assertEqual(self.path.read_bytes(), saved)
        backup = self.path.with_name("account-before-first-stage-execution.json")
        self.assertEqual(json.loads(backup.read_bytes()), before)

    def test_catalog_uses_the_actual_seven_supported_stage_ids(self):
        catalog = missions.mission_catalog()
        self.assertEqual([(key, row["stage_id"]) for key, row in catalog.items()],
                         list(zip(range(10001, 10008), range(10101, 10108))))

    def test_unfinished_and_no_settlement_cannot_claim(self):
        self.account = fixture()
        self.write()
        self.assertEqual(self.call("GetMissionDataReq")[1]["mission_list"][0]["status"], 2)
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10001)[1], {"retcode": 3})
        self.assertEqual(self.path.read_bytes(), before)
        self.account["stage_list"] = [{"id": 10101, "is_done": True, "progress": 1}]
        self.write()
        self.assertEqual(self.call("GetMissionDataReq")[1]["mission_list"][0]["status"], 2)

    def test_lost_or_failed_receipt_is_not_a_win(self):
        self.account["stage_runtime"]["settlements"][0]["end_status"] = 3
        self.write()
        self.assertEqual(self.call("GetMissionDataReq")[1]["mission_list"][0]["progress"], 0)
        self.account["stage_runtime"]["settlements"][0].update(end_status=1,
                                            response={"retcode": 1, "progress": 1})
        self.write()
        self.assertEqual(self.claim(10001)[1], {"retcode": 3})

    def test_linear_claim_order_cannot_be_skipped(self):
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10005)[1], {"retcode": 3})
        self.assertEqual(self.path.read_bytes(), before)
        self.claim_prefix(10001)
        self.assertEqual(self.account["mission_data"]["mission_list"], [
            {"mission_id": 10002, "status": 3, "progress": 1}])

    def test_snapshot_closes_native_incremental_cache_and_exposes_next_task(self):
        # Original 70036 applies rows by ID without clearing the mission dict;
        # original 80562 excludes status5. Model only those proven branches.
        cache = {row["mission_id"]: row for row in self.call("GetMissionDataReq")[1]["mission_list"]}
        self.claim(10001)
        packet = missions.mission_snapshot(self.account)
        rows = proto.decode_message(packet[0], proto.encode_message(*packet))["mission_list"]
        for row in rows:
            cache[row["mission_id"]] = row
        self.assertEqual(cache[10001], {"mission_id": 10001, "status": 5, "progress": 1})
        self.assertEqual([key for key, row in cache.items() if row["status"] != 5], [10002])
        self.claim_prefix(10006)
        for row in missions.mission_snapshot(self.account)[1]["mission_list"]:
            cache[row["mission_id"]] = row
        self.assertTrue(all(cache[identity]["status"] == 5
                            for identity in range(10001, 10007)))
        self.assertEqual(cache[10007], {"mission_id": 10007, "status": 2, "progress": 0})
        before = self.path.read_bytes()
        self.call("GetMissionDataReq")
        self.assertEqual(self.path.read_bytes(), before)

    def test_exact_six_rewards_and_card_uses_existing_weapon(self):
        before_stage = deepcopy(self.account["stage_runtime"])
        before_weapons = deepcopy(self.account["weapon_list"])
        self.claim_prefix(10006)
        self.assertEqual(self.account["main"], {"level": 15, "exp": 108,
            "scoin": 5660, "hcoin": 90, "stamina": 30, "equipment_size_limit": 100})
        self.assertEqual(self.account["material_list"], [{"id": 3000, "num": 2},
                                                        {"id": 4005, "num": 1}])
        self.assertEqual(self.account["stigmata_list"], [{"unique_id": 20001, "id": 30004,
                                      "level": 1, "exp": 0, "is_protected": False}])
        avatar = self.account["avatar_list"][1]
        self.assertEqual(avatar, {"avatar_id": 201, "star": 1, "level": 1, "exp": 0,
            "weapon_unique_id": 2, "stigmata_unique_id_1": 0, "stigmata_unique_id_2": 0,
            "stigmata_unique_id_3": 0, "fragment": 0, "touch_goodfeel": 0,
            "today_has_add_goodfeel": 0, "stage_goodfeel": 0})
        self.assertEqual(self.account["weapon_list"], before_weapons)
        self.assertEqual(self.account["stage_runtime"], before_stage)
        self.assertEqual(self.account["mission_data"]["mission_list"], [
            {"mission_id": 10007, "status": 2, "progress": 0}])
        self.assertEqual(self.account["mission_runtime"]["claimed_ids"], list(range(10001, 10007)))

    def test_retries_survive_new_account_object_without_granting_twice(self):
        first = self.claim(10001)
        for identity in range(10002, 10005):
            self.assertEqual(self.claim(identity)[1]["retcode"], 0)
        before = self.path.read_bytes()
        stale = fixture()
        self.assertEqual(self.call("GetMissionRewardReq", {"mission_id": 10001}, stale)[1], {"retcode": 3})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(stale, self.account)

    def test_parallel_identical_claims_issue_one_reward(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda unused: self.call("GetMissionRewardReq",
                    {"mission_id": 10001}, deepcopy(self.account)), range(2)))
        self.assertEqual(sorted(result[1]["retcode"] for result in results), [0, 3])
        stored = json.loads(self.path.read_bytes())
        self.assertEqual(len(stored["stigmata_list"]), 1)
        self.assertEqual(stored["main"]["exp"], 48)
        self.assertEqual(len(stored["mission_runtime"]["receipts"]), 1)

    def test_separate_process_retry_uses_persisted_receipt(self):
        self.claim(10001)
        before = self.path.read_bytes()
        script = ("import json,sys; from pathlib import Path; import server19_missions as m; "
                  "p=Path(sys.argv[1]); a=json.loads(p.read_bytes()); "
                  "r=m.response('GetMissionRewardReq',a,{'mission_id':10001},account_path=p); "
                  "assert r[1]['retcode']==3")
        subprocess.run([sys.executable, "-c", script, str(self.path)], check=True,
                       cwd=Path(__file__).resolve().parent, capture_output=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_unknown_id_and_bool_selector_leave_bytes_unchanged(self):
        before = self.path.read_bytes()
        self.assertEqual(self.claim(99999)[1], {"retcode": 2})
        self.assertEqual(self.claim(True)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)

    def test_capacity_and_material_limits_roll_back(self):
        self.account["main"]["equipment_size_limit"] = 2
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10001)[1], {"retcode": 4})
        self.assertEqual(self.path.read_bytes(), before)
        self.account["main"]["equipment_size_limit"] = 100
        self.write()
        self.claim_prefix(10001)
        self.account["material_list"] = [{"id": 3000, "num": 99999}]
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10002)[1], {"retcode": 5})
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_initial_weapon_has_no_partial_card_or_stamina(self):
        self.claim_prefix()
        self.account["weapon_list"].pop()
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10005)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.account["avatar_list"]), 1)

    def test_occupied_default_weapon_is_not_taken_from_other_avatar(self):
        self.claim_prefix()
        self.account["avatar_list"].append({"avatar_id": 202, "star": 1,
                                        "level": 1, "weapon_unique_id": 2})
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10005)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)

    def test_existing_locked_fragments_and_weapon_levels_are_preserved(self):
        self.claim_prefix()
        self.account["avatar_list"].append({"avatar_id": 201, "star": 0,
                                "level": 1, "exp": 0, "fragment": 3, "touch_goodfeel": 2})
        self.account["weapon_list"][1].update(level=2, exp=1)
        self.write()
        before = deepcopy(self.account["weapon_list"])
        self.assertEqual(self.claim(10005)[1]["retcode"], 0)
        self.assertEqual(self.account["avatar_list"][1]["fragment"], 3)
        self.assertEqual(self.account["avatar_list"][1]["touch_goodfeel"], 2)
        self.assertEqual(self.account["weapon_list"], before)

    def test_already_owned_card_requires_separate_conversion_audit(self):
        self.claim_prefix()
        self.account["avatar_list"].append({"avatar_id": 201, "star": 1,
                                             "level": 1, "weapon_unique_id": 2})
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10005)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)

    def test_low_level_upgrade_boundary_does_not_lose_reward(self):
        self.account["main"].update(level=1, exp=12)
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10001)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)

    def test_configuration_changes_fail_without_awards(self):
        original = stage._table
        def changed(name):
            rows = original(name)
            if name == "rewarddata":
                next(row for row in rows if row["RewardID"] == 10005)["RewardItem1Num"] = 2
            return rows
        before = self.path.read_bytes()
        with patch.object(stage, "_table", changed):
            self.assertEqual(self.claim(10001)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)

    def test_unencodable_snapshot_cannot_commit_any_reward_or_progress(self):
        self.account["mission_data"] = {"mission_list": [
            {"mission_id": 30001, "status": 2, "progress": 0, "unsupported_field": 17}]}
        self.write()
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10001)[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.call("GetMissionDataReq")[1], {"retcode": 1})
        self.assertEqual(self.path.read_bytes(), before)

    def test_unrelated_missions_duty_state_and_explicit_closed_history_preserved(self):
        other = {"mission_id": 30001, "status": 2, "progress": 0, "begin_time": 123}
        self.account["mission_data"] = {"mission_list": [other,
            {"mission_id": 10001, "status": 5, "progress": 1}], "daily_duty_point": 11,
            "has_take_daily_duty_id_list": [1], "weekly_duty_point": 7}
        self.write()
        result = self.call("GetMissionDataReq")
        self.assertEqual(result[1]["mission_list"], [
            {"mission_id": 10001, "status": 5}, other,
            {"mission_id": 10002, "status": 3, "progress": 1}])
        self.assertEqual(result[1]["daily_duty_point"], 11)
        before = self.path.read_bytes()
        self.assertEqual(self.claim(10001)[1], {"retcode": 3})
        self.assertEqual(self.path.read_bytes(), before)

    def test_original_wire_schema_and_notification_order(self):
        self.claim_prefix(10005)
        notifications = missions.notification_snapshot(self.account)
        self.assertEqual([name for name, _ in notifications], ["GetEquipmentDataRsp",
                           "GetMainDataRsp", "GetMissionDataRsp", "GetAvatarDataRsp"])
        for name, value in notifications + [self.claim(10005), self.call("GetHasGotItemIdListReq")]:
            raw = proto.encode_message(name, value)
            decoded = proto.decode_message(name, raw)
            self.assertEqual(decoded["retcode"], 0)
            if name == "GetAvatarDataRsp":
                self.assertEqual(decoded["avatar_list"][1]["weapon_unique_id"], 2)
            if name == "GetHasGotItemIdListRsp":
                self.assertIn(60201, decoded["item_id_list"])
                self.assertIn(30004, decoded["item_id_list"])

    def test_has_got_card_id_requires_actual_claim_receipt(self):
        self.assertNotIn(60201, self.call("GetHasGotItemIdListReq")[1]["item_id_list"])
        self.claim_prefix(10005)
        self.assertIn(60201, self.call("GetHasGotItemIdListReq")[1]["item_id_list"])

    def test_observed_and_real_receipted_item_history_survives_inventory_removal(self):
        self.account["stage_runtime"]["settlements"][0]["accepted_drops"].append(
            {"item_id": 4001, "level": 0, "num": 3})
        self.write()
        first = self.call("GetHasGotItemIdListReq")[1]["item_id_list"]
        self.assertIn(4001, first)
        self.assertIn(20041, first)
        self.account["weapon_list"].pop()
        self.write()
        self.assertIn(20041, self.call("GetHasGotItemIdListReq")[1]["item_id_list"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
