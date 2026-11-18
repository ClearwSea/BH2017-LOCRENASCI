"""Keep the game service and save editor from running at the same time."""
import fcntl
from pathlib import Path

_guard = None


def acquire(context):
    global _guard
    if _guard is not None:
        raise RuntimeError('已有存档编辑或游戏会话正在运行')
    path = Path(str(context.getFilesDir().getAbsolutePath())) / 'game-editor-session.lock'
    stream = path.open('a+b')
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close()
        raise RuntimeError('游戏或存档编辑器仍在运行，请先退出后重试')
    _guard = stream


def release():
    global _guard
    if _guard is not None:
        stream, _guard = _guard, None
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
