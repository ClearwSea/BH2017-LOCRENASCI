"""Real generated runtime regression for fragment unlock and story reward ordering."""
from copy import deepcopy
import json,os,sys,tempfile,unittest
from pathlib import Path

@unittest.skipUnless(os.environ.get('BH3_TEST_RUNTIME') and os.environ.get('BH3_TEST_ACCOUNT'), 'requires generated runtime and reproduced account')
class FragmentUnlockTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  sys.path.insert(0,os.environ['BH3_TEST_RUNTIME'])
  import server19_portable as portable
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.fixture=json.loads(Path(os.environ['BH3_TEST_ACCOUNT']).read_bytes())
  Path(cls.tmp.name,'account.json').write_text(json.dumps(cls.fixture))
  portable.configure(cls.tmp.name)
  import server19_stage as stage,server19_avatar_cultivation as cultivation,server19_missions as missions
  cls.stage=stage;cls.c=cultivation;cls.m=missions
 def setUp(self):
  self.account=deepcopy(self.fixture)
  self.path=Path(self.tmp.name,'request.json')
 def request(self,module,name,values):
  self.path.write_text(json.dumps(self.account))
  return module.response(name,self.account,values,account_path=self.path)[1]
 def locked(self,identity,count):
  self.account['avatar_list']=[x for x in self.account['avatar_list'] if x['avatar_id']!=identity]
  self.account['avatar_list'].append(dict(avatar_id=identity,star=0,level=1,exp=0,fragment=count,weapon_unique_id=0))
 def test_regular_unlocks_use_actual_cumulative_cost_and_valid_weapon(self):
  import server19_avatar_fragments as fragments
  tables=self.c._tables()
  for meta in tables['avatardata']:
   identity=meta['avatarID']
   if meta['baseAvatarID'] or fragments.AUDITED_IDS.get(meta['avatarFragmentID'])!=identity:continue
   with self.subTest(avatar=identity):
    self.account=deepcopy(self.fixture)
    need=sum(x['upgradeFragment'] for x in tables['avatarstardata'] if x['avatarID']==identity and x['star']<meta['unlockStar'])
    self.locked(identity,need+3)
    old=len(self.account['weapon_list'])
    self.assertEqual(self.request(self.c,'AvatarStarUpReq',dict(avatar_id=identity))['retcode'],0)
    av=next(x for x in self.account['avatar_list'] if x['avatar_id']==identity)
    self.assertEqual((av['star'],av['fragment']),(meta['unlockStar'],3))
    self.assertEqual(len(self.account['weapon_list']),old+1)
    weapon=next(w for w in self.account['weapon_list'] if w['unique_id']==av['weapon_unique_id'])
    self.assertEqual(weapon['id'],meta['initialWeapon'])
 def test_insufficient_and_repeat_request_are_atomic(self):
  for identity in [201,301]:
   self.account=deepcopy(self.fixture);self.locked(identity,9);before=deepcopy(self.account)
   self.assertNotEqual(self.request(self.c,'AvatarStarUpReq',dict(avatar_id=identity))['retcode'],0);self.assertEqual(before,self.account)
   self.locked(identity,10);self.assertEqual(self.request(self.c,'AvatarStarUpReq',dict(avatar_id=identity))['retcode'],0)
   before=deepcopy(self.account);self.assertNotEqual(self.request(self.c,'AvatarStarUpReq',dict(avatar_id=identity))['retcode'],0);self.assertEqual(before,self.account)
 def test_equipment_precedes_avatar_unlock_snapshot(self):
  self.assertEqual(self.request(self.c,'AvatarStarUpReq',dict(avatar_id=201))['retcode'],0)
  packets=self.c.notification_snapshot(self.account,201,equipment_first=True)
  self.assertEqual([x[0] for x in packets],['GetEquipmentDataRsp','GetAvatarDataRsp'])
  self.assertEqual(packets[1][1]['avatar_list'][0]['avatar_id'],201)
 def test_story_claim_without_fragment_unlock_preserves_ten_fragments(self):
  for identity in [10004,10005]:self.assertEqual(self.request(self.m,'GetMissionRewardReq',dict(mission_id=identity))['retcode'],0)
  av=next(x for x in self.account['avatar_list'] if x['avatar_id']==201)
  self.assertEqual((av['star'],av['fragment']),(1,10))
 def test_story_claim_after_fragment_unlock_converts_card_once(self):
  self.assertEqual(self.request(self.c,'AvatarStarUpReq',dict(avatar_id=201))['retcode'],0)
  weapons=deepcopy(self.account['weapon_list'])
  for identity in [10004,10005]:self.assertEqual(self.request(self.m,'GetMissionRewardReq',dict(mission_id=identity))['retcode'],0)
  av=next(x for x in self.account['avatar_list'] if x['avatar_id']==201)
  self.assertEqual((av['star'],av['fragment']),(1,7));self.assertEqual(self.account['weapon_list'],weapons)
  before=deepcopy(self.account);self.assertNotEqual(self.request(self.m,'GetMissionRewardReq',dict(mission_id=10005))['retcode'],0);self.assertEqual(before,self.account)

if __name__=='__main__':unittest.main()
