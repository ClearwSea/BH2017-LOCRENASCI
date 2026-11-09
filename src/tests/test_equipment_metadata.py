import unittest
from packager.equipment_metadata import complete
from packager.core import BuildError


class EquipmentMetadataTests(unittest.TestCase):
    def test_closes_all_equipment_references_without_replacing_existing_rows(self):
        tables = {'equipmentskilldata': [{'ID': 1, 'skillName': 'existing'}],
                  'weapondata': [{'prop1ID': 2}], 'stigmatadata': [{'prop2ID': 3}],
                  'equipmentsetdata': [{'prop3ID': 2}]}
        source = [{'ID': 1, 'skillName': 'different'}, {'ID': 2}, {'ID': 3}, {'ID': 4}]
        self.assertEqual(complete(tables, source), [2, 3])
        self.assertEqual(tables['equipmentskilldata'], [{'ID': 1, 'skillName': 'existing'}, {'ID': 2}, {'ID': 3}])
        self.assertEqual(complete(tables, source), [])

    def test_missing_source_fails_without_partial_mutation(self):
        tables = {'equipmentskilldata': [], 'weapondata': [{'prop1ID': 2, 'prop2ID': 3}],
                  'stigmatadata': [], 'equipmentsetdata': []}
        with self.assertRaises(BuildError):
            complete(tables, [{'ID': 2}])
        self.assertEqual(tables['equipmentskilldata'], [])

    def test_restores_description_and_labels_missing_source_name_without_inventing_one(self):
        tables = {'equipmentskilldata': [], 'weapondata': [{'prop1ID': 2084}],
                  'stigmatadata': [], 'equipmentsetdata': [], 'textmap': []}
        complete(tables, [{'ID': 2084, 'skillName': 'name', 'skillDisplay': 'description'}],
                 [{'ID': 'description', 'Text': 'source description'}])
        self.assertEqual(tables['textmap'], [{'ID': 'name', 'Text': '技能 2084'},
                                           {'ID': 'description', 'Text': 'source description'}])
