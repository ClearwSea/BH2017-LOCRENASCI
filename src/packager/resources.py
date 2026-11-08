"""Extract and adapt client resources; retain supplied baseline artwork exactly."""
import hashlib
from pathlib import Path
import shutil
import zipfile
from .core import ROOT, read_json, write_json, safe_relative
from .splice import apply


def prepare(client19, client24, client_tables, output, extracted, supplemental_images):
    import server19_resources as resources
    import server19_baked as baked
    resources.DEFAULT19, resources.DEFAULT24 = client19, client24
    if not (extracted / 'metaconfig.txt').is_file():
        baked.extract(extracted, client24)
    recipes = read_json(ROOT / 'rules/client-resource-splices.json')
    mapping = {r['path']: r for r in resources.resource_map(client24)}
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(client24) as package:
        for destination, spec in recipes['resources'].items():
            safe_relative(destination)
            if spec['source'] == 'baked':
                source = (extracted / str(safe_relative(spec['path']))).read_bytes()
            else:
                _, raw = resources.object_bytes(package, mapping[spec['path']])
                _, source = resources.text_asset(raw)
            target = output / 'private/data' / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(apply(source, spec['operations']))
    metadata = output / 'private/data/bh3-server19-metadata/_exceloutputasset'
    shutil.copytree(client_tables, metadata)
    from .recommendations import sync_tsv
    recommendation_text = output / 'private/data/bh3-server19-resources/data/_exceloutput/newbieequipadv'
    recommendation_text.write_bytes(sync_tsv(recommendation_text.read_bytes(),
                                             read_json(client_tables / 'newbieequipadv')))
    for name in ('bridge/celebration.png', 'bridge/github.png', 'gacha/dracula.png',
                 'gacha/ziyuan.png', 'announcement/teaparty.png', 'announcement/update.png'):
        target = output / 'private/data/bh3-server19-resources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(supplemental_images / name, target)
    return len(recipes['resources']) + len(list(client_tables.iterdir())) + 6


def pack(resource_root, output):
    output.mkdir(parents=True, exist_ok=False)
    entries = []
    with zipfile.ZipFile(output / 'client-resources.zip', 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as main, \
            zipfile.ZipFile(output / 'client-videos.zip', 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as videos:
        for path in sorted(resource_root.rglob('*')):
            if not path.is_file():
                continue
            name = path.relative_to(resource_root).as_posix()
            separate = name.startswith('external/')
            raw = path.read_bytes()
            (videos if separate else main).writestr(name, raw)
            entries.append({'path': name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                            'pack': 'video' if separate else 'main'})
    write_json(output / 'client-resources.json', {'version': 'server19-original-inputs-1', 'entries': entries})
    return len(entries)
