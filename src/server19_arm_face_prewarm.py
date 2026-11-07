"""Preload original face atlas textures before handing a provider to animation.

Does not replace expressions or skip resource loading. Candidate for the
observed synchronous FaceAtlas/Kiana/Eye/13 wait during level-end animation.
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
import argparse
import server19_arm_native as n
from server19_arm_resources import jump


def build(source, output, sha):
    im = n.ArmImage(source, expected_sha256=sha)
    assert im.field_offset('MoleMole.AtlasMatInfoProvider', 'items') == 0x14
    hook = im.method(82598)
    before = im.read(hook, 12)
    assert before.hex() == 'f04f2de91cb08de204d04de2'
    trampoline = im.allocate_code('Original face provider fetch prologue', 32,
        unwind=n.unwind_for_push(0x4ff0, 4))
    t = n.ArmCode(trampoline)
    t.emit(before)
    jump(t, hook + 12)
    code = t.finish()
    im.patch(trampoline, bytes(len(code)), code, 'Replay original non-PC-relative prologue')
    wrapper = im.allocate_code('Face atlas native texture prewarm', 256,
        unwind=n.unwind_for_push(0x41f0, 24))
    c = n.ArmCode(wrapper)
    c.push(0x41f0)
    c.emit(0xe24dd018)
    c.call(trampoline)
    c.mov(4, 0)
    c.emit(0xe3500000)
    c.branch('done', cond='eq')
    c.load(6, 4, 0x14)
    c.emit(0xe3560000)
    c.branch('done', cond='eq')
    c.load(6, 6, 0xc)
    c.immediate(5, 0)
    c.label('loop')
    c.emit(0xe1550006)
    c.branch('done', cond='hs')
    c.mov(0, 13)  # 20-byte original FaceMatInfo struct return buffer.
    c.mov(1, 4)
    c.mov(2, 5)
    c.immediate(3, 0)
    c.call(im.method(82600))
    c.emit(0xe2855001)
    c.branch('loop')
    c.label('done')
    c.mov(0, 4)
    c.emit(0xe28dd018)
    c.pop(0x81f0)
    code = c.finish()
    im.patch(wrapper, bytes(len(code)), code, 'Use original GetFaceMatInfo and its texture retention list')
    im.patch(hook, before, n.word(0xe59fc000) + n.word(0xe08ff00c) +
             n.word(wrapper - (hook + 12)), 'Prewarm before native face provider is consumed')
    im.save(output)
    return im, wrapper, trampoline


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('output'); p.add_argument('sha')
    a = p.parse_args()
    build(a.source, a.output, a.sha)
