"""User-approved reference values for the two missing first-cycle trial items."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import csv
import hashlib
import io
import json
import zipfile

import server19_metadata_export as export
import server19_resources as resources
from server19_sakura_prepare import ROOT, OUT


def prepare():
    output = OUT / 'candidate-v1'
    ledger = json.loads((ROOT / 'server19-run/extra-baseline-20261025-v3/runtime-artifacts.json').read_bytes())
    accepted = next(r for r in ledger if r['remote'].endswith('/_exceloutputasset/stigmatadata'))
    raw = (ROOT / accepted['local']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == accepted['sha256']
    original = json.loads(raw)
    kind = export.asset_types()['MoleMole.StigmataDataAsset']
    fields = export.serialized_fields(kind['row_type_index'])
    paths = {r['path']: r for r in resources.resource_map(resources.DEFAULT24)}
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        objects = export.PackageObjects(package)
        _, table_raw = objects.object(paths['data/_exceloutput/stigmatadata'])
        _, text = resources.text_asset(table_raw)
    reader = csv.DictReader(io.StringIO(text.decode('utf-8-sig')), delimiter='\t')
    mapping = export.column_mapping(kind['row_type_index'], reader.fieldnames)
    key = fields[0][0]
    additions, sources = [], []
    for row in reader:
        if int(row[mapping[key]]) not in (30034, 30087):
            continue
        assert row['GameVersionBegin'] == '2.1' and not row['GameVersionEnd']
        item = {}
        for name, pointer in fields:
            expanded = export.array_source(kind['row_type'], name, row)
            value = expanded[0] if expanded is not None else row[mapping[name]]
            item[name] = export.convert(value, pointer)
            if expanded is not None:
                item[name].insert(0, expanded[1])
        additions.append(item)
        sources.append(row)
    assert {r[key] for r in additions} == {30034, 30087} and len(additions) == 2
    assert not ({r[key] for r in original} & {30034, 30087})
    combined = original + additions
    encoded = export.native_json(combined)[0].encode('utf-8')
    assert json.loads(encoded)[:len(original)] == original
    target = output / '_exceloutputasset/stigmatadata'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    report = dict(approval='User accepted reference-value compatibility 2026-10-25',
                  historical_19_values_verified=False, source_version='2.1 rows in existing 2.4 reference',
                  accepted_preimage=accepted, preserved_rows=len(original), added_rows=additions,
                  source_rows=sources, sha256=hashlib.sha256(encoded).hexdigest())
    (output / 'equipment-compatibility.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return additions


if __name__ == '__main__':
    print('Added', len(prepare()), 'approved reference rows; all accepted rows preserved')
