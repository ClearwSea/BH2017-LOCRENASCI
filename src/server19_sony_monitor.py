"""Owned Sony ARM acceptance capture; no game control or account mutations.

Uses the existing bounded log collector, with an explicit physical-device
identity. The x86 device/deployment helper keeps its original ABI guard.
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
import re

import server19_device as device
import server19_story_batch_monitor as monitor

SERIAL = 'REFERENCE_DEVICE'
ROOT = Path(__file__).resolve().parent


def identity():
    device.SERIAL = SERIAL
    text = device.adb('shell', 'dumpsys', 'package', device.PKG)
    if 'versionName=1.9.0' not in text or 'primaryCpuAbi=armeabi-v7a' not in text:
        raise ValueError('Sony original1.9 ARM package identity changed')
    model = device.shell('getprop ro.product.model').strip()
    if model != 'SOV36' or 'uid=0(root)' not in device.shell('id', root=True):
        raise ValueError('Wrong or unrooted physical development device')
    uid = int(re.search(r'userId=(\d+)', text).group(1))
    path = re.search(r'codePath=(\S+)', text).group(1)
    if uid != 10107 or not path.startswith('/data/app/' + device.PKG + '-'):
        raise ValueError('Sony installation identity changed')
    return {'serial': SERIAL, 'package': device.PKG, 'uid': uid, 'code_path': path,
            'library': path + '/lib/arm/libil2cpp.so', 'abi': 'armeabi-v7a',
            'model': model, 'source': 'physical_device_readback'}


if __name__ == '__main__':
    monitor.SERIAL = SERIAL
    monitor.BASE = ROOT / 'server19-run/sony-arm-preparation/acceptance'
    device.SERIAL = SERIAL
    # Scoped to this collector process; never relax the x86 deployment guard.
    monitor.device.identity = identity
    monitor.main()
