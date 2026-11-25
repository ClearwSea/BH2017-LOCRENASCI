import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from packager import v030_verified_content as content
from packager.core import BuildError

def sha(value):return hashlib.sha256(value).hexdigest()

class VerifiedContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.work=root/'work';self.work.mkdir();self.bundle=root/'supplements'
        content_dir=self.bundle/'fuka601/v1/content';(content_dir/'payload').mkdir(parents=True)
        self.target=self.work/'runtime/one.py';self.target.parent.mkdir();self.target.write_bytes(b'before')
        (content_dir/'payload/value').write_bytes(b'after')
        self.manifest={'schema':1,'kind':'bh2017-v030-verified-content','count':1,'files':[
            {'path':'runtime/one.py','before':sha(b'before'),'after':sha(b'after'),'size':5,'payload':'payload/value'}]}
        self.path=content_dir/'manifest.json';self.save_manifest()
    def save_manifest(self):
        data=json.dumps(self.manifest).encode();self.path.write_bytes(data)
        self.pin=patch.object(content,'CONTENT_MANIFEST_SHA256',sha(data));self.pin.start();self.addCleanup(self.pin.stop)
    def test_checked_replay_and_conflict(self):
        self.assertEqual(content.apply(self.work,self.bundle)['files'],1)
        self.assertEqual(self.target.read_bytes(),b'after')
        with self.assertRaises(BuildError):content.apply(self.work,self.bundle)
    def test_conflict_does_not_modify_other_files(self):
        self.target.write_bytes(b'conflict')
        with self.assertRaises(BuildError):content.apply(self.work,self.bundle)
        self.assertEqual(self.target.read_bytes(),b'conflict')
    def test_cannot_overwrite_bulletin(self):
        self.manifest['files'][0]['path']='runtime/server19_bulletin.py';self.save_manifest()
        with self.assertRaises(BuildError):content.plan(self.work,self.bundle)

if __name__=='__main__':unittest.main()
