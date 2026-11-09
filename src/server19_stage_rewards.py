"""Original Req556/558 chapter-star rewards with persisted atomic receipts.

Only reviewed Normal Acts in chapters1–6 and resource-ready account
stages contribute. Configurations/rewards are deployed filtered 2.4 rows;
historical 1.9 economy has not been recovered. This module never invents
clears, stars, first drops, repeated random drops or tutorial completion.
"""
from copy import deepcopy
import json
from pathlib import Path
import time

import server19_initialization as initialization
import server19_missions as missions
import server19_protocol as proto
import server19_stage as stage

HANDLED_REQUESTS = frozenset(("GetStageActDifficultyReq", "TakeStageActChallengeRewardReq"))
SOURCE_POLICY = "deployed24_scoped_act_star_rewards"
SUPPORTED_KEYS = tuple((act_id, 1) for act_id in range(101, 108))
_CURRENCIES = {"exp": "RewardExp", "scoin": "RewardSCoin", "hcoin": "RewardHCoin",
               "stamina": "RewardStamina", "skill_point": "RewardSkillPoint",
               "friends_point": "RewardFriendPoint", "duty_point": "RewardDutyPoint"}
_EXPECTED = {
    (101, 1): ((7, 990011, 2000, 0, [(3000, 0, 5)]),
               (11, 990012, 3000, 0, [(3000, 0, 9), (1001, 0, 15)]),
               (15, 990013, 4000, 30, [(3000, 0, 14)])),
    (102, 1): ((7, 990041, 2000, 0, [(3000, 0, 5)]),
               (11, 990042, 3000, 0, [(3000, 0, 10), (1001, 0, 15)]),
               (15, 990043, 4000, 30, [(3000, 0, 15)])),
    (103, 1): ((7, 990071, 2000, 0, [(3000, 0, 5)]),
               (11, 990072, 3000, 0, [(3000, 0, 10), (1001, 0, 15)]),
               (15, 990073, 5000, 30, [(3000, 0, 15)])),
    (104, 1): ((7, 990101, 2000, 0, [(3000, 0, 5)]),
               (11, 990102, 4000, 0, [(3000, 0, 11), (1001, 0, 15)]),
               (15, 990103, 5000, 30, [(3000, 0, 16)])),
    (105, 1): ((7, 990131, 2000, 0, [(3000, 0, 6)]),
               (11, 990132, 4000, 0, [(3000, 0, 11), (1001, 0, 20)]),
               (15, 990133, 5000, 30, [(3000, 0, 17)])),
    (106, 1): ((9, 990161, 3000, 0, [(3000, 0, 6)]),
               (13, 990162, 4000, 0, [(3000, 0, 12), (1001, 0, 20)]),
               (18, 990163, 5000, 30, [(3000, 0, 18)])),
    (107, 1): ((7, 990191, 3000, 0, [(3000, 0, 6)]),
               (11, 990192, 4000, 0, [(3000, 0, 13), (1001, 0, 20)]),
               (15, 990193, 6000, 30, [(3000, 0, 19)])),
}

# Reviewed source thresholds and reward quantities; never derive payouts from
# an unchecked client request. Actual stars still require persisted WINs.
_STORY_ACT_SOURCE = Path(__file__).with_name('server19_story_act_rewards.json')
_STORY_ACT_DATA = json.loads(_STORY_ACT_SOURCE.read_bytes())
# Generated JSON may change whitespace and key order without changing rewards.
from server19_build_capabilities import canonical_sha
if canonical_sha(_STORY_ACT_DATA) != '42df457893bfbce751a50d36475d8da2ae0b8b82a0639e937c6b825ec80a320d':
    raise ValueError('Reviewed story Act reward source changed')
for _act, _tiers in _STORY_ACT_DATA.items():
    _EXPECTED[int(_act), 1] = tuple((n, rid, coin, crystal, [tuple(x) for x in items])
                                  for n, rid, coin, crystal, items in _tiers)
