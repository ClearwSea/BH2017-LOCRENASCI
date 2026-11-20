"""Keep the approved bulletin text and both native announcement tabs intact."""
import hashlib
import unittest

import server19_bulletin as bulletin


APPROVED_V020 = (
    '<color=#FF4040FF>该公告面向V0.2.0</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n'
    '<color=#00C3FFFF>本次修复与改进</color>\n'
    '1.\u00a0<color=#FF4040FF>兼容开放</color>女武神训练基地的生物、异能、机械、武器及圣痕材料训练；掉落数据采用本地兼容规则并适当提高。\n'
    '2.\u00a0<color=#FF4040FF>兼容开放</color>单人曜日活动；修复部分活动及训练基地封面显示异常的问题，未完整验收，按照本地规则实现。\n'
    '3.\u00a0<color=#FF4040FF>兼容开放</color>记忆战场，未完整验收，按照本地规则实现。\n'
    '4.\u00a0进一步修复部分补给券消耗至 0 后，界面数量未及时清零的问题。\n'
    '5.\u00a0<color=#FF4040FF>兼容修复</color>樱色轮回第二轮回末尾剧情结束后报错的问题。\n'
    '6.\u00a0重构更美观的启动页面，保留原核心功能，以及更丰富的内置存档编辑备份，伪服务端GM功能（未做完整测试）。\n\n'
    '<color=#00C3FFFF>问题反馈</color>\n'
    '如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n'
    '——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n'
    '鸣谢 Hssssssssi，以及各位AI。'
)

APPROVED = (
    '<color=#FF4040FF>当前版本为V0.2.0-r1</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n'
    '<color=#00C3FFFF>本次修复与改进</color>\n'
    '1.\u00a0<color=#FF4040FF>兼容修复</color>装备「吼姆」圣痕套装后，进入主线困难 2-18 等关卡时卡死在加载界面的问题。\n'
    '2.\u00a0修复脉冲装·绯红闪避技能「瞬斩」及分支「樱花散落」等部分女武神技能描述文本缺失的问题。\n'
    '3.\u00a0补全里纳尔多（下）、时雨绮罗（上）、阿提拉（下）、呼邪（中/下）、姬鳞·戏水（上/中）、查理曼（下）、罗兰（上/下）圣痕缺失部位的数据配置（<color=#FF4040FF>尚未逐一实机穿戴验收</color>）。\n\n'
    '<color=#00C3FFFF>更新提示</color>\n'
    '本次为热修版本，Windows 构建器沿用 <b>V0.2.0 基础包</b>，仅需下载并导入新版构建主包重新构建 APK；覆盖安装前请先导出备份存档。\n\n'
    '<color=#00C3FFFF>问题反馈</color>\n'
    '如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n'
    '——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n'
    '鸣谢 Hssssssssi，以及各位AI。'
)


class Bulletin020Test(unittest.TestCase):
    def test_approved_text_and_whitespace(self):
        self.assertEqual(APPROVED, bulletin.UPDATE_CONTENT_V020R1)
        self.assertEqual(APPROVED_V020, bulletin.UPDATE_CONTENT_V020)
        numbered = [line for line in APPROVED.splitlines() if line[:2] in
                    ('1.', '2.', '3.')]
        self.assertEqual([line[:3] for line in numbered],
                         [str(i) + '.\u00a0' for i in range(1, 4)])
        self.assertNotIn('\\<color', APPROVED)

    def test_both_tabs_and_prior_announcement(self):
        kind, response = bulletin.response('GetBulletinReq', {}, {'type': 1})
        self.assertEqual(kind, 'GetBulletinRsp')
        all_rows = response['bulletin_list']
        self.assertEqual(len({row['id'] for row in all_rows}), len(all_rows))
        rows = [row for row in all_rows if row['title_button'] == '更新公告V0.2.0-r1']
        self.assertEqual({(row['id'], row['type']) for row in rows}, {(201821, 0), (201822, 1)})
        self.assertTrue(all(row['content'] == APPROVED for row in rows))
        old_v020 = [row for row in all_rows if row['title_button'] == '更新公告V0.2.0']
        self.assertEqual({(row['id'], row['type']) for row in old_v020}, {(201811, 0), (201812, 1)})
        self.assertTrue(all(row['content'] == APPROVED_V020 for row in old_v020))
        self.assertTrue(all(row['weight'] < rows[0]['weight'] for row in old_v020))
        old = [row for row in all_rows if row['title_button'] == '更新公告V0.1.7']
        self.assertEqual(len(old), 2)
        self.assertTrue(all(row['weight'] < old_v020[0]['weight'] for row in old))
        self.assertFalse(any(row['title_button'].startswith('更新公告V0.1.7-r') for row in all_rows))
        for marker in ('V0.1.7 修复与改进', 'V0.1.7-r1 修复与改进', 'V0.1.7-r2 修复与改进',
                       'V0.1.7-r3 修复与改进', 'V0.1.7-r4 修复与改进'):
            self.assertIn(marker, bulletin.UPDATE_CONTENT_V017)
        self.assertEqual(bulletin.UPDATE_CONTENT_V017.count('该公告面向V0.1.7'), 1)
        self.assertEqual(bulletin.UPDATE_CONTENT_V017.count('问题反馈'), 1)
        self.assertEqual(bulletin.UPDATE_CONTENT_V017.count('GITHUB/ClearwSea'), 1)

    def test_specific_id_fetch(self):
        _, result = bulletin.response('GetBulletinReq', {},
                                      {'type': 2, 'bulletin_id_list': [201821, 201822]})
        self.assertFalse(result['is_all'])
        self.assertEqual({row['id'] for row in result['bulletin_list']}, {201821, 201822})
        self.assertTrue(all(row['content'] == APPROVED for row in result['bulletin_list']))

    def test_offline_guide_precedes_all_update_weights_in_each_tab(self):
        _, result = bulletin.response('GetBulletinReq', {}, {'type': 1})
        rows = result['bulletin_list']
        for kind in (0, 1):
            with self.subTest(kind=kind):
                entries = [row for row in rows if row['type'] == kind]
                guide = next(row for row in entries if row['title_button'] == 'V1.9离线版说明')
                updates = [row for row in entries if row['title_button'].startswith('更新公告')]
                self.assertTrue(updates)
                self.assertGreater(guide['weight'], max(row['weight'] for row in updates))
                v020 = next(row for row in updates if row['title_button'] == '更新公告V0.2.0')
                current = next(row for row in updates if row['title_button'] == '更新公告V0.2.0-r1')
                self.assertGreater(current['weight'], v020['weight'])
                expected = ['更新公告V0.2.0-r1', '更新公告V0.2.0', '更新公告V0.1.7',
                            '更新公告V0.1.6', '更新公告V0.1.5', '更新公告V0.1.4',
                            '更新公告V0.1.3', '更新公告V0.1.2']
                self.assertEqual([row['title_button'] for row in sorted(updates, key=lambda x: -x['weight'])], expected)

    def test_all_prior_texts_are_preserved(self):
        prior = {
            'UPDATE_CONTENT': '4fa7622d212e3d2310c29d233f07f4311ef6abbf4ccc7b89793321a372bb5c57',
            'UPDATE_CONTENT_V013': 'c601fa990992b3733d0c2a6f90b08d07de59b66a77790e76b741aa938d8437da',
            'UPDATE_CONTENT_V014': '18b8750177722f4c3d11c5bc8cc27d3a35e7afd48b73a317492a8771a0a30e7e',
            'UPDATE_CONTENT_V015': 'c21183384e798d4c947d0f6ac940af0e5e8c2aa7f718ed81435f1c1644b38ca5',
            'UPDATE_CONTENT_V016': 'e86868361288f8dc8beca14cf6a0a561919e4b08f02905971e4368dcf00868dc',
        }
        for name, expected in prior.items():
            value = getattr(bulletin, name)
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(value.encode()).hexdigest(), expected)
        positions = [bulletin.UPDATE_CONTENT_V017.index(tag) for tag in (
            'V0.1.7 修复与改进', 'V0.1.7-r1 修复与改进', 'V0.1.7-r2 修复与改进',
            'V0.1.7-r3 修复与改进', 'V0.1.7-r4 修复与改进'
        )]
        self.assertEqual(positions, sorted(positions))


if __name__ == '__main__':
    unittest.main()
