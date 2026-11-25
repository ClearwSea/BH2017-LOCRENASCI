"""Apply the reviewed V0.2.1 data and poster changes to freshly generated outputs."""
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / 'release_021_data'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def apply(work, supplemental_root):
    from PIL import Image
    import sys

    if str(DATA / "runtime") not in sys.path:
        sys.path.insert(0, str(DATA / "runtime"))
    import server19_supply_rotation as supply
    index = json.loads((DATA / 'index.json').read_bytes())
    updates = []
    for section in ('runtime', 'resources'):
        for name, record in index[section].items():
            target = work / section / name
            current = digest(target.read_bytes()) if target.is_file() else None
            if current != record['before']:
                raise ValueError(f'Unexpected V0.2.1 preimage: {section}/{name} ({current})')
            source = (DATA / section / name).read_bytes()
            if digest(source) != record['after']:
                raise ValueError(f'Invalid V0.2.1 input: {section}/{name}')
            updates.append((target, source))
    previews = {}
    for name, expected in index['posters'].items():
        poster = supplemental_root / 'images/gacha/rotation' / name
        payload = poster.read_bytes() if poster.is_file() else b''
        if digest(payload) != expected:
            raise ValueError('Use the V0.2.1 supplemental resource ZIP. Missing or mismatched poster: ' + name)
        updates.append((work / 'runtime/supply-posters' / name, payload))
        with Image.open(BytesIO(payload)) as image:
            if image.size != (1680, 350):
                raise ValueError('Invalid supply poster dimensions: ' + name)
            thumb = BytesIO()
            image.convert('RGB').resize((840, 175), Image.Resampling.LANCZOS).save(thumb, 'JPEG', quality=83)
        previews[poster.stem] = 'data:image/jpeg;base64,' + base64.b64encode(thumb.getvalue()).decode('ascii')

    record = index['native']
    target = work / 'native/libil2cpp.so'
    native = bytearray(target.read_bytes())
    if digest(native) != record['before']:
        raise ValueError('The V0.2.1 poster patch expects the reviewed ARM library')
    for offset, replacement in record['ranges']:
        block = bytes.fromhex(replacement)
        native[offset:offset + len(block)] = block
    native.extend((DATA / 'native-tail.bin').read_bytes())
    if len(native) != record['length'] or digest(native) != record['after']:
        raise ValueError('Unexpected V0.2.1 native output')
    for path, payload in updates:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    target.write_bytes(native)
    template = (DATA.parent / 'android-server-probe/app/src/main/assets/gm2017.html').read_text(encoding='utf-8-sig')
    catalog = (work / 'runtime/gm-catalog.json').read_text(encoding='utf-8').strip()
    themes = json.dumps(dict(themes=supply.catalog(), previews=previews), ensure_ascii=False, separators=(',', ':'))
    if template.count('/*CATALOG*/ null') != 1 or template.count('/*SUPPLY*/ null') != 1:
        raise ValueError('Missing GM HTML data placeholders')
    page = template.replace('/*CATALOG*/ null', catalog.replace('<', chr(92) + 'u003c'))
    page = page.replace('/*SUPPLY*/ null', themes.replace('<', chr(92) + 'u003c'))
    (work / 'gm2017.html').write_text(page, encoding='utf-8')
    return {'runtime_files': len(index['runtime']), 'resource_files': len(index['resources']),
            'native_sha256': record['after']}
