"""Build a typed-table serializer isolation overlay on an existing ARM library.

No device, service or account changes. Keep original callers and error flow.
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
from pathlib import Path
import server19_arm_native as native
import server19_arm_resources as resources


def build(source, previous_payload, output):
    output = Path(output).resolve()
    if not output.is_relative_to(native.ROOT) or output.exists():
        raise ValueError('Use a fresh workspace output directory')
    output.mkdir()
    image = native.ArmImage(Path(source), expected_sha256=None)
    resources.generate_header(image, output)
    base = image.allocate_code('isolated typed serializer payload', resources.BLOCK_BYTES)
    elf, blob, _ = resources.compile_payload(image, output, base)
    image.patch(base, bytes(len(blob)), blob, 'independent typed serializer cycle state')
    resources.import_unwind(image, elf)
    prior = resources.Elf32(Path(previous_payload))
    entry = prior.symbols['arm_typed_supply']['va']
    before = prior.mapped(entry, 4)
    if image.read(entry, 4) != before:
        raise ValueError('Current typed supplier differs from the provided payload')
    image.patch(entry, before, native.arm_branch(entry, elf.symbols['arm_typed_supply']['va']),
                'typed supplier tail branch; original caller and exceptions retained')
    image.save(output / 'libil2cpp.so')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--previous-payload', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(build(args.source, args.previous_payload, args.output))
