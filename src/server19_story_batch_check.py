"""One isolated Act102 transaction-chain check; no device or live-save writes.

Synthetic WINs prove scoped protocol/business transactions, not gameplay.
Run with Python 3.13. Retains the actual seven WINs, two repeat settlements,
claimed missions and Act101 rewards in a clone while checking the new chain.
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
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import server19_missions as missions
import server19_protocol as proto
import server19_repeat_drops as repeat
import server19_stage as stage
import server19_stage_rewards as rewards
import server19_player_progression as captain

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json"


def main():
    raw = SOURCE.read_bytes()
    original = json.loads(raw)
    assert original["stage_runtime"]["active"] is None
    assert set(range(10101, 10108)) <= missions._confirmed_wins(original)
    assert original["mission_runtime"]["claimed_ids"] == list(range(10001, 10008))
    assert rewards.star_count(original, 102, 1) == 6
    out = ROOT / "server19-run/story-batch-check" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True)
    account = deepcopy(original)
    account["main"]["stamina"] = 120  # Isolated fixture only; no live refill.
    path = out / "simulated-account.json"
    path.write_text(json.dumps(account, ensure_ascii=False), encoding="utf-8")
    checks = []
    real_readiness = stage.STORY_RUNTIME_READY_FILE
    fixture_readiness = out / "simulated-runtime-ready.json"
    # Never generate a deployment receipt at the production gate path.
    stage.STORY_RUNTIME_READY_FILE = fixture_readiness

    def call(module, name, values=None):
        packet = module.response(name, account, values, account_path=path)
        proto.decode_message(packet[0], proto.encode_message(*packet))
        return packet

    def begin(identity):
        return call(stage, "StageBeginReq", {"stage_id": identity, "avatar_id_list": [201, 101, 0]})

    def end_request(identity, begun, drops=None):
        body = proto.encode_message("StageEndReqBody", {"stage_id": identity,
            "end_status": stage.STAGE_WIN, "stage_pass_time": 60,
            "challenge_index_list": [0, 1, 2], "drop_item_list": begun["drop_item_list"] if drops is None else drops,
            "scoin_reward": 0, "avatar_exp_reward": 0})
        return {"body": body, "sign": stage.stage_end_signature(body, begun["sign_key"])}

    before = path.read_bytes()
    assert begin(10108)[1] == {"retcode": 2} and path.read_bytes() == before
    assert 10108 not in {row["id"] for row in stage.available_stage_list(account)}
    fixture_readiness.write_text(json.dumps({"schema": 1,
        "audited_source_sha256": stage.AUDITED_ACT102_INCREMENT_SHA256,
        "ready_stage_ids": [10110]}), encoding="utf-8")
    assert begin(10110)[1] == {"retcode": 34} and path.read_bytes() == before
    fixture_readiness.write_text(json.dumps({"schema": 1,
        "audited_source_sha256": stage.AUDITED_ACT102_INCREMENT_SHA256,
        "ready_stage_ids": list(stage.AUDITED_ACT102_INCREMENT)}), encoding="utf-8")
    checks.append("missing_resource_receipt_keeps_new_stages_closed_partial_ready_keeps_prerequisite")

    # Full chapter audit is read-only: later Acts remain rejected even though
    # their rows exist. The consumer table contains 36 normal chapter1 rows.
    chapter = [row for row in stage._table("stagedata_main")
               if row["chapterId"] == 1 and row["difficulty"] == 1 and row["type"] == 1]
    assert {row["levelId"] for row in chapter} == set(range(10101, 10137))
    audit = [{"stage_id": row["levelId"], "act_id": row["actId"], "lua": row["luaFile"],
              "prerequisites": row["preLevelID"], "server_catalog_audited": row["levelId"] in stage.STORY_CATALOG_STAGE_IDS,
              "avatar_exp": row["avatarExpReward"], "coin": row["scoinReward"],
              "team_max": row["maxNumList"], "restrict": row["restrictList"],
              "challenge_reward_ids": [item["rewardId"] for item in row["challengeList"]]}
             for row in chapter]
    for identity in (10109, 10110, 10111, 10131, 10136):
        before = path.read_bytes()
        expected = 34 if identity <= 10110 else 2
        assert begin(identity)[1] == {"retcode": expected}
        assert path.read_bytes() == before
    assert {row["id"] for row in stage.available_stage_list(account)} == set(range(10101, 10109))
    call(missions, "GetMissionDataReq")
    assert next(row for row in account["mission_data"]["mission_list"] if row["mission_id"] == 10008)["status"] == 2
    assert call(missions, "GetMissionRewardReq", {"mission_id": 10008})[1] == {"retcode": 3}
    checks.append("full_source_audit_bounded_scope_predecessor_and_unwon_mission_rejected")

    # A batch-source change cannot be silently treated as reviewed input.
    actual_table = stage._table
    def changed(name):
        rows = actual_table(name)
        if name == "stagedata_main":
            next(row for row in rows if row["levelId"] == 10109)["scoinReward"] += 1
        return rows
    with patch.object(stage, "_table", side_effect=changed):
        try:
            stage.stage_config(10108)
            raise AssertionError("Changed source batch accepted")
        except ValueError:
            pass
    checks.append("whole_reviewed_increment_guard_rejects_any_changed_source_row")

    initial_coin = account["main"]["scoin"]
    initial_crystal = account["main"]["hcoin"]
    old_receipts = deepcopy(account["stage_runtime"]["settlements"])
    old_missions = deepcopy(account["mission_runtime"]["receipts"])
    old_act101 = deepcopy(account["act_reward_runtime"])
    source_avatars = deepcopy(account["avatar_list"])
    for identity, tier in zip(range(10108, 10111), range(1, 4)):
        begun = begin(identity)[1]
        assert begun["retcode"] == 0 and begun["progress"] == 0
        assert begun["drop_item_list"] == stage.first_clear_drop_plan(stage.stage_config(identity))
        committed = path.read_bytes()
        assert begin(identity)[1] == begun and path.read_bytes() == committed
        request = end_request(identity, begun)
        end = call(stage, "StageEndReq", request)[1]
        assert end["retcode"] == 0 and end["progress"] == 1
        assert (end["player_exp_reward"], end["avatar_exp_reward"], end["scoin_reward"]) == (6, 27, 750)
        assert len(end["challenge_list"]) == 3
        committed = path.read_bytes()
        assert call(stage, "StageEndReq", request)[1] == end and path.read_bytes() == committed
        mission = identity - 100
        call(missions, "GetMissionDataReq")
        row = next(row for row in account["mission_data"]["mission_list"] if row["mission_id"] == mission)
        assert row["status"] == 3 and row["progress"] == 1
        claimed = call(missions, "GetMissionRewardReq", {"mission_id": mission})
        assert claimed[1]["retcode"] == 0
        assert claimed[1]["reward_list"][0]["exp"] == 12 and claimed[1]["reward_list"][0]["scoin"] == 640
        committed = path.read_bytes()
        assert call(missions, "GetMissionRewardReq", {"mission_id": mission}) == claimed
        assert path.read_bytes() == committed
        assert rewards.star_count(account, 102, 1) == 6 + tier * 3
        star_req = {"act_id": 102, "difficulty": 1, "challenge_num_index": tier}
        star = call(rewards, "TakeStageActChallengeRewardReq", star_req)
        assert star[1]["retcode"] == 0
        committed = path.read_bytes()
        assert call(rewards, "TakeStageActChallengeRewardReq", star_req) == star and path.read_bytes() == committed
        if identity < 10110:
            assert identity + 1 in {row["id"] for row in stage.available_stage_list(account)}
    assert account["main"]["scoin"] == initial_coin + 2250 + 1920 + 9000 + 800
    assert account["main"]["hcoin"] == initial_crystal + 45 + 30
    assert (account["main"]["level"], account["main"]["exp"]) == (16, 26)
    upgrade = next(row["player_progression"] for row in account["mission_runtime"]["receipts"]
                   if row["mission_id"] == 10009)
    assert upgrade["level_rewards"] == [{"reached_level": 16, "scoin": 800, "stamina": 38}]
    assert account["main"]["stamina"] == 120 - 18 + 38
    assert account["mission_runtime"]["claimed_ids"] == list(range(10001, 10011))
    assert account["stage_runtime"]["settlements"][:len(old_receipts)] == old_receipts
    assert account["mission_runtime"]["receipts"][:len(old_missions)] == old_missions
    assert account["act_reward_runtime"]["receipts"][:len(old_act101["receipts"])] == old_act101["receipts"]
    assert [row["avatar_id"] for row in account["avatar_list"]] == [row["avatar_id"] for row in source_avatars]
    checks.append("actual_exp138_act102_three_wins_missions_captain16_arrival_rewards_tiers_and_retries")

    # Re-enter new stage10 with conservative policy; no redraw on retry,
    # no repeated first items, crystals or mission grant. Legitimate no-item.
    coin = account["main"]["scoin"]
    crystal = account["main"]["hcoin"]
    materials = deepcopy(account["material_list"])
    equipment = deepcopy(account["stigmata_list"])
    with patch.object(repeat.secrets, "randbelow", return_value=50):
        begun = begin(10110)[1]
    assert begun["retcode"] == 0 and begun["progress"] == 1 and not begun["drop_item_list"]
    committed = path.read_bytes()
    with patch.object(repeat, "draw", side_effect=AssertionError("repeat retry redraw")):
        assert begin(10110)[1] == begun and path.read_bytes() == committed
    forged = stage.first_clear_drop_plan(stage.stage_config(10110))
    assert call(stage, "StageEndReq", end_request(10110, begun, forged))[1] == {"retcode": 3}
    assert path.read_bytes() == committed
    result = call(stage, "StageEndReq", end_request(10110, begun))[1]
    assert result["retcode"] == 0 and not result["challenge_list"]
    assert account["main"]["scoin"] == coin + 750 and account["main"]["hcoin"] == crystal
    assert account["material_list"] == materials and account["stigmata_list"] == equipment
    assert repeat.probability_summary(stage.stage_config(10110))["no_item_percent"] == 51
    checks.append("new_stage_repeat_saved_plan_forged_drop_rejected_no_duplicate_first_or_challenge")

    # Shared mission save-error rollback: do not report a grant if persistence
    # failed. Use a claimable isolated branch, never alter the real save.
    failed = deepcopy(original)
    failed["stage_list"].append({"id": 10108, "is_done": True, "progress": 1})
    failed["stage_runtime"]["settlements"].append({"stage_id": 10108, "end_status": 1,
        "response": {"retcode": 0, "progress": 1}})
    failure_path = out / "simulated-write-failure.json"
    failure_path.write_text(json.dumps(failed, ensure_ascii=False), encoding="utf-8")
    before = failure_path.read_bytes()
    with patch.object(stage, "_save", side_effect=OSError("injected atomic-write failure")):
        assert missions.response("GetMissionRewardReq", failed, {"mission_id": 10008},
            account_path=failure_path)[1] == {"retcode": 1}
    assert failure_path.read_bytes() == before and failed == json.loads(before)
    checks.append("shared_mission_atomic_save_failure_returns_fail_and_preserves_memory_and_disk")
    # The same upgrade mechanism also applies when Stage WIN crosses the
    # threshold. Begin preview cannot issue bonuses; exact End replay cannot
    # issue them twice. Stamina bonus may exceed the native recovery cap.
    branch = deepcopy(original)
    branch["main"].update(exp=162, stamina=95)
    branch_path = out / "simulated-stage-levelup.json"
    branch_path.write_text(json.dumps(branch, ensure_ascii=False), encoding="utf-8")
    with patch.object(repeat.secrets, "randbelow", return_value=50):
        begun = stage.response("StageBeginReq", branch, {"stage_id": 10107,
            "avatar_id_list": [201, 101, 0]}, account_path=branch_path)[1]
    assert begun["retcode"] == 0
    assert (branch["main"]["level"], branch["main"]["exp"], branch["main"]["scoin"], branch["main"]["stamina"]) == (
        15, 162, original["main"]["scoin"], 89)
    end = end_request(10107, begun)
    packet = stage.response("StageEndReq", branch, end, account_path=branch_path)
    assert packet[1]["retcode"] == 0
    assert (branch["main"]["level"], branch["main"]["exp"], branch["main"]["stamina"]) == (16, 2, 127)
    assert branch["main"]["scoin"] == original["main"]["scoin"] + 750 + 800
    before = branch_path.read_bytes()
    assert stage.response("StageEndReq", branch, end, account_path=branch_path) == packet
    assert branch_path.read_bytes() == before
    for snap in stage.notification_snapshot(branch):
        proto.decode_message(snap[0], proto.encode_message(*snap))
    # A shared function handles multiple reached rows exactly, fails before
    # changing a caller if UInt32 overflow/source drift/capped EXP is unknown.
    multiple = {"level": 1, "exp": 0, "scoin": 0, "stamina": 80}
    audit_multi = captain.grant_player_exp(multiple, 51)
    assert multiple == {"level": 3, "exp": 0, "scoin": 250, "stamina": 102}
    assert len(audit_multi["level_rewards"]) == 2
    maximum = max(row["level"] for row in stage._table("playerleveldata"))
    for invalid in ({"level": maximum, "exp": 0, "scoin": 0, "stamina": 0},
                    {"level": 15, "exp": 162, "scoin": 0xFFFFFFFF, "stamina": 0}):
        unchanged = deepcopy(invalid)
        try:
            captain.grant_player_exp(invalid, 6)
            raise AssertionError("Unknown cap or reward overflow accepted")
        except ValueError:
            pass
        assert invalid == unchanged
    checks.append("stage_preview_no_bonus_win_captain_upgrade_once_overcap_stamina_multilevel_and_failure_atomic")
    assert SOURCE.read_bytes() == raw
    report = {"pass": True, "scope": "isolated synthetic protocol/business checks; human gameplay pending",
        "source": str(SOURCE), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_unchanged": True, "source_settlement_count": len(original["stage_runtime"]["settlements"]),
        "fixture_adjustments": {"stamina": 120, "captain_exp": "preserved_actual138"},
        "captain_progression_policy": captain.SOURCE_POLICY,
        "captain_table_sha256": captain.TABLE_SHA256,
        "legacy_supported_stages": list(stage.SUPPORTED_STAGE_IDS),
        "candidate_catalog_stages": list(stage.STORY_CATALOG_STAGE_IDS), "supported_missions": list(missions.SUPPORTED_MISSION_IDS),
        "audited_increment_sha256": stage.AUDITED_ACT102_INCREMENT_SHA256, "checks": checks,
        "chapter1_normal_source_inventory": audit,
        "repeat_policy": [repeat.probability_summary(stage.stage_config(i)) for i in range(10108, 10111)],
        "role_unlock": "10008..10010 contain no avatar card; existing mission10005 -> Mei201 retained"}
    (out / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    stage.STORY_RUNTIME_READY_FILE = real_readiness
    print(json.dumps({"pass": True, "checks": len(checks), "evidence": str(out / "verification.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
