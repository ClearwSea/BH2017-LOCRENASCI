from copy import deepcopy
import unittest

from packager.item_navigation import adapt, restore_text, TABLES, SPLIT_SHOP_TAIL


def link(kind, args='', text='source'):
    return f'<type="{kind}{"|" + args if args else ""}" text="{text}"/>'


class ItemNavigationTests(unittest.TestCase):
    def fixture(self):
        return dict(stagedata_main=[dict(levelId=10305)], **{
            name: [dict(ID=7032 if name == 'materialdata' else 1, rarity=4,
                        comeFromList=[link(17, '1'), link(1, '10305'), link(1, '10707'), link(11)])]
            for name in TABLES})

    def test_all_item_categories_remove_only_absent_stage_links(self):
        tables = self.fixture()
        before = deepcopy(tables)
        result = adapt(tables)
        self.assertEqual(len(result['removed']), 4)
        for name in TABLES:
            expected = deepcopy(before[name][0])
            expected['comeFromList'].pop(2)
            self.assertEqual(tables[name][0], expected)

    def test_available_but_locked_stages_are_retained(self):
        tables = self.fixture()
        tables['stagedata_main'].append(dict(levelId=10707))
        before = deepcopy(tables)
        self.assertEqual(adapt(tables)['removed'], [])
        self.assertEqual(tables, before)

    def test_later_native_navigation_types_are_not_advertised(self):
        tables = self.fixture()
        tables['materialdata'][0]['comeFromList'].append(link(43, '1'))
        report = adapt(tables)
        self.assertEqual(len(report['removed']), 5)
        self.assertEqual(report['removed'][1]['reason'], 'navigation type absent from selected native client')
        self.assertNotIn(link(43, '1'), tables['materialdata'][0]['comeFromList'])

    def test_known_source_shop_tail_removed_without_replacing_valid_shop(self):
        tables = self.fixture()
        tables['materialdata'][0]['comeFromList'].insert(1, SPLIT_SHOP_TAIL)
        result = adapt(tables)
        self.assertEqual(len(result['removed']), 5)
        self.assertEqual(tables['materialdata'][0]['comeFromList'][0], link(17, '1'))

    def test_unexpected_malformed_entry_fails_without_partial_mutation(self):
        tables = self.fixture()
        tables['avatarfragmentdata'][0]['comeFromList'].append('broken')
        before = deepcopy(tables)
        with self.assertRaisesRegex(ValueError, 'Malformed item navigation'):
            adapt(tables)
        self.assertEqual(tables, before)

    def test_invalid_stage_arguments_are_rejected(self):
        for args in ('', '10305;10707'):
            tables = self.fixture()
            tables['materialdata'][0]['comeFromList'] = [link(1, args)]
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'Invalid stage navigation'):
                adapt(tables)

    def test_adaptation_is_idempotent(self):
        tables = self.fixture()
        adapt(tables)
        before = deepcopy(tables)
        self.assertEqual(adapt(tables)['removed'], [])
        self.assertEqual(tables, before)

    def test_restores_only_referenced_missing_source_text(self):
        tables = self.fixture()
        adapt(tables)
        tables['textmap'] = [dict(ID='existing', Text='project wording')]
        source = [dict(ID='source', Text='Original source label'),
                  dict(ID='existing', Text='must not replace'), dict(ID='unrelated', Text='unused')]
        self.assertEqual(restore_text(tables, source), ['source'])
        self.assertEqual(tables['textmap'], [dict(ID='existing', Text='project wording'),
                                            dict(ID='source', Text='Original source label')])
        self.assertEqual(restore_text(tables, source), [])

    def test_missing_source_text_fails_without_adding_partial_labels(self):
        tables = self.fixture()
        adapt(tables)
        tables['textmap'] = []
        with self.assertRaisesRegex(ValueError, 'Missing source acquisition text'):
            restore_text(tables, [])
        self.assertEqual(tables['textmap'], [])


class LocalDestinationTests(unittest.TestCase):
    def fixture(self, entries, identity=7032):
        return {'materialdata': [dict(ID=identity, rarity=4, comeFromList=entries)]}

    def catalog(self):
        return dict(shops={1: dict(name='材料', items={7032}),
                           5: dict(name='碎片', items={10401}),
                           6: dict(name='补给卡', items={1101})},
                    stages={10305: {7032}, 30112: {1001}},
                    activities={1601: {7032}}, openworld={7032}, duty={7032})

    def test_shop_destinations_follow_stock_and_deduplicate(self):
        from packager.item_navigation import reconcile
        tables = self.fixture([link(17, '5'), link(17, '8'), link(17, '1')])
        result = reconcile(tables, self.catalog())
        self.assertEqual(tables['materialdata'][0]['comeFromList'],
                         [link(17, '1', 'LocalObtainShop1')])
        self.assertEqual(result['labels'], [dict(ID='LocalObtainShop1', Text='【购买】材料')])
        self.assertFalse(reconcile(tables, self.catalog())['changed'])

    def test_unsold_item_has_no_misleading_shop(self):
        from packager.item_navigation import reconcile
        tables = self.fixture([link(17, '1'), link(39, '36012')], identity=903)
        reconcile(tables, self.catalog())
        self.assertEqual(tables['materialdata'][0]['comeFromList'], [])

    def test_stage_exists_but_does_not_drop_item(self):
        from packager.item_navigation import reconcile
        tables = self.fixture([link(1, '10305'), link(1, '30112'), link(2, '1501'), link(3, '1601')])
        reconcile(tables, self.catalog())
        self.assertEqual(tables['materialdata'][0]['comeFromList'],
                         [link(1, '10305'), link(3, '1601')])

    def test_openworld_only_actual_reward_items_and_generic_entry(self):
        from packager.item_navigation import reconcile
        tables = self.fixture([link(23, '2;1;311'), link(23, '1')])
        reconcile(tables, self.catalog())
        self.assertEqual(tables['materialdata'][0]['comeFromList'], [link(23, '1', 'LocalObtainSakura')])
        tables = self.fixture([link(23, '1')], identity=5550)
        reconcile(tables, self.catalog())
        self.assertEqual(tables['materialdata'][0]['comeFromList'], [])

    def test_usage_links_preserved_and_unimplemented_acquisition_removed(self):
        from packager.item_navigation import reconcile
        tables = self.fixture([link(6, '2'), link(32, '1')] +
                              [link(k) for k in (10, 11, 15, 16, 30, 37, 39)])
        reconcile(tables, self.catalog())
        self.assertEqual(tables['materialdata'][0]['comeFromList'], [link(6, '2'), link(32, '1')])
