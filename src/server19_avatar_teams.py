"""Original 1.9 team snapshots and persisted native team updates.

The original client sends UpdateAvatarTeamNotify (49), not a Req/Rsp pair.
NetworkManager.NotifyUpdateAvatarTeam73009 copies the member list as-is;
StageBegin's three slots are a separate message. Zero slots and their order
are therefore preserved, while a compact list of up to three is also valid.
Original consumers and enum evidence: server19-run/avatar-team-audit/.

No roster grants, stage unlocks, equipment changes or client switching hacks.
The query (48) synchronizes native PlayerDataItem lists, including presets.
"""
from copy import deepcopy
from pathlib import Path

import server19_protocol as proto
import server19_stage as stage

HANDLED_REQUESTS = frozenset(("GetAvatarTeamDataReq", "UpdateAvatarTeamNotify",
                              "UpdateCustomAvatarTeamReq"))
MUTATION_REQUESTS = HANDLED_REQUESTS - {"GetAvatarTeamDataReq"}
STAGE_TYPES = frozenset((1, 2, 3, 4, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16))
MAX_MEMBERS = 3  # PlayerDataItem.MAX_TEAM_MEMBER_NUM and PlayerCustomTeamData.
MIN_CUSTOM_TEAM_ID, MAX_CUSTOM_TEAM_ID = 1, 6
MAX_CUSTOM_NAME_BYTES = 24  # proto.CustomAvatarTeam.Enum.MAX_NAME_LEN.


class _Rejected(ValueError):
    def __init__(self, retcode, reason):
        super().__init__(reason)
        self.retcode = retcode


def owned_avatar_ids(account):
    """Only positive-star avatars with actual original-compatible metadata."""
    metadata = {stage._u32(row["avatarID"], "metadata avatar id")
                for row in stage._table("avatardata")}
    avatars = account.get("avatar_list", [])
    if not isinstance(avatars, list):
        raise ValueError("Malformed avatar inventory")
    seen, owned = set(), []
    for avatar in avatars:
        avatar_id = stage._u32(avatar["avatar_id"], "avatar id")
        star = stage._u32(avatar.get("star", 0), "avatar star")
        if not avatar_id or avatar_id in seen:
            raise ValueError("Ambiguous avatar inventory")
        seen.add(avatar_id)
        if star:
            if avatar_id not in metadata:
                raise ValueError("Owned avatar has no original-compatible metadata")
            owned.append(avatar_id)
    return owned


def _members(values, owned):
    if not isinstance(values, list) or len(values) > MAX_MEMBERS:
        raise _Rejected(4, "Team contains more than three slots")
    members = [stage._u32(value, "team avatar id") for value in values]
    occupied = [value for value in members if value]
    if len(occupied) != len(set(occupied)) or not set(occupied) <= set(owned):
        raise _Rejected(3, "Team contains repeated or unowned avatars")
    return members


def _ordinary_team(team, owned):
    if not isinstance(team, dict) or "stage_type" not in team or \
            set(team) - {"stage_type", "avatar_id_list"}:
        raise ValueError("Malformed native team")
    stage_type = stage._u32(team["stage_type"], "team stage type")
    if stage_type not in STAGE_TYPES:
        raise ValueError("Unknown original stage type")
    return {"stage_type": stage_type,
            "avatar_id_list": _members(team.get("avatar_id_list", []), owned)}


def _custom_team(team, owned):
    if not isinstance(team, dict) or "team_id" not in team or \
            set(team) - {"team_id", "name", "avatar_id_list"}:
        raise ValueError("Malformed native preset")
    team_id = stage._u32(team["team_id"], "custom team id")
    if not MIN_CUSTOM_TEAM_ID <= team_id <= MAX_CUSTOM_TEAM_ID:
        raise _Rejected(2, "Preset id is outside original 1..6")
    result = {"team_id": team_id,
              "avatar_id_list": _members(team.get("avatar_id_list", []), owned)}
    if "name" in team:
        name = team["name"]
        if not isinstance(name, str) or len(name.encode("utf-8")) > MAX_CUSTOM_NAME_BYTES:
            raise _Rejected(6, "Preset name exceeds the original compatibility limit")
        # The native rename dialog already trims and truncates to six UTF16
        # code units before sending. Preserve the sent string; no nonexistent
        # historical sensitive-word dictionary or invented name is supplied.
        result["name"] = name
    return result


