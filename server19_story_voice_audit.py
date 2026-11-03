"""Locate required story voice events in the local original/reference sound banks."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
import struct
import zipfile
import server19_resources as resources
import server19_avatar_battle_resources as batch
from server19_story_all_resources import WORK


def event_hash(value):
    result = 2166136261
    for byte in value.lower().encode():
        result = ((result * 16777619) ^ byte) & 0xffffffff
    return result


def events(package):
    with zipfile.ZipFile(package) as archive:
        raw = archive.read('assets/Audio/GeneratedSoundBanks/Android/AUDIO_Default.pck')
    assert raw[:4] == b'AKPK'
    start = 28 + struct.unpack_from('<I', raw, 12)[0]
    count = struct.unpack_from('<I', raw, start)[0]
    found = set()
    for index in range(count):
        _, block, size, offset, _ = struct.unpack_from('<5I', raw, start + 4 + index*20)
        blob = raw[block*offset:block*offset+size]
        assert blob[:4] == b'BKHD' and len(blob) == size
        pos = 0
        while pos < len(blob):
            kind = blob[pos:pos+4]
            length = struct.unpack_from('<I', blob, pos+4)[0]
            if kind == b'HIRC':
                content = blob[pos+8:pos+8+length]
                at = 4
                for _ in range(struct.unpack_from('<I', content)[0]):
                    typ = content[at]
                    size = struct.unpack_from('<I', content, at+1)[0]
                    if typ == 4:
                        found.add(struct.unpack_from('<I', content, at+5)[0])
                    at += 5 + size
                assert at == len(content)
            pos += 8 + length
        assert pos == len(blob)
    assert event_hash('VO_Dialog_1') in found  # positive control
    return found, count


def main():
    plots = json.loads((batch.TABLES/'plotdata').read_bytes())
    dialogs = json.loads((batch.TABLES/'dialogdata').read_bytes())
    sections = []
    for display, identity in [('1-26',20021), ('2-1',20022)]:
        row = next(r for r in plots if r['plotID'] == identity)
        sections.append({'display_stage': display, 'plot': row,
                         'audio_ids': [d['audioID'] for d in dialogs if row['startDialogID'] <= d['dialogID'] <= row['endDialogID']]})
    evidence = []
    for label, package in [('original1.9', resources.DEFAULT19), ('reference2.4', resources.DEFAULT24)]:
        ids, count = events(package)
        evidence.append({'source': label, 'package': str(package), 'banks': count,
                         'positive_control': 'VO_Dialog_1',
                         'sections': [{**s, 'missing_events': [v for v in s['audio_ids'] if event_hash(v) not in ids]} for s in sections]})
    report = {'status': 'blocked_missing_required_voice_events_in_local_APKs', 'sources': evidence,
              'limitation': 'Does not establish whether downloadable voice packages contain these events. No substitute audio or disabled story.'}
    (WORK/'voice-source-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'sections': sections}, ensure_ascii=False))


if __name__ == '__main__':
    main()
