"""Create standalone local save templates from the deployed runtime tables.

The caller supplies the local account UID explicitly; no existing save or
private template file is read. Generation has no side effects or game I/O.
"""
from copy import deepcopy

import server19_editor_inventory as inventory
import server19_editor_progress as progress


def _one(rows, key, value):
    found = [r for r in rows if r.get(key) == value]
    if len(found) != 1:
        raise ValueError('运行时模板目录缺少唯一的 %s=%s' % (key, value))
    return found[0]


def create(catalog, kind, *, uid):
    """Create independent starter, starter_first_login or full_level account."""
    if not isinstance(catalog, dict) or kind not in ('starter', 'starter_first_login', 'full_level'):
        raise ValueError('未知存档模板')
    if type(uid) is not int or not 1 <= uid <= 0xffffffff:
        raise ValueError('请提供有效的本地玩家 UID')
    levels = catalog.get('playerleveldata')
    avatars = catalog.get('avatardata')
    if not isinstance(levels, list) or not levels or not isinstance(avatars, list) or not avatars:
        raise ValueError('运行时缺少舰长或角色表')
    level = max(r['level'] for r in levels) if kind == 'full_level' else 1
    level_data = _one(levels, 'level', level)
    default_avatar = _one(avatars, 'avatarID', 101)
    if type(level_data.get('stamina')) is not int or type(default_avatar.get('initialWeapon')) is not int:
        raise ValueError('运行时初始数据不完整')
    first = kind == 'starter_first_login'
    account = {'schema': 1, 'fixture': 'server19-single-avatar-initialization', 'uid': uid,
               'account_mode': 'experience-template' if kind == 'full_level' else 'starter-template',
               'is_first_login': first,
               'main': {'nickname': '本地测试舰长', 'self_desc': '', 'level': level, 'exp': 0,
                        'hcoin': 0, 'scoin': 0, 'stamina': level_data['stamina'], 'friends_point': 0,
                        'skill_point': 0, 'skill_point_limit': 50, 'equipment_size_limit': 500,
                        'assistant_avatar_id': 101},
               'avatar_list': [{'avatar_id': 101, 'star': default_avatar['unlockStar'], 'level': 1,
                                'exp': 0, 'fragment': 0, 'weapon_unique_id': 1,
                                'touch_goodfeel': 0, 'stage_goodfeel': 0, 'skill_list': [], 'dress_list': [],
                                'stigmata_unique_id_1': 0, 'stigmata_unique_id_2': 0, 'stigmata_unique_id_3': 0}],
               'weapon_list': [{'unique_id': 1, 'id': default_avatar['initialWeapon'],
                                'level': 1, 'exp': 0, 'is_protected': False}],
               'stigmata_list': [], 'material_list': [], 'guide_id_list': [],
               'stage_list': [progress._empty_stage(10101)],
               'stage_runtime': {'schema': 1, 'active': None, 'settlements': []}}
    if kind != 'full_level':
        return account
    cap = level_data.get('avatarLevelLimit')
    if type(cap) is not int or cap < 1:
        raise ValueError('运行时缺少角色等级上限')
    # Original forms are always unlocked before their awakened forms.
    ordered = sorted(avatars, key=lambda r: (bool(r.get('baseAvatarID')), r['avatarID']))
    for avatar in ordered:
        account = inventory.apply(account, catalog, {'op': 'avatar', 'avatar_id': avatar['avatarID'],
                                                       'star': 5, 'level': cap})
    account = inventory.apply(account, catalog, {'op': 'costume_all', 'owned': True})
    configs = progress._stages(catalog)
    saved = progress._stage_records(account)
    for identity, cfg in configs.items():
        progress._set_stars(account, saved, cfg, identity, range(len(cfg['challengeList'])))
        saved[identity].update(progress=cfg['maxProgress'], is_done=True)
    return account
