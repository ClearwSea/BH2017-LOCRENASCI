"""GalTouch affection handling and persistence."""
from copy import deepcopy
from pathlib import Path

import server19_stage as stage

HANDLED_REQUESTS = frozenset(("AddGoodfeelReq",))


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    request_values = request_values or {}

    avatar_id = request_values.get("avatar_id")
    add_goodfeel = request_values.get("add_goodfeel", 0)
    add_type = request_values.get("add_goodfeel_type", 1)

    if not isinstance(avatar_id, int) or avatar_id <= 0:
        return "AddGoodfeelRsp", {"retcode": 1}
    if not isinstance(add_goodfeel, int) or add_goodfeel < 0:
        return "AddGoodfeelRsp", {"retcode": 1}

    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)

        target_avatar = None
        for a in current.get("avatar_list", []):
            if a.get("avatar_id") == avatar_id:
                target_avatar = a
                break

        if target_avatar is None:
            stage._sync(account, before)
            return "AddGoodfeelRsp", {"retcode": 1}

        current_touch = target_avatar.get("touch_goodfeel", 0)
        current_today = target_avatar.get("today_has_add_goodfeel", 0)

        new_touch = min(0xFFFFFFFF, current_touch + add_goodfeel)
        new_today = min(0xFFFFFFFF, current_today + add_goodfeel)

        target_avatar["touch_goodfeel"] = new_touch
        target_avatar["today_has_add_goodfeel"] = new_today

        stage._save(path, before, current)
        stage._sync(account, current)

    return "AddGoodfeelRsp", {"retcode": 0}
