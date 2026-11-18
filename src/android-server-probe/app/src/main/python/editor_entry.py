"""Android save editor bridge. Work is performed on an isolated account copy."""
import json
import os
from pathlib import Path
import tempfile
import threading

CATALOG = None
_CONFIG_DIRECTORY = None
_CATALOG_LOCK = threading.RLock()


def _strings(value, found):
    if isinstance(value, dict):
        for item in value.values():
            _strings(item, found)
    elif isinstance(value, list):
        for item in value:
            _strings(item, found)
    elif isinstance(value, str):
        found.add(value)


def _view_catalog(catalog, account):
    """Send the Java screen only fields it renders; validation uses full tables."""
    fields = {
        'avatardata': ('avatarID', 'fullName', 'unlockStar', 'avatarFragmentID', 'skillList'),
        'avatarsubskilldata': ('skillId', 'avatarSubSkillId', 'name', 'maxLv'),
        'dressdata': ('dressID', 'name', 'avatarIDList', 'dressType'),
        'weapondata': ('ID', 'displayTitle', 'maxLv', 'evoID', 'evoMaterial', 'expType', 'baseType'),
        'stigmatadata': ('ID', 'displayTitle', 'maxLv', 'evoID', 'evoMaterial', 'expType', 'baseType', 'setID'),
        'materialdata': ('ID', 'displayTitle', 'ItemType', 'quantityLimit'),
        'equipmentleveldata': ('level', 'Type1'),
        'playerleveldata': ('level', 'avatarLevelLimit'),
        'avatarfragmentdata': ('ID', 'quantityLimit'),
        'cabintechtreedata': ('Cabin', 'X', 'Y', 'AbilityType', 'UnlockLevel', 'Argument1', 'Title'),
        'stages': ('id', 'kind', 'difficulty', 'editor_chapter_id', 'display_name'),
    }
    result = {name: [{key: row[key] for key in keys if key in row} for row in catalog[name]]
              for name, keys in fields.items()}
    result['sakura'] = {'stories': [{'Cycle': row['Cycle'], 'StoryID': row['StoryID']}
                                     for row in catalog['sakura']['stories']]}
    result['abyss_floors'] = catalog['abyss_floors']
    result['material_presets'] = catalog['material_presets']
    referenced = set()
    _strings(result, referenced)
    result['textmap'] = [row for row in catalog['textmap'] if row.get('ID') in referenced]
    import server19_editor_captain as captain
    result['captain_limits'] = captain.limits(account, catalog)
    return result


def _catalog(context):
    global CATALOG, _CONFIG_DIRECTORY
    with _CATALOG_LOCK:
        if CATALOG is not None:
            return CATALOG
        files = Path(str(context.getFilesDir().getAbsolutePath()))
        from probe_entry import extract_runtime
        files, runtime, _ = extract_runtime(context)
        os.environ['BH3_PACKAGED_NATIVE_LIBRARY'] = str(context.getApplicationInfo().nativeLibraryDir) + '/libil2cpp.so'
        # An editor-only empty directory remains alive for the process lifetime.
        # portable.configure may initialize/migrate its account, never the user's.
        directory = tempfile.TemporaryDirectory(prefix='editor-config-', dir=str(files))
        _CONFIG_DIRECTORY = directory
        import server19_portable as portable
        portable.configure(Path(directory.name))
        import server19_stage as stage
        import server19_editor_progress as progress
        catalog = progress.catalog_from_configured_runtime()
        names = ('avatardata', 'avatarsubskilldata', 'avatarexdata', 'dressdata',
                 'weapondata', 'stigmatadata', 'materialdata', 'equipmentleveldata',
                 'avatarleveldata', 'playerleveldata', 'avatarfragmentdata',
                 'cabinleveldata', 'cabinextendgradedata', 'cabintechtreedata')
        catalog.update({name: stage._table(name) for name in names})
        # Send only text IDs referenced by these tables through the Java bridge.
        # The full source textmap remains in the configured runtime itself.
        referenced = set()
        _strings(catalog, referenced)
        catalog['textmap'] = [row for row in stage._table('textmap') if row.get('ID') in referenced]
        import server19_editor_material_presets as presets
        import server19_gacha
        catalog['material_presets'] = presets.build(catalog, server19_gacha.CHANNELS)
        CATALOG = catalog
        return CATALOG


def load(context, account_json, new_uid=None, new_kind=None):
    account = None if account_json is None else json.loads(str(account_json))
    if account is not None and (not isinstance(account, dict) or account.get('schema') != 1 or type(account.get('uid')) is not int):
        raise ValueError('存档身份或格式无效')
    catalog = _catalog(context)
    if account is None:
        import server19_editor_templates as templates
        account = templates.create(catalog, str(new_kind), uid=int(new_uid))
    view_catalog = _view_catalog(catalog, account)
    capabilities = ['captain', 'avatar', 'skill', 'costume', 'costume_all',
                    'material', 'materials_batch', 'equipment_add', 'equipment_edit',
                    'equipment_delete', 'equipment_equip', 'equipment_exchange', 'story_unlock',
                    'story_max_stars', 'sakura_set_part', 'abyss_set', 'cabin', 'template']
    return json.dumps({'account': account, 'catalog': view_catalog, 'capabilities': capabilities}, ensure_ascii=False)


def create(context, uid, kind):
    return load(context, None, uid, kind)


def apply(account_json, operation_json):
    if CATALOG is None:
        raise ValueError('请先读取存档')
    account, operation = json.loads(str(account_json)), json.loads(str(operation_json))
    name = operation.get('op')
    if name == 'captain':
        import server19_editor_captain as captain
        result = captain.apply(account, CATALOG, operation)
    elif name == 'template':
        import server19_editor_templates as templates
        result = templates.create(CATALOG, operation.get('kind'), uid=account['uid'])
    elif name in ('story_unlock', 'story_max_stars', 'sakura_set_part', 'abyss_set'):
        import server19_editor_progress as progress
        result, _ = progress.apply(account, CATALOG, operation)
    elif name == 'cabin':
        import server19_editor_cabin as cabin
        result = cabin.apply(account, CATALOG, operation)
    else:
        import server19_editor_inventory as inventory
        result = inventory.apply(account, CATALOG, operation)
    return json.dumps(result, ensure_ascii=False)


def save(context, account_json, backup_dir, expected_hash):
    files = Path(str(context.getFilesDir().getAbsolutePath()))
    import server19_editor_store as store
    return store.save(files / 'formal-data/account.json', files / 'formal-import.json',
                      Path(str(backup_dir)) if str(backup_dir) else None, str(expected_hash), json.loads(str(account_json)))


def with_account_lock(context, action):
    files = Path(str(context.getFilesDir().getAbsolutePath()))
    import server19_stage as stage
    with stage._transaction_lock(files / 'formal-data/account.json'):
        action.run()