def _team_list(values, owned, custom=False):
    if not isinstance(values, list):
        raise ValueError("Malformed saved team list")
    result, seen = [], set()
    key = "team_id" if custom else "stage_type"
    for team in values:
        checked = (_custom_team if custom else _ordinary_team)(team, owned)
        if checked[key] in seen:
            raise ValueError("Duplicate saved team selector")
        seen.add(checked[key])
        result.append(checked)
    return result


def snapshot(account):
    """Native Get48 packet; a missing team keeps the existing owned-first default.

    An explicit empty list remains empty. Reading never persists default teams
    or fills presets. Native SetCustomAvatarTeamList68615 creates its container
    and upserts returned IDs; CreateCustomTeamProvider80305 reads this list.
    """
    owned = owned_avatar_ids(account)
    teams = account.get("avatar_team_list")
    if teams is None and "avatar_team_list" not in account:
        teams = [{"stage_type": 1, "avatar_id_list": owned[:1]}] if owned else []
    packet = "GetAvatarTeamDataRsp", {
        "retcode": 0, "avatar_team_list": _team_list(teams, owned),
        "custom_avatar_team_list": _team_list(
            account.get("custom_avatar_team_list", []), owned, custom=True)}
    proto.encode_message(*packet)
    return packet


def notification_snapshot(account):
    return [snapshot(account)]


def _update(account, request_name, request_values):
    if not isinstance(request_values, dict) or set(request_values) != {"team"}:
        raise ValueError("Native team update requires one team")
    owned = owned_avatar_ids(account)
    custom = request_name == "UpdateCustomAvatarTeamReq"
    team = (_custom_team if custom else _ordinary_team)(request_values["team"], owned)
    key, selector = ("custom_avatar_team_list", "team_id") if custom else (
        "avatar_team_list", "stage_type")
    # Validate saved selectors before modifying one; retain other stage types
    # and presets. No shared roster or normal progress fields are changed.
    default = ([] if custom or not owned else
               [{"stage_type": 1, "avatar_id_list": owned[:1]}])
    existing = _team_list(account.get(key, default), owned, custom=custom)
    for index, old in enumerate(existing):
        if old[selector] == team[selector]:
            existing[index] = team
            break
    else:
        existing.append(team)
    account[key] = existing


def response(request_name, account, request_values=None, *, account_path=None):
    """Return native response data, or None for an unrelated request.

    A handled ordinary Notify is acknowledged using the original Get48 snapshot
    (there is no invented Update49Rsp). Custom269 returns original Rsp270;
    its successful caller sends notification_snapshot before that response.
    All mutation results and synchronization packets serialize before saving.
    """
    if request_name not in HANDLED_REQUESTS:
        return None
    if request_name == "GetAvatarTeamDataReq":
        try:
            return snapshot(account)
        except (ValueError, TypeError, KeyError, UnicodeError):
            return "GetAvatarTeamDataRsp", {"retcode": 1}
    custom = request_name == "UpdateCustomAvatarTeamReq"
    response_name = "UpdateCustomAvatarTeamRsp" if custom else "GetAvatarTeamDataRsp"
    failure = response_name, {"retcode": 1}
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    try:
        with stage._transaction_lock(path):
            before = stage._read(path, account)
            current = deepcopy(before)
            try:
                values = request_values or {}
                proto.encode_message(request_name, values)
                _update(current, request_name, values)
                result = ((response_name, {"retcode": 0}) if custom else snapshot(current))
                proto.encode_message(*result)
                for packet in notification_snapshot(current):
                    proto.encode_message(*packet)
                stage._save(path, before, current)
            except _Rejected as error:
                result = response_name, {"retcode": error.retcode if custom else 1}
            except (ValueError, TypeError, KeyError, UnicodeError, OSError, OverflowError):
                result = failure
            stage._sync(account, current if result[1]["retcode"] == 0 else before)
            return result
    except (ValueError, TypeError, KeyError, OSError):
        return failure
