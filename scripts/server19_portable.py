"""独立目录启动现有业务 / Relocatable host for unchanged server business code.

No formal save is bundled or implicitly imported. Call configure once per process.
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
import hashlib
import json
import threading
from copy import deepcopy

ROOT = Path(__file__).resolve().parent


def verify():
    manifest = json.loads((ROOT / 'portable-manifest.json').read_bytes())
    for row in manifest['files']:
        path = (ROOT / row['path']).resolve()
        path.relative_to(ROOT)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Runtime file changed: ' + row['path'])
    return len(manifest['files'])


def install_table_cache(stage):
    from server19_table_cache import install_table_cache as install
    return install(stage, ROOT, startup=True)


def configure(data_directory):
    verified = verify()
    data = Path(data_directory).resolve()
    if data == ROOT or ROOT in data.parents:
        raise ValueError('Writable data must be separate from the runtime bundle')
    data.mkdir(parents=True, exist_ok=True)
    import server19 as s
    import server19_stage as stage
    import server19_equipment as equipment
    s.PORTABLE_TABLE_CACHE = install_table_cache(stage)
    try:
        base = ROOT / '.local-baseline/server19-dev'
        stage.STORY_RUNTIME_READY_FILE = base / 'chapter1-remaining-ready/runtime-ready.json'
        metadata = base / 'chapter1-unified-ready/v1/_exceloutputasset'
        stage.TABLE_OVERRIDES = {n: metadata / n for n in ('materialdata', 'avatarfragmentdata', 'constvaluesclient', 'textmap')}
        stage.TABLE_OVERRIDES['textmap'] = base / 'sony-human-fixes-v1/textmap'
        equipment.FULL_CULTIVATION_READY_FILE = base / 'cultivation-full-equipment-ready/runtime-ready.json'
        s.RUN = data
        stage.DEFAULT_ACCOUNT = data / 'account.json'
        s.LOCAL_RECHARGE_ENABLED = True
        import server19_story_all_server
        import server19_story_trial_policy
        import server19_extra_story
        import server19_openworld
        server19_story_all_server.configure()
        runtime = ROOT / 'server19-run'
        server19_story_trial_policy.configure(runtime / 'razer-migration-20261025/trial-policy')
        stage.TABLE_OVERRIDES['stagerevivecostdata'] = runtime / 'razer-migration-20261025/revive-diagnosis/stagerevivecostdata'
        server19_extra_story.configure(runtime / 'kallen-20261025/all-open-delivery')
        server19_openworld.configure(runtime / 'sakura-cycle4-20261026/candidate-v1/catalog.json')
        stage.TABLE_OVERRIDES['stigmatadata'] = runtime / 'sakura-20261025/candidate-v1/_exceloutputasset/stigmatadata'
        server19_openworld.configure_commissions(runtime / 'sakura-commissions-20261025/candidate-v3/catalog.json')
        server19_openworld.configure_cooking(runtime / 'sakura-cooking-20261026/catalog.json')
        s.server19_endless.configure(runtime / 'endless-temperature-mapping-20261027/hp-only-delivery/catalog.json')
        import server19_config_cache
        import server19_gacha_cache
        server19_config_cache.install(stage)
        server19_gacha_cache.install(stage)
        import server19_request_cost
        import server19_gacha
        import server19_gacha_policy
        server19_request_cost.install_cost_observer(stage, server19_gacha, server19_gacha_policy, s)
        s.load_account()
    except BaseException:
        stage._finish_startup_tables(validate=False)
        raise
    else:
        stage._finish_startup_tables()
    return s, verified


def start(s, http_port=0, tcp_port=0):
    import server19_http as h
    tcp = s.GameServer(('127.0.0.1', tcp_port), s.GameHandler)
    try:
        http = h.ThreadingHTTPServer(('127.0.0.1', http_port), h.make_handler(
            s.event, '127.0.0.1', http_port, tcp.server_address[1], local_recharge=True))
        # Port zero is useful for isolated technical checks; advertise the selected port.
        http.RequestHandlerClass = h.make_handler(s.event, '127.0.0.1', http.server_address[1],
                                                 tcp.server_address[1], local_recharge=True)
    except BaseException:
        tcp.server_close()
        raise
    for server in (http, tcp):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return http, tcp


def stop(servers):
    for server in servers:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--http-port', type=int, default=21118)
    parser.add_argument('--tcp-port', type=int, default=21119)
    args = parser.parse_args()
    s, count = configure(args.data_dir)
    servers = start(s, args.http_port, args.tcp_port)
    print(json.dumps({'verified_files': count, 'ports': [x.server_address[1] for x in servers]}), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        stop(servers)
