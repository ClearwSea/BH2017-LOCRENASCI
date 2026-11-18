"""Keep the client's native save-point event alive until its real reply."""
import hashlib
from .core import BuildError

SCRIPTS = {
    '111.lua': ('bf89cabce05793b642e21a9a4f2b59e9de87feaf1fdfe81c45ddb8ab40e36774', 'Mission_2_1_Start'),
    '207.lua': ('e628362c274b604e07ed3159db0c7add73adb2192dc31e3902c32ae1add710d5', 'Mission_3_1_Start'),
}
HELPER = (b'function reset_save_point(point)\n'
          b'\tif level.is_open_world_boss_stage == true then\n\t\treturn\n\tend\n'
          b'\tif point then\n\t\t_current_save_point = point\n\tend\n'
          b'\tprint("new_save_point == ".._current_save_point)\n'
          b'\tLevelDesign:CreateCoroutine(function ()\n'
          b'\t\tlocal event_table = {}\n\t\tlocal event_tretTable = {}\n'
          b'\t\tevent_table["type"] =  5\n\t\tevent_table["p1"] =  _current_save_point\n'
          b"\t\tcoroutine.yield {'LDEvtInLevelNetWorkRequest', event_table, event_tretTable}\n"
          b'\tend)\nend')


def adapt(name, raw):
    expected, point = SCRIPTS[name]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise BuildError('Sakura mission input fingerprint changed: ' + name)
    old = f'\t\treset_save_point("{point}")\n\t\tLevelDesign:QuitLevelDirectly()'.encode()
    if raw.count(old) != 1:
        raise BuildError('Sakura ending save/exit sequence changed: ' + name)
    replacement = (f'\t\tif level.is_open_world_boss_stage ~= true then\n'
                   f'\t\t\t_current_save_point = "{point}"\n'
                   '\t\t\tlocal event_table = {type = 5, p1 = _current_save_point}\n'
                   '\t\t\tlocal event_tretTable = {}\n'
                   "\t\t\tcoroutine.yield {'LDEvtInLevelNetWorkRequest', event_table, event_tretTable}\n"
                   '\t\tend\n\t\tLevelDesign:QuitLevelDirectly()').encode()
    return raw.replace(old, replacement, 1)


def verify_helper(raw):
    if raw.count(HELPER) != 1:
        raise BuildError('Sakura original save-point helper changed')
