"""Scoin and Stamina exchange handlers for Server 19.

Allows converting HCoin (crystals) to SCoin (gold) or Stamina with
no daily count limits, respecting system upper limits.
"""
from copy import deepcopy
from pathlib import Path
import server19_stage as stage

HANDLED_REQUESTS = frozenset((
    "GetScoinExchangeInfoReq",
    "ScoinExchangeReq",
    "GetStaminaExchangeInfoReq",
    "StaminaExchangeReq",
    "GetSkillPointExchangeInfoReq",
    "SkillPointExchangeReq",
))

SCOIN_COST_HCOIN = 100
SCOIN_GET_AMOUNT = 100000
SCOIN_SYSTEM_LIMIT = 100000000  # 100 million

STAMINA_COST_HCOIN = 100
STAMINA_GET_AMOUNT = 100
STAMINA_SYSTEM_LIMIT = 999      # Absolute upper stamina cap

# User-approved offline price. No purchase counter or daily cap.
SKILL_POINT_COST_HCOIN = 10
SKILL_POINT_GET_AMOUNT = 20


def skill_point_exchange(name, account, *, account_path=None, now=None):
    import server19_avatar_skills as skills
    rsp = name.removesuffix('Req') + 'Rsp'
    if name == 'GetSkillPointExchangeInfoReq':
        # Native wire requires numeric counts; this display value never limits purchases.
        return rsp, dict(retcode=0, usable_times=9999, total_times=9999,
                         hcoin_cost=SKILL_POINT_COST_HCOIN, skill_point_get=SKILL_POINT_GET_AMOUNT)
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            skills.synchronize_skill_point(current, now=now)
            main = current['main']
            if main['skill_point'] >= main.get('skill_point_limit', 20):
                stage._sync(account, before)
                return rsp, {'retcode': 4}  # Native SKILL_POINT_FULL -> Err_SkillPointFull.
            if main['hcoin'] < SKILL_POINT_COST_HCOIN:
                stage._sync(account, before)
                return rsp, {'retcode': 2}  # Native HCOIN_LACK.
            main['hcoin'] = stage._u32(main['hcoin'] - SKILL_POINT_COST_HCOIN, 'skill point exchange crystals')
            main['skill_point'] = stage._u32(main['skill_point'] + SKILL_POINT_GET_AMOUNT, 'purchased skill points')
            skills.synchronize_skill_point(current, now=now)
            result = dict(retcode=0, hcoin_cost=SKILL_POINT_COST_HCOIN, skill_point_get=SKILL_POINT_GET_AMOUNT)
            skills.proto.encode_message(rsp, result)
            skills.proto.encode_message('GetMainDataRsp', dict(retcode=0, **main))
            stage._save(path, before, current)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            stage._sync(account, before)
            return rsp, {'retcode': 1}
        stage._sync(account, current)
        return rsp, result


def response(name, account, values=None, *, account_path=None):
    if name not in HANDLED_REQUESTS:
        return None
    if name in ('GetSkillPointExchangeInfoReq', 'SkillPointExchangeReq'):
        return skill_point_exchange(name, account, account_path=account_path)

    if name == "GetScoinExchangeInfoReq":
        return "GetScoinExchangeInfoRsp", {
            "retcode": 0,
            "usable_times": 9999,
            "total_times": 9999,
            "hcoin_cost": SCOIN_COST_HCOIN,
            "scoin_get": SCOIN_GET_AMOUNT,
        }

    if name == "GetStaminaExchangeInfoReq":
        return "GetStaminaExchangeInfoRsp", {
            "retcode": 0,
            "usable_times": 9999,
            "total_times": 9999,
            "hcoin_cost": STAMINA_COST_HCOIN,
            "stamina_get": STAMINA_GET_AMOUNT,
        }

    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()

    if name == "ScoinExchangeReq":
        with stage._transaction_lock(path):
            before = stage._read(path, account)
            current = deepcopy(before)
            main = current.get("main", {})
            hcoin = main.get("hcoin", 0)
            scoin = main.get("scoin", 0)

            if hcoin < SCOIN_COST_HCOIN:
                return "ScoinExchangeRsp", {"retcode": 2}
            if scoin + SCOIN_GET_AMOUNT > SCOIN_SYSTEM_LIMIT:
                return "ScoinExchangeRsp", {"retcode": 1}

            main["hcoin"] = stage._u32(hcoin - SCOIN_COST_HCOIN, "deducted exchange hcoin")
            main["scoin"] = stage._u32(scoin + SCOIN_GET_AMOUNT, "credited exchange scoin")
            stage._save(path, before, current)
            stage._sync(account, current)

        return "ScoinExchangeRsp", {
            "retcode": 0,
            "hcoin_cost": SCOIN_COST_HCOIN,
            "scoin_get": SCOIN_GET_AMOUNT,
            "boost_rate": 1,
        }

    if name == "StaminaExchangeReq":
        with stage._transaction_lock(path):
            before = stage._read(path, account)
            current = deepcopy(before)
            main = current.get("main", {})
            hcoin = main.get("hcoin", 0)
            stamina = main.get("stamina", 0)

            if hcoin < STAMINA_COST_HCOIN:
                return "StaminaExchangeRsp", {"retcode": 2}
            if stamina + STAMINA_GET_AMOUNT > STAMINA_SYSTEM_LIMIT:
                return "StaminaExchangeRsp", {"retcode": 4}

            main["hcoin"] = stage._u32(hcoin - STAMINA_COST_HCOIN, "deducted exchange hcoin")
            main["stamina"] = stage._u32(stamina + STAMINA_GET_AMOUNT, "credited exchange stamina")
            stage._save(path, before, current)
            stage._sync(account, current)

        return "StaminaExchangeRsp", {
            "retcode": 0,
            "hcoin_cost": STAMINA_COST_HCOIN,
            "stamina_get": STAMINA_GET_AMOUNT,
        }

    return None
