"""Export source TSV rows for original 1.9 typed configuration readers.

Only configuration assets are adapted. There is no client, service, player or
module execution. JSON files contain arrays for the original itemList field.
Source APKs and native binaries remain read-only; incomplete fields and source
rows excluded by version, region or conversion errors are reported explicitly.
"""
from pathlib import Path
from functools import lru_cache
import argparse
import csv
import hashlib
import io
import json
import math
import re
import struct
import zipfile

import analyze19 as a
import server19_resources as resources

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / '.local-baseline/server19-dev/metadata-fallback'
TYPE_TABLE = 0x359c46c
TYPE_COUNT = 63040
TYPE_REGISTRATION_PAIR = 0x34a67c4


def native_json(value):
    """Encode numbers for the original parser without changing their values.

    The 1.9 parser distinguishes floating-point tokens by a decimal point.
    Python can emit a float as 8e-05, which that parser sends to Int64.Parse.
    Match quoted strings first so their contents remain byte-for-byte intact.
    """
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    changed = 0

    def compatible_token(match):
        nonlocal changed
        token = match[0]
        if token.startswith('"') or '.' in token or not re.search('[eE]', token):
            return token
        changed += 1
        mantissa, marker, exponent = re.split('([eE])', token, maxsplit=1)
        return mantissa + '.0' + marker + exponent

    encoded = re.sub(r'"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?',
                     compatible_token, encoded)
    return encoded, changed


@lru_cache(None)
def type_pointer(index):
    if struct.unpack_from('<II', a.E, TYPE_REGISTRATION_PAIR) != (TYPE_COUNT, TYPE_TABLE):
        raise ValueError('Not the inspected original 1.9 type registration')
    if not 0 <= index < TYPE_COUNT:
        raise ValueError('Invalid native field type index')
    return struct.unpack_from('<I', a.E, TYPE_TABLE + index * 4)[0]


@lru_cache(None)
def type_info(pointer):
    data, flags = struct.unpack_from('<II', a.E, pointer)
    result = {'pointer': pointer, 'kind': (flags >> 16) & 0xff,
              'attributes': flags & 0xffff, 'data': data}
    if result['kind'] in (0x11, 0x12):
        result.update(type_index=data, name=a.type_name(data))
    elif result['kind'] == 0x15:
        definition, inst = struct.unpack_from('<II', a.E, data)
        count, argv = struct.unpack_from('<II', a.E, inst)
        result.update(type_index=definition, name=a.type_name(definition),
                      arguments=tuple(struct.unpack_from('<I', a.E, argv + i * 4)[0]
                                      for i in range(count)))
    elif result['kind'] == 0x1d:
        result['element'] = data
    return result


@lru_cache(None)
def fields(type_index):
    result = []
    typ = a.T[type_index]
    for index in range(typ[16], typ[16] + typ[26]):
        name, native_type, _, _ = struct.unpack_from('<4I', a.B, 9233316 + index * 16)
        pointer = type_pointer(native_type)
        if type_info(pointer)['attributes'] & 0x10:  # Static fields are not row data.
            continue
        result.append((a.string(name), pointer))
    return tuple(result)


def serialized_fields(type_index):
    """Row data excludes the original runtime-only NotSerialized fields.

    Keep fields() unchanged: baked schema inspection also uses its declaration
    order. Original fsConfig ignores NonSerializedAttribute, and Unity does not
    store these fields in its configuration assets.
    """
    return tuple((name, pointer) for name, pointer in fields(type_index)
                 if not type_info(pointer)['attributes'] & 0x80)


def asset_types():
    result = {}
    for index in range(len(a.T)):
        if not a.type_name(index).startswith('MoleMole.') or not a.type_name(index).endswith('Asset'):
            continue
        item_list = next((pointer for name, pointer in fields(index) if name == 'itemList'), None)
        if item_list is None:
            continue
        info = type_info(item_list)
        if info.get('name') != 'System.Collections.Generic.List`1' or len(info['arguments']) != 1:
            continue
        row = type_info(info['arguments'][0])
        if row['kind'] in (0x11, 0x12):
            result[a.type_name(index)] = {'asset_type': a.type_name(index),
                                         'asset_type_index': index,
                                         'row_type': row['name'], 'row_type_index': row['type_index']}
    return result


class PackageObjects:
    def __init__(self, package):
        self.package, self.cache = package, {}

    def file(self, name):
        if name not in self.cache:
            data = self.package.read('assets/bin/Data/' + name)
            self.cache[name] = data, resources.serialized(data)
        return self.cache[name]

    def object(self, record):
        data, info = self.file(record['file'])
        obj = info['objects'][record['path_id']]
        return obj, data[obj['offset']:obj['offset'] + obj['size']]

    def script_type(self, record, raw):
        _, info = self.file(record['file'])
        file_id, path_id = struct.unpack_from('<iq', raw, 16)
        filename = info['externals'][file_id - 1].rsplit('/', 1)[-1] if file_id else record['file']
        obj, script = self.object({'file': filename, 'path_id': path_id})
        if obj['class'] != 115:
            raise ValueError('Config ScriptableObject does not refer to a MonoScript')
        reader = resources.Reader(script)
        reader.string()
        reader.pos += 20  # Execution order and properties hash.
        name, namespace, assembly = (reader.string() for _ in range(3))
        if assembly != 'Assembly-CSharp.dll':
            raise ValueError('Unexpected source config assembly')
        return '.'.join(part for part in (namespace, name) if part)