# Reviewed difficulty tiers, same original atomic reward transaction.
_EXPECTED.update({(101, 2): ((7, 990021, 3000, 0, [(3001, 0, 1)]),
            (11, 990022, 4000, 0, [(3001, 0, 3), (10102, 0, 1)]),
            (15, 990023, 6000, 50, [(3002, 0, 1)])),
 (101, 3): ((7, 990031, 4000, 0, [(3006, 0, 1)]),
            (11, 990032, 6000, 0, [(3006, 0, 2), (7032, 0, 3)]),
            (15, 990033, 9000, 0, [(3007, 0, 1), (7032, 0, 5)])),
 (102, 2): ((7, 990051, 3000, 0, [(3005, 0, 1)]),
            (11, 990052, 5000, 0, [(3005, 0, 3), (10102, 0, 1)]),
            (15, 990053, 6000, 50, [(3006, 0, 1)])),
 (102, 3): ((7, 990061, 4000, 0, [(3002, 0, 1)]),
            (11, 990062, 7000, 0, [(3002, 0, 2), (7032, 0, 3)]),
            (15, 990063, 9000, 0, [(3003, 0, 1), (7032, 0, 5)])),
 (103, 2): ((7, 990081, 3000, 0, [(3001, 0, 2)]),
            (11, 990082, 5000, 0, [(3001, 0, 3), (10102, 0, 1)]),
            (15, 990083, 6000, 50, [(3002, 0, 2)])),
 (103, 3): ((7, 990091, 5000, 0, [(3006, 0, 1)]),
            (11, 990092, 7000, 0, [(3006, 0, 2), (7032, 0, 3)]),
            (15, 990093, 9000, 0, [(3007, 0, 1), (7032, 0, 5)])),
 (104, 2): ((7, 990111, 3000, 0, [(3005, 0, 2)]),
            (11, 990112, 5000, 0, [(3005, 0, 3), (10102, 0, 1)]),
            (15, 990113, 7000, 50, [(3006, 0, 2)])),
 (104, 3): ((7, 990121, 5000, 0, [(3002, 0, 1)]),
            (11, 990122, 7000, 0, [(3002, 0, 2), (7032, 0, 3)]),
            (15, 990123, 10000, 0, [(3003, 0, 1), (7032, 0, 5)])),
 (105, 2): ((7, 990141, 3000, 0, [(3001, 0, 2)]),
            (11, 990142, 5000, 0, [(3001, 0, 3), (10102, 0, 1)]),
            (15, 990143, 7000, 50, [(3002, 0, 2)])),
 (105, 3): ((7, 990151, 5000, 0, [(3006, 0, 1)]),
            (11, 990152, 8000, 0, [(3006, 0, 2), (7032, 0, 3)]),
            (15, 990153, 10000, 0, [(3007, 0, 1), (7032, 0, 5)])),
 (106, 2): ((9, 990171, 4000, 0, [(3005, 0, 2)]),
            (13, 990172, 6000, 0, [(3005, 0, 3), (10102, 0, 1)]),
            (18, 990173, 8000, 50, [(3006, 0, 2)])),
 (106, 3): ((9, 990181, 5000, 0, [(3002, 0, 1)]),
            (13, 990182, 8000, 0, [(3002, 0, 2), (7032, 0, 3)]),
            (18, 990183, 11000, 0, [(3003, 0, 1), (7032, 0, 5)])),
 (107, 2): ((7, 990201, 4000, 0, [(3001, 0, 2)]),
            (11, 990202, 6000, 0, [(3001, 0, 4), (10102, 0, 1)]),
            (15, 990203, 8000, 50, [(3002, 0, 2)])),
 (107, 3): ((7, 990211, 6000, 0, [(3006, 0, 1)]),
            (11, 990212, 9000, 0, [(3006, 0, 2), (7032, 0, 3)]),
            (15, 990213, 11000, 0, [(3007, 0, 1), (7032, 0, 5)])),
 (201, 2): ((7, 990231, 4000, 0, [(3005, 0, 2)]),
            (11, 990232, 6000, 0, [(3005, 0, 4), (10202, 0, 1)]),
            (15, 990233, 8000, 50, [(3006, 0, 2)])),
 (201, 3): ((7, 990241, 6000, 0, [(3002, 0, 1)]),
            (11, 990242, 9000, 0, [(3002, 0, 2), (7032, 0, 3)]),
            (15, 990243, 11000, 0, [(3003, 0, 1), (7032, 0, 5)])),
 (202, 2): ((7, 990261, 4000, 0, [(3001, 0, 2)]),
            (11, 990262, 6000, 0, [(3001, 0, 4), (10202, 0, 1)]),
            (15, 990263, 8000, 50, [(3002, 0, 2)])),
 (202, 3): ((7, 990271, 6000, 0, [(3006, 0, 1)]),
            (11, 990272, 9000, 0, [(3006, 0, 2), (7032, 0, 3)]),
            (15, 990273, 12000, 0, [(3007, 0, 1), (7032, 0, 5)])),
 (203, 2): ((7, 990291, 4000, 0, [(3005, 0, 2)]),
            (11, 990292, 6000, 0, [(3005, 0, 4), (10202, 0, 1)]),
            (15, 990293, 9000, 50, [(3006, 0, 2)])),
 (203, 3): ((7, 990301, 6000, 0, [(3002, 0, 1)]),
            (11, 990302, 9000, 0, [(3002, 0, 2), (7032, 0, 3)]),
            (15, 990303, 12000, 0, [(3003, 0, 1), (7032, 0, 5)])),
 (204, 2): ((7, 990321, 4000, 0, [(3001, 0, 2)]),
            (11, 990322, 7000, 0, [(3001, 0, 4), (10202, 0, 1)]),
            (15, 990323, 9000, 50, [(3002, 0, 2)])),
 (204, 3): ((7, 990331, 6000, 0, [(3006, 0, 1)]),
            (11, 990332, 10000, 0, [(3006, 0, 2), (7032, 0, 3)]),
            (15, 990333, 13000, 0, [(3007, 0, 2), (7032, 0, 5)])),
 (205, 2): ((9, 990351, 5000, 0, [(3005, 0, 2)]),
            (13, 990352, 7000, 0, [(3005, 0, 4), (10202, 0, 1)]),
            (18, 990353, 9000, 50, [(3006, 0, 2)])),
 (205, 3): ((9, 990361, 7000, 0, [(3002, 0, 1)]),
            (13, 990362, 10000, 0, [(3002, 0, 2), (7032, 0, 3)]),
            (18, 990363, 14000, 0, [(3003, 0, 2), (7032, 0, 5)])),
 (206, 2): ((9, 990381, 5000, 0, [(3001, 0, 2)]),
            (13, 990382, 8000, 0, [(3001, 0, 5), (10202, 0, 1)]),
            (18, 990383, 10000, 50, [(3002, 0, 2)])),
 (206, 3): ((9, 990391, 7000, 0, [(3006, 0, 1)]),
            (13, 990392, 11000, 0, [(3006, 0, 3), (7032, 0, 3)]),
            (18, 990393, 15000, 0, [(3007, 0, 2), (7032, 0, 5)])),
 (207, 2): ((7, 990411, 5000, 0, [(3005, 0, 3)]),
            (11, 990412, 8000, 0, [(3005, 0, 5), (10202, 0, 1)]),
            (15, 990413, 11000, 50, [(3006, 0, 3)])),
 (207, 3): ((7, 990421, 8000, 0, [(3002, 0, 1)]),
            (11, 990422, 11000, 0, [(3002, 0, 3), (9003, 0, 1)]),
            (15, 990423, 15000, 0, [(3003, 0, 2), (9003, 0, 2)])),
 (301, 2): ((7, 990441, 5000, 0, [(3001, 0, 3)]),
            (11, 990442, 8000, 0, [(3001, 0, 5), (10302, 0, 1)]),
            (15, 990443, 11000, 50, [(3002, 0, 3)])),
 (301, 3): ((7, 990451, 8000, 0, [(3007, 0, 1)]),
            (11, 990452, 11000, 0, [(3007, 0, 1), (9003, 0, 1)]),
            (15, 990453, 15000, 0, [(3007, 0, 2), (9003, 0, 2)])),
 (302, 2): ((7, 990471, 5000, 0, [(3005, 0, 3)]),
            (11, 990472, 8000, 0, [(3005, 0, 5), (10302, 0, 1)]),
            (15, 990473, 11000, 50, [(3006, 0, 3)])),
 (302, 3): ((7, 990481, 8000, 0, [(3003, 0, 1)]),
            (11, 990482, 12000, 0, [(3003, 0, 1), (9004, 0, 1)]),
            (15, 990483, 16000, 0, [(3003, 0, 2), (9004, 0, 2)])),
 (303, 2): ((7, 990501, 6000, 0, [(3001, 0, 3)]),
            (11, 990502, 9000, 0, [(3001, 0, 5), (10302, 0, 1)]),
            (15, 990503, 11000, 50, [(3002, 0, 3)])),
 (303, 3): ((7, 990511, 8000, 0, [(3007, 0, 1)]),
            (11, 990512, 12000, 0, [(3007, 0, 1), (9003, 0, 1)]),
            (15, 990513, 16000, 0, [(3008, 0, 1), (9003, 0, 2)])),
 (304, 2): ((9, 990531, 6000, 0, [(3005, 0, 3)]),
            (13, 990532, 9000, 0, [(3005, 0, 5), (10302, 0, 1)]),
            (18, 990533, 12000, 50, [(3006, 0, 3)])),
 (304, 3): ((9, 990541, 9000, 0, [(3003, 0, 1)]),
            (13, 990542, 13000, 0, [(3003, 0, 2), (9004, 0, 1)]),
            (18, 990543, 17000, 0, [(3004, 0, 1), (9004, 0, 2)])),
 (305, 2): ((9, 990561, 6000, 0, [(3001, 0, 3)]),
            (13, 990562, 10000, 0, [(3001, 0, 6), (10302, 0, 1)]),
            (18, 990563, 13000, 50, [(3002, 0, 3)])),
 (305, 3): ((9, 990571, 9000, 0, [(3007, 0, 1)]),
            (13, 990572, 14000, 0, [(3007, 0, 2), (9003, 0, 1)]),
            (18, 990573, 18000, 0, [(3008, 0, 1), (9003, 0, 2)])),
 (306, 2): ((9, 990591, 7000, 0, [(3005, 0, 3)]),
            (13, 990592, 10000, 0, [(3005, 0, 6), (10302, 0, 1)]),
            (18, 990593, 14000, 50, [(3006, 0, 3)])),
 (306, 3): ((9, 990601, 9000, 0, [(3003, 0, 1)]),
            (13, 990602, 14000, 0, [(3003, 0, 2), (9004, 0, 1)]),
            (18, 990603, 19000, 0, [(3004, 0, 1), (9004, 0, 2)])),
 (307, 2): ((7, 990621, 7000, 0, [(3001, 0, 3)]),
            (11, 990622, 11000, 0, [(3001, 0, 6), (10302, 0, 1)]),
            (15, 990623, 14000, 50, [(3002, 0, 3)])),
 (307, 3): ((7, 990631, 10000, 0, [(3007, 0, 1)]),
            (11, 990632, 15000, 0, [(3007, 0, 2), (9003, 0, 1)]),
            (15, 990633, 20000, 0, [(3008, 0, 1), (9003, 0, 2)])),
 (401, 2): ((7, 990651, 7000, 0, [(3006, 0, 1)]),
            (11, 990652, 11000, 0, [(3006, 0, 3), (10203, 0, 1)]),
            (15, 990653, 14000, 50, [(3007, 0, 2)])),
 (401, 3): ((7, 990661, 10000, 0, [(3003, 0, 1)]),
            (11, 990662, 14000, 0, [(3003, 0, 2), (9003, 0, 1)]),
            (15, 990663, 19000, 0, [(3004, 0, 1), (9003, 0, 2)])),
 (402, 2): ((7, 990681, 7000, 0, [(3002, 0, 1)]),
            (11, 990682, 11000, 0, [(3002, 0, 3), (10203, 0, 1)]),
            (15, 990683, 15000, 50, [(3003, 0, 2)])),
 (402, 3): ((7, 990691, 10000, 0, [(3007, 0, 1)]),
            (11, 990692, 15000, 0, [(3007, 0, 2), (9004, 0, 1)]),
            (15, 990693, 20000, 0, [(3008, 0, 1), (9004, 0, 2)])),
 (403, 2): ((9, 990711, 8000, 0, [(3006, 0, 1)]),
            (13, 990712, 11000, 0, [(3006, 0, 3), (10203, 0, 1)]),
            (18, 990713, 15000, 50, [(3007, 0, 2)])),
 (403, 3): ((9, 990721, 10000, 0, [(3003, 0, 1)]),
            (13, 990722, 16000, 0, [(3003, 0, 2), (9003, 0, 1)]),
            (18, 990723, 21000, 0, [(3004, 0, 1), (9003, 0, 2)])),
 (404, 2): ((9, 990741, 8000, 0, [(3002, 0, 2)]),
            (13, 990742, 12000, 0, [(3002, 0, 3), (10203, 0, 1)]),
            (18, 990743, 16000, 50, [(3003, 0, 2)])),
 (404, 3): ((9, 990751, 11000, 0, [(3007, 0, 1)]),
            (13, 990752, 16000, 0, [(3007, 0, 2), (9004, 0, 1)]),
            (18, 990753, 22000, 0, [(3008, 0, 1), (9004, 0, 2)])),
 (405, 2): ((9, 990771, 9000, 0, [(3006, 0, 2)]),
            (13, 990772, 13000, 0, [(3006, 0, 3), (10203, 0, 1)]),
            (18, 990773, 17000, 50, [(3007, 0, 2)])),
 (405, 3): ((9, 990781, 11000, 0, [(3003, 0, 1)]),
            (13, 990782, 17000, 0, [(3003, 0, 2), (9003, 0, 1)]),
            (18, 990783, 22000, 0, [(3004, 0, 1), (9003, 0, 2)])),
 (406, 2): ((9, 990801, 9000, 0, [(3002, 0, 2)]),
            (13, 990802, 13000, 0, [(3002, 0, 3), (10203, 0, 1)]),
            (18, 990803, 18000, 50, [(3003, 0, 2)])),
 (406, 3): ((9, 990811, 12000, 0, [(3007, 0, 1)]),
            (13, 990812, 17000, 0, [(3007, 0, 2), (9004, 0, 1)]),
            (18, 990813, 23000, 0, [(3008, 0, 1), (9004, 0, 2)])),
 (407, 2): ((7, 990831, 9000, 0, [(3006, 0, 2)]),
            (11, 990832, 14000, 0, [(3006, 0, 3), (10203, 0, 1)]),
            (15, 990833, 18000, 50, [(3007, 0, 2)])),
 (407, 3): ((7, 990841, 12000, 0, [(3003, 0, 1)]),
            (11, 990842, 18000, 0, [(3003, 0, 2), (9003, 0, 1)]),
            (15, 990843, 24000, 0, [(3004, 0, 1), (9003, 0, 2)])),
 (501, 2): ((2, 990861, 5000, 0, [(3002, 0, 2)]),
            (4, 990862, 7000, 0, [(3002, 0, 3), (9003, 0, 1)]),
            (6, 990863, 10000, 0, [(3003, 0, 2), (9003, 0, 2)])),
 (501, 3): ((2, 990871, 7000, 0, [(3007, 0, 1)]),
            (4, 990872, 11000, 0, [(3007, 0, 2), (10503, 0, 1)]),
            (6, 990873, 14000, 0, [(3008, 0, 1), (10503, 0, 1)])),
 (502, 2): ((2, 990891, 5000, 0, [(3006, 0, 2)]),
            (4, 990892, 8000, 0, [(3006, 0, 3), (9004, 0, 1)]),
            (6, 990893, 10000, 0, [(3007, 0, 2), (9004, 0, 2)])),
 (502, 3): ((2, 990901, 7000, 0, [(3003, 0, 1)]),
            (4, 990902, 11000, 0, [(3003, 0, 2), (10503, 0, 1)]),
            (6, 990903, 15000, 0, [(3004, 0, 1), (10503, 0, 1)])),
 (503, 2): ((2, 990921, 5000, 0, [(3002, 0, 2)]),
            (4, 990922, 8000, 0, [(3002, 0, 3), (9004, 0, 1)]),
            (6, 990923, 11000, 0, [(3003, 0, 2), (9004, 0, 2)])),
 (503, 3): ((2, 990931, 8000, 0, [(3007, 0, 1)]),
            (4, 990932, 11000, 0, [(3007, 0, 2), (10503, 0, 1)]),
            (6, 990933, 15000, 0, [(3008, 0, 1), (10503, 0, 1)])),
 (504, 2): ((2, 990951, 6000, 0, [(3006, 0, 2)]),
            (4, 990952, 8000, 0, [(3006, 0, 3), (9004, 0, 1)]),
            (6, 990953, 11000, 0, [(3007, 0, 2), (9004, 0, 2)])),
 (504, 3): ((2, 990961, 8000, 0, [(3003, 0, 1)]),
            (4, 990962, 11000, 0, [(3003, 0, 2), (10503, 0, 1)]),
            (6, 990963, 16000, 0, [(3004, 0, 2), (10503, 0, 1)])),
 (601, 2): ((2, 990981, 5000, 0, [(3002, 0, 2)]),
            (4, 990982, 8000, 0, [(3002, 0, 3), (9003, 0, 1)]),
            (6, 990983, 10000, 0, [(3003, 0, 2), (9003, 0, 2)])),
 (601, 3): ((2, 990991, 7000, 0, [(3007, 0, 1)]),
            (4, 990992, 11000, 0, [(3007, 0, 2), (10112, 0, 1)]),
            (6, 990993, 14000, 0, [(3008, 0, 1), (10112, 0, 2)])),
 (602, 2): ((2, 991011, 5000, 0, [(3006, 0, 2)]),
            (4, 991012, 8000, 0, [(3006, 0, 3), (9003, 0, 1)]),
            (6, 991013, 10000, 0, [(3007, 0, 2), (9003, 0, 2)])),
 (602, 3): ((2, 991021, 7000, 0, [(3003, 0, 1)]),
            (4, 991022, 11000, 0, [(3003, 0, 2), (10112, 0, 1)]),
            (6, 991023, 14000, 0, [(3004, 0, 1), (10112, 0, 2)])),
 (603, 2): ((2, 991041, 5000, 0, [(3002, 0, 2)]),
            (4, 991042, 8000, 0, [(3002, 0, 3), (9004, 0, 1)]),
            (6, 991043, 11000, 0, [(3003, 0, 2), (9004, 0, 2)])),
 (603, 3): ((2, 991051, 7000, 0, [(3007, 0, 1)]),
            (4, 991052, 11000, 0, [(3007, 0, 2), (10112, 0, 1)]),
            (6, 991053, 14000, 0, [(3008, 0, 1), (10112, 0, 2)])),
 (604, 2): ((2, 991071, 5000, 0, [(3006, 0, 2)]),
            (4, 991072, 8000, 0, [(3006, 0, 3), (9004, 0, 1)]),
            (6, 991073, 11000, 0, [(3007, 0, 2), (9004, 0, 2)])),
 (604, 3): ((2, 991081, 7000, 0, [(3003, 0, 1)]),
            (4, 991082, 11000, 0, [(3003, 0, 2), (10112, 0, 1)]),
            (6, 991083, 14000, 0, [(3004, 0, 1), (10112, 0, 2)]))})
