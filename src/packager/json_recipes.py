"""Source-referenced JSON selection and sparse edits; no embedded game tables."""
from copy import deepcopy
from .core import BuildError


def render(recipe, sources):
    if isinstance(recipe, dict):
        if set(recipe) == {'@text'}:
            original, pieces = recipe['@text']
            original = render(original, sources)
            return ''.join(original[piece[0]:piece[1]] if isinstance(piece, list) else piece for piece in pieces)
        if set(recipe) == {'@concat'}:
            return [value for section in recipe['@concat'] for value in render(section, sources)]
        if set(recipe) == {'@select'}:
            name, path, indices = recipe['@select']
            values = render({'@ref': [name, path]}, sources)
            return [values[i] for i in indices]
        if set(recipe) == {'@ref'}:
            name, path = recipe['@ref']
            try:
                value = sources[name]
                for key in path:
                    value = value[key]
            except (KeyError, IndexError, TypeError) as error:
                raise BuildError('JSON recipe source is unavailable: ' + name) from error
            return deepcopy(value)
        if set(recipe) == {'@merge'}:
            base, changes, removed = recipe['@merge']
            value = render(base, sources)
            if not isinstance(value, dict):
                raise BuildError('JSON recipe merge requires an object')
            for key in removed:
                del value[key]
            value.update({k: render(v, sources) for k, v in changes.items()})
            return value
        return {k: render(v, sources) for k, v in recipe.items()}
    if isinstance(recipe, list):
        return [render(v, sources) for v in recipe]
    return recipe


def sources(data_work, effective, apk24):
    from pathlib import Path
    from .core import ROOT, read_json
    from .tables import SourceTables
    result = {}
    for label, root in (('base', data_work / 'generated/tables/_exceloutputasset'), ('server', effective)):
        for path in root.iterdir():
            if path.is_file() and not path.name.endswith('.chars'):
                result[label + '/' + path.name] = read_json(path)
    source = SourceTables(apk24, read_json(data_work / 'generated/base-tables/manifest.json'))
    try:
        for name in ('monsterconfigdata', 'uniquemonsterdata', 'endlessitem', 'equipmentskilldata'):
            result['unfiltered/' + name] = source.projected_tsv(name)
        _, raw = source.objects.object(source.mapping['_baked/stringmap'])
        reader = source.resources.Reader(raw, 28)
        reader.string()
        result['source/stringmap'] = [reader.string() for _ in range(reader.read('i'))]
        result['source/resource_paths'] = [r['path'] for r in source.mapping.values()]
        _, raw = source.objects.object(source.mapping['_exceloutputasset/textmap'])
        rows, _ = source.meta.text_map_sources(source.objects, list(source.mapping.values()), raw)
        result['source/textmap_rows'] = [{'ID': r['ID'], 'Text': r['Text']} for r in rows]
    finally:
        source.close()
    # Reward payloads are joined from original reward columns, not stored snapshots.
    def reward(row):
        fields = {'exp': 'RewardExp', 'scoin': 'RewardSCoin', 'hcoin': 'RewardHCoin',
                  'stamina': 'RewardStamina', 'skill_point': 'RewardSkillPoint',
                  'friends_point': 'RewardFriendPoint', 'duty_point': 'RewardDutyPoint'}
        value = {name: row.get(field, 0) for name, field in fields.items()}
        value['item_list'] = [{'id': row['RewardItem%dID' % i],
                              'level': row['RewardItem%dLevel' % i],
                              'num': row['RewardItem%dNum' % i]}
                             for i in range(1, 6) if row.get('RewardItem%dID' % i) and row.get('RewardItem%dNum' % i)]
        return value
    result['derived/rewards'] = {str(r['RewardID']): reward(r) for r in result['server/rewarddata']}
    result['rule/commission-rarity'] = read_json(ROOT / 'rules/commission-rarity.json')['rows']
    result['rule/endless-bot-names'] = read_json(ROOT / 'rules/endless-bot-names.json')['names']
    return result