class SourceTypedDecoder:
    """Decode inspected 2.4 typed rows for composite fields absent in TSV cells."""
    def __init__(self, package):
        self.binary = package.read('lib/x86/libil2cpp.so')
        self.metadata = package.read('assets/bin/Data/Managed/Metadata/global-metadata.dat')
        header = struct.unpack_from('<64I', self.metadata)
        if header[1] != 23 or struct.unpack_from('<II', self.binary, 0x42520e8) != (93237, 0x409d890):
            raise ValueError('Not the inspected 2.4 reference metadata/type registration')
        self.strings, self.field_table = header[6], header[24]
        self.types = [struct.unpack_from('<20I8H2I', self.metadata, header[40] + offset)
                      for offset in range(0, header[41], 104)]
        self.names = {self.name(index): index for index in range(len(self.types))}
        self.cache = {}

    def string(self, index):
        start = self.strings + index
        return self.metadata[start:self.metadata.index(0, start)].decode('utf-8')

    def name(self, index):
        typ = self.types[index]
        return '.'.join(part for part in (self.string(typ[1]), self.string(typ[0])) if part)

    def fields(self, index):
        if index not in self.cache:
            typ, result = self.types[index], []
            for field in range(typ[12], typ[12] + typ[22]):
                name, native_type, _, _ = struct.unpack_from('<4I', self.metadata, self.field_table + field * 16)
                pointer = struct.unpack_from('<I', self.binary, 0x409d890 + native_type * 4)[0]
                _, flags = struct.unpack_from('<II', self.binary, pointer)
                if not flags & 0x10:
                    result.append((self.string(name), pointer))
            self.cache[index] = tuple(result)
        return self.cache[index]

    def value(self, reader, pointer):
        data, flags = struct.unpack_from('<II', self.binary, pointer)
        kind = (flags >> 16) & 0xff
        if kind == 0x0e:
            return reader.string()
        if kind == 0x02:
            value = reader.read('B')
            if value not in (0, 1):
                raise ValueError('Invalid source serialized Boolean')
            reader.align()
            return bool(value)
        primitive = {0x03: 'H', 0x04: 'b', 0x05: 'B', 0x06: 'h', 0x07: 'H',
                     0x08: 'i', 0x09: 'I', 0x0a: 'q', 0x0b: 'Q', 0x0c: 'f', 0x0d: 'd'}
        if kind in primitive:
            value = reader.read(primitive[kind])
            if kind < 0x08:
                reader.align()
            return value
        if kind in (0x15, 0x1d):
            if kind == 0x15:
                definition, inst = struct.unpack_from('<II', self.binary, data)
                count, argv = struct.unpack_from('<II', self.binary, inst)
                if self.name(definition) != 'System.Collections.Generic.List`1' or count != 1:
                    raise ValueError('Unsupported source serialized generic field')
                element = struct.unpack_from('<I', self.binary, argv)[0]
            else:
                element = data
            count = reader.read('i')
            if not 0 <= count <= len(reader.data) // 4:
                raise ValueError('Invalid source serialized array length')
            result = [self.value(reader, element) for _ in range(count)]
            reader.align()
            return result
        if kind in (0x11, 0x12):
            members = self.fields(data)
            if any(name == 'value__' for name, _ in members):
                return reader.read('i')
            return {name: self.value(reader, member) for name, member in members}
        raise ValueError(f'Unsupported source serialized kind {kind:#x}')

    def rows(self, raw, row_name, row_spans=None):
        row_index = self.names[row_name]
        reader = resources.Reader(raw, 28)
        reader.string()
        count = reader.read('i')
        if not 0 <= count <= len(raw) // 4:
            raise ValueError('Invalid source typed row count')
        values = []
        for _ in range(count):
            start = reader.pos
            values.append({name: self.value(reader, pointer)
                           for name, pointer in self.fields(row_index)})
            if row_spans is not None:
                row_spans.append((start, reader.pos))
        path = reader.string()
        if reader.pos != len(raw) or not path.startswith('_ExcelOutputAsset/'):
            raise ValueError('Source typed row schema did not consume the exact object boundary')
        return values


def project_typed(value, pointer):
    info = type_info(pointer)
    if info['kind'] in (0x15, 0x1d):
        element = info['arguments'][0] if info['kind'] == 0x15 else info['element']
        return [project_typed(item, element) for item in value]
    if info['kind'] in (0x11, 0x12):
        return {name: project_typed(value[name], member) for name, member in fields(info['type_index'])}
    return value


def version_tuple(value):
    return tuple(int(part) for part in value.split('.')) if value else ()


def in_version(row, version):
    begin, end = row.get('GameVersionBegin', ''), row.get('GameVersionEnd', '')
    return (not begin or version_tuple(begin) <= version) and (not end or version_tuple(end) >= version)


def in_region(row, region):
    values = row.get('EffectRegionList', '')
    return not values or 'all' in values.split(',') or region in values.split(',')


def original_cg_icon_name(value):
    """Adapt the source full path to the basename consumed by original 1.9.

    MonoCgIconButton.SetupView84177@e11772 formats cgIconPath with
    SpriteOutput/CGReplay/{0} at e119ff/e11a1e. Strip that exact prefix once;
    reject other paths rather than inventing an icon or accepting traversal.
    """
    prefix = 'SpriteOutput/CGReplay/'
    name = value[len(prefix):] if value.startswith(prefix) else value
    if re.fullmatch(r'[A-Za-z0-9_]+', name) is None:
        raise ValueError('CG icon must be a basename or an exact SpriteOutput/CGReplay/ path')
    return name


def convert(value, pointer):
    info = type_info(pointer)
    kind = info['kind']
    if kind == 0x0e:
        return value
    if kind == 0x02:
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        number = int(value or '0')
        if number not in (0, 1):
            raise ValueError('Boolean source value is outside 0/1')
        return bool(number)
    if kind == 0x03:
        if len(value) != 1 or ord(value) > 0xffff or 0xd800 <= ord(value) <= 0xdfff:
            raise ValueError('Expected one source character')
        return value
    if 0x04 <= kind <= 0x0b:
        return int(value or '0')
    if kind in (0x0c, 0x0d):
        number = float(value or '0')
        if not math.isfinite(number):
            raise ValueError('Non-finite source number')
        return number
    if kind in (0x15, 0x1d):
        if kind == 0x15:
            if info['name'] != 'System.Collections.Generic.List`1' or len(info['arguments']) != 1:
                raise ValueError('Unsupported source generic field')
            element = info['arguments'][0]
        else:
            element = info['element']
        return [convert(part, element) for part in value.split(',') if part != '']
    if kind in (0x11, 0x12):
        member_fields = fields(info['type_index'])
        if any(name == 'value__' for name, _ in member_fields):
            if not value or value.lstrip('-').isdigit():
                return int(value or '0')
            # FullSerializer accepts source enum names; validate against the
            # actual enum declaration before handing them to the native parser.
            typ = a.T[info['type_index']]
            enum_names = {a.string(struct.unpack_from('<4I', a.B, 9233316 + index * 16)[0])
                          for index in range(typ[16], typ[16] + typ[26])}
            if value not in enum_names:
                raise ValueError('Unknown original enum member')
            return value
        parts = value.split(':')
        if len(parts) != len(member_fields):
            raise ValueError('Source composite field shape does not match original fields')
        return {name: convert(part, member_type)
                for part, (name, member_type) in zip(parts, member_fields)}
    raise ValueError(f'Unsupported original native field kind {kind:#x}')