SUPPORTED_KEYS = tuple(_EXPECTED)


def catalog():
    """Audit thresholds and reward quantities for each supported difficulty."""
    acts = stage._table("actchallengedata", field="actId", identities=[key[0] for key in _EXPECTED])
    rewards = stage._table("rewarddata", field="RewardID", identities=[
        row[1] for expected in _EXPECTED.values() for row in expected])
    result = {}
    for key, expected in _EXPECTED.items():
        matches = [row for row in acts if (row.get("actId"), row.get("difficulty")) == key]
        if len(matches) != 1 or matches[0].get("isShow") != 1:
            raise ValueError("Missing or changed Act challenge configuration")
        config = matches[0]
        for index, (threshold, reward_id, scoin, hcoin, items) in enumerate(expected, 1):
            if (config.get(f"challengeNum{index}"), config.get(f"RewardID{index}")) != (threshold, reward_id):
                raise ValueError("Act star threshold or reward ID changed")
            selected = [row for row in rewards if row.get("RewardID") == reward_id]
            if len(selected) != 1:
                raise ValueError("Missing or ambiguous Act reward row")
            row = selected[0]
            reward = {name: stage._u32(row[field], field) for name, field in _CURRENCIES.items()}
            actual_items = []
            for slot in range(1, 6):
                item = tuple(stage._u32(row[f"RewardItem{slot}{field}"], "reward item")
                             for field in ("ID", "Level", "Num"))
                if item[0] and item[2]:
                    actual_items.append(item)
                elif item != (0, 0, 0):
                    raise ValueError("Malformed Act reward item slot")
            if reward != {"exp": 0, "scoin": scoin, "hcoin": hcoin, "stamina": 0,
                          "skill_point": 0, "friends_point": 0, "duty_point": 0} or actual_items != items:
                raise ValueError("Act star reward changed; audit before granting")
            for item_id, level, count in actual_items:
                if stage._item_metadata(item_id)[0] not in ("material", "avatar_fragment") or level != 0:
                    raise ValueError("Act item storage type requires another audit")
            reward["item_list"] = [dict(zip(("id", "level", "num"), item)) for item in actual_items]
            result[key + (index,)] = {"threshold": threshold, "reward_id": reward_id, "reward": reward}
    return result


