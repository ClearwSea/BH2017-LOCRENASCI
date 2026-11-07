"""Formatting must not change reviewed captain rewards; value changes must fail."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import server19_player_progression as progression
from server19_build_capabilities import canonical_sha


class ProgressionSerializationTests(unittest.TestCase):
    def test_formatting_and_changed_values(self):
        rows = [{"level": 1, "exp": 10, "scBonus": 0, "staminaBonus": 0},
                {"level": 2, "exp": 20, "scBonus": 50, "staminaBonus": 5}]
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "playerleveldata"
            stage = types.SimpleNamespace(TABLE_DIRECTORY=Path(directory),
                _table=lambda name: json.loads(table.read_bytes()),
                _u32=lambda value, label: value)
            with patch.dict(sys.modules, {"server19_stage": stage}), \
                    patch.object(progression, "TABLE_CONTENT_SHA256", canonical_sha(rows)):
                for raw in (json.dumps(rows) + "\n", json.dumps(rows) + "\r\n",
                            json.dumps(rows, sort_keys=True, indent=2)):
                    with self.subTest(format=raw[-3:]):
                        table.write_bytes(raw.encode())
                        main = {"level": 1, "exp": 0, "scoin": 0, "stamina": 80}
                        progression.grant_player_exp(main, 10)
                        self.assertEqual(main, {"level": 2, "exp": 0,
                                               "scoin": 50, "stamina": 85})
                changed = copy.deepcopy(rows)
                changed[1]["scBonus"] += 1
                table.write_bytes(json.dumps(changed).encode())
                main = {"level": 1, "exp": 0, "scoin": 0, "stamina": 80}
                before = copy.deepcopy(main)
                with self.assertRaisesRegex(ValueError, "Reviewed captain progression source changed"):
                    progression.grant_player_exp(main, 10)
                self.assertEqual(main, before)


if __name__ == "__main__":
    unittest.main()