def column_mapping(row_type_index, headers):
    lookup = {}
    for name in headers:
        lookup.setdefault(name.strip().casefold(), []).append(name)
    result = {}
    for name, _ in serialized_fields(row_type_index):
        matches = lookup.get(name.casefold(), [])
        if len(matches) == 1:
            result[name] = matches[0]
    return result


def array_source(row_type, field, row):
    """Expanded columns whose serialized list sentinel was inspected earlier."""
    specs = {
        ('MoleMole.ReviveCostTypeMetaData', 'Type1'): ('Type', 1, 10, 0),
        ('MoleMole.EquipmentLevelMetaData', 'Type1'): ('Type', 1, 7, 0),
        ('MoleMole.AvatarSubSkillLevelMetaData', 'SCoin_1'): ('SCoin_', 1, 25, 0),
        ('MoleMole.AvatarSubSkillLevelMetaData', 'Item_1'): ('Item_', 1, 9, ''),
    }
    spec = specs.get((row_type, field))
    if spec is None:
        return None
    prefix, first, last, sentinel = spec
    names = [prefix + str(index) for index in range(first, last + 1)]
    if not all(name in row for name in names):
        raise ValueError('Expanded source columns are missing')
    return ','.join(row[name] for name in names), sentinel


def text_map_sources(objects, paths, raw):
    """Locate the source tables actually contributing to the typed TextMap."""
    reader = resources.Reader(raw, 28)
    reader.string()
    pairs = {(reader.string(), reader.string()) for _ in range(reader.read('i'))}
    asset_path = reader.string()
    if reader.pos != len(raw) or asset_path != '_ExcelOutputAsset/TextMap':
        raise ValueError('Unexpected source TextMapAsset layout')
    combined, sources = [], []
    for record in paths:
        name = record['path']
        if not name.startswith('data/_exceloutput/') or 'textmap' not in name:
            continue
        if name.rsplit('/', 1)[-1].startswith(('textmapgamestart', 'textmapstatistics')):
            continue
        obj, source_raw = objects.object(record)
        if obj['class'] != 49:
            continue
        _, text = resources.text_asset(source_raw)
        table = csv.DictReader(io.StringIO(text.decode('utf-8-sig'), newline=''), delimiter='\t')
        headers = table.fieldnames
        id_column = next((key for key in ('ID', 'TextID', 'AccountBuff_') if key in headers), None)
        text_column = next((key for key in ('Text', 'Contents') if key in headers), None)
        if id_column is None or text_column is None:
            continue
        rows = list(table)
        matched = sum((row.get(id_column), row.get(text_column)) in pairs for row in rows)
        if not matched:
            continue
        sources.append(dict(record, source_text_sha256=hashlib.sha256(text).hexdigest(),
                            field_mapping={'ID': id_column, 'Text': text_column},
                            source_rows=len(rows), matches_original_typed_source=matched))
        for line, row in enumerate(rows, 2):
            item = {'ID': row.get(id_column), 'Text': row.get(text_column),
                    '_source_path': name, '_source_line': line}
            for key in ('GameVersionBegin', 'GameVersionEnd', 'EffectRegionList'):
                item[key] = row.get(key, '')
            if None in row or any(value is None for value in row.values()):
                item['_malformed'] = True
            combined.append(item)
    return combined, sources


def required_avatar_skill_rows(objects, by_path, decoder, raw, row_fields, mapping, text, version, region):
    """Audit two real later-version rows required by retained avatar skillLists.

    This is an explicit compatibility dependency, not an expansion of the
    version filter or a claim that the 2.0 values are historical 1.9 values.
    """
    if version != (1, 9) or region != 'cn':
        return []
    required = {52: 201, 182: 212}
    avatar_table = by_path['data/_exceloutput/avatardata']
    _, avatar_raw = objects.object(avatar_table)
    _, avatar_text = resources.text_asset(avatar_raw)
    avatar_rows = list(csv.DictReader(io.StringIO(avatar_text.decode('utf-8-sig'), newline=''), delimiter='\t'))
    dependencies = {}
    for line, row in enumerate(avatar_rows, 2):
        if not in_version(row, version) or not in_region(row, region):
            continue
        avatar_id = int(row['avatarID'])
        for skill_id, expected_avatar in required.items():
            if avatar_id == expected_avatar and skill_id in [int(value) for value in row['skillList'].split(',')]:
                dependencies[skill_id] = {'avatar_id': avatar_id, 'avatar_source_line': line,
                                          'avatar_skillList': row['skillList'],
                                          'avatar_version_begin': row['GameVersionBegin'],
                                          'avatar_version_end': row['GameVersionEnd']}
    if set(dependencies) != set(required):
        raise ValueError('The explicit skill dependency is absent from a retained source avatar')
    spans = []
    typed_rows = decoder.rows(raw, 'MoleMole.AvatarSkillMetaData', spans)
    source_fields = decoder.fields(decoder.names['MoleMole.AvatarSkillMetaData'])
    if len(row_fields) != 24 or [name for name, _ in row_fields] != [name for name, _ in source_fields]:
        raise ValueError('AvatarSkill source/original 24-field declaration differs')
    for (_, original), (_, source) in zip(row_fields, source_fields):
        flags = struct.unpack_from('<II', decoder.binary, source)[1]
        if (flags >> 16) & 0xff != type_info(original)['kind']:
            raise ValueError('AvatarSkill source/original field types differ')
    typed = {row['skillId']: (index, row, span)
             for index, (row, span) in enumerate(zip(typed_rows, spans))}
    if len(typed) != len(typed_rows):
        raise ValueError('AvatarSkill typed source IDs are not unique')
    source_lines = text.decode('utf-8-sig').splitlines(keepends=True)
    result = []
    seen = set()
    for line, row in enumerate(csv.DictReader(io.StringIO(text.decode('utf-8-sig'), newline=''), delimiter='\t'), 2):
        skill_id = int(row['skillId'])
        if skill_id not in required:
            continue
        if skill_id in seen or None in row or any(value is None for value in row.values()):
            raise ValueError('Explicit skill source row is duplicated or malformed')
        if row['GameVersionBegin'] != '2.0' or row['GameVersionEnd'] != '' or not in_region(row, region):
            raise ValueError('Explicit skill source version/region differs from the audited source')
        seen.add(skill_id)
        converted = {name: convert(row[mapping[name]], pointer) for name, pointer in row_fields}
        index, typed_row, (start, end) = typed[skill_id]
        for name, pointer in row_fields:
            value = ord(converted[name]) if type_info(pointer)['kind'] == 0x03 else converted[name]
            if value != typed_row[name]:
                raise ValueError(f'Explicit skill {skill_id} TSV/typed value differs in {name}')
        audit = dict(dependencies[skill_id], skill_id=skill_id, source_line=line, source_row_index=index,
                     source_byte_span=[start, end], source_row_sha256=hashlib.sha256(raw[start:end]).hexdigest(),
                     source_tsv_row_sha256=hashlib.sha256(source_lines[line - 1].encode('utf-8')).hexdigest(),
                     source_version_begin=row['GameVersionBegin'], source_version_end=row['GameVersionEnd'],
                     source_region=row['EffectRegionList'], source_version_metadata_preserved=True,
                     source_tsv_typed_fields_verified=[name for name, _ in row_fields],
                     source_typed_exact_boundary_verified=True, historical_19_values_verified=False,
                     original_consumer_evidence='AvatarSkillDataItem::.ctor@14cd9f3 stores lookup result at14cda77; GetAvatarSkillMetaDataByKey@14cda8a returns the TryGetValue out value without checking its bool at14cdb97',
                     runtime_compatibility='Requires original-flow device verification; source is genuinely version2.0',
                     avatar_source_table=dict(avatar_table),
                     avatar_source_text_sha256=hashlib.sha256(avatar_text).hexdigest())
        result.append((converted, audit))
    if seen != set(required):
        raise ValueError('An explicit skill dependency has no actual TSV source row')
    return result


