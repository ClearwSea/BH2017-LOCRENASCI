"""Append real compatibility dependencies; keep all accepted rows unchanged.

Only inspected 2.4 typed rows are projected into original serialized fields.
Artwork availability is audited separately; paths are never substituted.
No device, account, service or accepted baseline is modified by this builder.
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
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

import analyze19 as native
import server19_metadata_export as metadata
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
BASE = ROOT / '.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset'
OUT = ROOT / '.local-baseline/server19-dev/chapter1-metadata-ready/v1'
INPUTS = {
    'materialdata': 'c020cadada3bbe99eae313be315a704224d6ecea166c9816d047cce6d2250da0',
    'avatarfragmentdata': '9577432b9297b1fe780abf404b947d9078e6d1a5a784b1330f5099a32ab9d32f',
    'textmap': 'f5653d1c85eded5c8213d7c82a65e86aff320e13406449b895f4f463253ce46e',
    'constvaluesclient': 'dc9329c47960b3af94a6d418e30a832af044e407860abcf4b3aa7d798bfec5ee',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(output=OUT):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use a fresh workspace candidate directory')
    baseline = {}
    for name, digest in INPUTS.items():
        raw = (BASE / name).read_bytes()
        if sha(raw) != digest:
            raise ValueError('Accepted metadata changed: ' + name)
        baseline[name] = json.loads(raw)
    paths = resources.resource_map(resources.DEFAULT24)
    by_path = {row['path']: row for row in paths}
    report = {'schema': 1, 'source24_sha256': sha(resources.DEFAULT24.read_bytes()),
              'files': [], 'added_rows': {}, 'artwork': 'independent availability audit required',
              'save_operation': 'none', 'device_operation': 'none'}
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        decoder = metadata.SourceTypedDecoder(package)
        objects = metadata.PackageObjects(package)
        text_dependencies = set()
        for table, row_type, identities in (
                ('materialdata', 'MoleMole.ItemMetaData', (3108,)),
                ('avatarfragmentdata', 'MoleMole.AvatarFragmentMetaData', (10601, 10603))):
            record = by_path['_exceloutputasset/' + table]
            _, raw = objects.object(record)
            rows = decoder.rows(raw, row_type)
            original_type = next(i for i in range(len(native.T)) if native.type_name(i) == row_type)
            fields = metadata.serialized_fields(original_type)
            additions = []
            for identity in identities:
                source_rows = [row for row in rows if row['ID'] == identity]
                if len(source_rows) != 1 or any(row['ID'] == identity for row in baseline[table]):
                    raise ValueError('Dependency must be unique and absent from accepted table')
                source = source_rows[0]
                row = {name: metadata.project_typed(source[name], pointer) for name, pointer in fields}
                additions.append(row)
                for field in ('displayTitle', 'displayDescription', 'displayBGDescription'):
                    if row.get(field):
                        text_dependencies.add(row[field])
                import re
                for entry in row.get('comeFromList', []):
                    text_dependencies.update(re.findall(r'text="([^"]+)"', entry))
            baseline[table] += additions
            report['added_rows'][table] = {
                'row_type': row_type, 'original_type_index': original_type,
                'source_asset_sha256': sha(raw), 'rows': additions,
                'historical19_values_recovered': False,
                'original_rows_preserved': True,
            }
        _, raw = objects.object(by_path['_exceloutputasset/textmap'])
        source_texts, sources = metadata.text_map_sources(objects, paths, raw)
        existing = {row['ID']: row['Text'] for row in baseline['textmap']}
        additions = []
        for identity in sorted(text_dependencies - existing.keys()):
            matches = {row['Text'] for row in source_texts if row['ID'] == identity and not row.get('_malformed')}
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous real item text: ' + identity)
            additions.append({'ID': identity, 'Text': matches.pop()})
        baseline['textmap'] += additions
        report['added_rows']['textmap'] = {'rows': additions, 'original_rows_preserved': True}
        rows = [row for row in baseline['constvaluesclient'] if row['name'] == 'IsExtraActHide']
        if rows != [{'name': 'IsExtraActHide', 'type': 'bool', 'value': 'true'}]:
            raise ValueError('Original Extra visibility constant changed')
        rows[0]['value'] = 'false'
        report['visibility'] = {'name': 'IsExtraActHide', 'before': 'true', 'after': 'false',
            'actType2_retained': True, 'scope': 'local updated client only'}
    output.mkdir(parents=True)
    for name, value in baseline.items():
        encoded, fixes = metadata.native_json(value)
        raw = encoded.encode('utf-8')
        relative = '_exceloutputasset/' + name
        path = output / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        report['files'].append({'path': relative, 'sha256': sha(raw), 'bytes': len(raw),
            'required_existing_sha256': INPUTS[name], 'native_number_fixups': fixes,
            'device_path': '/sdcard/bh3-server19-metadata/' + relative})
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    report = build(args.output)
    print(json.dumps({'candidate': str(args.output), 'files': report['files'],
                      'added_item_ids': {key: [r['ID'] for r in info['rows']]
                        for key, info in report['added_rows'].items() if key != 'textmap'},
                      'added_texts': len(report['added_rows']['textmap']['rows'])}))
