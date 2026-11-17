"""Source-backed weekday activity assets; business rules are separate.

These helpers prepare data for an isolated candidate. They do not open an
activity, define drops or claim that the 2.4 scripts run on the 1.9 client.
"""

from copy import deepcopy
import hashlib
import struct

from .core import BuildError


ACTIVITIES = {
    1001: (101100, 'theme01'),
    1002: (101200, 'theme02'),
    1003: (101300, 'theme03'),
    1004: (101400, 'theme04'),
    1005: (101500, 'theme05'),
    1301: (101600, 'redpacket'),
    1501: (45000, 'bio'),
    1511: (45100, 'psy'),
    1521: (45200, 'mech'),
    1531: (45300, 'weapon'),
    1541: (45400, 'stigmata'),
}

SCRIPTS = {
    'redpacket': {'lua/levels/event/new weekday06.lua': 'd35148e5a8d4a0c2ae334a254af074a157d4e9d27c05d0eb1c1cf888420d5703'},
    'theme01': {'lua/levels/event/new weekday01.lua': 'fd090b905d85f7d4be465401c12e20cb4b85238897c33165c9074b9c0dfbee82'},
    'theme02': {'lua/levels/event/new weekday02.lua': '5adccac2ce5782960e8b85c84f407a12818f833e4b7691e4d451d6d84f4f46d1'},
    'theme03': {'lua/levels/event/new weekday03.lua': 'd6cac8824a82beebc9fdf90961513ccb2e8d2033f71151257130f036352038f1'},
    'theme04': {'lua/levels/event/new weekday04.lua': '3722b11e40da73ce1dd8f722dcad18c3831d7c2a918524172c4840664926f9f5'},
    'theme05': {'lua/levels/event/new weekday05.lua': '61a35cc3b488b5b0803dea7593f223e898e256990b5f1bcd0c8d7408b92b1a1b'},
    'bio': {
        'lua/levels/newevent/sp_material_avatarexp_bio_config_normal.lua': 'df1028afdc1f740a49c542304436ab9eccbd72beab73856065602fae9bca8157',
        'lua/levels/newevent/sp_material_avatarexp_bio_common.lua': 'ad0d86b371378ee07db7bdf4c6e6bd8b97d13b4053c5b25940e28f7d30e9e263',
    },
    'psy': {
        'lua/levels/newevent/sp_material_avatarexp_psy_config_normal.lua': '2b97ed9d53af5ddaf76ceed522a16cb07630070cb10e78ebdc6c47fede346391',
        'lua/levels/newevent/sp_material_avatarexp_psy_common.lua': '6176bc3168cfe0a325e8325fad8e55424e8daf54e85278b86021c0c454bed445',
    },
    'mech': {
        'lua/levels/newevent/sp_material_avatarexp_mech_config_normal.lua': '6e5dad0c57456d2b5e10224f157a25b8a9668228c7c96c3f007581249386eb52',
        'lua/levels/newevent/sp_material_avatarexp_mech_common.lua': 'fff1866e58f9101fca7a6b5bb18cde200a1b5e9d3f528830cad7499e6ccee8db',
    },
    'weapon': {
        'lua/levels/newevent/sp_material_weaponexp.lua': '546eaf1ffd25a65a50638df991130a8b0f51024cc793ccb379b50e694875824d',
    },
    'stigmata': {
        'lua/levels/newevent/sp_material_stigmataexp.lua': '5e80e19d2605c607517ceeb0cebc8c9a41e86e2a30ade3c379c8ba02b098d5d0',
    },
}

