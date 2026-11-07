"""Append real source text for every first-chapter challenge dependency.

Preserves accepted rows and challenge behavior; later-source wording is
identified as compatibility data, never claimed as recovered historical1.9.
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
import json
import re
import zipfile
import server19_metadata_export as metadata
import server19_resources as resources
import server19_stage as stage

ROOT = Path(__file__).resolve().parent


def build():
    stage.STORY_RUNTIME_READY_FILE = ROOT / '.local-baseline/server19-dev/chapter1-remaining-ready/runtime-ready.json'
    base = ROOT / '.local-baseline/server19-dev/sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset'
    texts = json.loads((base / 'textmap').read_bytes())
    existing = {row['ID'] for row in texts}
    challenges = {row['challengeId']: row for row in json.loads((base / 'stagechallengedata').read_bytes())}
    dependencies = {}
    for identity in range(10101, 10137):
        for item in stage.stage_config(identity)['challengeList']:
            row = challenges[item['challengeId']]
            for field in ('diaplayTarget', 'explanation'):
                dependencies.setdefault(row[field], []).append(identity)
    missing = set(dependencies) - existing
    paths = resources.resource_map(resources.DEFAULT24)
    with zipfile.ZipFile(resources.DEFAULT24) as package:
        objects = metadata.PackageObjects(package)
        _, raw = objects.object(next(row for row in paths if row['path'] == '_exceloutputasset/textmap'))
        source, _ = metadata.text_map_sources(objects, paths, raw)
    added = []
    for key in sorted(missing):
        matches = [row for row in source if row['ID'] == key and not row.get('_malformed')]
        values = {row['Text'] for row in matches}
        if len(values) != 1:
            raise ValueError('Missing/ambiguous source challenge text: ' + key)
        text = values.pop()
        # Source TSV stores literal Unicode escapes; preserve their exact codepoints.
        text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match[1], 16)), text)
        texts.append({'ID': key, 'Text': text})
        added.append({'ID': key, 'Text': text, 'stages': dependencies[key],
                      'source_path': matches[0]['_source_path'],
                      'source_line': matches[0]['_source_line'],
                      'version_begin': matches[0].get('GameVersionBegin')})
    out = ROOT / '.local-baseline/server19-dev/sony-human-fixes-v1'
    out.mkdir(exist_ok=True)
    encoded, _ = metadata.native_json(texts)
    (out / 'textmap').write_text(encoded, encoding='utf-8')
    assert texts[:-len(added)] == json.loads((base / 'textmap').read_bytes()) if added else True
    (out / 'challenge-text-report.json').write_text(json.dumps({'added': added,
        'checked_stages': 36, 'challenge_behavior_changed': False,
        'historical19_text_recovered': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'missing_keys_fixed': sorted(missing), 'checked_stages': 36}))


if __name__ == '__main__':
    build()
