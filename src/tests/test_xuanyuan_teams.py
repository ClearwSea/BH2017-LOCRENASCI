"""Real StageBegin replay against external generated tables; no live save writes."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest


@unittest.skipUnless(os.environ.get("BH3_TEST_RUNTIME"), "requires generated runtime")
class XuanyuanTeamsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ["BH3_TEST_RUNTIME"])
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location("server19_stage", Path(__file__).resolve().parents[1] / "server19_stage.py")
        cls.s = importlib.util.module_from_spec(spec)
        sys.modules["server19_stage"] = cls.s
        spec.loader.exec_module(cls.s)
        cls.s.TABLE_DIRECTORY = root / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"
        rows = json.loads((root / "server19-run/kallen-20261025/all-open-delivery/stagedata_main").read_bytes())
        cls.rows = {r["levelId"]: r for r in rows}
        cls.s.stage_config = lambda identity=cls.s.STAGE_ID: deepcopy(cls.rows[identity])
        cls.s.supported_stage_ids = lambda: tuple(cls.rows)
        cls.s.STORY_TRIAL_AVATARS[214107] = (502, 501)

    def setUp(self):
        self.account = dict(schema=1, uid=1024,
            main=dict(level=60, exp=0, stamina=200, scoin=100000, equipment_size_limit=20000),
            avatar_list=[dict(avatar_id=i, star=3, level=20, exp=0) for i in (101,102,103,201,202,203)],
            weapon_list=[], stigmata_list=[], material_list=[], stage_list=[])

    def begin(self, stage, avatars):
        return self.s._begin(self.account, dict(stage_id=stage, avatar_id_list=avatars))[1]

    def test_captured_three_team_request_and_5_2_begin_retry_exit(self):
        slots = [101,0,0,102,0,0,103,0,0]
        for identity in (210106,210111):
            self.setUp()
            result = self.begin(identity, slots)
            self.assertEqual(result["retcode"], 0)
            self.assertEqual(self.account["stage_runtime"]["active"]["avatar_slots"], slots)
            charged = deepcopy(self.account)
            self.assertEqual(self.begin(identity, slots), result)
            self.assertEqual(self.account, charged)
            raw = self.s.proto.encode_message("StageEndReqBody", dict(stage_id=identity,end_status=3,stage_pass_time=1))
            end = self.s._end(self.account, dict(body=raw,sign=self.s.stage_end_signature(raw,result["sign_key"])))[1]
            self.assertEqual(end["retcode"],0)
            self.assertIsNone(self.account["stage_runtime"]["active"])

    def test_8_1_one_two_three_capacity(self):
        result = self.begin(210116, [101,0,0,102,103,0,201,202,203])
        self.assertEqual(result["retcode"],0)

    def test_invalid_multiteams_leave_account_unchanged(self):
        for slots in ([101,0,0], [101,102,0,103,0,0,201,0,0],
                      [101,0,0,0,0,0,103,0,0], [101,0,0,101,0,0,103,0,0],
                      [101,0,0,102,0,0,999,0,0]):
            with self.subTest(slots=slots):
                before = deepcopy(self.account)
                self.assertNotEqual(self.begin(210106,slots)["retcode"],0)
                self.assertEqual(self.account,before)

    def test_ordinary_stage_still_rejects_nine_slots(self):
        self.assertEqual(self.begin(210101,[101,0,0,102,0,0,103,0,0])["retcode"],13)
        self.assertEqual(self.begin(210101,[101,0,0])["retcode"],0)

    def test_prescribed_trial_blocks_still_work(self):
        self.assertEqual(self.begin(214107,[502,0,0,501,0,0])["retcode"],0)


if __name__ == "__main__":
    unittest.main()