def star_count(account, act_id, difficulty):
    """Count unique valid saved challenges only on successfully settled WINs."""
    wins = missions._confirmed_wins(account)
    supported = frozenset(stage.supported_stage_ids())
    total = 0
    for saved in account.get("stage_list", []):
        identity = saved.get("id")
        if identity not in supported:
            continue
        config = stage.stage_config(identity)
        if (config["actId"], config["difficulty"]) != (act_id, difficulty):
            continue
        indices = saved.get("challenge_index_list", [])
        if not isinstance(indices, list) or any(type(index) is not int or
                not 0 <= index < len(config["challengeList"]) for index in indices) or len(indices) != len(set(indices)):
            raise ValueError("Invalid saved star indices")
        if identity in wins:
            total += len(indices)
    return total


def _groups(account):
    rows = account.get("stage_act_difficulty_list", [])
    if not isinstance(rows, list):
        raise ValueError("Malformed saved Act difficulty state")
    groups = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"act_id", "difficulty", "has_take_challenge_num_index"}:
            raise ValueError("Malformed saved Act difficulty row")
        key = (stage._u32(row["act_id"], "act_id"), stage._u32(row["difficulty"], "difficulty"))
        indices = row["has_take_challenge_num_index"]
        if not all(key) or key in groups or not isinstance(indices, list) or \
                any(type(index) is not int or index not in (1, 2, 3) for index in indices) or len(indices) != len(set(indices)):
            raise ValueError("Duplicate or invalid saved Act reward identity")
        groups[key] = deepcopy(row)
    return groups


