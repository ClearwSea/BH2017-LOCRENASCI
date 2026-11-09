"""A persisted UP deadline must remain reachable despite a full rare cap."""
import unittest
from unittest.mock import patch

import server19_gacha_policy as policy


class UpCapTests(unittest.TestCase):
    def test_due_up_wins_but_ordinary_draw_stays_capped(self):
        for channel, rare, common, up in (
            (3, 'GEAR5', 'GEAR4', ('weapon', 20464, 1, 1)),
            (5, 'S', 'A', ('avatar_card', 60502, 1, 1)),
        ):
            with self.subTest(channel=channel):
                state = dict(since_up=199, since_rare=4, since_common=2,
                             recent=[rare, rare])
                pools = {rare: [up], common: [('material', 1, 0, 1)]}
                with patch.object(policy, 'state', return_value=state), \
                     patch.object(policy, 'choices', return_value=pools), \
                     patch.object(policy, 'catalog', return_value=({}, {}, {}, {})):
                    self.assertEqual(policy.select({}, channel), up)
                    state['since_up'] = 0
                    self.assertEqual(policy.select({}, channel), pools[common][0])


if __name__ == '__main__':
    unittest.main()
