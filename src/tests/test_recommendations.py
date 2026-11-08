import copy
import unittest

from packager.core import BuildError
from packager.recommendations import adapt, sync_tsv, validate


class RecommendationsTests(unittest.TestCase):
    def setUp(self):
        row = dict(equipAdvID=2022, weaponAdvID=10, weaponAdvText='weapon',
                   stigmataAdv1ID=21, stigmataAdv2ID=22, stigmataAdv3ID=23,
                   stigmataAdvText='valid-description', practiceStageID=1)
        invalid = dict(row, equipAdvID=2021, stigmataAdv1ID=99,
                       stigmataAdvText='old-description')
        self.tables = dict(
            newbieequipadv=[invalid, row], weapondata=[dict(ID=10, baseType=2)],
            stigmatadata=[dict(ID=20+i, baseType=i) for i in (1, 2, 3)],
            avatardata=[dict(avatarID=202, weaponBaseTypeList=[2])],
            newbiegroupadv=[dict(groupAdvID=1, groupAvatarID=202, recommendText='group')],
            avatareffectinfo=[dict(effectID=1)],
            textmap=[dict(ID=x) for x in ('weapon', 'valid-description', 'old-description', 'group')],
            newbieavatarguide=[dict(avatarID=202, EquipAdvNewbieID=2021,
                                   EquipAdvSuperiorID=2022, groupAdvsID=[1], avatarEffects=[1])])

    def test_missing_reference_rejected_then_explanation_moves_with_set(self):
        with self.assertRaises(BuildError):
            validate(self.tables)
        unchanged = copy.deepcopy(self.tables['newbieequipadv'][1])
        adapt(self.tables, {'equipment': [{'id': 2021, 'stigmata_from': 2022}]})
        self.assertEqual(self.tables['newbieequipadv'][0]['stigmataAdvText'], 'valid-description')
        self.assertEqual(self.tables['newbieequipadv'][1], unchanged)

    def test_wrong_slot_rejected(self):
        self.tables['newbieequipadv'][0]['stigmataAdv1ID'] = 22
        with self.assertRaises(BuildError):
            validate(self.tables)

    def test_related_group_reference_rejected(self):
        self.tables['newbiegroupadv'][0]['groupAvatarID'] = 999
        with self.assertRaises(BuildError):
            adapt(self.tables, {'equipment': [{'id': 2021, 'stigmata_from': 2022}]})

    def test_text_asset_preserves_source_only_columns(self):
        raw = b'EquipAdvID\tWeaponAdvID\tGameVersionBegin\n2022\t99\t1.5\n'
        result = sync_tsv(raw, self.tables['newbieequipadv'])
        self.assertIn(b'2022\t10\t1.5\n', result)


if __name__ == '__main__':
    unittest.main()