def _runtime(account, audited, groups):
    runtime = account.get("act_reward_runtime", {"schema": 1, "source_policy": SOURCE_POLICY, "receipts": []})
    if not isinstance(runtime, dict) or runtime.get("schema") != 1 or runtime.get("source_policy") != SOURCE_POLICY:
        raise ValueError("Unsupported Act reward receipt schema")
    receipts = runtime.get("receipts")
    if not isinstance(receipts, list):
        raise ValueError("Malformed Act reward receipt list")
    keys = set()
    for row in receipts:
        if not isinstance(row, dict):
            raise ValueError("Malformed Act reward receipt")
        key = (row.get("act_id"), row.get("difficulty"), row.get("challenge_num_index"))
        if any(type(value) is not int for value in key) or key not in audited or key in keys:
            raise ValueError("Duplicate or invalid Act reward receipt identity")
        expected = {"retcode": 0, "act_id": key[0], "difficulty": key[1],
                    "challenge_num_index": key[2], "reward_list": [audited[key]["reward"]]}
        if row.get("response") != expected or key[2] not in groups.get(key[:2], {}).get("has_take_challenge_num_index", []):
            raise ValueError("Act claim marker and receipt disagree")
        keys.add(key)
    return deepcopy(runtime)


def difficulty_snapshot(account):
    audited = catalog()
    groups = _groups(account)
    _runtime(account, audited, groups)
    # Include unclaimed supported Acts explicitly. Preserve saved other groups
    # without granting their rewards or deriving unavailable difficulty stars.
    for act_id, difficulty in SUPPORTED_KEYS:
        groups.setdefault((act_id, difficulty), {"act_id": act_id, "difficulty": difficulty,
                                                "has_take_challenge_num_index": []})
    return "GetStageActDifficultyRsp", {"retcode": 0, "act_difficulty_list": list(groups.values())}


