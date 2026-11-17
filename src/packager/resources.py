"""Extract and adapt client resources; retain supplied baseline artwork exactly."""
import hashlib
from pathlib import Path
import shutil
import struct
import zipfile
from .core import ROOT, BuildError, read_json, write_json, safe_relative
from .splice import apply

# 2.4 -> 1.9 structural translation for Equip_EX3_GarlandOfFire (Chacha 2-piece set):
# translates ModifySelfParameterByPropertyMixin tag 128->120, ConfigAbilityModifier 30->29,
# SpawnPropObject 26->24, DamageByAttackValue, etc. (966 -> 946 bytes).
_GARLAND_OF_FIRE_EDITS = (
    (8, 10, b'x'), (26, 28, b'x'), (44, 46, b'x'), (62, 64, b'x'), (190, 191, b''),
    (165, 168, b'\xdc\x00\x1d'), (226, 227, b'\x10'), (238, 239, b''), (213, 216, b'\xdc\x00\x1d'),
    (279, 280, b''), (282, 283, b'\r'), (291, 292, b'#'), (295, 296, b','), (303, 304, b','),
    (311, 312, b','), (321, 322, b'\r'), (330, 331, b'0'), (334, 335, b'#'), (338, 339, b','),
    (346, 347, b','), (354, 355, b','), (261, 264, b'\xdc\x00\x1d'), (407, 408, b''),
    (384, 387, b'\xdc\x00\x1d'), (455, 456, b''), (459, 461, b'{'), (476, 477, b''),
    (477, 478, b''), (461, 464, b'\xdc\x00\x18'), (496, 497, b'\r'), (430, 433, b'\xdc\x00\x1d'),
    (551, 552, b''), (555, 557, b'{'), (572, 573, b''), (573, 574, b''),
    (557, 560, b'\xdc\x00\x18'), (526, 529, b'\xdc\x00\x1d'), (636, 637, b''), (639, 640, b'Y'),
    (651, 652, b'-'), (656, 657, b''), (652, 655, b'\xdc\x00\x18'), (702, 703, b'8'),
    (730, 731, b'Y'), (740, 741, b'\r'), (764, 765, b';'), (611, 614, b'\xdc\x00\x1d'),
    (841, 842, b''), (849, 850, b'-'), (854, 855, b''), (850, 853, b'\xdc\x00\x18'),
    (792, 795, b'\xdc\x00\x1d'), (901, 902, b'\r'), (912, 913, b'\r'),
)


def _patch_baked_abilities(raw_bytes, stringmap_bytes):
    """Patch Equip_EX3_GarlandOfFire from 2.4 schema to 1.9 inside bakedabilitydata."""
    strings = stringmap_bytes.decode('utf-8', 'replace').split('\x1f')
    target_idx = strings.index('Equip_EX3_GarlandOfFire')
    h0, h1 = struct.unpack_from('<II', raw_bytes, 0)
    pos = 8
    ne = struct.unpack_from('<I', raw_bytes, pos)[0]
    pos += 4
    entries = [struct.unpack_from('<II', raw_bytes, pos + i * 8) for i in range(ne)]
    pos += ne * 8
    no = struct.unpack_from('<I', raw_bytes, pos)[0]
    pos += 4
    overrides = [struct.unpack_from('<III', raw_bytes, pos + i * 12) for i in range(no)]
    pos += no * 12
    dlen = struct.unpack_from('<I', raw_bytes, pos)[0]
    pos += 4
    if pos + dlen != len(raw_bytes):
        raise BuildError('bakedabilitydata container length mismatch')
    data = raw_bytes[pos:]
    refs = {o: (k, None) for k, o in entries}
    refs.update({o: (k, v) for k, v, o in overrides})
    offs = sorted(refs)
    spans = {refs[o]: (o, offs[i + 1] if i + 1 < len(offs) else dlen) for i, o in enumerate(offs)}
    out, new_offs = bytearray(), {}
    for o in offs:
        ident = refs[o]
        left, right = spans[ident]
        chunk = data[left:right]
        if ident == (target_idx, None):
            if len(chunk) != 966:
                raise BuildError('Unexpected Equip_EX3_GarlandOfFire span length')
            buf = bytearray(chunk)
            for start, end, rep in sorted(_GARLAND_OF_FIRE_EDITS, key=lambda x: (x[0], x[1]), reverse=True):
                buf[start:end] = rep
            chunk = bytes(buf)
        new_offs[o] = len(out)
        out.extend(chunk)
    res = bytearray(struct.pack('<III', h0, h1, ne))
    for k, o in entries:
        res.extend(struct.pack('<II', k, new_offs[o]))
    res.extend(struct.pack('<I', no))
    for k, v, o in overrides:
        res.extend(struct.pack('<III', k, v, new_offs[o]))
    res.extend(struct.pack('<I', len(out)))
    res.extend(out)
    return bytes(res)


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
        # Restore the original scripts for independently audited Befall activities.
        for befall_path in ('lua/levels/event/bosslevel01_l.lua',
                            'lua/levels/event/bosslevel03_l.lua',
                            'lua/levels/event/bosslevel02_h.lua',
                            'lua/levels/event/bosslevel04_h.lua',
                            'lua/levels/event/bosslevel05_h.lua',
                            'lua/levels/event/bosslevel06_h.lua',
                            'lua/levels/event/bosslevel07_h.lua',
                            'lua/levels/event/bosslevel08_h.lua'):
            _, raw = resources.object_bytes(package, mapping[befall_path])
            _, script = resources.text_asset(raw)
            if befall_path.endswith('bosslevel05_h.lua'):
                marker = b'level.forceweak3 = function()'
                if script.count(marker) != 2 or script.count(b'level.forceweak4 = function()') != 0:
                    raise ValueError('Changed Befall wind loop; audit source before repair')
                at = script.rfind(marker)
                script = script[:at] + script[at:].replace(marker, b'level.forceweak4 = function()', 1)
            target = output / 'private/data/bh3-server19-resources' / befall_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(script)
        for destination, spec in recipes['resources'].items():
            safe_relative(destination)
            if spec['source'] == 'baked':
                source = (extracted / str(safe_relative(spec['path']))).read_bytes()
            else:
                _, raw = resources.object_bytes(package, mapping[spec['path']])
                _, source = resources.text_asset(raw)
            target = output / 'private/data' / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            rendered = apply(source, spec['operations'])
            if destination == 'bh3-server19-baked/_baked/bakedabilitydata':
                sm_spec = recipes['resources']['bh3-server19-baked/_baked/stringmap.txt']
                sm_src = (extracted / str(safe_relative(sm_spec['path']))).read_bytes()
                rendered = _patch_baked_abilities(rendered, apply(sm_src, sm_spec['operations']))
            target.write_bytes(rendered)
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
    return len(recipes['resources']) + len(list(client_tables.iterdir())) + 14


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
