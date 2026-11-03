"""Check actual story event references against delivered banks before unlock."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from functools import lru_cache
from pathlib import Path
import struct

from server19_story_voice_audit import event_hash, events
import server19_resources as resources


@lru_cache(maxsize=1)
def original_events():
    return events(resources.DEFAULT19)[0]


def bank_events(path):
    """Seek over PCM data rather than loading the whole bank for an audit."""
    with Path(path).open('rb') as stream:
        while header := stream.read(8):
            kind, size = struct.unpack('<4sI', header)
            if kind != b'HIRC':
                stream.seek(size, 1)
                continue
            data = stream.read(size)
            count = struct.unpack_from('<I', data)[0]
            pos, result = 4, set()
            for _ in range(count):
                typ = data[pos]
                length = struct.unpack_from('<I', data, pos+1)[0]
                if typ == 4:
                    result.add(struct.unpack_from('<I', data, pos+5)[0])
                pos += 5 + length
            assert pos == len(data)
            return result
    raise ValueError('Voice bank lacks HIRC')


def coverage(stage, bank_ids, *, supported_prefixes=('VO_Dialog_',)):
    names = sorted({r['audioID'] for r in stage.get('dialog_rows', []) if r['audioID']})
    original = original_events()
    missing = [n for n in names if event_hash(n) not in original | bank_ids]
    unsupported = [n for n in names if event_hash(n) not in original
                   and not n.startswith(supported_prefixes)]
    return {'events': names, 'missing': missing, 'loader_unsupported': unsupported,
            'status': 'PASS' if not missing and not unsupported else 'BLOCKED'}
