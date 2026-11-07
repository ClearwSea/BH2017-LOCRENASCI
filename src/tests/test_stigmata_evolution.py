import unittest
from packager.core import BuildError
from packager.tables import complete_stigmata_evolution


class EvolutionClosureTests(unittest.TestCase):
    def test_transitive_source_dependencies_only(self):
        kept = [{'ID': 1, 'evoID': 2, 'custom': True}]
        source = [{'ID': 2, 'evoID': 3}, {'ID': 3, 'evoID': 0}, {'ID': 4, 'evoID': 0}]
        result = complete_stigmata_evolution(kept, source)
        self.assertEqual([r['ID'] for r in result], [1, 2, 3])
        self.assertEqual(result[0], kept[0])
        self.assertEqual(len(kept), 1)

    def test_missing_dependency_fails(self):
        with self.assertRaises(BuildError):
            complete_stigmata_evolution([{'ID': 1, 'evoID': 2}], [])

    def test_cycle_fails_instead_of_native_infinite_loop(self):
        with self.assertRaises(BuildError):
            complete_stigmata_evolution([{'ID': 1, 'evoID': 2}], [{'ID': 2, 'evoID': 1}])
