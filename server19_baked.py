"""Missing baked-configuration resource supplier for the normal 1.9 startup.

This adapts statically verified 2.4 resource containers into 1.9 configuration
resource classes. It changes neither player/module creation nor page flow and
does not enable the original DISABLE_NETWORK_DEBUG/FakePacket paths.

The native readers and their schema determine runtime compatibility. Supplying
these bytes does not establish that every 2.4 packed configuration is compatible.
"""

from pathlib import Path
import hashlib
import json
import struct
import zipfile
import analyze19 as a
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / '.local-baseline/server19-dev/baked-fallback'
DEFAULT_DEVICE_ROOT = '/sdcard/bh3-server19-baked/'
META_CODE_BASE = 0xa61de5  # Unused GetFakeLobbyMember body; never invoked as FakePacket.
META_CODE_END = 0xa6253b
LIST_CODE_BASE = 0xa60636  # Unused GetFakeAskAddFriendListRsp body; storage only.
LIST_CODE_END = 0xa6091d
CONTAINER_CODE_END = 0xa648dd  # Preserve the original GachaMainPageContext ctor.


def verify_container_list_schema():
    """Require the actual inspected 1.9 generic declarations before patching."""
    if struct.unpack_from('<II', a.E, 0x34a67c4) != (63040, 0x359c46c):
        raise ValueError('Unexpected original 1.9 type registration')
    result = []
    for owner, field, element in (
        ('MoleMole.Bake.PackedConfigContainer', 'indices', 'MoleMole.Bake.PackedEntry'),
        ('MoleMole.Bake.PackedConfigContainer', 'overrideIndices', 'MoleMole.Bake.PackedOverrideEntry'),
        ('MoleMole.Bake.PackedIndexConfigContainer', 'offsets', 'System.Int32'),
    ):
        native_type = dict(resources.native_fields(owner))[field]
        pointer = struct.unpack_from('<I', a.E, 0x359c46c + native_type * 4)[0]
        data, flags = struct.unpack_from('<II', a.E, pointer)
        if (flags >> 16) & 0xff != 0x15:
            raise ValueError(f'{owner}.{field} is not the expected generic List field')
        definition, inst = struct.unpack_from('<II', a.E, data)
        count, argv = struct.unpack_from('<II', a.E, inst)
        if a.type_name(definition) != 'System.Collections.Generic.List`1' or count != 1:
            raise ValueError(f'{owner}.{field} is not List<T>')
        argument = struct.unpack_from('<I', a.E, argv)[0]
        element_data, element_flags = struct.unpack_from('<II', a.E, argument)
        kind = (element_flags >> 16) & 0xff
        actual = 'System.Int32' if kind == 0x08 else a.type_name(element_data) if kind in (0x11, 0x12) else None
        if actual != element:
            raise ValueError(f'{owner}.{field} has a different original List element type')
        result.append({'owner': owner, 'field': field, 'type': f'List<{element}>', 'native_type_index': native_type})
    return result


class Code:
    def __init__(self, base):
        self.base, self.data, self.strings = base, bytearray(), []

    def emit(self, value):
        self.data.extend(bytes.fromhex(value))

    def call(self, address):
        self.data.extend(b'\xe8' + struct.pack('<i', address - self.base - len(self.data) - 5))

    def branch(self, opcode):
        self.emit(opcode)
        pos = len(self.data)
        self.data.extend(bytes(4))
        return pos

    def bind(self, pos):
        struct.pack_into('<i', self.data, pos, len(self.data) - pos - 4)

    def raw_string(self, value):
        self.emit('8d 83')
        self.strings.append((len(self.data), value))
        self.data.extend(bytes(4))

    def string(self, value):
        self.raw_string(value)
        self.emit('89 04 24')
        self.call(0x29549a0)

    def args(self):
        self.emit('89 44 24 04 c7 04 24 00 00 00 00 c7 44 24 08 00 00 00 00')

    def pic(self):
        self.call(self.base + len(self.data) + 5)
        self.pic_base = self.base + len(self.data)
        self.emit('5b')

    def finish(self):
        for pos, value in self.strings:
            struct.pack_into('<i', self.data, pos, self.base + len(self.data) - self.pic_base)
            self.data.extend(value.encode('utf-8') + b'\0')
        return bytes(self.data)


class MessagePackSpanReader:
    """Inspect token boundaries while retaining every original encoded byte."""
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError('MessagePack token exceeds the source payload')
        start = self.pos
        self.pos += count
        return self.data[start:self.pos]

    def integer(self, size):
        return int.from_bytes(self.take(size), 'big')

    def node(self, depth=0):
        if depth > 64:
            raise ValueError('MessagePack source nesting exceeds the inspected limit')
        start = self.pos
        code = self.integer(1)
        kind, count, children = 'scalar', 0, []
        if code <= 0x7f or code >= 0xe0 or code in (0xc0, 0xc2, 0xc3):
            pass
        elif code in (0xca, 0xcb, 0xcc, 0xcd, 0xce, 0xcf, 0xd0, 0xd1, 0xd2, 0xd3):
            self.take({0xca: 4, 0xcb: 8, 0xcc: 1, 0xcd: 2, 0xce: 4,
                       0xcf: 8, 0xd0: 1, 0xd1: 2, 0xd2: 4, 0xd3: 8}[code])
        elif 0x90 <= code <= 0x9f or code in (0xdc, 0xdd):
            kind = 'array'
            count = code & 15 if code <= 0x9f else self.integer(2 if code == 0xdc else 4)
        elif 0x80 <= code <= 0x8f or code in (0xde, 0xdf):
            kind = 'map'
            count = code & 15 if code <= 0x8f else self.integer(2 if code == 0xde else 4)
        elif 0xa0 <= code <= 0xbf or code in (0xd9, 0xda, 0xdb, 0xc4, 0xc5, 0xc6):
            size = code & 31 if code <= 0xbf else self.integer({0xd9: 1, 0xda: 2, 0xdb: 4, 0xc4: 1, 0xc5: 2, 0xc6: 4}[code])
            self.take(size)
        elif code in (0xc7, 0xc8, 0xc9):
            self.take(self.integer({0xc7: 1, 0xc8: 2, 0xc9: 4}[code]) + 1)
        elif code in (0xd4, 0xd5, 0xd6, 0xd7, 0xd8):
            self.take({0xd4: 1, 0xd5: 2, 0xd6: 4, 0xd7: 8, 0xd8: 16}[code] + 1)
        else:
            raise ValueError(f'Unsupported MessagePack code {code:#x} at {start}')
        if count > len(self.data):
            raise ValueError('MessagePack container count exceeds source size')
        if kind in ('array', 'map'):
            children = [self.node(depth + 1) for _ in range(count * (2 if kind == 'map' else 1))]
        return {'start': start, 'end': self.pos, 'code': code, 'kind': kind, 'count': count, 'children': children}


