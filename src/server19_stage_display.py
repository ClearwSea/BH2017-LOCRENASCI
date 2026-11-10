"""Read-only original stage-drop display protocol for the compatibility server.

Wire fields are the original 1.9 StageDropDisplayInfo, while the displayed
items/quantities come from the already deployed, filtered 2.4 stagedata_main.
This is display data, not reconstructed historical drop probabilities or a
repeat-clear reward plan. No inventory, progression or Begin scope is changed.
"""
import server19_stage as stage
import server19_befall

HANDLED_REQUESTS = frozenset({"GetStageDropDisplayReq"})
INITIAL_CHAPTER_ID = 1
DISPLAY_SOURCE = "deployed24_stagedata_main_display"


def _u32(value, name, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= 0xFFFFFFFF:
        raise ValueError(name + " must be UInt32")
    return value


def _record(config):
    # Original OnGetStageDropDisplayRsp69127@c1368d marks this stage's
    # dropDisplayInfoReceived (+0x7c). @c1369c/c136b3 consumes tag2 as IDs
    # converted to RewardItemData(level0,num0); @c136c6/c136cb consumes tag10
    # directly. Keep the authored display level/quantity, including equipment
    # level0. Begin/End grant levels are a separate original protocol.
    drop_ids = config.get("displayDropList")
    first = config.get("firstDisplayDropList")
    if not isinstance(drop_ids, list) or not isinstance(first, list):
        raise ValueError("Stage has no authored drop display")
    return {
        "stage_id": _u32(config["levelId"], "stage_id", positive=True),
        "drop_item_id_list": [_u32(item, "display item", positive=True)
                              for item in drop_ids],
        "first_drop_item_data_list": [
            {"id": _u32(item["id"], "first display item", positive=True),
             "level": _u32(item["level"], "first display level"),
             "num": _u32(item["num"], "first display quantity", positive=config.get("type") != 7)}
            for item in first],
    }


def response(request_name, account=None, request_values=None, *, account_path=None):
    """Serve real records; an empty initialization request preloads chapter1.

    OnSetupDifficultyNotify80121@8679ff checks *every* level in the chapter,
    including locked difficulties. Missing drop-ready data sets isNeedDrop
    (+0x38) and skips SetupLevels@867b51, leaving _actScroller unbound. The
    original result dialog calls ShowPage and then sends StageEndNotify41
    synchronously@c3934d/c39404, so waiting for a later query is insufficient.
    Preloading chapter1 visible Acts preserves that original order. By default
    Act101..106 (actType1) supply93 records across3 difficulties. The explicitly
    selected local metadata sets original IsExtraActHide=false, so its original
    ChapterDataItem.GetAllLevelList includes the15 Act107 rows too. Preserve
    Act107's original type2 instead of relabeling it as an ordinary Act.

    Explicit requests can display other deployed ordinary story stages. This
    does not make their battle resources, repeat rewards or item previews
    restored. In particular, later display references3108/10601/10603 have no
    currently deployed compatible item metadata; they are not replaced here.
    Activity bonus/drop multipliers and battle buff fields are not authored by
    this ordinary-story source, so they retain original absent/default state.
    """
    if request_name not in HANDLED_REQUESTS:
        return None
    values = request_values or {}
    requested = values.get("stage_id_list", [])
    if not isinstance(requested, list) or any(
            type(item) is not int or not 1 <= item <= 0xFFFFFFFF for item in requested):
        return "GetStageDropDisplayRsp", {"retcode": 1}
    hidden = [row for row in stage._table('constvaluesclient')
              if row.get('name') == 'IsExtraActHide']
    if len(hidden) != 1 or hidden[0].get('type') != 'bool' or hidden[0].get('value') not in ('true', 'false'):
        raise ValueError('Malformed original Extra visibility configuration')
    ordinary_acts = {row["actId"] for row in stage._table("actdata")
                     if row.get("actType") == 1 or
                     (row.get('actId') == 107 and row.get('actType') == 2
                      and hidden[0]['value'] == 'false')}
    configs = [row for row in stage._table("stagedata_main")
               if row.get("type") == 1 and row.get("actId") in ordinary_acts]
    befall = server19_befall.stage_ids() if (account or {}).get('main', {}).get('level', 1) >= 20 else set()
    configs.extend(row for row in stage._table('stagedata_main') if row['levelId'] in befall)
    by_id = {row["levelId"]: row for row in configs}
    if len(by_id) != len(configs):
        raise ValueError("Duplicate ordinary story display stage")
    if requested:
        selected = list(dict.fromkeys(requested))
        if any(item not in by_id for item in selected):
            # Unavailable data must not masquerade as a successful empty list.
            return "GetStageDropDisplayRsp", {"retcode": 1}
    else:
        selected = sorted(row["levelId"] for row in configs
                          if row.get("chapterId") == INITIAL_CHAPTER_ID or row["levelId"] in befall)
        if not selected:
            raise ValueError("Initial chapter has no authored stage display")
    return "GetStageDropDisplayRsp", {
        "retcode": 0,
        "stage_drop_list": [_record(by_id[item]) for item in selected],
    }
