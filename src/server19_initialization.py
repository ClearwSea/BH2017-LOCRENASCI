"""Bounded original-response initialization data with documented provenance.

No client page injection, debug-mode flag or FakePacketHelper is used. Values
are a development account fixture, not a recovered historical official save.
The native client creates the actual module/page/scene objects.
"""
from copy import deepcopy
import server19_stage
import server19_befall
from server19_business_clock import day_bounds


# Original IslandModule.InitCabinDict (69029, 0xb5220c) creates all nine cabins
# with level=0, extend_grade=1. Matching those native defaults keeps locked cabins
# locked. It does not supply missing CabinTechTreeMetaData on the client.
NATIVE_INITIAL_CABINS = tuple(
    {"type": cabin_type, "level": 1 if cabin_type in (1, 3, 4, 5) else 0, "extend_grade": 1, "tech_list": []}
    for cabin_type in range(1, 10)
)

# These four values are present in the saved 2.4 demo FakePacketRsp.json as data.
# This copies a bounded reference value into a real network response; it does
# not execute that client's FakePacketHelper or prove historical 1.9 rates.
REFERENCE_MAIN_TIMERS = {
    "stamina_recover_left_time": 7200,
    "stamina_recover_config_time": 7200,
    "skill_point_recover_left_time": 7200,
    "skill_point_recover_config_time": 7200,
}

# Original GameEntryPageContext.StartFirstLevel (78761, entry 0xad0767)
# selects 10101 at 0xad07ea. This is initial availability, not completion
# or an imported save. LevelDataItem's native ctor uses stamina_discount=100;
# the response handler creates ordinary levels only for supplied Stage IDs.
# Adding the first story level also creates the chapter's remaining locked
# levels through ChapterDataItem.AddStoryLevel (68119, 0x85a849).
NATIVE_FIRST_STORY_STAGE = {
    "id": 10101, "progress": 0, "enter_times": 0, "reset_times": 0,
    "assist_enter_times": 0, "challenge_index_list": [],
    "stamina_discount": 100, "is_done": False,
}


def initial_story_stage_list():
    """Independent zero-progress state; no bonus deadline or challenge grants."""
    return [deepcopy(NATIVE_FIRST_STORY_STAGE)]


