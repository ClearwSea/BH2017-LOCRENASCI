"""Verify launcher V0.3.0-r1 version, detail notice links, and reading gate."""
from pathlib import Path
import unittest


JAVA_DIR = Path(__file__).resolve().parents[1] / 'android-server-probe/app/src/main/java/local/bh3/server19probe'


class LauncherNoticeTests(unittest.TestCase):
    def test_launcher_version_outer_card_and_mandatory_gate(self):
        screen = (JAVA_DIR / 'LauncherScreen.java').read_text(encoding='utf-8')
        activity = (JAVA_DIR / 'IntegratedActivity.java').read_text(encoding='utf-8')
        notice = (JAVA_DIR / 'LauncherNotice.java').read_text(encoding='utf-8')

        self.assertIn('static final String VERSION = "V0.3.0-r1";', screen)
        self.assertIn(
            '"项目仅供数字遗产保存与学习交流，版权归米哈游所有\\n------------------\\n'
            '禁止倒卖；如果你是花钱付费获取，说明你被骗了，请申请退款并举报。"',
            screen,
        )
        self.assertIn('pop.setCancelable(false)', screen)
        self.assertIn('pop.setCanceledOnTouchOutside(false)', screen)
        self.assertIn('readBox.setText("我已阅读")', screen)
        self.assertIn('new CountDownTimer(10000,250)', screen)

        self.assertIn('private static final String PREF_NOTICE_ACK_VERSION = "notice_ack_version";', activity)
        self.assertIn('if (!LauncherScreen.VERSION.equals(ackVersion))', activity)
        self.assertIn('new CountDownTimer(3000, 250)', activity)
        self.assertNotIn('new CountDownTimer(5000', activity)

        self.assertEqual(activity.count('遇到问题之前请确保当前是最新构建版！'), 3)
        self.assertIn('仅在特定开发平台验证，不做可玩性技术承诺。', activity)
        self.assertIn('\\u3000\\u3000部分采用Mali GPU的新款机型', activity)
        self.assertIn('\\u3000\\u3000采用Maleoon GPU的机型', activity)

        self.assertIn('while ((index = raw.indexOf(label, index)) >= 0)', notice)
        self.assertIn('linkAll(content, raw, "最新构建版", LATEST_RELEASE_URL);', notice)
        self.assertIn('linkAll(content, raw, "特定开发平台验证", VERIFIED_PLATFORMS_URL);', notice)
        self.assertIn('https://github.com/ClearwSea/BH2017-LOCRENASCI/releases/latest', notice)
        self.assertIn('https://github.com/ClearwSea/BH2017-LOCRENASCI#详细参考源码导航与实测列表', notice)


if __name__ == '__main__':
    unittest.main()
