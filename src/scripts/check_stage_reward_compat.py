"""Check real ARM reward getters and copied-account settlement; no device writes."""

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
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'.local-baseline/server19-dev/story-goal-tools/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC
import server19_stage_reward_compat as compat
import server19_arm_native as native
import server19_protocol as proto


def main():
    folder = ROOT/'server19-run/sony-resume-20261025/settlement-failure-10433'
    source = folder/'phone-stagedata-before.json'
    before = source.read_bytes()
    payload, changes = compat.patch_payload(before)
    rows, fixed = json.loads(before), json.loads(payload)
    assert [r['stage_id'] for r in changes] == list(compat.STAGE_IDS)
    for old, new in zip(rows, fixed):
        changed = {k for k in old if old[k] != new[k]}
        assert changed == (set(compat.RATIO_FIELDS) if old['levelId'] in compat.STAGE_IDS else set())
    assert not compat.audit(fixed)['ratio_anomaly_ids']
    assert compat.audit(rows)['reward_limit_mismatch_ids'] == compat.audit(fixed)['reward_limit_mismatch_ids']
    assert compat.patch_payload(payload) == (payload, [])
    bad = deepcopy(rows)
    next(r for r in bad if r['levelId'] == 10433)['scoinInside'] = 4.7
    try:
        compat.repair(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Unreviewed preimage accepted')

    image = native.ArmImage()
    def getter(mid, row):
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        address = image.method_code_addr(mid)
        page = address & ~4095
        u.mem_map(page, 4096)
        u.mem_write(page, image.read(page, 4096))
        u.mem_map(0x10000, 0x10000)
        u.mem_write(0x10178, struct.pack('<I', 0x11000))
        u.mem_write(0x11048, struct.pack('<ifif', row['avatarExpReward'],
            row['avatarExpInside'], row['scoinReward'], row['scoinInside']))
        u.reg_write(UC_ARM_REG_R0, 0x10100)
        u.reg_write(UC_ARM_REG_SP, 0x1f000)
        u.reg_write(UC_ARM_REG_LR, 0x1ff00)
        u.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        u.emu_start(address, 0x1ff00, count=100)
        return struct.unpack('<f', struct.pack('<I', u.reg_read(UC_ARM_REG_R0)))[0]
    original = next(r for r in rows if r['levelId'] == 10433)
    assert getter(68413, original) == -101
    assert abs(getter(68415, original) + 3060) < .01
    native_checks = []
    for row in fixed:
        if row['levelId'] not in compat.STAGE_IDS:
            continue
        values = [getter(mid, row) for mid in (68413, 68414, 68415, 68416)]
        assert all(v >= 0 for v in values)
        assert abs(values[0] + values[1] - row['avatarExpReward']) < .01
        assert abs(values[2] + values[3] - row['scoinReward']) < .01
        native_checks.append({'stage_id': row['levelId'], 'reward_parts': values})

    run = ROOT/'server19-run/black3d-repair/local-comparison-1791780361'
    live = run/'scratch-server/account.json'
    live_bytes = live.read_bytes()
    pc = ROOT/'server19-run/emulator-recording-20261017/scratch-server/account.json'
    pc_bytes = pc.read_bytes()
    wrapper = run/'run-comparison-server.py'
    exec(compile(wrapper.read_text().split('http=h.ThreadingHTTPServer')[0], str(wrapper), 'exec'),
         {'__file__': str(wrapper)})
    import server19_stage as stage
    account = json.loads((folder/'account现场.json').read_bytes())
    copy = folder/'isolated-account.json'
    copy.write_text(json.dumps(account), encoding='utf8')
    events = [json.loads(x) for x in (folder/'server-stdout.log').read_text(encoding='utf8').splitlines()]
    wire = next(r for r in reversed(events) if r['event'] == 'game_stage_wire' and r['command'] == 'StageEndReq')
    failed = proto.decode_message('StageEndReq', bytes.fromhex(wire['body_hex']))
    assert stage.response('StageEndReq', account, failed, account_path=copy)[1] == {'retcode': 3}
    body = proto.decode_message('StageEndReqBody', failed['body'])
    repaired = next(r for r in fixed if r['levelId'] == 10433)
    body.update(avatar_exp_reward=int(getter(68413, repaired)), scoin_reward=int(getter(68415, repaired)))
    raw = proto.encode_message('StageEndReqBody', body)
    signed = {'body': raw, 'sign': stage.stage_end_signature(raw,
        account['stage_runtime']['active']['begin_response']['sign_key'])}
    result = stage.response('StageEndReq', account, signed, account_path=copy)
    assert result[1]['retcode'] == 0, result
    assert result[1]['avatar_exp_reward'] == 101 and result[1]['scoin_reward'] == 1809
    committed = copy.read_bytes()
    assert stage.response('StageEndReq', account, signed, account_path=copy) == result
    assert copy.read_bytes() == committed
    assert live.read_bytes() == live_bytes and pc.read_bytes() == pc_bytes
    (folder/'candidate-stagedata_main').write_bytes(payload)
    report = dict(status='PASS', changed_rows=changes, audit_before=compat.audit(rows),
        audit_after=compat.audit(fixed), native_getter_checks=native_checks,
        copied_account_settlement=result[1], retry_idempotent=True,
        live_and_pc_accounts_unchanged=True, human_acceptance='pending',
        candidate_sha256=hashlib.sha256(payload).hexdigest())
    (folder/'technical-check.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print('PASS: six-row preservation, original ARM reward getters, copied settlement and retry; live/PC unchanged.')


if __name__ == '__main__':
    main()
