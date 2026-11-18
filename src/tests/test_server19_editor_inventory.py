import copy
import unittest

import server19_editor_inventory as editor


def fixture():
    account = {'main': {'level': 10}, 'unknown': {'kept': True},
               'avatar_list': [
                   {'avatar_id': 101, 'star': 1, 'level': 1, 'weapon_unique_id': 1,
                    'skill_list': [{'skill_id': 11, 'sub_skill_list': [{'sub_skill_id': 111, 'level': 4, 'is_mask': False}]}]},
                   {'avatar_id': 102, 'star': 1, 'level': 1, 'weapon_unique_id': 2,
                    'skill_list': [{'skill_id': 12, 'sub_skill_list': [{'sub_skill_id': 121, 'level': 4, 'is_mask': False}]}]}],
               'weapon_list': [{'unique_id': 1, 'id': 501, 'level': 1, 'exp': 0, 'is_protected': False},
                               {'unique_id': 2, 'id': 501, 'level': 1, 'exp': 0, 'is_protected': False}],
               'stigmata_list': [{'unique_id': 20001, 'id': 601, 'level': 1, 'exp': 0, 'is_protected': False}],
               'material_list': [{'id': 701, 'num': 30}]}
    tables = {'avatardata': [
                  {'avatarID': 101, 'unlockStar': 1, 'avatarFragmentID': 801, 'skillList': [11], 'initialWeapon': 501, 'weaponBaseTypeList': [1]},
                  {'avatarID': 102, 'unlockStar': 1, 'avatarFragmentID': 802, 'skillList': [12], 'initialWeapon': 501, 'weaponBaseTypeList': [1]}],
              'avatarexdata': [{'avatarIDList': [101, 102], 'commonSubSkillList': [{'Skill1': '101-11-111', 'Skill2': '102-12-121'}]}],
              'avatarsubskilldata': [{'avatarSubSkillId': 111, 'skillId': 11, 'maxLv': 5}, {'avatarSubSkillId': 121, 'skillId': 12, 'maxLv': 5}],
              'dressdata': [{'dressID': 901, 'dressType': 1, 'avatarIDList': [101, 102]}],
              'weapondata': [{'ID': 501, 'maxLv': 10, 'expType': 1, 'baseType': 1, 'cost': 1}],
              'stigmatadata': [{'ID': 601, 'maxLv': 10, 'expType': 1, 'baseType': 1, 'cost': 1}],
              'equipmentleveldata': [{'level': i, 'Type1': [0, 100]} for i in range(1, 11)],
              'avatarleveldata': [{'level': i, 'cost': 10} for i in range(1, 11)],
              'playerleveldata': [{'level': 10, 'avatarLevelLimit': 10}],
              'avatarfragmentdata': [{'ID': 801, 'quantityLimit': 99}, {'ID': 802, 'quantityLimit': 99}],
              'materialdata': [{'ID': 701, 'quantityLimit': 100}]}
    return account, tables


class InventoryEditorTest(unittest.TestCase):
    def setUp(self):
        self.account, self.tables = fixture()

    def test_shared_skill_downgrade_is_atomic(self):
        before = copy.deepcopy(self.account)
        changed = editor.apply(self.account, self.tables, {'type': 'skill', 'avatar_id': 101, 'skill_id': 11, 'sub_skill_id': 111, 'level': 2})
        self.assertEqual(self.account, before)
        self.assertEqual([a['skill_list'][0]['sub_skill_list'][0]['level'] for a in changed['avatar_list']], [2, 2])
        self.assertEqual(changed['unknown'], {'kept': True})

    def test_ranges_and_worn_weapon_deletion(self):
        changed = editor.apply(self.account, self.tables, {'type': 'equipment_add', 'kind': 'weapon', 'id': 501})
        self.assertEqual(changed['weapon_list'][-1]['unique_id'], 3)
        with self.assertRaises(ValueError):
            editor.apply(changed, self.tables, {'type': 'equipment_delete', 'unique_id': 1})
        changed = editor.apply(changed, self.tables, {'type': 'equipment_delete', 'unique_id': 1, 'replacement_uid': 3})
        self.assertEqual(changed['avatar_list'][0]['weapon_unique_id'], 3)

    def test_costume_ownership_and_fallback(self):
        account = editor.apply(self.account, self.tables, {'type': 'costume_all', 'owned': True})
        account = editor.apply(account, self.tables, {'type': 'costume', 'avatar_id': 101, 'equip': 901})
        account = editor.apply(account, self.tables, {'type': 'costume', 'dress_id': 901, 'owned': False})
        self.assertEqual(account['avatar_list'][0]['dress_id'], 0)
        self.assertNotIn(901, account['has_got_item_id_list'])
        self.assertTrue(all(901 not in a['dress_list'] for a in account['avatar_list']))

    def test_weapon_exchange_keeps_both_characters_armed(self):
        changed = editor.apply(self.account, self.tables, {'op': 'equipment_exchange',
                                                          'avatar_id_1': 101, 'avatar_id_2': 102})
        self.assertEqual([a['weapon_unique_id'] for a in changed['avatar_list']], [2, 1])

    def test_material_cap_and_batch_does_not_reduce(self):
        changed = editor.apply(self.account, self.tables, {'type': 'materials_batch', 'items': [{'id': 701, 'num': 20}]})
        self.assertEqual(changed['material_list'][0]['num'], 30)
        with self.assertRaises(ValueError):
            editor.apply(self.account, self.tables, {'type': 'material', 'id': 701, 'num': 101})

    def test_locked_battle_items_and_awakened_dependency(self):
        self.account['exboss_runtime'] = {'bosses': {'1': {'avatars': [101], 'weapons': [1], 'stigmata': []}}}
        with self.assertRaises(ValueError):
            editor.apply(self.account, self.tables, {'type': 'avatar', 'avatar_id': 101, 'star': 0})
        with self.assertRaises(ValueError):
            editor.apply(self.account, self.tables, {'type': 'equipment_delete', 'unique_id': 1})
        del self.account['exboss_runtime']
        with self.assertRaises(ValueError):
            editor.apply(self.account, self.tables, {'type': 'avatar', 'avatar_id': 101, 'star': 0})


if __name__ == '__main__':
    unittest.main()
