"""Native captain profile mutations, persisted through the shared account lock.

Limits and packet consumers were recovered from the original 1.9 client.
Evidence: server19-run/lobby-audit/profile-native/FINDINGS.md.
"""
from copy import deepcopy
from pathlib import Path
import re

import server19_initialization
import server19_stage as stage

HANDLED_REQUESTS = frozenset((
    "NicknameModifyReq",
    "SetSelfDescReq",
    "UpdateAssistantAvatarIdReq",
    "ChangePlayerCardReq",
    "GetMedalDataReq",
    "MedalOpReq",
    "GetRedeemCodeInfoReq",
    "ExchangeRedeemCodeReq",
    "SendPlayerCardMsgReq",
))

NICKNAME_LIMIT = 8
SELF_DESC_LIMIT = 30
_WHITESPACE = "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
_SIZE_TAG = re.compile(r"<size=\s*\d*\s*>")


def _value(request_name, request_values):
    key, limit = ("nickname", NICKNAME_LIMIT) if request_name == "NicknameModifyReq" else ("self_desc", SELF_DESC_LIMIT)
    value = request_values.get(key)
    if not isinstance(value, str):
        raise ValueError("Profile value must be a string")
    value = value.strip(_WHITESPACE)
    if key == "self_desc" and "</size>" in value:
        match = _SIZE_TAG.search(value)
        if match:
            value = value.replace(match.group(), "").replace("</size>", "")
    if not value or len(value.encode("utf-16-le")) // 2 > limit:
        raise ValueError("Profile value is empty or exceeds the native UTF16 limit")
    return key, value


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    response_name = request_name[:-3] + "Rsp"
    request_values = request_values or {}

    # Read-only queries or rejected endpoints
    if request_name in ("GetRedeemCodeInfoReq", "ExchangeRedeemCodeReq", "SendPlayerCardMsgReq"):
        return response_name, {"retcode": 1}

    if request_name == "GetMedalDataReq":
        medals = account.get("medal_list", [])
        return response_name, {"retcode": 0, "medal_list": deepcopy(medals)}

    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        current = stage._read(path, account)
        before = deepcopy(current)
        if not isinstance(current.get("main"), dict):
            return response_name, {"retcode": 1}

        if request_name in ("NicknameModifyReq", "SetSelfDescReq"):
            try:
                key, value = _value(request_name, request_values)
            except (ValueError, UnicodeError):
                return response_name, {"retcode": 2}
            current["main"][key] = value
            rsp_payload = {"retcode": 0}

        elif request_name == "UpdateAssistantAvatarIdReq":
            aid = int(request_values.get("avatar_id", 0))
            if aid <= 0:
                return response_name, {"retcode": 1}
            current["main"]["assistant_avatar_id"] = aid
            current["assistant_avatar_id"] = aid
            rsp_payload = {"retcode": 0}

        elif request_name == "ChangePlayerCardReq":
            req_type = int(request_values.get("type", 1))
            slot_list = list(request_values.get("slot_list", []))
            msg_config = int(request_values.get("msg_config", 0))
            card = current.setdefault("player_card", {})
            if req_type == 1:
                avatars = list(card.get("avatar_id_list", [current["main"].get("assistant_avatar_id", 101), 0, 0]))
                while len(avatars) < 3:
                    avatars.append(0)
                for s in slot_list:
                    idx = int(s.get("index", 0))
                    tid = int(s.get("target_id", 0))
                    if 0 <= idx < 3:
                        avatars[idx] = tid
                card["avatar_id_list"] = avatars
            elif req_type == 2:
                medals = list(card.get("medal_id_list", [0, 0, 0]))
                while len(medals) < 3:
                    medals.append(0)
                for s in slot_list:
                    idx = int(s.get("index", 0))
                    tid = int(s.get("target_id", 0))
                    if 0 <= idx < 3:
                        medals[idx] = tid
                card["medal_id_list"] = medals
            card["msg_config"] = msg_config
            rsp_payload = {
                "retcode": 0,
                "type": req_type,
                "slot_list": slot_list,
                "msg_config": msg_config,
            }

        elif request_name == "MedalOpReq":
            op = int(request_values.get("op", 1))
            on_id = int(request_values.get("on_id", 0))
            off_id = int(request_values.get("off_id", 0))
            if op == 1 and on_id:
                current["main"]["on_medal_id"] = on_id
            elif op == 2:
                current["main"]["on_medal_id"] = 0
            rsp_payload = {"retcode": 0, "op": op, "on_id": on_id, "off_id": off_id}

        else:
            return None

        stage._save(path, before, current)
        stage._sync(account, current)

    return response_name, rsp_payload


def notification_snapshot(account):
    # Success responses carry only a retcode or minimal fields.
    # PlayerProfile rebuilds the actual profile and worn medal from MainData.
    return [server19_initialization.response("GetMainDataReq", account)]
