"""Restore ordinary Extra chapter entries outside the later short-story registry."""

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
from pathlib import Path
import server19_arm_native as n


def build(source, output, expected_sha256):
    image = n.ArmImage(source, expected_sha256)
    # ShowExEntry(70719): a valid chapter can have no ShortStoryData (Xuanyuan).
    # Keep the existing challenge-chapter exclusion for registered short stories.
    # The earlier null chapter check remains an error.
    site = 0x1457ebc
    image.patch(0x1457e90, n.word(0xe3a04000), n.word(0xe3a04001),
                'Default ordinary Extra entry visible')
    image.patch(site, n.arm_branch(site, 0x1457edc, cond='eq'),
                n.arm_branch(site, 0x1457ed4, cond='eq'), 'Return visible for absent ShortStoryData')
    image.patch(0x1457ed0, n.word(0x13004001), n.word(0x03a04000),
                'Registered challenge chapter remains hidden')
    image.save(output)
    result = dict(source_sha256=expected_sha256, sha256=hashlib.sha256(Path(output).read_bytes()).hexdigest(),
                  site=site, method=70719, human_acceptance='pending')
    Path(output).with_suffix('.entry.json').write_text(json.dumps(result, indent=2))
    return result


def build_map(source, output, expected_sha256):
    image = n.ArmImage(source, expected_sha256)
    # Reset(82000) clears the challenge-only team unconditionally. Ordinary
    # Extra chapters have no ShortStoryData, but still need the remaining map init.
    image.patch(0xf74538, n.arm_branch(0xf74538, 0xf7477c, cond='eq'),
                n.arm_branch(0xf74538, 0xf74558, cond='eq'),
                'Skip challenge team reset only when no short-story data exists')
    # r5 was zeroed inside that optional block; r1 is always zero here.
    image.patch(0xf7456c, n.word(0xe58450f4), n.word(0xe58410f4),
                'Initialize current map state independently of optional team reset')
    image.save(output)
    result = dict(source_sha256=expected_sha256,sha256=hashlib.sha256(Path(output).read_bytes()).hexdigest(),
                  method=82000,human_acceptance='pending')
    Path(output).with_suffix('.map.json').write_text(json.dumps(result,indent=2))
    return result


def build_widgets(source, output, expected_sha256):
    from server19_arm_resources import jump
    image = n.ArmImage(source, expected_sha256)
    # Missing short-story data means mode zero for optional challenge widgets.
    # Continue the native inactive-widget path rather than skipping map refresh.
    for site, old, target in ((0xf7677c,0xf76c1c,0xf76788),
                              (0xf76e64,0xf76e94,0xf76e70),
                              (0xf76be8,0xf76c1c,0xf76bf4)):
        image.patch(site,n.arm_branch(site,old,cond='eq'),n.arm_branch(site,target,cond='eq'),
                    'Ordinary Extra chapter has no challenge mode')
    # RefreshView_BronyaExEntry previously enabled info/memory buttons even for
    # ordinary Extra chapters. Resolve registration once, in the existing frame.
    site=0xf76ce8
    hook=image.allocate_code('Short-story entry eligibility',256,unwind=n.unwind_for_push(0x4c70))
    before=n.word(0xe5940028)+n.word(0xe3500000)+n.arm_branch(0xf76cf0,0xf76e94,cond='eq')
    c=n.ArmCode(hook);c.mov(0,4);c.call(0xf6f560)
    c.emit(0xe3500000);c.emit(0xe3a06000);c.emit(0x13a06001)
    c.load(0,4,0x28);c.emit(0xe3500000);c.branch('null',cond='eq');jump(c,0xf76cf4)
    c.label('null');jump(c,0xf76e94)
    raw2=c.finish();image.patch(hook,bytes(len(raw2)),raw2,'Preserve canvas-null error path')
    image.patch(site,before,n.word(0xe59fc000)+n.word(0xe08ff00c)+n.word(hook-site-12),
                'Resolve whether short-story controls apply')
    for address in (0xf76d5c,0xf76ddc):
        image.patch(address,n.word(0xe3a01001),n.word(0xe1a01006),'Only show short-story buttons for registered chapters')
    image.save(output)
    result=dict(source_sha256=expected_sha256,sha256=hashlib.sha256(Path(output).read_bytes()).hexdigest(),
                eligibility_hook=hook,human_acceptance='pending')
    Path(output).with_suffix('.widgets.json').write_text(json.dumps(result,indent=2))
    return result
