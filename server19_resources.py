"""Static 1.9/2.4 Unity resource inspection; no client or reference server execution.

Uses the source APKs under .local-baseline. Native initialization objects are
never constructed by this helper. Source packages remain read-only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import zipfile

ROOT = Path(__file__).resolve().parent
DEFAULT19 = ROOT / 'inputs/client-1.9.apk'
DEFAULT24 = ROOT / 'inputs/client-2.4.apk'


class Reader:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def read(self, fmt):
        value = struct.unpack_from('<' + fmt, self.data, self.pos)
        self.pos += struct.calcsize('<' + fmt)
        return value[0] if len(value) == 1 else value

    def align(self):
        self.pos = (self.pos + 3) & ~3

    def zero_string(self):
        end = self.data.index(0, self.pos)
        value = self.data[self.pos:end].decode('utf-8')
        self.pos = end + 1
        return value

    def string(self):
        size = self.read('i')
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError('Invalid Unity string length')
        value = self.data[self.pos:self.pos + size].decode('utf-8')
        self.pos += size
        self.align()
        return value


def serialized(data):
    metadata_size, file_size, version, data_offset = struct.unpack_from('>4I', data)
    if file_size != len(data) or version not in (15, 17) or data[16] != 0:
        raise ValueError('Unsupported serialized file header')
    r = Reader(data, 20)
    unity, platform, trees = r.zero_string(), r.read('i'), r.read('B')
    types = []
    for _ in range(r.read('i')):
        start = r.pos
        class_id = r.read('i')
        if version == 17:
            r.read('B')
            script_index = r.read('h')
            if class_id == 114:
                r.pos += 16
        else:
            script_index = None
            if class_id < 0:
                r.pos += 16
        r.pos += 16
        if trees:
            nodes, strings = r.read('ii')
            r.pos += nodes * 24 + strings
        types.append({'class': class_id, 'script_index': script_index, 'raw': data[start:r.pos]})
    object_count_at = r.pos
    objects = {}
    for _ in range(r.read('i')):
        r.align()
        start = r.pos
        path_id, offset, size, type_id = r.read('qIIi')
        if version == 15:
            class_id, script_index, stripped = r.read('hhB')
        else:
            class_id = types[type_id]['class']
            script_index, stripped = types[type_id]['script_index'], None
        objects[path_id] = {'offset': data_offset + offset, 'size': size,
                            'class': class_id, 'type_id': type_id,
                            'script_index': script_index, 'stripped': stripped,
                            'record_at': start, 'record_end': r.pos}
    scripts_at = r.pos
    scripts = []
    for _ in range(r.read('i')):
        file_id = r.read('i')
        r.align()
        scripts.append((file_id, r.read('q')))
    externals = []
    for _ in range(r.read('i')):
        r.zero_string()
        r.pos += 20
        externals.append(r.zero_string())
    return {'version': version, 'unity': unity, 'platform': platform,
            'metadata_size': metadata_size, 'data_offset': data_offset,
            'types': types, 'objects': objects, 'scripts': scripts,
            'externals': externals, 'object_count_at': object_count_at,
            'scripts_at': scripts_at, 'metadata_end': r.pos}


def resource_map(apk):
    with zipfile.ZipFile(apk) as package:
        data = package.read('assets/bin/Data/globalgamemanagers')
        info = serialized(data)
        resources = [o for o in info['objects'].values() if o['class'] == 147]
        if len(resources) != 1:
            raise ValueError('Expected one ResourceManager object')
        r = Reader(data, resources[0]['offset'])
        result = []
        for _ in range(r.read('i')):
            name = r.string()
            file_id, path_id = r.read('iq')
            filename = info['externals'][file_id - 1] if file_id else 'globalgamemanagers'
            result.append({'path': name, 'file_id': file_id, 'path_id': path_id,
                           'file': filename.rsplit('/', 1)[-1]})
        if r.pos > resources[0]['offset'] + resources[0]['size']:
            raise ValueError('ResourceManager object overrun')
        return result


def object_bytes(package, record):
    data = package.read('assets/bin/Data/' + record['file'])
    info = serialized(data)
    obj = info['objects'][record['path_id']]
    return obj, data[obj['offset']:obj['offset'] + obj['size']]


def text_asset(raw):
    r = Reader(raw)
    name = r.string()
    size = r.read('i')
    if size < 0 or r.pos + size > len(raw):
        raise ValueError('Invalid TextAsset length')
    return name, raw[r.pos:r.pos + size]


def strip_json_comments(text):
    # A lexer preserves quoted URLs and escaped strings; comments/trailing commas
    # are source formatting, not a reason to replace missing values.
    import re
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else '', text)
    return re.sub(r',\s*([}\]])', r'\1', text)


def inventory(apk19=DEFAULT19, apk24=DEFAULT24):
    old, reference = resource_map(apk19), resource_map(apk24)
    old_paths = {r['path'] for r in old}
    wanted = [r for r in reference if r['path'].startswith(('_baked/', 'data/'))]
    summary = []
    with zipfile.ZipFile(apk24) as package:
        for rec in wanted:
            obj, raw = object_bytes(package, rec)
            item = dict(rec, **{'class': obj['class'], 'bytes': len(raw),
                               'sha256': hashlib.sha256(raw).hexdigest(),
                               'present_in_19': rec['path'] in old_paths})
            if obj['class'] == 49:
                name, text = text_asset(raw)
                item.update(name=name, text_bytes=len(text))
            summary.append(item)
    return {'source19': str(apk19), 'source24': str(apk24),
            'count19': len(old), 'count24': len(reference), 'configuration24': summary}


def native_fields(type_name):
    import analyze19 as a
    ti = next(i for i in range(len(a.T)) if a.type_name(i) == type_name)
    t = a.T[ti]
    return [(a.string(struct.unpack_from('<4I', a.B, 9233316 + i * 16)[0]),
             struct.unpack_from('<4I', a.B, 9233316 + i * 16)[1])
            for i in range(t[16], t[16] + t[26])]


BOOTSTRAP_JSON = {
    'data/ai/groupai/groupaigrid_dg': 'MoleMole.Config.ConfigGroupAIGridEntry',
    'data/ai/groupai/groupaigrid_ms': 'MoleMole.Config.ConfigGroupAIGridEntry',
    'data/ai/groupai/groupaigrid_ul': 'MoleMole.Config.ConfigGroupAIGridEntry',
    'data/_bothlocalandassetbundle/graphicssettingconfig/volatilesetting': 'MoleMole.Config.ConfigGraphicsVolatileSetting',
    'data/effectpatternnames/testpreloadpattern1': 'MoleMole.Config.ConfigEffectPatternNames',
    'data/wwiseaudio/loopeventpair': 'MoleMole.Config.ConfigEventLoopPair',
}

# The original UI design module requests the configured entry script. Its
# actual source requires Base/Inspect; supply both files without rewriting any
# Lua callbacks. Later-source script behavior still needs native-flow checks.
BOOTSTRAP_LUA = {
    'lua/ui/uiluadesign.lua': ['Base/Inspect'],
    'lua/base/inspect.lua': [],
}

BOOTSTRAP_TEXT = {'data/agreement1', 'data/agreement2'}


def bootstrap_schema(path, value):
    """Report static source shape against actual 1.9 declarations, not runtime success."""
    target = BOOTSTRAP_JSON[path]
    names = {name for name, _ in native_fields(target)}
    check = {'target_type19': target, 'declared_fields19': sorted(names),
             'runtime_compatibility': 'not yet verified'}
    if value is None:
        check['source_check'] = 'not inspected: source JSON has a syntax error'
        return check
    if target.endswith('ConfigEventLoopPair'):
        check['original_parent_type'] = 'System.Collections.Generic.Dictionary<string,string>'
        check['source_root_shape'] = 'object' if isinstance(value, dict) else type(value).__name__
        check['source_rows'] = len(value) if isinstance(value, dict) else None
        check['shape_issues'] = ([] if isinstance(value, dict) and
                                 all(isinstance(key, str) and isinstance(item, str)
                                     for key, item in value.items()) else
                                 [{'error': 'Expected a JSON object of string keys and string values'}])
        return check
    records = list(value.values()) if isinstance(value, dict) else value
    check['source_root_shape'] = 'object' if isinstance(value, dict) else 'array'
    check['source_rows'] = len(records)
    extra = set()
    issues = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            issues.append({'row': index, 'error': 'Expected source config object'})
            continue
        extra.update(key for key in item if key not in names and not key.startswith('$'))
        if target.endswith('ConfigEffectPatternNames'):
            if not isinstance(item.get('Name'), str) or not isinstance(item.get('PatternNames'), list) or not all(isinstance(name, str) for name in item.get('PatternNames', [])):
                issues.append({'row': index, 'error': 'Expected Name:string and PatternNames:string[]'})
        elif target.endswith('ConfigGraphicsVolatileSetting'):
            for key, data in item.items():
                if key in names - {'PostFXGrade'} and not isinstance(data, bool):
                    issues.append({'row': index, 'field': key, 'error': 'Expected Boolean'})
            if 'PostFXGrade' in item and item['PostFXGrade'] not in {name for name, _ in native_fields('MoleMole.Config.PostEffectQualityGrade')}:
                issues.append({'row': index, 'field': 'PostFXGrade', 'error': 'Unknown original enum name'})
        elif target.endswith('ConfigGroupAIGridEntry'):
            if not isinstance(item.get('Name'), str) or not isinstance(item.get('LeaderActions'), dict) or not isinstance(item.get('Minions'), list):
                issues.append({'row': index, 'error': 'Expected Name:string, LeaderActions:object, Minions:array'})
    check['source_fields_absent_in19'] = sorted(extra)
    check['shape_issues'] = issues
    if target.endswith('ConfigGroupAIGridEntry'):
        minion_fields = {name for name, _ in native_fields('MoleMole.Config.ConfigGroupAIMinion')}
        source_fields = {key for item in records if isinstance(item, dict)
                         for minion in item.get('Minions', []) if isinstance(minion, dict)
                         for key in minion if not key.startswith('$')}
        check['minion_declared_fields19'] = sorted(minion_fields)
        check['minion_source_fields_absent_in19'] = sorted(source_fields - minion_fields)
    return check


def export_text_resources(output, apk24=DEFAULT24, apk19=DEFAULT19):
    """Export verified bootstrap text and raw tables, preserving source metadata.

    The native loaders consume JSON and Lua through their original parsers.
    This exporter does not execute scripts or populate any runtime state.
    """
    output = Path(output)
    paths = resource_map(apk24)
    original_paths = {record['path']: record for record in resource_map(apk19)}
    whitelist = {'common/metaconfig', 'data/miscdata', 'data/channelsettings',
                 'data/luahackconfig', 'data/_bothlocalandassetbundle/iphonexdata',
                 'data/_bothlocalandassetbundle/localdataversion',
                 'data/_bothlocalandassetbundle/graphicssettingconfig/volatilesetting',
                 'data/wwiseaudio/loopeventpair',
                 'data/ai/groupai/groupaigrid_dg', 'data/ai/groupai/groupaigrid_ms',
                 'data/ai/groupai/groupaigrid_ul'}
    whitelist.update(BOOTSTRAP_LUA)
    whitelist.update(BOOTSTRAP_TEXT)
    target_fields = {name for name, _ in native_fields('MoleMole.ConfigMisc')}
    result = {'source': str(apk24), 'source19': str(apk19), 'files': [], 'misc_missing_fields': [],
              'deployment_files': [], 'reference_only_files': []}
    with zipfile.ZipFile(apk24) as package, zipfile.ZipFile(apk19) as original_package:
        for rec in paths:
            path = rec['path']
            if path not in whitelist and not path.startswith(('data/_exceloutput/', 'data/effectpatternnames/')):
                continue
            obj, raw = object_bytes(package, rec)
            if obj['class'] != 49:
                continue
            name, text = text_asset(raw)
            original = text
            if path == 'data/miscdata':
                source = json.loads(strip_json_comments(text.decode('utf-8')))
                result['misc_missing_fields'] = sorted(target_fields - source.keys())
                source = {k: v for k, v in source.items() if k in target_fields}
                # Existing cross-version evidence only verifies pages 0..3.
                # Retain the native first four entries; no later page-enum claims.
                source['PageAvatarShowInfo'] = source['PageAvatarShowInfo'][:4]
                text = json.dumps(source, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            dest = output / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(text)
            record = dict(rec, name=name, bytes=len(text),
                          present_in_19=path in original_paths,
                          source_text_sha256=hashlib.sha256(original).hexdigest(),
                          output_sha256=hashlib.sha256(text).hexdigest())
            if path in BOOTSTRAP_LUA:
                text.decode('utf-8')
                record['lua_source'] = {
                    'required_modules': BOOTSTRAP_LUA[path],
                    'source_bytes_preserved': text == original,
                    'exporter_executes_script': False,
                    'historical_19_script_verified': False,
                    'runtime_compatibility': 'Requires original loader and callback verification',
                    'consumer_evidence': 'Original UI Lua initializer requests Lua/UI/UILuaDesign.lua; native missing-resource trace d1f5cf->1426389 in PID13699',
                }
            if path in BOOTSTRAP_TEXT:
                text.decode('utf-8')
                record['plain_text_source'] = {
                    'encoding': 'UTF-8',
                    'source_bytes_preserved': text == original,
                    'historical_19_text_verified': False,
                    'runtime_compatibility': 'Requires original agreement dialog verification',
                    'consumer_evidence': 'Original agreement dialog text loader; native missing-resource trace Data/Agreement1 d1f5cf->54684d in PID14262',
                }
            if path in BOOTSTRAP_JSON:
                value = None
                try:
                    value = json.loads(strip_json_comments(text.decode('utf-8')))
                    record['json_check'] = 'valid after removing source comments and trailing commas'
                except json.JSONDecodeError as error:
                    record['json_check'] = 'source syntax unverified by native parser; exported without repairs'
                    record['json_error'] = {'line': error.lineno, 'column': error.colno, 'reason': error.msg}
                record['schema19'] = bootstrap_schema(path, value)
            if path in BOOTSTRAP_JSON and path in original_paths:
                old_obj, old_raw = object_bytes(original_package, original_paths[path])
                if old_obj['class'] == 49:
                    _, old_text = text_asset(old_raw)
                    record['original19_text_sha256'] = hashlib.sha256(old_text).hexdigest()
                    record['byte_identical_to19'] = old_text == original
                record['deployment_role'] = 'reference only: use the existing original 1.9 asset'
                result['reference_only_files'].append(path)
            else:
                record['deployment_role'] = 'configuration fallback'
                result['deployment_files'].append(path)
            result['files'].append(record)
    (output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk19', type=Path, default=DEFAULT19)
    parser.add_argument('--apk24', type=Path, default=DEFAULT24)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    if args.export:
        result = export_text_resources(args.export, args.apk24, args.apk19)
        print(json.dumps({'exported': len(result['files']), 'misc_missing_fields': result['misc_missing_fields']}, ensure_ascii=False))
        return
    result = inventory(args.apk19, args.apk24)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('count19', 'count24')}, ensure_ascii=False))
    print('\n'.join(f"{r['path']} class={r['class']} bytes={r['bytes']} present19={r['present_in_19']}"
                    for r in result['configuration24'] if r['path'].startswith('_baked/') or
                    r['path'] in ('data/miscdata', 'data/metaconfig', 'data/localdataversion')))


if __name__ == '__main__':
    main()
