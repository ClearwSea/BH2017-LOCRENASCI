"""Restore effective server tables from client inputs and explicit edit rules."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import zipfile

from .core import ROOT, BuildError, read_json, write_json


class SourceTables:
    def __init__(self, apk24, manifest):
        import server19_metadata_export as meta
        import server19_resources as resources
        self.meta, self.resources = meta, resources
        self.package = zipfile.ZipFile(apk24)
        self.mapping = {r['path']: r for r in resources.resource_map(apk24)}
        self.objects = meta.PackageObjects(self.package)
        self.decoder = meta.SourceTypedDecoder(self.package)
        self.kinds = {Path(r['output_file']).name: r for r in manifest['files'] if r.get('output_file')}

    def close(self):
        self.package.close()

    def typed(self, name, key, identities):
        kind = self.kinds[name]
        _, raw = self.objects.object(self.mapping['_exceloutputasset/' + name])
        rows = self.decoder.rows(raw, kind['row_type'])
        fields = self.meta.serialized_fields(kind['row_type_index'])
        selected = {r[key]: r for r in rows if r[key] in identities}
        if set(selected) != set(identities):
            raise BuildError('Missing source rows in ' + name)
        return [{n: self.meta.project_typed(selected[i][n], p) for n, p in fields} for i in identities]

    def tsv(self, name):
        _, raw = self.objects.object(self.mapping['data/_exceloutput/' + name])
        _, text = self.resources.text_asset(raw)
        return list(csv.DictReader(io.StringIO(text.decode('utf-8-sig')), delimiter='\t'))

    def projected_tsv(self, name, key=None, identities=None):
        kind = self.kinds[name]
        rows = self.tsv(name)
        fields = self.meta.serialized_fields(kind['row_type_index'])
        mapping = self.meta.column_mapping(kind['row_type_index'], list(rows[0]))
        output = []
        for row in rows:
            if identities is not None and int(row[mapping[key]]) not in identities:
                continue
            item = {}
            for field, pointer in fields:
                expanded = self.meta.array_source(kind['row_type'], field, row)
                value = expanded[0] if expanded is not None else row[mapping[field]]
                item[field] = self.meta.convert(value, pointer)
                if expanded is not None:
                    item[field].insert(0, expanded[1])
            output.append(item)
        return output


def complete_stigmata_evolution(stigmata, source_stigmata):
    """Close retained items' evolution chains without widening the version filter."""
    result = deepcopy(stigmata)
    present = {row['ID'] for row in result}
    source = {row['ID']: row for row in source_stigmata}
    for row in result:
        target = row.get('evoID', 0)
        if target > 0 and target not in present:
            if target not in source:
                raise BuildError('Missing source stigmata evolution: ' + str(target))
            result.append(deepcopy(source[target]))
            present.add(target)
    by_id = {row['ID']: row for row in result}
    for row in result:
        seen = set()
        while row.get('evoID', 0) > 0:
            if row['ID'] in seen:
                raise BuildError('Cyclic stigmata evolution: ' + str(row['ID']))
            seen.add(row['ID'])
            row = by_id[row['evoID']]
    return result


def complete_stigmata_positions(stigmata, positions, source_positions):
    """Close retained stigmata's artwork dependencies using real source layouts.

    Some 2.4 layout rows carry later version tags although retained 1.9
    stigmata already reference them. Do not broaden the equipment version filter
    or replace artwork with another item's picture.
    """
    present = {row['name'] for row in positions}
    required = {row['imagePath'] for row in stigmata} - present
    candidates = {row['name']: row for row in source_positions if row['name'] in required}
    missing = required - candidates.keys()
    if missing:
        raise BuildError('Missing source stigmata layouts: ' + ', '.join(sorted(missing)))
    return deepcopy(positions) + [deepcopy(candidates[name]) for name in sorted(required)]


