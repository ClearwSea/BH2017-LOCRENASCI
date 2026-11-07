"""Targeted 10107/10007 protocol simulation in retained isolated account copies.

Run: py -3.13 server19_stage10107_check.py
The source six-WIN account is read only. Synthetic Begin/WIN/claim packets
prove transaction checks, not human combat, original UI, or historical 1.9
reward fidelity. The deployed configuration is adapted from 2.4. No device,
server process, original account, resources or client locks are modified.
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

import server19_initialization as initialization
import server19_missions as missions
import server19_protocol as proto
import server19_stage as stage

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "server19-run/black3d-repair/local-comparison-1791780361/scratch-server/account.json"


def main():
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    assert set(range(10101, 10107)) <= missions._confirmed_wins(source), "Need actual six-WIN input"
    assert source["mission_runtime"]["claimed_ids"] == list(range(10001, 10007))
    assert source["stage_runtime"]["active"] is None
    assert not any(row["id"] == 10107 for row in source["stage_list"])
    directory = ROOT / "server19-run/attack-research-data" / (
        "stage10107-protocol-check-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4))
    directory.mkdir(parents=True)
    assert directory.resolve().is_relative_to(ROOT.resolve())
    account = deepcopy(source)
    path = directory / "simulated-account.json"
    path.write_bytes(source_bytes)
    checks = []

    def call(module, name, values=None):
        packet = module.response(name, account, values, account_path=path)
        # The actual serializer/deserializer validates response field shapes.
        proto.decode_message(packet[0], proto.encode_message(*packet))
        return packet

    # Inspect deployed rows through the same bounded audits used for runtime.
    config = stage.stage_config(10107)
    catalog = missions.mission_catalog()
    assert config["sectionId"] == 2 and config["actId"] == 102 and config["preLevelID"] == [10106]
    assert catalog[10007]["predecessor"] == 10006
    assert catalog[10007]["reward"] == {"exp": 12, "scoin": 610, "hcoin": 0,
        "stamina": 0, "skill_point": 0, "friends_point": 0, "duty_point": 0, "item_list": []}
    assert next(row for row in stage._table("unlockuidata") if row["id"] == 2) == {
        "id": 2, "unlockTarget": "", "unlockByMission": 10007,
        "OnDoing": 0, "OnFinish": 1, "OnClose": 1, "unlockByTutorial": 0}
    checks.append("deployed24_10107_section_rewards_10007_and_unlockui2_audited")

    before = deepcopy(account)
    packet = initialization.response("GetStageDataReq", account)
    decoded = proto.decode_message(packet[0], proto.encode_message(*packet))
    available = next(row for row in decoded["stage_list"] if row["id"] == 10107)
    assert available["progress"] == 0 and available["is_done"] is False
    assert account == before and path.read_bytes() == source_bytes
    mission_rows = call(missions, "GetMissionDataReq")[1]["mission_list"]
    assert next(row for row in mission_rows if row["mission_id"] == 10007) == {
        "mission_id": 10007, "status": missions.MISSION_DOING, "progress": 0}
    pending = path.read_bytes()
    assert call(missions, "GetMissionRewardReq", {"mission_id": 10007})[1] == {"retcode": 3}
    assert path.read_bytes() == pending
    checks.append("natural_stage_query_zero_progress_and_mission10007_doing_no_early_claim")

    # A separate rejected branch cannot overwrite either the source or the
    # successful branch. It deliberately removes prerequisite evidence only
    # inside this simulated test copy.
    locked = deepcopy(source)
    locked["stage_list"] = [row for row in locked["stage_list"] if row["id"] != 10106]
    locked_path = directory / "simulated-missing-prerequisite.json"
    locked_path.write_text(json.dumps(locked, ensure_ascii=False), encoding="utf-8")
    locked_bytes = locked_path.read_bytes()
    assert stage.response("StageBeginReq", locked, {"stage_id": 10107,
        "avatar_id_list": [101, 0, 0]}, account_path=locked_path)[1] == {"retcode": 34}
    assert locked_path.read_bytes() == locked_bytes
    snapshot = path.read_bytes()
    assert call(stage, "StageBeginReq", {"stage_id": 10108,
        "avatar_id_list": [101, 0, 0]})[1] == {"retcode": 2}
    assert path.read_bytes() == snapshot
    checks.append("prerequisite10106_and_out_of_scope10108_rejected_without_write")

    old_levels = deepcopy(account["stage_list"])
    old_settlements = deepcopy(account["stage_runtime"]["settlements"])
    old_claims = deepcopy(account["mission_runtime"])
    before_main = deepcopy(account["main"])
    before_avatars = deepcopy(account["avatar_list"])
    before_stigmata = deepcopy(account["stigmata_list"])
    before_materials = {row["id"]: row["num"] for row in account["material_list"]}
    assert before_main["level"] == 15 and before_main["exp"] == 108
    avatar = next(row for row in before_avatars if row["avatar_id"] == 101)
    assert (avatar["level"], avatar["exp"]) == (5, 34)
    begin = call(stage, "StageBeginReq", {"stage_id": 10107, "avatar_id_list": [101, 0, 0]})[1]
    assert begin["retcode"] == 0 and begin["progress"] == 0
    assert account["main"]["stamina"] == before_main["stamina"] - 6
    assert [(row["item_id"], row["level"], row["num"]) for row in begin["drop_item_list"]] == [
        (4009, 0, 3), (3000, 0, 4), (30054, 1, 1), (120010, 0, 1)]
    body = proto.encode_message("StageEndReqBody", {"stage_id": 10107,
        "end_status": stage.STAGE_WIN, "stage_pass_time": 60,
        "challenge_index_list": [0, 1, 2], "drop_item_list": begin["drop_item_list"],
        "scoin_reward": 0, "avatar_exp_reward": 0})
    values = {"body": body, "sign": stage.stage_end_signature(body, begin["sign_key"])}
    active_bytes = path.read_bytes()
    assert call(stage, "StageEndReq", {"body": body, "sign": "0" * 64})[1] == {"retcode": 2}
    assert path.read_bytes() == active_bytes
    end = call(stage, "StageEndReq", values)
    assert end[1]["retcode"] == 0 and end[1]["progress"] == 1
    assert (end[1]["player_exp_reward"], end[1]["avatar_exp_reward"], end[1]["scoin_reward"]) == (6, 26, 750)
    assert account["main"]["exp"] == before_main["exp"] + 6
    assert account["main"]["scoin"] == before_main["scoin"] + 750
    assert account["main"]["hcoin"] == before_main["hcoin"] + 15
    avatar = next(row for row in account["avatar_list"] if row["avatar_id"] == 101)
    assert (avatar["level"], avatar["exp"]) == (6, 5)  # 34 + 26 - configured level5 requirement55
    assert [row for row in account["avatar_list"] if row["avatar_id"] != 101] == [
        row for row in before_avatars if row["avatar_id"] != 101]
    assert account["stigmata_list"][:-1] == before_stigmata
    assert account["stigmata_list"][-1]["id"] == 30054 and account["stigmata_list"][-1]["level"] == 1
    materials = {row["id"]: row["num"] for row in account["material_list"]}
    assert {identity: materials[identity] - before_materials.get(identity, 0)
            for identity in (4009, 3000, 120010)} == {4009: 3, 3000: 4, 120010: 1}
    settled_bytes = path.read_bytes()
    assert call(stage, "StageEndReq", values) == end and path.read_bytes() == settled_bytes
    checks.append("signed_simulated_win_rewards_and_exact_settlement_retry_once")

    mission_rows = call(missions, "GetMissionDataReq")[1]["mission_list"]
    assert next(row for row in mission_rows if row["mission_id"] == 10007) == {
        "mission_id": 10007, "status": missions.MISSION_FINISH, "progress": 1}
    # Saved progress without a successful WIN settlement must remain DOING.
    no_receipt = deepcopy(account)
    no_receipt["stage_runtime"]["settlements"] = deepcopy(old_settlements)
    missions.synchronize(no_receipt)
    assert next(row for row in no_receipt["mission_data"]["mission_list"]
                if row["mission_id"] == 10007)["status"] == missions.MISSION_DOING
    before_claim = deepcopy(account)
    claimed = call(missions, "GetMissionRewardReq", {"mission_id": 10007})
    assert claimed[1] == {"retcode": 0, "reward_list": [catalog[10007]["reward"]]}
    assert account["main"]["exp"] == before_claim["main"]["exp"] + 12
    assert account["main"]["scoin"] == before_claim["main"]["scoin"] + 610
    for key in ("weapon_list", "stigmata_list", "material_list", "avatar_list"):
        assert account[key] == before_claim[key]
    closed = call(missions, "GetMissionDataReq")[1]["mission_list"]
    assert next(row for row in closed if row["mission_id"] == 10007) == {
        "mission_id": 10007, "status": missions.MISSION_CLOSE, "progress": 1}
    claimed_bytes = path.read_bytes()
    assert call(missions, "GetMissionRewardReq", {"mission_id": 10007}) == claimed
    assert path.read_bytes() == claimed_bytes
    checks.append("10007_requires_win_then_finish_claim_close_with_idempotent_reward")

    assert account["stage_list"][:len(old_levels)] == old_levels
    assert account["stage_runtime"]["settlements"][:len(old_settlements)] == old_settlements
    assert account["mission_runtime"]["claimed_ids"][:-1] == old_claims["claimed_ids"]
    assert account["mission_runtime"]["receipts"][:-1] == old_claims["receipts"]
    assert SOURCE.read_bytes() == source_bytes
    checks.append("original_six_levels_win_and_claim_receipts_and_source_file_preserved")
    report = {"status": "passed", "test_kind": "isolated_protocol_simulation_not_human_acceptance",
        "source_account": str(SOURCE), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_unmodified": True, "historical19_rewards_recovered": False,
        "configuration_policy": "deployed_filtered24_compatibility",
        "checks": checks, "simulation_directory": str(directory),
        "human_stage10107_and_skilltab_acceptance": "pending"}
    (directory / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
