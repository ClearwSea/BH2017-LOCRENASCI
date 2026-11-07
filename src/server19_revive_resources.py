"""Recover the expanded revive-cost table, verified against source binary rows."""

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
import io
import json
import zipfile
from pathlib import Path

import server19_resources as resources
from server19_metadata_export import array_source


def build(output, apk=resources.DEFAULT24):
    paths = {row['path']: row for row in resources.resource_map(apk)}
    with zipfile.ZipFile(apk) as package:
        _, raw = resources.object_bytes(package, paths['_exceloutputasset/stagerevivecostdata'])
        _, text_raw = resources.object_bytes(package, paths['data/_exceloutput/stagerevivecostdata'])
    _, text = resources.text_asset(text_raw)
    source = list(csv.DictReader(io.StringIO(text.decode('utf-8-sig')), delimiter='\t'))
    reader = resources.Reader(raw, 28)
    reader.string()
    rows = []
    for _ in range(reader.read('i')):
        number = reader.read('i')
        values = [reader.read('i') for _ in range(reader.read('i'))]
        row = next(row for row in source if int(row['reviveTimes']) == number)
        expanded, sentinel = array_source('MoleMole.ReviveCostTypeMetaData', 'Type1', row)
        assert values == [sentinel] + [int(value) for value in expanded.split(',')]
        rows.append({'reviveTimes': number, 'Type1': values})
    assert reader.string().lower() == '_exceloutputasset/stagerevivecostdata'
    assert reader.pos == len(raw)
    assert [row['reviveTimes'] for row in rows] == list(range(1, 13))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return rows


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
