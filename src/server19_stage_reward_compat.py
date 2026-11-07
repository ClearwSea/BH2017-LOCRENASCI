"""Approved 1.9 reward-ratio compatibility; never changes reward totals or saves.

The 2.4 reference has six ratios above one. Original LevelDataItem getters
68413..68416 split total rewards by (1-ratio)/ratio, producing negatives.
Use the adjacent normal 0/0.7 split, explicitly as compatibility, not a
recovered historical 1.9 value. Other activities remain outside this repair.
"""

from copy import deepcopy
import json
import math

RATIO_FIELDS = ('avatarExpInside', 'scoinInside')
STAGE_IDS = (10432, 10433, 10434, 20432, 20433, 20434)


def audit(rows):
    return {
        'row_count': len(rows),
        'ratio_anomaly_ids': [r['levelId'] for r in rows if any(
            not math.isfinite(r[k]) or not 0 <= r[k] <= 1 for k in RATIO_FIELDS)],
        'reward_limit_mismatch_ids': [r['levelId'] for r in rows if any(
            r[total] < 0 or r[maximum] < r[total] for total, maximum in
            (('avatarExpReward', 'maxAvatarExpReward'), ('scoinReward', 'maxScoinReward')))],
    }


def repair(rows):
    result = deepcopy(rows)
    changes = []
    seen = set()
    for r in result:
        identity = r['levelId']
        if identity not in STAGE_IDS:
            continue
        if identity in seen:
            raise ValueError('Duplicate compatibility stage')
        seen.add(identity)
        before = [r[k] for k in RATIO_FIELDS]
        if before == [0.0, 0.7]:
            continue
        ordinal = identity % 100 - 31
        expected = [float(ordinal), ordinal + 0.7]
        if r['chapterId'] != 4 or r['type'] != 1 or r['difficulty'] != identity // 10000 or any(
                not math.isclose(a, b, abs_tol=1e-6) for a, b in zip(before, expected)):
            raise ValueError('Unreviewed compatibility preimage: ' + str(identity))
        r.update(avatarExpInside=0.0, scoinInside=0.7)
        changes.append({'stage_id': identity, 'before': before, 'after': [0.0, 0.7]})
    return result, changes


def patch_payload(payload):
    """Replace only changed row spans; retain all other bytes, including whitespace."""
    text = payload.decode('utf-8')
    rows = json.loads(text)
    fixed, changes = repair(rows)
    decoder = json.JSONDecoder()
    cursor = text.index('[') + 1
    replacements = []
    for old, new in zip(rows, fixed):
        while text[cursor].isspace() or text[cursor] == ',':
            cursor += 1
        value, end = decoder.raw_decode(text, cursor)
        assert value == old
        if old != new:
            replacements.append((cursor, end, json.dumps(new, ensure_ascii=False,
                separators=(',', ':'), allow_nan=False)))
        cursor = end
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    encoded = text.encode('utf-8')
    assert json.loads(encoded) == fixed
    return encoded, changes
