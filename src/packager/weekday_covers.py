"""Map themed weekday covers to the original 1.9 native resources."""

from .core import BuildError


def adapt(rows, native_resource_paths):
    """Fix the extra Event directory on the five retained native cover paths.

    The 2.4 table omits one directory present in the 1.9 ResourceManager.
    Preserve each activity's own original artwork and all unrelated rows.
    """
    native = {path.lower() for path in native_resource_paths}
    selected = {1001 + i: f'BookEventDailyMaterial{i + 1:02d}' for i in range(5)}
    selected[1531] = 'BookEventDaily02'
    found = set()
    for row in rows:
        identity = row.get('weekDayActivityID')
        if identity not in selected:
            continue
        if identity in found:
            raise BuildError('Duplicate weekday cover activity: ' + str(identity))
        source = f'SpriteOutput/ChapterCover/Event/{selected[identity]}'
        target = source.replace('/Event/', '/Event/Event/')
        if row.get('enterImgPath') != source or target.lower() not in native:
            raise BuildError('Weekday cover source or native resource changed: ' + str(identity))
        row['enterImgPath'] = target
        found.add(identity)
    if found != selected.keys():
        raise BuildError('Missing weekday cover activity')
    return len(found)
