"""Export the evidenced stage 10101 Lua closure with explicit 1.9 ABI adaptation.

This helper reads the original 1.9 APK first, then the audited 2.4 TextAssets
only for missing paths. Source bytes are retained separately; only evidenced
call argument differences are adapted. It does not deploy, run a client,
patch native code, alter an account or assert runtime compatibility.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

import analyze19 as native
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / ".local-baseline/server19-dev/stage10101-with-tutorial-resources"
ENTRY = "lua/levels/mainline_stage01/level 1-1.lua"
TUTORIAL = "lua/levels/mainline_stage01/level tutorial.lua"
EXPECTED24 = {
    ENTRY: "c38ffa7f49ddec847eac4c1e45e284395c8a219b7f1acfa8dfe42cf0063c921e",
    TUTORIAL: "ea5dd440aba2956939f66ae607c66806cdcd72b4f1645ec956a5be5ddaeb0ac1",
    "lua/base/leveldesignnormal.lua": "78a145836ecb987506408145adcf8a45027132d1317249d5e8f125a866308295",
    "lua/base/inspect.lua": "9f94654dc7dc05bb6cdc3770c230802657106d8cddae67a3a349d36f386bf91e",
    "lua/base/common.lua": "fa8eb04d4ba29207653001209c616033722d5b96b28d1de8dc54fc948716d762",
    "lua/base/levelanalysecommon.lua": "ce4eefb154b2b9ff3ea592eb980bad43f67b69a1e89d6f4f6919d76590d1a89e",
    "lua/base/preset.lua": "c0853a2ff25cb58608e5809b5ddf2796903c85f2832c78bac25f749f82b3d3b4",
    "lua/base/leveldesigncommonmethods.lua": "f1eebcac2491753084572ff0d87fcc6ca173e3ae0df672196ee267d67ed5af9e",
    "lua/base/leveldesignluahack.lua": "2dee5f69ce4848ffc209c660b51596d50838a67257ce6a98aa10abe56814b5ab",
}
ORIGINAL19_SHA = "672c3eadd1300accb265f09dfce52f05965b15e4b1a8d54114913f3f4f87d5be"
NATIVE19_SHA = "dc8365244e56a9de670b326d40510cab688d6876107e6a9151372917963ada7d"
INSPECT = ROOT / ".local-baseline/server19-dev/resource-fallback/lua/base/inspect.lua"
ACT101_OUTPUT = ROOT / ".local-baseline/server19-dev/act101-entry-lua-resources"
ACT101_SOURCES = {
    "lua/levels/mainline_stage01/level 1-2.lua": "f1dc3ac4c6635b49554ed6111ecede6c3fdb2cb24980581a8e5e73ec4b2689e3",
    "lua/levels/mainline_stage01/level 1-3.lua": "fbb7d5696762e025acb5ccd12b2b588c07176f9ff3f07f450e720ee8ffc5f636",
    "lua/levels/mainline_stage01/level 1-4.lua": "8429a9293494094b224bc9203d335aa1060bd1b62763e1e33548d1ccc2baf82f",
    "lua/levels/mainline_stage01/level 1-5.lua": "d85c57e5f92ebc157a92c9b6fff98e6f31d9741f91dbc38e1978b60688120b32",
    "lua/levels/mainline_stage01/level 1-6.lua": "44e308f6d9c5967a46aab6941dc04f7be2582fef0a055da47fc62e3e49888148",
}
STAGE7_OUTPUT = ROOT / ".local-baseline/server19-dev/stage7-ready"
STAGE7_ENTRY = "lua/levels/mainline_stage01/level 1-7-normal.lua"
STAGE7_SOURCE_SHA = "59d026a92a40a3883f679c5a6b30cf358d73128a0725955c307c5f044c359f86"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def lua_tokens(text):
    """A lexical scanner: comments do not create imports/calls, strings stay atomic.

    This is not a Lua parser or an execution/reachability proof. Token offsets
    are retained to report the actual source line and argument expressions.
    """
    result, pos, size = [], 0, len(text)
    long_open = re.compile(r"\[(=*)\[")
    while pos < size:
        if text[pos].isspace():
            pos += 1
            continue
        if text.startswith("--", pos):
            match = long_open.match(text, pos + 2)
            if match:
                end = text.find("]" + match[1] + "]", match.end())
                if end < 0:
                    raise ValueError("Unclosed Lua long comment")
                pos = end + len(match[1]) + 2
            else:
                end = text.find("\n", pos + 2)
                pos = size if end < 0 else end + 1
            continue
        start = pos
        if text[pos] in ("'", '"'):
            quote = text[pos]
            pos += 1
            while pos < size:
                if text[pos] == "\\":
                    pos += 2
                elif text[pos] == quote:
                    pos += 1
                    break
                else:
                    pos += 1
            else:
                raise ValueError("Unclosed Lua string")
            result.append((text[start:pos], start, pos, "string"))
            continue
        match = long_open.match(text, pos)
        if match:
            end = text.find("]" + match[1] + "]", match.end())
            if end < 0:
                raise ValueError("Unclosed Lua long string")
            pos = end + len(match[1]) + 2
            result.append((text[start:pos], start, pos, "string"))
            continue
        if text.startswith("..", pos):
            atom = "..." if text.startswith("...", pos) else ".."
            pos += len(atom)
            result.append((atom, start, pos, "symbol"))
            continue
        number = re.match(r"(?:0[xX][0-9a-fA-F]+|(?:[0-9]+(?:\.(?!\.)[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", text[pos:])
        if number:
            pos += len(number[0])
            result.append((number[0], start, pos, "number"))
            continue
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*|\.\.\.", text[pos:])
        if match:
            pos += len(match[0])
            result.append((match[0], start, pos, "word"))
        else:
            pos += 1
            result.append((text[start:pos], start, pos, "symbol"))
    return result


def requires(text):
    tokens = lua_tokens(text)
    found = []
    for index, token in enumerate(tokens):
        if token[0] != "require" or (index and tokens[index - 1][0] in (".", ":")):
            continue
        item = index + 1
        parenthesized = item < len(tokens) and tokens[item][0] == "("
        if parenthesized:
            item += 1
        if item >= len(tokens) or tokens[item][3] != "string":
            raise ValueError("Dynamic require in audited Lua scope")
        raw = tokens[item][0]
        if parenthesized and (item + 1 >= len(tokens) or tokens[item + 1][0] != ')'):
            raise ValueError("Dynamic require expression in audited Lua scope")
        if raw[:1] not in ("'", '"') or "\\" in raw:
            raise ValueError("Unsupported require string")
        module = raw[1:-1]
        if not re.fullmatch(r"[A-Za-z0-9_ /.-]+", module) or ".." in module:
            raise ValueError("Unsafe Lua module path")
        found.append({"module": module, "path": "lua/" + module.lower() + ".lua",
                      "line": text.count("\n", 0, token[1]) + 1})
    return found


def method_signatures(*, include_mp=False):
    defaults = {struct.unpack_from("<3i", native.B, at)[0]
                for at in range(7458316, 7458316 + 24720, 12)}
    result = {}
    for index, name in native.N.items():
        prefixes = ("MoleMole.LevelDesignManager::", "MoleMole.LuaManager::")
        if include_mp: prefixes += ("MoleMole.MPLevelDesignManager::",)
        if not name.startswith(prefixes):
            continue
        method = native.M[index]
        parameters = []
        for param in range(method[3], method[3] + method[15]):
            data = struct.unpack_from("<4I", native.B, 7818260 + param * 16)
            parameters.append({"name": native.string(data[0]), "has_default": param in defaults})
        result.setdefault(name.rsplit("::", 1)[1], []).append({
            "method_index": index, "address": hex(native.pointer(method)), "declaring_name": name,
            "parameters": parameters, "maximum_args": len(parameters),
            "minimum_args": max((i + 1 for i, param in enumerate(parameters)
                                 if not param["has_default"]), default=0)})
    return result


def calls(text):
    tokens = lua_tokens(text)
    result = []
    for index in range(len(tokens) - 3):
        if tokens[index][0] != "LevelDesign" or tokens[index + 1][0] != ":" or tokens[index + 3][0] != "(":
            continue
        start, item, depth, boundaries = index + 3, index + 4, [], []
        blocks = []
        arg_start = tokens[start][2]
        while item < len(tokens):
            value = tokens[item][0]
            if value == ")" and not depth and not blocks:
                if text[arg_start:tokens[item][1]].strip():
                    boundaries.append(text[arg_start:tokens[item][1]].strip())
                break
            if value in ('function', 'if', 'repeat'):
                blocks.append(value)
            elif value in ('for', 'while'):
                blocks.append('await_do')
            elif value == 'do':
                if blocks and blocks[-1] == 'await_do': blocks[-1] = 'loop'
                else: blocks.append('do')
            elif value in ('end', 'until'):
                if not blocks: raise ValueError('Unbalanced Lua callback block')
                block = blocks.pop()
                if (value == 'until') != (block == 'repeat'):
                    raise ValueError('Mismatched Lua callback block')
            if value in ("(", "[", "{"):
                depth.append(value)
            elif value in (")", "]", "}"):
                if not depth or {"(": ")", "[": "]", "{": "}"}[depth.pop()] != value:
                    raise ValueError("Unbalanced Lua call expression")
            elif value == "," and not depth and not blocks:
                boundaries.append(text[arg_start:tokens[item][1]].strip())
                arg_start = tokens[item][2]
            item += 1
        else:
            raise ValueError("Unclosed Lua call")
        result.append({"method": tokens[index + 2][0],
                       "line": text.count("\n", 0, tokens[index][1]) + 1,
                       "arguments": boundaries,
                       # Varargs inside a callback body do not expand the
                       # enclosing native call's arguments. Inspect only an
                       # argument expression's direct expansion form.
                       "static_argument_count": None if any(re.match(r"^(?:unpack\s*\(|\.\.\.(?:\s|$))", arg)
                                                             for arg in boundaries) else len(boundaries)})
    return result


def text_record(package, record, source_version):
    obj, raw = resources.object_bytes(package, record)
    if obj["class"] != 49:
        raise ValueError("Expected a real Unity TextAsset: " + record["path"])
    name, payload = resources.text_asset(raw)
    return payload, {"source_version": source_version, "resource": record,
                     "object_class": obj["class"], "object_name": name,
                     "object_bytes": len(raw), "object_sha256": sha(raw),
                     "source_text_bytes": len(payload), "source_text_sha256": sha(payload)}


def adapt(path, source, signatures):
    """Only five pinned ASCII replacements; preserve every other source byte."""
    if path != "lua/base/leveldesignnormal.lua":
        return source, []
    monster = native.M[65953]
    score_index = monster[3] + 8
    score_name = native.string(struct.unpack_from("<4I", native.B, 7818260 + score_index * 16)[0])
    score_defaults = [struct.unpack_from("<3i", native.B, at)
                      for at in range(7458316, 7458316 + 24720, 12)
                      if struct.unpack_from("<i", native.B, at)[0] == score_index]
    if score_name != "score" or len(score_defaults) != 1:
        raise ValueError("Original CreateMonster score parameter evidence changed")
    _, default_type, offset = score_defaults[0]
    if default_type != 7 or offset < 0 or struct.unpack_from("<i", native.B, 7645960 + offset)[0] != 0:
        raise ValueError("Original CreateMonster score default is not the evidenced zero")
    replacements = [
        ("LevelEndNewWithPoint", "LevelDesign:LevelEndNewWithPoint(m_wave.result, m_wave.collectgoods,endCgId, m_wave.point, moveAvatarToOrigin)",
         "LevelDesign:LevelEndNewWithPoint(m_wave.result, m_wave.collectgoods,endCgId, m_wave.point)"),
        ("LevelEndNew", "LevelDesign:LevelEndNew(m_wave.result, m_wave.collectgoods,endCgId, moveAvatarToOrigin)",
         "LevelDesign:LevelEndNew(m_wave.result, m_wave.collectgoods,endCgId)"),
        ("LevelEndNewWithPoint", "LevelDesign:LevelEndNewWithPoint(m_wave.result, true, endCgId, m_wave.point, moveAvatarToOrigin)",
         "LevelDesign:LevelEndNewWithPoint(m_wave.result, true, endCgId, m_wave.point)"),
        ("LevelEndNew", "LevelDesign:LevelEndNew(m_wave.result,true, endCgId, moveAvatarToOrigin)",
         "LevelDesign:LevelEndNew(m_wave.result,true, endCgId)"),
        ("CreateMonster", "generate_final_drop_table(drops), exp, checkOutsideWall, disableBehaviorWhenInit, defaultState, faceToAvatar, bornOffStage,",
         "generate_final_drop_table(drops), exp, 0, checkOutsideWall, disableBehaviorWhenInit, defaultState, faceToAvatar, bornOffStage,"),
    ]
    result, changes = source, []
    for method, before, after in replacements:
        old, new = before.encode("ascii"), after.encode("ascii")
        if source.count(old) != 1 or result.count(old) != 1:
            raise ValueError("Pinned ABI adaptation site changed: " + method)
        position = source.index(old)
        candidates = signatures[method]
        if len(candidates) != 1 or candidates[0]["maximum_args"] != {
            "LevelEndNew": 3, "LevelEndNewWithPoint": 4, "CreateMonster": 20}[method]:
            raise ValueError("Native ABI evidence changed: " + method)
        changes.append({"source_byte_offset": position,
                        "source_line": source[:position].count(b"\n") + 1,
                        "before": before, "after": after,
                        "native19_signature": candidates[0],
                        "reason": ("Remove later moveAvatarToOrigin argument absent in original 1.9"
                                   if method != "CreateMonster" else
                                   "Restore original score argument after avatarExpReward using its native default zero; all following source arguments retain their original positions")})
        if method == "CreateMonster":
            changes[-1]["native19_default_evidence"] = {"parameter_index": score_index,
                                                       "parameter_name": score_name,
                                                       "default_type_index": default_type,
                                                       "default_data_offset": offset,
                                                       "value": 0}
        result = result.replace(old, new, 1)
    return result, changes


def original_evidence(package, mapping):
    data = package.read("assets/bin/Data/globalgamemanagers")
    info = resources.serialized(data)
    build = next(obj for obj in info["objects"].values() if obj["class"] == 141)
    reader = resources.Reader(data, build["offset"])
    scene_names = [reader.string() for _ in range(reader.read("i"))]
    scenes = []
    for index, name in enumerate(scene_names):
        if name not in ("Assets/Scenes/LevelScene.unity", "Assets/Scenes/NavMesh/Spaceship_Outside04.unity"):
            continue
        path = "assets/bin/Data/level" + str(index)
        scene = package.read(path)
        parsed = resources.serialized(scene)
        scenes.append({"scene": name, "build_index": index, "apk_entry": path,
                       "bytes": len(scene), "sha256": sha(scene),
                       "object_class_counts": {str(key): value for key, value in
                                               Counter(obj["class"] for obj in parsed["objects"].values()).items()},
                       "runtime_navigation_accepted": False})
    if len(scenes) != 2:
        raise ValueError("Original stage scene identity evidence is missing")
    proofs = []
    wanted = ["levels/thelevelv1", "stage/data/stage_spaceship",
              "stage/stage_spaceship_outside/perpstage_spaceship_outside",
              "stage/stage_spaceship_outside/env_outside_04",
              "weather/stagerenderingdata/style_01/style01_aircraft_outside",
              "auxobject/cameraanim/monster/see_dg_010",
              "auxobject/cameraanim/monster/tutorial_1",
              "auxobject/cameraanim/monster/tutorial_2"]
    for path in wanted:
        record = mapping.get(path)
        if record is None:
            raise ValueError("Original stage resource absent: " + path)
        obj, raw = resources.object_bytes(package, record)
        proofs.append({"resource": record, "object_class": obj["class"],
                       "object_bytes": len(raw), "object_sha256": sha(raw),
                       "deployment_role": "retained in original APK, not exported or replaced"})
    symbols = []
    for index, expected, address in [(78761, "MoleMole.GameEntryPageContext::StartFirstLevel", 0xAD0767),
                                      (65889, "MoleMole.LevelDesignManager::LoadLevelScript", 0xBD1AD0),
                                      (88069, "MoleMole.Miscs::LoadTextFileToString", 0xD1F511),
                                      (65962, "MoleMole.LevelDesignManager::CreateStage", 0xBDC6CA),
                                      (65396, "MoleMole.LevelDesignManager::LevelEndNew", 0xBAA5EF)]:
        if native.N[index] != expected or native.pointer(native.M[index]) != address:
            raise ValueError("Original native symbol identity changed")
        symbols.append({"index": index, "name": expected, "address": hex(address),
                        "parameter_count": native.M[index][15]})
    return {"native_image_sha256": sha(native.E), "symbols": symbols,
            "first_stage": {"id": 10101, "native_argument_site": "0xad07ea",
                            "instruction_contains_10101": "0x2775" in native.disasm(78761, 1200),
                            "historical_first_stage_lua_content_recovered": False},
            "scenes": scenes, "original_resources": proofs,
            "original_resource_map_lua_path_count": sum(path.startswith("lua/") for path in mapping)}


def tutorial_evidence(source, common, signatures):
    """Record the actual source tutorial and statically checked wave handlers."""
    if sha(source) != EXPECTED24[TUTORIAL]:
        raise ValueError("Tutorial source identity changed")
    tokens = lua_tokens(source.decode("utf-8-sig"))
    first_strings = [tokens[index + 1][0][1:-1] for index, token in enumerate(tokens[:-1])
                     if token[0] == "{" and tokens[index + 1][3] == "string"]
    monsters = Counter(value for value in first_strings if value in ("DeadWalker", "UlyssesWarrior"))
    if dict(monsters) != {"DeadWalker": 3, "UlyssesWarrior": 1}:
        raise ValueError("Audited tutorial Monster waves changed")
    handlers = ["CreateMonster", "CreateStageExitField", "MuteInput", "RecoveryInput",
                "PlayCameraAnimationOnAnimatorEntity", "StartInLevelLevelTimer",
                "StopInLevelLevelTimer", "ControlLevelDamageStastics", "HasLevelActorCountDownPlugin",
                "SetMonsterEnabled", "SetMonsterTrigger", "SetMonsterHPRatio", "SetInLevelUIActive",
                "SetLocalAvatarFaceTo", "DestroyHelperAvatar", "MainCameraFollowSetFar", "LevelEndNew"]
    actual_calls = calls(common.decode("utf-8-sig"))
    checks = []
    for name in handlers:
        found = [row for row in actual_calls if row["method"] == name]
        if not found or name not in signatures or any(row["static_argument_count"] is None or not any(
                sig["minimum_args"] <= row["static_argument_count"] <= sig["maximum_args"]
                for sig in signatures[name]) for row in found):
            raise ValueError("Tutorial handler lacks original method/static arity evidence: " + name)
        checks.append({"method": name, "source_call_lines": [row["line"] for row in found],
                       "static_argument_counts": [row["static_argument_count"] for row in found],
                       "native19_signatures": signatures[name], "static_arity_matches": True})
    return {"entry": TUTORIAL,
            "native_selection_evidence": "Original LoadLevelScript requested Lua/Levels/MainLine_Stage01/Level Tutorial.lua on incomplete-guide account; device PID2921 2026-10-11 16:47:40.967 TEXT_MISSING",
            "source_sha256": sha(source), "source_bytes_unchanged": True,
            "requires": requires(source.decode("utf-8-sig")),
            "stage": "Spaceship_Outside04", "born": "Born", "weather": "Style01_Aircraft_Outside",
            "bgm": "SpaceShip", "scene_nodes": ["Center01", "Spawn05", "Center", "TutorialPos"],
            "camera_animations": ["See_DG_010", "Tutorial_1", "Tutorial_2"],
            "monster_wave_counts": dict(monsters), "last_monster_hp_ratio": 0.4,
            "source_wave_opcodes": list(dict.fromkeys(value for value in first_strings if "=" not in value and "-" not in value)),
            "audited_handler_calls": checks,
            "guide_pause_hack": "HACK_destroyPause Func wave is source-commented; source retained unchanged",
            "runtime_reachability_and_original_tutorial_equivalence": "unaccepted; static source and method arity evidence only"}


def prepare(apk19, apk24, output):
    apk19, apk24, output = Path(apk19), Path(apk24), Path(output)
    if file_sha(apk19) != ORIGINAL19_SHA or sha(native.E) != NATIVE19_SHA:
        raise ValueError("Original 1.9 APK/native analysis source identity changed")
    old = {record["path"]: record for record in resources.resource_map(apk19)}
    later = {record["path"]: record for record in resources.resource_map(apk24)}
    rows, payloads, originals, queue = {}, {}, {}, [ENTRY, TUTORIAL]
    signatures = method_signatures()
    with zipfile.ZipFile(apk19) as original, zipfile.ZipFile(apk24) as reference:
        proofs = original_evidence(original, old)
        while queue:
            path = queue.pop(0)
            if path in rows:
                continue
            if path not in EXPECTED24:
                raise ValueError("Lua closure expanded beyond the audited nine paths: " + path)
            if path in old:
                payload, row = text_record(original, old[path], "1.9.0")
                row["role"] = "original_present_not_deployed"
            else:
                if path not in later:
                    raise ValueError("Source TextAsset absent: " + path)
                payload, row = text_record(reference, later[path], "2.4.0")
                if sha(payload) != EXPECTED24[path]:
                    raise ValueError("Audited later-source bytes changed: " + path)
                row["role"] = "missing_original_later_compatibility_candidate"
            source_payload = payload
            payload, adaptations = adapt(path, source_payload, signatures)
            text = payload.decode("utf-8-sig")
            deps = requires(text)
            call_rows = calls(text)
            for call in call_rows:
                candidates = signatures.get(call["method"], [])
                count = call["static_argument_count"]
                call["native19_signatures"] = candidates
                call["status"] = ("method_absent_in_original19" if not candidates else
                                  "dynamic_arity_not_proven" if count is None else
                                  "static_arity_matches" if any(sig["minimum_args"] <= count <= sig["maximum_args"]
                                                               for sig in candidates) else "static_arity_mismatch")
            row.update(path=path, bytes=len(payload), output_bytes=len(payload), output_sha256=sha(payload),
                       original19_resource_present=path in old,
                       source_bytes_unchanged=not adaptations, requires=deps, native_calls=call_rows,
                       adaptations=adaptations, reference_path="reference/" + path,
                       runtime_compatibility="not accepted; static findings are not reachability proof",
                       historical19_equivalence=False)
            rows[path], payloads[path] = row, payload
            originals[path] = source_payload
            queue.extend(dep["path"] for dep in deps)
    if set(rows) != set(EXPECTED24):
        raise ValueError("Audited nine-file Lua closure was not obtained")
    if not INSPECT.is_file() or INSPECT.read_bytes() != payloads["lua/base/inspect.lua"]:
        raise ValueError("Existing Inspect must remain byte-identical; refusing replacement")
    rows["lua/base/inspect.lua"]["existing_inspect"] = {
        "path": str(INSPECT), "sha256": file_sha(INSPECT), "byte_identical": True,
        "deployment_policy": "reuse existing file; verify device bytes independently"}
    # Validate every destination before any write; changed outputs are preserved.
    for path, payload in payloads.items():
        target = output / path
        if target.exists() and (not target.is_file() or target.read_bytes() != payload):
            raise ValueError("Preserve an existing changed output: " + str(target))
        source_target = output / "reference" / path
        if source_target.exists() and (not source_target.is_file() or source_target.read_bytes() != originals[path]):
            raise ValueError("Preserve an existing changed source copy: " + str(source_target))
    findings = [{"path": path, **call} for path, row in rows.items()
                for call in row["native_calls"] if call["status"] != "static_arity_matches"]
    manifest = {"format": "server19-stage10101-explicit-abi-adaptation-v2", "stage_id": 10101,
                "source19": {"path": str(apk19.resolve()), "bytes": apk19.stat().st_size,
                             "sha256": ORIGINAL19_SHA},
                "source24": {"path": str(apk24.resolve()), "bytes": apk24.stat().st_size,
                             "sha256": file_sha(apk24)},
                "entry": ENTRY, "entry_scripts": [ENTRY, TUTORIAL],
                "tutorial_evidence": tutorial_evidence(originals[TUTORIAL], payloads["lua/base/leveldesignnormal.lua"], signatures),
                "files": list(rows.values()), "closure_count": len(rows),
                "deployment_files": [path for path, row in rows.items() if not row["original19_resource_present"]],
                "original19_evidence": proofs, "static_compatibility_findings": findings,
                "limits": ["2.4 source copies remain unchanged in reference/; no claim of historical 1.9 script equivalence",
                           "Only the five recorded original 1.9 argument adaptations are applied to deployment bytes",
                           "Lua method existence/arity checks do not prove selected-branch reachability or type conversion",
                           "Variable unpack argument counts and nested native configuration compatibility need runtime evidence",
                           "No device deployment, native library, account, progress, stamina or service changes by this helper",
                           "Native stage entry, original exit and actual success settlement remain separate acceptance gates"]}
    manifest_path = output / "manifest.json"
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != text:
        raise ValueError("Existing manifest changed; preserve it and select a fresh output directory")
    output.mkdir(parents=True, exist_ok=True)
    for path, payload in payloads.items():
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(payload)
        source_target = output / "reference" / path
        source_target.parent.mkdir(parents=True, exist_ok=True)
        if not source_target.exists():
            source_target.write_bytes(originals[path])
    if not manifest_path.exists():
        manifest_path.write_text(text, encoding="utf-8")
    return manifest


def audit(output, apk19, apk24):
    """Reconstruct all sources in memory and compare hashes, closure and findings."""
    output = Path(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "server19-stage10101-explicit-abi-adaptation-v2":
        raise ValueError("Unsupported manifest")
    if {row["path"] for row in manifest["files"]} != set(EXPECTED24) or len(manifest["files"]) != 9:
        raise ValueError("Unexpected manifest Lua closure")
    for key, path in [("source19", apk19), ("source24", apk24)]:
        if file_sha(path) != manifest[key]["sha256"]:
            raise ValueError("Source APK hash changed: " + key)
    maps = {"1.9.0": {row["path"]: row for row in resources.resource_map(apk19)},
            "2.4.0": {row["path"]: row for row in resources.resource_map(apk24)}}
    signatures = method_signatures()
    all_findings = []
    with zipfile.ZipFile(apk19) as original, zipfile.ZipFile(apk24) as reference:
        archives = {"1.9.0": original, "2.4.0": reference}
        if original_evidence(original, maps["1.9.0"]) != manifest["original19_evidence"]:
            raise ValueError("Original native/resource evidence changed")
        for row in manifest["files"]:
            path, version = row["path"], row["source_version"]
            expected_version = "1.9.0" if path in maps["1.9.0"] else "2.4.0"
            if version != expected_version:
                raise ValueError("Original resource priority violated")
            payload, source = text_record(archives[version], maps[version][path], version)
            if any(row.get(key) != value for key, value in source.items()):
                raise ValueError("Source object provenance changed: " + path)
            if version == "2.4.0" and sha(payload) != EXPECTED24[path]:
                raise ValueError("Unaccepted later source")
            if (output / row["reference_path"]).read_bytes() != payload:
                raise ValueError("Retained source bytes changed: " + path)
            payload, adaptations = adapt(path, payload, signatures)
            if adaptations != row["adaptations"] or row["source_bytes_unchanged"] != (not adaptations):
                raise ValueError("Adaptation provenance changed: " + path)
            if (output / path).read_bytes() != payload or sha(payload) != row["output_sha256"] or len(payload) != row["bytes"]:
                raise ValueError("Exported deployment bytes changed: " + path)
            text = payload.decode("utf-8-sig")
            if requires(text) != row["requires"]:
                raise ValueError("Dependency evidence changed")
            checks = calls(text)
            for call in checks:
                candidates, count = signatures.get(call["method"], []), call["static_argument_count"]
                call["native19_signatures"] = candidates
                call["status"] = ("method_absent_in_original19" if not candidates else
                                  "dynamic_arity_not_proven" if count is None else
                                  "static_arity_matches" if any(sig["minimum_args"] <= count <= sig["maximum_args"]
                                                               for sig in candidates) else "static_arity_mismatch")
            if checks != row["native_calls"]:
                raise ValueError("Native signature audit evidence changed")
            all_findings.extend({"path": path, **call} for call in checks
                                if call["status"] != "static_arity_matches")
    if all_findings != manifest["static_compatibility_findings"]:
        raise ValueError("Static findings changed")
    if INSPECT.read_bytes() != (output / "lua/base/inspect.lua").read_bytes():
        raise ValueError("Existing Inspect changed")
    if manifest.get("entry_scripts") != [ENTRY, TUTORIAL] or manifest.get("tutorial_evidence") != tutorial_evidence(
            (output / "reference" / TUTORIAL).read_bytes(),
            (output / "lua/base/leveldesignnormal.lua").read_bytes(), signatures):
        raise ValueError("Tutorial selection/closure evidence changed")
    return {"status": "source_bytes_and_static_evidence_verified", "files": 9,
            "findings": dict(Counter(row["status"] for row in all_findings)),
            "runtime_compatibility": "unaccepted", "manifest_sha256": file_sha(output / "manifest.json")}


def normal_monster_waves(text, monster_names):
    """Read static wave tables; the wave count is separate from NPC hard level."""
    tokens, stack, tables = lua_tokens(text), [], []
    for index, token in enumerate(tokens):
        if token[0] == "{":
            stack.append(index)
        elif token[0] == "}":
            if not stack:
                raise ValueError("Unbalanced stage table")
            tables.append((stack.pop(), index))
    if stack:
        raise ValueError("Unclosed stage table")
    records = []
    for left, right in sorted(tables):
        if left + 1 >= right or tokens[left + 1][3] != "string":
            continue
        first = tokens[left + 1][0][1:-1]
        if first == "Elite":
            if tokens[left + 2][0] != "," or tokens[left + 3][3] != "string":
                raise ValueError("Dynamic Elite monster selection")
            monster_name = tokens[left + 3][0][1:-1]
        elif first in monster_names:
            monster_name = first
        else:
            continue
        depth, fields = 0, {}
        for index in range(left + 1, right):
            value = tokens[index][0]
            if value in ("{", "(", "["):
                depth += 1
            elif value in ("}", ")", "]"):
                depth -= 1
            if depth == 0 and value in ("mode", "configType", "hard_level") and tokens[index + 1][0] == "=":
                atom = tokens[index + 2]
                if atom[3] not in ("string", "word", "number"):
                    raise ValueError("Dynamic wave selection field")
                fields[value] = atom[0][1:-1] if atom[3] == "string" else atom[0]
        # Section preloads use {monsterName, typeName}, unlike spawn waves.
        # Resolve only direct children of a named preloadmonsters table.
        parents = [(a, z) for a, z in tables if a < left and right < z]
        parent = max(parents, default=None, key=lambda pair: pair[0])
        is_preload = (parent is not None and parent[0] >= 2
                      and tokens[parent[0] - 2][0] == 'preloadmonsters'
                      and tokens[parent[0] - 1][0] == '=')
        if is_preload:
            if (first == 'Elite' or right != left + 4
                    or tokens[left + 2][0] != ',' or tokens[left + 3][3] != 'string'):
                raise ValueError('Unresolved preloadmonsters pair')
            fields['configType'] = tokens[left + 3][0][1:-1]
        mode = fields.get("mode", "Normal&Hard&Hell")
        if "Normal" not in mode.split("&"):
            continue
        attributes = []
        depth = 0
        attr_start = None
        for index in range(left + 1, right):
            value = tokens[index][0]
            if depth == 0 and value == 'attr' and tokens[index + 1][0] == '=' and tokens[index + 2][0] == '{':
                attr_start = index + 2
                break
            if value in ('{', '(', '['): depth += 1
            elif value in ('}', ')', ']'): depth -= 1
        if attr_start is not None:
            depth = 1
            for index in range(attr_start + 1, right):
                value = tokens[index][0]
                if depth == 1 and tokens[index][3] == 'word' and tokens[index + 1][0] == '=':
                    attributes.append(value)
                elif depth == 1 and value == '[' and tokens[index + 1][3] == 'string' and tokens[index + 2][0] == ']' and tokens[index + 3][0] == '=':
                    attributes.append(tokens[index + 1][0][1:-1])
                if value in ('{', '(', '['): depth += 1
                elif value in ('}', ')', ']'): depth -= 1
                if depth == 0: break

        records.append({"monster": monster_name, "configType": fields.get("configType", "Default"),
                        "isElite": first == "Elite", "mode": mode,
                        "line": text.count("\n", 0, tokens[left][1]) + 1,
                        "wave_hard_level_override": fields.get("hard_level"),
                        "explicit_attributes": sorted(set(attributes))})
    return records


def build_act101(apk19, apk24):
    """Extend the frozen nine-file closure with five real Normal stage entries."""
    if file_sha(apk19) != ORIGINAL19_SHA or sha(native.E) != NATIVE19_SHA:
        raise ValueError("Original baseline identity changed")
    base_manifest_path = DEFAULT_OUTPUT / "manifest.json"
    if file_sha(base_manifest_path) != "7504b1b3f9512b26a9ecd750867f386998e970d514c153253e21002515aaa7bc":
        raise ValueError("Frozen first-stage Lua manifest changed")
    base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
    dependencies = []
    for record in base_manifest["files"]:
        if file_sha(DEFAULT_OUTPUT / record["path"]) != record["output_sha256"]:
            raise ValueError("Frozen first-stage Lua file changed")
        dependencies.append({"path": record["path"], "bytes": record["bytes"],
                             "output_sha256": record["output_sha256"]})
    canonical = ROOT / ".local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset"
    stage_raw = (canonical / "stagedata_main").read_bytes()
    if sha(stage_raw) != "e535124cbbb34f2f47a64cbd18453dc018cf7b8a724f9a8f8f8e8f266ed6b743":
        raise ValueError("Actual stage metadata changed")
    stages = [row for row in json.loads(stage_raw) if 10101 <= row["levelId"] <= 10106]
    if [(r["levelId"], r["actId"], r["hardLevel"], r["UseDynamicHardLv"]) for r in stages] != [
            (10101, 101, 1, 0), (10102, 101, 1, 0), (10103, 101, 2, 0),
            (10104, 101, 2, 0), (10105, 101, 2, 0), (10106, 102, 3, 0)]:
        raise ValueError("Only Act101 and Act102 first entry are in this profile")
    monster_rows = json.loads((canonical / "monsterconfigdata").read_bytes())
    monster_names = {row["monsterName"] for row in monster_rows}
    old = {r["path"]: r for r in resources.resource_map(apk19)}
    later = {r["path"]: r for r in resources.resource_map(apk24)}
    signatures, targets, records, stage_evidence = method_signatures(), {}, [], []
    with zipfile.ZipFile(apk19) as original, zipfile.ZipFile(apk24) as reference:
        for stage in stages:
            path = stage["luaFile"].lower()
            if path == ENTRY:
                data = (DEFAULT_OUTPUT / path).read_bytes()
            else:
                if path not in ACT101_SOURCES or path not in later:
                    raise ValueError("Actual stage script absent or outside audited scope")
                version, archive, mapping = ("1.9.0", original, old) if path in old else ("2.4.0", reference, later)
                data, record = text_record(archive, mapping[path], version)
                if version == "2.4.0" and sha(data) != ACT101_SOURCES[path]:
                    raise ValueError("Actual later stage Lua bytes changed")
                text = data.decode("utf-8-sig")
                deps = requires(text)
                if [r["path"] for r in deps] != ["lua/base/leveldesignnormal.lua"]:
                    raise ValueError("Stage Lua requires expanded beyond frozen closure")
                direct_calls = calls(text)
                for call in direct_calls:
                    candidates = signatures.get(call["method"], [])
                    if call["static_argument_count"] is None or not any(s["minimum_args"] <= call["static_argument_count"] <= s["maximum_args"] for s in candidates):
                        raise ValueError("New entry has an unproven direct native call")
                record.update(path=path, bytes=len(data), output_sha256=sha(data),
                              original19_resource_present=path in old, requires=deps,
                              source_bytes_unchanged=True, adaptations=[], native_calls=direct_calls,
                              reference_path="reference/" + path, historical19_equivalence=False)
                records.append(record)
                targets[path] = data
                targets["reference/" + path] = data
            text = data.decode("utf-8-sig")
            waves = normal_monster_waves(text, monster_names)
            basic_refs = []
            for name, variant in sorted({(r["monster"], r["configType"]) for r in waves}):
                matches = [r for r in monster_rows if r["monsterName"] == name and r["typeName"] == variant]
                if len(matches) != 1:
                    raise ValueError("Native monster basic row is absent or duplicated")
                basic_refs.append(matches[0])
            stage_evidence.append({"levelId": stage["levelId"], "actId": stage["actId"],
                "hardLevel": stage["hardLevel"], "UseDynamicHardLv": 0,
                "preLevelID": stage["preLevelID"], "lua": path,
                "stage_names": re.findall(r'\bstage\s*=\s*"([^"]+)"', text),
                "weather_names": re.findall(r'\bdefault_weather\s*=\s*"([^"]+)"', text),
                "normal_monster_waves": waves, "native_basic_monster_rows": basic_refs})
        scene_data = original.read("assets/bin/Data/globalgamemanagers")
        parsed = resources.serialized(scene_data)
        build = next(o for o in parsed["objects"].values() if o["class"] == 141)
        cursor = resources.Reader(scene_data, build["offset"])
        names = [cursor.string() for _ in range(cursor.read("i"))]
        scenes = []
        wanted = {"Spaceship_Outside01", "Spaceship_Outside02", "Spaceship_Outside04", "St_Freyja_01"}
        for index, name in enumerate(names):
            if name.rsplit("/", 1)[-1].removesuffix(".unity") in wanted:
                raw = original.read("assets/bin/Data/level" + str(index))
                scenes.append({"scene": name, "build_index": index, "bytes": len(raw), "sha256": sha(raw), "role": "original retained"})
        if len(scenes) != 4:
            raise ValueError("Original actual navigation scenes are unavailable")
        original_paths = ["stage/data/stage_spaceship", "stage/stage_spaceship_outside/env_outside_01",
            "stage/stage_spaceship_outside/env_outside_02", "stage/stage_spaceship_outside/env_outside_04",
            "stage/stage_spaceship_outside/perpstage_spaceship_outside", "stage/data/stage_st_freyja",
            "stage/stage_st_freyja/env/env_s02_01", "stage/stage_st_freyja/perpstage_s02_01",
            "weather/stagerenderingdata/style_01/style01_aircraft_outside", "weather/stagerenderingdata/style_01/style01_day"]
        retained = []
        for path in original_paths:
            if path not in old:
                raise ValueError("Original scene/weather resource unavailable: " + path)
            obj, raw = resources.object_bytes(original, old[path])
            retained.append({"resource": old[path], "class": obj["class"], "bytes": len(raw), "sha256": sha(raw), "role": "original retained"})
    manifest = {"format": "server19-act101-normal-and-act102-entry-lua-v1", "stage_ids": list(range(10101, 10107)),
        "mode": "Normal", "source19": {"sha256": ORIGINAL19_SHA}, "source24": {"sha256": file_sha(apk24)},
        "base_first_stage_manifest_sha256": file_sha(base_manifest_path), "required_existing_files": dependencies,
        "files": records, "deployment_files": [r["path"] for r in records if not r["original19_resource_present"]],
        "stagedata_main_sha256": sha(stage_raw), "stage_evidence": stage_evidence,
        "original_scenes": scenes, "original_resources": retained,
        "limits": ["Only Normal10101–10105 and Act102 entry10106; Hard/Hell and10107 onward are outside this profile",
            "New entry Lua bytes remain real source bytes; accepted five base ABI adaptations are reused unchanged",
            "Later2.4 scripts are explicit compatibility, not recovered historical1.9 scripts",
            "Monster/Ability and NPC hard-level1/2/3 need their separate audited profiles",
            "Original scenes/resources retained; static identity does not replace actual entry verification",
            "No device/service/library/account/progress/stamina operation"]}
    targets["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return targets, manifest


def run_act101(command, apk19, apk24, output):
    targets, manifest = build_act101(apk19, apk24)
    for relative, value in targets.items():
        target = output / relative
        if command == "audit":
            if target.read_bytes() != value:
                raise ValueError("Act101 source/output/evidence changed")
        elif target.exists() and (not target.is_file() or target.read_bytes() != value):
            raise ValueError("Preserve changed Act101 output")
    if command == "prepare":
        for relative, value in targets.items():
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(value)
    return {"status": "act101_static_resources_verified" if command == "audit" else "act101_real_entries_exported",
            "output": str(output.resolve()), "deployment_files": manifest["deployment_files"],
            "files": len(manifest["files"]), "manifest_sha256": sha(targets["manifest.json"]),
            "runtime_compatibility": "unaccepted"}


def build_stage7(apk19, apk24, baseline_plan):
    """Prepare only three explicit overlays, retaining the actual827-file base.

    This does not regenerate older builders or silently choose a generic1-7
    script instead of the actual Normal metadata path. Human play is separate.
    """
    import server19_stage_abilities as abilities
    import server19_stage_monsters as monsters
    plan_raw = Path(baseline_plan).read_bytes()
    plan = json.loads(plan_raw)
    if file_sha(apk19) != ORIGINAL19_SHA or file_sha(apk24) != monsters.SOURCE24_SHA or sha(native.E) != NATIVE19_SHA:
        raise ValueError("Pinned stage7 source identity changed")
    if len(plan["resources"]) != 827:
        raise ValueError("Expected latest827-file deployment baseline")
    existing, preservation = {}, []
    for row in plan["resources"]:
        relative = row["device_relative_path"]
        if relative in existing:
            raise ValueError("Duplicate baseline device resource")
        raw = Path(row["local_absolute_path"]).read_bytes()
        if sha(raw) != row["sha256"] or len(raw) != row["bytes"]:
            raise ValueError("Baseline input changed: " + relative)
        existing[relative] = raw
        preservation.append({"path": relative, "local_source": row["local_absolute_path"],
            "before_sha256": sha(raw), "before_bytes": len(raw), "after_sha256": sha(raw),
            "after_bytes": len(raw), "operation": "retain"})
    if STAGE7_ENTRY in existing:
        raise ValueError("Stage7 entry already exists; do not overwrite an unknown increment")
    # Include every prior nine-file closure and six-stage entry, not only the
    # one shared require, so this overlay cannot silently drop prior content.
    for folder in (DEFAULT_OUTPUT, ACT101_OUTPUT):
        manifest = json.loads((folder / "manifest.json").read_bytes())
        for row in manifest["files"]:
            path = row["path"]
            if path not in existing or sha(existing[path]) != row["output_sha256"]:
                raise ValueError("Preserve prior Lua closure: " + path)
    required = {"_baked/bakedabilitydata": abilities.STAGE7_PREVIOUS_SHA,
        "_baked/bakedmonsterdata": "6608058b07fc8229daab5355b1ea59a841ee5f802d13aa81d3d889f01fa38b51",
        "_baked/bakedpropdata": "a523418d83cb738e58757b98eca17ff0406441ddc975de35671cdf07d5437fb6",
        "_baked/stringmap.txt": "297215d8fc2f2596abff1a7bf1a46073fa73541cfb85e2d3a5f0c7bf772714b1",
        "_exceloutputasset/npclevellogic": "feaa7d9a17b6cab682df194beaccfd237eedabe62b7e9038474fe8bb8b41c3cd"}
    if any(path not in existing or sha(existing[path]) != expected for path, expected in required.items()):
        raise ValueError("Preserve exact accepted Monster/NPC/Prop/56Ability/StringMap baseline")
    stages = json.loads(existing["_exceloutputasset/stagedata_main"])
    actual = [row for row in stages if row["levelId"] == 10107]
    if len(actual) != 1:
        raise ValueError("Actual10107 metadata absent or duplicate")
    stage = actual[0]
    if (stage["luaFile"].lower(), stage["hardLevel"], stage["UseDynamicHardLv"], stage["preLevelID"]) != (STAGE7_ENTRY, 3, 0, [10106]):
        raise ValueError("Actual1-7 path/real difficulty/prerequisite changed")
    hard_rows = [row for row in json.loads(existing["_exceloutputasset/npclevellogic"]) if row["HardLevel"] == 3]
    if len(hard_rows) != 1:
        raise ValueError("Existing real NPC level3 is required")
    old = {row["path"]: row for row in resources.resource_map(apk19)}
    later = {row["path"]: row for row in resources.resource_map(apk24)}
    if STAGE7_ENTRY in old:
        raise ValueError("Original Lua is present; preserve it instead of later overlay")
    retained_originals, scenes = [], []
    with zipfile.ZipFile(apk24) as reference, zipfile.ZipFile(apk19) as original:
        lua, source = text_record(reference, later[STAGE7_ENTRY], "2.4.0")
        if sha(lua) != STAGE7_SOURCE_SHA:
            raise ValueError("Only the actual frozen Normal1-7 source accepted")
        text = lua.decode("utf-8-sig")
        deps, direct = requires(text), calls(text)
        if [row["path"] for row in deps] != ["lua/base/leveldesignnormal.lua"]:
            raise ValueError("Stage7 require scope expanded")
        signatures = method_signatures()
        for row in direct:
            count, options = row["static_argument_count"], signatures.get(row["method"], [])
            if count is None or not any(o["minimum_args"] <= count <= o["maximum_args"] for o in options):
                raise ValueError("Unproven1-7 direct original ABI: " + row["method"])
            row["native19_signatures"] = options
        monster_rows = json.loads(existing["_exceloutputasset/monsterconfigdata"])
        waves = normal_monster_waves(text, {row["monsterName"] for row in monster_rows})
        if {(row["monster"], row["configType"], row["isElite"]) for row in waves} != {("DeadWalker", "Default", True), ("UlyssesFast", "Default", True)}:
            raise ValueError("Actual Normal1-7 monster scope changed")
        basic = [row for row in monster_rows if row["monsterName"] in ("DeadWalker", "UlyssesFast") and row["typeName"] == "Default"]
        if len(basic) != 2:
            raise ValueError("Previously audited stage7 monster metadata missing")
        for name in abilities.STAGE7_SELECTED.values():
            if '"' + name + '"' not in text and name + " =" not in text:
                raise ValueError("Actual tutorial ability reference disappeared")
        scene_data = original.read("assets/bin/Data/globalgamemanagers")
        parsed = resources.serialized(scene_data)
        build = next(row for row in parsed["objects"].values() if row["class"] == 141)
        cursor = resources.Reader(scene_data, build["offset"])
        names = [cursor.string() for _ in range(cursor.read("i"))]
        found = [(i, name) for i, name in enumerate(names) if name.endswith("/St_Freyja_11.unity")]
        if len(found) != 1:
            raise ValueError("Original St_Freyja_11 navigation scene missing")
        index, name = found[0]
        raw = original.read("assets/bin/Data/level" + str(index))
        points = ("Exit3", "Wall02", "Wall01", "Wall04", "InnerWall02", "InnerWall03")
        scenes.append({"scene": name, "build_index": index, "sha256": sha(raw), "bytes": len(raw)})
        for path in ("stage/data/stage_st_freyja", "stage/stage_st_freyja/env/env_s02_11",
                "stage/stage_st_freyja/perpstage_s02_01", "weather/stagerenderingdata/style_01/style01_day",
                "effect/data/avatar/effectpattern_kiana", "ui/menus/dialog/newbie/newbiedialog"):
            if path not in old:
                raise ValueError("Required original stage7 resource absent: " + path)
            obj, raw = resources.object_bytes(original, old[path])
            if path == "effect/data/avatar/effectpattern_kiana" and b"Kiana_WitchTime_Duration" not in raw:
                raise ValueError("Original tutorial evade-effect pattern missing")
            proof = {"path": path, "resource": old[path], "class": obj["class"], "sha256": sha(raw), "bytes": len(raw), "operation": "original_retained"}
            if path == "stage/stage_st_freyja/env/env_s02_11":
                # Waypoints/barriers are children of the environment prefab,
                # not named objects inside the separate navigation scene.
                full = original.read("assets/bin/Data/" + old[path]["file"])
                parsed = resources.serialized(full)
                names = []
                for child in parsed["objects"].values():
                    if child["class"] != 1:
                        continue
                    cursor = resources.Reader(full, child["offset"])
                    count = cursor.read("i")
                    for _ in range(count):
                        cursor.read("iiq")
                    cursor.read("I")
                    names.append(cursor.string())
                if any(point not in names for point in points):
                    raise ValueError("Original environment named GameObjects missing")
                proof.update(serialized_file_sha256=sha(full), serialized_file_bytes=len(full),
                    actual_named_gameobjects=list(points))
            retained_originals.append(proof)
    tutorial_rows = json.loads(existing["_exceloutputasset/tutorialstepdata"])
    tutorials = [row for row in tutorial_rows if row["id"] in range(85001, 85006)]
    if len(tutorials) != 5 or any(row["nextStepID"] or row["FinishOnStart"] or row["FinishOnEnd"] for row in tutorials):
        raise ValueError("Actual tutorial metadata dependency changed")
    # Keep existing plot/dialog data; the original AllowEnterStoryMode predicate
    # decides whether the source's StoryMode20005 actually plays.
    plots = [row for row in json.loads(existing["_exceloutputasset/plotdata"]) if row["plotID"] == 20005]
    if len(plots) != 1:
        raise ValueError("Referenced StoryMode20005 data missing")
    ability_source, ability, ability_manifest = abilities.build_stage7(apk19, apk24)
    next_monster = (monsters.STAGE2_OUTPUT / monsters.PATH).read_bytes()
    if sha(next_monster) != "f4323d0e849200b518ee88cc9bbed53c46d1f8bdf87ec8bcbbef3e929a11adc7":
        raise ValueError("Accepted DG020 ATK03 repair artifact changed")

    def roots(raw):
        h, entries, overrides, packed = monsters.unpack_container(raw)
        refs = {off: (key, None) for key, off in entries}
        refs.update({off: (key, variant) for key, variant, off in overrides})
        if len(refs) != len(entries) + len(overrides):
            raise ValueError("Monster aliases need independent proof")
        ends = dict(zip(sorted(refs), sorted(refs)[1:] + [len(packed)]))
        return h, [key for key, _ in entries], [(key, variant) for key, variant, _ in overrides], {identity: packed[off:ends[off]] for off, identity in refs.items()}

    before_roots, after_roots = roots(existing[monsters.PATH]), roots(next_monster)
    if before_roots[:3] != after_roots[:3] or [key for key, raw in before_roots[3].items() if raw != after_roots[3][key]] != [(8522, None)]:
        raise ValueError("Known Monster repair must preserve all other registry roots")
    if len(next_monster) != len(existing[monsters.PATH]) - 1:
        raise ValueError("Only accepted one-byte Monster repair is allowed")
    targets = {STAGE7_ENTRY: lua, abilities.PATH: ability, monsters.PATH: next_monster,
        "reference/" + STAGE7_ENTRY: lua,
        "reference/" + abilities.PATH: ability_source,
        "reference/before/" + abilities.PATH: existing[abilities.PATH],
        "reference/before/" + monsters.PATH: existing[monsters.PATH],
        "ability-manifest.json": (json.dumps(ability_manifest, ensure_ascii=False, indent=2) + "\n").encode()}
    deployment_files = [STAGE7_ENTRY, abilities.PATH, monsters.PATH]
    for row in preservation:
        if row["path"] in deployment_files:
            raw = targets[row["path"]]
            row.update(after_sha256=sha(raw), after_bytes=len(raw), operation="replace_explicit_delta")
    preservation.append({"path": STAGE7_ENTRY, "before_sha256": None, "before_bytes": None,
        "after_sha256": sha(lua), "after_bytes": len(lua), "operation": "add_exact_actual_normal_source"})
    manifest = {"format": "server19-normal10107-resource-closure-v1", "stage_id": 10107, "mode": "Normal",
        "source19": {"sha256": ORIGINAL19_SHA}, "source24": {"sha256": monsters.SOURCE24_SHA},
        "baseline_plan": {"path": str(Path(baseline_plan).resolve()), "sha256": sha(plan_raw), "files": 827},
        "stage_metadata": stage, "source_lua": {**source, "path": STAGE7_ENTRY, "output_sha256": sha(lua),
            "source_bytes_unchanged": True, "adaptations": [], "requires": deps, "native_calls": direct},
        "deployment_files": deployment_files, "files": [{"path": p, "bytes": len(targets[p]), "output_sha256": sha(targets[p]),
            "required_existing_sha256": sha(existing[p]) if p in existing else None} for p in deployment_files],
        "normal_monster_waves": waves, "retained_monster_basic_rows": basic, "retained_npc_hard_level": hard_rows,
        "original_scenes": scenes, "original_resources": retained_originals, "retained_tutorial_rows": tutorials,
        "retained_plot20005": plots[0], "ability_increment": {"previous56_roots_byte_identical": True,
            "new_roots": list(abilities.STAGE7_SELECTED.values()), "selected_roots": 58,
            "manifest_path": "ability-manifest.json", "manifest_sha256": sha(targets["ability-manifest.json"])},
        "known_monster_repair": {"source": str((monsters.STAGE2_OUTPUT / monsters.PATH).resolve()),
            "source_manifest_sha256": file_sha(monsters.STAGE2_OUTPUT / "manifest.json"),
            "changed_identity": [8522, None], "all_other315_roots_byte_identical": True,
            "policy": "Previously audited DG020 ATK03 nil FollowOwnerTimeScale deletion; separate from1-7 source increment"},
        "preservation": preservation, "before_file_count": 827, "after_file_count": 828,
        "retained_existing_file_count": 825,
        "limits": ["Static source/ABI/resource checks only; human entry/tutorial/battle/settlement pending",
            "2.4 Normal1-7 source compatibility; historical1.9 script/content equivalence not established",
            "Exact script hpRatio5/tutorial/StoryMode branches retained; no source behavior replacements",
            "Existing plot20005 is bound to10108; original AllowEnterStoryMode predicate retained, branch play unverified",
            "Retain all prior Lua, NPC1–3, Props, all56 prior abilities and expanded StringMap; never deploy old builder output",
            "No device, server, native library, account, guide completion, stamina or progress operation"]}
    targets["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    return targets, manifest


def run_stage7(command, apk19, apk24, output, baseline_plan):
    if baseline_plan is None:
        raise ValueError("Stage7 requires an explicit current --baseline-plan")
    targets, manifest = build_stage7(apk19, apk24, baseline_plan)
    for relative, data in targets.items():
        path = output / relative
        if command == "audit":
            if path.read_bytes() != data:
                raise ValueError("Stage7 output changed: " + relative)
        elif path.exists() and path.read_bytes() != data:
            raise ValueError("Preserve existing changed stage7 output: " + relative)
    if command == "prepare":
        for relative, data in targets.items():
            path = output / relative; path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(data)
    return {"status": "stage7_source_and_static_closure_verified", "output": str(output.resolve()),
        "deployment_files": manifest["files"], "retained_existing_files": 825,
        "manifest_sha256": sha(targets["manifest.json"]), "runtime_compatibility": "human_test_pending"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "audit"))
    parser.add_argument("--apk19", type=Path, default=resources.DEFAULT19)
    parser.add_argument("--apk24", type=Path, default=resources.DEFAULT24)
    parser.add_argument("--profile", choices=("firststage", "act101_entry", "stage10107"), default="firststage")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-plan", type=Path)
    args = parser.parse_args()
    if args.profile == "stage10107":
        print(json.dumps(run_stage7(args.command, args.apk19, args.apk24, args.output or STAGE7_OUTPUT, args.baseline_plan), ensure_ascii=False, indent=2))
        return
    if args.profile == "act101_entry":
        print(json.dumps(run_act101(args.command, args.apk19, args.apk24, args.output or ACT101_OUTPUT), ensure_ascii=False, indent=2))
        return
    args.output = args.output or DEFAULT_OUTPUT
    result = (prepare(args.apk19, args.apk24, args.output) if args.command == "prepare"
              else audit(args.output, args.apk19, args.apk24))
    print(json.dumps(result if args.command == "audit" else {
        "status": "explicit_abi_adaptation_exported", "files": result["closure_count"],
        "manifest": str(args.output / "manifest.json"),
        "findings": dict(Counter(row["status"] for row in result["static_compatibility_findings"])),
        "runtime_compatibility": "unaccepted"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
