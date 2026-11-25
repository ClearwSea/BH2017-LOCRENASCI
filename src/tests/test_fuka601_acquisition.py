import json
from pathlib import Path
import shutil
import tempfile
import unittest

from packager import fuka601_acquisition as patch
from packager.core import BuildError

SOURCE=Path(__file__).resolve().parents[1]/'release_021_data'

class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name)
        for section in ('runtime','resources'):
            shutil.copytree(SOURCE/section,self.work/section)
        meta=self.work/'resources/private/data/bh3-server19-metadata/_exceloutputasset'
        (meta/'avatardata').write_text(json.dumps([{'avatarID':601,'avatarCardID':60601,'avatarFragmentID':10601}]),encoding='utf-8')
        posters=self.work/'runtime/supply-posters';posters.mkdir()
        (posters/'E02.png').write_bytes(b'\x89PNG\r\n\x1a\n-test')
        catalog=json.loads((self.work/'runtime/gm-catalog.json').read_bytes())
        supply={'themes':[{'key':'E02'}],'previews':{'E02':'same'}}
        (self.work/'gm2017.html').write_text('var data='+json.dumps(catalog,ensure_ascii=False)+';\nvar supplyData='+json.dumps(supply)+';\n',encoding='utf-8')

    def test_data_and_conflict_protection(self):
        planned=patch.plan(self.work)
        self.assertFalse((self.work/'runtime/supply-posters/E07.png').exists())
        patch.apply(self.work)
        cat=json.loads((self.work/'runtime/gm-catalog.json').read_bytes())
        self.assertTrue(cat['items']['10601']['available'])
        self.assertFalse(cat['items']['10603']['available'])
        for key in ('runtime/.local-baseline/server19-dev/metadata-cg-icons-corrected/_exceloutputasset/shopgoodsdata',
                    'resources/private/data/bh3-server19-metadata/_exceloutputasset/shopgoodsdata'):
            self.assertEqual([r for r in json.loads((self.work/key).read_bytes()) if r['ID']==900037],[patch.GOODS])
        self.assertEqual((self.work/'runtime/supply-posters/E07.png').read_bytes(),(self.work/'runtime/supply-posters/E02.png').read_bytes())
        page=(self.work/'gm2017.html').read_text(encoding='utf-8').splitlines()
        supply=json.loads(next(s for s in page if s.startswith('var supplyData='))[15:-1])
        self.assertEqual(supply['themes'][-1],patch.THEME)
        self.assertEqual(supply['previews']['E07'],supply['previews']['E02'])
        tsv=(self.work/'resources/private/data/bh3-server19-resources/data/_exceloutput/shopgoodsdata').read_text(encoding='utf-8').splitlines()
        self.assertEqual([r for r in tsv if r.startswith('900037\t')],[patch.TSV])
        self.assertEqual((self.work/'runtime/server19_gacha.py').read_bytes(),planned['runtime/server19_gacha.py'])
        with self.assertRaises(BuildError):patch.plan(self.work)

    def test_character_precondition_does_not_write(self):
        path=self.work/'resources/private/data/bh3-server19-metadata/_exceloutputasset/avatardata'
        path.write_text('[]',encoding='utf-8')
        original=(self.work/'gm2017.html').read_bytes()
        with self.assertRaises(BuildError):patch.apply(self.work)
        self.assertEqual((self.work/'gm2017.html').read_bytes(),original)

if __name__=='__main__':unittest.main()
