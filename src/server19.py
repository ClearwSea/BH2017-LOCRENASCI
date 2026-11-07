"""Small local 1.9 server: original packet format and response types.

The persisted account is a bounded development fixture, not an official save.
Unknown mutations stay unsupported; empty collections do not implement business.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import socketserver
import threading
import time
import traceback

import server19_http
import server19_protocol as proto
import server19_initialization
import server19_stage
import server19_battle_session
import server19_extra_story
import server19_openworld
import server19_endless
import server19_stage_display
import server19_equipment
import server19_profile
import server19_missions
import server19_avatar_skills
import server19_avatar_cultivation
import server19_avatar_teams
import server19_stage_rewards
import server19_friends
import server19_gacha
import server19_recharge
import server19_exchange
import server19_signin
import server19_bulletin
import server19_newbie
import server19_shop
import server19_galtouch
import server19_cabin

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "server19-run"
LOCK = threading.Lock()
LOCAL_RECHARGE_ENABLED = False


def event(kind, **values):
    row = {"time": time.time(), "event": kind, **values}
    text = json.dumps(row, ensure_ascii=False)
    with LOCK:
        RUN.mkdir(exist_ok=True)
        with (RUN / "server-events.jsonl").open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)


def load_account():
    path = RUN / "account.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1:
            raise ValueError("Unsupported account schema; original file preserved")
        if "is_first_login" not in data:
            # Migrate only our authored existing-account fixture. This records
            # the previous fixture policy, not completion of the first stage
            # or of any tutorial, and does not infer official save progress.
            if data.get("fixture") != "server19-single-avatar-initialization":
                raise ValueError("Account login state is unspecified; original file preserved")
            backup = path.with_name("account-before-explicit-login-state.json")
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
            data.update(account_mode="existing-development-account", is_first_login=False)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not isinstance(data["is_first_login"], bool):
            raise ValueError("Account first-login state must be explicit boolean")
        if data.get("fixture") == "server19-single-avatar-initialization":
            # Old authored fixtures omitted ordinary-stage availability. Keep
            # explicit lists (including intentionally empty lists) and imported
            # account state intact. Supply only the original first story stage,
            # with zero completions; native handlers choose the act and page.
            if "stage_list" not in data:
                backup = path.with_name("account-before-explicit-stage-availability.json")
                if not backup.exists():
                    backup.write_bytes(path.read_bytes())
                data["stage_list"] = server19_initialization.initial_story_stage_list()
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            # Original GalTouchModule.OnGetAvatarDataRsp requires both nullable
            # accumulated-feel fields to be present before it creates an item.
            # Initialize only our authored fixture, without changing any stored
            # nonzero value or inferring progress from an imported save. Native
            # conversion also requires the separately supplied TouchLevel table.
            feel_fields = ("touch_goodfeel", "stage_goodfeel")
            missing = [(avatar, key) for avatar in data["avatar_list"]
                       for key in feel_fields if key not in avatar]
            for avatar in data["avatar_list"]:
                for key in feel_fields:
                    if key in avatar and (type(avatar[key]) is not int or
                                          not 0 <= avatar[key] <= 0xFFFFFFFF):
                        raise ValueError("Avatar accumulated-feel state must be UInt32")
            if missing:
                backup = path.with_name("account-before-explicit-avatar-feel.json")
                if not backup.exists():
                    backup.write_bytes(path.read_bytes())
                for avatar, key in missing:
                    avatar[key] = 0
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    account = {"schema": 1, "fixture": "server19-single-avatar-initialization", "uid": 1024,
        "account_mode": "existing-development-account", "is_first_login": False,
        "main": {"nickname": "本地测试舰长", "level": 15, "exp": 0,
                 "hcoin": 0, "scoin": 0, "stamina": 60, "skill_point": 0,
                 "skill_point_limit": 20, "equipment_size_limit": 100,
                 "assistant_avatar_id": 101, "self_desc": ""},
        "avatar_list": [{"avatar_id": 101, "star": 1, "level": 1, "exp": 0,
                         "fragment": 0, "weapon_unique_id": 1,
                         "touch_goodfeel": 0, "stage_goodfeel": 0,
                         "stigmata_unique_id_1": 0, "stigmata_unique_id_2": 0,
                         "stigmata_unique_id_3": 0}],
        "weapon_list": [{"unique_id": 1, "id": 20001, "level": 1, "exp": 0,
                         "is_protected": False}],
        "stigmata_list": [], "material_list": [],
        "stage_list": server19_initialization.initial_story_stage_list()}
    RUN.mkdir(exist_ok=True)
    path.write_text(json.dumps(account, ensure_ascii=False, indent=2), encoding="utf-8")
    return account


def response(name, account, request_values=None, *, account_path=None):
    endless = server19_endless.response(name, account, request_values, account_path=account_path)
    if endless is not None:
        return endless
    world = server19_openworld.response(name, account, request_values, account_path=account_path)
    if world is not None:
        return world
    recharge = server19_recharge.response(name, account, request_values,
                                         account_path=account_path, enabled=LOCAL_RECHARGE_ENABLED)
    if recharge is not None:
        return recharge
    if name == "GetMainDataReq":
        return server19_avatar_skills.sync_skill_point(account, account_path=account_path)
    for module in (server19_avatar_teams, server19_stage_rewards):
        result = module.response(name, account, request_values, account_path=account_path)
        if result is not None:
            return result
    for cultivation in (server19_avatar_skills, server19_avatar_cultivation):
        result = cultivation.response(name, account, request_values, account_path=account_path)
        if result is not None:
            return result
    profile_result = server19_profile.response(name, account, request_values,
                                             account_path=account_path)
    if profile_result is not None:
        return profile_result
    mission_result = server19_missions.response(name, account, request_values,
                                             account_path=account_path)
    if mission_result is not None:
        return mission_result
    extra_result = server19_extra_story.response(name, account, request_values, account_path=account_path)
    if extra_result is not None:
        return extra_result
    display_result = server19_stage_display.response(name, account, request_values,
                                                   account_path=account_path)
    if display_result is not None:
        return display_result
    stage_result = server19_stage.response(name, account, request_values,
                                         account_path=account_path)
    if stage_result is not None:
        return stage_result
    equipment_result = server19_equipment.response(name, account, request_values,
                                                 account_path=account_path)
    if equipment_result is not None:
        return equipment_result
    friends = server19_friends.response(name, account, request_values)
    if friends is not None:
        return friends
    gacha = server19_gacha.response(name, account, request_values,
                                    account_path=account_path)
    if gacha is not None:
        return gacha
    exchange_result = server19_exchange.response(name, account, request_values,
                                                account_path=account_path)
    if exchange_result is not None:
        return exchange_result
    signin_result = server19_signin.response(name, account, request_values,
                                             account_path=account_path)
    if signin_result is not None:
        return signin_result
    bulletin_result = server19_bulletin.response(name, account, request_values,
                                                 account_path=account_path)
    if bulletin_result is not None:
        return bulletin_result
    newbie_result = server19_newbie.response(name, account, request_values,
                                             account_path=account_path)
    if newbie_result is not None:
        return newbie_result
    shop_result = server19_shop.response(name, account, request_values,
                                         account_path=account_path)
    if shop_result is not None:
        return shop_result
    galtouch_result = server19_galtouch.response(name, account, request_values,
                                                 account_path=account_path)
    if galtouch_result is not None:
        return galtouch_result
    cabin_result = server19_cabin.response(name, account, request_values,
                                           account_path=account_path)
    if cabin_result is not None:
        return cabin_result
    specialized = server19_initialization.response(name, account, request_values)
    if specialized is not None:
        return specialized
    uid = account["uid"]
    if name == "GetPlayerTokenReq":
        return "GetPlayerTokenRsp", {"retcode": 0, "uid": uid,
                "token": "server19-local-only", "account_uid": str(uid), "account_type": 1}
    if name == "PlayerLoginReq":
        return "PlayerLoginRsp", {"retcode": 0, "is_first_login": account["is_first_login"],
                                   "region_name": "server19-local"}
    if name == "GetMainDataReq":
        return "GetMainDataRsp", {"retcode": 0, **account["main"]}
    if name == "GetConfigReq":
        return "GetConfigRsp", {"retcode": 0, "server_cur_time": int(time.time()),
                # Original Config consumer overwrites both constructor limits
                # unconditionally; omitted scalar fields become zero and make
                # unchanged balances trigger a cap dialog during scene loading.
                "scoin_limit": 100000000, "friends_point_limit": 100000,
                "stamina_recover_config_time": 7200, "skill_point_recover_config_time": 7200,
                "avatar_revive_hcoin_cost": 0, **server19_equipment.POWER_UP_CONFIG,
                "day_time_offset": 14400, "max_friend_num": 100,
                "endless_min_player_level": 25,
                "endless_max_progress": 0,
                "avatar_max_add_goodfeel": 99999999,
                "region_name": "server19-local"}
    if name == "GetEquipmentDataReq":
        materials = [m for m in account.get("material_list", []) if m.get("num", 0) > 0]
        return "GetEquipmentDataRsp", {"retcode": 0,
                                       "weapon_list": account.get("weapon_list", []),
                                       "stigmata_list": account.get("stigmata_list", []),
                                       "material_list": materials}
    if name == "GetAvatarDataReq":
        avatars = [{"stigmata_unique_id_1": 0, "stigmata_unique_id_2": 0,
                    "stigmata_unique_id_3": 0, **avatar} for avatar in account["avatar_list"]]
        return "GetAvatarDataRsp", {"retcode": 0, "avatar_list": avatars}
    if name == "KeepAliveNotify":
        return "KeepAliveNotify", {}
    if name.endswith("Req"):
        rsp = name[:-3] + "Rsp"
        if rsp in proto.CMD_IDS and rsp in proto.CMD_NAMES.values():
            schema = proto.schema(rsp)
            fields = {f["name"] for f in schema["fields"]}
            # Only read-only initialization queries get valid empty state.
            if name.startswith("Get"):
                return rsp, {"retcode": 0} if "retcode" in fields else {}
            return rsp, {"retcode": 1} if "retcode" in fields else None
    return None, None


class GameHandler(socketserver.BaseRequestHandler):
    def handle(self):
        event("game_connected", peer=self.client_address[0])
        account = load_account()
        session = server19_battle_session.Session()
        buffer = bytearray()
        packet_id = 0
        self.request.settimeout(120)
        try:
            while True:
                data = self.request.recv(65536)
                if not data:
                    break
                buffer.extend(data)
                for frame in proto.take_frames(buffer):
                    request_started = time.perf_counter()
                    with session.frame(frame.name, account, RUN / "account.json", event):
                        name = frame.name
                        event("game_request", command=name, cmd_id=frame.cmd_id, body_size=len(frame.body))
                        request_values = proto.decode_message(name, frame.body)
                        if name in ("StageBeginReq", "StageEndReq", "FinishGuideReportReq", "AvatarReviveReq"):
                            # Original serialized payloads are preserved as evidence
                            # for stage entry/exit, rather than inferred from UI.
                            event("game_stage_wire", command=name,
                                  body_hex=frame.body.hex(),
                                  client_version=frame.client_version)
                        if name in server19_avatar_teams.MUTATION_REQUESTS:
                            event("game_avatar_team_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name == "TakeStageActChallengeRewardReq":
                            event("game_act_reward_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in server19_equipment.HANDLED_REQUESTS:
                            event("game_equipment_wire", command=name,
                                  body_hex=frame.body.hex(),
                                  client_version=frame.client_version)
                        if name in server19_profile.HANDLED_REQUESTS:
                            event("game_profile_wire", command=name,
                                  body_hex=frame.body.hex(),
                                  client_version=frame.client_version)
                        if name in (server19_avatar_skills.HANDLED_REQUESTS |
                                    server19_avatar_cultivation.HANDLED_REQUESTS):
                            event("game_avatar_cultivation_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in ("GetMissionRewardReq", "TakeDutyRewardReq"):
                            event("game_mission_wire" if name == "GetMissionRewardReq" else "game_duty_wire",
                                  command=name,
                                  body_hex=frame.body.hex(),
                                  client_version=frame.client_version)
                        if name in server19_gacha.HANDLED_REQUESTS:
                            event("game_gacha_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in server19_exchange.HANDLED_REQUESTS:
                            event("game_exchange_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in server19_signin.HANDLED_REQUESTS:
                            event("game_signin_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in server19_bulletin.HANDLED_REQUESTS:
                            event("game_bulletin_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in server19_newbie.HANDLED_REQUESTS:
                            event("game_newbie_wire", command=name,
                                  body_hex=frame.body.hex(), client_version=frame.client_version)
                        if name in server19_stage_display.HANDLED_REQUESTS:
                            event("game_stage_display_request", command=name,
                                  stage_ids=request_values.get("stage_id_list", []))
                        # Empty heartbeat neither reads nor mutates account data.
                        # Business requests still refresh/roll over before handling.
                        if name != "KeepAliveNotify":
                            server19_stage.refresh_account(account, RUN / "account.json")
                        rsp_name, values = response(name, account, request_values,
                                                   account_path=RUN / "account.json")
                        if rsp_name is None or values is None:
                            event("game_unsupported", command=name)
                            continue
                        packets = [(rsp_name, values)]
                        if name == "FinishGuideReportReq" and values.get("retcode") == 0:
                            packets = server19_stage.guide_notification_snapshot(account, request_values) + packets
                        if name == "GetSignInRewardReq" and values.get("retcode") == 0:
                            materials = [m for m in account.get("material_list", []) if m.get("num", 0) > 0]
                            packets = [
                                ("GetMainDataRsp", {"retcode": 0, **account["main"]}),
                                ("GetEquipmentDataRsp", {
                                    "retcode": 0,
                                    "weapon_list": account.get("weapon_list", []),
                                    "stigmata_list": account.get("stigmata_list", []),
                                    "material_list": materials,
                                }),
                            ] + packets
                            event("game_signin_reward_committed",
                                  signed_days=account.get("sign_in_runtime", {}).get("signed_days"))
                        if name == "ManualRefreshShopReq" and values.get("retcode") == 0:
                            packets = [server19_shop.get_shop_list_rsp(account, RUN / "account.json")] + packets
                            event("game_shop_manual_refresh", sid=request_values.get("shop_id"))
                        if name == "BuyGoodsReq" and values.get("retcode") == 0:
                            materials = [m for m in account.get("material_list", []) if m.get("num", 0) > 0]
                            packets = [
                                ("GetMainDataRsp", {"retcode": 0, **account["main"]}),
                                ("GetAvatarDataRsp", {"retcode": 0, "avatar_list": deepcopy(account.get("avatar_list", []))}),
                                ("GetEquipmentDataRsp", {
                                    "retcode": 0,
                                    "weapon_list": account.get("weapon_list", []),
                                    "stigmata_list": account.get("stigmata_list", []),
                                    "material_list": materials,
                                }),
                                server19_shop.get_shop_list_rsp(account, RUN / "account.json"),
                            ] + packets
                            event("game_shop_buy_committed", goods_id=values.get("goods_id"), shop_id=values.get("shop_id"))
                        if name in ("ScoinExchangeReq", "StaminaExchangeReq", "SkillPointExchangeReq") and values.get("retcode") == 0:
                            packets = [("GetMainDataRsp", {"retcode": 0, **account["main"]})] + packets
                            event("game_exchange_committed",
                                  command=name,
                                  main=account["main"])
                        if name in ("TakeNewbieLoginRewardReq", "TakeNewbieLevelRewardReq") and values.get("retcode") == 0:
                            materials = [m for m in account.get("material_list", []) if m.get("num", 0) > 0]
                            packets = [
                                ("GetMainDataRsp", {"retcode": 0, **account["main"]}),
                                ("GetAvatarDataRsp", {"retcode": 0, "avatar_list": deepcopy(account.get("avatar_list", []))}),
                                ("GetEquipmentDataRsp", {
                                    "retcode": 0,
                                    "weapon_list": account.get("weapon_list", []),
                                    "stigmata_list": account.get("stigmata_list", []),
                                    "material_list": materials,
                                }),
                            ] + packets
                            event("game_newbie_reward_committed",
                                  command=name,
                                  main=account["main"])
                        if LOCAL_RECHARGE_ENABLED and name == 'GetVipRewardReq' and values.get('retcode') == 0:
                            import server19_recharge_welfare as welfare
                            packets = welfare.notification_snapshot(account) + packets
                            event('game_local_welfare', levels=request_values.get('vip_level_list'),
                                  new_rewards=len(values.get('reward_list', [])), total_pay_hcoin=welfare.total(account))
                        if LOCAL_RECHARGE_ENABLED and name == 'ReportClickRechargeButtonNotify':
                            if rsp_name == 'RechargeFinishNotify' and values.get('retcode') == 0:
                                # Native success handler builds its reward dialog from PlayerModule.
                                packets = server19_recharge.notification_snapshot(account) + packets
                            event('game_local_recharge', product=request_values.get('product_name'),
                                  outcome=rsp_name, retcode=values.get('retcode'),
                                  granted=values.get('pay_hcoin', 0), hcoin=account['main'].get('hcoin'))
                        if name in server19_equipment.HANDLED_REQUESTS and values.get('retcode') != 0:
                            event('game_equipment_rejected', command=name,
                                  retcode=values.get('retcode'),
                                  diagnostic=server19_equipment.rejection_detail(name))
                        if name in server19_avatar_teams.MUTATION_REQUESTS and values.get("retcode") == 0:
                            # Cmd49 is a Notify with no fictional Cmd49Rsp. Its
                            # handler returns the original Cmd48 full snapshot.
                            # Preset Cmd270 consumes the updated team objects first.
                            if name == "UpdateCustomAvatarTeamReq":
                                packets = server19_avatar_teams.notification_snapshot(account) + packets
                            event("game_avatar_team_committed", command=name,
                                  avatar_team_list=account.get("avatar_team_list", []),
                                  custom_avatar_team_list=account.get("custom_avatar_team_list", []))
                        if name == "TakeStageActChallengeRewardReq" and values.get("retcode") == 0:
                            # Both native reward views redraw on Rsp559; Cmd557
                            # must update LevelModule's claim state first.
                            snapshots = server19_stage_rewards.notification_snapshot(account)
                            packets = [snapshots[-1]] + packets + snapshots[:-1]
                            event("game_act_reward_committed",
                                  act_id=request_values.get("act_id"),
                                  difficulty=request_values.get("difficulty"),
                                  challenge_num_index=request_values.get("challenge_num_index"),
                                  act_difficulty_list=account.get("stage_act_difficulty_list", []),
                                  main=account["main"])
                        for cultivation in (server19_avatar_skills, server19_avatar_cultivation):
                            if name in cultivation.HANDLED_REQUESTS and values.get("retcode") == 0:
                                # Native Rsp36/Rsp51 immediately inspect existing
                                # avatar/skill objects; snapshots precede the result.
                                snapshots = (cultivation.notification_snapshot(account, request_values.get('avatar_id'))
                                    if cultivation is server19_avatar_cultivation
                                    else cultivation.notification_snapshot(account))
                                packets = snapshots + packets
                                event("game_avatar_cultivation_committed", command=name,
                                      main=account["main"], avatars=account["avatar_list"],
                                      materials=account["material_list"])
                        if name in server19_profile.HANDLED_REQUESTS and values.get("retcode") == 0:
                            packets.extend(server19_profile.notification_snapshot(account))
                            event("game_profile_committed", command=name,
                                  nickname=account["main"].get("nickname"),
                                  self_desc=account["main"].get("self_desc"))
                        if name in server19_cabin.MUTATION_REQUESTS and values.get("retcode") == 0:
                            packets.extend(server19_cabin.notification_snapshot(account, command=name))
                            event("game_cabin_committed", command=name,
                                  cabin_list=account.get("cabin_list"),
                                  scoin=account["main"].get("scoin"),
                                  hcoin=account["main"].get("hcoin"))
                        if name in server19_gacha.MUTATION_REQUESTS and values.get("retcode") == 0:
                            # OnGachaRsp ends by calling UpdateView immediately.
                            # Refresh wallet/storage before it reads ticket counts;
                            # keep avatar ownership after the result so unlock
                            # dialogs still see the pre-pull ownership state.
                            snapshots = server19_gacha.notification_snapshot(account)
                            if name == "BuyGachaTicketReq":
                                packets = snapshots + packets
                            else:
                                before = [p for p in snapshots if p[0] != "GetAvatarDataRsp"]
                                after = [p for p in snapshots if p[0] == "GetAvatarDataRsp"]
                                packets = before + packets + after
                            event("game_gacha_committed", command=name,
                                  hcoin=account["main"].get("hcoin"),
                                  friends_point=account["main"].get("friends_point"),
                                  materials=account.get("material_list", []),
                                  duty=account.get("duty_runtime", {}).get("progress"),
                                  guidance=account.get("guidance_runtime", {}).get("done"))
                        if name == "AvatarReviveReq" and values.get("retcode") == 0:
                            packets.extend(server19_stage.revive_notification_snapshot(account))
                        if name in server19_endless.REQUESTS and server19_endless.CATALOG is not None:
                            packets.extend(server19_endless.notification_snapshot(name, account, values.get('retcode')))
                            if name == 'EndlessStageBeginReq':
                                event('game_endless_begin_result', team=request_values.get('avatar_id_list'),
                                      retcode=values.get('retcode'),
                                      dead_avatars=[h['avatar_id'] for h in account.get('endless_runtime', {}).get('hp', []) if h.get('is_die')])
                            if values.get('retcode') == 0 and name in ('EndlessStageEndReq', 'GetLastEndlessRewardDataReq'):
                                packets.extend(server19_openworld.reward_snapshot(account))
                        if name == 'EatOpenworldCookReq':
                            event('game_cooking_result', cook_id=request_values.get('cook_id'),
                                  avatar_id=request_values.get('avatar_id'), retcode=values.get('retcode'))
                        if name in server19_openworld.REQUESTS and values.get('retcode') == 0:
                            packets.extend(server19_openworld.commission_snapshot(name, account, account_path=RUN / 'account.json'))
                            if name in ('TakeOpenworldStoryRewardReq', 'TakeOpenworldCycleFinishRewardReq'):
                                packets.extend(server19_openworld.reward_snapshot(account))
                            if name not in ('GetOpenworldReq', 'GetOpenworldStageReq'):
                                event('game_openworld_committed', command=name,
                                      story_id=request_values.get('story_id'),
                                      story_progress=request_values.get('story_progress'),
                                      finished=account.get('openworld_data', {}).get('finish_story_id_list', []),
                                      active=account.get('openworld_runtime', {}).get('active'))
                        if name in ("StageBeginReq", "StageEndReq") and values.get("retcode") == 0:
                            packets.extend(server19_stage.notification_snapshot(account))
                            event("game_stage_committed", command=name,
                                  stage_id=values.get("stage_id"),
                                  stamina=account["main"]["stamina"],
                                  stages=account.get("stage_list", []))
                            if name == "StageEndReq":
                                # Derived task progress must not roll back a real,
                                # already committed battle settlement if its own
                                # compatibility metadata needs repair.
                                try:
                                    mission_packet = server19_missions.response(
                                        "GetMissionDataReq", account,
                                        account_path=RUN / "account.json")
                                    if mission_packet[1].get("retcode") == 0:
                                        # Validate optional task serialization here,
                                        # before it can interrupt the battle send.
                                        proto.encode_message(*mission_packet)
                                        packets.append(mission_packet)
                                    else:
                                        event("game_mission_sync_error",
                                              retcode=mission_packet[1].get("retcode"))
                                except Exception as exc:
                                    event("game_mission_sync_error",
                                          error=type(exc).__name__, message=str(exc))
                        if name == "GetMissionRewardReq" and values.get("retcode") == 0:
                            # Native reward dialog must exist before AvatarData
                            # emits the new-avatar notification. Its equipment
                            # UID must already exist in Storage at that time.
                            snapshots = server19_missions.notification_snapshot(account)
                            # Close the old task in MissionModule before success
                            # opens its dialog; keep equipment/avatar unlock order.
                            packets = [p for p in snapshots if p[0] == "GetMissionDataRsp"] + packets
                            packets.extend(p for p in snapshots if p[0] != "GetMissionDataRsp")
                            event("game_mission_committed",
                                  mission_id=request_values.get("mission_id"),
                                  claimed_ids=account.get("mission_runtime", {}).get("claimed_ids", []),
                                  avatars=account.get("avatar_list", []),
                                  main=account["main"])
                        elif name == "GetMissionRewardReq" and values.get("retcode") == 3:
                            # Also repair a stale button after a duplicate claim.
                            packets.insert(0, server19_missions.mission_snapshot(account))
                        if name == "TakeDutyRewardReq" and values.get("retcode") == 0:
                            packets.extend(server19_missions.notification_snapshot(account))
                            event("game_duty_committed",
                                  duty_type=request_values.get("duty_type"),
                                  duty_id=request_values.get("duty_id"),
                                  daily_taken=account.get("duty_runtime", {}).get("daily_taken", []),
                                  weekly_taken=account.get("duty_runtime", {}).get("weekly_taken", []),
                                  main=account["main"])
                        if name in server19_equipment.HANDLED_REQUESTS and values.get("retcode") == 0:
                            snapshots = server19_equipment.notification_snapshot(account, name)
                            if name in ("EquipmentPowerUpReq", "EquipmentEvoReq", "EquipSynthesisReq",
                                        "EquipmentSellReq", "IslandDisjoinEquipmentReq",
                                        "UpdateEquipmentProtectedStatusReq"):
                                # Native Rsp32 immediately constructs its result
                                # dialog from StorageModule's existing objects.
                                # Detail OnPacket81575 refreshes the lock on Rsp75,
                                # so protection also needs the inventory first.
                                packets = snapshots + packets
                            else:
                                packets.extend(snapshots)
                            event("game_equipment_committed", command=name,
                                  avatars=account.get("avatar_list", []),
                                  scoin=account["main"].get("scoin"),
                                  weapons=account.get("weapon_list", []),
                                  stigmata=account.get("stigmata_list", []),
                                  materials=account.get("material_list", []))
                            if name == 'EquipmentEvoReq':
                                event('game_equipment_evolution_replaced',
                                      transition=server19_equipment.evolution_detail())
                        for packet_name, packet_values in packets:
                            body = proto.encode_message(packet_name, packet_values)
                            packet_id += 1
                            packet = proto.encode_frame(packet_name, body, user_id=account["uid"],
                                                       client_version=frame.client_version, time=packet_id)
                            self.request.sendall(packet)
                            event("game_response", command=packet_name, body_size=len(body),
                                  stage_snapshot=packet_name != rsp_name,
                                  request=name, elapsed_ms=round((time.perf_counter()-request_started)*1000,3))
                            if name in server19_stage_display.HANDLED_REQUESTS and packet_name == rsp_name:
                                event("game_stage_display_response", command=packet_name,
                                      retcode=packet_values.get("retcode"),
                                      stage_ids=[row["stage_id"] for row in packet_values.get("stage_drop_list", [])])
                            if packet_name in ("StageBeginRsp", "StageEndRsp", "FinishGuideReportRsp"):
                                event("game_stage_response_wire", command=packet_name,
                                      body_hex=body.hex())
                            if name in server19_equipment.HANDLED_REQUESTS and packet_name == rsp_name:
                                event("game_equipment_response_wire", command=packet_name,
                                      body_hex=body.hex())
                            if name in ("GetMissionRewardReq", "TakeDutyRewardReq") and packet_name == rsp_name:
                                event("game_mission_response_wire" if name == "GetMissionRewardReq" else "game_duty_response_wire",
                                      command=packet_name,
                                      body_hex=body.hex())
                            if name in server19_gacha.HANDLED_REQUESTS and packet_name == rsp_name:
                                event("game_gacha_response_wire", command=packet_name,
                                      retcode=packet_values.get("retcode"),
                                      body_hex=body.hex())
                            if name in (server19_avatar_skills.HANDLED_REQUESTS |
                                        server19_avatar_cultivation.HANDLED_REQUESTS) and packet_name == rsp_name:
                                event("game_avatar_cultivation_response_wire", command=packet_name,
                                      body_hex=body.hex())
        except Exception as exc:
            event("game_error", error=type(exc).__name__, message=str(exc))
            traceback.print_exc()
        finally:
            event("game_disconnected")


class GameServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            with server19_battle_session.LOCK:
                report = server19_battle_session.recover(load_account(), RUN / "account.json", 'server_start')
                event('battle_session_recovery', **report)
        except Exception:
            self.server_close()
            raise


def main():
    global LOCAL_RECHARGE_ENABLED
    p = argparse.ArgumentParser()
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--advertised-host", default="127.0.0.1")
    p.add_argument("--local-recharge", action="store_true",
                   help="Enable offline recharge; requires matching patched client")
    a = p.parse_args()
    LOCAL_RECHARGE_ENABLED = a.local_recharge
    load_account()
    threading.Thread(target=server19_http.serve, args=(event, a.bind, a.advertised_host),
                     kwargs={'local_recharge': a.local_recharge}, daemon=True).start()
    with GameServer((a.bind, 21019), GameHandler) as server:
        event("game_listen", bind=a.bind, port=21019)
        server.serve_forever()


if __name__ == "__main__":
    main()
