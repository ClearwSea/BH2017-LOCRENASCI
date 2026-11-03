"""隔离账号技术检查，不执行战斗 / Isolated protocol/storage smoke, no battle.

Use a fresh data directory. Existing probe data may be reused to check persistence.
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
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import struct
import sys
import time
from urllib.request import urlopen

SERVERS = None


def exchange(sock, proto, name, values, expected, expected_retcode=0):
    sock.sendall(proto.encode_frame(name, proto.encode_message(name, values)))
    buffer = bytearray()
    while True:
        raw = sock.recv(65536)
        if not raw:
            raise RuntimeError('Server disconnected before ' + expected)
        buffer.extend(raw)
        for frame in proto.take_frames(buffer):
            if frame.name == expected:
                result = proto.decode_message(frame.name, frame.body)
                if result.get('retcode', 0) != expected_retcode:
                    raise ValueError((expected, result))
                return result


def run(data_directory, http_port=0, tcp_port=0, keep_alive=False):
    global SERVERS
    import server19_portable as portable
    started = time.monotonic()
    data = Path(data_directory).resolve()
    if (data / 'account.json').exists() and not (data / 'probe-owned.json').exists():
        raise ValueError('Refusing an existing non-probe account')
    data.mkdir(parents=True, exist_ok=True)
    (data / 'probe-owned.json').write_text('{"purpose":"isolated technical validation"}', encoding='utf-8')
    previous = json.loads((data / 'account.json').read_bytes()) if (data / 'account.json').exists() else None
    s, verified = portable.configure(data)
    import server19_protocol as proto
    import server19_stage as stage
    import server19_endless_climate as climate
    import numpy as np
    from zoneinfo import ZoneInfo
    from datetime import datetime
    report = dict(status='RUNNING', python=sys.version, numpy=np.__version__, machine=platform.machine(),
                  pointer_bits=struct.calcsize('P') * 8, pid=os.getpid(), verified_files=verified,
                  root=str(portable.ROOT), data=str(data),
                  prior_probe_nickname=previous['main']['nickname'] if previous else None,
                  human_gameplay=False, formal_save_used=False)
    servers = portable.start(s, http_port, tcp_port)
    SERVERS = servers
    try:
        hp, tp = [server.server_address[1] for server in servers]
        report['ports'] = [hp, tp]
        health = json.load(urlopen(f'http://127.0.0.1:{hp}/health', timeout=10))
        assert health['status'] == 'ok' and health['game_port'] == tp
        dispatch = json.load(urlopen(f'http://127.0.0.1:{hp}/query_gateway', timeout=10))
        assert dispatch['gameserver'] == {'ip': '127.0.0.1', 'port': tp}
        report['http'] = 'health and dispatch passed'
        with socket.create_connection(('127.0.0.1', tp), timeout=15) as sock:
            sock.settimeout(30)
            requests = ['GetPlayerTokenReq', 'PlayerLoginReq', 'GetMainDataReq',
                        'GetEquipmentDataReq', 'GetAvatarDataReq', 'GetConfigReq',
                        'GetMissionDataReq', 'GetAvatarTeamDataReq', 'GetIslandReq',
                        'GetExtraStoryDataReq', 'GetOpenworldReq', 'GetEndlessDataReq']
            responses = {}
            for name in requests:
                if name not in proto.CMD_IDS:
                    raise ValueError('Unknown test request: ' + name)
                # The fresh Lv15 fixture must remain below Endless's Lv25 gate.
                values = exchange(sock, proto, name, {}, name[:-3] + 'Rsp',
                                  3 if name == 'GetEndlessDataReq' else 0)
                responses[name] = {'retcode': values.get('retcode', 0), 'fields': sorted(values)}
            report['tcp'] = responses
            # Profile-only test mutation; no rewards, stage entry or settlement.
            exchange(sock, proto, 'NicknameModifyReq', {'nickname': 'ARM32测试'}, 'NicknameModifyRsp')
            saved = json.loads((data / 'account.json').read_bytes())
            assert saved['main']['nickname'] == 'ARM32测试'
            assert not saved.get('stage_runtime', {}).get('receipts')
            report['atomic_profile_persistence'] = True
        # Stop and re-open sockets to test account reload, separate from process restart.
        portable.stop(servers)
        servers = portable.start(s, hp, tp)
        SERVERS = servers
        with socket.create_connection(('127.0.0.1', tp), timeout=15) as sock:
            sock.settimeout(30)
            exchange(sock, proto, 'PlayerLoginReq', {}, 'PlayerLoginRsp')
            main = exchange(sock, proto, 'GetMainDataReq', {}, 'GetMainDataRsp')
            assert main['nickname'] == 'ARM32测试'
        report['restart_persistence'] = True
        report['available_stages'] = len(stage.supported_stage_ids())
        # Exercise the actual NumPy random generator, full population projection and rollover.
        c = climate.create(1792968000)
        p = deepcopy(climate.project(c))
        climate.advance(c)
        report['climate'] = {key: p[key] for key in ['next_temperature', 'participants', 'clear_rate', 'reason']}
        report['climate']['rollover_begin'] = c['begin']
        report['climate']['population_id_sha256'] = hashlib.sha256(json.dumps(c['ids'], separators=(',', ':')).encode()).hexdigest()
        report['timezone'] = datetime(2026, 10, 27, tzinfo=ZoneInfo('Asia/Shanghai')).isoformat()
        # Populate lazy catalog readers without granting or purchasing anything.
        import server19_gacha as gacha
        report['gacha_eligibility_rows'] = len(json.loads(gacha.ELIGIBILITY.read_bytes())['items'])
        report['table_cache'] = dict(s.PORTABLE_TABLE_CACHE)
        report['status'] = 'PASS'
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (data / 'smoke-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return report
    finally:
        if not keep_alive or report['status'] != 'PASS':
            portable.stop(servers)
            SERVERS = None


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.data_dir), ensure_ascii=False, indent=2))
