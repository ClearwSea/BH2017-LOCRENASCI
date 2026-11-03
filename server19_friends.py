"""Explicit local virtual friends using the original 1.9 list/detail protocol.

These fixtures are local test identities, never remote users. Queries and
assistant selection do not grant their equipment or EXP to the player.
"""
from copy import deepcopy
from pathlib import Path
import json
import time

PROFILE_FILE = Path(__file__).with_name('server19_virtual_friend_profiles.json')
HANDLED_REQUESTS = frozenset(('GetFriendListReq', 'GetRecommendFriendListReq',
    'GetAskAddFriendListReq', 'GetAssistantFrozenListReq', 'GetPlayerDetailDataReq',
    'GetOtherPlayerCardDataReq'))


def profiles():
    if not PROFILE_FILE.exists():
        return []
    rows = json.loads(PROFILE_FILE.read_bytes())['profiles']
    if len({row['brief']['uid'] for row in rows}) != len(rows):
        raise ValueError('Duplicate local virtual friend UID')
    return rows


def assistant(uid):
    return next((deepcopy(row) for row in profiles() if row['brief']['uid'] == uid), None)


def response(name, account, values=None):
    if name not in HANDLED_REQUESTS:
        return None
    values = values or {}
    rows = profiles()
    # These are explicitly available local virtual identities; stale Unix0
    # must not cause original last-login filters to hide them from assistance.
    for row in rows:
        row['brief']['last_login_time'] = int(time.time())
    if name == 'GetFriendListReq':
        # Preserve saved real list entries and append only explicit fixtures.
        friends = deepcopy(account.get('friend_list', []))
        seen = {row['uid'] for row in friends}
        friends.extend(deepcopy(row['brief']) for row in rows if row['brief']['uid'] not in seen)
        return 'GetFriendListRsp', {'retcode': 0, 'is_whole_data': True,
            'friend_list': friends, 'assistant_num': len(friends)}
    if name == 'GetRecommendFriendListReq':
        excluded = set(values.get('filter_uid_list', []))
        return 'GetRecommendFriendListRsp', {'retcode': 0,
            'recommend_list': [deepcopy(row['brief']) for row in rows if row['brief']['uid'] not in excluded]}
    if name == 'GetAskAddFriendListReq':
        return 'GetAskAddFriendListRsp', {'retcode': 0, 'ask_list': []}
    if name == 'GetAssistantFrozenListReq':
        return 'GetAssistantFrozenListRsp', {'retcode': 0, 'frozen_list': []}
    if name == 'GetOtherPlayerCardDataReq':
        target = values.get('target_uid', 0)
        friend = assistant(target)
        if friend is None:
            # Reference behavior: unknown UID is rejected, never faked.
            return 'GetOtherPlayerCardDataRsp', {'retcode': 1, 'target_uid': target}
        # Native OnOtherPlayerCardDataRsp dereferences card_data/msg_data with
        # no null guard (same pattern as OnGetPlayerCardRsp). Mirror the
        # reference server: card_data carries the UID and a non-null msg_data;
        # the leader avatar travels in player_data, not card_data.avatar_list.
        card = {'uid': friend['brief']['uid'],
                'msg_data': {'msg_index': 0, 'msg_config': 1, 'msg_list': []},
                'island_like_num': 0}
        return 'GetOtherPlayerCardDataRsp', {'retcode': 0,
            'target_uid': friend['brief']['uid'],
            'card_data': card, 'player_data': deepcopy(friend['detail'])}
    friend = assistant(values.get('target_uid'))
    if friend:
        return 'GetPlayerDetailDataRsp', {'retcode': 0, 'detail': friend['detail']}
    # Other identities retain the existing handler, rather than fake a profile.
    return None