# These two bounded 1.9 compatibility edits retain the original Lua flow.
# The missing mute method only hides damage numbers; the other edit corrects
# the monster name to the exact value already used by the same Lua's preload.
SCRIPT_EDITS = {
    'lua/levels/event/new weekday03.lua': (
        'd6cac8824a82beebc9fdf90961513ccb2e8d2033f71151257130f036352038f1',
        b'\t\t\t\tLevelDesign:SetInLevelMainPageMuteDamageText(true)\n', b'',
        '70d3b98283d6d3a1f9718260559b762e621268638dd20c02a769bd4222cbaa68'),
    'lua/levels/event/new weekday05.lua': (
        '61a35cc3b488b5b0803dea7593f223e898e256990b5f1bcd0c8d7408b92b1a1b',
        b'RobotLancher', b'RobotLauncher',
        'de58d42fc871761aac607cc6765f555ab252e6497d5257ce4c4234447868104e'),
}

# 2.4 ability roots used by the unmodified weapon/stigmata scripts. These
# edits were derived from both versions' typed readers: union tags keep the
# same concrete classes; the two removed later-only fields are nil. Hashes
# bind the conversion to the verified source roots and the expected output.
ABILITY_EDITS = {
    'Fake_Avatar_SP_012_Accelerate': (
        'fbdcecf6efb242f14862f58b5dd772c5a85255a10cfedf928fb0f4d6c8c111cc',
        '08e1a333c2936a3487eb67694c282530ff79e0d1cdfc957636f26a584d2545a4',
        ((50, 51, b''), (12, 15, b'\xdc\x00\x1d'), (73, 74, b'\x0d'))),
    # Source typed readers preserve retained terminal values; later-only fields are nil.
    'Level_New_WeekDay_01_Property': (
        'f292af85b0bab4c206ce32053482c6af0c1bcd5b556678208c932d35d8f610fd',
        'b89e0ebda0799ed410aa9f3fb35c60328bc4c8dd9daf80e52d4e71cc953ac0e1',
        ((48, 49, b''), (21, 24, b'\xdc\x00\x1d'), (71, 72, b'\x0d'))),
    'Level_New_WeekDay_02_Property': ('d5e502b4ce0a02b94ed5961c3d8f7e021e27efdbe085c8625cdcff695583ca27', '087f1d33fa6adffc974d1d617bbce50e8c4ccdd19d66c636d1153bf7df69c97c', ((57, 58, b''), (21, 24, b'\xdc\x00\x1d'), (80, 81, b'\r'))),
    'Level_New_WeekDay_03_Property': ('52506fb40f68dcbe977027f7350dd5ad670dadf78bd9fc1e6908b849e85894e0', '1977f4a5c2bc6f098900231190fa729a28535361ccba630acef53a27ffbc3b32', ((8, 9, b'q'), (79, 80, b''), (50, 53, b'\xdc\x00\x1d'), (102, 103, b'\r'))),
    'Level_New_WeekDay_04_Property': ('0aed7ada9cfd5a35cd0bf722e662ba35441417104102db331d0541c65df0f779', 'a5298e64b4f8333f41223761eb44eba27e07e051d70a7659faeb72c3404a791c', ((50, 51, b''), (21, 24, b'\xdc\x00\x1d'), (73, 74, b'\r'), (84, 85, b'>'), (98, 99, b''), (85, 86, b'\x9b'))),
    'Level_New_WeekDay_05_Property': ('d86eded294905ee7d05741683895f43af468d5d4c99b3b5e564c3135e1b6de2c', '67340367b234c28675d0afca2c56cceb23f9f185d438c882a03749442a8e0368', ((92, 93, b''), (21, 24, b'\xdc\x00\x1d'), (115, 116, b'\r'))),
    'Fake_Avatar_SP_012_DisableAttack': ('ae4ae998be117c02c43fc18d4ed70a070fd3e9898bbbe84926246831a9c785c1', 'f5a342cd5cd97184aa4da221a770a439fbc8663ac17791b247b8b757aa77ed0e', ((8, 9, b'4'), (19, 20, b'4'))),
    'Fake_Avatar_Fast_Mode': ('ac5f39d3478620abdf45cc6508bd257d1f04d42af274dcb00ed502b204794212', '33ffdd6655a6265b7c11695f05d6079111bc78ec256a376999a50fec99e47d0c', ((48, 49, b''), (21, 24, b'\xdc\x00\x1d'), (71, 72, b'\r'))),
    'Fake_Avatar_SP_013': (
        '2b03fb86baae809001e37ccb59fb888170e17da99959966a0f27281d8aa7dcbf',
        '21f76babecc1b1b0b2b60273fbf0e4e06d1bd1e204ad5a6170c5370127c77234',
        ((8, 9, b'\x07'), (44, 45, b'\x12'), (64, 65, b'\x12'), (84, 85, b'\x1e'), (152, 153, b'\x12'), (168, 169, b'\n'), (201, 202, b''), (183, 186, b'\xdc\x00\x1d'), (242, 243, b''), (245, 246, b'$'), (224, 227, b'\xdc\x00\x1d'), (295, 296, b''), (298, 299, b'$'), (277, 280, b'\xdc\x00\x1d'), (359, 360, b''), (362, 363, b'_'), (373, 374, b'\r'), (330, 333, b'\xdc\x00\x1d'), (436, 437, b''), (439, 440, b'\r'), (451, 452, b'_'), (404, 407, b'\xdc\x00\x1d'), (494, 495, b'e'), (518, 519, b'e'), (547, 548, b''), (481, 484, b'\xdc\x00\x1d'), (588, 589, b''), (591, 592, b'n'), (603, 604, b'n'), (570, 573, b'\xdc\x00\x1d'), (635, 636, b'\x15'), (644, 645, b'\r'), (655, 656, b'\r'))),
    'Fake_Avatar_SP_013_DashEffect': (
        '3b01774da8051ae7010308e5d2a8a0992313fdb43f97bdf3641288d38774fb70',
        '6f8f637d72b96d3331da0febd827d6c3840082d2c368abd0025f645bb269e998',
        ((37, 38, b''), (40, 41, b'\x13'), (12, 15, b'\xdc\x00\x1d'), (76, 77, b'\r'))),
    'Activity_DoubleSeventMonsterDeadBomb': (
        '01da171b024dd6e5426b268079533d68f0d24f2a3158bd8bdfea2d942e04eefa',
        '1e1f35d9679c10cb21990d6095cf9a8934aee5b678bbe7b25c9cf27394a37931',
        ((30, 31, b''), (33, 34, b';'), (12, 15, b'\xdc\x00\x1d'), (80, 81, b''), (95, 96, b'\r'), (114, 115, b'8'), (62, 65, b'\xdc\x00\x1d'), (144, 145, b'\r'))),
    'Fake_Avatar_Boss_050_Bullet_L': (
        'c67fd6fc8b6d8b6a21c42f4cd324bc76df23a83ad80fa443668142014f2fee90',
        '2b143f74ccefc673cb3b5b56c2913f3e3d9b1b1abfdce70c0f79c6298f05c3f9',
        ((8, 9, b'T'), (93, 94, b''), (94, 95, b''), (95, 96, b''), (9, 12, b'\xdc\x00,'))),
    'Fake_Avatar_Boss_050_Bullet_R': (
        'd328c77ef84dcbc07d7dc012172cd79eef225e0952d547e6aa75788495fd5548',
        'b5ff318a3c92066069bd8ca9b45368887c7b37c0706bb8efa630b1b75ef7d599',
        ((8, 9, b'T'), (93, 94, b''), (94, 95, b''), (95, 96, b''), (9, 12, b'\xdc\x00,'))),
    'Fake_Avatar_Boss_050_Bullet_Trigger': (
        'df1e6b4bde5ccbf094bd77bdc22389640df067b0e7a3bafc582b13ee9dea8551',
        '529e5f7536bc03c55899eed9adaaf4fb4c0ee8c1641b47a096968aa784d2900c',
        ((14, 16, b'}'), (21, 22, b''), (25, 26, b''), (16, 17, b'\x98'), (33, 35, b'}'), (40, 41, b''), (44, 45, b''), (35, 36, b'\x98'))),
    'Level_Avatar_WeaponSP': (
        '5ecf83e776c176499da4f1b68ba2fff26e78f66e9dbe44b8bed2ab3ba3259ce0',
        '5ab1a005ed975f61ebffe96f92df265664669a412542dc4a55b2b34ac8da73b2',
        ((25, 27, b'\xcc\xa2'), (35, 36, b'\x3e'), (51, 52, b''),
         (36, 37, b'\x9b'), (76, 77, b''), (12, 15, b'\xdc\x00\x1d'), (101, 102, b'\x0d'))),
    'Activity_Monster_Beta_Test_01': (
        '0f43756dc2c866bb2ff1240250f161b5face3298357bcd5dbfe44cedab84e104',
        '22dc6de3c8483fcc4056ad340b1ae3206a45f16aa9d3c21475e27f585bb43070',
        ((30, 31, b''), (33, 34, b'\x15'), (12, 15, b'\xdc\x00\x1d'), (62, 63, b'\x0d'))),
}


