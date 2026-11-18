import copy
import unittest

import server19_editor_cabin as cabin


class CabinEditorTest(unittest.TestCase):
    def setUp(self):
        self.account = {'main': {'level': 40, 'skill_point_limit': 76},
                        'cabin_list': [{'type': 4, 'level': 2, 'extend_grade': 1,
                                        'level_up_end_time': 0,
                                        'tech_list': [{'pos_x': 0, 'pos_y': 1, 'unknown': 'keep'}],
                                        'unknown': 'keep'}]}
        self.tables = {'cabinleveldata': [{'cabinType': 4, 'level': 2, 'playerLevelNeed': 23},
                                          {'cabinType': 4, 'level': 3, 'playerLevelNeed': 23},
                                          {'cabinType': 4, 'level': 13, 'playerLevelNeed': 23}],
                       'cabinextendgradedata': [{'cabinType': 4, 'extendGrade': 1, 'cabinLevelMax': 12},
                                                {'cabinType': 4, 'extendGrade': 2, 'cabinLevelMax': 24}],
                       'cabintechtreedata': [{'Cabin': 4, 'X': 0, 'Y': 1, 'UnlockLevel': 2,
                                              'UnlockAvatarID': 0, 'AbilityType': 11, 'Argument1': 1}]}

    def test_level_and_expansion_preserve_tech_and_custom_skill_limit(self):
        before = copy.deepcopy(self.account)
        changed = cabin.apply(self.account, self.tables, {'op': 'cabin', 'cabin_type': 4,
                                                          'level': 13, 'extend_grade': 2})
        self.assertEqual(self.account, before)
        self.assertEqual(changed['main']['skill_point_limit'], 76)
        self.assertEqual(changed['cabin_list'][0]['tech_list'], before['cabin_list'][0]['tech_list'])
        self.assertEqual(changed['cabin_list'][0]['unknown'], 'keep')

    def test_invalid_levels_and_tech_edits_are_refused(self):
        with self.assertRaises(ValueError):
            cabin.apply(self.account, self.tables, {'op': 'cabin', 'cabin_type': 4, 'level': 13})
        with self.assertRaises(ValueError):
            cabin.apply(self.account, self.tables, {'op': 'cabin', 'cabin_type': 4, 'level': 1})
        with self.assertRaises(ValueError):
            cabin.apply(self.account, self.tables, {'op': 'cabin_tech', 'cabin_type': 4,
                                                   'pos_x': 0, 'pos_y': 1, 'enabled': False})

    def test_upgrade_in_progress_stays_untouched(self):
        self.account['cabin_list'][0]['level_up_end_time'] = 2000000000
        with self.assertRaises(ValueError):
            cabin.apply(self.account, self.tables, {'op': 'cabin', 'cabin_type': 4, 'level': 3})


if __name__ == '__main__':
    unittest.main()