def _claim(account, values):
    key = tuple(stage._u32(values.get(field, 0), field)
                for field in ("act_id", "difficulty", "challenge_num_index"))
    audited = catalog()
    if key not in audited:
        return {"retcode": 1}  # Original FAIL=1; no fabricated other Act/difficulty.
    groups = _groups(account)
    runtime = _runtime(account, audited, groups)
    for receipt in runtime["receipts"]:
        if tuple(receipt[field] for field in ("act_id", "difficulty", "challenge_num_index")) == key:
            return deepcopy(receipt["response"])
    if key[2] in groups.get(key[:2], {}).get("has_take_challenge_num_index", []):
        # Imported prior claims have no authored response receipt to replay.
        return {"retcode": 2}  # Original HAS_TAKE=2.
    if star_count(account, *key[:2]) < audited[key]["threshold"]:
        return {"retcode": 3}  # Original CHALLENGE_NUM_LACK=3.
    reward = audited[key]["reward"]
    # Apply all inventory/currency changes to the caller's transaction copy;
    # any capacity/metadata error aborts without a saved marker or partial loot.
    stage._grant_drops(account, {(item["id"], item["level"]): item["num"] for item in reward["item_list"]})
    for currency in ("scoin", "hcoin"):
        account["main"][currency] = stage._u32(account["main"].get(currency, 0) + reward[currency], currency)
    group = groups.setdefault(key[:2], {"act_id": key[0], "difficulty": key[1], "has_take_challenge_num_index": []})
    group["has_take_challenge_num_index"] = sorted(group["has_take_challenge_num_index"] + [key[2]])
    account["stage_act_difficulty_list"] = list(groups.values())
    result = {"retcode": 0, "act_id": key[0], "difficulty": key[1],
              "challenge_num_index": key[2], "reward_list": [deepcopy(reward)]}
    runtime["receipts"].append({"act_id": key[0], "difficulty": key[1], "challenge_num_index": key[2],
                                "response": deepcopy(result), "claimed_at": time.time()})
    account["act_reward_runtime"] = runtime
    return result