def adapt_ability_data(payload, stringmap):
    """Convert fingerprinted roots while preserving every other root."""
    strings = stringmap.decode('utf-8').split('\x1f')
    try:
        targets = {strings.index(name): value for name, value in ABILITY_EDITS.items()}
        header0, header1, count = struct.unpack_from('<III', payload, 0)
        pos = 12
        entries = [struct.unpack_from('<II', payload, pos + 8 * i) for i in range(count)]
        pos += 8 * count
        count_overrides = struct.unpack_from('<I', payload, pos)[0]
        pos += 4
        overrides = [struct.unpack_from('<III', payload, pos + 12 * i) for i in range(count_overrides)]
        pos += 12 * count_overrides
        size = struct.unpack_from('<I', payload, pos)[0]
        pos += 4
        data = payload[pos:]
        refs = {offset: (key, None) for key, offset in entries}
        refs.update({offset: (key, variant) for key, variant, offset in overrides})
        offsets = sorted(refs)
        if header0 != 0 or size != len(data) or not offsets or offsets[0] != 0 or len(refs) != len(entries) + len(overrides):
            raise ValueError('Invalid ability container')
        output, new_offsets, found = bytearray(), {}, set()
        for index, left in enumerate(offsets):
            right = offsets[index + 1] if index + 1 < len(offsets) else len(data)
            key, variant = refs[left]
            chunk = data[left:right]
            if key in targets and variant is None:
                before, after, edits = targets[key]
                if hashlib.sha256(chunk).hexdigest() != before:
                    raise ValueError('Ability source fingerprint changed')
                adapted = bytearray(chunk)
                for start, end, replacement in sorted(edits, reverse=True):
                    adapted[start:end] = replacement
                chunk = bytes(adapted)
                if hashlib.sha256(chunk).hexdigest() != after:
                    raise ValueError('Ability conversion fingerprint mismatch')
                found.add(key)
            new_offsets[left] = len(output)
            output.extend(chunk)
        if found != targets.keys():
            raise ValueError('Material training ability root missing')
        result = bytearray(struct.pack('<III', header0, header1, len(entries)))
        for key, offset in entries:
            result.extend(struct.pack('<II', key, new_offsets[offset]))
        result.extend(struct.pack('<I', len(overrides)))
        for key, variant, offset in overrides:
            result.extend(struct.pack('<III', key, variant, new_offsets[offset]))
        result.extend(struct.pack('<I', len(output)))
        result.extend(output)
        return bytes(result)
    except (ValueError, KeyError, UnicodeDecodeError, struct.error) as exc:
        raise BuildError('Material training ability conversion failed: ' + str(exc)) from exc


