"""Read ability dependencies from Lua data instructions, not only API calls."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import re
import json
import zipfile
from pathlib import Path
import server19_stage_resources as lua


def registered_references(text, names):
    """Conservative literal/key inventory for skill tables and config forwarders.

    Names must already exist as ability roots. Lexer excludes comments; table
    keys, dictionary keys and forwarded string values are retained as evidence.
    This does not resolve arbitrary concatenated or server-provided names.
    """
    found=[]
    for token in lua.lua_tokens(text):
        name=token[0][1:-1] if token[3]=='string' else token[0]
        if name in names:
            found.append(dict(ability=name,source='registered_literal_or_table_key',
                              line=text.count('\n',0,token[1])+1))
    return list({(r['ability'],r['line']):r for r in found}.values())


def references(text, *, unresolved=None):
    tokens = lua.lua_tokens(text)
    result = []

    def add(name, source, offset):
        if not re.fullmatch(r'[A-Za-z0-9_]+', name):
            raise ValueError('Nonliteral ability identity requires separate resolution')
        result.append({'ability':name, 'source':source,
                       'line':text.count('\n',0,offset)+1})

    for i, token in enumerate(tokens):
        if token[0] == '{' and i+1 < len(tokens) and tokens[i+1][3] == 'string':
            command = tokens[i+1][0][1:-1]
            if command in ('add_avatar_ability','add_ability'):
                if i+4 >= len(tokens) or tokens[i+2][0] != ',' or tokens[i+3][3] != 'string' or tokens[i+4][0] not in (',','}'):
                    line = text.count('\n',0,token[1])+1
                    if unresolved is None:
                        raise ValueError('Dynamic ability data instruction at line'+str(line))
                    unresolved.append({'command':command,'line':line,'expression':tokens[i+3][0]})
                    continue
                add(tokens[i+3][0][1:-1],command,token[1])
            elif command == 'WitchTime':
                add('Level_WitchTime',command,token[1])
        if token[0] == 'triggerAbility' and i+1 < len(tokens) and tokens[i+1][0] == '=':
            if i+2 >= len(tokens) or tokens[i+2][0] != '{':
                raise ValueError('Dynamic monster triggerAbility list')
            j = i+3
            while j < len(tokens) and tokens[j][0] != '}':
                if tokens[j][0] == ',': j += 1; continue
                if tokens[j][3] != 'string' or tokens[j+1][0] not in (',','}'):
                    raise ValueError('Dynamic monster triggerAbility element')
                add(tokens[j][0][1:-1],'triggerAbility',tokens[j][1]); j += 1
            if j == len(tokens): raise ValueError('Unclosed triggerAbility list')
    for call in lua.calls(text):
        if call['method'] not in ('TriggerAbilityOnAvatar', 'TriggerAbilityOnMonster',
                'TriggerLevelAbilityOnTarget', 'AddNewAbility', 'AddNewAbilityToAvatar'): continue
        args = call['arguments']
        if len(args) < 2: raise ValueError('Ability native call lacks its name argument')
        literal = args[1].strip()
        if re.fullmatch(r'''["'][A-Za-z0-9_]+["']''',literal):
            add(literal[1:-1],call['method'],0)
        # Variable-name handlers forward the data instructions parsed above;
        # this function does not claim arbitrary expressions are resolved.
    return list({(r['ability'],r['source'],r['line']):r for r in result}.values())


def prepare(ability_file, stringmap_file, delivery_plan, output):
    import server19_avatar_battle_resources as batch
    import server19_resources as resources
    import server19_stage_monsters as monster
    from server19_story_shield_bridge import ShieldClosure
    ability_file, stringmap_file, delivery_plan, output = map(Path,
        (ability_file, stringmap_file, delivery_plan, output))
    output.mkdir(exist_ok=False)
    strings = stringmap_file.read_text(encoding='utf8').split('\x1f')
    before_strings = strings.copy()
    plan = json.loads(delivery_plan.read_bytes())
    rows, module_forwarders, stage_files, lua_files = [], [], 0, 0
    selected = set()
    for rec in plan['files']:
        if not rec['path'].endswith('.lua'): continue
        lua_files += 1
        text = Path(rec['local_absolute_path']).read_text(encoding='utf-8-sig')
        is_stage = rec['path'].startswith('lua/levels/')
        unresolved = []
        refs = references(text, unresolved=None if is_stage else unresolved)
        if is_stage:
            stage_files += 1
            selected.update((strings.index(r['ability']),None) for r in refs)
        if refs: rows.append({'path':rec['path'],'is_stage':is_stage,'references':refs})
        if unresolved: module_forwarders.append({'path':rec['path'],'unresolved':unresolved})
    with zipfile.ZipFile(resources.DEFAULT24) as source:
        closure = ShieldClosure(source, strings,
            {r['path']:r for r in resources.resource_map(resources.DEFAULT19)}, output)
        closure.schema.ui_custom_buff_ids = (1001,6005,6006)
        closure.before = ability_file.read_bytes()
        closure.data, closure.spans = batch.packed(closure.before)[3::2]
        for identity in sorted(selected): closure.project(identity)
        if closure.errors: raise ValueError('Stage data ability closure blocked: '+str(closure.errors))
        if strings != before_strings: raise ValueError('Changed StringMap requires another delivery')
        h, entries, overrides, data, refs, spans = batch.packed(closure.before)
        packed, offsets = bytearray(), {}
        for _, identity in sorted(refs.items()):
            offsets[identity] = len(packed)
            left, right = spans[identity]
            packed.extend(closure.changes.get(identity, data[left:right]))
        result = monster.pack_container(h, [(k,offsets[k,None]) for k,_ in entries],
            [(k,v,offsets[k,v]) for k,v,_ in overrides], bytes(packed))
        (output/'bakedabilitydata').write_bytes(result)
        report = {'status':'PASS_stage_literal_closure_human_pending',
            'lua_files_scanned':lua_files,'stage_files_scanned':stage_files,
            'selected':len(selected),'changed':len(closure.changes),
            'references':rows,'unresolved_module_forwarders':module_forwarders,
            'module_dynamic_reachability':'Not established by this literal scanner; retained as separate evidence',
            'records':list(closure.records.values()),'errors':[],
            'before_sha256':monster.sha(closure.before),'after_sha256':monster.sha(result),
            'human_acceptance':'pending'}
        (output/'scan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    for name in ('ability_file','stringmap_file','delivery_plan','output'): parser.add_argument(name)
    args = parser.parse_args()
    report = prepare(args.ability_file,args.stringmap_file,args.delivery_plan,args.output)
    print(json.dumps({k:report[k] for k in ('status','lua_files_scanned','stage_files_scanned','selected','changed','errors')}))
