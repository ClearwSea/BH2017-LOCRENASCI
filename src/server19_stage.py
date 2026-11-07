"""Original 1.9 story-stage protocol and local account transactions.

StageBegin/End command IDs and fields are from the original serializer schema.
10101 is independently selected by original StartFirstLevel (78761). The
business catalog covers ordinary Act101..106 and the original Extra Act107.
The original
seven stages remain supported; new stages require a deployment readiness
receipt. Client resource closure and human acceptance are separate. Numeric
stage settings are the already deployed, filtered 2.4 compatibility table,
not an independently recovered historical 1.9 economy.
Repeated item drops use the user's explicit local conservative JSON policy;
first-clear drops and challenge awards remain separate from repeat RNG.

Call response(..., account_path=...) on the game server's request thread. It
refreshes the supplied account from disk before processing, and returns the
ordinary (response_name, values) pair. A successful mutation can be followed
by notification_snapshot(account), using those original response messages.
refresh_account() must also precede other account queries in other handlers.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time

import server19_protocol as proto
import server19_player_progression as player_progression

ROOT = Path(__file__).resolve().parent
DEFAULT_ACCOUNT = ROOT / "server19-run" / "account.json"
TABLE_DIRECTORY = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"
# Explicit per-instance compatibility assets. Default/remote retains baseline.
TABLE_OVERRIDES = {}
# 本地已部署的指定试用角色白名单；空映射不改变旧实例。
# Prescribed trial roster for explicitly configured local deployments.
STORY_TRIAL_AVATARS = {}
STAGE_ID = 10101
SUPPORTED_STAGE_IDS = tuple(range(10101, 10108))
STORY_CATALOG_STAGE_IDS = tuple(range(10101, 10137))
# A reviewed batch of deployed source rows, not a permissive whole-chapter
# switch. Full canonical rows bind Lua, prerequisites, drops and restrictions.
# Client dependency closure and real gameplay still require separate acceptance.
AUDITED_ACT102_INCREMENT = tuple(range(10108, 10111))
AUDITED_ACT102_INCREMENT_SHA256 = "a7404e5d78d82e0756f49cad597ebfa5735bd9a4d8276e750caf82bb85f01f2c"
# All remaining Chapter1 rows are audited. Act107 retains its original actType2,
# chapter-star unlocks and fragment storage. Its native Extra entrance requires
# the explicitly selected local metadata assets, never a category rewrite.
AUDITED_CHAPTER1_REMAINDER = tuple(range(10111, 10137))
AUDITED_CHAPTER1_REMAINDER_SHA256 = "65031a5c710d7fcd15cabc4a3272fcaa741ebcb4941a2afe06245541cdd1ab99"
RESOURCE_GATE_STAGE_IDS = tuple(range(10108, 10137))
CHARACTER_STORY_STAGE_IDS = tuple(range(10132, 10137))
# Only the explicitly selected local comparison server opts into this gate.
# Remote/default server instances retain their original seven-stage scope.
STORY_RUNTIME_READY_FILE = None
_LOCK = threading.RLock()
_TABLES = {}

# Original NetworkManager.RequestLevelEndReq (73007, 0x11580f4) serializes
# StageEndReqBody, appends Encoding.Default.GetBytes(signKey), then appends
# _requestStr before SHA256 (51292, 0x12a7ddc), emitted as lowercase hex.
# _requestStr is the original char-array XOR result, not login_random_num:
# NetworkManager ctor 72965 @11502f0/11505e9, UIUtil.GetItemx86 82525 @145082d,
# GlobalVars ctor 43292 @5473bb. Metadata fieldRefs 73/49 map to field defaults
# 57353/23639, offsets 132240/71245; first 11 UTF-16 chars XOR the 32-char sk.
ORIGINAL_REQUEST_SUFFIX = "A0SL8WDU2DS"
STAGE_WIN = 1
STAGE_NOT_MEET_CONDITION = 2
STAGE_ALL_DEAD = 3
STAGE_EXIT = 4
FIRST_CLEAR_DROP_POLICY = "deployed24_first_display_fixed_compatibility"


def _u32(value, name):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(name + " must be UInt32")
    return value


def _table(name, *, field=None, identities=None):
    """Hash-check whole asset, then copy only requested rows where specified.

    Callers receive independent objects. Filtering the cached immutable rows
    avoids repeatedly deep-copying megabytes for each Stage/Act/loot lookup;
    every read still detects changes to the actual configured asset.
    """
    path = Path(TABLE_OVERRIDES.get(name, TABLE_DIRECTORY / name))
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    key = (str(path), digest)
    if key not in _TABLES:
        value = json.loads(raw)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError("Malformed original-compatible table: " + name)
        for old_key in list(_TABLES):
            if old_key[0] == str(path):
                del _TABLES[old_key]
        _TABLES[key] = value
    if field is None:
        if identities is not None:
            raise ValueError("Table row selection requires a field")
        selected = _TABLES[key]
    else:
        if identities is None:
            raise ValueError("Table row selection requires identities")
        allowed = frozenset(identities)
        selected = [row for row in _TABLES[key] if row.get(field) in allowed]
    return deepcopy(selected)


def supported_stage_ids():
    """Legacy seven plus explicitly deployed, read-back-verified new resources.

    A candidate build manifest does not activate stages. Deployment writes the
    separate runtime-ready receipt only after device resource verification.
    Schema1 preserves the accepted Act102 gate. Schema2 additionally binds the
    complete remaining source audit. Real deployment also prepares the original
    Extra entrance and its resource closure; receipt IDs activate only those
    explicitly verified client resources, without rewriting Act categories.
    """
    if STORY_RUNTIME_READY_FILE is None or not STORY_RUNTIME_READY_FILE.is_file():
        return SUPPORTED_STAGE_IDS
    ready = json.loads(STORY_RUNTIME_READY_FILE.read_text(encoding="utf-8"))
    ids = ready.get("ready_stage_ids")
    schema = ready.get("schema")
    if ready.get('build_proof'):
        from server19_build_capabilities import require
        require('chapter1', ready)
        valid_source, allowed = True, RESOURCE_GATE_STAGE_IDS
    elif schema == 1:
        valid_source = ready.get("audited_source_sha256") == AUDITED_ACT102_INCREMENT_SHA256
        allowed = AUDITED_ACT102_INCREMENT
    elif schema == 2:
        valid_source = ready.get("audited_source_sha256") == AUDITED_CHAPTER1_REMAINDER_SHA256 and \
                       ready.get("act102_source_sha256") == AUDITED_ACT102_INCREMENT_SHA256
        allowed = RESOURCE_GATE_STAGE_IDS
    else:
        valid_source, allowed = False, ()
    if not valid_source or \
            not isinstance(ids, list) or any(type(value) is not int or value not in allowed for value in ids) or \
            len(ids) != len(set(ids)):
        raise ValueError("Invalid deployed story-resource readiness receipt")
    if any(identity in CHARACTER_STORY_STAGE_IDS for identity in ids):
        visibility = _table("constvaluesclient", field="name", identities=("IsExtraActHide",))
        if visibility != [{"name": "IsExtraActHide", "type": "bool", "value": "false"}]:
            raise ValueError("Extra readiness requires the original local visibility configuration")
    return tuple(sorted(set(SUPPORTED_STAGE_IDS) | set(ids)))


def chapter1_remainder_audit():
    """Bind all26 canonical rows, including the original character stories."""
    rows = _table("stagedata_main", field="levelId", identities=AUDITED_CHAPTER1_REMAINDER)
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
    if digest != AUDITED_CHAPTER1_REMAINDER_SHA256:
        raise ValueError("Reviewed Chapter1 remainder source batch changed; audit before use")
    return rows


def stage_config(stage_id=STAGE_ID):
    if stage_id not in STORY_CATALOG_STAGE_IDS:
        raise ValueError("Stage resources are outside the supported story chain")
    rows = _table("stagedata_main", field="levelId", identities=(stage_id,))
    if len(rows) != 1:
        raise ValueError("Expected one configured story stage")
    row = rows[0]
    if stage_id in AUDITED_CHAPTER1_REMAINDER:
        chapter1_remainder_audit()
        acts = _table("actdata", field="actId", identities=(row["actId"],))
        expected_act_type = 2 if stage_id in CHARACTER_STORY_STAGE_IDS else 1
        if len(acts) != 1 or acts[0].get("chapterId") != 1 or acts[0].get("actType") != expected_act_type:
            raise ValueError("Original story Act category changed")
        expected_reward = 6 if stage_id in CHARACTER_STORY_STAGE_IDS else 1
        if len(row["challengeList"]) != 3 or any(
                challenge["rewardId"] != expected_reward for challenge in row["challengeList"]):
            raise ValueError("Additional challenge reward requires audit")
        # Values are read directly from the whole-row canonical source guard,
        # including real Lv3/5/7 requirements and changing EXP/coin values.
        # Drop metadata is validated by the exact plan and disposable grant
        # preview at Begin, and again before committing End. Read-only stage
        # snapshots need not rebuild every other stage's reward inventory.
        return row
    if stage_id in AUDITED_ACT102_INCREMENT:
        batch = _table("stagedata_main", field="levelId", identities=AUDITED_ACT102_INCREMENT)
        digest = hashlib.sha256(json.dumps(batch, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
        if digest != AUDITED_ACT102_INCREMENT_SHA256:
            raise ValueError("Reviewed Act102 source batch changed; audit before use")
    avatar_exp = 25 if stage_id <= 10102 else (26 if stage_id <= 10107 else 27)
    expected = {"type": 1, "chapterId": 1, "difficulty": 1, "battleType": 1,
                "actId": 101 if stage_id <= 10105 else 102,
                "sectionId": stage_id - 10100 if stage_id <= 10105 else stage_id - 10105,
                "preLevelID": [0 if stage_id == STAGE_ID else stage_id - 1],
                "unlockPlayerLevel": 1, "unlockStarNum": 0,
                "staminaCost": 6, "maxProgress": 1, "enterTimes": 65535,
                "playerExpReward": 6, "avatarExpReward": avatar_exp, "scoinReward": 750,
                "maxAvatarExpReward": avatar_exp, "maxScoinReward": 750,
                "avatarExpInside": 0.0,
                "scoinInside": 0.0 if stage_id <= 10102 else 0.7,
                "teamNum": 1, "maxNumList": [3], "restrictList": [0]}
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError("Story-chain configuration changed; audit it before use")
    acts = _table("actdata", field="actId", identities=(row["actId"],))
    if len(acts) != 1 or acts[0].get("chapterId") != 1 or acts[0].get("actType") != 1:
        raise ValueError("Story Act configuration changed")
    if not isinstance(row.get("firstDisplayDropList"), list) or not row["firstDisplayDropList"]:
        raise ValueError("Story stage has no explicit first-clear compatibility plan")
    if len(row.get("challengeList", [])) != 3 or any(
            challenge.get("rewardId") != 1 for challenge in row["challengeList"]):
        raise ValueError("Story-chain challenge reward needs an additional audit")
    # Keep the already accepted real-device first-stage reward baseline exact.
    if stage_id == STAGE_ID and (row.get("firstDisplayDropList") != [
            {"id": 4001, "level": 0, "num": 3},
            {"id": 3000, "level": 0, "num": 4},
            {"id": 20041, "level": 0, "num": 1},
            {"id": 130007, "level": 0, "num": 1},
            {"id": 1001, "level": 0, "num": 3}] or row.get("challengeList") != [
            {"challengeId": 13001, "rewardId": 1},
            {"challengeId": 4004, "rewardId": 1},
            {"challengeId": 2002, "rewardId": 1}]):
        raise ValueError("First-clear compatibility reward plan changed; audit it before use")
    # Scope the new row to the inspected deployed 2.4 configuration. This
    # proves the compatibility reward inputs, not historical 1.9 drop rates.
    if stage_id == 10107 and (any(row.get(key) != value for key, value in {
            "luaFile": "Lua/Levels/MainLine_Stage01/Level 1-7-Normal.lua",
            "hardLevel": 3, "recommendPlayerLevel": 3,
            "UseDropSeq": 1, "playerGetAllDrops": False}.items()) or
            row.get("firstDisplayDropList") != [
                {"id": 4009, "level": 0, "num": 3},
                {"id": 3000, "level": 0, "num": 4},
                {"id": 30054, "level": 0, "num": 1},
                {"id": 120010, "level": 0, "num": 1}] or
            row.get("challengeList") != [
                {"challengeId": 5007, "rewardId": 1},
                {"challengeId": 4004, "rewardId": 1},
                {"challengeId": 2002, "rewardId": 1}]):
        raise ValueError("Stage 10107 compatibility inputs changed; audit before use")
    return row


def _item_metadata(item_id):
    import server19_avatar_fragments as fragments
    if item_id in fragments.AUDITED_IDS:
        return "avatar_fragment", fragments.metadata(item_id)
    for name, kind in (("materialdata", "material"), ("weapondata", "weapon"),
                       ("stigmatadata", "stigmata")):
        rows = _table(name, field="ID", identities=(item_id,))
        if len(rows) == 1:
            return kind, rows[0]
        if len(rows) > 1:
            raise ValueError("Ambiguous item metadata")
    raise ValueError("Stage item has no supported original-compatible metadata")


def first_clear_drop_plan(config=None):
    """Explicit local compatibility plan from deployed firstDisplayDropList.

    This is a fixed authored plan, not restored historical drop probabilities.
    Later 7.0 DropID 200910 maps to 100x6000, conflicting with the deployed
    2.4 display's 4001x3; that mapping is deliberately NOT used. The other
    four later mappings corroborate display values but prove no old probability.
    Original HandleLevelEnd 69250 @c455b8-c45602 automatically moves the entire
    configured ground-drop list into actual drops on WIN when begin progress=0.
    is_equip_drop selects the additive list @c2bcce; it is a delivery flag,
    not the item's storage type. Keep this fixed plan in the ground-drop list.
    """
    config = config or stage_config()
    plan = []
    for row in config["firstDisplayDropList"]:
        item_id = _u32(row["id"], "drop id")
        kind, metadata = _item_metadata(item_id)
        count = _u32(row["num"], "drop num")
        if not count:
            if config.get("type") == 7:
                # Extra display-only entries have no authored fixed quantity.
                # Do not turn a zero preview into an invented first-clear grant.
                continue
            raise ValueError("Empty configured first-clear reward")
        # Original WeaponDataItem ctor 52613@144abad initializes level=1,
        # exp=0@144abc1 and number=1@144abc8. A display level=0 therefore
        # uses that native newly constructed weapon level. Original Stigmata
        # ctor52069@138efa4/138efb8/138efbf likewise sets level1/exp0/number1.
        # Material wire
        # records only hold id/num, and their display level remains zero.
        level = row["level"] or (1 if kind in ("weapon", "stigmata") else 0)
        plan.append({"item_id": item_id, "level": level, "num": count,
                     "rarity": _u32(metadata["rarity"], "drop rarity"),
                     "is_equip_drop": False})
    return plan


def _has_audited_active_plan(active, config):
    if active.get("drop_policy") == "local_authored_conservative_v1":
        import server19_repeat_drops
        return server19_repeat_drops.validate_active(active, config)
    plan = first_clear_drop_plan(config)
    begin = active.get("begin_response", {})
    return active.get("drop_policy") == FIRST_CLEAR_DROP_POLICY and \
        active.get("drop_plan") == plan and begin.get("drop_item_list") == plan and \
        active.get("stage_id") == begin.get("stage_id") == config["levelId"] and \
        begin.get("progress") == 0


@contextmanager
def _transaction_lock(path):
    # Independent of server19.event's lock. The file lock serializes multiple
    # server processes as well as this process's request threads.
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_name(path.name + ".stage.lock").open("a+b") as lock:
            lock.seek(0, os.SEEK_END)
            if not lock.tell():
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                deadline = time.monotonic() + 10
                while True:
                    try:
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


# One exact-content parse cache, protected by the existing process lock.
# 每次仍读文件；跨进程锁、原子写入及每次身份验证保持原样。
_READ_CACHE = None


def _read(path, account):
    global _READ_CACHE
    import marshal
    with _LOCK:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Stage transaction requires an existing ordinary account file")
        raw = path.read_bytes()
        if _READ_CACHE is not None and _READ_CACHE[0] == path and _READ_CACHE[1] == raw:
            current = marshal.loads(_READ_CACHE[2])
        else:
            current = json.loads(raw.decode('utf-8'))
            encoded = marshal.dumps(current, 4)
            _READ_CACHE = (path, raw, encoded)
        if current.get("schema") != 1 or current.get("uid") != account.get("uid"):
            raise ValueError("Stage account identity/schema changed")
        return current


def copy_account(value):
    """Copy a decoded JSON account tree without deepcopy's per-scalar bookkeeping.

    Account transactions read JSON from disk, so mutable containers are dict/list,
    and there are no shared references or cycles. Other values fail explicitly.
    """
    kind = type(value)
    if kind is dict:
        result = value.copy()
        items = value.items()
    elif kind is list:
        result = value.copy()
        items = enumerate(value)
    elif kind in (str, int, float, bool, type(None)):
        return value
    else:
        raise TypeError('Account must contain JSON values')
    for key, item in items:
        if type(item) in (dict, list):
            result[key] = copy_account(item)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise TypeError('Account must contain JSON values')
    return result


def _sync(account, current):
    if account == current:
        return
    account.clear()
    account.update(copy_account(current))


ACCOUNT_MAINTENANCE = None


def refresh_account(account, account_path=None):
    path = Path(account_path or DEFAULT_ACCOUNT).resolve()
    with _transaction_lock(path):
        before = _read(path, account)
        current = copy_account(before)
        if ACCOUNT_MAINTENANCE is not None:
            ACCOUNT_MAINTENANCE(current)
        _save(path, before, current)
        _sync(account, current)
    return account


def _save(path, before, current):
    import server19_account_maintenance as maintenance
    maintenance.normalize_gold(current)
    if current == before:
        return
    # Exact pre-execution bytes remain beside the account. Existing backups
    # are retained; a stage or tutorial report never invents a new baseline.
    backup = path.with_name(path.stem + "-before-first-stage-execution" + path.suffix)
    try:
        with backup.open("xb") as output:
            output.write(path.read_bytes())
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        pass
    temporary = path.with_name(path.name + ".stage-" + secrets.token_hex(8) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            # One encoded write instead of thousands of tiny writes on Android.
            output.write(json.dumps(current, ensure_ascii=False, separators=(',', ':')) + "\n")
            output.flush()
            os.fsync(output.fileno())
        deadline = time.monotonic() + 3
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
    finally:
        if temporary.exists():
            temporary.unlink()


def _runtime(account):
    runtime = account.setdefault("stage_runtime", {"schema": 1, "active": None,
                                                 "settlements": []})
    if runtime.get("schema") != 1 or not isinstance(runtime.get("settlements"), list):
        raise ValueError("Unsupported stage transaction state")
    return runtime


def _empty_stage(stage_id):
    return {"id": stage_id, "progress": 0, "enter_times": 0,
            "reset_times": 0, "assist_enter_times": 0,
            "challenge_index_list": [], "stamina_discount": 100,
            "is_done": False}


def _stage(account, stage_id=STAGE_ID, *, create=False):
    rows = [row for row in account.get("stage_list", []) if row.get("id") == stage_id]
    if len(rows) > 1:
        raise ValueError("Duplicate stored stage IDs")
    if rows:
        return rows[0]
    if not create:
        return None
    # A record is created only for a legitimate Begin, after real prerequisites
    # pass. No future stages, guide groups, or synthetic unlock flags are saved.
    stage = _empty_stage(stage_id)
    account.setdefault("stage_list", []).append(stage)
    return stage


def available_stage_list(account):
    """Read-only native stage snapshot, including legitimately available stages.

    Original OnGetStageDataRsp69126@c122d1/c122e6 initializes a listed type1
    item; Init68447@b9d158-b9d17a selects status2 using bit1 of0x2082.
    Unlisted metadata placeholders remain status1. MonoActButton.SetupActView
    85064@d50f30-d50f39 requires any item with status!=1; GetPackedTitle85073
    @d514bc-d51536 otherwise displays the previous-Act completion warning.
    Thus available, never-entered stages need real zero-progress Stage records
    in queries/notifications. Their availability follows persisted prerequisites,
    not synthetic completion or unlock flags. Only Begin writes entered state.
    """
    rows = deepcopy(account.get("stage_list", []))
    stored = {row["id"]: row for row in rows}
    if len(stored) != len(rows):
        raise ValueError("Duplicate stored stage IDs")
    for stage_id in supported_stage_ids():
        if stage_id in stored:
            continue
        config = stage_config(stage_id)
        if account["main"]["level"] < config["unlockPlayerLevel"]:
            continue
        prerequisites = [value for value in config["preLevelID"] if value]
        if any(value not in stored or not stored[value].get("is_done") or
               stored[value].get("progress", 0) < stage_config(value)["maxProgress"]
               for value in prerequisites):
            continue
        if config["unlockStarNum"] and chapter_star_count(account, config["chapterId"],
                                                       config["difficulty"]) < config["unlockStarNum"]:
            continue
        rows.append(_empty_stage(stage_id))
    # 战斗学院教学关 901001..901008 (等级 >= 5 且通关 1-1 后解锁)
    if account["main"]["level"] >= 5 and 10101 in stored:
        for t_id in range(901001, 901009):
            if t_id not in stored:
                rows.append(_empty_stage(t_id))
    return rows


def chapter_star_count(account, chapter_id, difficulty):
    """Original same-Chapter/same-difficulty scope, including visible Extras.

    GetTotalFinishedChanllengeNum68120@85abf2 uses GetLevelList(difficulty),
    skips unavailable status1 and counts done challenge states. With this local
    batch's native IsExtraActHide=false it includes Extra stages as well. Server
    counting additionally requires our real saved successful WIN receipt.
    """
    import server19_missions as missions
    wins = missions._confirmed_wins(account)
    total = 0
    for saved in account.get("stage_list", []):
        if saved.get("id") not in wins:
            continue
        config = stage_config(saved["id"])
        if (config["chapterId"], config["difficulty"]) != (chapter_id, difficulty):
            continue
        indices = saved.get("challenge_index_list", [])
        if not isinstance(indices, list) or len(set(indices)) != len(indices) or any(
                type(index) is not int or not 0 <= index < len(config["challengeList"])
                for index in indices):
            raise ValueError("Invalid saved chapter-star indices")
        total += len(indices)
    return total


def _begin(account, request):
    name = "StageBeginRsp"
    stage_id = _u32(request.get("stage_id", 0), "stage_id")
    if stage_id not in supported_stage_ids():
        return name, {"retcode": 2}
    if request.get("is_fast_pass_stage", False) is not False:
        return name, {"retcode": 22}
    assistant_uid = _u32(request.get("assistant_uid", 0), "assistant UID")
    if request.get("avatar_trial_id_list", []):
        return name, {"retcode": 5}
    if assistant_uid:
        import server19_friends
        if server19_friends.assistant(assistant_uid) is None:
            return name, {"retcode": 5}
    avatars = request.get("avatar_id_list", [])
    prescribed = STORY_TRIAL_AVATARS.get(stage_id)
    # Native multi-trial preparation serializes one three-slot block per trial.
    # Trial blocks must match the exact configured roster.
    trial_blocks = (isinstance(avatars, list) and prescribed is not None
                    and 1 < len(prescribed) <= 3 and len(avatars) == 3 * len(prescribed)
                    and all(type(value) is int for value in avatars)
                    and set(avatars[::3]) == set(prescribed)
                    and all(value == 0 for index, value in enumerate(avatars) if index % 3))
    config = stage_config(stage_id)
    # Ordinary multi-team stages use the same three-slot wire blocks as trials,
    # but their team count/capacities come from stage metadata, not trial rosters.
    multi_team = config.get("teamNum", 1) > 1 and prescribed is None
    if multi_team:
        capacities = config.get("maxNumList", [])
        if (not isinstance(avatars, list) or len(avatars) != 3 * config["teamNum"]
                or len(capacities) != config["teamNum"]
                or any(type(limit) is not int or not 1 <= limit <= 3 for limit in capacities)
                or any(not 1 <= sum(value != 0 for value in avatars[i * 3:i * 3 + 3]) <= limit
                       for i, limit in enumerate(capacities))):
            return name, {"retcode": 13}
    elif not isinstance(avatars, list) or not avatars or (len(avatars) > 3 and not trial_blocks):
        return name, {"retcode": 13}
    # Native preparation sends all three slots, including empty zero slots
    # (captured original request: [101, 0, 0]). Preserve slot positions for the
    # retry fingerprint while ownership and experience apply to occupied slots.
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in avatars):
        return name, {"retcode": 5}
    occupied = [value for value in avatars if value]
    if not occupied or len(set(occupied)) != len(occupied):
        return name, {"retcode": 5}
    owned = {avatar["avatar_id"] for avatar in account.get("avatar_list", [])}
    prescribed = STORY_TRIAL_AVATARS.get(stage_id)
    if prescribed is not None and not set(occupied) <= set(prescribed):
        return name, {"retcode": 5}
    if not set(occupied) <= owned | set(prescribed or ()):
        return name, {"retcode": 5}
    if account["main"]["level"] < config["unlockPlayerLevel"]:
        return name, {"retcode": 3}
    for prerequisite_id in config["preLevelID"]:
        if not prerequisite_id:
            continue
        prerequisite = _stage(account, prerequisite_id)
        prerequisite_config = stage_config(prerequisite_id)
        if prerequisite is None or not prerequisite.get("is_done") or \
                prerequisite.get("progress", 0) < prerequisite_config["maxProgress"]:
            # Original StageBeginRsp.Retcode.PRE_STAGE_NOT_FINISH=34:
            # original metadata field11841, field-default record at header64.
            return name, {"retcode": 34}
    if config["unlockStarNum"] and chapter_star_count(account, config["chapterId"],
                                                   config["difficulty"]) < config["unlockStarNum"]:
        # Original enum field11821: CHALLENGE_NUM_LACK=14.
        return name, {"retcode": 14}
    fingerprint = hashlib.sha256(json.dumps({"stage_id": stage_id,
        "avatar_id_list": avatars, **({"assistant_uid": assistant_uid} if assistant_uid else {})},
        sort_keys=True).encode("utf-8")).hexdigest()
    runtime = _runtime(account)
    active = runtime.get("active")
    if active:
        if active.get("begin_fingerprint") != fingerprint:
            return name, {"retcode": 1}
        if not _has_audited_active_plan(active, config):
            # Older Begin-only research fixtures supplied no drop plan. Preserve
            # their record for audit/EXIT, never turn that empty plan into a
            # successful first clear with silently missing rewards.
            return name, {"retcode": 1}
        return name, deepcopy(active["begin_response"])
    level = _stage(account, stage_id, create=True)
    cost = config["staminaCost"]
    if _u32(account["main"]["stamina"], "stamina") < cost:
        return name, {"retcode": 4}
    if level.get("enter_times", 0) >= config["enterTimes"]:
        return name, {"retcode": 7}
    # First clears retain their exact accepted compatibility plan. Repeats use
    # the user's explicit local conservative policy, not an old RNG claim.
    progress = level.get("progress", 0)
    drop_audit = None
    drop_policy = FIRST_CLEAR_DROP_POLICY
    if progress == 0:
        plan = first_clear_drop_plan(config)
    elif progress == config["maxProgress"] and level.get("is_done") is True:
        import server19_repeat_drops
        plan, drop_audit = server19_repeat_drops.draw(config)
        drop_policy = server19_repeat_drops.SOURCE_POLICY
    else:
        return name, {"retcode": 1}
    # Preview the shared compatible EXP/level-reward plan before charging.
    # Preview changes only this disposable copy; no level rewards at Begin.
    preview = deepcopy(account)
    player_rows = _table("playerleveldata")
    player_progression.grant_player_exp(preview["main"], config["playerExpReward"])
    player_config = next(row for row in player_rows if row["level"] == preview["main"]["level"])
    for avatar in preview["avatar_list"]:
        if avatar["avatar_id"] in occupied:
            _add_exp(avatar, config["avatarExpReward"], "avatarleveldata",
                     player_config["avatarLevelLimit"])
    if len(account.get("weapon_list", [])) + len(account.get("stigmata_list", [])) + \
            sum(row["num"] for row in plan if _item_metadata(row["item_id"])[0] in
                ("weapon", "stigmata")) > \
            account["main"]["equipment_size_limit"]:
        return name, {"retcode": 6}
    _grant_drops(preview, _drop_totals(plan))
    result = {"retcode": 0, "stage_id": stage_id,
              "progress": progress, "drop_item_list": plan,
              "is_collect_cheat_data": False, "sign_key": secrets.token_hex(16),
              "tag": 0, "equip_buff_list": [], "battle_buff_list": [],
              "battle_attr_list": []}
    account["main"]["stamina"] -= cost
    level["enter_times"] = _u32(level.get("enter_times", 0) + 1, "enter_times")
    if assistant_uid:
        level["assist_enter_times"] = _u32(level.get("assist_enter_times", 0) + 1, "assist enter times")
    runtime["active"] = {"stage_id": stage_id, "avatar_id_list": occupied,
                         "avatar_slots": list(avatars),
                         "begin_fingerprint": fingerprint,
                         "begin_response": deepcopy(result),
                         "started_at": time.time(), "stamina_cost": cost,
                         "drop_plan": deepcopy(plan),
                         "drop_policy": drop_policy}
    if assistant_uid:
        runtime["active"]["assistant_uid"] = assistant_uid
    if drop_audit is not None:
        runtime["active"]["drop_audit"] = deepcopy(drop_audit)
    return name, result


def stage_end_signature(body, sign_key):
    """Original x86 signing algorithm; body bytes must stay byte-identical."""
    return hashlib.sha256(bytes(body) + sign_key.encode("utf-8") +
                          ORIGINAL_REQUEST_SUFFIX.encode("utf-8")).hexdigest()


def _drop_totals(rows):
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Invalid drop list")
    totals = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid drop record")
        key = (_u32(row.get("item_id", 0), "item_id"),
               _u32(row.get("level", 0), "item level"))
        count = _u32(row.get("num", 0), "item num")
        if not key[0] or not count:
            raise ValueError("Empty drop")
        totals[key] = _u32(totals.get(key, 0) + count, "combined drop num")
    return totals


def _add_exp(target, amount, table_name, limit, *, allow_level_up=True):
    amount = _u32(amount, "experience reward")
    rows = {row["level"]: row for row in _table(table_name)}
    level = _u32(target["level"], "stored level")
    old_level = level
    exp = _u32(target.get("exp", 0) + amount, "stored experience")
    if level > limit or level not in rows:
        raise ValueError("Stored level has no audited experience row")
    while level < limit and exp >= rows[level]["exp"]:
        required = _u32(rows[level]["exp"], "next-level experience")
        if not required or level + 1 not in rows:
            raise ValueError("Invalid level progression configuration")
        exp -= required
        level += 1
    if not allow_level_up and level != old_level:
        raise ValueError("Player level-up rewards require a separate business audit")
    if level == limit and exp:
        if table_name != "avatarleveldata":
            raise ValueError("Capped experience conversion requires a separate business audit")
        # Same reviewed local cap/full-bar policy as material cultivation:
        # retain EXP up to this level's threshold, discard only overflow.
        # No invented currency conversion or captain-limit bypass.
        exp = min(exp, _u32(rows[level]["exp"], "capped avatar EXP"))
    target.update(level=level, exp=exp)


def _reward(reward_id):
    rows = _table("rewarddata", field="RewardID", identities=(reward_id,))
    if len(rows) != 1:
        raise ValueError("Missing configured challenge reward")
    row = rows[0]
    mapping = {"exp": "RewardExp", "scoin": "RewardSCoin", "hcoin": "RewardHCoin",
               "stamina": "RewardStamina", "skill_point": "RewardSkillPoint",
               "friends_point": "RewardFriendPoint", "duty_point": "RewardDutyPoint"}
    result = {name: _u32(row[key], key) for name, key in mapping.items()}
    result["item_list"] = [{"id": row[f"RewardItem{i}ID"],
                            "level": row[f"RewardItem{i}Level"],
                            "num": row[f"RewardItem{i}Num"]}
                           for i in range(1, 6) if row[f"RewardItem{i}ID"]]
    # Ordinary challenges use reward1 (5hcoin); original Extra rows use6
    # (10hcoin). The source row must match exactly before granting either.
    # Broader reward mutation types must be implemented before accepting them.
    if reward_id not in (1, 6) or result != {"exp": 0, "scoin": 0, "hcoin": 5 if reward_id == 1 else 10, "stamina": 0,
                                  "skill_point": 0, "friends_point": 0,
                                  "duty_point": 0, "item_list": []}:
        raise ValueError("Challenge reward needs an additional business audit")
    return result


def _grant_drops(account, totals):
    for (item_id, level), count in totals.items():
        kind, metadata = _item_metadata(item_id)
        if kind == "avatar_fragment":
            import server19_avatar_fragments as fragments
            fragments.grant(account, item_id, level, count)
        elif kind == "material":
            materials = account.setdefault("material_list", [])
            rows = [row for row in materials if row.get("id") == item_id]
            if len(rows) > 1:
                raise ValueError("Duplicate stored material IDs")
            if rows:
                total = _u32(rows[0].get("num", 0) + count, "stored material num")
                if total > metadata["quantityLimit"]:
                    raise ValueError("Material quantity limit would lose a first-clear reward")
                rows[0]["num"] = total
            else:
                if count > metadata["quantityLimit"]:
                    raise ValueError("Material reward exceeds its configured quantity limit")
                materials.append({"id": item_id, "num": count})
        else:
            if not 1 <= level <= metadata["maxLv"]:
                raise ValueError("Invalid equipment reward level")
            equipment = account.setdefault("weapon_list" if kind == "weapon"
                                           else "stigmata_list", [])
            # Original consts: Weapon UID_BEGIN_NUM0/MAX_UID_NUM20000;
            # Stigmata UID_BEGIN_NUM20000/MAX_UID_NUM40000. Stay strictly
            # inside each type's range and preserve global inventory uniqueness.
            uid_begin, uid_limit = (0, 20000) if kind == "weapon" else (20000, 40000)
            all_uids = [row["unique_id"] for name in ("weapon_list", "stigmata_list")
                        for row in account.get(name, [])]
            if len(set(all_uids)) != len(all_uids):
                raise ValueError("Duplicate stored equipment unique IDs")
            typed_uids = [row["unique_id"] for row in equipment]
            if any(not uid_begin < value < uid_limit for value in typed_uids):
                raise ValueError("Stored equipment UID is outside its original type range")
            unique_id = max(typed_uids, default=uid_begin) + 1
            for _ in range(count):
                if unique_id >= uid_limit or unique_id in all_uids:
                    raise ValueError("Original equipment UID range is exhausted")
                equipment.append({"unique_id": _u32(unique_id, "equipment unique id"),
                                  "id": item_id, "level": level, "exp": 0,
                                  "is_protected": False})
                all_uids.append(unique_id)
                unique_id += 1


def _end(account, request):
    name = "StageEndRsp"
    raw = request.get("body")
    sign = request.get("sign")
    if not isinstance(raw, (bytes, bytearray)) or not 1 <= len(raw) <= 1024 * 1024:
        return name, {"retcode": 2}
    if not isinstance(sign, str) or len(sign) != 64:
        return name, {"retcode": 2}
    digest = hashlib.sha256(bytes(raw) + b"\0" + sign.encode("utf-8")).hexdigest()
    runtime = _runtime(account)
    # A response-lost retry survives reconnect and process restart. The exact
    # body+signature receipt is committed atomically with all awarded progress.
    for receipt in runtime["settlements"]:
        if receipt.get("request_digest") == digest:
            return name, deepcopy(receipt["response"])
    active = runtime.get("active")
    if not active or not secrets.compare_digest(
            sign, stage_end_signature(raw, active["begin_response"]["sign_key"])):
        return name, {"retcode": 2}
    try:
        body = proto.decode_message("StageEndReqBody", bytes(raw))
        stage_id = body.get("stage_id")
        if stage_id not in supported_stage_ids() or active["stage_id"] != stage_id:
            return name, {"retcode": 2}
        status = body.get("end_status")
        if type(status) is not int or status not in (1, 2, 3, 4):
            return name, {"retcode": 2}
        challenges = body.get("challenge_index_list", [])
        if not isinstance(challenges, list) or len(set(challenges)) != len(challenges):
            return name, {"retcode": 4}
        config = stage_config(stage_id)
        if status == STAGE_WIN and not _has_audited_active_plan(active, config):
            return name, {"retcode": 3}
        if any(type(index) is not int or not 0 <= index < len(config["challengeList"])
               for index in challenges):
            return name, {"retcode": 4}
        drops = _drop_totals(body.get("drop_item_list", []))
        planned = _drop_totals(active.get("drop_plan", []))
        if any(key not in planned or count > planned[key] for key, count in drops.items()):
            return name, {"retcode": 3}
        if status == STAGE_WIN and active["begin_response"]["progress"] == 0 and drops != planned:
            # Original HandleLevelEnd auto-collects this entire first-clear plan.
            # Do not mark a supposedly successful clear while silently losing it.
            return name, {"retcode": 3}
        _u32(body.get("stage_pass_time", 0), "stage_pass_time")
        for key in ("scoin_reward", "avatar_exp_reward"):
            _u32(body.get(key, 0), key)
        if body.get("scoin_reward", 0) > config["maxScoinReward"] or \
                body.get("avatar_exp_reward", 0) > config["maxAvatarExpReward"]:
            return name, {"retcode": 3}
    except (ValueError, TypeError, KeyError):
        return name, {"retcode": 2}
    level = _stage(account, stage_id)
    if level is None:
        return name, {"retcode": 2}
    result = {"retcode": 0, "stage_id": stage_id,
              "player_exp_reward": 0, "avatar_exp_reward": 0, "scoin_reward": 0,
              "challenge_list": [], "friends_point_add": 0,
              "progress": level.get("progress", 0), "special_challenge_list": []}
    player_exp_audit = None
    if status == STAGE_WIN:
        previous = set(level.get("challenge_index_list", []))
        for index in challenges:
            if index not in previous:
                reward = _reward(config["challengeList"][index]["rewardId"])
                result["challenge_list"].append({"challenge_index": index, "reward": reward})
                account["main"]["hcoin"] = _u32(account["main"].get("hcoin", 0) +
                                                 reward["hcoin"], "stored hcoin")
        level["challenge_index_list"] = sorted(previous | set(challenges))
        level.update(progress=config["maxProgress"], is_done=True)
        pass_time = body.get("stage_pass_time", 0)
        if pass_time:
            level["min_stage_time"] = min(level.get("min_stage_time") or pass_time, pass_time)
        result.update(player_exp_reward=config["playerExpReward"],
                      avatar_exp_reward=config["avatarExpReward"],
                      scoin_reward=config["scoinReward"], progress=level["progress"])
        account["main"]["scoin"] = _u32(account["main"].get("scoin", 0) +
                                         config["scoinReward"], "stored scoin")
        player_rows = _table("playerleveldata")
        player_exp_audit = player_progression.grant_player_exp(account["main"], config["playerExpReward"])
        result['scoin_reward'] += player_exp_audit.get('cap_exp_conversion', {}).get('scoin', 0)
        player_config = next(row for row in player_rows if row["level"] == account["main"]["level"])
        for avatar in account["avatar_list"]:
            if avatar["avatar_id"] in active["avatar_id_list"]:
                _add_exp(avatar, config["avatarExpReward"], "avatarleveldata",
                         player_config["avatarLevelLimit"])
        _grant_drops(account, drops)
        # Daily tasks "首次胜利" (any cleared stage) and "好友助战" (a cleared stage
        # entered with an assistant) advance here.
        import server19_duty
        server19_duty.note_event(account, "stage_win")
        if active.get("assistant_uid"):
            server19_duty.note_event(account, "stage_win_assist")
    # Loss/exit is acknowledged without fabricated progress, challenges or loot.
    # Stage stamina was debited once at begin; an unproven historical refund
    # schedule is not inferred from a newer server version.
    runtime["settlements"].append({"request_digest": digest,
        "stage_id": stage_id, "end_status": status, "response": deepcopy(result),
        "completed_at": time.time(), "drop_policy": active.get("drop_policy"),
        "accepted_drops": body.get("drop_item_list", []) if status == STAGE_WIN else []})
    if "drop_audit" in active:
        runtime["settlements"][-1]["drop_audit"] = deepcopy(active["drop_audit"])
    if "revive_audit" in active:
        runtime["settlements"][-1]["revive_audit"] = deepcopy(active["revive_audit"])
    if player_exp_audit is not None:
        runtime["settlements"][-1]["player_progression"] = player_exp_audit
    runtime["active"] = None
    return name, result


def _revive(account, request):
    """Original AvatarReviveRsp returns used count, not remaining count.

    Native75836 sets available=max-revive_times;68452 clamps cost row to
    the last row and indexes Type1 by stage.reviveCostType.
    """
    name = "AvatarReviveRsp"
    active = _runtime(account).get("active")
    if not active:
        return name, {"retcode": 4}  # Original NOT_IN_STAGE.
    retry = request.get("is_retry", False)
    if type(retry) is not bool:
        return name, {"retcode": 1}
    count = _u32(active.get("revive_times", 0), "revive_times")
    if retry:
        # A retry queries the previous accepted operation, never charges again.
        return name, ({"retcode": 0, "revive_times": count} if count else {"retcode": 1})
    config = stage_config(active["stage_id"])
    if count >= _u32(config["reviveTimes"], "revive limit"):
        return name, {"retcode": 3}  # Original TIMES_LACK.
    rows = _table("stagerevivecostdata")
    number = min(count + 1, len(rows))
    row = next((row for row in rows if row["reviveTimes"] == number), None)
    kind = _u32(config["reviveCostType"], "revive cost type")
    if row is None or kind >= len(row["Type1"]):
        return name, {"retcode": 1}
    cost = _u32(row["Type1"][kind], "revive cost")
    balance = _u32(account["main"]["hcoin"], "hcoin")
    if balance < cost:
        return name, {"retcode": 2}  # Original HCOIN_LACK.
    account["main"]["hcoin"] = balance - cost
    active["revive_times"] = count + 1
    active.setdefault("revive_audit", []).append({"revive_times": count + 1,
        "hcoin_cost": cost, "balance_after": balance - cost, "at": time.time()})
    return name, {"retcode": 0, "revive_times": count + 1}


def revive_notification_snapshot(account):
    import server19_initialization
    return [server19_initialization.response("GetMainDataReq", account)]


def _guide(account, request):
    ids = request.get("guide_id_list", [])
    if not isinstance(ids, list) or not ids or len(ids) > 256 or \
            any(type(value) is not int for value in ids) or len(set(ids)) != len(ids):
        return "FinishGuideReportRsp", {"retcode": 1}
    # Only IDs actually reported by the client are persisted. This union never
    # completes prerequisite groups or bulk-reports a tutorial. Native handler
    # 71015@141d2b8 compares returned IDs to its pending list exactly.
    valid = {row["id"] for row in _table("tutorialdata")}
    valid.update(row["tutorialId"] for row in _table("stagetutorialdata"))
    # Original LoadVideo 65627@bbd333 -> MarkCGIDFinish 67615@844032
    # reports CgID via RequestFinishGuideReport@8440ea before video playback.
    # Plot completion uses the same native report consumer. These domains are
    # validated from their actual deployed rows, never pre-completed in bulk.
    valid.update(row["CgID"] for row in _table("cgdata"))
    valid.update(row["plotID"] for row in _table("plotdata"))
    if not set(ids) <= valid:
        return "FinishGuideReportRsp", {"retcode": 1}
    completed = set(account.get("guide_id_list", []))
    # Native supply step 91032 reports 9103 before the first pull. Grant its
    # configured ticket once, atomically with the completion marker. Forced
    # skip reports are not the observed reward flow and do not grant here.
    if 9103 in ids and 9103 not in completed and not request.get("is_force_finish", False):
        tutorial = next(row for row in _table("tutorialdata") if row["id"] == 9103)
        rewards = _table("rewarddata", field="RewardID", identities=(tutorial["Reward"],))
        if tutorial["Reward"] != 13005 or len(rewards) != 1:
            raise ValueError("Supply tutorial reward configuration changed")
        reward = rewards[0]
        if any(reward.get(key, 0) for key in ("RewardExp", "RewardSCoin", "RewardHCoin",
                "RewardStamina", "RewardSkillPoint", "RewardFriendPoint", "RewardDutyPoint")):
            raise ValueError("Supply tutorial currency reward needs review")
        items = [(reward[f"RewardItem{i}ID"], reward[f"RewardItem{i}Level"], reward[f"RewardItem{i}Num"])
                 for i in range(1, 6) if reward[f"RewardItem{i}ID"]]
        if items != [(1101, 0, 1)]:
            raise ValueError("Supply tutorial item reward needs review")
        _grant_drops(account, {(1101, 0): 1})
    account["guide_id_list"] = sorted(completed | set(ids))
    return "FinishGuideReportRsp", {"retcode": 0, "guide_id_list": list(ids), "is_finish": True}


def guide_notification_snapshot(account, request):
    # The next native tutorial step reads the ticket count immediately on Rsp.
    if 9103 not in request.get("guide_id_list", []):
        return []
    return [("GetEquipmentDataRsp", {"retcode": 0, **{key: deepcopy(account.get(key, []))
            for key in ("weapon_list", "stigmata_list", "material_list")}})]


def notification_snapshot(account):
    """Original packet types; send after the successful StageBegin/EndRsp.

    Each is an authoritative snapshot rather than incrementing client state.
    Native initialization consumers already accept these messages repeatedly.
    """
    import server19_initialization
    return [server19_initialization.response("GetMainDataReq", account),
            ("GetAvatarDataRsp", {"retcode": 0,
                                  "avatar_list": deepcopy(account.get("avatar_list", []))}),
            ("GetEquipmentDataRsp", {"retcode": 0, **{key: deepcopy(account.get(key, []))
                for key in ("weapon_list", "stigmata_list", "material_list")}}),
            ("GetStageDataRsp", {"retcode": 0,
                                 "stage_list": available_stage_list(account)})]


def response(request_name, account, request_values=None, *, account_path=None):
    handlers = {"StageBeginReq": _begin, "StageEndReq": _end,
                "FinishGuideReportReq": _guide, "AvatarReviveReq": _revive}
    if request_name not in handlers:
        return None
    path = Path(account_path or DEFAULT_ACCOUNT).resolve()
    with _transaction_lock(path):
        before = _read(path, account)
        current = deepcopy(before)
        try:
            result = handlers[request_name](current, request_values or {})
            proto.encode_message(*result)
            if result[1].get("retcode") == 0:
                if request_name in ("StageBeginReq", "StageEndReq"):
                    for packet in notification_snapshot(current):
                        proto.encode_message(*packet)
                if request_name == "FinishGuideReportReq":
                    for packet in guide_notification_snapshot(current, request_values or {}):
                        proto.encode_message(*packet)
                if request_name == "AvatarReviveReq":
                    for packet in revive_notification_snapshot(current):
                        proto.encode_message(*packet)
                _save(path, before, current)
                _sync(account, current)
            else:
                _sync(account, before)
        except (ValueError, TypeError, KeyError, OSError):
            result = (request_name[:-3] + "Rsp", {"retcode": 1})
            _sync(account, before)
        return result
