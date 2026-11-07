"""Stop only the latest native story playing ID on dialogue lifecycle changes.

No StopAll, replacement playback, subtitle timing guesses or save operations.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib
import json
import struct
import server19_arm_native as n
from server19_arm_resources import module_base, jump
from server19_arm_story_presentation import add_rw_page
from server19_story_goal_prepare import OUT

PREFIXES = ('VO_Dialog_', 'VO_Weekly_Dialog_')
LIFECYCLE = (62480, 79062, 79059, 79067, 79068, 79051, 62467)
CAPTURE_SITE = 0x1642dc4


def build(version='native-dialog-interrupt-v2'):
    source = OUT/'native-lock-acceleration-v2/libil2cpp.so'
    image = n.ArmImage(source, expected_sha256=None)
    assert image.read(0x470420, 4) == n.word(0xe1a04001)
    assert image.read(0x4704c0, 4) == n.word(0xe1a04001)
    state_va = n.align(image.append_va+0x1000000)

    def state(code, reg):
        module_base(code, reg)
        code.immediate(12, state_va)
        code.emit(0xe080000c | (reg << 16) | (reg << 12))

    # Existing trace continues to log the real return value and preserve the
    # original Post branch/callbacks. Capture precedes it without changing r0.
    before = image.read(CAPTURE_SITE, 12)
    assert before[:8] == n.word(0xe59fc000)+n.word(0xe08ff00c)
    previous = CAPTURE_SITE+12+struct.unpack('<i', before[8:])[0]
    capture = image.allocate_code('capture current story playing ID', 2048,
                                  unwind=n.unwind_for_push(0x41f0, 16))
    c = n.ArmCode(capture)
    c.push(0x41ff)
    c.emit(0xe3500000); c.branch('restore', cond='eq')
    c.emit(0xe3540000); c.branch('restore', cond='eq')
    for i, prefix in enumerate(PREFIXES):
        c.load(0, 4, 8); c.immediate(1, len(prefix))
        c.emit(0xe1500001); c.branch('next'+str(i), cond='lt')
        raw = prefix.encode('utf-16le')
        for off in range(0, len(raw), 4):
            part = raw[off:off+4]; offset = 12+off
            if len(part) == 4: c.load(0, 4, offset)
            else: c.emit(0xe1d400b0 | ((offset & 0xf0) << 4) | (offset & 15))
            c.immediate(1, int.from_bytes(part, 'little'))
            c.emit(0xe1500001); c.branch('next'+str(i), cond='ne')
        state(c, 5); c.load(0, 13, 0); c.store(0, 5, 0)
        c.branch('restore'); c.label('next'+str(i))
    c.label('restore'); c.pop(0x41ff); jump(c, previous)
    code = c.finish()
    image.patch(capture, bytes(len(code)), code, 'Track only successful Dialogue/Weekly native playing IDs')
    image.patch(CAPTURE_SITE, before,
        n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(capture-CAPTURE_SITE-12),
        'Preserve original Post return, callback and existing diagnostics')

    stop = image.allocate_code('stop only captured story ID', 256,
                               unwind=n.unwind_for_push(0x4010))
    c = n.ArmCode(stop); c.push(0x4010)
    state(c, 4); c.load(0, 4, 0)
    c.emit(0xe3500000); c.branch('done', cond='eq')
    # Clear before StopPlayingID: an EndOfEvent callback may be reentrant.
    c.mov(1, 0); c.immediate(0, 0); c.store(0, 4, 0)
    # Original IL2CPP static ABI has an unused leading receiver in r0.
    # Both managed wrapper44713 and PInvoke44292 save playingID from r1.
    c.immediate(2, 0)
    c.call(image.method(44713))
    c.label('done'); c.pop(0x8010)
    code = c.finish(); image.patch(stop, bytes(len(code)), code, 'Specific ID only; never StopAll')

    hooks = []
    for mid in LIFECYCLE:
        entry = image.method(mid); before = image.read(entry, 12)
        instructions = image.disasm(va=entry, size=12)
        assert all('pc' not in x.op_str and x.mnemonic not in ('b', 'bl', 'blx') for x in instructions)
        trampoline = image.allocate_code('original dialog entry '+str(mid), 32, unwind=1)
        c = n.ArmCode(trampoline); c.emit(before); jump(c, entry+12)
        code = c.finish(); image.patch(trampoline, bytes(len(code)), code, 'Relocate proven PC-independent original prologue')
        desc = next(x for x in image.exidx if x['function_va'] == entry)
        image.unwinds = [x for x in image.unwinds if x[0] != trampoline]
        if desc['extab_va'] is None: image.register_unwind(trampoline, desc['descriptor'])
        else: image.register_unwind_external(trampoline, desc['extab_va'])
        hook = image.allocate_code('story interrupt '+str(mid), 128,
                                   unwind=n.unwind_for_push(0x41f0, 88))
        c = n.ArmCode(hook); c.push(0x41ff); c.emit(0xed2d0b12)
        c.call(stop)
        c.emit(0xecbd0b12); c.pop(0x41ff); jump(c, trampoline)
        code = c.finish(); image.patch(hook, bytes(len(code)), code, 'Preserve integer/VFP args and run original lifecycle')
        image.patch(entry, before,
            n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-entry-12), 'Stop active story voice only')
        hooks.append({'method_id': mid, 'name': n.metadata.N[mid], 'entry': entry,
                      'hook': hook, 'trampoline': trampoline})
    dest = OUT/version/'libil2cpp.so'; image.save(dest)
    rw = add_rw_page(dest, state_va)
    manifest = dest.with_suffix('.so.json'); data = json.loads(manifest.read_bytes())
    data.update(output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), extra_rw_segment=rw,
                output_bytes=dest.stat().st_size)
    manifest.write_text(json.dumps(data, indent=2), encoding='utf8')
    checked = n.ArmImage(dest, expected_sha256=None)
    assert not any(p[6] & 3 == 3 for p in checked.loads)
    report = {'status': 'prepared_human_pending', 'source': str(source),
              'capture_site': CAPTURE_SITE, 'capture': capture, 'previous_trace': previous,
              'state_va': state_va, 'stop': stop, 'stop_method': image.method(44713),
              'stop_ABI': {'unused_receiver_r0': 0, 'playing_ID_r1': True, 'method_info_r2': 0},
              'hooks': hooks, 'no_StopAll': True, 'no_RWX': True,
              'original_callbacks_and_Post_return_preserved': True,
              'text_and_coroutines_unchanged': True}
    (dest.parent/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    return report


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
