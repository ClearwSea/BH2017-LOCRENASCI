"""Build a bounded old-Unity resource bundle from real local2.0 fist assets.

No device operations. Old weapon shader237 is the original1.9 weapon shader
whose complete saved-property key set matches the source material. Its visual
compatibility remains a human acceptance item; geometry/textures are source2.0.
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
import hashlib
import json
import struct
import zipfile
from pathlib import Path
import server19_fuka601_asset_extract as extract
import server19_resources as resources
from UnityPy.helpers.TypeTreeNode import TypeTreeNode
from UnityPy.helpers.Tpk import get_typetree_node
from UnityPy.helpers.UnityVersion import UnityVersion
from UnityPy.helpers.TypeTreeHelper import read_typetree, write_typetree
from UnityPy.streams import EndianBinaryReader, EndianBinaryWriter
import UnityPy

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '.local-baseline/server19-dev/fuka601-recovery-20261015/asset-bundle-v1'
VERSION = UnityVersion.from_str('5.3.6p5')


def node(class_id):
    result = get_typetree_node(class_id, VERSION)
    for index, child in enumerate(result.traverse()):
        for key in ('m_TypeFlags', 'm_MetaFlag'):
            if getattr(child, key) is None:
                setattr(child, key, 0)
        if child.m_Index is None:
            child.m_Index = index
    return result


def encoded(value, tree):
    writer = EndianBinaryWriter(endian='<')
    write_typetree(value, tree, writer)
    result = writer.bytes
    restored = read_typetree(tree, EndianBinaryReader(result, endian='<'), byte_size=len(result))
    if restored != value:
        raise ValueError('Serialized value roundtrip differs')
    return result


def effect_node():
    def flat(n):
        return [{k: v for k, v in row.items() if k != 'm_Children'} for row in n.to_dict_list()]
    rows = flat(node(114))
    string = flat(node(114).m_Children[-1])
    integer = flat(next(x for x in node(1).m_Children if x.m_Name == 'm_Layer'))
    boolean = flat(next(x for x in node(1).m_Children if x.m_Name == 'm_IsActive'))
    for name, template in (('floatPropertyKey', string), ('curveIx', integer),
                           ('materialKeyword', string), ('includeChildrenRenderers', boolean)):
        copied = [dict(x) for x in template]
        copied[0]['m_Name'] = name
        if name == 'includeChildrenRenderers':
            copied[0]['m_MetaFlag'] |= 0x4000
        rows.extend(copied)
    return TypeTreeNode.from_list(rows)


def pattern_node():
    """Original ConfigEffectPattern public serialized fields, not runtime ops."""
    rows = [{k: v for k, v in row.items() if k != 'm_Children'} for row in node(114).to_dict_list()]
    def scalar(name, typ, level=1, size=4, align=False):
        rows.append({'m_Level': level, 'm_Type': typ, 'm_Name': name, 'm_ByteSize': size,
                     'm_Version': 1, 'm_Index': len(rows), 'm_TypeFlags': 0,
                     'm_MetaFlag': 0x4000 if align else 0})
    def string(name, level):
        for row in node(114).m_Children[-1].to_dict_list():
            copied = {k: v for k, v in row.items() if k != 'm_Children'}
            copied['m_Level'] += level - 1
            if copied['m_Level'] == level:
                copied['m_Name'] = name
            rows.append(copied)
    def array(name, typ, level):
        scalar(name, 'vector', level, -1)
        scalar('Array', 'Array', level + 1, -1, True)
        rows[-1]['m_TypeFlags'] = 1
        scalar('size', 'int', level + 2)
        scalar('data', typ, level + 2, -1)
    string('groupName', 1)
    array('patterns', 'EffectPattern', 1)
    string('name', 4)
    scalar('randomOneFromSubs', 'bool', 4, 1, True)
    array('subEffects', 'SubEffect', 4)
    string('prefabPath', 7); string('predicate', 7)
    scalar('opEntry', 'EffectCreationOpEntry', 7, -1)
    scalar('type', 'int', 8)
    string('stringArg', 8)
    array('floatArgs', 'float', 8)
    rows[-1]['m_ByteSize'] = 4
    return TypeTreeNode.from_list(rows)


def parse_pattern(raw):
    reader = resources.Reader(raw, 28)
    name = reader.string(); group = reader.string(); patterns = []
    for _ in range(reader.read('i')):
        title = reader.string(); random = bool(reader.read('B')); reader.align()
        subs = []
        for _ in range(reader.read('i')):
            prefab, predicate = reader.string(), reader.string()
            kind, arg = reader.read('i'), reader.string()
            args = [reader.read('f') for _ in range(reader.read('i'))]
            subs.append({'prefabPath': prefab, 'predicate': predicate,
                         'opEntry': {'type': kind, 'stringArg': arg, 'floatArgs': args}})
        patterns.append({'name': title, 'randomOneFromSubs': random, 'subEffects': subs})
    if reader.pos != len(raw):
        raise ValueError('Effect pattern source not fully consumed')
    return {'m_GameObject': {'m_FileID': 0, 'm_PathID': 0}, 'm_Enabled': 1,
            'm_Script': {'m_FileID': 0, 'm_PathID': -998}, 'm_Name': name,
            'groupName': group, 'patterns': patterns}


def serialized(objects, trees, script_types):
    """A realv15 SerializedFile with type trees; one external original shader."""
    meta = EndianBinaryWriter(endian='<')
    meta.write_string_to_null('5.3.6p5')
    meta.write_int(13)  # Android.
    meta.write_boolean(True)
    meta.write_int(len(trees))
    for class_id, tree in sorted(trees.items()):
        meta.write_int(class_id)
        if class_id < 0:
            meta.write_bytes(script_types[class_id][:16])
        tw = EndianBinaryWriter(endian='<')
        tree.dump_blob(tw, 15)
        meta.write_bytes(script_types[class_id][16:] if class_id < 0 else hashlib.md5(tw.bytes).digest())
        meta.write_bytes(tw.bytes)
    data = EndianBinaryWriter(endian='<')
    meta.write_int(len(objects))
    for pid, class_id, value in objects:
        data.align_stream(8)
        payload = encoded(value, trees[class_id])
        meta.align_stream(4)
        meta.write_long(pid)
        meta.write_u_int(data.Position)
        meta.write_u_int(len(payload))
        meta.write_int(class_id)
        meta.write_short(114 if class_id < 0 else class_id)
        meta.write_short(-class_id - 1 if class_id < 0 else -1)
        meta.write_boolean(False)
        data.write_bytes(payload)
    scripts = [pid for pid, cid, _ in objects if cid == 115]
    meta.write_int(len(scripts))
    for script in scripts:
        meta.write_int(0)
        meta.align_stream(4)
        meta.write_long(script)
    meta.write_int(2)
    for external in ('sharedassets0.assets', 'unity default resources'):
        meta.write_string_to_null('')
        meta.write_bytes(bytes(16))
        meta.write_int(0)
        meta.write_string_to_null(external)
    meta.write_string_to_null('')
    raw_meta = meta.bytes
    offset = (20 + len(raw_meta) + 15) & ~15
    return struct.pack('>4I', len(raw_meta), offset + len(data.bytes), 15, offset) + bytes(4) + raw_meta + bytes(offset - 20 - len(raw_meta)) + data.bytes


def bundle(cab):
    info = EndianBinaryWriter(endian='>')
    info.write_bytes(bytes(16))
    info.write_int(1)
    info.write_u_int(len(cab)); info.write_u_int(len(cab)); info.write_u_short(0)
    info.write_int(1)
    info.write_long(0); info.write_long(len(cab)); info.write_u_int(4)
    info.write_string_to_null('CAB-fuka601-original-models')
    header = EndianBinaryWriter(endian='>')
    header.write_string_to_null('UnityFS'); header.write_u_int(6)
    header.write_string_to_null('5.x.x'); header.write_string_to_null('5.3.6p5')
    total = header.Position + 20 + len(info.bytes) + len(cab)
    header.write_long(total); header.write_u_int(len(info.bytes)); header.write_u_int(len(info.bytes)); header.write_u_int(64)
    return header.bytes + info.bytes + cab


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads((extract.OUT / 'report.json').read_text(encoding='utf-8'))
    env = UnityPy.Environment()
    files = {}
    values = {}
    classes = {}
    with zipfile.ZipFile(extract.APK) as source, zipfile.ZipFile(resources.DEFAULT19) as old:
        for name in report['files']:
            if name != 'sharedassets0.assets':
                files[name] = env.load_file(source.read('assets/bin/Data/' + name), name=name)
        original = env.load_file(old.read('assets/bin/Data/globalgamemanagers.assets'), name='original-global')
        scripts = [o for o in original.objects.values() if o.type.name == 'MonoScript'
                   and b'MonoWeaponFX_InterpolateRendererProperty' in o.get_raw_data()]
        if len(scripts) != 1:
            raise ValueError('Original renderer-property script ambiguous')
        script = scripts[0].parse_as_dict()
        if script['m_ClassName'] != 'MonoWeaponFX_InterpolateRendererProperty':
            raise ValueError('Wrong original script')
        # Native schema hashes come from original MonoScripts. The bounded
        # renderer-opacity adapter has a new deterministic compatibility GUID:
        # the original class exists but no serialized instance was found in
        # either APK. Do not mislabel that GUID as a historical script GUID.
        original_map = resources.resource_map(resources.DEFAULT19)
        script_types = {}
        visited = set()
        target_scripts = {scripts[0].path_id: -1}
        for record in original_map:
            if not record['path'].startswith(('entities/weapon/', 'effect/data/')) or record['file'] in visited:
                continue
            visited.add(record['file'])
            raw_file = old.read('assets/bin/Data/' + record['file'])
            layout = resources.serialized(raw_file)
            for obj in layout['objects'].values():
                if obj['class'] != 114:
                    continue
                fid, pid = struct.unpack_from('<iq', raw_file, obj['offset'] + 16)
                external = layout['externals'][fid - 1].rsplit('/', 1)[-1] if fid else record['file']
                if external != 'globalgamemanagers.assets':
                    continue
                script_object = original.objects.get(pid)
                if script_object is None or script_object.class_id != 115:
                    continue
                class_name = script_object.parse_as_dict()['m_ClassName']
                cid = -1 if pid in target_scripts else -2 if class_name == 'ConfigEffectPattern' else None
                if cid is not None:
                    found = next(t for t in layout['types'] if t['class'] == obj['type_id'])['raw'][4:36]
                    if cid in script_types and script_types[cid] != found:
                        raise ValueError('Original script type hashes disagree')
                    script_types[cid] = found
            if len(script_types) == 2:
                break
        if -2 not in script_types:
            raise ValueError('Actual original ConfigEffectPattern type identity missing')
        if -1 not in script_types:
            guid = hashlib.md5(b'bh3-offline-maintenance/Fuka601/RendererOpacityAdapter/v1').digest()
            script_types[-1] = guid + bytes(script['m_PropertiesHash'].values())
        old_material = env.load_file(old.read('assets/bin/Data/9eb6168fc5796a344a98aaf1d4093767'), name='original-material').objects[1].parse_as_dict()
        for row in report['objects']:
            if row['file'] == 'sharedassets0.assets':
                continue
            key = (row['file'], row['path_id'])
            obj = files[key[0]].objects[key[1]]
            classes[key] = -1 if obj.class_id == 114 else obj.class_id
            if obj.class_id == 114:
                raw = obj.get_raw_data()
                reader = resources.Reader(raw, 32)
                prop = reader.string(); curve = reader.read('i'); material_index = reader.read('i')
                if reader.pos != len(raw) or (prop, curve, material_index) != ('_Opaqueness', 0, 0):
                    raise ValueError('Not the bounded single-material opacity profile')
                head = obj.parse_monobehaviour_head()
                values[key] = {'m_GameObject': {'m_FileID': head.m_GameObject.m_FileID, 'm_PathID': head.m_GameObject.m_PathID},
                               'm_Enabled': head.m_Enabled, 'm_Script': {'m_FileID': 0, 'm_PathID': -999},
                               'm_Name': head.m_Name, 'floatPropertyKey': prop, 'curveIx': curve,
                               'materialKeyword': '', 'includeChildrenRenderers': False}
            else:
                value = obj.parse_as_dict()
                values[key] = extract.old_layout(value, obj.type.name)
                if obj.class_id == 1:
                    pairs = []
                    for component in value['m_Component']:
                        ptr = component['component']; owner = key[0] if not ptr['m_FileID'] else files[key[0]].externals[ptr['m_FileID'] - 1].name
                        pairs.append((files[owner].objects[ptr['m_PathID']].class_id, ptr))
                    values[key]['m_Component'] = pairs
                if obj.class_id == 21:
                    for group, pairs in value['m_SavedProperties'].items():
                        original_keys = {name['name'] for name, _ in old_material['m_SavedProperties'][group]}
                        if {name for name, _ in pairs} != original_keys:
                            raise ValueError('Original weapon shader property contract differs')
        script_key = ('original-script', scripts[0].path_id)
        values[script_key] = script; classes[script_key] = 115
        effect_scripts = [o for o in original.objects.values() if o.type.name == 'MonoScript'
                          and b'ConfigEffectPattern' in o.get_raw_data()]
        effect_scripts = [o for o in effect_scripts if o.parse_as_dict()['m_ClassName'] == 'ConfigEffectPattern']
        if len(effect_scripts) != 1:
            raise ValueError('Original ConfigEffectPattern script ambiguous')
        effect_script_key = ('original-script', effect_scripts[0].path_id)
        values[effect_script_key] = effect_scripts[0].parse_as_dict(); classes[effect_script_key] = 115
        pattern_roots = []
        for path, filename in (('effect/data/avatar/effectpattern_fuka_nl', '384aa431f3587664c9c6b1882bef3184'),
                               ('effect/data/weapon/effectpattern_fuka_weapon', '0ede37ee65ce19c45b6bf9d6dc8998ac')):
            f = env.load_file(source.read('assets/bin/Data/' + filename), name=filename)
            key = (filename, 1)
            values[key] = parse_pattern(f.objects[1].get_raw_data()); classes[key] = -2
            pattern_roots.append((path, key))
        icon_roots = []
        for suffix, filename in (('2', '83f41e6c474381d478c7ea3609dd288c'), ('3', 'a3ad153d6adb527448fb155f6c730fd7')):
            files[filename] = env.load_file(source.read('assets/bin/Data/' + filename), name=filename)
            sprite_renderer = next(o for o in files[filename].objects.values() if o.class_id == 212)
            dep = files[filename].externals[sprite_renderer.parse_as_dict()['m_Sprite']['m_FileID'] - 1].name
            files[dep] = env.load_file(source.read('assets/bin/Data/' + dep), name=dep)
            for owner in (filename, dep):
                for obj in files[owner].objects.values():
                    key = (owner, obj.path_id)
                    value = extract.old_layout(obj.parse_as_dict(), obj.type.name)
                    if obj.class_id == 1:
                        value['m_Component'] = [(files[owner].objects[p['component']['m_PathID']].class_id, p['component']) for p in value['m_Component']]
                    if obj.class_id == 212:
                        value['m_Materials'] = [{'m_FileID': -123, 'm_PathID': 10754}]
                    values[key] = value; classes[key] = obj.class_id
            icon_roots.append((f'spriteoutput/weaponicons/weapon_fist_f1_25_{suffix}', (filename, 1)))
        identities = {key: i + 1 for i, key in enumerate(values)}
        def remap(value, owner):
            if isinstance(value, dict):
                if 'm_FileID' in value and 'm_PathID' in value:
                    pid, fid = value['m_PathID'], value['m_FileID']
                    if fid == -123 and pid == 10754:
                        return {'m_FileID': 2, 'm_PathID': 10754}
                    if pid == -999:
                        return {'m_FileID': 0, 'm_PathID': identities[script_key]}
                    if pid == -998:
                        return {'m_FileID': 0, 'm_PathID': identities[effect_script_key]}
                    if not pid:
                        return {'m_FileID': 0, 'm_PathID': 0}
                    target = owner if not fid else files[owner].externals[fid - 1].name
                    if target == 'sharedassets0.assets':
                        if pid != 260:
                            raise ValueError('Unexpected external object')
                        return {'m_FileID': 1, 'm_PathID': 237}
                    return {'m_FileID': 0, 'm_PathID': identities[(target, pid)]}
                return {k: remap(v, owner) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                converted = [remap(v, owner) for v in value]
                return tuple(converted) if isinstance(value, tuple) else converted
            return value
        objects = [(identities[key], classes[key], remap(value, key[0])) for key, value in values.items()]
        preload = [{'m_FileID': 0, 'm_PathID': pid} for pid, _, _ in objects]
        containers = []
        for name, suffix in zip(extract.SEEDS, ('2', '3')):
            containers.append((f'entities/weapon/fist_f1/weapon_fist_f1_25_{suffix}',
                               {'preloadIndex': 0, 'preloadSize': len(preload), 'asset': {'m_FileID': 0, 'm_PathID': identities[(name, 3)]}}))
        containers.extend((path, {'preloadIndex': 0, 'preloadSize': len(preload), 'asset': {'m_FileID': 0, 'm_PathID': identities[key]}}) for path, key in icon_roots + pattern_roots)
        objects.append((len(objects) + 1, 142, {'m_Name': 'fuka601-original-models', 'm_PreloadTable': preload,
                       'm_Container': containers, 'm_MainAsset': {'preloadIndex': 0, 'preloadSize': 0, 'asset': {'m_FileID': 0, 'm_PathID': 0}},
                       'm_RuntimeCompatibility': 1, 'm_AssetBundleName': 'fuka601-original-models',
                       'm_Dependencies': [], 'm_IsStreamedSceneAssetBundle': False}))
        trees = {cid: (effect_node() if cid == -1 else pattern_node()) if cid < 0 else node(cid) for _, cid, _ in objects}
        cab = serialized(objects, trees, script_types)
        packed = bundle(cab)
        (OUT / 'fuka601-models.unity3d').write_bytes(packed)
        check = UnityPy.load(packed)
        if set(check.container) != {name for name, _ in containers}:
            raise ValueError('Native container paths differ after bundle roundtrip')
        for obj in check.objects:
            obj.parse_as_dict()
        result = {'objects': len(objects), 'bundle_bytes': len(packed), 'containers': list(check.container),
                  'shader': {'external': 'original1.9/sharedassets0.assets', 'path_id': 237,
                             'proof': 'Same complete material property key set as original weapon shader; source values preserved',
                             'human_visual_acceptance': 'pending'},
                  'opacity_adapter': 'Original RendererProperty curve0, own single-material renderer, no keyword/children',
                  'opacity_guid_origin': 'New deterministic compatibility GUID; native field hash copied from original MonoScript',
                  'deployment_allowed': False, 'human_acceptance': 'pending'}
        (OUT / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