def required_cabin_level_rows(decoder, raw, row_fields, mapping, text, version, region):
    """Audit four real rows needed by the original nine-cabin level-one lookup.

    Keep the normal version/region filter and its exclusion counts unchanged.
    These explicit dependencies are source 2.0 values, not historical 1.9 data.
    """
    if version != (1, 9) or region != 'cn':
        return []
    required = {(1, 1), (3, 1), (4, 1), (5, 1)}
    expected_fields = ['cabinType', 'cabinName', 'level', 'playerLevelNeed',
                       'scoinNeed', 'itemListNeed', 'upLevelTimeNeed']
    source_fields = decoder.fields(decoder.names['MoleMole.CabinLevelMetaData'])
    if ([name for name, _ in row_fields] != expected_fields or
            [name for name, _ in source_fields] != expected_fields or
            set(mapping) != set(expected_fields)):
        raise ValueError('CabinLevel source/original seven-field declarations differ')

    def signature(pointer, original):
        binary = a.E if original else decoder.binary
        data, flags = struct.unpack_from('<II', binary, pointer)
        kind = (flags >> 16) & 0xff
        if kind == 0x1d:
            return ('array', signature(data, original))
        if kind == 0x15:
            definition, inst = struct.unpack_from('<II', binary, data)
            count, argv = struct.unpack_from('<II', binary, inst)
            name = a.type_name(definition) if original else decoder.name(definition)
            return (name, tuple(signature(struct.unpack_from('<I', binary, argv + index * 4)[0], original)
                                for index in range(count)))
        if kind in (0x11, 0x12):
            name = a.type_name(data) if original else decoder.name(data)
            members = serialized_fields(data) if original else tuple(
                (field, member) for field, member in decoder.fields(data)
                if not struct.unpack_from('<II', decoder.binary, member)[1] & 0x80)
            return (name, tuple((field, signature(member, original)) for field, member in members))
        return kind

    for (_, original), (_, source) in zip(row_fields, source_fields):
        if signature(original, True) != signature(source, False):
            raise ValueError('CabinLevel source/original field or nested item types differ')
    spans = []
    typed_rows = decoder.rows(raw, 'MoleMole.CabinLevelMetaData', spans)
    typed = {(item['cabinType'], item['level']): (index, item, span)
             for index, (item, span) in enumerate(zip(typed_rows, spans))}
    if len(typed) != len(typed_rows):
        raise ValueError('CabinLevel typed source composite keys are not unique')
    rows = list(csv.DictReader(io.StringIO(text.decode('utf-8-sig'), newline=''), delimiter='\t'))
    keys = [(int(row['cabinType']), int(row['level'])) for row in rows]
    if len(set(keys)) != len(keys) or len(rows) != len(typed_rows):
        raise ValueError('CabinLevel TSV keys are duplicated or source row counts differ')
    source_lines = text.decode('utf-8-sig').splitlines(keepends=True)
    result, seen = [], set()
    for line, row in enumerate(rows, 2):
        key = (int(row['cabinType']), int(row['level']))
        if key not in required:
            continue
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Required CabinLevel source row is malformed')
        if (row['GameVersionBegin'] != '2.0' or row['GameVersionEnd'] != '' or
                not in_region(row, region) or in_version(row, version)):
            raise ValueError('Required CabinLevel source version/region differs from the audited source')
        converted = {name: convert(row[mapping[name]], pointer) for name, pointer in row_fields}
        index, typed_row, (start, end) = typed[key]
        if converted != typed_row:
            raise ValueError(f'Required CabinLevel {key} TSV/typed values differ')
        seen.add(key)
        audit = {
            'cabin_type': key[0], 'level': key[1], 'source_line': line,
            'source_row_index': index, 'source_byte_span': [start, end],
            'source_row_sha256': hashlib.sha256(raw[start:end]).hexdigest(),
            'source_tsv_row_sha256': hashlib.sha256(source_lines[line - 1].encode('utf-8')).hexdigest(),
            'source_version_begin': row['GameVersionBegin'], 'source_version_end': row['GameVersionEnd'],
            'source_region': row['EffectRegionList'], 'source_version_metadata_preserved': True,
            'source_tsv_typed_fields_verified': expected_fields,
            'source_original_nested_type_signatures_equal': True,
            'source_typed_exact_boundary_verified': True, 'historical_19_values_verified': False,
            'original_consumer_evidence': 'IslandModule.InitCabinDict69029@b5220c creates cabin types1..9; CabinDataItemBase.GetUnlockPlayerLevel@7f3378 looks up(cabinType,1), then dereferences an unchecked result at7f3408; OnPlayerLevelChanged@b5753e calls it',
            'runtime_compatibility': 'Requires original-flow device verification; these are genuine source2.0 values',
            'cabin_unlock_or_level_progress_fabricated': False,
        }
        result.append((converted, audit))
    if seen != required:
        raise ValueError('A required CabinLevel dependency has no complete actual source row')
    return result


