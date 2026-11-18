import unittest
import server19_editor_material_presets as presets
import server19_editor_inventory as inventory


class MaterialPresetsTests(unittest.TestCase):
    def test_recipe_evidence_channel_evidence_capacity_and_preserved_stock(self):
        def mat(i, kind, limit, **fields):
            return {'ID': i, 'ItemType': kind, 'quantityLimit': limit, **fields}
        catalog = {'materialdata': [mat(1001, 'exp_item', 40, characterExpProvide=60),
                                  mat(3000, 'evo_material', 1000, gearExpProvideBase=200),
                                  mat(4001, 'evo_material', 1000), mat(4002, 'evo_material', 1000),
                                  mat(1101, 'gacha_item', 9999), mat(1104, 'gacha_item', 9999)],
                   'weapondata': [{'evoMaterial': ['4001:1', '0']} for _ in range(5)] +
                                 [{'evoMaterial': ['4002:1']}],
                   'stigmatadata': [], 'avatardata': []}
        groups = presets.build(catalog, {1: {'ticket_material_id': 1101}})
        values = {x['id']: x['items'] for x in groups}
        self.assertEqual(values['avatar_exp'], [{'id': 1001, 'num': 39}])
        self.assertEqual(values['equipment_evolution'], [{'id': 4001, 'num': 200}])
        self.assertEqual(values['supply_tickets'], [{'id': 1101, 'num': 100}])
        account = {'material_list': [{'id': 1001, 'num': 40}]}
        edited = inventory.apply(account, catalog, {'op': 'materials_batch', 'items': values['avatar_exp']})
        self.assertEqual(edited['material_list'], [{'id': 1001, 'num': 40}])
        self.assertEqual(account['material_list'], [{'id': 1001, 'num': 40}])


if __name__ == '__main__':
    unittest.main()
