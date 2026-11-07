"""User-authorized local repeat drops, explicitly not historical 1.9 RNG.

One category draw per Begin: 49% material, 1% equipment, 50% no item by
default. Audited avatar fragments share the non-equipment category and use
their native avatar quantity, never material inventory. Missing categories
transfer their weight to no-item. Eligible items
are the deployed stage's normal displayDropList; each category is uniform.
Store an exact plan and configuration snapshot before returning Begin. An
active retry never reads a new policy or draws again. Client-collected End
drops may not exceed that saved plan. The JSON is the editable policy source.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets

SOURCE_POLICY = "local_authored_conservative_v1"
POLICY_FILE = Path(__file__).with_name("server19_repeat_drop_policy.json")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_policy(policy):
    if not isinstance(policy, dict) or set(policy) != {"source_policy", "version", "slots_per_attempt",
            "weights", "quantity", "equipment_level", "eligible_source"} or \
            policy["source_policy"] != SOURCE_POLICY or policy["slots_per_attempt"] != 1 or \
            policy["eligible_source"] != "deployed24_stagedata_main.displayDropList":
        raise ValueError("Unknown repeat-drop policy shape or source")
    for key in ("version", "slots_per_attempt", "quantity", "equipment_level"):
        if type(policy[key]) is not int or not 0 < policy[key] <= 0xFFFFFFFF:
            raise ValueError("Repeat-drop policy parameters must be positive UInt32")
    weights = policy["weights"]
    if not isinstance(weights, dict) or set(weights) != {"material", "equipment", "none"} or \
            any(type(value) is not int or not 0 <= value <= 100 for value in weights.values()) or sum(weights.values()) != 100:
        raise ValueError("Repeat category weights must be integer percentages totaling100")
    return policy


def policy_snapshot():
    return deepcopy(_validate_policy(json.loads(POLICY_FILE.read_text(encoding="utf-8"))))


def candidates(config, policy):
    import server19_stage as stage
    ids = config.get("displayDropList")
    if not isinstance(ids, list) or any(type(identity) is not int or identity <= 0 for identity in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid normal stage display-drop identities")
    result = {"stage_id": config["levelId"], "display_ids": list(ids), "material": [], "equipment": []}
    for identity in ids:
        kind, row = stage._item_metadata(identity)
        if kind not in ("material", "avatar_fragment", "weapon", "stigmata"):
            raise ValueError("Unsupported normal display item kind")
        category = "material" if kind in ("material", "avatar_fragment") else "equipment"
        level = 0 if category == "material" else policy["equipment_level"]
        if category == "material" and policy["quantity"] > row["quantityLimit"] or \
                category != "material" and not 1 <= level <= row["maxLv"]:
            raise ValueError("Repeat item parameters exceed actual item limits")
        result[category].append({"kind": kind, "item_id": identity, "level": level,
            "num": policy["quantity"], "rarity": stage._u32(row["rarity"], "rarity"), "is_equip_drop": False})
    return result


def draw(config):
    policy = policy_snapshot()
    eligible = candidates(config, policy)
    material_weight = policy["weights"]["material"] if eligible["material"] else 0
    equipment_weight = policy["weights"]["equipment"] if eligible["equipment"] else 0
    choice = secrets.randbelow(100)
    category = "material" if choice < material_weight else (
        "equipment" if choice < material_weight + equipment_weight else "none")
    plan = []
    if category != "none":
        selected = deepcopy(eligible[category][secrets.randbelow(len(eligible[category]))])
        selected.pop("kind")
        plan.append(selected)
    audit = {"schema": 1, "policy": policy, "policy_sha256": _digest(policy),
             "candidates": eligible, "candidates_sha256": _digest(eligible), "selected_category": category}
    return plan, audit


def validate_active(active, config):
    """Validate saved snapshot against metadata; current policy may be edited.

    An in-flight attempt keeps its Begin policy snapshot, version and draw.
    Changing JSON affects subsequent Begin only. A changed item or stage
    candidate row aborts validation instead of silently changing the plan.
    """
    try:
        audit = active["drop_audit"]
        policy = _validate_policy(audit["policy"])
        eligible = candidates(config, policy)
        plan = active["drop_plan"]
        begin = active["begin_response"]
        if audit.get("schema") != 1 or audit.get("policy_sha256") != _digest(policy) or \
                audit.get("candidates") != eligible or audit.get("candidates_sha256") != _digest(eligible) or \
                active.get("drop_policy") != SOURCE_POLICY or begin.get("drop_item_list") != plan or \
                begin.get("stage_id") != active.get("stage_id") or active["stage_id"] != config["levelId"] or \
                begin.get("progress") != config["maxProgress"]:
            return False
        category = audit.get("selected_category")
        if category == "none":
            no_item_weight = policy["weights"]["none"] + sum(policy["weights"][key]
                for key in ("material", "equipment") if not eligible[key])
            return plan == [] and no_item_weight > 0
        if category not in ("material", "equipment") or policy["weights"][category] == 0 or len(plan) != 1:
            return False
        return any(plan[0] == {key: value for key, value in row.items() if key != "kind"}
                   for row in eligible[category])
    except (KeyError, ValueError, TypeError):
        return False


def probability_summary(config):
    policy = policy_snapshot()
    eligible = candidates(config, policy)
    material = policy["weights"]["material"] if eligible["material"] else 0
    equipment = policy["weights"]["equipment"] if eligible["equipment"] else 0
    return {"stage_id": config["levelId"], "source_policy": policy["source_policy"],
            "policy_version": policy["version"], "policy_sha256": _digest(policy),
            "material_percent": material, "equipment_percent": equipment,
            "no_item_percent": 100 - material - equipment,
            "material_ids": [row["item_id"] for row in eligible["material"]],
            "equipment_ids": [row["item_id"] for row in eligible["equipment"]],
            "category_internal_distribution": "uniform", "quantity": policy["quantity"],
            "equipment_level": policy["equipment_level"]}