def stage_ids(activities, selected):
    """Validate the native activity-to-stage links before sourcing the rows."""
    selected = set(selected)
    if not selected or not selected <= ACTIVITIES.keys():
        raise BuildError('Unknown material training activity selection')
    rows = [row for row in activities if row['weekDayActivityID'] in selected]
    if len(rows) != len(selected) or {r['weekDayActivityID'] for r in rows} != selected:
        raise BuildError('Missing or duplicated material training activity')
    result = []
    for row in rows:
        base, _ = ACTIVITIES[row['weekDayActivityID']]
        expected = ([base + slot for slot in (1, 2, 3, 4)] if row['weekDayActivityID'] in (*range(1001, 1006), 1301) else [base + 10 * tier + slot for tier in range(4) for slot in (1, 2, 3)])
        if row['levelIDList'] != expected:
            raise BuildError('Material training stage links changed')
        result.extend(expected)
    return result


def source_stages(activities, source, selected):
    """Project exact 2.4 source rows; leave all gameplay policy untouched."""
    ids = stage_ids(activities, selected)
    rows = source.typed('stagedata_main', 'levelId', ids)
    if [row['levelId'] for row in rows] != ids:
        raise BuildError('Material training source rows changed order or identity')
    for row in rows:
        base = row['levelId'] // 100 * 100
        category = next((kind for first, kind in ACTIVITIES.values() if first == base), None)
        allowed = SCRIPTS.get(category, {})
        script = row['luaFile'].replace('\\', '/').lower()
        if (row.get('type'), row.get('battleType'), row.get('teamNum')) != (2, 1, 1) or script not in allowed:
            raise BuildError('Material training source stage differs: ' + str(row['levelId']))
    return deepcopy(rows)


