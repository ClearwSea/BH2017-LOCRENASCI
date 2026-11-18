import hashlib
import unittest
from unittest.mock import patch

from packager.core import BuildError
from packager import sakura_exit


class SakuraExitTest(unittest.TestCase):
    def test_only_final_save_waits_for_original_network_event(self):
        original = (b'function finish()\n\t\treset_save_point("Mission_3_1_Start")\n'
                    b'\t\tplay_video()\n\t\treset_save_point("Mission_3_1_Start")\n'
                    b'\t\tLevelDesign:QuitLevelDirectly()\nend\n')
        signature = hashlib.sha256(original).hexdigest()
        with patch.dict(sakura_exit.SCRIPTS, {'207.lua': (signature, 'Mission_3_1_Start')}):
            result = sakura_exit.adapt('207.lua', original)
            self.assertEqual(result.count(b'reset_save_point("Mission_3_1_Start")'), 1)
            self.assertEqual(result.count(b"coroutine.yield {'LDEvtInLevelNetWorkRequest'"), 1)
            self.assertLess(result.index(b'coroutine.yield'), result.index(b'LevelDesign:QuitLevelDirectly()'))
            self.assertEqual(result.count(b'play_video()'), 1)
            with self.assertRaises(BuildError):
                sakura_exit.adapt('207.lua', original + b'-- altered input')

    def test_save_helper_must_match_inspected_client_logic(self):
        sakura_exit.verify_helper(b'prefix\n' + sakura_exit.HELPER + b'\nsuffix')
        with self.assertRaises(BuildError):
            sakura_exit.verify_helper(sakura_exit.HELPER.replace(b'type"] =  5', b'type"] =  4'))


if __name__ == '__main__':
    unittest.main()