def project_baked_misc(package, packed):
    """Project the verified 2.4 positional root onto original 1.9 field order."""
    from server19_metadata_export import SourceTypedDecoder, fields, type_info
    source = SourceTypedDecoder(package)
    name = 'MoleMole.Config.ConfigInLevelMiscData'
    original_index = next(i for i in range(len(a.T)) if a.type_name(i) == name)
    target_fields = fields(original_index)
    source_fields = source.fields(source.names[name])
    if len(target_fields) != 42 or len(source_fields) != 58:
        raise ValueError('BakedMisc root differs from the inspected 42/58 field declarations')
    names = [field for field, _ in source_fields]
    if len(set(names)) != len(names) or any(field not in names for field, _ in target_fields):
        raise ValueError('BakedMisc source has duplicate or missing original field names')

    def signature(pointer, original):
        if original:
            info = type_info(pointer)
            data, kind = info['data'], info['kind']
        else:
            data, flags = struct.unpack_from('<II', source.binary, pointer)
            kind = (flags >> 16) & 0xff
        if kind in (0x11, 0x12):
            return a.type_name(data) if original else source.name(data)
        if kind == 0x15:
            binary = a.E if original else source.binary
            definition, inst = struct.unpack_from('<II', binary, data)
            count, argv = struct.unpack_from('<II', binary, inst)
            class_name = a.type_name(definition) if original else source.name(definition)
            return class_name + '[' + ','.join(signature(struct.unpack_from('<I', binary, argv + index * 4)[0], original) for index in range(count)) + ']'
        if kind == 0x1d:
            return signature(data, original) + '[]'
        return f'primitive:{kind:#x}'

    reader = MessagePackSpanReader(packed)
    root = reader.node()
    if reader.pos != len(packed) or root['kind'] != 'array' or root['count'] != len(source_fields):
        raise ValueError('BakedMisc source root does not match the exact inspected object boundary')
    result = {'target_type': name, 'source_fields': len(source_fields), 'target_fields': len(target_fields),
              'source_packed_bytes': len(packed), 'source_packed_sha256': hashlib.sha256(packed).hexdigest(),
              'mapping': [], 'excluded_source_fields': [], 'nested_schema_checks': [],
              'runtime_compatibility': 'not yet verified after positional projection'}
    output = b'\xdc' + struct.pack('>H', len(target_fields))
    for target_index, (field, pointer) in enumerate(target_fields):
        source_index = names.index(field)
        source_pointer = source_fields[source_index][1]
        if signature(pointer, True) != signature(source_pointer, False):
            raise ValueError(f'BakedMisc field type mismatch: {field}')
        node = root['children'][source_index]
        raw = packed[node['start']:node['end']]
        result['mapping'].append({'target_index': target_index, 'target_field': field,
                                  'source_index': source_index, 'source_field': names[source_index],
                                  'type_signature': signature(pointer, True),
                                  'source_byte_span': [node['start'], node['end']], 'bytes': len(raw),
                                  'sha256': hashlib.sha256(raw).hexdigest(), 'output_byte_span': [len(output), len(output) + len(raw)]})
        output += raw
    target_names = {field for field, _ in target_fields}
    for index, (field, _) in enumerate(source_fields):
        if field not in target_names:
            node = root['children'][index]
            raw = packed[node['start']:node['end']]
            result['excluded_source_fields'].append({'source_index': index, 'source_field': field,
                                                    'source_byte_span': [node['start'], node['end']],
                                                    'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    for child_name in ('MoleMole.Config.ConfigInLevelControlPrefabPath', 'OverrideEntry', 'MoleMole.Config.ConfigEntityAttackEffect'):
        original_child = next(i for i in range(len(a.T)) if a.type_name(i) == child_name)
        old = [(field, signature(pointer, True)) for field, pointer in fields(original_child)]
        new = [(field, signature(pointer, False)) for field, pointer in source.fields(source.names[child_name])]
        if old != new:
            raise ValueError(f'BakedMisc referenced child schema differs: {child_name}')
        result['nested_schema_checks'].append({'type': child_name, 'field_order_and_type_signatures_equal': True,
                                              'fields': [field for field, _ in old]})
    prefab = root['children'][names.index('InLevelControlPrefabPath')]
    if prefab['code'] != 0xc0 and (prefab['kind'] != 'array' or prefab['count'] != 8):
        raise ValueError('BakedMisc prefab-path child does not have the inspected eight fields')
    animation = root['children'][names.index('AnimationOverrideMaps')]
    override_nodes = 0
    if animation['code'] != 0xc0:
        if animation['kind'] != 'map':
            raise ValueError('BakedMisc AnimationOverrideMaps is not a dictionary')
        for dictionary in animation['children'][1::2]:
            if dictionary['kind'] != 'map':
                raise ValueError('BakedMisc animation override value is not a dictionary')
            for entry in dictionary['children'][1::2]:
                if entry['code'] != 0xc0 and (entry['kind'] != 'array' or entry['count'] != 2):
                    raise ValueError('BakedMisc OverrideEntry does not have the inspected two fields')
                override_nodes += 1
    result['nested_payload_checks'] = {'prefab_path_fields': 8, 'animation_override_entries': override_nodes,
                                       'indexed_attack_effects': 'declared eight-field schema equal; referenced packed resource payload validation pending',
                                       'string_map_and_enum_values': 'original encoded nodes retained; semantic reference validation pending'}
    result.update(output_packed_bytes=len(output), output_packed_sha256=hashlib.sha256(output).hexdigest(),
                  packed_hash_policy='Retain source packedHash. Original PackedMiscLookUp constructor reads only indices and packedBytes.')
    return output, result


def project_baked_avatar(package, entries, overrides, packed):
    """Project proven root/nested layouts, preserving retained child bytes."""
    from server19_metadata_export import SourceTypedDecoder, fields, type_info, type_pointer
    source = SourceTypedDecoder(package)
    original_names = {a.type_name(index): index for index in range(len(a.T))}
    root_name = 'MoleMole.Config.ConfigAvatar'

    def info(pointer, original):
        if original:
            return type_info(pointer)
        data, flags = struct.unpack_from('<II', source.binary, pointer)
        return {'data': data, 'kind': (flags >> 16) & 0xff, 'attributes': flags & 0xffff}

    def type_name(index, original):
        return a.type_name(index) if original else source.name(index)

    def signature(pointer, original):
        value = info(pointer, original)
        data, kind = value['data'], value['kind']
        if kind in (0x11, 0x12):
            return type_name(data, original)
        if kind == 0x15:
            binary = a.E if original else source.binary
            definition, inst = struct.unpack_from('<II', binary, data)
            count, argv = struct.unpack_from('<II', binary, inst)
            return type_name(definition, original) + '[' + ','.join(
                signature(struct.unpack_from('<I', binary, argv + index * 4)[0], original)
                for index in range(count)) + ']'
        if kind == 0x1d:
            return signature(data, original) + '[]'
        return f'primitive:{kind:#x}'

    def parent(index, original):
        native_type = (a.T if original else source.types)[index][6]
        if native_type == 0xffffffff:
            return None
        pointer = (type_pointer(native_type) if original else
                   struct.unpack_from('<I', source.binary, 0x409d890 + native_type * 4)[0])
        value = info(pointer, original)
        return value['data'] if value['kind'] in (0x11, 0x12) else None

    def members(index, original):
        declared = fields(index) if original else source.fields(index)
        result = [(name, pointer) for name, pointer in declared if not info(pointer, original)['attributes'] & 0x80]
        ancestor = parent(index, original)
        if ancestor is not None:
            result += members(ancestor, original)
        return result

    target_fields = members(original_names[root_name], True)
    source_fields = members(source.names[root_name], False)
    source_names = [name for name, _ in source_fields]
    retained = list(range(20)) + list(range(21, 26))
    if (len(target_fields) != 25 or len(source_fields) != 27 or
            source_names[20] != 'FPSSetting' or source_names[26] != 'ApplyRootMotionAnimationList' or
            [source_fields[index][0] for index in retained] != [name for name, _ in target_fields]):
        raise ValueError('ConfigAvatar differs from the inspected source27/original25 root order')
    for target, source_index in zip(target_fields, retained):
        if signature(target[1], True) != signature(source_fields[source_index][1], False):
            raise ValueError(f'ConfigAvatar retained field type differs: {target[0]}')

    # Recursively audit declarations, including inherited fields and generic
    # arguments. Equal declarations do not prove custom/poly formatter tags.
    checks, checked = [], set()

    def inspect_type(pointer, original):
        value = info(pointer, original)
        data, kind = value['data'], value['kind']
        if kind == 0x1d:
            inspect_type(data, original)
        elif kind == 0x15:
            binary = a.E if original else source.binary
            definition, inst = struct.unpack_from('<II', binary, data)
            count, argv = struct.unpack_from('<II', binary, inst)
            for index in range(count):
                inspect_type(struct.unpack_from('<I', binary, argv + index * 4)[0], original)
            inspect_class(type_name(definition, original))
        elif kind in (0x11, 0x12):
            inspect_class(type_name(data, original))

    def inspect_class(name):
        if not name.startswith('MoleMole.') or name in checked:
            return
        checked.add(name)
        if name not in original_names or name not in source.names:
            raise ValueError(f'ConfigAvatar referenced declaration missing: {name}')
        old = members(original_names[name], True)
        new = members(source.names[name], False)
        if name == root_name:
            new = [new[index] for index in retained]
        elif name == 'MoleMole.Config.ConfigAnimatorEntity':
            new = [(field, pointer) for field, pointer in new if field != 'ApplyRootMotionAnimationList']
        elif name == 'MoleMole.Config.TargetLockedAnimatedColliderDetect':
            if len(old) != 13 or len(new) != 14 or new[12][0] != 'FollowOwnerTimeScale' or new[13][0] != 'Scale':
                raise ValueError('TargetLockedAnimatedColliderDetect differs from the inspected nested14/original13 layout')
            new = new[:12] + new[13:]
        if [(field, signature(pointer, True)) for field, pointer in old] != [(field, signature(pointer, False)) for field, pointer in new]:
            raise ValueError(f'ConfigAvatar referenced declaration differs: {name}')
        checks.append({'type': name, 'fields': [field for field, _ in old],
                       'field_order_and_type_signatures_equal_after_explicit_projection': True,
                       'excluded_source_fields': (['FollowOwnerTimeScale'] if name == 'MoleMole.Config.TargetLockedAnimatedColliderDetect' else
                                                  ['FPSSetting', 'ApplyRootMotionAnimationList'] if name == root_name else
                                                  ['ApplyRootMotionAnimationList'] if name == 'MoleMole.Config.ConfigAnimatorEntity' else [])})
        for _, pointer in old:
            inspect_type(pointer, True)
        ancestor = parent(original_names[name], True)
        if ancestor is not None:
            inspect_class(type_name(ancestor, True))

    inspect_class(root_name)
    reader = MessagePackSpanReader(packed)
    roots = []
    while reader.pos < len(packed):
        node = reader.node()
        if node['kind'] != 'array' or node['count'] != 27:
            raise ValueError('ConfigAvatar source stream contains a non-27-field root')
        roots.append(node)
    if reader.pos != len(packed) or len(entries) % 8 or len(overrides) % 12:
        raise ValueError('ConfigAvatar source packed/index boundaries differ')
    entry_values = list(struct.iter_unpack('<II', entries))
    override_values = list(struct.iter_unpack('<III', overrides))
    starts = {root['start'] for root in roots}
    referenced = {offset for _, offset in entry_values} | {offset for _, _, offset in override_values}
    if len(roots) != 64 or len(entry_values) != 64 or override_values or referenced != starts:
        raise ValueError('ConfigAvatar differs from the inspected 64 roots/64 indices/zero overrides')

    poly = {
        'AvatarAttackTargetSelect': {1: 'SelectEnemyByEllipse', 2: 'SelectMonsterAndPropByEllipse', 3: 'SelectNearestEnemyV1'},
        'ConfigAvatarAttackTargetSelectV2': {1: 'ConfigAvatarTargettingV2', 2: 'ConfigAvatarTargettingV3', 3: 'ConfigDistanceWeightedTargetting', 4: 'ConfigOriginalTargetting'},
        'ConfigAvatarCameraAction': {1: 'PlayAvatarCameraAnimation', 2: 'SetCameraDistance', 3: 'SuddenRecover'},
        'ConfigAvatarCameraEffect': {1: 'PlayCameraRadialBlur'},
        'IMixinArgument': {1: 'GrenadesMixinArgument', 2: 'HitExplodeTracingBulletMixinArgument', 3: 'MonsterSuicideAttackMixinArgument', 4: 'MonsterSummonMixinArgument'},
        'ConfigEntityAttackPattern': {1: 'AnimatedColliderDetect', 2: 'CylinderCollisionDetect',
                                    3: 'CylinderCollisionDetectTargetLocked', 4: 'FanCollisionDetect',
                                    5: 'FanCollisionWithHeightDetect', 6: 'HitscanDetect',
                                    7: 'RectCollisionDetect', 8: 'RectCollisionWithHeightDetect',
                                    9: 'StaticHitBoxDetect', 10: 'TargetLockedAnimatedColliderDetect'},
    }
    poly = {'MoleMole.Config.' + name: {tag: 'MoleMole.Config.' + subtype for tag, subtype in tags.items()}
            for name, tags in poly.items()}
    poly_checks, custom_shapes = {}, {}
    indexed_references, indexed_values = {}, {}
    nested_edits = []

    def scalar_integer(node):
        code = node['code']
        if code <= 0x7f:
            return code
        if code >= 0xe0:
            return code - 256
        if code in (0xcc, 0xcd, 0xce, 0xcf, 0xd0, 0xd1, 0xd2, 0xd3):
            return int.from_bytes(packed[node['start'] + 1:node['end']], 'big', signed=code >= 0xd0)
        raise ValueError('ConfigAvatar union discriminator is not an integer')

    def note_custom(name, node, path, reason):
        key = (name, node['kind'], node['count'], reason)
        audit = custom_shapes.setdefault(key, {'type': name, 'kind': node['kind'], 'count': node['count'],
                                               'reason': reason, 'occurrences': 0,
                                               'example_path': path, 'example_source_byte_span': [node['start'], node['end']]})
        audit['occurrences'] += 1

    def scan_class(name, node, path):
        if node['code'] == 0xc0:
            return
        if name in poly:
            if node['kind'] != 'array' or node['count'] != 2:
                raise ValueError(f'ConfigAvatar union node does not have tag/payload shape: {name}')
            tag = scalar_integer(node['children'][0])
            if tag not in poly[name]:
                raise ValueError(f'ConfigAvatar source union tag unsupported by original1.9: {name}/{tag}')
            subtype = poly[name][tag]
            inspect_class(subtype)
            payload = node['children'][1]
            audit = poly_checks.setdefault((name, tag), {'type': name, 'tag': tag, 'subtype': subtype,
                                                       'source_original_tag_mapping_equal': True, 'occurrences': 0,
                                                       'payload_shapes': {}, 'example_path': path,
                                                       'example_source_byte_span': [node['start'], node['end']]})
            audit['occurrences'] += 1
            shape = f"{payload['kind']}:{payload['count']}"
            audit['payload_shapes'][shape] = audit['payload_shapes'].get(shape, 0) + 1
            scan_class(subtype, payload, path + '<' + subtype + '>')
            return
        if name == 'MoleMole.Config.TargetLockedAnimatedColliderDetect':
            field_values = members(source.names[name], False)
            if node['kind'] != 'array' or node['count'] != 14:
                raise ValueError('TargetLockedAnimatedColliderDetect source payload is not array14')
            keep = list(range(12)) + [13]
            encoded, retained_fields = bytearray(b'\x9d'), []
            for target_index, source_index in enumerate(keep):
                child = node['children'][source_index]
                raw_child = packed[child['start']:child['end']]
                retained_fields.append({'target_index': target_index, 'source_index': source_index,
                                        'field': field_values[source_index][0],
                                        'source_byte_span': [child['start'], child['end']],
                                        'output_relative_byte_span': [len(encoded), len(encoded) + len(raw_child)],
                                        'bytes': len(raw_child), 'sha256': hashlib.sha256(raw_child).hexdigest()})
                encoded.extend(raw_child)
                scan(field_values[source_index][1], child, path + '.' + field_values[source_index][0])
            excluded = node['children'][12]
            raw_excluded = packed[excluded['start']:excluded['end']]
            audit = {'type': name, 'source_path': path, 'source_fields': 14, 'target_fields': 13,
                     'source_byte_span': [node['start'], node['end']],
                     'source_sha256': hashlib.sha256(packed[node['start']:node['end']]).hexdigest(),
                     'output_bytes': len(encoded), 'output_sha256': hashlib.sha256(encoded).hexdigest(),
                     'mapping': retained_fields,
                     'excluded_source_field': {'source_index': 12, 'field': 'FollowOwnerTimeScale',
                                               'source_byte_span': [excluded['start'], excluded['end']],
                                               'bytes': len(raw_excluded), 'sha256': hashlib.sha256(raw_excluded).hexdigest()},
                     'native_formatter_evidence': 'Original58667@75a4ab consumes12 own fields then Scale ReadSingle@75ad96, no trailing skip; source70425@24183f1 reads NoTargetDistance@2418c30, new FollowOwnerTimeScale Boolean@2418ccf, then Scale@2418d66'}
            nested_edits.append((node['start'], node['end'], bytes(encoded), audit))
            return
        if name == 'MoleMole.Config.AnimatorTransitionSet':
            if node['kind'] != 'array':
                raise ValueError('AnimatorTransitionSet custom array shape differs')
            for index, child in enumerate(node['children']):
                scan_class('MoleMole.Config.AnimatorTransitionEntry', child, path + f'[{index}]')
            return
        field_values = members(source.names[name], False)
        if any(field == 'value__' for field, _ in field_values):
            return
        if name in ('MoleMole.Config.ConfigEntityAttackEffect', 'MoleMole.Config.ConfigEntityAttackProperty',
                    'MoleMole.Config.ConfigEntityCameraShake', 'MoleMole.Config.HitExplodeTracingBulletMixinArgument') and node['kind'] == 'scalar':
            reference = scalar_integer(node)
            indexed_references[name] = indexed_references.get(name, 0) + 1
            indexed_values.setdefault(name, set()).add(reference)
            return
        if node['kind'] != 'array' or node['count'] != len(field_values):
            note_custom(name, node, path, 'Actual custom/generated formatter field order must be audited; declaration count alone is not a payload rule')
            return
        for (field, pointer), child in zip(field_values, node['children']):
            scan(pointer, child, path + '.' + field)

    def scan(pointer, node, path):
        if node['code'] == 0xc0:
            return
        value = info(pointer, False)
        data, kind = value['data'], value['kind']
        if kind == 0x1d:
            if node['kind'] != 'array':
                raise ValueError(f'ConfigAvatar declared array shape differs: {path}')
            for index, child in enumerate(node['children']):
                scan(data, child, path + f'[{index}]')
        elif kind == 0x15:
            definition, inst = struct.unpack_from('<II', source.binary, data)
            count, argv = struct.unpack_from('<II', source.binary, inst)
            arguments = [struct.unpack_from('<I', source.binary, argv + index * 4)[0] for index in range(count)]
            name = source.name(definition)
            if name == 'System.Collections.Generic.Dictionary`2' and len(arguments) == 2:
                if node['kind'] != 'map':
                    raise ValueError(f'ConfigAvatar declared dictionary shape differs: {path}')
                for index, child in enumerate(node['children']):
                    scan(arguments[index % 2], child, path + f'[{index // 2}]')
            elif name == 'System.Collections.Generic.List`1' and len(arguments) == 1:
                if node['kind'] != 'array':
                    raise ValueError(f'ConfigAvatar declared List shape differs: {path}')
                for index, child in enumerate(node['children']):
                    scan(arguments[0], child, path + f'[{index}]')
            elif name == 'System.Nullable`1' and len(arguments) == 1:
                scan(arguments[0], node, path)
            else:
                note_custom(name, node, path, 'Custom generic representation is retained; runtime/reference validation pending')
        elif kind in (0x11, 0x12):
            scan_class(source.name(data), node, path)

    for ordinal, root in enumerate(roots):
        for index in retained:
            field, pointer = source_fields[index]
            scan(pointer, root['children'][index], f'root[{ordinal}].' + field)

    indexed_paths = {
        'MoleMole.Config.ConfigEntityAttackEffect': '_baked/bakedconfigentityattackeffect',
        'MoleMole.Config.ConfigEntityAttackProperty': '_baked/bakedconfigentityattackproperty',
        'MoleMole.Config.ConfigEntityCameraShake': '_baked/bakedconfigentitycamerashake',
        'MoleMole.Config.HitExplodeTracingBulletMixinArgument': '_baked/bakedhitexplodetracingbulletmixinargument',
    }
    source_paths = {record['path']: record for record in resources.resource_map(Path(package.filename))}
    indexed_checks = []
    for name, values in indexed_values.items():
        record = source_paths[indexed_paths[name]]
        obj, raw = resources.object_bytes(package, record)
        if obj['class'] != 114:
            raise ValueError('ConfigAvatar indexed dependency is not the inspected ScriptableObject')
        cursor = resources.Reader(raw, 28)
        cursor.string()
        count = cursor.read('I')
        if count > len(raw) // 4:
            raise ValueError('Invalid indexed dependency offset count')
        index_offsets = list(struct.unpack_from('<' + 'i' * count, raw, cursor.pos))
        cursor.pos += count * 4
        size = cursor.read('I')
        if cursor.pos + size > len(raw):
            raise ValueError('Indexed dependency packed bytes exceed source asset')
        resource_bytes = raw[cursor.pos:cursor.pos + size]
        cursor.pos += size
        cursor.align()
        packed_hash = cursor.read('I')
        if cursor.pos != len(raw):
            raise ValueError('Indexed dependency does not consume the exact source boundary')
        resource_reader = MessagePackSpanReader(resource_bytes)
        boundaries = {}
        while resource_reader.pos < len(resource_bytes):
            child = resource_reader.node()
            boundaries[child['start']] = child
        expected_fields = members(source.names[name], False)
        original_fields = members(original_names[name], True)
        if [(field, signature(pointer, False)) for field, pointer in expected_fields] != [(field, signature(pointer, True)) for field, pointer in original_fields]:
            raise ValueError('Indexed dependency original/source field schema differs')
        selected = []
        for index in sorted(values):
            if not 0 <= index < count or index_offsets[index] not in boundaries:
                raise ValueError(f'ConfigAvatar indexed reference has no complete source root: {name}/{index}')
            child = boundaries[index_offsets[index]]
            if child['kind'] != 'array' or child['count'] != len(expected_fields):
                raise ValueError('Indexed dependency payload does not match the original field count')
            selected.append({'index': index, 'source_offset': index_offsets[index],
                             'source_byte_span': [child['start'], child['end']],
                             'source_node_sha256': hashlib.sha256(resource_bytes[child['start']:child['end']]).hexdigest(),
                             'field_count': child['count']})
        indexed_checks.append({'type': name, 'resource': dict(record), 'offset_count': count,
                               'source_asset_sha256': hashlib.sha256(raw).hexdigest(), 'packed_hash': packed_hash,
                               'source_packed_sha256': hashlib.sha256(resource_bytes).hexdigest(),
                               'fields': [field for field, _ in expected_fields], 'selected_roots': selected,
                               'complete_source_token_boundaries_verified': True,
                               'selected_offsets_in_range_and_array_field_counts_equal': True,
                               'lookup_scope': 'The retained integer addresses the matching source offsets[index] root. Original IndexedConfig.Get passes it unchanged to its mapping delegate; exact LazyMapping delegate implementation and runtime reference semantics remain separately unverified',
                               'source_payload_unchanged': True,
                               'semantic_reference_and_gameplay_runtime_compatibility': 'Not yet verified'})

    projection = {'target_type': root_name, 'source_fields': 27, 'target_fields': 25,
                  'retained_source_indices': retained, 'excluded_source_indices': [20, 26],
                  'source_packed_bytes': len(packed), 'source_packed_sha256': hashlib.sha256(packed).hexdigest(),
                  'original_formatter_evidence': 'ConfigAvatarFormatter.Deserialize57435@155a176 ignores ReadArrayHeader count and writes22 declared fields, then three inherited fields at155bb19/155bc2a/155bd48; it has no trailing skip',
                  'nested_declaration_checks': checks, 'roots': [], 'indices': [], 'override_indices': [],
                  'actual_polymorphic_nodes': list(poly_checks.values()),
                  'polymorphic_mapping_evidence': 'Original/source native Poly Deserialize mapping equal: methods58723/70489,58755/70521,58759/70525,58763/70529,58783/70565,58771/70537; declaration equality alone is not used to infer tags',
                  'custom_payload_audit_pending': list(custom_shapes.values()),
                  'indexed_reference_counts': indexed_references,
                  'indexed_reference_values': {name: sorted(values) for name, values in indexed_values.items()},
                  'indexed_resource_checks': indexed_checks,
                  'nested_schema_projections': [],
                  'source_indices_sha256': hashlib.sha256(entries).hexdigest(),
                  'source_override_indices_sha256': hashlib.sha256(overrides).hexdigest(),
                  'packed_hash_policy': 'Keep source packedHash as provenance only. Original shared PackedConfigLookup ctor@1b36d5d stores it without recalculation/comparison; projected payload has its own SHA256',
                  'runtime_compatibility': 'Not yet verified. Root layout is projected; custom/poly tags and referenced resources are preserved, not presumed fully compatible'}
    output, offsets = bytearray(), {}
    for ordinal, root in enumerate(roots):
        offsets[root['start']] = len(output)
        old_start, new_start = root['start'], len(output)
        output.extend(b'\xdc\x00\x19')
        audit = {'root_ordinal': ordinal, 'source_byte_span': [old_start, root['end']],
                 'source_sha256': hashlib.sha256(packed[old_start:root['end']]).hexdigest(),
                 'mapping': [], 'excluded_source_fields': []}
        for target_index, source_index in enumerate(retained):
            node = root['children'][source_index]
            raw_node = packed[node['start']:node['end']]
            # Only the explicitly audited nested subtype is rewritten. Every
            # retained terminal child in that subtype keeps its encoded bytes.
            edits = sorted((edit for edit in nested_edits if node['start'] <= edit[0] and edit[1] <= node['end']), key=lambda edit: edit[0])
            rewritten, cursor = bytearray(), node['start']
            for start, end, encoded, nested_audit in edits:
                if start < cursor:
                    raise ValueError('ConfigAvatar nested projection ranges overlap')
                rewritten.extend(packed[cursor:start])
                nested_start = len(output) + len(rewritten)
                nested_audit['output_byte_span'] = [nested_start, nested_start + len(encoded)]
                projection['nested_schema_projections'].append(nested_audit)
                rewritten.extend(encoded)
                cursor = end
            rewritten.extend(packed[cursor:node['end']])
            output_node = bytes(rewritten)
            audit['mapping'].append({'target_index': target_index, 'source_index': source_index,
                                     'field': target_fields[target_index][0],
                                     'type_signature': signature(target_fields[target_index][1], True),
                                     'source_byte_span': [node['start'], node['end']],
                                     'output_byte_span': [len(output), len(output) + len(output_node)],
                                     'source_bytes': len(raw_node), 'output_bytes': len(output_node),
                                     'source_sha256': hashlib.sha256(raw_node).hexdigest(),
                                     'output_sha256': hashlib.sha256(output_node).hexdigest(),
                                     'byte_for_byte_equal': not edits,
                                     'explicit_nested_projections': len(edits)})
            output.extend(output_node)
        for source_index in (20, 26):
            node = root['children'][source_index]
            raw_node = packed[node['start']:node['end']]
            audit['excluded_source_fields'].append({'source_index': source_index,
                                                    'field': source_fields[source_index][0],
                                                    'source_byte_span': [node['start'], node['end']],
                                                    'bytes': len(raw_node), 'sha256': hashlib.sha256(raw_node).hexdigest()})
        audit.update(output_byte_span=[new_start, len(output)],
                     output_sha256=hashlib.sha256(output[new_start:]).hexdigest())
        projection['roots'].append(audit)
    new_entries = b''
    for index, (key, offset) in enumerate(entry_values):
        new_entries += struct.pack('<II', key, offsets[offset])
        projection['indices'].append({'source_index': index, 'key': key,
                                      'source_offset': offset, 'output_offset': offsets[offset],
                                      'source_entry_sha256': hashlib.sha256(entries[index * 8:(index + 1) * 8]).hexdigest()})
    new_overrides = b''
    for index, (key, override_key, offset) in enumerate(override_values):
        new_overrides += struct.pack('<III', key, override_key, offsets[offset])
        projection['override_indices'].append({'source_index': index, 'key': key, 'override_key': override_key,
                                               'source_offset': offset, 'output_offset': offsets[offset]})
    # A second parse proves the rewritten offset map selects exactly all roots.
    output_reader = MessagePackSpanReader(output)
    new_starts = []
    while output_reader.pos < len(output):
        node = output_reader.node()
        if node['kind'] != 'array' or node['count'] != 25:
            raise ValueError('ConfigAvatar projected root boundary differs')
        new_starts.append(node['start'])
    if set(new_starts) != set(offsets.values()) or output_reader.pos != len(output):
        raise ValueError('ConfigAvatar projected offsets do not cover the entire output')
    projection.update(output_packed_bytes=len(output), output_packed_sha256=hashlib.sha256(output).hexdigest(),
                      output_indices_sha256=hashlib.sha256(new_entries).hexdigest(),
                      complete_output_root_boundaries_verified=True,
                      unchanged_root_field_nodes_byte_for_byte_equal=True,
                      nested_retained_child_nodes_byte_for_byte_equal=True,
                      nested_projection_count=len(nested_edits), keys_and_entry_order_preserved=True)
    return new_entries, new_overrides, bytes(output), projection


def extract(output=DEFAULT_OUTPUT, apk24=resources.DEFAULT24):
    output = Path(output)
    baked = output / '_baked'
    baked.mkdir(parents=True, exist_ok=True)
    manifest = {'source': str(apk24), 'runtime_compatibility': 'not yet verified', 'resources': []}
    with zipfile.ZipFile(apk24) as package:
        for rec in resources.resource_map(apk24):
            if not rec['path'].startswith('_baked/'):
                continue
            obj, raw = resources.object_bytes(package, rec)
            if obj['class'] != 114:
                raise ValueError('Expected a baked ScriptableObject')
            # Unity 5.6 MonoBehaviour header: GameObject ptr, enabled + padding,
            # MonoScript ptr, then aligned object name.
            r = resources.Reader(raw, 28)
            name = r.string()
            if rec['path'] == '_baked/stringmap':
                count = r.read('i')
                values = [r.string() for _ in range(count)]
                packed_hash = r.read('I')
                if any('\x1f' in value for value in values):
                    raise ValueError('String-map delimiter collision')
                payload = '\x1f'.join(values).encode('utf-8')
                filename = 'stringmap.txt'
                counts = [count]
            else:
                indexed = any(word in rec['path'] for word in
                              ('configentity', 'grenadesmixin', 'hitexplodetracing'))
                arrays = []
                for element_size in ([4, 1] if indexed else [8, 12, 1]):
                    count = r.read('I')
                    size = count * element_size
                    if r.pos + size > len(raw):
                        raise ValueError('Invalid baked array size')
                    arrays.append((count, raw[r.pos:r.pos + size]))
                    r.pos += size
                    r.align()
                packed_hash = r.read('I')
                projection = None
                if rec['path'] == '_baked/bakedmiscdatacombined':
                    if indexed or arrays[0][0] != 1 or arrays[1][0] != 0 or struct.unpack_from('<I', arrays[0][1], 4)[0] != 0:
                        raise ValueError('BakedMisc is not the inspected single root at offset zero')
                    projected, projection = project_baked_misc(package, arrays[-1][1])
                    arrays[-1] = (len(projected), projected)
                elif rec['path'] == '_baked/bakedavatardata':
                    if indexed:
                        raise ValueError('ConfigAvatar must use the inspected non-indexed container')
                    entries, overrides, projected, projection = project_baked_avatar(
                        package, arrays[0][1], arrays[1][1], arrays[2][1])
                    arrays = [(len(entries) // 8, entries), (len(overrides) // 12, overrides), (len(projected), projected)]
                payload = struct.pack('<II', int(indexed), packed_hash)
                payload += b''.join(struct.pack('<I', count) + data for count, data in arrays)
                filename = rec['path'].rsplit('/', 1)[-1]
                counts = [count for count, _ in arrays]
            if r.pos != len(raw):
                raise ValueError(f'Baked schema size mismatch: {rec["path"]}')
            (baked / filename).write_bytes(payload)
            manifest['resources'].append(dict(rec, name=name, counts=counts, packed_hash=packed_hash,
                                               source_sha256=hashlib.sha256(raw).hexdigest(),
                                               output_sha256=hashlib.sha256(payload).hexdigest(),
                                               output_file='_baked/' + filename))
            if rec['path'] in ('_baked/bakedmiscdatacombined', '_baked/bakedavatardata'):
                manifest['resources'][-1]['schema_projection'] = projection
        rec = next(r for r in resources.resource_map(apk24) if r['path'] == 'common/metaconfig')
        obj, raw = resources.object_bytes(package, rec)
        if obj['class'] != 114:
            raise ValueError('Expected ConfigMetaConfig ScriptableObject')
        r = resources.Reader(raw, 28)
        name = r.string()
        fields = [name for name, field_type in resources.native_fields('MoleMole.ConfigMetaConfig') if field_type == 27835]
        arrays = {name: [r.string() for _ in range(r.read('i'))] for name in fields}
        if r.pos != len(raw) or any(not values for values in arrays.values()):
            raise ValueError('Unexpected ConfigMetaConfig serialization')
        if any('\x1f' in value or '\x1e' in value for values in arrays.values() for value in values):
            raise ValueError('MetaConfig delimiter collision')
        # These groups name concrete Resources assets. Retain paths present in
        # the original 1.9 source, rather than referring to later avatar assets.
        # Registry paths needed by original readers and scene names retain the
        # source values; they require their own resource suppliers when absent.
        original_paths = {rec['path'].lower() for rec in resources.resource_map(resources.DEFAULT19)}
        path_groups = {'effectPatternPathes', 'stageEntryPathes', 'auxEntryPathes',
                       'dynamicObjectRegistryPathes', 'weatherEntryPathes',
                       'animatorEventPatternPathes', 'touchPatternPathes'}
        excluded = {}
        for field in path_groups:
            excluded[field] = [value for value in arrays[field] if value.lower() not in original_paths]
            arrays[field] = [value for value in arrays[field] if value.lower() in original_paths]
            if not arrays[field]:
                raise ValueError(f'No verified 1.9 Resources paths remain for {field}')
        payload = '\x1e'.join('\x1f'.join(values) for values in arrays.values()).encode('utf-8')
        (output / 'metaconfig.txt').write_bytes(payload)
        (output / 'metaconfig.json').write_text(json.dumps(arrays, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        manifest['metaconfig'] = dict(rec, name=name, field_names=fields,
                                     counts={name: len(values) for name, values in arrays.items()},
                                     excluded_paths=excluded,
                                     filter_basis='original 1.9 ResourceManager exact path presence for seven concrete asset groups',
                                     source_sha256=hashlib.sha256(raw).hexdigest(),
                                     output_sha256=hashlib.sha256(payload).hexdigest())
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def string_map_code(device_root, packed_hash):
    c = Code(0xa64000)
    c.emit('55 89 e5 53 56 57 83 e4 f0 83 ec 40')
    c.pic()
    c.string(device_root + '_baked/stringmap.txt')
    c.args()
    c.call(a.pointer(a.M[2882]))  # System.IO.File.ReadAllText
    c.emit('89 c6')
    c.call(0x2952990)  # il2cpp_get_corlib
    c.emit('89 44 24 30')
    c.raw_string('System')
    c.emit('89 44 24 04')
    c.raw_string('Char')
    c.emit('89 44 24 08 8b 44 24 30 89 04 24')
    c.call(0x2952e00)
    c.emit('89 04 24 c7 44 24 04 01 00 00 00')
    c.call(0x2952b10)
    c.emit('66 c7 40 10 1f 00 89 44 24 04 89 34 24 c7 44 24 08 00 00 00 00')
    c.call(a.pointer(a.M[391]))  # String.Split(char[])
    c.emit('89 c6')
    c.call(0x29538a0)  # domain_get
    c.emit('89 44 24 30')
    c.raw_string('Assembly-CSharp')
    c.emit('89 44 24 04 8b 44 24 30 89 04 24')
    c.call(0x29538d0)
    c.emit('89 04 24')
    c.call(0x2952c20)
    c.emit('89 44 24 30')
    c.raw_string('MoleMole.Bake')
    c.emit('89 44 24 04')
    c.raw_string('PackedStringMap')
    c.emit('89 44 24 08 8b 44 24 30 89 04 24')
    c.call(0x2952e00)
    c.emit('89 04 24')
    c.call(0x29532a0)
    c.emit('89 04 24')
    c.call(0x2954db0)
    c.args()
    c.call(a.pointer(a.M[16691]))  # ScriptableObject.CreateInstance(Type)
    c.emit('85 c0')
    missing = c.branch('0f 84')
    c.emit('89 70 10 c7 40 14')
    c.data.extend(struct.pack('<I', packed_hash))
    c.bind(missing)
    c.emit('8d 65 f4 5f 5e 5b 5d c3')
    return c.finish()


def container_code(device_root, original):
    c = Code(0xa64300)
    # Only intercept _Baked/ resources; preserve original loading otherwise.
    c.emit('50 51 8b 44 24 10 85 c0')
    fallback = [c.branch('0f 84')]
    c.emit('83 78 08 07')
    fallback.append(c.branch('0f 8c'))
    for offset, value in ((12,0x005f),(14,0x0042),(16,0x0061),(18,0x006b),
                          (20,0x0065),(22,0x0064),(24,0x002f)):
        c.emit('66 81 78 ' + f'{offset:02x}')
        c.data.extend(struct.pack('<H', value))
        fallback.append(c.branch('0f 85'))
    c.emit('59 58 55 89 e5 53 56 57 83 e4 f0 83 ec 60')
    c.pic()

    def klass(name, namespace='System', image=0x30):
        c.raw_string(namespace)
        c.emit('89 44 24 04')
        c.raw_string(name)
        c.emit('89 44 24 08 8b 44 24 ' + f'{image:02x}' + ' 89 04 24')
        c.call(0x2952e00)

    c.emit('8b 45 0c 89 04 24 c7 44 24 04 00 00 00 00')
    c.call(a.pointer(a.M[458]))  # String.ToLower (original helper used by the probe)
    c.emit('89 c6')
    c.string(device_root)
    c.args()
    c.emit('89 74 24 08 c7 44 24 0c 00 00 00 00')
    c.call(a.pointer(a.M[475]))  # String.Concat
    c.emit('89 c6')
    c.args()
    c.call(a.pointer(a.M[2873]))  # File.Exists
    c.emit('84 c0')
    file_missing = c.branch('0f 84')
    c.emit('89 f0')
    c.args()
    c.call(a.pointer(a.M[2879]))  # File.ReadAllBytes
    c.emit('8d 70 10 8b 06 89 44 24 40 8b 46 04 89 44 24 44 83 c6 08')
    c.call(0x2952990)
    c.emit('89 44 24 30')
    c.call(0x29538a0)
    c.emit('89 44 24 34')
    c.raw_string('Assembly-CSharp')
    c.emit('89 44 24 04 8b 44 24 34 89 04 24')
    c.call(0x29538d0)
    c.emit('89 04 24')
    c.call(0x2952c20)
    c.emit('89 44 24 34 83 7c 24 40 00')
    indexed = c.branch('0f 85')
    klass('PackedConfigContainer', 'MoleMole.Bake', 0x34)
    common = c.branch('e9')
    c.bind(indexed)
    klass('PackedIndexConfigContainer', 'MoleMole.Bake', 0x34)
    c.bind(common)
    c.emit('89 04 24')
    c.call(0x29532a0)
    c.emit('89 04 24')
    c.call(0x2954db0)
    c.args()
    c.call(a.pointer(a.M[16691]))
    c.emit('89 c7 89 7c 24 38')

    list_failed = []

    def array(name, element_size, field, namespace='System', image=0x30, list_field=None):
        klass(name, namespace, image)
        c.emit('8b 0e 83 c6 04 89 4c 24 3c 89 4c 24 04 89 04 24')
        c.call(0x2952b10)
        c.emit('8b 7c 24 38')
        if list_field is None:
            c.emit('89 47 ' + f'{field:02x}')
        c.emit('8d 78 10 8b 4c 24 3c')
        if element_size != 1:
            c.emit('6b c9 ' + f'{element_size:02x}')
        c.emit('f3 a4 8b 7c 24 38')
        if list_field is not None:
            # The array is a backing store, not the List object held by the
            # original container field. The helper preserves an existing List
            # or invokes the original reflected List<T> ctor when it is null.
            c.emit('89 c2')
            c.raw_string(list_field)
            c.emit('89 3c 24 89 44 24 04 89 54 24 08 8b 44 24 3c 89 44 24 0c')
            c.call(LIST_CODE_BASE)
            c.emit('85 c0')
            list_failed.append(c.branch('0f 84'))

    c.emit('83 7c 24 40 00')
    indexed = c.branch('0f 85')
    array('PackedEntry', 8, 16, 'MoleMole.Bake', 0x34, 'indices')
    array('PackedOverrideEntry', 12, 20, 'MoleMole.Bake', 0x34, 'overrideIndices')
    array('Byte', 1, 24)
    c.emit('8b 44 24 44 89 47 1c')
    common = c.branch('e9')
    c.bind(indexed)
    array('Int32', 4, 16, list_field='offsets')
    array('Byte', 1, 20)
    c.emit('8b 44 24 44 89 47 18')
    c.bind(common)
    c.emit('89 f8 8d 65 f4 5f 5e 5b 5d c3')
    # If the exported file is absent, keep the native resource loader behavior.
    c.bind(file_missing)
    for branch in list_failed:
        c.bind(branch)
    c.emit('8d 65 f4 5f 5e 5b 5d')
    late_fallback = c.branch('e9')
    for branch in fallback:
        c.bind(branch)
    c.emit('59 58')
    c.bind(late_fallback)
    c.data.extend(original[0x268673e:0x2686743])
    c.data.extend(b'\xe9' + struct.pack('<i', 0x2686743 - c.base - len(c.data) - 5))
    return c.finish()


def container_list_code():
    """Set a backing array on an actual original List<T>, never a fake List.

    Arguments are (container, UTF-8 field name, array, count). Both original
    container ctors only call ScriptableObject.ctor; null List fields therefore
    require the actual inflated List<T> class and its original parameterless
    ctor. runtime_invoke supplies the ctor's required inflated MethodInfo and
    captures exceptions instead of unwinding through this injected code.
    """
    c = Code(LIST_CODE_BASE)
    c.emit('55 89 e5 53 56 57 83 e4 f0 83 ec 50')
    c.pic()
    failed = []

    def guard():
        c.emit('85 c0')
        failed.append(c.branch('0f 84'))

    c.emit('8b 75 08 8b 06 89 04 24 8b 45 0c 89 44 24 04')
    c.call(0x2952f90)  # class_get_field_from_name(container.class, field name)
    guard()
    c.emit('89 44 24 30 89 04 24')
    c.call(0x2953b90)  # field_get_offset
    c.emit('89 44 24 34 8b 04 06 89 44 24 3c 85 c0')
    present = c.branch('0f 85')
    c.emit('8b 44 24 30 89 04 24')
    c.call(0x2953bc0)  # field_get_type: original inflated List<T> field type
    guard()
    c.emit('89 04 24')
    c.call(0x2953270)  # class_from_type
    guard()
    c.emit('89 44 24 38 89 04 24')
    c.call(0x2954530)  # object_new(original inflated List<T> class)
    guard()
    c.emit('89 44 24 3c')
    c.raw_string('.ctor')
    c.emit('89 44 24 04 8b 44 24 38 89 04 24 c7 44 24 08 00 00 00 00')
    c.call(0x2952ff0)  # class_get_method_from_name(inflated class, .ctor, 0)
    guard()
    c.emit('c7 44 24 40 00 00 00 00 89 04 24 8b 44 24 3c 89 44 24 04 c7 44 24 08 00 00 00 00 8d 44 24 40 89 44 24 0c')
    c.call(0x29547b0)  # runtime_invoke(MethodInfo, List instance, null, &exception)
    c.emit('83 7c 24 40 00')
    failed.append(c.branch('0f 85'))
    c.bind(present)
    # Native List<PackedEntry>, List<PackedOverrideEntry>, and List<int> ctor/
    # get_Item/get_Count confirm _items+8, _size+0xc, _version+0x10. Retain the
    # original object and version; only replace the backing array and size.
    c.emit('8b 44 24 3c 8b 55 10 89 50 08 8b 55 14 89 50 0c 8b 54 24 34 89 04 16')
    done = c.branch('e9')
    for branch in failed:
        c.bind(branch)
    c.emit('31 c0')
    c.bind(done)
    c.emit('8d 65 f4 5f 5e 5b 5d c3')
    return c.finish()


def meta_config_code(device_root):
    """Provide the original typed MetaConfig resource, preserving ctor defaults."""
    c = Code(META_CODE_BASE)
    c.emit('55 89 e5 53 56 57 83 e4 f0 83 ec 60')
    c.pic()
    c.string(device_root + 'metaconfig.txt')
    c.args()
    c.call(a.pointer(a.M[2882]))
    c.emit('89 c6')
    c.call(0x2952990)
    c.emit('89 44 24 30')
    c.raw_string('System')
    c.emit('89 44 24 04')
    c.raw_string('Char')
    c.emit('89 44 24 08 8b 44 24 30 89 04 24')
    c.call(0x2952e00)
    c.emit('89 04 24 c7 44 24 04 01 00 00 00')
    c.call(0x2952b10)
    c.emit('89 44 24 44 66 c7 40 10 1e 00 89 44 24 04 89 34 24 c7 44 24 08 00 00 00 00')
    c.call(a.pointer(a.M[391]))
    c.emit('89 44 24 40 8b 44 24 44 66 c7 40 10 1f 00')
    c.call(0x29538a0)
    c.emit('89 44 24 30')
    c.raw_string('Assembly-CSharp')
    c.emit('89 44 24 04 8b 44 24 30 89 04 24')
    c.call(0x29538d0)
    c.emit('89 04 24')
    c.call(0x2952c20)
    c.emit('89 44 24 30')
    c.raw_string('MoleMole')
    c.emit('89 44 24 04')
    c.raw_string('ConfigMetaConfig')
    c.emit('89 44 24 08 8b 44 24 30 89 04 24')
    c.call(0x2952e00)
    c.emit('89 04 24')
    c.call(0x29532a0)
    c.emit('89 04 24')
    c.call(0x2954db0)
    c.args()
    c.call(a.pointer(a.M[16691]))
    c.emit('89 c6 31 ff')
    loop = len(c.data)
    c.emit('8b 44 24 40 8b 44 b8 10 89 04 24 8b 44 24 44 89 44 24 04 c7 44 24 08 00 00 00 00')
    c.call(a.pointer(a.M[391]))
    c.emit('8d 93')
    offsets_fixup = len(c.data)
    c.data.extend(bytes(4))
    c.emit('0f b6 0c 3a 89 04 0e 47 83 ff 0d 0f 8c')
    c.data.extend(struct.pack('<i', loop - len(c.data) - 4))
    c.emit('89 f0 8d 65 f4 5f 5e 5b 5d c3')
    struct.pack_into('<i', c.data, offsets_fixup, c.base + len(c.data) - c.pic_base)
    # Four scalar registry paths stay as assigned by the original native ctor.
    c.data.extend(bytes((0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x2c,0x38,0x3c,0x40,0x44,0x50)))
    return c.finish()


def async_meta_config_code():
    """Supply only an absent MetaConfig after the original asynchronous wait.

    The hook is the specific get_asset call in LoadInLevelDataAsync, not the
    shared getter. Request creation, yielding the operation, and the original
    cast/global assignment all remain in the original coroutine.
    """
    c = Code(0xa642c0)
    c.emit('55 89 e5 83 e4 f0 83 ec 10')
    c.emit('8b 45 08 89 04 24 8b 45 0c 89 44 24 04')
    c.call(a.pointer(a.M[87691]))  # AsyncAssetRequst.get_asset(this, MethodInfo)
    c.emit('c9 85 c0')
    present = c.branch('0f 85')
    missing = c.branch('e9')
    struct.pack_into('<i', c.data, missing, META_CODE_BASE - c.base - missing - 4)
    c.bind(present)
    c.emit('c3')
    return c.finish()


def install(binary, output=DEFAULT_OUTPUT, device_root=DEFAULT_DEVICE_ROOT, apk24=resources.DEFAULT24):
    if not device_root.endswith('/'):
        device_root += '/'
    list_schema = verify_container_list_schema()
    manifest = extract(output, apk24)
    map_record = next(r for r in manifest['resources'] if r['path'] == '_baked/stringmap')
    map_payload = string_map_code(device_root, map_record['packed_hash'])
    container_payload = container_code(device_root, bytes(binary))
    list_payload = container_list_code()
    meta_payload = meta_config_code(device_root)
    async_meta_payload = async_meta_config_code()
    if len(map_payload) > 0x2c0 or len(async_meta_payload) > 0x40 or len(container_payload) > CONTAINER_CODE_END - 0xa64300 or len(meta_payload) > META_CODE_END - META_CODE_BASE or len(list_payload) > LIST_CODE_END - LIST_CODE_BASE:
        raise ValueError('Configuration supplier exceeds reserved code caves')
    patches = [
        (0xa64000, map_payload, 'PackedStringMap resource supplier'),
        (0xa642c0, async_meta_payload, 'missing MetaConfig asset supplier after original asynchronous wait'),
        (0xa64300, container_payload, 'baked configuration resource supplier'),
        (LIST_CODE_BASE, list_payload, 'original List<T> field adapter; unused method body used only as byte storage'),
        (META_CODE_BASE, meta_payload, 'typed MetaConfig resource supplier; unused method body used only as byte storage'),
        (0xae26f1, b'\xe8' + struct.pack('<i', 0xa64000 - 0xae26f6), 'SetupBakedDataRead StringMap resource call'),
        (0x268673e, b'\xe9' + struct.pack('<i', 0xa64300 - 0x2686743), 'baked resource loader adapter'),
        (0xae30e2, b'\xe8' + struct.pack('<i', META_CODE_BASE - 0xae30e7), 'synchronous MetaConfig resource call'),
        (0xae6a2f, b'\xe8' + struct.pack('<i', 0xa642c0 - 0xae6a34), 'asynchronous MetaConfig get_asset call'),
    ]
    for offset, payload, _ in patches:
        if binary[offset:offset + len(payload)] != a.E[offset:offset + len(payload)]:
            raise ValueError(f'Resource loader range {offset:#x} is already patched or not the expected original')
    ordered_ranges = sorted((offset, offset + len(payload)) for offset, payload, _ in patches)
    if any(left[1] > right[0] for left, right in zip(ordered_ranges, ordered_ranges[1:])):
        raise ValueError('Resource loader patch ranges overlap')
    manifest['patch_ranges'] = []
    for offset, payload, purpose in patches:
        manifest['patch_ranges'].append({'offset': hex(offset), 'size': len(payload),
                                         'before': bytes(binary[offset:offset + len(payload)]).hex(),
                                         'after': payload.hex(), 'purpose': purpose})
        binary[offset:offset + len(payload)] = payload
    manifest.update(device_root=device_root, map_stub_bytes=len(map_payload), container_stub_bytes=len(container_payload),
                    container_list_stub_bytes=len(list_payload),
                    metaconfig_stub_bytes=len(meta_payload), async_metaconfig_stub_bytes=len(async_meta_payload),
                    hooks={'stringmap_call': '0xae26f1', 'baked_resource_loader': '0x268673e',
                           'metaconfig_call': '0xae30e2', 'async_metaconfig_asset_call': '0xae6a2f'})
    manifest['container_list_adapter'] = {
        'helper_address': hex(LIST_CODE_BASE),
        'field_types': {'PackedConfigContainer.indices': 'List<PackedEntry>',
                        'PackedConfigContainer.overrideIndices': 'List<PackedOverrideEntry>',
                        'PackedIndexConfigContainer.offsets': 'List<Int32>'},
        'verified_original_declarations': list_schema,
        'field_offset': 'runtime field_get_offset on the original container class',
        'null_field': 'object_new of the original field type; runtime_invoke of its original parameterless List<T> constructor',
        'existing_list': 'preserved; backing _items and _size replaced',
        'verified_list_offsets': {'_items': '0x8', '_size': '0xc', '_version': '0x10'},
        'array_fields_preserved': ['PackedConfigContainer.packedBytes', 'PackedIndexConfigContainer.packedBytes', 'PackedStringMap.strings'],
    }
    (Path(output) / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest
