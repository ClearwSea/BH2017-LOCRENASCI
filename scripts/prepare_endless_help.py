"""补齐原生深渊说明窗口文本 / Supply the native Endless information dialog text.

Use the deployed textmap as input so unrelated accepted translations are preserved.
Native EndlessInfoDialogContext.SetupView reads EndlessType.introduction.
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
import argparse
import json
from pathlib import Path

KEY = 'Menu_Desc_EndlessInfo'
TEXT = (
    '<color=#beff41>无尽深渊 · 离线规则</color>\\n'
    '每周一、周四04:00换期，每期共33层。未满层按层数、先到时间排名；33层按最佳通关秒数排名，同秒按固定顺序。\\n'
    '33层可从准备入口重挑战，只保留更快成绩，楼层奖励不重复发。每组为舰长与19名模拟对手；前5名晋级，第16名起降级，最低组不降级。无限组前5名保级，并保留3名固定满层对手。\\n\\n'
    '<color=#beff41>温度与对手如何变化</color>\\n'
    '系统模拟7组、每组500人的挑战，根据实力、技巧、投入和波动估算通关率与用时，再抽取本组对手。模拟人群每期成长、流动；同实力按固定顺序处理。\\n'
    '通关普遍又快又稳时升温，吃力时降温；通关率过低会持续冷却，恢复后退出。温度只调整敌人生命，不调整攻击、防御、抗性或流血。\\n'
    '本期温度与对手目标固定，对手进度随时间推进；下期才更新温度与人群。相同初始状态和赛期在电脑、手机上采用相同计算规则。'
)


def build(source, output):
    rows = json.loads(source.read_bytes())
    matches = [r for r in rows if r['ID'] == KEY]
    assert len(matches) <= 1
    if matches:
        matches[0]['Text'] = TEXT
    else:
        rows.append(dict(ID=KEY, Text=TEXT))
    assert not output.exists(), 'Preserve existing artifacts; choose a new output'
    output.write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    build(a.source, a.output)
