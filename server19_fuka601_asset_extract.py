"""Read-only, selected 2.0 fist dependency extraction; never deploys assets."""

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
import copy
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.local-baseline/server19-dev/fuka601-tools/python'))
import UnityPy
from UnityPy.helpers.Tpk import get_typetree_node
from UnityPy.helpers.UnityVersion import UnityVersion
from UnityPy.helpers.TypeTreeHelper import read_typetree, write_typetree
from UnityPy.streams import EndianBinaryReader, EndianBinaryWriter

OUT = ROOT / '.local-baseline/server19-dev/fuka601-recovery-20261015/asset-extraction'
APK = ROOT / '.local-baseline/original-apks/bh3-2.0-original-reference.apk'
SEEDS = ('efbbd14019d69674590a75214ced9520', '58d6ddbf1f216204290b5281f571c44a')


def old_layout(value, kind):
    """Explicit format mappings; no geometry, texture or material-value edits."""
    value = copy.deepcopy(value)
    if kind == 'Avatar':
        def vectors(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in ('t', 's') and isinstance(child, dict) and set(child) == {'x', 'y', 'z'}:
                        # Verified in the original1.9 Fuka Avatar: translation
                        # homogeneous component0, scale homogeneous component1.
                        child['w'] = 0.0 if key == 't' else 1.0
                    vectors(child)
            elif isinstance(item, list):
                for child in item:
                    vectors(child)
        vectors(value)
        # m_AvatarSize describes native constant storage, not serialized bytes.
        # Inspected original Fuka122 nodes:14136; source Fuka130:15032;
        # source fist66:7864. All are472+112*N despite5.6 stream compression.
        # Preserve the actual source native size; expanding serialized t/s to
        # Vector4 must not replace it with the byte-stream length.
        count = len(value['m_Avatar']['m_AvatarSkeleton']['data']['m_Node'])
        if value['m_AvatarSize'] != 472 + 112 * count:
            raise ValueError('Uninspected native Avatar constant layout')
    elif kind == 'Material':
        for key in ('m_EnableInstancingVariants', 'm_DoubleSidedGI', 'disabledShaderPasses'):
            if value.pop(key):
                raise ValueError(f'Active later material feature: {key}')
        for key, pairs in value['m_SavedProperties'].items():
            value['m_SavedProperties'][key] = [({'name': name}, item) for name, item in pairs]
    elif kind == 'Texture2D':
        value['m_ReadAllowed'] = value['m_IsReadable']
    elif kind in ('SkinnedMeshRenderer', 'SpriteRenderer'):
        batch = value.pop('m_StaticBatchInfo')
        if batch != {'firstSubMesh': 0, 'subMeshCount': 0}:
            raise ValueError('Non-empty static batch requires subset conversion')
        value['m_SubsetIndices'] = []
        probes = value.pop('m_LightProbeUsage')
        if probes not in (0, 1):
            raise ValueError('Unsupported light probe mode')
        value['m_UseLightProbes'] = bool(probes)
        volume = value.pop('m_LightProbeVolumeOverride')
        if volume['m_PathID']:
            raise ValueError('Active light probe override')
        if value.pop('m_MotionVectors') != 1:
            raise ValueError('Non-default later motion vector settings')
        if kind == 'SkinnedMeshRenderer' and value.pop('m_SkinnedMotionVectors') is not True:
            raise ValueError('Non-default skinned motion vectors')
        if value.pop('m_SortingLayer') != 0:
            raise ValueError('Active later sorting layer')
        if kind == 'SpriteRenderer':
            if value.pop('m_DrawMode') != 0 or value.pop('m_SpriteTileMode') != 0:
                raise ValueError('Only original simple sprites are supported')
            for key in ('m_Size', 'm_AdaptiveModeThreshold', 'm_WasSpriteAssigned'):
                value.pop(key)
    elif kind == 'Sprite':
        if value.pop('m_Pivot') != {'x': 0.5, 'y': 0.5}:
            raise ValueError('Non-central sprite pivot requires offset conversion')
        render = value['m_RD']
        vd = render.pop('m_VertexData')
        if vd['m_VertexCount'] != 4 or len(vd['m_DataSize']) != 80:
            raise ValueError('Only inspected four-vertex icon layout is supported')
        if vd['m_Channels'][0] != {'stream': 0, 'offset': 0, 'format': 0, 'dimension': 3}:
            raise ValueError('Icon position channel differs')
        render['vertices'] = [{'pos': dict(zip(('x', 'y', 'z'), struct.unpack_from('<3f', vd['m_DataSize'], i * 20)))} for i in range(4)]
        raw = bytes(render.pop('m_IndexBuffer'))
        render['indices'] = list(struct.unpack('<' + 'H' * (len(raw) // 2), raw))
        if len(render.pop('m_SubMeshes')) != 1:
            raise ValueError('Multiple icon submeshes')
        if render.pop('atlasRectOffset') != {'x': -1.0, 'y': -1.0}:
            raise ValueError('Packed atlas icon requires additional mapping')
    return value


def pointers(value):
    if isinstance(value, dict):
        if 'm_FileID' in value and 'm_PathID' in value:
            yield value['m_FileID'], value['m_PathID']
        else:
            for child in value.values():
                yield from pointers(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from pointers(child)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = UnityPy.Environment()
    files, records, queue, seen = {}, [], [], set()
    with zipfile.ZipFile(APK) as archive:
        def load(name):
            if name not in files:
                path = 'assets/bin/Data/' + name
                if path in archive.namelist():
                    raw = archive.read(path)
                else:
                    chunks = []
                    index = 0
                    while f'{path}.split{index}' in archive.namelist():
                        chunks.append(archive.read(f'{path}.split{index}'))
                        index += 1
                    if not chunks:
                        raise KeyError(f'Missing asset and split parts: {name}')
                    raw = b''.join(chunks)
                files[name] = env.load_file(raw, name=name)
            return files[name]

        for name in SEEDS:
            queue.extend((name, pid) for pid in load(name).objects)
        while queue:
            name, pid = queue.pop(0)
            if (name, pid) in seen:
                continue
            seen.add((name, pid))
            row = {'file': name, 'path_id': pid}
            try:
                obj = load(name).objects[pid]
                row['class'] = obj.type.name
                (OUT / f'{name}-{pid}.bin').write_bytes(obj.get_raw_data())
                value = obj.parse_as_dict()
                row['name'] = value.get('m_Name', '')
                # MonoBehaviour fields require a game-specific schema; do not
                # claim their base header is a complete dependency parse.
                row['complete'] = obj.type.name != 'MonoBehaviour'
                # Test actual old-layout serialization only for classes with
                # identical fields. This is not an asset bundle or a deployment.
                if obj.type.name in ('GameObject', 'Transform', 'Mesh', 'Avatar', 'Animator',
                                     'Material', 'Texture2D', 'SkinnedMeshRenderer'):
                    try:
                        projected = old_layout(value, obj.type.name)
                        if obj.type.name == 'GameObject':
                            pairs = []
                            for component in value['m_Component']:
                                pointer = component['component']
                                owner = name if not pointer['m_FileID'] else load(name).externals[pointer['m_FileID'] - 1].name
                                class_id = load(owner).objects[pointer['m_PathID']].class_id
                                pairs.append((class_id, pointer))
                            projected['m_Component'] = pairs
                        node = get_typetree_node(obj.class_id, UnityVersion.from_str('5.3.6p5'))
                        writer = EndianBinaryWriter(endian='<')
                        write_typetree(projected, node, writer)
                        converted = writer.bytes
                        restored = read_typetree(node, EndianBinaryReader(converted, endian='<'),
                                                 byte_size=len(converted))
                        if restored != projected:
                            raise ValueError('Old-layout roundtrip changed source values')
                        (OUT / f'{name}-{pid}.unity53.bin').write_bytes(converted)
                        row['unity53_roundtrip'] = True
                    except Exception as exc:
                        row['conversion_error'] = f'{type(exc).__name__}: {exc}'
                (OUT / f'{name}-{pid}.json').write_text(
                    json.dumps(value, ensure_ascii=False, default=lambda x: {'binary_length': len(x)} if isinstance(x, bytes) else str(x)), encoding='utf-8')
                for file_id, path_id in pointers(value):
                    if not path_id:
                        continue
                    dependency = name if file_id == 0 else load(name).externals[file_id - 1].name
                    queue.append((dependency, path_id))
                if obj.type.name == 'Texture2D':
                    image = obj.parse_as_object().image
                    image.save(OUT / f'{name}-{pid}.png')
                    row['image_size'] = image.size
            except Exception as exc:
                row.update(complete=False, error=f'{type(exc).__name__}: {exc}')
            records.append(row)
    report = {'unitypy': UnityPy.__version__, 'source': str(APK),
              'files': list(files), 'objects': records, 'deployment_allowed': False}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'objects': len(records), 'files': len(files),
                      'incomplete': [r for r in records if not r['complete']],
                      'unity53_roundtrips': sum(r.get('unity53_roundtrip', False) for r in records),
                      'conversion_errors': [r for r in records if 'conversion_error' in r],
                      'textures': [r for r in records if 'image_size' in r]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