def required_touch_level_rows(decoder, raw, row_fields, mapping, text, version, region):
    """Audit the five real source levels required by native feel conversion.

    Source rows remain version 2.0 dependencies. Only their original five
    fields are projected, with Single values compared and emitted as float32.
    """
    if version != (1, 9) or region != 'cn':
        return []
    required = set(range(1, 6))
    expected_fields = ['level', 'touchExp', 'prop', 'rate', 'battleGain']
    expected_kinds = [0x08, 0x08, 0x0c, 0x0c, 0x08]
    expected_mapping = dict(zip(expected_fields, ['Level', 'TouchExp', 'Prop', 'Rate', 'BattleGain']))
    source_fields = decoder.fields(decoder.names['MoleMole.TouchLevelMetaData'])
    if ([name for name, _ in row_fields] != expected_fields or
            [name for name, _ in source_fields] != expected_fields + ['addGoodfeelPerMinute'] or
            mapping != expected_mapping):
        raise ValueError('TouchLevel source/original fields or TSV mapping differ')
    for index, (_, original) in enumerate(row_fields):
        source = source_fields[index][1]
        source_kind = (struct.unpack_from('<II', decoder.binary, source)[1] >> 16) & 0xff
        if type_info(original)['kind'] != expected_kinds[index] or source_kind != expected_kinds[index]:
            raise ValueError('TouchLevel source/original primitive field types differ')
    if (struct.unpack_from('<II', decoder.binary, source_fields[-1][1])[1] >> 16) & 0xff != 0x08:
        raise ValueError('Unexpected source-only TouchLevel minute field type')

    spans = []
    typed_rows = decoder.rows(raw, 'MoleMole.TouchLevelMetaData', spans)
    typed = {item['level']: (index, item, span)
             for index, (item, span) in enumerate(zip(typed_rows, spans))}
    if len(typed) != len(typed_rows) or set(typed) != required:
        raise ValueError('TouchLevel typed source levels are not exactly unique keys1..5')
    rows = list(csv.DictReader(io.StringIO(text.decode('utf-8-sig'), newline=''), delimiter='\t'))
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Required TouchLevel source row is malformed')
    keys = [int(row['Level']) for row in rows]
    if len(keys) != len(required) or set(keys) != required:
        raise ValueError('TouchLevel TSV levels are not exactly unique keys1..5')

    source_lines = text.decode('utf-8-sig').splitlines(keepends=True)
    result = []
    for line, row in enumerate(rows, 2):
        level = int(row['Level'])
        if (row['GameVersionBegin'] != '2.0' or row['GameVersionEnd'] != '' or
                row['EffectRegionList'] != 'all' or not in_region(row, region) or in_version(row, version)):
            raise ValueError('Required TouchLevel source version/region differs from the audited source')
        converted = {name: convert(row[mapping[name]], pointer) for name, pointer in row_fields}
        index, typed_row, (start, end) = typed[level]
        float_audit = {}
        for name, pointer in row_fields:
            if type_info(pointer)['kind'] == 0x0c:
                tsv_bits = struct.pack('<f', converted[name])
                typed_bits = struct.pack('<f', typed_row[name])
                if tsv_bits != typed_bits:
                    raise ValueError(f'Required TouchLevel{level} TSV/typed float32 differs in {name}')
                converted[name] = struct.unpack('<f', tsv_bits)[0]
                float_audit[name] = {'tsv_token': row[mapping[name]],
                                     'float32_little_endian_hex': tsv_bits.hex(),
                                     'normalized_value': converted[name]}
            if converted[name] != typed_row[name]:
                raise ValueError(f'Required TouchLevel{level} TSV/typed value differs in {name}')
        if converted['touchExp'] <= 0:
            raise ValueError('Source TouchLevel threshold must be positive for native zero-feel conversion')
        audit = {
            'level': level, 'source_line': line, 'source_row_index': index,
            'source_byte_span': [start, end],
            'source_row_sha256': hashlib.sha256(raw[start:end]).hexdigest(),
            'source_tsv_row_sha256': hashlib.sha256(source_lines[line - 1].encode('utf-8')).hexdigest(),
            'source_version_begin': row['GameVersionBegin'], 'source_version_end': row['GameVersionEnd'],
            'source_region': row['EffectRegionList'], 'source_version_metadata_preserved': True,
            'source_tsv_typed_fields_verified': expected_fields,
            'source_original_primitive_types_equal': True, 'float32_normalization': float_audit,
            'source_typed_exact_boundary_verified': True, 'historical_19_values_verified': False,
            'excluded_source_typed_fields': ['addGoodfeelPerMinute'],
            'original_consumer_evidence': 'GalTouchModule.TotalToHeartLevelAndGoodFeel68985@ac35c0 starts heartLevel1 and queries levels1..4; QueryLevelUpFeelNeed59823@ac1005 reads TouchLevel.touchExp at ac1086 or returns0 for a missing row; GetTouchLevelItem59830@ac1787 queries the current level including5',
            'zero_accumulated_feel': {'first_threshold': converted['touchExp'] if level == 1 else None,
                                     'source_account_progress_changed': False},
            'runtime_compatibility': 'Requires original-flow device verification; these are genuine source2.0 values',
            'feel_buff_or_progress_fabricated': False,
        }
        result.append((converted, audit))
    return result