def response(request_name, account, request_values=None):
    """Return a specialized initialization (response_name, values), or None.

    Account-supplied state takes precedence and should be persisted by the server.
    An empty guide list means no completed tutorials; no completion is fabricated.
    Pass decoded request_values for PlayerCard/Openworld/mentor selectors and
    bulletin IDs. Missing selectors use each original login helper's default.
    """
    request_values = request_values or {}
    if request_name == "GetIslandReq":
        return "GetIslandRsp", {
            "retcode": 0,
            "cabin_list": deepcopy(account.get("cabin_list", NATIVE_INITIAL_CABINS)),
            "help_num": account.get("island_help_num", 0),
        }
    if request_name == "GetIslandVentureReq":
        return "GetIslandVentureRsp", {
            "retcode": 0, "venture_list": deepcopy(account.get("venture_list", [])),
            "is_all": True, "refresh_times": account.get("venture_refresh_times", 0),
        }
    if request_name == "GetCollectCabinReq":
        # OnGetCollectCabinRsp (69024) reads these scalar getters even if absent,
        # then stores next_add_timeSpecified in CabinCollectDataItem+0x30.
        # Leave the schedule absent for a locked cabin: explicit timestamp zero
        # would incorrectly assert that a collection schedule exists at epoch.
        return "GetCollectCabinRsp", {
            "retcode": 0, "add_scoin": 0,
            "drop_item_list": [],
        }
    if request_name == "GetFinishGuideDataReq":
        # TutorialModule.OnGetFinishGuideDataRsp (71014, 0x141d011) updates only
        # the listed IDs, then filters/starts unfinished native tutorials.
        return "GetFinishGuideDataRsp", {
            "retcode": 0, "guide_id_list": list(account.get("guide_id_list", [])),
        }
    if request_name == "GetAvatarTeamDataReq":
        # Native team data is shared with ordinary Notify49 / preset Req269
        # persistence. Positive star marks actual ownership; no unlock grants.
        import server19_avatar_teams
        return server19_avatar_teams.response(request_name, account, request_values)
    if request_name == "GetMainDataReq":
        main = {**REFERENCE_MAIN_TIMERS, **account["main"]}
        return "GetMainDataRsp", {"retcode": 0, **main}
    if request_name == "GetPlayerCardReq":
        owned = [int(a["avatar_id"]) for a in account.get("avatar_list", [])]
        preset_msgs = [
            {"index": 1, "msg": {"uid": 10001, "nickname": "爱酱", "time": 1700000000, "msg": "版本基于崩坏3 V1.9 国服版本", "avatar_id": 101, "content": {"items": [{"type": 1, "msg_str": "版本基于崩坏3 V1.9 国服版本"}]}}},
            {"index": 2, "msg": {"uid": 10001, "nickname": "爱酱", "time": 1700000001, "msg": "由Hssssssssi逆向适配", "avatar_id": 101, "content": {"items": [{"type": 1, "msg_str": "由Hssssssssi逆向适配"}]}}},
            {"index": 3, "msg": {"uid": 10001, "nickname": "爱酱", "time": 1700000002, "msg": "禁止倒卖！版权归米哈游所有", "avatar_id": 101, "content": {"items": [{"type": 1, "msg_str": "禁止倒卖！版权归米哈游所有"}]}}},
        ]
        card = {
            "avatar_id_list": owned[:1], "medal_id_list": [],
            "msg_config": 0, "msg_data": {"msg_list": deepcopy(preset_msgs), "msg_index": len(preset_msgs), "msg_config": 0},
            "last_read_msg_index": 0, "mp_like_num": 0, "island_like_num": 0,
            **deepcopy(account.get("player_card", {})),
        }
        # OnGetPlayerCardRsp (70436, 0x1202f49) indexes both lists at 0,1,2.
        # Original PlayerDataItem ctor adds three zero medal slots; zero slots
        # are empty displays, not invented owned avatars or medals.
        for key in ("avatar_id_list", "medal_id_list"):
            slots = list(card[key])
            card[key] = slots + [0] * max(0, 3 - len(slots))
        # Native get_msg_data at 0x12030c2 is dereferenced without a null guard.
        if card["msg_data"] is None or not card["msg_data"].get("msg_list"):
            card["msg_data"] = {"msg_list": deepcopy(preset_msgs), "msg_index": len(preset_msgs), "msg_config": 0}
        card["type"] = int(request_values.get("type", 0))  # CARD_ALL=0
        card["retcode"] = 0
        return "GetPlayerCardRsp", card
    if request_name == "GetMissionDataReq":
        # OnGetMissionDataRsp (70036, 0xd309fc) applies the complete duty state
        # when is_all=true and sets missionDataReceived at 0xd31786. An empty
        # mission list contains no invented tasks, completions or rewards.
        mission = {
            "mission_list": [], "daily_duty_point": 0,
            "has_take_daily_duty_id_list": [], "weekly_duty_point": 0,
            "has_take_weekly_duty_id_list": [], "is_in_activity": False,
            **deepcopy(account.get("mission_data", {})),
        }
        # challenge_mission is optional: the original null branch reaches the
        # native received flag. Do not manufacture an unlocked challenge tree.
        mission.update(retcode=0, is_all=True)
        return "GetMissionDataRsp", mission
    if request_name == "GetOpenworldReq":
        world = {
            "cycle": 0, "finish_story_id_list": [], "cur_story_list": [],
            "event_list": [], "over_view_list": [], "cook_list": [],
            "event_stat_list": [], "servant_level": 0, "servant_exp": 0,
            "period_max_quest_num": 0, "period_finish_quest_num": 0,
            **deepcopy(account.get("openworld_data", {})),
        }
        # Refresh (70319, 0x11b56e6) stores quest_data at object+0x24. Later
        # ALL/QUEST refreshes dereference the newly received quest_data while
        # comparing lists, so retain a real locked, empty container.
        if world.get("quest_data") is None:
            world["quest_data"] = {"is_open": False, "quest_list": []}
        world["data_type"] = int(request_values.get("data_type", 0))
        world["retcode"] = 0
        # No spawn point, refresh deadline or reward cycle is invented. Lists
        # report the fixture's empty world; this does not implement its gameplay.
        return "GetOpenworldRsp", world
    if request_name == "GetStageDataReq":
        # OnGetStageDataRsp (69126, 0xc11f63) calls LevelModule.Init when needed,
        # even for an empty list. Init creates chapters/special stages; ordinary
        # levels require the stored Stage entries consumed at 0xc1204c. Native
        # code creates the rest of each supplied story chapter as locked levels.
        # Supply the next legitimately available stage with zero progress so
        # its native LevelDataItem is initialized; this records no completion.
        return "GetStageDataRsp", {
            "retcode": 0, "stage_list": list({r["id"]: r for r in (server19_stage.available_stage_list(account)
                + server19_befall.stage_snapshots(account))}.values()),
        }
    if request_name == "GetWeekDayActivityDataReq":
        activity = {
            "activity_list": [], "is_camp_war_open": False,
            **deepcopy(account.get("weekday_activity_data", {})),
        }
        server19_befall.update_activity_list(activity, account)
        # Handler 69130 (0xc13962) clears the complete activity list when
        # is_whole_data=true. At 0xc144eb it checks endless_data for null and
        # skips the schedule when absent; no active season is manufactured.
        activity.update(retcode=0, is_whole_data=True)
        return "GetWeekDayActivityDataRsp", activity
    if request_name == "GetActivityOpenworldReq":
        # Handler 70191 (0x11bf77b) requires both optional treasure fields to be
        # present and a nonzero generation time before generating an event.
        # An account without an event must leave those fields absent.
        return "GetActivityOpenworldRsp", {
            **deepcopy(account.get("activity_openworld_data", {})), "retcode": 0,
        }
    if request_name == "MpGetTeamReq":
        # Original MpGetTeamRsp.Retcode.NOT_IN_TEAM=2. Handler 69420 clears
        # team state at 0x1122f04 and avoids the generic FAIL error hint.
        team = account.get("mp_team_data")
        return "MpGetTeamRsp", (
            {**deepcopy(team), "retcode": 0} if team else {"retcode": 2}
        )
    if request_name == "MpGetMatchInfoReq":
        # Handler 69429 (0x11234b6) counts this list before consuming matches.
        # A successful empty query means no current match, without creating one.
        return "MpGetMatchInfoRsp", {
            "retcode": 0,
            "match_info_list": deepcopy(account.get("mp_match_info_list", [])),
        }
    if request_name == "GetEndlessDataReq":
        # Original GetEndlessDataRsp.Retcode.NO_ENDLESS=3. No saved event means
        # no participation/schedule; a successful empty event must not be forged.
        endless = account.get("endless_data")
        return "GetEndlessDataRsp", (
            {**deepcopy(endless), "retcode": 0}
            if endless else {"retcode": 3}
        )
    if request_name == "GetArmadaDataReq":
        # Original ArmadaPlayerStatus.ARMADA_PLAYER_NOT_JOIN=1. Refresh
        # (67351, 0x1055c59) needs an armada object only for status 3/4.
        return "GetArmadaDataRsp", {
            "status": 1, "apply_list": [],
            **deepcopy(account.get("armada_data", {})), "retcode": 0,
        }
    if request_name == "GetConsignedOrderDataReq":
        # Retcode.NOT_IN_ARMADA=2 is a defined non-error-hint branch in handler
        # 67310. Supply stored orders only for a genuinely joined account.
        armada_status = account.get("armada_data", {}).get("status", 1)
        if armada_status not in (3, 4):
            return "GetConsignedOrderDataRsp", {"retcode": 2}
        return "GetConsignedOrderDataRsp", {
            **deepcopy(account.get("consigned_order_data", {})), "retcode": 0,
        }
    if request_name == "GetMasterPupilDataReq":
        # SendPacketsOnLoginSuccess (72966) requests type=3 at 0x1150dc6.
        # Handler 69606 tests bit 1 at 0xd01b46 and bit 2 at 0xd01c7b before
        # clearing/replacing the two relation lists. A retcode-only success
        # defaults to type=0 and performs neither synchronization.
        return "GetMasterPupilDataRsp", {
            "retcode": 0, "type": int(request_values.get("type", 3)),
            "data_list": deepcopy(account.get("master_pupil_data_list", [])),
        }
    if request_name == "GetTrialAvatarReq":
        # AvatarModule.OnGetTrialAvatarRsp (67549) tests is_all_update at
        # 0x136ab87, then clears old trial availability before applying the
        # returned list. This is an account snapshot, not an invented grant.
        return "GetTrialAvatarRsp", {
            "retcode": 0, "is_all_update": True,
            "avatar_list": deepcopy(account.get("trial_avatar_list", [])),
        }
    if request_name == "GetFriendListReq":
        # FriendModule.OnGetFriendListRsp (68888) clears both dictionaries at
        # 0xa7e704 / 0xa7e723 only when is_whole_data is present and true.
        # A complete account query must not retain another login's cache.
        return "GetFriendListRsp", {
            "retcode": 0, "is_whole_data": True,
            "friend_list": deepcopy(account.get("friend_list", [])),
            "assistant_num": account.get("friend_assistant_num", 0),
        }
    if request_name == "GetBulletinReq":
        bulletins = deepcopy(account.get("bulletin_list", []))
        # ReqBulletinType: ALL=0, UPDATE_TIME=1, TITLE=2, CONTENT=3.
        # Original login helper 73056 sends UPDATE_TIME at 0x1151451. Handler
        # 67587 enters its full-list reconciliation only for is_all=true.
        whole = int(request_values.get("type", 1)) in (0, 1)
        if not whole:
            requested_ids = set(request_values.get("bulletin_id_list", []))
            bulletins = [b for b in bulletins if b["id"] in requested_ids]
        return "GetBulletinRsp", {
            "retcode": 0, "is_all": whole, "bulletin_list": bulletins,
        }
    return None
