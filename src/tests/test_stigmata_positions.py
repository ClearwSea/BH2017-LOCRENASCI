import unittest
from packager.core import BuildError, ROOT, read_json
from packager.json_recipes import render
from packager.tables import complete_stigmata_positions


class StigmataPositionTests(unittest.TestCase):
    def test_dependency_closure_preserves_existing_and_source_values(self):
        existing = [{'name': 'known', 'rootWidth': 600}]
        source = [{'name': 'known', 'rootWidth': 999},
                  {'name': 'missing', 'rootWidth': 720, 'backEnable': True},
                  {'name': 'unrelated', 'rootWidth': 800}]
        equipment = [{'imagePath': 'known'}, {'imagePath': 'missing'}, {'imagePath': 'missing'}]
        result = complete_stigmata_positions(equipment, existing, source)
        self.assertEqual(result, [existing[0], source[1]])
        self.assertEqual(len(existing), 1)
        self.assertEqual(complete_stigmata_positions(equipment, result, source), result)

    def test_missing_source_fails_instead_of_fabricating_artwork(self):
        with self.assertRaisesRegex(BuildError, 'absent'):
            complete_stigmata_positions([{'imagePath': 'absent'}], [], [])

    def test_client_recipe_uses_completed_table(self):
        recipe = read_json(ROOT / 'rules/generated-data-recipes.json')['client_tables']['stigmatapositiondata']
        self.assertEqual(render(recipe, {'base/stigmatapositiondata': [],
                                        'server/stigmatapositiondata': [{'name': 'restored'}]}),
                         [{'name': 'restored'}])


if __name__ == '__main__':
    unittest.main()
