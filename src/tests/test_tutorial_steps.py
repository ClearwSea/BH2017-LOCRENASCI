import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from packager.core import BuildError
from packager.tables import _restore_missing_tutorial_steps


class _StubSource:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def projected_tsv(self, name):
        assert name == 'tutorialstepdata'
        self.calls += 1
        return list(self._rows)


class TutorialStepClosureTest(unittest.TestCase):
    def test_restores_transitive_missing_steps(self):
        tables = {
            'tutorialdata': [
                {'id': 9081, 'startStepID': 90811},
                {'id': 9041, 'startStepID': 90411},
            ],
            'tutorialstepdata': [
                {'id': 10662, 'nextStepID': 0},
                {'id': 10731, 'nextStepID': 0},
                {'id': 90411, 'nextStepID': 90412},
                {'id': 90413, 'nextStepID': 0},
            ],
        }
        source = _StubSource([
            {'id': 90811, 'nextStepID': 90812},
            {'id': 90812, 'nextStepID': 0},
            {'id': 90412, 'nextStepID': 90413},
        ])
        _restore_missing_tutorial_steps(tables, source)
        ids = {row['id'] for row in tables['tutorialstepdata']}
        self.assertTrue({90811, 90812, 90412}.issubset(ids))
        self.assertEqual(source.calls, 1)

    def test_raises_when_step_missing_in_source(self):
        tables = {
            'tutorialdata': [{'id': 9081, 'startStepID': 90811}],
            'tutorialstepdata': [{'id': 10662, 'nextStepID': 0}, {'id': 10731, 'nextStepID': 0}],
        }
        source = _StubSource([])
        with self.assertRaises(BuildError):
            _restore_missing_tutorial_steps(tables, source)


if __name__ == '__main__':
    unittest.main()
