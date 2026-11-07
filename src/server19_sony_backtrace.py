"""One explicitly authorized Sony backtrace, streamed directly to a file.

--verify-output only prints debuggerd usage; it does not sample a process.
--capture performs exactly one sample and never retries. Human authorization
must cover that invocation, including any replacement for an earlier attempt.
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
import json
from pathlib import Path
import subprocess
import time

from server19_fuka601_deploy import ADB, SERIAL, PACKAGE, ACCOUNT

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'.local-baseline/server19-dev/story-all-20261015'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--verify-output',action='store_true')
    action.add_argument('--capture',action='store_true')
    args=parser.parse_args()
    if args.verify_output:
        out=WORK/'backtrace-output-check.txt'
        with out.open('wb') as stream:
            result=subprocess.run([str(ADB),'-s',SERIAL,'shell','debuggerd --help'],
                stdout=stream,stderr=subprocess.STDOUT,timeout=15)
        assert b'backtrace' in out.read_bytes()
        print('Direct binary file output verified; no process sampled')
        return
    identity=subprocess.run([str(ADB),'-s',SERIAL,'shell','pidof',PACKAGE],
        capture_output=True,text=True,timeout=15,check=True)
    pid=identity.stdout.strip()
    if not pid.isdecimal():raise ValueError('Expected exactly one game PID')
    out=WORK/('stack-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir(exist_ok=False)
    before=ACCOUNT.read_bytes()
    receipt={'pid':int(pid),'invocations':1,'status':'invoking','automatic_retry':False}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    with (out/'backtrace.txt').open('wb') as stream:
        result=subprocess.run([str(ADB),'-s',SERIAL,'shell',"su -c 'debuggerd -b "+pid+"'"],
            stdout=stream,stderr=subprocess.STDOUT,timeout=45)
    receipt.update(status='returned',returncode=result.returncode,
                   output_bytes=(out/'backtrace.txt').stat().st_size,
                   account_bytes_unchanged=ACCOUNT.read_bytes()==before)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(out.resolve())


if __name__=='__main__':main()
