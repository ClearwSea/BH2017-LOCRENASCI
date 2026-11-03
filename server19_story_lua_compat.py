"""Route SP defense custom drops through the original SP dispatcher."""

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
import re

PATH = 'lua/mp/mpwavedispatch.lua'
ANCHOR = 'local goodId = LevelDesign:CreateCustomGoodsWithoutCallback(wave[1],wave[2], wave[3])'
GUARD = 'if not LevelDesign:IsMPLevel() then return _do_wave_original(wave) end'


def transform(path, raw):
    if path.startswith('lua/levels/mainline_stage06/') and b'LevelDesign:AddTeamBuffByID(' in raw:
        result,count=re.subn(rb'\bLevelDesign:AddTeamBuffByID\(',b'LevelDesign:AddTeamBuffById(',raw)
        return result,{'kind':'Use original native65714 AddTeamBuffById spelling; preserve buff IDs and showHintMsg arguments',
                      'calls':count,'source_sha256':hashlib.sha256(raw).hexdigest(),
                      'output_sha256':hashlib.sha256(result).hexdigest()}
    if path != PATH: return raw, None
    text = raw.decode('utf-8-sig')
    assert text.count(ANCHOR)==1
    assert 'local _do_wave_original = do_wave' in text
    result=text.replace(ANCHOR,GUARD+'\n\t\t'+ANCHOR).encode('utf-8')
    return result, {'kind':'SP custom drop dispatch uses original SP callback/coroutine path',
                    'MP branch':'original MP CreateCustomGoodsWithoutCallback, native72545 args3..4',
                    'source_sha256':hashlib.sha256(raw).hexdigest(),
                    'output_sha256':hashlib.sha256(result).hexdigest()}
