"""Offline ExBoss score population, using the existing Endless identities.

Scores are simulation data only. Player results come from the ExBoss battle
protocol. The population is deterministic for a period and never writes the
player account or interferes with native UI and battle objects.
"""
import random
import math

import server19_endless as endless

_POPULATION = 10000  # Includes the local player and 9999 simulated captains.
_UID_BASE = 900000000
_MAX_U32 = (1 << 32) - 1
_LEADERS = {
    101: ('第二名我求你了', '我就差一分啊！', '差两分睡不着'),
    102: ('停手吧你没机会的', '差一分你给我等着', '第二名也给我等着'),
    103: endless.INFINITE_LEADERS,
}
_UID_OFFSETS = {101: 19, 102: 38, 103: 0}


def leaderboard(account, begin, end, now, score, achieved_time, rank_id, names, score_ceiling):
    """Return original 1.9 rank response fields from one deterministic field.

    The highest group's first three use Endless's infinite-group identities;
    the lower groups have their own requested leaders and disjoint UIDs.
    Other displayed names come from the same Endless name pool;
    anonymous population members contribute to the percentage and are never
    returned as fake profile records. Period score bands are diagnostic values
    and should be calibrated against actual ExBoss client results.
    """
    unique_names = list(dict.fromkeys(names))
    if not (0 < score_ceiling <= _MAX_U32 and 0 <= score <= score_ceiling
            and begin < end and len(unique_names) >= 48 and rank_id in _LEADERS):
        raise ValueError('Invalid score, period or Endless name pool')
    rng = random.Random(endless.seed(account['uid'], begin, 'exboss', 'names'))
    sampled = rng.sample(unique_names, 48)
    offset = (rank_id - 101) * 16
    visible_names = list(_LEADERS[rank_id]) + sampled[offset:offset + 16]
    uid_base = _UID_BASE + _UID_OFFSETS[rank_id]
    fraction = min(1.0, max(0.0, (now - begin) / (end - begin)))
    rng = random.Random(endless.seed(account['uid'], begin, rank_id, 'exboss'))

    # Visible NPCs are the leading part of the same population, not a second
    # independent leaderboard. Lower population goals and slower pace ensure
    # that omitted anonymous NPCs cannot outrank the visible sixteen.
    def progress(goal, pace):
        value = int(goal * min(1.0, fraction / pace))
        reached = begin + math.ceil(value * pace * (end - begin) / goal)
        return value, reached

    visible = []
    for index in range(3, 19):
        goal = rng.randint(max(1, score_ceiling * 73 // 100), max(1, score_ceiling * 99 // 100))
        pace = rng.uniform(.35, .50)
        value, reached = progress(goal, pace)
        visible.append((value, uid_base + index, visible_names[index], reached))
    anonymous = []
    for index in range(_POPULATION - 20):
        goal = rng.randint(max(1, score_ceiling // 48), max(1, score_ceiling * 70 // 100))
        pace = rng.uniform(.50, 1.0)
        anonymous.append(progress(goal, pace))

    # Fixed leaders retain an earlier tie-break if the user reaches the exact
    # theoretical ceiling; simulated scores never exceed that ceiling.
    leader_base = max(score, score_ceiling * 98 // 100, *(row[0] for row in visible))
    leaders = [(min(score_ceiling, leader_base + 3 - i), uid_base + i, visible_names[i], begin) for i in range(3)]
    def before(value, reached):
        return value > score or (value == score and reached <= achieved_time)
    ahead = 3 + sum(before(value, reached) for value, _, _, reached in visible)
    ahead += sum(before(value, reached) for value, reached in anonymous)
    player_rank = min(10000, ahead + 1) if score else 0

    rows = []
    for value, uid, nickname, reached in sorted(leaders + visible, key=lambda x: (-x[0], x[3], x[1])):
        position = 1 + sum(other[0] > value or (other[0] == value and (other[3], other[1]) < (reached, uid))
                           for other in leaders + visible)
        if score and (score > value or (score == value and achieved_time < reached)):
            position += 1
        rows.append({'uid': uid, 'score': value, 'rank': position, 'nickname': nickname,
                     'armada_id': 0, 'armada_name': ''})
    mine = {'uid': account['uid'], 'score': score, 'rank': player_rank,
            'nickname': account['main'].get('nickname', ''), 'armada_id': 0,
            'armada_name': ''}
    return {'retcode': 0, 'rank_id': rank_id, 'my_rank': mine,
            'rank_list': rows, 'is_filtered': False}