def export(output=DEFAULT_OUTPUT, apk24=resources.DEFAULT24, version=(1, 9), region='cn', stage_ratios='repaired'):
    if stage_ratios not in ('baseline', 'repaired'):
        raise ValueError('Unknown stage ratio policy')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    known = asset_types()
    paths = resources.resource_map(apk24)
    by_path = {record['path']: record for record in paths}
    manifest = {'source': str(apk24), 'target_version': '.'.join(map(str, version)), 'target_region': region,
                'stage_ratio_policy': stage_ratios,
                'json_shape': 'array for the original itemList field', 'runtime_compatibility': 'not yet verified',
                'field_selection': {'excluded_field_attribute_mask': '0x80 (NotSerialized)',
                                    'original_serializer_evidence': 'fsConfig::.ctor30372@15a1b40 puts System.NonSerializedAttribute in IgnoreSerializeAttributes; fsMetaType.CollectProperties30539@15a7e6c skips members through Any(HasAttribute)',
                                    'runtime_fields_are_not_fabricated': True},
                'number_encoding': {'rule': 'Scientific numeric tokens without a decimal point gain .0 before the exponent',
                                    'reason': 'Original 1.9 fsJsonParser selects floating-point parsing only when the token contains a decimal point',
                                    'value_preserved': True, 'strings_preserved': True},
                'files': [], 'deployment_files': [], 'unmatched_source_assets': [], 'missing_source_assets': []}
    matched = set()
    with zipfile.ZipFile(apk24) as package:
        objects = PackageObjects(package)
        typed_decoder = None
        for asset in paths:
            if not asset['path'].startswith('_exceloutputasset/'):
                continue
            obj, raw = objects.object(asset)
            if obj['class'] != 114:
                continue
            asset_type = objects.script_type(asset, raw)
            if asset_type not in known:
                manifest['unmatched_source_assets'].append({'path': asset['path'], 'asset_type': asset_type})
                continue
            matched.add(asset_type)
            record = dict(known[asset_type], resource_path=asset['path'], source_asset=dict(asset),
                          source_asset_sha256=hashlib.sha256(raw).hexdigest(),
                          missing_fields=[], unsupported_fields=[], conversion_errors=[], char_fixups=[],
                          excluded_version=0, excluded_region=0, malformed_rows=0)
            table_path = 'data/_exceloutput/' + asset['path'].split('/', 1)[1]
            table = by_path.get(table_path)
            if table is None:
                record.update(status='missing source TSV', source_table=table_path)
                manifest['files'].append(record)
                continue
            _, table_raw = objects.object(table)
            _, text = resources.text_asset(table_raw)
            reader = csv.DictReader(io.StringIO(text.decode('utf-8-sig'), newline=''), delimiter='\t')
            headers = reader.fieldnames
            if asset_type == 'MoleMole.TextMapAsset':
                reader, record['source_tables'] = text_map_sources(objects, paths, raw)
                headers = ['ID', 'Text', 'GameVersionBegin', 'GameVersionEnd', 'EffectRegionList']
            row_fields = serialized_fields(record['row_type_index'])
            record['runtime_fields'] = [{'field': name,
                                         'type': type_info(pointer).get('name'),
                                         'attributes': hex(type_info(pointer)['attributes']),
                                         'reason': 'Original NotSerialized field, initialized by the original runtime logic'}
                                        for name, pointer in fields(record['row_type_index'])
                                        if type_info(pointer)['attributes'] & 0x80]
            mapping = column_mapping(record['row_type_index'], headers)
            expanded_fields = {name for name, _ in row_fields
                               if array_source(record['row_type'], name, {key: '' for key in headers}) is not None}
            record['missing_fields'] = [name for name, _ in row_fields if name not in mapping and name not in expanded_fields]
            record['extra_source_fields'] = [name for name in headers if name not in mapping.values()]
            record['field_mapping'] = mapping
            if asset_type == 'MoleMole.CgDataAsset':
                record['field_semantic_adaptations'] = [{
                    'field': 'CgIconSpritePath',
                    'rule': 'Strip one exact SpriteOutput/CGReplay/ prefix; preserve basenames; reject other paths',
                    'original_consumer': 'MonoCgIconButton.SetupView84177@e11772',
                    'original_format': 'SpriteOutput/CGReplay/{0}',
                    'format_literal_address': '0xe119ff',
                    'format_call_address': '0xe11a1e',
                    'field_copy_evidence': 'CgDataItem.ctor68101@83f803 copies CgMetaData+0x24 to cgIconPath+0x1c at83f853/83f856',
                    'source_values': [],
                }]
            typed_by_key = None
            typed_spans = None
            if record['row_type'] in ('MoleMole.LevelMetaData', 'MoleMole.DialogMetaData'):
                try:
                    if typed_decoder is None:
                        typed_decoder = SourceTypedDecoder(package)
                    source_spans = []
                    source_items = typed_decoder.rows(raw, record['row_type'], source_spans)
                    key_field = row_fields[0][0]
                    typed_by_key = {item[key_field]: item for item in source_items}
                    typed_spans = {item[key_field]: (index, span)
                                   for index, (item, span) in enumerate(zip(source_items, source_spans))}
                    if len(typed_by_key) != len(source_items):
                        raise ValueError('Source typed primary keys are not unique')
                    record['typed_composite_recoveries'] = []
                    record['typed_source_rows'] = len(source_items)
                    record['typed_source_exact_boundary_verified'] = True
                except (ValueError, KeyError, struct.error) as error:
                    typed_by_key = None
                    record['typed_source_error'] = str(error)
            items = []
            source_count = 0
            grand_key_table = asset_type in ('MoleMole.GrandKeyAsset', 'MoleMole.GrandKeyBuffAsset')
            if grand_key_table:
                record['source_version_begin_counts'] = {}
            for source_index, row in enumerate(reader, 2):
                source_count += 1
                provenance = {'source_line': row.get('_source_line', source_index)}
                if '_source_path' in row:
                    provenance['source_path'] = row['_source_path']
                if row.get('_malformed') or None in row or any(value is None for value in row.values()):
                    record['malformed_rows'] += 1
                    record['conversion_errors'].append(dict(provenance, error='TSV column count mismatch'))
                    continue
                try:
                    if grand_key_table:
                        begin = row.get('GameVersionBegin', '')
                        record['source_version_begin_counts'][begin] = record['source_version_begin_counts'].get(begin, 0) + 1
                    if not in_version(row, version):
                        record['excluded_version'] += 1
                        continue
                    if not in_region(row, region):
                        record['excluded_region'] += 1
                        continue
                    item, chars = {}, []
                    for name, pointer in row_fields:
                        if name in record['missing_fields']:
                            continue
                        expanded = array_source(record['row_type'], name, row)
                        value = expanded[0] if expanded is not None else row[mapping[name]]
                        try:
                            converted = convert(value, pointer)
                        except ValueError:
                            if typed_by_key is None or type_info(pointer)['kind'] not in (0x11, 0x12, 0x15, 0x1d):
                                raise
                            source_key = convert(row[mapping[row_fields[0][0]]], row_fields[0][1])
                            source_value = typed_by_key[source_key][name]
                            converted = project_typed(source_value, pointer)
                            record['typed_composite_recoveries'].append(dict(provenance, field=name, source_primary_key=source_key))
                        if expanded is not None:
                            converted.insert(0, expanded[1])
                        if asset_type == 'MoleMole.CgDataAsset' and name == 'CgIconSpritePath':
                            original_name = original_cg_icon_name(converted)
                            record['field_semantic_adaptations'][0]['source_values'].append(
                                dict(provenance, cg_id=int(row[mapping['CgID']]),
                                     source_value=converted, output_value=original_name))
                            converted = original_name
                        if type_info(pointer)['kind'] == 0x03:
                            chars.append({'row': len(items), 'field': name, 'codepoint': ord(converted)})
                        else:
                            item[name] = converted
                    items.append(item)
                    record['char_fixups'].extend(chars)
                except (ValueError, KeyError, TypeError) as error:
                    record['conversion_errors'].append(dict(provenance, error=str(error)))
            if asset_type == 'MoleMole.AvatarSkillDataAsset':
                if typed_decoder is None:
                    typed_decoder = SourceTypedDecoder(package)
                additions = required_avatar_skill_rows(objects, by_path, typed_decoder, raw, row_fields,
                                                       mapping, text, version, region)
                if additions:
                    record['cross_version_dependency_rows'] = []
                    existing_ids = {item['skillId'] for item in items}
                    for converted, audit in additions:
                        if converted['skillId'] in existing_ids:
                            raise ValueError('Explicit compatibility skill would duplicate a retained row')
                        row_index = len(items)
                        for name, pointer in row_fields:
                            if type_info(pointer)['kind'] == 0x03:
                                record['char_fixups'].append({'row': row_index, 'field': name,
                                                              'codepoint': ord(converted[name])})
                        items.append({name: converted[name] for name, pointer in row_fields
                                      if type_info(pointer)['kind'] != 0x03})
                        record['cross_version_dependency_rows'].append(dict(audit, output_row_index=row_index))
                    record['cross_version_dependency_scope'] = {
                        'allowed_skill_ids': [52, 182], 'original_retained_rows_unchanged': True,
                        'source_version_exclusion_count_includes_these_rows': True,
                        'avatar_skillLists_unchanged': True,
                        'reason': 'Only actual missing skills referenced by retained avatars201/212; the source version filter remains unchanged for all other rows'}
            if asset_type == 'MoleMole.CabinLevelDataAsset':
                if typed_decoder is None:
                    typed_decoder = SourceTypedDecoder(package)
                additions = required_cabin_level_rows(typed_decoder, raw, row_fields, mapping, text,
                                                      version, region)
                if additions:
                    existing_keys = {(item['cabinType'], item['level']) for item in items}
                    if len(existing_keys) != len(items):
                        raise ValueError('Retained CabinLevel composite keys are not unique')
                    record['cross_version_dependency_rows'] = []
                    for converted, audit in additions:
                        key = (converted['cabinType'], converted['level'])
                        if key in existing_keys:
                            raise ValueError('Explicit CabinLevel dependency would duplicate a retained row')
                        record['cross_version_dependency_rows'].append(dict(audit, output_row_index=len(items)))
                        items.append(converted)
                        existing_keys.add(key)
                    if any((cabin_type, 1) not in existing_keys for cabin_type in range(1, 10)):
                        raise ValueError('Original nine-cabin level-one lookup closure is incomplete')
                    record['cross_version_dependency_scope'] = {
                        'allowed_composite_keys': [[1, 1], [3, 1], [4, 1], [5, 1]],
                        'original_retained_rows_unchanged': True,
                        'source_version_exclusion_count_includes_these_rows': True,
                        'required_level_one_keys_verified': [[cabin_type, 1] for cabin_type in range(1, 10)],
                        'cabin_levels_or_unlocks_changed': False,
                        'reason': 'Only four genuine missing level-one rows required by original InitCabinDict/GetUnlockPlayerLevel; normal filtering remains unchanged for all other rows'}
            if asset_type == 'MoleMole.TouchLevelDataAsset':
                if typed_decoder is None:
                    typed_decoder = SourceTypedDecoder(package)
                additions = required_touch_level_rows(typed_decoder, raw, row_fields, mapping, text,
                                                      version, region)
                if additions:
                    existing_levels = {item['level'] for item in items}
                    if len(existing_levels) != len(items):
                        raise ValueError('Retained TouchLevel keys are not unique')
                    record['cross_version_dependency_rows'] = []
                    for converted, audit in additions:
                        if converted['level'] in existing_levels:
                            raise ValueError('Explicit TouchLevel dependency would duplicate a retained row')
                        record['cross_version_dependency_rows'].append(dict(audit, output_row_index=len(items)))
                        items.append(converted)
                        existing_levels.add(converted['level'])
                    if any(level not in existing_levels for level in range(1, 6)):
                        raise ValueError('Native TouchLevel lookup closure is incomplete')
                    first_threshold = next(item['touchExp'] for item in items if item['level'] == 1)
                    record['cross_version_dependency_scope'] = {
                        'allowed_levels': [1, 2, 3, 4, 5],
                        'original_retained_rows_unchanged': True,
                        'source_version_exclusion_count_includes_these_rows': True,
                        'required_level_keys_verified': [1, 2, 3, 4, 5],
                        'zero_accumulated_feel_native_result': {
                            'first_touchExp': first_threshold, 'heart_level': 1, 'remaining_goodfeel': 0,
                            'evidence': 'Native ac361d initializes heartLevel1; ac3644 computes0-touchExp; ac3646 exits the level loop when negative'},
                        'account_feel_or_progress_changed': False,
                        'reason': 'Only five genuine source levels required by the native feel-level conversion/current-level lookup; normal filtering remains unchanged for all other rows'}
            if asset_type == 'MoleMole.StageData_MainAsset':
                # LevelModule.Init69124 in the original 1.9 binary requires
                # this exact key. It exists only in the inspected typed source,
                # so no TSV version/region columns can be claimed for it.
                required_key = 900302
                if not any(item.get('levelId') == required_key for item in items):
                    if typed_by_key is None or required_key not in typed_by_key:
                        record['conversion_errors'].append({'source_primary_key': required_key,
                                                            'error': 'Required original LevelModule key missing in typed source'})
                    else:
                        source_item = typed_by_key[required_key]
                        restored = {name: project_typed(source_item[name], pointer)
                                    for name, pointer in row_fields}
                        source_index, (start, end) = typed_spans[required_key]
                        items.append(restored)
                        record['typed_only_rows'] = [{'source_primary_key': required_key,
                                                      'source_row_index': source_index,
                                                      'source_byte_span': [start, end],
                                                      'source_row_sha256': hashlib.sha256(raw[start:end]).hexdigest(),
                                                      'fields': [name for name, _ in row_fields],
                                                      'excluded_source_fields': sorted(source_item.keys() - restored.keys()),
                                                      'source_version_region_metadata': 'Absent: this row is not present in the source TSV',
                                                      'retention_evidence': 'Original 1.9 LevelModule.Init69124@c10f2f reads key900302 at c1128b and passes it to LevelDataItem::.ctor68378@b9b7a5',
                                                      'historical_19_source_table_verified': False}]
            version_filtered_empty = (grand_key_table and source_count > 0 and not items and
                                      record['excluded_version'] == source_count and
                                      record['excluded_region'] == 0 and record['malformed_rows'] == 0 and
                                      not record['conversion_errors'])
            if version_filtered_empty:
                record['version_filtered_empty'] = {
                    'reason': 'All actual source rows are outside the target version; no row fields or historical values are fabricated',
                    'original_19_historical_table_restored': False,
                    'gameplay_restored': False,
                    'unavailable_historical_fields': list(record['missing_fields']),
                    'consumer_evidence': 'Original GrandKeyModule.Init@aec8b1 initializes its own collections and returns normally when the source List count is zero; GrandKeyBuffMetaDataReader.LoadFromFile@ae9fb6 also accepts zero rows',
                    'runtime_scope': 'Startup with the current account, which has no GrandKey data; positive-ID gameplay remains unverified and historical metadata is unavailable'}
            partial_random_dialog = (asset_type == 'MoleMole.RandomDialogDataAsset' and bool(items) and
                                     set(record['missing_fields']) == {'storyPicPath', 'gameId'} and
                                     not record['conversion_errors'] and record['malformed_rows'] == 0)
            if partial_random_dialog:
                ids = [item['dialogId'] for item in items]
                known_ids = set(ids)
                if len(known_ids) != len(ids):
                    raise ValueError('RandomDialogData source dialog IDs are not unique')
                links = [(item['dialogId'], predecessor) for item in items
                         for predecessor in item['preDialogIdList'] if predecessor != 0]
                record['partial_configuration'] = {
                    'provided_fields': [name for name, _ in row_fields if name not in record['missing_fields']],
                    'omitted_fields': list(record['missing_fields']),
                    'missing_field_values_fabricated': False,
                    'original_serializer_evidence': 'fsReflectedConverter.TryDeserialize@15bf8d0 skips an absent JSON key at15bfabd/15bfac4 without writing the field or reporting failure',
                    'initialization_evidence': 'IslandModule.InitIslandEventData uses dialogId, preDialogIdList and original postDialogList; it does not read storyPicPath or gameId. ContainsKey false atb52ddf/b52de6 skips an unavailable predecessor',
                    'original_19_historical_table_restored': False,
                    'unrestored_behavior': 'Historical story-image paths and game IDs are unavailable; corresponding original event behavior is not restored',
                    'unique_dialog_ids': len(known_ids),
                    'nonzero_predecessor_links': len(links),
                    'missing_predecessor_links_preserved': [{'dialogId': current, 'preDialogId': predecessor}
                                                            for current, predecessor in links
                                                            if predecessor not in known_ids]}
            invalid_cg_rows = asset_type == 'MoleMole.CgDataAsset' and bool(record['conversion_errors'])
            if (record['missing_fields'] and not version_filtered_empty and not partial_random_dialog) or (not items and record['conversion_errors']) or invalid_cg_rows:
                record.update(source_table=dict(table), source_text_sha256=hashlib.sha256(text).hexdigest(),
                              source_rows=source_count, converted_rows=len(items),
                              status=('failed: CG row conversion error' if invalid_cg_rows else
                                      'failed: missing original fields' if record['missing_fields'] else 'failed: no convertible source rows'))
                # Prior exports remain as historical evidence. The explicit
                # deployment_files list never includes these incompatible files.
                manifest['files'].append(record)
                continue
            if asset_type == 'MoleMole.StageData_MainAsset' and stage_ratios == 'repaired':
                from server19_stage_reward_compat import repair
                items, reward_changes = repair(items)
                if reward_changes:
                    record['reward_ratio_compatibility'] = {
                        'changes': reward_changes,
                        'reward_totals_unchanged': True,
                        'historical_19_values_recovered': False,
                        'reason': 'Approved adjacent-stage 0/0.7 split for six invalid 2.4 ratios'}
            encoded, compatibility_count = native_json(items)
            payload = (encoded + '\n').encode('utf-8')
            destination = output / asset['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            manifest['deployment_files'].append(asset['path'])
            char_fields = [name for name, pointer in row_fields if type_info(pointer)['kind'] == 0x03]
            if char_fields:
                by_row_field = {(fixup['row'], fixup['field']): fixup['codepoint'] for fixup in record['char_fixups']}
                chars = b''.join(struct.pack('<H', by_row_field[(index, field)])
                                 for field in char_fields for index in range(len(items)))
                char_destination = Path(str(destination) + '.chars')
                char_destination.write_bytes(chars)
                manifest['deployment_files'].append(asset['path'] + '.chars')
                record['char_file'] = {'output_file': asset['path'] + '.chars', 'encoding': 'UTF-16LE without BOM',
                                       'order': 'field first, then all rows for that field', 'field_order': char_fields,
                                       'row_count': len(items), 'bytes': len(chars),
                                       'sha256': hashlib.sha256(chars).hexdigest()}
            record.update(source_table=dict(table), source_text_sha256=hashlib.sha256(text).hexdigest(),
                          source_rows=source_count, output_rows=len(items), output_file=asset['path'],
                          output_sha256=hashlib.sha256(payload).hexdigest(), output_bytes=len(payload),
                          scientific_numbers_with_decimal_point_added=compatibility_count,
                          status=('version-filtered empty: original historical configuration unavailable'
                                  if version_filtered_empty else
                                  'partial' if record['missing_fields'] or record['conversion_errors'] else 'exported'))
            manifest['files'].append(record)
    manifest['missing_source_assets'] = [known[name] for name in sorted(known.keys() - matched)]
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--apk24', type=Path, default=resources.DEFAULT24)
    parser.add_argument('--version', default='1.9')
    parser.add_argument('--region', default='cn')
    parser.add_argument('--stage-ratios', choices=('baseline', 'repaired'), default='repaired',
                        help='baseline keeps the reference ratios; repaired applies the six-stage fix')
    args = parser.parse_args()
    result = export(args.output, args.apk24, version_tuple(args.version), args.region, args.stage_ratios)
    print(json.dumps({'files': len(result['files']), 'exported': sum('output_file' in row for row in result['files']),
                      'partial': sum(row.get('status') == 'partial' for row in result['files']),
                      'missing_source_assets': len(result['missing_source_assets'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
