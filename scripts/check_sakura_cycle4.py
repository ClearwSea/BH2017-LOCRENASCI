"""Isolated approved cycle transition/reward checks, no live-account access."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server19_openworld as world
import server19_protocol as proto


def check():
    world.configure(ROOT / 'server19-run/sakura-cycle4-20261026/candidate-v1/catalog.json')
    with tempfile.TemporaryDirectory(prefix='sakura4-') as folder:
        path = Path(folder) / 'account.json'
        a = dict(schema=1, uid=99999, main=dict(level=41, scoin=0, hcoin=0, equipment_size_limit=100),
                 avatar_list=[dict(avatar_id=101, star=1)], material_list=[],
                 openworld_data=dict(cycle=3, finish_story_id_list=list(range(101, 112)) + list(range(201, 208)) + list(range(301,309))))
        path.write_text(json.dumps(a))
        def request(name, **values):
            response_name, result = world.response(name, a, values, account_path=path)
            proto.decode_message(response_name, proto.encode_message(response_name, result))
            return result
        assert request('GetOpenworldReq')['cycle'] == 4
        assert not a['openworld_data'].get('has_take_finish_reward_cycle')
        assert request('OpenworldStageBeginReq', area_id=101, avatar_id_list=[101])['retcode'] == 2
        assert request('AcceptOpenworldStoryReq', story_id=401)['retcode'] == 2
        a['main']['level'] = 42
        path.write_text(json.dumps(a))
        assert request('OpenworldStageBeginReq', area_id=101, avatar_id_list=[101])['retcode'] == 0
        assert request('OpenworldStageBeginReq', area_id=102, avatar_id_list=[101])['retcode'] == 6
        assert request('AcceptOpenworldStoryReq', story_id=411)['retcode'] == 3
        for identity, count in zip(range(401, 412), (1,)*11):
            assert request('AcceptOpenworldStoryReq', story_id=identity)['retcode'] == 0
            assert request('TakeOpenworldStoryRewardReq', story_id=identity)['retcode'] == 1
            assert request('SetOpenworldStoryProgressReq', story_id=identity, story_progress=count+1)['retcode'] == 1
            assert request('SetOpenworldStoryProgressReq', story_id=identity, story_progress=count)['retcode'] == 0
            assert request('TakeOpenworldStoryRewardReq', story_id=identity)['retcode'] == 0
            if identity == 405:
                assert a['openworld_data']['servant_level'] == 1
            if identity == 407:
                assert request('OpenworldStageBeginReq', area_id=102, avatar_id_list=[101])['retcode'] == 0
            before = path.read_bytes()
            assert request('TakeOpenworldStoryRewardReq', story_id=identity)['reward_list'] == []
            assert path.read_bytes() == before
        # Cycle rewards are independent, even if requested out of order.
        assert request('TakeOpenworldCycleFinishRewardReq', cycle=4)['retcode'] == 0
        assert a['openworld_data']['has_take_finish_reward_cycle'] == 0
        a.clear(); a.update(json.loads(path.read_bytes()))
        assert request('TakeOpenworldCycleFinishRewardReq', cycle=4)['reward_list'] == []
        assert request('TakeOpenworldCycleFinishRewardReq', cycle=1)['retcode'] == 0
        assert a['openworld_data']['has_take_finish_reward_cycle'] == 1
        assert request('TakeOpenworldCycleFinishRewardReq', cycle=2)['retcode'] == 0
        assert a['openworld_data']['has_take_finish_reward_cycle'] == 2
        assert request('TakeOpenworldCycleFinishRewardReq', cycle=3)['retcode'] == 0
        assert a['openworld_data']['has_take_finish_reward_cycle'] == 4
        assert request('GetOpenworldReq')['cycle'] == 4  # fifth cycle not enabled
        assert request('AcceptOpenworldStoryReq', story_id=501)['retcode'] == 2
        assert request('OpenworldStageEndReq', end_status=3)['retcode'] == 0
    print('PASS fourth-cycle eligibility, level gate, eleven steps, independent rewards, retries and wire encoding')


if __name__ == '__main__':
    check()
