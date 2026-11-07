"""Differential five-pool transaction tests, with real grant failures and pity."""

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
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import time


def run(runtime, source, output):
    import sys
    sys.path.insert(0,str(Path(runtime).resolve()))
    import server19_portable as portable
    import server19_gacha_cache
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    raw = Path(source).read_bytes()
    path = root / 'account.json'
    path.write_bytes(raw)
    portable.configure(root)
    import server19_stage as stage
    import server19_gacha as g
    import server19_gacha_policy as p
    import server19_business_clock as clock
    # configure installs candidates; restore the captured originals for baseline.
    original_draw = g._draw.__wrapped__.__wrapped__
    import copy
    g._draw = original_draw
    g.deepcopy = copy.deepcopy
    p.deepcopy = copy.deepcopy
    g._table_for = g._table_for.__wrapped__.__wrapped__
    g._awakened_avatar_ids = g._awakened_avatar_ids.__wrapped__
    # choices captures the source implementation in install; explicit reference.
    p.choices = p._uncached_choices
    stage._gacha_optimized = False
    now = clock.local_now
    time.time = lambda: 1793592000.0
    clock.local_now = lambda value=None: now(1793592000.0 if value is None else value)
    base = json.loads(raw)
    grant = g._grant
    results = []
    labels = []
    for optimized in (False, True):
        if optimized:
            server19_gacha_cache.install(stage)
        outcomes = []
        for channel in (1, 2, 10, 5, 3):
            for count in (1, 10):
                variants = ['normal', 'first-grant', 'all-grants', 'insufficient', 'tickets']
                if channel != 1:
                    variants += ['common-pity', 'rare-pity', 'collision-pity']
                    if p.has_up_pity(channel):
                        variants += ['up-pity']
                for variant in variants:
                    value = deepcopy(base)
                    value['main'].update(hcoin=1000000, friends_point=100000)
                    if variant == 'tickets':
                        for identity in (1101, 1102, 1103, 1105):
                            item = next((x for x in value['material_list'] if x['id'] == identity), None)
                            if item is None: value['material_list'].append(dict(id=identity, num=100))
                            else: item['num'] = 100
                    if variant == 'insufficient':
                        value['main'].update(hcoin=0, friends_point=0)
                        for item in value['material_list']:
                            if item['id'] in (1101, 1102, 1103, 1105):
                                item['num'] = 0
                    if variant.endswith('pity'):
                        state = p.state(value, channel)
                        state.update(since_common=0, since_rare=0, since_up=0, recent=[])
                        if variant == 'common-pity': state['since_common'] = 9
                        if variant == 'rare-pity': state['since_rare'] = 99
                        if variant == 'up-pity': state['since_up'] = 199
                        if variant == 'collision-pity':
                            state.update(since_common=8, since_rare=98, since_up=198)
                    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                    account = deepcopy(value)
                    random.seed(173)
                    calls = [0]

                    def failing_grant(account, *args):
                        calls[0] += 1
                        if variant == 'all-grants' or (variant == 'first-grant' and calls[0] == 1):
                            # Fail after the real grant mutated inventory, as well as payment.
                            grant(account, *args)
                            account['main']['hcoin'] -= 17
                            account['failed_grant_probe'] = [1]
                            raise ValueError('injected grant failure')
                        return grant(account, *args)

                    g._grant = failing_grant
                    response = g.response('GachaReq', account,
                        {'type': channel, 'num': count, 'is_use_hcoin': variant != 'tickets'},
                        account_path=path)
                    if variant in ('insufficient', 'all-grants'):
                        assert response[1]['retcode'] != 0
                        assert json.loads(path.read_bytes()) == value
                    else:
                        assert response[1]['retcode'] == 0, (channel, count, variant, response)
                        assert len(response[1]['item_list']) == count
                    assert 'failed_grant_probe' not in account
                    for key in ('stage_runtime', 'endless_climate'):
                        assert account[key] == value[key]
                    outcomes.append((response, account, path.read_bytes(), random.getstate(), calls[0]))
                    if not optimized: labels.append(f'{channel}:{count}:{variant}')
        results.append(outcomes)
    for label, before, after in zip(labels, *results):
        assert before == after, label
    g._grant = grant
    for channel in (2, 10, 5, 3):
        choices = p.choices(channel)
        original = deepcopy(choices)
        choices.clear()
        assert p.choices(channel) == original
    assert Path(source).read_bytes() == raw
    report = {'status': 'PASS', 'checks': labels,
              'response_save_rng_retry_identical': True, 'candidate_ownership': True,
              'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_unchanged': True}
    (root / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'source', 'output'):
        parser.add_argument('--' + name, required=True)
    print(json.dumps(run(**vars(parser.parse_args()))))
