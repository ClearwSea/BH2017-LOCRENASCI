"""Generate server data, client tables and capability records from raw inputs."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from .core import ROOT, read_json, write_json, digest
from .json_recipes import render, sources

READY = {
    'chapter1': '.local-baseline/server19-dev/chapter1-remaining-ready/runtime-ready.json',
    'story': '.local-baseline/server19-dev/story-all-20261015/runtime-ready.json',
    'equipment': '.local-baseline/server19-dev/cultivation-full-equipment-ready/runtime-ready.json',
    'extra_story': 'server19-run/kallen-20261025/all-open-delivery/runtime-ready.json',
}


def copy_sources(output):
    shutil.copyfile(ROOT / 'rules/virtual-friend-profiles.json',
                    output / 'server19_virtual_friend_profiles.json')
    manifest = read_json(ROOT / 'SOURCE-MANIFEST.json')
    names = {r['path'] for r in manifest['files'] if r['role'] == 'runtime'}
    names.update(('server19_portable.py', 'server19_build_capabilities.py'))
    pending = list(names)
    while pending:
        name = pending.pop()
        for node in ast.walk(ast.parse((ROOT / name).read_text(encoding='utf-8-sig'))):
            modules = [a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import) else \
                [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else []
            for module in modules:
                relative = module + '.py'
                if (ROOT / relative).is_file() and relative not in names:
                    names.add(relative)
                    pending.append(relative)
    for name in names:
        shutil.copyfile(ROOT / name, output / name)
    for name in ('server19_gacha_policy.json', 'server19_repeat_drop_policy.json', 'server19_befall_drop_policy.json', 'server19_shop_config.json',
                 'data/endless-climate-calibration.json'):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    return names


def prepare(client24, data_work, output, client_tables):
    from server19_metadata_export import native_json
    output.mkdir(parents=True, exist_ok=False)
    client_tables.mkdir(parents=True, exist_ok=False)
    effective = data_work / 'generated/effective-tables'
    data = sources(data_work, effective, client24)
    recipes = read_json(ROOT / 'rules/generated-data-recipes.json')
    from .story_difficulties import adapt as adapt_difficulties
    for name, recipe in recipes['runtime'].items():
        value = render(recipe, data)
        if name.endswith('/stagedata_main'):
            adapt_difficulties(value)
        write_json(output / name, value)
    default = output / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
    shutil.copytree(effective, default)
    from .story_difficulties import adapt as adapt_difficulties
    story_rows = read_json(default / 'stagedata_main')
    adapt_difficulties(story_rows)
    write_json(default / 'stagedata_main', story_rows)
    # Paths retained by the business modules are generated destinations, never inputs.
    overrides = output / '.local-baseline/server19-dev/chapter1-unified-ready/v1/_exceloutputasset'
    overrides.mkdir(parents=True, exist_ok=True)
    for name in ('materialdata', 'avatarfragmentdata', 'constvaluesclient', 'textmap'):
        shutil.copyfile(effective / name, overrides / name)
    cabin = output / '.local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/cabinleveldata'
    cabin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(effective / 'cabinleveldata', cabin)
    stigmata = output / 'server19-run/sakura-20261025/candidate-v1/_exceloutputasset/stigmatadata'
    stigmata.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(effective / 'stigmatadata', stigmata)
    from .recommendations import adapt
    encoded_tables = {name: native_json(render(recipe, data))[0]
                      for name, recipe in recipes['client_tables'].items()}
    # native_json removes source array-length markers. Validate the actual
    # client representation rather than treating those counts as references.
    rendered = {name: json.loads(encoded) for name, encoded in encoded_tables.items()}
    # Source recipes retain historical row selections. Overlay the restored
    # Befall dependencies into the client projection as well as server tables.
    befall = set(range(1601, 1672, 10))
    restored_activities = json.loads(native_json(read_json(effective / 'weekdayactivity'))[0])
    level_ids = {sid for row in restored_activities if row['weekDayActivityID'] in befall
                 for sid in row['levelIDList']}
    scopes = {'weekdayactivity': ('weekDayActivityID', befall),
              'stagedata_main': ('levelId', level_ids),
              'tutorialstepdata': ('id', {10731}),
              'rewarddata': ('RewardID', set(range(200048, 200054))),
              'stageresetcostdata': ('times', None)}
    for table, (key, identities) in scopes.items():
        restored = json.loads(native_json(read_json(effective / table))[0])
        if identities is None:
            rendered[table] = restored
        else:
            additions = [row for row in restored if row[key] in identities]
            if {row[key] for row in additions} != identities:
                raise ValueError('Missing restored client dependencies: ' + table)
            by_id = {row[key]: row for row in rendered[table]}
            by_id.update({row[key]: row for row in additions})
            rendered[table] = list(by_id.values())
        encoded_tables[table] = json.dumps(rendered[table], ensure_ascii=False, separators=(',', ':'))
    adapt_difficulties(rendered['stagedata_main'])
    encoded_tables['stagedata_main'] = json.dumps(rendered['stagedata_main'], ensure_ascii=False,
                                                separators=(',', ':'))
    adapt(rendered, read_json(ROOT / 'rules/recommendation-compatibility.json'))
    from .equipment_metadata import complete
    complete(rendered, json.loads(native_json(data['unfiltered/equipmentskilldata'])[0]),
             data['source/textmap_rows'])
    encoded_tables['equipmentskilldata'] = json.dumps(rendered['equipmentskilldata'], ensure_ascii=False,
                                                     separators=(',', ':'))
    encoded_tables['textmap'] = json.dumps(rendered['textmap'], ensure_ascii=False, separators=(',', ':'))
    encoded_tables['newbieequipadv'] = json.dumps(rendered['newbieequipadv'], ensure_ascii=False,
                                                 separators=(',', ':'))
    for name, encoded in encoded_tables.items():
        (client_tables / name).write_text(encoded + '\n', encoding='utf-8')
    shutil.copyfile(effective / 'avatarskilldata.chars', client_tables / 'avatarskilldata.chars')
    shutil.copyfile(data_work / 'generated/protocol/server19_protocol_schema.json', output / 'server19_protocol_schema.json')
    names = copy_sources(output)
    return {'runtime_modules': len(names), 'client_tables': len(recipes['client_tables']) + 1}


def finish(output, native, resource_manifest, archive):
    import server19_build_capabilities as capabilities
    records = {}
    native_caps = set()
    for scope, name in READY.items():
        path = output / name
        ready = read_json(path)
        ready['build_proof'] = 'packaged-artifacts-v1'
        if 'table_sha256' in ready:
            ready['table_sha256'] = {n: digest(path.parent / n) for n in ready['table_sha256']}
        if scope == 'equipment':
            ready['matrix_sha256'] = digest(path.parent / 'matrix.json')
        if scope == 'story':
            table = read_json(output / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/stagedata_main')
            ids = set(ready['ready_stage_ids'])
            ready['source_rows_sha256'] = capabilities.canonical_sha([r for r in table if r['levelId'] in ids])
        native_caps.update(ready.get('required_native_capabilities', []))
        write_json(path, ready)
        records[scope] = capabilities.canonical_sha(ready)
    write_json(output / 'build-capabilities.json', {'schema': 1, 'evidence_kind': 'packaged-artifacts',
        'source_mode': 'original-inputs', 'human_gameplay_verified': False,
        'native_sha256': digest(native), 'resource_manifest_sha256': digest(resource_manifest),
        'native_capabilities': sorted(native_caps), 'records': records})
    files = [{'path': p.relative_to(output).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(output.rglob('*')) if p.is_file()]
    write_json(output / 'portable-manifest.json', {'schema': 1, 'files': files,
        'contains_save': False, 'source_mode': 'original-inputs'})
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                package.write(p, p.relative_to(output).as_posix())
    return len(files)
