"""Build two explicitly authored virtual profiles from accepted test equipment.

Reads an account snapshot; writes only the separate reviewable fixture file.
No game or account mutation. Original protocol encodes each profile first.
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
import json
from copy import deepcopy
import server19_protocol as proto


def build(account_path, output):
    account = json.loads(Path(account_path).read_bytes())
    weapons = {row['unique_id']: row for row in account['weapon_list']}
    stigmata = {row['unique_id']: row for row in account['stigmata_list']}
    profiles = []
    for uid, name, avatar_id in ((21001, '宁静致远', 101),
                                 (21002, '舰长当绳匠好玩吗', 201)):
        avatar = next(row for row in account['avatar_list'] if row['avatar_id'] == avatar_id)
        leader = {'avatar_id': avatar_id, 'avatar_star': avatar['star'],
                  'avatar_level': avatar['level'], 'dress_id': avatar.get('dress_id', avatar_id),
                  'skill_list': deepcopy(avatar.get('skill_list', []))}
        for key, source, identity in [('weapon', weapons, avatar['weapon_unique_id'])] + [
                ('stigmata_' + str(i), stigmata, avatar.get('stigmata_unique_id_' + str(i), 0))
                for i in (1, 2, 3)]:
            if not identity:
                continue
            item = source[identity]
            fields = {f['name'] for f in proto.schema('WeaponDetailData' if key == 'weapon'
                                                    else 'StigmataDetailData')['fields']}
            leader[key] = {k: deepcopy(v) for k, v in item.items() if k in fields}
        brief = {'uid': uid, 'nickname': name, 'level': account['main']['level'],
                 'avatar_id': avatar_id, 'avatar_star': avatar['star'],
                 'avatar_level': avatar['level'], 'dress_id': leader['dress_id'],
                 'last_login_time': 0, 'bond': 0, 'main_sub_skill_list': []}
        detail = {'uid': uid, 'nickname': name, 'level': account['main']['level'],
                  'leader_avatar': leader, 'self_desc': '本地虚拟好友 / Local virtual friend'}
        proto.encode_message('PlayerFriendBriefData', brief)
        proto.encode_message('PlayerDetailData', detail)
        profiles.append({'brief': brief, 'detail': detail})
    Path(output).write_text(json.dumps({'schema': 1, 'kind': 'local_virtual_test_profiles',
        'source': 'accepted player equipment snapshot copied into independent fixtures',
        'profiles': profiles}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'profiles': len(profiles), 'account_operation': 'read_only'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    build(args.account, args.output)
