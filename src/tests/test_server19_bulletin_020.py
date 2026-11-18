"""Keep the approved bulletin text and both native announcement tabs intact."""
import hashlib
import unittest

import server19_bulletin as bulletin


APPROVED = (
    '<color=#FF4040FF>当前版本为V0.2.0</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n'
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


class Bulletin020Test(unittest.TestCase):
    def test_approved_text_and_whitespace(self):
        self.assertEqual(APPROVED, bulletin.UPDATE_CONTENT_V020)
        numbered = [line for line in APPROVED.splitlines() if line[:2] in
                    ('1.', '2.', '3.', '4.', '5.', '6.')]
        self.assertEqual([line[:3] for line in numbered],
                         [str(i) + '.\u00a0' for i in range(1, 7)])
        self.assertNotIn('\\<color', APPROVED)

    def test_both_tabs_and_prior_announcement(self):
        kind, response = bulletin.response('GetBulletinReq', {}, {'type': 1})
        self.assertEqual(kind, 'GetBulletinRsp')
        all_rows = response['bulletin_list']
        self.assertEqual(len({row['id'] for row in all_rows}), len(all_rows))
        rows = [row for row in all_rows if row['title_button'] == '更新公告V0.2.0']
        self.assertEqual({(row['id'], row['type']) for row in rows}, {(201811, 0), (201812, 1)})
        self.assertTrue(all(row['content'] == APPROVED for row in rows))
        old = [row for row in all_rows if row['title_button'] == '更新公告V0.1.7-r4']
        self.assertEqual(len(old), 2)
        self.assertTrue(all(row['weight'] < rows[0]['weight'] for row in old))
        self.assertEqual(hashlib.sha256(bulletin.UPDATE_CONTENT_V017R4.encode()).hexdigest(),
                         'a0b560ae03125edfd17aa645019f03b698fc847851d2488f83a9e8038054172b')

    def test_specific_id_fetch(self):
        _, result = bulletin.response('GetBulletinReq', {},
                                      {'type': 2, 'bulletin_id_list': [201811, 201812]})
        self.assertFalse(result['is_all'])
        self.assertEqual({row['id'] for row in result['bulletin_list']}, {201811, 201812})
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
                r4 = next(row for row in updates if row['title_button'] == '更新公告V0.1.7-r4')
                current = next(row for row in updates if row['title_button'] == '更新公告V0.2.0')
                self.assertGreater(current['weight'], r4['weight'])
                expected = ['更新公告V0.2.0', '更新公告V0.1.7-r4', '更新公告V0.1.7-r3',
                            '更新公告V0.1.7-r2', '更新公告V0.1.7-r1', '更新公告V0.1.7',
                            '更新公告V0.1.6', '更新公告V0.1.5', '更新公告V0.1.4',
                            '更新公告V0.1.3', '更新公告V0.1.2']
                self.assertEqual([row['title_button'] for row in sorted(updates, key=lambda x: -x['weight'])], expected)

    def test_all_prior_texts_are_preserved(self):
        # Hashes from the released v0.1.7-r4 tag; only r4's lead-in is revised.
        prior = {
            'UPDATE_CONTENT': '4fa7622d212e3d2310c29d233f07f4311ef6abbf4ccc7b89793321a372bb5c57',
            'UPDATE_CONTENT_V013': 'c601fa990992b3733d0c2a6f90b08d07de59b66a77790e76b741aa938d8437da',
            'UPDATE_CONTENT_V014': '18b8750177722f4c3d11c5bc8cc27d3a35e7afd48b73a317492a8771a0a30e7e',
            'UPDATE_CONTENT_V015': 'c21183384e798d4c947d0f6ac940af0e5e8c2aa7f718ed81435f1c1644b38ca5',
            'UPDATE_CONTENT_V016': 'e86868361288f8dc8beca14cf6a0a561919e4b08f02905971e4368dcf00868dc',
            'UPDATE_CONTENT_V017': '40c343595b8c22208cde34378a8fab08a92c6a7930866f000bb5711f5e2de6cc',
            'UPDATE_CONTENT_V017R1': 'f149939b8da07344be8e6f0a7d884964114346d7df04728e4b67f938d36d37ac',
            'UPDATE_CONTENT_V017R2': 'd357d13e0c6c5f9895a5a4083556b4b87cc178bbc4ffe8a45900640ead8567fc',
            'UPDATE_CONTENT_V017R3': 'e4b87729ff677185f401e6da562e1acf41e65bfe666d858ed45a7d1caad9c7a8',
            'UPDATE_CONTENT_V017R4': 'e96ebddad8c4d984350cad16649c0e41b7ade9e035cc810b0e092f0cab5849c0',
        }
        for name, expected in prior.items():
            value = getattr(bulletin, name)
            if name == 'UPDATE_CONTENT_V017R4':
                value = value.replace('该公告面向V0.1.7-r4', '当前版本为V0.1.7-r4', 1)
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(value.encode()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
