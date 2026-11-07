"""收集现有服务的只读运行包 / Assemble a relocatable, save-free runtime.

Preserves business source and historical readiness receipts byte-for-byte.
Receipts describe the existing client baseline, not acceptance of this probe.
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
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def modules():
    seen = set()
    pending = ['server19', 'server19_story_all_server', 'server19_story_trial_policy']
    while pending:
        name = pending.pop()
        path = ROOT / (name + '.py')
        if name in seen or not path.is_file():
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            names = ([x.name.split('.')[0] for x in node.names] if isinstance(node, ast.Import)
                     else [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            pending.extend(n for n in names if (ROOT / (n + '.py')).is_file())
    return sorted(seen)


def build(output):
    output = output.resolve()
    output.relative_to(ROOT / 'server19-run')
    if output.exists():
        raise ValueError('Use a new output directory; existing artifacts are preserved')
    output.mkdir(parents=True)
    files = {name + '.py' for name in modules()}
    files.update(('server19_table_cache.py', 'server19_fastcopy.py',
                  'server19_gacha_cache.py', 'server19_config_cache.py', 'server19_request_cost.py'))
    files.update(['server19_protocol_schema.json', 'server19_gacha_policy.json',
                  'server19_repeat_drop_policy.json', 'server19_shop_config.json',
                  'server19_virtual_friend_profiles.json', 'server19_story_act_rewards.json',
                  'data/endless-climate-calibration.json'])
    base = '.local-baseline/server19-dev/'
    files.update(p.relative_to(ROOT).as_posix() for p in
                 (ROOT / base / 'metadata-cg-icons-corrected/_exceloutputasset').iterdir() if p.is_file())
    files.update(base + 'chapter1-unified-ready/v1/_exceloutputasset/' + n for n in
                 ('materialdata', 'avatarfragmentdata', 'constvaluesclient', 'textmap'))
    files.update(base + n for n in [
        'chapter1-remaining-ready/runtime-ready.json', 'sony-human-fixes-v1/textmap',
        'cultivation-full-equipment-ready/runtime-ready.json',
        'cultivation-full-equipment-ready/matrix.json',
        'equipment-chain-batch-ready-v3/matrix.json',
        'story-all-20261015/runtime-ready.json', 'story-all-20261015/metadata/materialdata',
        'story-all-20261015/metadata/textmap'])
    cabin = base + 'sony-arm-supply/v1/bh3-server19-metadata/_exceloutputasset/cabinleveldata'
    if (ROOT / cabin).is_file():
        files.add(cabin)
    files.update('server19-run/' + n for n in [
        'equipment-eligibility-20261013/eligibility.json',
        'razer-migration-20261025/trial-policy/leveltrialdata',
        'razer-migration-20261025/trial-policy/avatartrialdata',
        'razer-migration-20261025/revive-diagnosis/stagerevivecostdata',
        'sakura-cycle4-20261026/candidate-v1/catalog.json',
        'sakura-20261025/candidate-v1/_exceloutputasset/stigmatadata',
        'sakura-commissions-20261025/candidate-v3/catalog.json',
        'sakura-cooking-20261026/catalog.json',
        'endless-temperature-mapping-20261027/hp-only-delivery/catalog.json'])
    extra = 'server19-run/kallen-20261025/all-open-delivery/'
    ready = json.loads((ROOT / extra / 'runtime-ready.json').read_bytes())
    files.update(extra + n for n in ready['table_sha256'])
    files.update(extra + n for n in ['runtime-ready.json', 'stagedata_main', 'extrastorychapter',
                                    'extrastoryarea', 'extrastoryact', 'extra-achievement-catalog.json'])
    records = []
    for name in sorted(files):
        src = ROOT / name
        dst = output / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        records.append(dict(path=name, sha256=hashlib.sha256(dst.read_bytes()).hexdigest(), size=dst.stat().st_size))
    for name in ['server19_portable.py', 'server19_portable_smoke.py', 'audit_endless_numpy_portability.py']:
        src = ROOT / 'scripts' / name
        shutil.copyfile(src, output / name)
        records.append(dict(path=name, sha256=hashlib.sha256(src.read_bytes()).hexdigest(), size=src.stat().st_size))
    manifest = dict(schema=1, source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                    business_modules=modules(), files=records,
                    contains_save=False, client_resources_included=False,
                    readiness='Historical accepted-client receipts preserved; not Android gameplay acceptance',
                    dependencies={'python': '3.11', 'numpy_android': '1.26.2', 'tzdata': '2025.2'})
    (output / 'portable-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(output).as_posix())
    print(json.dumps(dict(directory=str(output), files=len(records), modules=len(modules()),
                         bytes=sum(r['size'] for r in records), zip_bytes=archive.stat().st_size,
                         zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()), indent=2))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
