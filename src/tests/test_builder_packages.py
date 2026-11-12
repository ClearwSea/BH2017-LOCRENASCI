import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('builder_host', Path(__file__).resolve().parents[1] / 'tools/builder_host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class MainPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        host.write(self.base / 'base-manifest.json', dict(toolchain_id='test-tools'))
        (self.base / 'user-data/keys').mkdir(parents=True)
        (self.base / 'user-data/keys/private.jks').write_bytes(b'preserve-key')

    def package(self, version='0.1.7', files=None, **overrides):
        files = files or {'app/launch_gui.py': b'print("main")', 'app/old.py': b'old'}
        manifest = dict(format='BH2017-main', schema=1, version=version, host_api=1,
                        toolchain_id='test-tools', files=[dict(path=k, size=len(v),
                        sha256=hashlib.sha256(v).hexdigest()) for k,v in files.items()])
        manifest.update(overrides)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('main-manifest.json', json.dumps(manifest))
            for name,raw in files.items(): z.writestr(name, raw)
        buffer.seek(0)
        return buffer

    def test_upgrade_switches_whole_tree_and_rollback_preserves_user_data(self):
        old = host.import_main(self.base, self.package('0.1.6'))
        new = host.import_main(self.base, self.package(files={'app/launch_gui.py': b'new'}))
        self.assertFalse((host.package_dir(self.base, new) / 'app/old.py').exists())
        self.assertEqual(host.read(host.state_path(self.base)), dict(current=new, previous=old))
        host.rollback(self.base)
        self.assertEqual(host.read(host.state_path(self.base))['current'], old)
        self.assertEqual((self.base / 'user-data/keys/private.jks').read_bytes(), b'preserve-key')

    def test_incompatible_tools_do_not_replace_current(self):
        old = host.import_main(self.base, self.package())
        with self.assertRaisesRegex(ValueError, '工具链'):
            host.import_main(self.base, self.package('0.1.8', toolchain_id='different'))
        self.assertEqual(host.read(host.state_path(self.base))['current'], old)

    def test_corrupt_payload_does_not_replace_current(self):
        old = host.import_main(self.base, self.package())
        damaged = self.package('0.1.8')
        with zipfile.ZipFile(damaged) as z: raw = {n:z.read(n) for n in z.namelist()}
        raw['app/launch_gui.py'] = b'X' * len(raw['app/launch_gui.py'])
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            for n,v in raw.items(): z.writestr(n,v)
        out.seek(0)
        with self.assertRaisesRegex(ValueError, '校验失败'): host.import_main(self.base, out)
        self.assertEqual(host.read(host.state_path(self.base))['current'], old)

    def test_path_escape_rejected(self):
        for path in ('app/../escape', 'app/C:/bad', 'app\\bad', 'user-data/keys/local.jks', 'app/./bad', 'app/bad.'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                host.import_main(self.base, self.package(files={'app/launch_gui.py':b'x', path:b'y'}))

    def test_case_collisions_and_unlisted_members_rejected(self):
        with self.assertRaises(ValueError):
            host.import_main(self.base, self.package(files={'app/launch_gui.py':b'x','app/A':b'x','app/a':b'x'}))
        package = self.package()
        with zipfile.ZipFile(package, 'a') as z: z.writestr('app/extra',b'x')
        package.seek(0)
        with self.assertRaises(ValueError): host.import_main(self.base, package)

    def test_import_same_version_is_idempotent(self):
        identity = host.import_main(self.base, self.package())
        self.assertEqual(host.import_main(self.base, self.package()), identity)
        self.assertIsNone(host.read(host.state_path(self.base))['previous'])

    def test_modified_installed_package_fails_before_launch(self):
        identity = host.import_main(self.base, self.package())
        (host.package_dir(self.base, identity) / 'app/old.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '校验失败'): host.verify_installed(self.base, identity)

    def test_new_host_api_rejected(self):
        with self.assertRaisesRegex(ValueError, '基础包'):
            host.import_main(self.base, self.package(host_api=2))
