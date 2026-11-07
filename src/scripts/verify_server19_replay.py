"""Deterministic original-handler replay, with isolated copies of the latest save.

One mode per fresh process. Outputs include full wire bytes, ordered frames,
per-request timings/save hashes, and the final account for byte comparison.
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
import hashlib
import json
from pathlib import Path
import random
import secrets
import struct
import time


def run(runtime, source, output, requests, optimized=False, diagnose=False, hotspots=False, pools=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    data = output / 'data'
    data.mkdir()
    original = Path(source).read_bytes()
    (data / 'account.json').write_bytes(original)
    (data / 'nx-stage3-owned.json').write_text(json.dumps(
        {'purpose': 'nx-stage3-isolated', 'formal_save': False}))
    random.seed(420)
    secrets.token_hex = lambda n=32: 'ab' * n
    secrets.randbelow = lambda n: 0
    time.time = lambda: 1793592000.0
    import sys
    sys.path.insert(0, str(Path(runtime).resolve()))
    import server19_business_clock as clock
    real_local_now = clock.local_now
    clock.local_now = lambda now=None: real_local_now(1793592000.0 if now is None else now)
    import server19_portable as portable
    started = time.perf_counter()
    server, verified = portable.configure(data)
    import server19_stage as stage
    import server19_protocol as proto
    cache = None
    setup_s = time.perf_counter() - started
    cases = json.loads(Path(requests).read_bytes(), object_hook=lambda v: bytes.fromhex(v['__bytes__']) if set(v) == {'__bytes__'} else v)
    wire = bytearray()
    frames = []
    timings = []
    errors = []
    gc_events = []
    profiles = []
    active_request = [None]
    gc_started = {}
    profiler = None
    if diagnose:
        import gc
        if diagnose != 'gc':
            import cProfile
            profiler = cProfile.Profile()

        def gc_callback(phase, info):
            generation = info['generation']
            if phase == 'start':
                gc_started[generation] = time.perf_counter()
            else:
                gc_events.append({'request': active_request[0], 'generation': generation,
                                  'seconds': time.perf_counter() - gc_started[generation],
                                  'collected': info['collected']})
        gc.callbacks.append(gc_callback)
    original_event = server.event

    def event(kind, **values):
        if kind == 'game_request':
            active_request[0] = values['command']
            if profiler and values['command'] in ('GachaReq', 'GetClearStageActivityReq'):
                profiler.clear()
                profiler.enable()
        if kind == 'game_error':
            errors.append(values)
        return original_event(kind, **values)

    server.event = event

    class Socket:
        def __init__(self, cases):
            self.cases = iter(cases)
            self.current = None
            self.sign_key = None

        def settimeout(self, value):
            pass

        def recv(self, size):
            if self.current is not None:
                if profiler and self.current in ('GachaReq', 'GetClearStageActivityReq'):
                    profiler.disable()
                    import io
                    import pstats
                    stream = io.StringIO()
                    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
                    profiles.append({'request': self.current, 'type': self.values.get('type'),
                                     'num': self.values.get('num'), 'profile': stream.getvalue()})
                timings.append({'request': self.current,
                                'type': self.values.get('type'), 'num': self.values.get('num'),
                                'seconds': time.perf_counter() - self.started,
                                'account_sha256': hashlib.sha256(
                                    (data / 'account.json').read_bytes()).hexdigest()})
            try:
                case = next(self.cases)
            except StopIteration:
                self.current = None
                return b''
            name, values = case['name'], case['values'].copy()
            if name == 'StageEndReq':
                assert self.sign_key is not None
                values['sign'] = stage.stage_end_signature(values['body'], self.sign_key)
            self.current, self.started = name, time.perf_counter()
            self.values = values
            return proto.encode_frame(proto.CMD_IDS[name], proto.encode_message(name, values))

        def sendall(self, payload):
            pos = 0
            while pos < len(payload):
                size = 44 + struct.unpack_from('!I', payload, pos + 30)[0]
                proto.decode_frame(payload[pos:pos + size], verify_crc=True)
                pos += size
            assert pos == len(payload)
            wire.extend(payload)
            buffer = bytearray(payload)
            for frame in proto.take_frames(buffer):
                value = proto.decode_message(frame.name, frame.body)
                frames.append({'name': frame.name, 'value': value})
                if frame.name == 'StageBeginRsp':
                    assert value.get('retcode', 0) == 0, value
                    self.sign_key = value['sign_key']
            assert not buffer, 'partial response frame'

    server.GameHandler(Socket(cases), ('127.0.0.1', 0), None)
    # New GameHandler/Session, same isolated on-disk account.
    server.GameHandler(Socket([{'name': n, 'values': {}} for n in
                              ('PlayerLoginReq', 'GetMainDataReq', 'GetStageDataReq')]),
                       ('127.0.0.1', 0), None)
    assert len(timings) == len(cases) + 3, 'Handler stopped before all requests completed'
    assert not errors, errors
    if diagnose:
        gc.callbacks.remove(gc_callback)
        (output / 'diagnostics.json').write_text(json.dumps(
            {'profiles': profiles, 'gc': gc_events}, indent=2), encoding='utf-8')
    (output / 'wire.bin').write_bytes(wire)
    (output / 'frames.json').write_text(json.dumps(frames, ensure_ascii=False, default=lambda v: {'__bytes__': v.hex()}), encoding='utf-8')
    report = {'optimized': optimized, 'hotspots': hotspots, 'pools': pools, 'verified_files': verified,
              'source_sha256': hashlib.sha256(original).hexdigest(),
              'source_unchanged': Path(source).read_bytes() == original,
              'setup_seconds': setup_s, 'requests': timings,
              'total_seconds': sum(r['seconds'] for r in timings),
              'frame_count': len(frames), 'wire_sha256': hashlib.sha256(wire).hexdigest(),
              'account_sha256': hashlib.sha256((data / 'account.json').read_bytes()).hexdigest()}
    if cache:
        report['table_cache'] = cache[0]
        report['stage_cache'] = cache[1]()._asdict()
    assert report['source_unchanged']
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'source', 'output', 'requests'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--optimized', action='store_true')
    p.add_argument('--diagnose', action='store_true')
    p.add_argument('--hotspots', action='store_true')
    p.add_argument('--pools', action='store_true')
    args = p.parse_args()
    print(json.dumps(run(**vars(args))))
