"""Desktop packager stage coverage and input validation checks."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from packager.core import BuildError, ROOT
from packager.desktop import STAGES
from packager.desktop_runtime import check


class DesktopPackagerTests(unittest.TestCase):
    def test_desktop_stages_cover_every_original_build_stage(self):
        tree = ast.parse((ROOT / 'packager/original.py').read_text(encoding='utf-8'))
        build_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
        emitted = []
        for node in ast.walk(build_fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'stage'
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                emitted.append((node.lineno, node.col_offset, node.args[0].value))
        self.assertEqual(list(STAGES), [name for _, _, name in sorted(emitted)])

    def _valid_fixture(self, root):
        for name in ('c19.apk', 'c24.apk'):
            with zipfile.ZipFile(root / name, 'w') as z:
                z.writestr('AndroidManifest.xml', b'<manifest/>')
        with zipfile.ZipFile(root / 'supp.zip', 'w') as z:
            z.writestr('supplements.json', json.dumps({'schema': 1, 'kind': 'bh2017-locrenasci-external-supplements'}))
            z.writestr('fuka601/v1/content/manifest.json', '{}')
            z.writestr('fuka601/v1/fuka601-v1-content.zip', b'pk')
        r7x = root / 'r7x'
        (r7x / 'Audio').mkdir(parents=True, exist_ok=True)
        (r7x / 'Video').mkdir(parents=True, exist_ok=True)
        tools = root / 'tools'
        for rel in (
            'zig/zig.exe', 'ffmpeg/ffmpeg.exe', 'vgmstream/vgmstream-cli.exe',
            'android/sdk/platforms/android-35/android.jar',
            'android/sdk/build-tools/35.0.0/zipalign.exe',
            'android/sdk/build-tools/35.0.0/apksigner.bat',
            'android/sdk/build-tools/34.0.0/aapt.exe',
            'android/python311/tools/python.exe',
            'android/gradle/gradle-8.9/bin/gradle.bat',
            'android/jdk/temurin-17/bin/java.exe',
            'wheelhouse/pkg-1.0-py3-none-any.whl',
        ):
            p = tools / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'x')
        out = root / 'out'
        return {
            'client19': str(root / 'c19.apk'),
            'client24': str(root / 'c24.apk'),
            'resources7x': str(r7x),
            'supplements': str(root / 'supp.zip'),
            'tools': str(tools),
            'output': str(out),
            'keystore': '',
        }

    def test_check_accepts_valid_inputs_and_rejects_bad_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._valid_fixture(root)
            checked = check(settings)
            self.assertEqual(checked['client19'], (root / 'c19.apk').resolve())

            with zipfile.ZipFile(root / 'c19.apk', 'w') as z:
                z.writestr('other.txt', b'not-an-apk')
            with self.assertRaisesRegex(BuildError, 'AndroidManifest.xml'):
                check(settings)

            settings = self._valid_fixture(root)
            with zipfile.ZipFile(root / 'supp.zip', 'w') as z:
                z.writestr('supplements.json', json.dumps({'schema': 1, 'kind': 'bh2017-locrenasci-external-supplements'}))
            with self.assertRaisesRegex(BuildError, '补充资源包版本不匹配'):
                check(settings)


if __name__ == '__main__':
    unittest.main()
