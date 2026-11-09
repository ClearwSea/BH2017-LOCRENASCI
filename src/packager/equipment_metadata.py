"""Complete skill descriptions referenced by retained equipment rows."""
from copy import deepcopy
from .core import BuildError


def complete(tables, source_rows, source_text_rows=None):
    rows = tables['equipmentskilldata']
    present = {row['ID'] for row in rows}
    source = {row['ID']: row for row in source_rows}
    required = {row[key] for name in ('weapondata', 'stigmatadata', 'equipmentsetdata')
                for row in tables[name] for key in ('prop1ID', 'prop2ID', 'prop3ID')
                if row.get(key, 0)}
    missing = sorted(required - present)
    unavailable = set(missing) - source.keys()
    if unavailable:
        raise BuildError('Missing source equipment skill metadata: ' + str(sorted(unavailable)))
    text_additions = []
    if source_text_rows is not None:
        existing_text = {row['ID'] for row in tables['textmap']}
        source_text = {row['ID']: row for row in source_text_rows}
        for key in missing:
            for field in ('skillName', 'skillDisplay'):
                text_key = source[key][field]
                if text_key not in existing_text:
                    if text_key not in source_text:
                        if field != 'skillName':
                            raise BuildError('Missing source equipment skill text: ' + text_key)
                        text_additions.append({'ID': text_key, 'Text': '技能 ' + str(key)})
                    else:
                        text_additions.append(deepcopy(source_text[text_key]))
                    existing_text.add(text_key)
    rows.extend(deepcopy(source[key]) for key in missing)
    if source_text_rows is not None:
        tables['textmap'].extend(text_additions)
    return missing
