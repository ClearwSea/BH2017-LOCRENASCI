"""External archive loading and source-boundary regressions, using synthetic data."""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile
from packager.core import BuildError
from packager.supplements import IMAGES, PACKAGE_KIND, load
from tools.check_source_boundary import check


class SupplementChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.archive = self.root / 'extra.zip'

    def make(self, extra=None, omitted=None, kind=PACKAGE_KIND):
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('supplements.json', json.dumps({'schema': 1, 'kind': kind}))
            for name in IMAGES:
                if name != omitted:
                    z.writestr('images/' + name, b'\x89PNG\r\n\x1a\nsynthetic')
            if extra: z.writestr(extra, b'synthetic')

    def test_external_images_are_copied_unchanged(self):
        self.make()
        output = load(self.archive, self.root / 'loaded')
        self.assertEqual((output / 'images/gacha/dracula.png').read_bytes(), b'\x89PNG\r\n\x1a\nsynthetic')

    def test_existing_archive_identifier_remains_compatible(self):
        self.make(kind='bh3-main-external-supplements')
        self.assertTrue((load(self.archive, self.root / 'loaded') / 'images/launcher/app-icon.png').is_file())

    def test_traversal_member_is_rejected_before_extraction(self):
        self.make('../escape')
        with self.assertRaisesRegex(BuildError, 'Unsafe artifact'):
            load(self.archive, self.root / 'loaded')
        self.assertFalse((self.root / 'escape').exists())

    def test_missing_image_is_explicit(self):
        self.make(omitted='launcher/app-icon.png')
        with self.assertRaisesRegex(BuildError, 'launcher/app-icon'):
            load(self.archive, self.root / 'loaded')

    def test_images_are_forbidden_in_source_tree(self):
        root = self.root / 'source'
        root.mkdir()
        (root / 'art.png').write_bytes(b'\x89PNG\r\n\x1a\n')
        self.assertEqual(check(root)['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
