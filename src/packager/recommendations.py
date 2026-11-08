"""Keep backported avatar recommendations within the retained equipment set."""
from copy import deepcopy
import csv
import io

from .core import BuildError


def sync_tsv(raw, equipment):
    """Keep the fallback text asset consistent with the effective JSON table."""
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter='\t')
    rows = list(reader)
    updates = {r['equipAdvID']: r for r in equipment}
    for row in rows:
        current = updates.get(int(row['EquipAdvID']))
        if current:
            for field, value in current.items():
                column = field[0].upper() + field[1:]
                if column in row:
                    row[column] = str(value)
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8')


def adapt(tables, rules):
    original = {r['equipAdvID']: r for r in tables['newbieequipadv']}
    result = deepcopy(original)
    for edit in rules['equipment']:
        row = result[edit['id']]
        for kind, fields in (
            ('weapon', ('weaponAdvID', 'weaponAdvText')),
            ('stigmata', ('stigmataAdv1ID', 'stigmataAdv2ID',
                          'stigmataAdv3ID', 'stigmataAdvText')),
        ):
            if kind + '_from' in edit:
                donor = original[edit[kind + '_from']]
                for field in fields:
                    row[field] = donor[field]
    tables['newbieequipadv'] = list(result.values())
    validate(tables)


def validate(tables):
    weapons = {r['ID']: r for r in tables['weapondata']}
    stigmata = {r['ID']: r for r in tables['stigmatadata']}
    avatars = {r['avatarID']: r for r in tables['avatardata']}
    equipment = {r['equipAdvID']: r for r in tables['newbieequipadv']}
    groups = {r['groupAdvID']: r for r in tables['newbiegroupadv']}
    effects = {r['effectID'] for r in tables['avatareffectinfo']}
    text = {r['ID'] for r in tables['textmap']}
    errors = []
    for key, row in equipment.items():
        weapon = weapons.get(row['weaponAdvID'])
        avatar = avatars.get(key // 10)
        if not weapon or not avatar or weapon['baseType'] not in avatar['weaponBaseTypeList']:
            errors.append(f'equipment {key}: incompatible weapon')
        for slot in (1, 2, 3):
            item = stigmata.get(row[f'stigmataAdv{slot}ID'])
            if not item or item['baseType'] != slot:
                errors.append(f'equipment {key}: missing/wrong-position stigmata {slot}')
        for field in ('weaponAdvText', 'stigmataAdvText'):
            if row[field] not in text:
                errors.append(f'equipment {key}: missing {field}')
    for key, row in groups.items():
        if row['groupAvatarID'] not in avatars or row['recommendText'] not in text:
            errors.append(f'group {key}: missing avatar/text')
    for row in tables['newbieavatarguide']:
        key = row['avatarID']
        if key not in avatars:
            errors.append(f'guide {key}: missing avatar')
        for field in ('EquipAdvNewbieID', 'EquipAdvSuperiorID'):
            if row[field] not in equipment:
                errors.append(f'guide {key}: missing {field}')
        if not set(row['groupAdvsID']) <= groups.keys():
            errors.append(f'guide {key}: missing group')
        if not set(row['avatarEffects']) <= effects:
            errors.append(f'guide {key}: missing effect')
        # Optional brief text is absent for some source avatars. It is resolved
        # by the client's string fallback, unlike dereferenced gear/guide rows.
    if errors:
        raise BuildError('Invalid avatar recommendations: ' + '; '.join(errors))
