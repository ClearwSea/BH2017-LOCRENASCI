import unittest
from unittest.mock import patch
import os, sys, importlib.util
from pathlib import Path
if not os.environ.get("BH3_TEST_RUNTIME"):
    raise unittest.SkipTest("requires generated runtime")
sys.path.insert(0, os.environ["BH3_TEST_RUNTIME"])
import server19_protocol
for name in ("server19_stage", "server19_missions"):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
import server19_stage as stage
import server19_missions as missions

class FirstLoginTests(unittest.TestCase):
    def test_completed_opening_repairs_only_login_flag(self):
        account = {"is_first_login": True, "guide_id_list": [1012],
                   "stage_list": [{"id": 10101, "is_done": True}],
                   "stage_runtime": {"settlements": [{"stage_id": 10101,
                       "end_status": 1, "response": {"retcode": 0}}]}}
        stage.reconcile_first_login(account)
        self.assertIs(account["is_first_login"], False)
        self.assertEqual(account["guide_id_list"], [1012])
        stage.reconcile_first_login(account)
        self.assertIs(account["is_first_login"], False)

    def test_exit_or_unfinished_opening_remains_retryable(self):
        for status in (2, 3, 4):
            account = {"is_first_login": True,
                "stage_list": [{"id": 10101, "is_done": True}],
                "stage_runtime": {"settlements": [{"stage_id": 10101,
                    "end_status": status, "response": {"retcode": 0}}]}}
            stage.reconcile_first_login(account)
            self.assertIs(account["is_first_login"], True)
        account = {"is_first_login": True, "stage_list": []}
        stage.reconcile_first_login(account)
        self.assertIs(account["is_first_login"], True)

    def test_supply_uses_configured_level(self):
        row = {"MissionID": 13004, "MinLevel": 9, "PreMissionId": 0}
        with patch.object(stage, "_table", return_value=[row]):
            for level in (1, 2, 8):
                self.assertEqual(missions._guidance_rows({"main": {"level": level}}), [])
            self.assertEqual(missions._guidance_rows({"main": {"level": 9}}),
                [{"mission_id": 13004, "status": missions.MISSION_DOING, "progress": 0}])
            self.assertEqual(missions._guidance_rows({"main": {"level": 2},
                "guidance_runtime": {"schema": 1, "done": [13004]}})[0]["status"], missions.MISSION_FINISH)

if __name__ == "__main__":
    unittest.main()
