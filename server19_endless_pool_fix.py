"""Refill exhausted per-nature Endless bags without changing eligible enemies."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
def patch(source):
 marker = "\t\tlocal chosen_index = math.random(#uniqueBoxGachaByNature[this_nature])"
 if "-- Refill the exhausted nature bag" in source: return source
 assert source.count(marker)==1
 refill = """		-- Refill the exhausted nature bag with the same eligible enemies and weights.
		if #uniqueBoxGachaByNature[this_nature] == 0 then
			for _, entry in ipairs(InfiData.LastUniques) do
				if compatible_nature[entry.uniqueID] == this_nature then
					for j = 1, monster_number_per_box do
						table.insert(uniqueBoxGachaByNature[this_nature], entry.uniqueID)
					end
				end
			end
		end
"""
 return source.replace(marker, refill+marker)