def response(request_name, account, request_values=None, *, account_path=None):
    if request_name not in HANDLED_REQUESTS:
        return None
    path = Path(account_path or stage.DEFAULT_ACCOUNT).resolve()
    with stage._transaction_lock(path):
        before = stage._read(path, account)
        current = deepcopy(before)
        try:
            result = difficulty_snapshot(current) if request_name == "GetStageActDifficultyReq" else (
                "TakeStageActChallengeRewardRsp", _claim(current, request_values or {}))
            proto.encode_message(*result)
            if request_name == "TakeStageActChallengeRewardReq" and result[1].get("retcode") == 0:
                for packet in notification_snapshot(current):
                    proto.encode_message(*packet)
            if result[1].get("retcode") == 0:
                stage._save(path, before, current)
                stage._sync(account, current)
            else:
                stage._sync(account, before)
        except (ValueError, TypeError, KeyError, OSError):
            result = request_name[:-3] + "Rsp", {"retcode": 1}
            stage._sync(account, before)
        return result


def notification_snapshot(account):
    """Snapshots: send the final claim-state packet before Rsp559 redraws UI.

    Main/inventory follow the reward response; this ordering applies to all
    supported Acts and tiers, including idempotent receipt replay.
    """
    return [initialization.response("GetMainDataReq", account),
            ("GetEquipmentDataRsp", {"retcode": 0, **{key: deepcopy(account.get(key, []))
                for key in ("weapon_list", "stigmata_list", "material_list")}}),
            ("GetAvatarDataRsp", {"retcode": 0, "avatar_list": deepcopy(account.get("avatar_list", []))}),
            difficulty_snapshot(account)]
