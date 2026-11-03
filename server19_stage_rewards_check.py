"""One scoped rewards simulation using a read-only clone of the human save.

Synthetic queries/claims/Begin/End establish transactions and boundaries,
not human UI or authentic 1.9 economy. Repeated drops use the explicitly
user-authorized local conservative policy. No device/server calls.
Run: py -3.13 server19_stage_rewards_check.py
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
import secrets
from unittest.mock import patch

import server19_protocol as proto
import server19_stage as stage
import server19_stage_rewards as rewards
import server19_repeat_drops as repeat

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json"


def main():
    source_bytes = SOURCE.read_bytes()
    original = json.loads(source_bytes)
    assert original["stage_runtime"]["active"] is None
    assert set(range(10101, 10108)) <= rewards.missions._confirmed_wins(original)
    assert 10007 in original["mission_runtime"]["claimed_ids"]
    assert not original.get("stage_act_difficulty_list") and not original.get("act_reward_runtime")
    folder = ROOT / "server19-run/attack-research-data" / (
        "rewards-protocol-check-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4))
    folder.mkdir(parents=True)
    account = deepcopy(original)
    path = folder / "simulated-account.json"
    path.write_bytes(source_bytes)
    checks = []

    def request(act, difficulty, index):
        return {"act_id": act, "difficulty": difficulty, "challenge_num_index": index}

    def call(name, values=None):
        packet = rewards.response(name, account, values, account_path=path)
        proto.decode_message(packet[0], proto.encode_message(*packet))
        return packet

    assert rewards.star_count(account, 101, 1) == 15
    assert rewards.star_count(account, 102, 1) == 6
    initial = call("GetStageActDifficultyReq")
    assert initial[1] == {"retcode": 0, "act_difficulty_list": [
        {"act_id": 101, "difficulty": 1, "has_take_challenge_num_index": []},
        {"act_id": 102, "difficulty": 1, "has_take_challenge_num_index": []}]}
    assert path.read_bytes() == source_bytes
    for values, expected in ((request(101, 1, 0), 1), (request(101, 1, 4), 1),
                             (request(101, 2, 1), 1), (request(103, 1, 1), 1),
                             (request(102, 1, 1), 3), (request(101, 1, True), 1)):
        before = path.read_bytes()
        assert call("TakeStageActChallengeRewardReq", values)[1] == {"retcode": expected}
        assert path.read_bytes() == before
    checks.append("one_based_indices_act_difficulty_and_act102_six_star_boundary")

    # Only this simulation branch alters star inputs to check the 6/7 boundary.
    boundary = deepcopy(original)
    for row in boundary["stage_list"]:
        if 10101 <= row["id"] <= 10105:
            row["challenge_index_list"] = [0, 1] if row["id"] <= 10103 else []
    boundary_path = folder / "simulated-six-star-boundary.json"
    boundary_path.write_text(json.dumps(boundary, ensure_ascii=False), encoding="utf-8")
    before = boundary_path.read_bytes()
    assert rewards.response("TakeStageActChallengeRewardReq", boundary, request(101, 1, 1),
                            account_path=boundary_path)[1] == {"retcode": 3}
    assert boundary_path.read_bytes() == before
    boundary["stage_list"][0]["challenge_index_list"] = [0, 1, 2]
    boundary_path.write_text(json.dumps(boundary, ensure_ascii=False), encoding="utf-8")
    assert rewards.star_count(boundary, 101, 1) == 7
    assert rewards.response("TakeStageActChallengeRewardReq", boundary, request(101, 1, 1),
                            account_path=boundary_path)[1]["retcode"] == 0
    duplicate = deepcopy(original)
    duplicate["stage_list"][0]["challenge_index_list"] = [0, 0, 1]
    duplicate_path = folder / "simulated-invalid-star-indices.json"
    duplicate_path.write_text(json.dumps(duplicate, ensure_ascii=False), encoding="utf-8")
    before = duplicate_path.read_bytes()
    assert rewards.response("TakeStageActChallengeRewardReq", duplicate, request(101, 1, 1),
                            account_path=duplicate_path)[1] == {"retcode": 1}
    assert duplicate_path.read_bytes() == before
    no_wins = deepcopy(original)
    no_wins["stage_runtime"]["settlements"] = []
    assert rewards.star_count(no_wins, 101, 1) == 0
    checks.append("threshold6_reject7_accept_and_unique_receipted_stars_only")

    material_before = {row["id"]: row["num"] for row in account["material_list"]}
    main_before = deepcopy(account["main"])
    for index in (1, 2, 3):
        first = call("TakeStageActChallengeRewardReq", request(101, 1, index))
        assert first[1]["retcode"] == 0 and first[1]["challenge_num_index"] == index
        committed = path.read_bytes()
        assert call("TakeStageActChallengeRewardReq", request(101, 1, index)) == first
        assert path.read_bytes() == committed
    assert account["main"]["scoin"] == main_before["scoin"] + 9000
    assert account["main"]["hcoin"] == main_before["hcoin"] + 30
    for key in set(main_before) - {"scoin", "hcoin"}:
        assert account["main"][key] == main_before[key]
    materials = {row["id"]: row["num"] for row in account["material_list"]}
    assert materials[3000] == material_before.get(3000, 0) + 28
    assert materials[1001] == material_before.get(1001, 0) + 15
    assert all(materials[key] == count for key, count in material_before.items() if key not in (3000, 1001))
    assert call("GetStageActDifficultyReq")[1]["act_difficulty_list"][0]["has_take_challenge_num_index"] == [1, 2, 3]
    for packet in rewards.notification_snapshot(account):
        proto.decode_message(packet[0], proto.encode_message(*packet))
    checks.append("exact_three_tier_rewards_atomic_claim_and_idempotent_retry_snapshot")

    # Original imported claim marker must not create a fresh grant or a
    # fabricated successful receipt. Persisted quantity-limit failure rolls back.
    imported = deepcopy(original)
    imported["stage_act_difficulty_list"] = [{"act_id": 101, "difficulty": 1,
                                               "has_take_challenge_num_index": [1]}]
    imported_path = folder / "simulated-prior-claim.json"
    imported_path.write_text(json.dumps(imported, ensure_ascii=False), encoding="utf-8")
    before = imported_path.read_bytes()
    assert rewards.response("TakeStageActChallengeRewardReq", imported, request(101, 1, 1),
                            account_path=imported_path)[1] == {"retcode": 2}
    assert imported_path.read_bytes() == before
    full = deepcopy(original)
    next(row for row in full["material_list"] if row["id"] == 3000)["num"] = stage._item_metadata(3000)[1]["quantityLimit"]
    full_path = folder / "simulated-material-limit.json"
    full_path.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    before = full_path.read_bytes()
    assert rewards.response("TakeStageActChallengeRewardReq", full, request(101, 1, 1),
                            account_path=full_path)[1] == {"retcode": 1}
    assert full_path.read_bytes() == before
    checks.append("prior_claim_marker_and_material_limit_preserve_bytes")

    # No old test suite is rerun: repeat, first-clear and failure cases share
    # this one scoped check and each uses a retained private account copy.
    summaries = [repeat.probability_summary(stage.stage_config(identity))
                 for identity in stage.SUPPORTED_STAGE_IDS]
    assert all(row["material_percent"] == 49 and row["quantity"] == row["equipment_level"] == 1
               for row in summaries)
    assert next(row for row in summaries if row["stage_id"] == 10105)["no_item_percent"] == 51
    assert all(row["equipment_percent"] == 1 and row["no_item_percent"] == 50
               for row in summaries if row["stage_id"] != 10105)

    def fork(label, seed=None):
        value = deepcopy(original if seed is None else seed)
        target = folder / ("simulated-" + label + ".json")
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return value, target

    def end_values(begin, drops=None, status=stage.STAGE_WIN):
        body = proto.encode_message("StageEndReqBody", {"stage_id": 10107, "end_status": status,
            "stage_pass_time": 60, "challenge_index_list": [0, 1, 2],
            "drop_item_list": begin["drop_item_list"] if drops is None else drops,
            "scoin_reward": 0, "avatar_exp_reward": 0})
        return {"body": body, "sign": stage.stage_end_signature(body, begin["sign_key"])}

    repeat_request = {"stage_id": 10107, "avatar_id_list": [101, 201, 0]}
    for label, draws, category in (("repeat-material", [0, 0], "material"),
                                   ("repeat-equipment", [49, 0], "equipment"),
                                   ("repeat-no-item", [50], "none")):
        value, target = fork(label)
        old = deepcopy(value)
        with patch.object(repeat.secrets, "randbelow", side_effect=draws) as sampler:
            begin_packet = stage.response("StageBeginReq", value, repeat_request, account_path=target)
        begin = begin_packet[1]
        assert begin["retcode"] == 0 and begin["progress"] == 1
        assert sampler.call_count == len(draws)
        assert value["stage_runtime"]["active"]["drop_audit"]["selected_category"] == category
        assert len(begin["drop_item_list"]) == (0 if category == "none" else 1)
        if category != "none":
            item = begin["drop_item_list"][0]
            assert item["num"] == 1 and item["level"] == (0 if category == "material" else 1)
            assert item["item_id"] in stage.stage_config(10107)["displayDropList"]
        active_bytes = target.read_bytes()
        # A reconnect with a stale in-memory account still returns the same
        # exact saved Begin, with neither a policy read nor a second draw.
        with patch.object(repeat.secrets, "randbelow", side_effect=AssertionError("redraw")), \
                patch.object(repeat, "policy_snapshot", side_effect=AssertionError("policy reloaded")):
            assert stage.response("StageBeginReq", deepcopy(old), repeat_request, account_path=target) == begin_packet
        assert target.read_bytes() == active_bytes
        over = deepcopy(begin["drop_item_list"]) or [{"item_id": 4009, "level": 0, "num": 1}]
        if begin["drop_item_list"]:
            over[0]["num"] = 2
        assert stage.response("StageEndReq", value, end_values(begin, over), account_path=target)[1] == {"retcode": 3}
        assert target.read_bytes() == active_bytes
        signed = end_values(begin)
        with patch.object(repeat.secrets, "randbelow", side_effect=AssertionError("redraw")), \
                patch.object(repeat, "policy_snapshot", side_effect=AssertionError("policy reloaded")):
            end = stage.response("StageEndReq", value, signed, account_path=target)
        assert end[1]["retcode"] == 0 and end[1]["challenge_list"] == []
        assert (end[1]["player_exp_reward"], end[1]["avatar_exp_reward"], end[1]["scoin_reward"]) == (6, 26, 750)
        assert value["main"]["scoin"] == old["main"]["scoin"] + 750
        assert value["main"]["hcoin"] == old["main"]["hcoin"]
        assert value["main"]["stamina"] == old["main"]["stamina"] - 6
        assert value["main"]["exp"] == old["main"]["exp"] + 6
        for identity in (101, 201):
            current = next(row for row in value["avatar_list"] if row["avatar_id"] == identity)
            prior = next(row for row in old["avatar_list"] if row["avatar_id"] == identity)
            # Count cumulative experience from deployed level thresholds to
            # verify both occupied members receive26 without assuming a level.
            rows = stage._table("avatarleveldata")
            cumulative = lambda row: row["exp"] + sum(x["exp"] for x in rows if x["level"] < row["level"])
            assert cumulative(current) - cumulative(prior) == 26
        assert value["stage_runtime"]["settlements"][:-1] == old["stage_runtime"]["settlements"]
        assert value["mission_runtime"] == old["mission_runtime"]
        assert value["stage_list"][-1]["challenge_index_list"] == old["stage_list"][-1]["challenge_index_list"]
        if category == "none":
            assert value["material_list"] == old["material_list"] and value["stigmata_list"] == old["stigmata_list"]
        elif category == "material":
            old_materials = {row["id"]: row["num"] for row in old["material_list"]}
            new_materials = {row["id"]: row["num"] for row in value["material_list"]}
            assert new_materials[4009] == old_materials.get(4009, 0) + 1
            assert all(new_materials[key] == count for key, count in old_materials.items() if key != 4009)
        else:
            assert value["stigmata_list"][:-1] == old["stigmata_list"]
            assert value["stigmata_list"][-1]["id"] == 30054 and value["stigmata_list"][-1]["level"] == 1
            assert value["material_list"] == old["material_list"]
        settled = target.read_bytes()
        assert stage.response("StageEndReq", deepcopy(old), signed, account_path=target) == end
        assert target.read_bytes() == settled
    checks.append("local49_1_50_one_slot_all_outcomes_retry_reconnect_no_redraw_signed_bounded_end_no_first_clear_or_star_regrant")

    first, first_path = fork("first-clear-backward-plan")
    saved = next(row for row in first["stage_list"] if row["id"] == 10107)
    saved.update(progress=0, is_done=False, challenge_index_list=[])
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    with patch.object(repeat.secrets, "randbelow", side_effect=AssertionError("first clear used repeat RNG")):
        packet = stage.response("StageBeginReq", first, repeat_request, account_path=first_path)
    assert packet[1]["retcode"] == 0 and packet[1]["drop_item_list"] == stage.first_clear_drop_plan(stage.stage_config(10107))
    assert first["stage_runtime"]["active"]["drop_policy"] == stage.FIRST_CLEAR_DROP_POLICY
    assert "drop_audit" not in first["stage_runtime"]["active"]
    assert stage._has_audited_active_plan(first["stage_runtime"]["active"], stage.stage_config(10107))
    checks.append("exact_first_clear_and_legacy_active_plan_shape_unchanged")

    # Saving/serialization errors must not expose or persist transaction copy
    # rewards/active state. The notification serialization is checked pre-save.
    for module, name, values in ((rewards, "TakeStageActChallengeRewardReq", request(101, 1, 1)),
                                 (stage, "StageBeginReq", repeat_request)):
        for failure in ("save", "serialization"):
            value, target = fork(name + "-" + failure)
            previous = deepcopy(value)
            data = target.read_bytes()
            encoder = proto.encode_message
            def fail_packet(packet_name, body):
                if packet_name == name[:-3] + "Rsp":
                    raise ValueError("simulated response serialization failure")
                return encoder(packet_name, body)
            manager = patch.object(stage, "_save", side_effect=OSError("simulated atomic write failure")) \
                if failure == "save" else patch.object(proto, "encode_message", side_effect=fail_packet)
            with manager:
                assert module.response(name, value, values, account_path=target)[1] == {"retcode": 1}
            assert target.read_bytes() == data and value == previous
    checks.append("save_and_response_serialization_failure_return_fail_without_publishing_copy")

    for key in ("stage_list", "stage_runtime", "mission_data", "mission_runtime",
                "avatar_list", "weapon_list", "stigmata_list", "guide_id_list"):
        if key in original:
            assert account[key] == original[key]
    assert SOURCE.read_bytes() == source_bytes
    checks.append("human_seven_wins_mission10007_older_receipts_and_source_preserved")
    report = {"status": "passed",
        "kind": "isolated_protocol_simulation_not_human_acceptance",
        "checks": checks, "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_unmodified": True, "historical19_economy_recovered": False,
        "repeat_begin_end_restored": True, "repeat_policy": repeat.SOURCE_POLICY,
        "probability_summary": summaries, "human_repeat_and_star_reward_ui_acceptance": "pending",
        "directory": str(folder)}
    (folder / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
