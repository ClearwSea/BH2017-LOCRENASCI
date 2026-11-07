"""Prepare a Sony601 overlay from current resources; no device/account writes."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import hashlib
import json
import shutil
import struct
import zipfile
import server19_fuka601_abilities as fuka
import server19_avatar_battle_resources as batch
import server19_equipment_battle_closure as closure
import server19_metadata_export as meta
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
WORK = ROOT / '.local-baseline/server19-dev/fuka601-recovery-20261015'
OUT = WORK / 'ready-v5'
BASE = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
EXPECTED_BASE = {
    'avatardata': 'a440d1e62daa77457312b419c57261624f3f568526295dee4947032b51130e7e',
    'avatarskilldata': 'b461ecfd851450c586d065aac6a38cc659d07a7767c7b1304f4a4c818dcddea3',
    'avatarsubskilldata': '45a03e50b23436eef4b44e3dd8d92eefd42a7fddeaf988dcdf8291e41b48286a',
    'avatarstardata': 'bcd27e0bcbe1f2ffd616cf9025074a2481958e4306ccfba3c43c6a4aa4405ceb',
    'weapondata': '82db882548dbed50a4d024dab08061cb8a7c48d265b6942f9d31467629e25c34',
    'avatarfragmentdata': 'b506d75f6fa52b787a648c83cd0bb546e306315ffca7d49b9f99af3521810494',
    'classdata': 'b1380bf5a9638f90e9f8ffeae01b91f5f88e3a5b30bac641774cafda03dce28a',
    'avatarcarddata': 'd5ca2432f15acab92c933bf78e6691f2bc40b3f048f7999b738a1af8c4d6c406',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare():
    if OUT.exists():
        raise ValueError('Use a fresh reviewed candidate output')
    OUT.mkdir(parents=True)
    audit = json.loads((WORK / 'tables-audit.json').read_text(encoding='utf-8'))
    extra = {}
    paths = {row['path']: row for row in resources.resource_map(resources.DEFAULT24)}
    with zipfile.ZipFile(resources.DEFAULT24) as archive:
        objects = meta.PackageObjects(archive); decoder = meta.SourceTypedDecoder(archive)
        known = meta.asset_types()
        for name, key, identity in (('classdata', 'classID', 6), ('avatarcarddata', 'ID', 60601)):
            record = paths['_exceloutputasset/' + name]
            _, raw = objects.object(record)
            spec = known[objects.script_type(record, raw)]
            rows = [row for row in decoder.rows(raw, spec['row_type']) if row[key] == identity]
            if len(rows) != 1:
                raise ValueError('Required original construction dependency missing: ' + name)
            fields = meta.serialized_fields(spec['row_type_index'])
            if any(field not in rows[0] for field, _ in fields):
                raise ValueError('Missing original construction field: ' + name)
            extra[name] = [{field: meta.project_typed(rows[0][field], pointer) for field, pointer in fields}]
            audit['tables'][name] = {'key': key, 'keys': [identity]}
    tables = {}
    for name, expected in EXPECTED_BASE.items():
        source = BASE / name
        if name == 'avatarfragmentdata':
            source = ROOT / '.local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset' / name
        raw = source.read_bytes()
        if sha(raw) != expected:
            raise ValueError('Current source table changed: ' + name)
        before = json.loads(raw)
        current = extra[name] if name in extra else json.loads((WORK / '_exceloutputasset' / name).read_bytes())
        key = audit['tables'][name]['key']
        selected = set(audit['tables'][name]['keys'])
        additions = [row for row in current if row[key] in selected]
        by_key = {row[key]: row for row in before}
        for row in additions:
            if row[key] in by_key and by_key[row[key]] != row:
                raise ValueError('Existing row conflict: ' + name)
        merged = before + [row for row in additions if row[key] not in by_key]
        char_receipt = None
        if name == 'avatarskilldata':
            fields = ('paramLogic_1', 'paramLogic_2', 'paramLogic_3')
            original_chars = (WORK / 'source/avatarskilldata.chars').read_bytes()
            if len(original_chars) != len(before) * 6:
                raise ValueError('Actual Sony character sidecar row count differs')
            added = merged[len(before):]
            codes = []
            for index, field in enumerate(fields):
                block = original_chars[index * len(before) * 2:(index + 1) * len(before) * 2]
                codes.extend(struct.unpack('<' + 'H' * len(before), block))
                for row in added:
                    value = row[field]
                    if not isinstance(value, str) or len(value.encode('utf-16-le')) != 2:
                        raise ValueError('New source Char is not one UTF16 code unit')
                    codes.append(struct.unpack('<H', value.encode('utf-16-le'))[0])
            for row in added:
                for field in fields:
                    del row[field]
            sidecar = b''.join(struct.pack('<H', value) for value in codes)
            target = OUT / '_exceloutputasset/avatarskilldata.chars'
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(sidecar)
            char_receipt = {'file': str(target.relative_to(OUT)), 'sha256': sha(sidecar),
                            'rows': len(merged), 'bytes': len(sidecar), 'fields': list(fields),
                            'original_field_blocks_preserved': True}
        output = meta.native_json(merged)[0].encode('utf-8')
        target = OUT / '_exceloutputasset' / name
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(output)
        tables[name] = {'file': str(target.relative_to(OUT)), 'sha256': sha(output),
                        'base_sha256': expected, 'base_path': str(source),
                        'preserved_rows': len(before), 'added_rows': len(merged) - len(before),
                        'selected_keys': sorted(selected)}
        if char_receipt:
            tables[name]['char_sidecar'] = char_receipt
    text_source = ROOT / '.local-baseline/server19-dev/sony-human-fixes-v1/textmap'
    text = json.loads(text_source.read_bytes())
    existing = {row['ID']: row for row in text}
    source = json.loads((WORK / '_exceloutputasset/textmap').read_bytes())
    merged = text + [row for row in source if row['ID'] not in existing]
    present = {row['ID'] for row in merged}
    text_keys = {str(value) for rows in extra.values() for row in rows for key, value in row.items()
                 if key in ('firstName', 'lastName', 'enFirstName', 'enLastName', 'displayTitle', 'displayDescription')}
    with zipfile.ZipFile(resources.DEFAULT24) as archive:
        objects = meta.PackageObjects(archive)
        _, raw = objects.object(paths['_exceloutputasset/textmap'])
        source_texts, _ = meta.text_map_sources(objects, list(paths.values()), raw)
        lookup = {row['ID']: row['Text'] for row in source_texts if row['ID'] in text_keys}
        for key in sorted(text_keys - present):
            if key not in lookup:
                raise ValueError('Missing construction text: ' + key)
            merged.append({'ID': key, 'Text': lookup[key]})
    target = OUT / '_exceloutputasset/textmap'
    target.write_text(meta.native_json(merged)[0], encoding='utf-8')
    tables['textmap'] = {'file': str(target.relative_to(OUT)), 'sha256': sha(target.read_bytes()),
                         'base_sha256': sha(text_source.read_bytes()), 'base_path': str(text_source),
                         'preserved_rows': len(text), 'added_rows': len(merged) - len(text)}
    abilities = WORK / 'adapted-abilities-v2'
    receipt = json.loads((abilities / 'manifest.json').read_text(encoding='utf-8'))
    if receipt['unsupported_roots'] or len(receipt['research_root_candidates']) != 29:
        raise ValueError('Actual601 ability closure is not complete')
    blockers = receipt['roster'][0]['blockers']
    if len(blockers) != 3 or {row.get('effect_group') for row in blockers if 'effect_group' in row} != {'Fuka_NL_Effects', 'Fuka_Weapon_Effects'}:
        raise ValueError('Unexpected resource blocker requires review')
    source_strings = batch.STRINGS.read_text(encoding='utf-8').split('\x1f')
    actual_strings = (WORK / 'source/stringmap.txt').read_text(encoding='utf-8').split('\x1f')
    if actual_strings[:len(source_strings)] != source_strings:
        raise ValueError('Actual Sony StringMap is not the preserved index prefix')
    changes = {}
    for row in receipt['research_root_candidates']:
        raw = (abilities / row['file']).read_bytes()
        if sha(raw) != row['sha256']:
            raise ValueError('Checked root candidate changed')
        changes[row['key'], row['variant']] = raw
    actual = (WORK / 'source/bakedabilitydata').read_bytes()
    merged = closure.assemble(actual, changes)
    baked_dir = OUT / '_baked'; baked_dir.mkdir()
    (baked_dir / 'bakedabilitydata').write_bytes(merged)
    original_meta = (WORK / 'source/metaconfig.txt').read_text(encoding='utf-8')
    groups = original_meta.split('\x1e')
    if len(groups) != 13:
        raise ValueError('Original MetaConfig group count differs')
    paths = groups[0].split('\x1f')
    additions = ('Effect/Data/Avatar/EffectPattern_Fuka_NL', 'Effect/Data/Weapon/EffectPattern_Fuka_Weapon')
    groups[0] = '\x1f'.join(paths + [path for path in additions if path not in paths])
    (OUT / 'metaconfig.txt').write_text('\x1e'.join(groups), encoding='utf-8')
    bundle_source = WORK / 'asset-bundle-v1/fuka601-models.unity3d'
    shutil.copyfile(bundle_source, OUT / bundle_source.name)
    shutil.copyfile(WORK / 'native-v3/libil2cpp.so', OUT / 'libil2cpp.so')
    result = {'schema': 1, 'avatar_id': 601, 'tables': tables,
              'ability_roots': len(changes), 'all_unrelated_ability_roots_preserved': True,
              'stringmap_preserved': True, 'weapon_root_20611_original_reader_passed': True,
              'metaconfig_original_entries_preserved': True,
              'metaconfig_added_effect_groups': list(additions),
              'files': {str(p.relative_to(OUT)): sha(p.read_bytes()) for p in OUT.rglob('*') if p.is_file()},
              'human_acceptance': 'pending', 'device_deployed': False,
              'limits': ['Source2.0 fist geometry/textures with original1.9 compatible weapon shader; visual acceptance pending',
                         'NL/weapon effect group definitions included; later armor602/advanced fist effect prefabs are outside601 initial weapon scope',
                         '15 source subskill desc keys absent; existing info/name text retained without invented replacement'],
              'approved_extra_growth_ids': [20611, 20612, 20613]}
    (OUT / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'roots': len(changes), 'tables': {n: t['added_rows'] for n,t in tables.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    prepare()