def adapt_redpacket_record_type(rows):
    """Use native HighScore so the original client reports its real score."""
    ids = {101601, 101602, 101603, 101604}
    selected = [row for row in rows if row.get('levelId') in ids]
    if len(selected) != len(ids) or {r['levelId'] for r in selected} != ids:
        raise BuildError('Red-packet client stages missing or duplicated')
    if any(type(row.get('RecordLevelType')) is not int or row['RecordLevelType'] != 0
           for row in selected):
        raise BuildError('Red-packet native record type source changed')
    for row in selected:
        row['RecordLevelType'] = 1


def adapt_script(path, script):
    """Apply only a fingerprinted, unique and verified Lua compatibility edit."""
    edit = SCRIPT_EDITS.get(path)
    if edit is None:
        return script
    before, needle, replacement, after = edit
    if hashlib.sha256(script).hexdigest() != before or script.count(needle) != 1:
        raise BuildError('Weekday Lua compatibility source changed: ' + path)
    result = script.replace(needle, replacement, 1)
    if hashlib.sha256(result).hexdigest() != after:
        raise BuildError('Weekday Lua compatibility output mismatch: ' + path)
    return result


def extract_scripts(package, mapping, output, selected):
    """Write only verified source scripts to a candidate's resource root."""
    import server19_resources as resources
    selected = set(selected)
    if not selected or not selected <= ACTIVITIES.keys():
        raise BuildError('Unknown material training activity selection')
    wanted = {}
    for activity_id in selected:
        wanted.update(SCRIPTS[ACTIVITIES[activity_id][1]])
    result = []
    for path, expected in sorted(wanted.items()):
        if path not in mapping:
            raise BuildError('Missing material training script: ' + path)
        _, raw = resources.object_bytes(package, mapping[path])
        _, script = resources.text_asset(raw)
        actual = hashlib.sha256(script).hexdigest()
        if actual != expected:
            raise BuildError('Material training source script changed: ' + path)
        script = adapt_script(path, script)
        output_hash = hashlib.sha256(script).hexdigest()
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(script)
        result.append({'path': path, 'bytes': len(script), 'sha256': output_hash,
                       **({'source_sha256': actual} if output_hash != actual else {})})
    return result
