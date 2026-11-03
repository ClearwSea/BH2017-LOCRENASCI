"""Offline Sony candidate: native subtitle-timed seeking and reversible test damage.

No device, save or service operations. Unavailable sentence timings never mute audio.
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
import json
import struct
import hashlib
import server19_arm_native as n
from server19_arm_resources import module_base, jump
from server19_story_goal_prepare import OUT


def build(version='native-dialog-seek-damage10-v3', multiplier=10):
    if multiplier != 10:
        raise ValueError('Only the explicitly requested tenfold test output is supported')
    parent = OUT/'native-dialog-interrupt-v2'
    spec = json.loads((parent/'report.json').read_bytes())
    image = n.ArmImage(parent/'libil2cpp.so', expected_sha256=None)
    original = n.ArmImage(OUT/'native-lock-acceleration-v2/libil2cpp.so', expected_sha256=None)
    hooks = {x['method_id']: x for x in spec['hooks']}
    # First tap merely completes the typewriter; this is not a sentence change.
    entry = hooks[62480]['entry']
    image.patch(entry, image.read(entry, 12), original.read(entry, 12),
                'Restore native typewriter completion without stopping shared voice')

    seek = image.allocate_code('seek shared dialogue to native next-page timing', 1536,
                               unwind=n.unwind_for_push(0x41f0, 16))
    c = n.ArmCode(seek); c.push(0x41f0); c.emit(0xe24dd010)
    c.mov(4, 0); c.emit(0xe3540000); c.branch('done', cond='eq')
    module_base(c, 5); c.immediate(12, spec['state_va'])
    c.emit(0xe085500c); c.load(5, 5, 0)
    c.emit(0xe3550000); c.branch('done', cond='eq')
    c.load(6, 4, 0x48)  # Coroutine increments after displaying a chat: next index.
    c.emit(0xe3560001); c.branch('done', cond='lt')
    c.immediate(0, 1024); c.emit(0xe1560000); c.branch('done', cond='gt')
    c.load(0, 4, 0x4c); c.emit(0xe3500000); c.branch('done', cond='eq')
    c.load(7, 0, 0x18); c.emit(0xe3570000); c.branch('done', cond='eq')
    c.load(0, 7, 12); c.emit(0xe1560000); c.branch('done', cond='ge')
    c.load(7, 7, 8); c.emit(0xe3570000); c.branch('done', cond='eq')
    c.load(0, 7, 12); c.emit(0xe1560000); c.branch('done', cond='ge')
    c.emit(0xe2877010); c.immediate(8, 0)
    c.label('sum')
    c.emit(0xe4970004); c.emit(0xe3500000); c.branch('done', cond='eq')
    c.load(0, 0, 12)
    # Positive finite native chatDuration only; no guessed cuts for zero/NaN.
    c.emit(0xe3500000); c.branch('done', cond='le')
    c.immediate(1, 0x45610000); c.emit(0xe1500001); c.branch('done', cond='ge')
    c.emit(0xee008a10)  # vmov s0,r8
    c.emit(0xee000a90)  # vmov s1,r0
    c.emit(0xee300a20)  # vadd.f32 s0,s0,s1
    c.emit(0xee108a10)  # vmov r8,s0
    c.emit(0xe2566001); c.branch('sum', cond='ne')
    c.immediate(1, 0x45610000); c.emit(0xe1580001); c.branch('done', cond='ge')
    c.immediate(0, 0x447a0000); c.emit(0xee000a90)  # 1000 milliseconds/second
    c.emit(0xee200a20); c.emit(0xeebd0ac0); c.emit(0xee108a10)
    c.load(0, 4, 0x4c); c.load(1, 0, 0x1c)
    c.emit(0xe3510000); c.branch('done', cond='eq')
    c.immediate(0, 0); c.immediate(2, 0); c.call(image.method(44663))
    c.emit(0xe3500000); c.branch('done', cond='eq')
    # SeekOnEvent(uint, GameObject, int milliseconds, bool, uint playingID).
    # The original story Post uses null gameObject; use the same auto-registration.
    c.mov(1, 0); c.immediate(0, 0); c.immediate(2, 0); c.mov(3, 8)
    c.immediate(12, 0); c.store(12, 13, 0); c.store(5, 13, 4); c.store(12, 13, 8)
    c.call(image.method(44692))
    c.label('done'); c.emit(0xe28dd010); c.pop(0x81f0)
    raw = c.finish(); image.patch(seek, bytes(len(raw)), raw, 'Use authored chat durations and current playing ID')
    h = hooks[79062]
    c = n.ArmCode(h['hook']); c.push(0x41ff); c.emit(0xed2d0b12)
    c.call(seek); c.emit(0xecbd0b12); c.pop(0x41ff); jump(c, h['trampoline'])
    raw = c.finish(); image.patch(h['hook'], image.read(h['hook'], len(raw)), raw,
                                'Manual next chat seeks instead of stopping the whole event')

    # DamageModelLogic's normal finalization path: all mitigation already applied.
    # Original constants RuntimeIDManager.AVATAR_CATE=3, MONSTER_CATE=4.
    # Skip rejected/early returns; retain original FinalResolved transition.
    damage_site = 0x9e1f64
    expected = n.word(0xe3a00002)+n.word(0xe58400cc)+n.word(0xe1a00004)
    assert image.read(damage_site, 12) == expected
    assert image.field_offset('MoleMole.AttackData', 'attackerCategory') == 0x6a
    damage = image.allocate_code('tenfold avatar final damage for human story acceptance', 512,
                                 unwind=n.unwind_for_push(0x4010, 24))
    c = n.ArmCode(damage); c.push(0x401f); c.emit(0xed2d0b02)
    c.emit(0xe1d406ba)  # ldrh r0,[r4,#0x6a]
    c.emit(0xe3500003); c.branch('finish', cond='ne')
    c.immediate(0, 0x41200000); c.emit(0xee000a90)  # s1=10
    for offset in (8, 12, 16, 20):
        c.load(0, 4, offset)
        c.emit(0xe3500000); c.branch('next'+str(offset), cond='le')
        c.immediate(1, 0x7f800000); c.emit(0xe1500001)
        c.branch('next'+str(offset), cond='hs')
        # Keep boosted finite positive damage finite at the float range boundary.
        c.immediate(1, 0x7dcccccb); c.emit(0xe1500001)
        c.branch('multiply'+str(offset), cond='ls')
        c.immediate(0, 0x7f7fffff); c.store(0, 4, offset); c.branch('next'+str(offset))
        c.label('multiply'+str(offset))
        c.emit(0xee000a10); c.emit(0xee200a20); c.emit(0xee100a10); c.store(0, 4, offset)
        c.label('next'+str(offset))
    c.label('finish'); c.emit(0xecbd0b02); c.pop(0x401f)
    c.emit(expected); jump(c, damage_site+12)
    raw = c.finish(); image.patch(damage, bytes(len(raw)), raw, 'Scale four final damage channels only for avatar attackers')
    image.patch(damage_site, expected,
                n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(damage-damage_site-12),
                'Reversible local acceptance damage multiplier; no save edits')
    dest = OUT/version/'libil2cpp.so'; image.save(dest)
    report = dict(status='prepared_human_pending', source=str(parent/'libil2cpp.so'),
                  seek=seek, seek_method=image.method(44692), hash_method=image.method(44663),
                  show_next_chat=h, skip_dialog_entry=entry,
                  state_va=spec['state_va'], retained_stop_methods=[79059,79067,79068,79051,62467],
                  damage=damage, damage_site=damage_site, multiplier=multiplier,
                  attacker_category=3, damage_channels=[8,12,16,20],
                  missing_timing='retain voice; do not guess or stop',
                  no_save_changes=True, no_service_changes=True,
                  output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    (dest.parent/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(build(),indent=2))
