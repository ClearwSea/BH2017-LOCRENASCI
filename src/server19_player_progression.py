"""Atomic-caller captain EXP using an explicit 2.4 arrival-row compatibility policy.

Original 1.9 Main/PlayerData consumers accept level, EXP, coin and uncapped
stamina; they do not issue server-side bonuses. Historical payout semantics
were not recovered. By the approved compatibility policy, each reached level
grants exactly that deployed row's scBonus/staminaBonus. No invented crystals,
extra rewards or unknown capped-EXP conversion. Caller owns save/idempotency.
"""
from copy import deepcopy
import json
from server19_build_capabilities import canonical_sha

SOURCE_POLICY = "deployed24-playerlevel-arrival-compatibility"
TABLE_SHA256 = "c908e465b869bd64c13e798e0c5a3951fd2534debba97bf8262ab862549eeeeb"
TABLE_CONTENT_SHA256 = "49ac1b59a2659ae15eba358a797ee93fc6adcb8d3bf2d17ecc01b906d9317370"
# Explicit local story-test policy; other instances retain the original refusal.
CAP_EXP_TO_SCOIN = False


def grant_player_exp(main, amount):
    """Validate and update a transaction copy; no file writes or notifications.

    Begin previews use a disposable main copy; StageEnd and mission claims
    store this audit alongside their existing atomic, replay-safe receipts.
    Preserve reward stamina above the recovery cap rather than discarding it.
    """
    import server19_stage as stage
    raw = (stage.TABLE_DIRECTORY / "playerleveldata").read_bytes()
    # Build output may change JSON whitespace or object key order.
    # Keep the reviewed values fixed, rather than their serialization bytes.
    if canonical_sha(json.loads(raw)) != TABLE_CONTENT_SHA256:
        raise ValueError("Reviewed captain progression source changed")
    rows = stage._table("playerleveldata")
    levels = {stage._u32(row["level"], "level"): row for row in rows}
    if len(levels) != len(rows) or not levels:
        raise ValueError("Duplicate or missing captain level rows")
    value = deepcopy(main)
    before_level = level = stage._u32(value["level"], "captain level")
    before_exp = stage._u32(value.get("exp", 0), "captain EXP")
    exp = stage._u32(before_exp + stage._u32(amount, "EXP reward"), "captain EXP")
    limit = max(levels)
    if level not in levels:
        raise ValueError("Captain level has no reviewed source row")
    bonuses = []
    while level < limit and exp >= levels[level]["exp"]:
        required = stage._u32(levels[level]["exp"], "next-level EXP")
        if not required or level + 1 not in levels:
            raise ValueError("Broken captain progression sequence")
        exp -= required
        level += 1
        row = levels[level]
        coin = stage._u32(row["scBonus"], "level-up coin")
        stamina = stage._u32(row["staminaBonus"], "level-up stamina")
        value["scoin"] = stage._u32(value.get("scoin", 0) + coin, "stored coin")
        value["stamina"] = stage._u32(value.get("stamina", 0) + stamina, "stored stamina")
        bonuses.append({"reached_level": level, "scoin": coin, "stamina": stamina})
    converted = 0
    if level == limit and exp:
        if not CAP_EXP_TO_SCOIN:
            raise ValueError("Capped captain EXP conversion is not audited")
        converted = exp
        value['scoin'] = stage._u32(value.get('scoin', 0) + converted, 'overflow EXP coin')
        exp = 0
    value.update(level=level, exp=exp)
    main.clear()
    main.update(value)
    return {"source_policy": SOURCE_POLICY, "table_sha256": TABLE_SHA256,
            "level_before": before_level, "exp_before": before_exp,
            "exp_added": amount, "level_after": level, "exp_after": exp,
            "level_rewards": bonuses,
            "cap_exp_conversion": {"policy": "local_1_exp_to_1_scoin" if CAP_EXP_TO_SCOIN else "reject",
                                   "exp": converted, "scoin": converted}}


def reconcile_level_avatar(account, account_path):
    """Restore the original Chariot level-9 entitlement, without duplicate cards.

    Text key Menu_Desc_NewbieAvatarUnlockCondition_301 specifies level 9.
    Existing ownership is authoritative; stored fragments are preserved.
    """
    import server19_stage as stage
    import server19_gacha as gacha
    from pathlib import Path
    def eligible(value):
        return value.get('main', {}).get('level', 0) >= 9 and not any(
            row.get('avatar_id') == 301 and row.get('star', 0) > 0
            for row in value.get('avatar_list', []))
    if not eligible(account):
        return False
    path = Path(account_path).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        if not eligible(current):
            stage._sync(account, current)
            return False
        gacha._grant_card(current, 60301)
        stage._save(path, before, current)
        stage._sync(account, current)
    return True