def restore(apk24, data_work, output):
    base = data_work / 'generated/tables/_exceloutputasset'
    tables = {p.name: read_json(p) for p in base.iterdir() if p.is_file() and not p.name.endswith('.chars')}
    manifest = read_json(data_work / 'generated/base-tables/manifest.json')
    rules = read_json(ROOT / 'rules/table-adaptations.json')
    daily = read_json(ROOT / 'rules/daily-missions.json')['rules']
    source = SourceTables(apk24, manifest)
    try:
        for name, key, ids in (('avatardata', 'avatarID', [503]),
                               ('materialdata', 'ID', [3108]),
                               ('avatarfragmentdata', 'ID', [10601, 10603])):
            tables[name].extend(source.typed(name, key, ids))
        tables['avatardata'].sort(key=lambda r: r['avatarID'])
        # 10661 survives the 1.9 filter but its target 10662 is tagged 2.2+.
        # Its TeamPanel/Team/2 widget and row fields exist in original 1.9.
        # Restore the source completion step instead of leaving a dangling edge.
        if not any(row['id'] == 10662 for row in tables['tutorialstepdata']):
            tables['tutorialstepdata'].extend(
                source.projected_tsv('tutorialstepdata', 'id', [10662]))

        tables['stigmatadata'].extend(source.projected_tsv('stigmatadata', 'ID', [30034, 30087]))
        tables['stigmatadata'] = complete_stigmata_evolution(
            tables['stigmatadata'], source.projected_tsv('stigmatadata'))
        original_positions = {row['name'] for row in tables['stigmatapositiondata']}
        tables['stigmatapositiondata'] = complete_stigmata_positions(
            tables['stigmatadata'], tables['stigmatapositiondata'],
            source.projected_tsv('stigmatapositiondata'))
        layout_dependencies = [
            {key: row[key] for key in ('name', 'GameVersionBegin', 'GameVersionEnd', 'EffectRegionList')}
            for row in source.tsv('stigmatapositiondata')
            if row['name'] not in original_positions
            and row['name'] in {item['name'] for item in tables['stigmatapositiondata']}]
        cabins = []
        for row in source.tsv('cabinleveldata'):
            items = [{'itemMetaID': int(s.split(':')[0]), 'itemNum': int(s.split(':')[1])}
                     for s in row['itemListNeed'].split(',') if ':' in s]
            cabins.append(dict(cabinType=int(row['cabinType']), cabinName=row['cabinName'],
                level=int(row['level']), playerLevelNeed=int(row['playerLevelNeed']),
                scoinNeed=int(row['scoinNeed'] or 0), itemListNeed=items or [{'itemMetaID': 0, 'itemNum': 0}],
                upLevelTimeNeed=int(row['upLevelTimeNeed'] or 0)))
        tables['cabinleveldata'] = cabins
        for row in tables['constvaluesclient']:
            if row['name'] in ('IsExtraActHide', 'MainPageShowEquipmentUp'):
                row['value'] = 'false'
        for row in tables['newbieguidetutorial']:
            row['unlockStageID'] = 0
        for row in tables['touchdata']:
            if row['touchId'] % 100 == 2:
                row['point'] = {1: 300, 2: 500, 3: 1000, 4: 3000, 5: 0}.get(row['level'], 0)
            elif row['level'] >= 5:
                row['point'] = 0
        for row in tables['touchleveldata']:
            row['rate'] = 0.0
        tables['dutydailydata'] = deepcopy(daily['DUTY_DAILY_DATA'])
        tables['missiondata'].append(deepcopy(daily['NEW_MISSION']))
        tables['rewarddata'].append(deepcopy(daily['NEW_REWARD']))
        # Edits carry only changed fields. Cross-version rows are projected above.
        for name, edit in rules['edits'].items():
            key = edit['key']
            by_id = {r[key]: r for r in tables[name]}
            original_rows = deepcopy(by_id)
            for row in edit['rows']:
                identity = row['id']
                if identity not in by_id:
                    raise BuildError('Edit refers to missing row: ' + name + ':' + str(identity))
                for field, value in row['set'].items():
                    if isinstance(value, dict) and '$source_field' in value:
                        from_id, from_field = value['$source_field']
                        value = original_rows[from_id][from_field]
                    by_id[identity][field] = deepcopy(value)
        for spec in rules['shop_additions']:
            template = deepcopy(tables['shopgoodsdata'][0])
            template.update(spec)
            tables['shopgoodsdata'].append(template)
        # Resolve text from the supplied 2.4 TSVs; project-authored wording is separate.
        text = {r['ID']: r for r in tables['textmap']}
        _, raw = source.objects.object(source.mapping['_exceloutputasset/textmap'])
        rows, _ = source.meta.text_map_sources(source.objects, list(source.mapping.values()), raw)
        texts24 = {(r['_source_path'], r['_source_line']): r for r in rows}
        for identity, spec in rules['text_edits'].items():
            value = spec.get('authored')
            if 'source_path' in spec:
                try:
                    row = texts24[(spec['source_path'], spec['source_line'])]
                    if row['ID'] != identity:
                        raise BuildError('Source text identity differs: ' + identity)
                    value = row['Text']
                except KeyError as error:
                    raise BuildError('Missing source text: ' + identity) from error
            text[identity] = {'ID': identity, 'Text': value}
        tables['textmap'] = list(text.values())
        output.mkdir(parents=True, exist_ok=False)
        for name, rows in tables.items():
            # Keep the original native float encoding, including exponent literals.
            encoded, _ = source.meta.native_json(rows)
            (output / name).write_text(encoded + '\n', encoding='utf-8')
        chars = base / 'avatarskilldata.chars'
        (output / chars.name).write_bytes(chars.read_bytes())
    finally:
        source.close()
    return {'tables': len(tables), 'material_rows': len(tables['materialdata']),
            'stigmata_layout_dependencies': layout_dependencies,
            'source': 'original-client-inputs-and-project-rules'}
