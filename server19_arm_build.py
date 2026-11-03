"""Compose one pinned original ARM network/resource candidate; never deploy.

All providers share one image and one final ELF/EHABI layout. A partial provider
implementation fails instead of creating a phone-deployable readiness claim.
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
from pathlib import Path
import argparse
import hashlib
import json

import server19_arm_native as native
import server19_arm_network as network
import server19_arm_resources as resources

ROOT = Path(__file__).resolve().parent
SUPPLIERS = ['text_lua', 'stringmap', 'metaconfig', 'baked', 'typed_metadata', 'async_json']


def build(directory, zig=None):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT) or directory.exists():
        raise ValueError('Build into a fresh project directory; preserve earlier candidates')
    directory.mkdir(parents=True)
    image = native.ArmImage()
    network_details = network.install(image)
    resource_details = resources.install(image, output_directory=directory / 'resources-build', zig=zig)
    # The module must report every installed class, rather than source intentions.
    if resource_details.get('supplier_scope') != SUPPLIERS:
        raise ValueError('ARM provider installation is incomplete')
    library = directory / 'libil2cpp.so'
    manifest = image.save(library)
    manifest.update(network=network_details, resources=resource_details,
                    supplier_scope=SUPPLIERS, architecture='armeabi-v7a_A32',
                    serial='REFERENCE_DEVICE', device_operation='none',
                    human_bridge_acceptance='pending', game_operation='none',
                    gyro_scope='Original phone gyro input retained; emulator gyro workaround not transplanted',
                    diagnostics_scope='Original errors and new resource failure logs; no x86 decode trace transplanted')
    manifest['build_source_files'] = [
        {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in map(Path, (native.__file__, network.__file__, resources.__file__, resources.SOURCE))]
    library.with_suffix('.so.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return library, manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--zig', type=Path)
    args = parser.parse_args()
    library, report = build(args.output_directory, args.zig)
    print(json.dumps({'candidate': str(library), 'sha256': report['output_sha256'],
                      'bytes': report['output_bytes'], 'suppliers': report['supplier_scope'],
                      'device_operation': 'none', 'human_bridge': 'pending'}))
