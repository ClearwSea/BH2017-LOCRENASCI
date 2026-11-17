import unittest

from packager.core import BuildError
from packager.weekday_covers import adapt


class WeekdayCoversTest(unittest.TestCase):
    def test_native_paths_for_five_themes_preserve_red_packet(self):
        rows = [{'weekDayActivityID': 1001 + i,
                 'enterImgPath': f'SpriteOutput/ChapterCover/Event/BookEventDailyMaterial{i + 1:02d}'}
                for i in range(5)]
        rows.append({'weekDayActivityID': 1301,
                     'enterImgPath': 'SpriteOutput/ChapterCover/Event/BookEventDiaryMoney'})
        rows.append({'weekDayActivityID': 1531,
                     'enterImgPath': 'SpriteOutput/ChapterCover/Event/BookEventDaily02'})
        native = [row['enterImgPath'].replace('/Event/', '/Event/Event/').lower() for row in rows[:5]]
        native.append(rows[-1]['enterImgPath'].replace('/Event/', '/Event/Event/').lower())
        self.assertEqual(adapt(rows, native), 6)
        self.assertEqual([r['enterImgPath'].lower() for r in rows[:5]], native[:5])
        self.assertEqual(rows[-1]['enterImgPath'].lower(), native[-1])
        self.assertEqual(rows[-2]['enterImgPath'], 'SpriteOutput/ChapterCover/Event/BookEventDiaryMoney')

    def test_missing_native_artwork_rejected(self):
        rows = [{'weekDayActivityID': 1001 + i,
                 'enterImgPath': f'SpriteOutput/ChapterCover/Event/BookEventDailyMaterial{i + 1:02d}'}
                for i in range(5)]
        with self.assertRaises(BuildError):
            adapt(rows, [])


if __name__ == '__main__':
    unittest.main()
