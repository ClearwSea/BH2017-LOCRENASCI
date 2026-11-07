"""Restore AuroraBlow's original 1.9 split animation slots; offline candidate."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import json,struct,zipfile,hashlib
from pathlib import Path
import server19_avatar_battle_resources as b
import server19_story_batch_resources as story
import server19_resources as res
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'server19-run/triumph-weapon-20261027'
def integer(v):return bytes([v]) if v<128 else b'\xcd'+struct.pack('>H',v)
def build():
 strings=(OUT/'stringmap.txt').read_text(encoding='utf-8').split('\x1f');old_strings=list(strings)
 names=['Excalibur_StandBy','Excalibur_Combat','AuxObject/OverrideClips/Override_Himeko1/Avatar_Himeko_Ani_Weapon_Excalibur_Combat']
 for name in names:
  if name not in strings:strings.append(name)
 before=(OUT/'bakedabilitydata').read_bytes();_,_,_,d,_,sp=b.packed(before);identity=(strings.index('Equip_Pt1_Claymore_AuroraBlow'),None);l,r=sp[identity]
 with zipfile.ZipFile(res.DEFAULT24) as z:
  schema=b.BattleSchema(z,strings);rd=b.BattleReader(d,strings,schema,True);rd.pos=l;rd.class_value(b.ability.ABILITY,'ability');assert rd.pos==r
  q=b.baked.MessagePackSpanReader(d);q.pos=l;root=q.node()
  # Resolve the mixin-array position from the original declared class fields.
  fields=[k for k,t in schema.members(b.ability.ABILITY,True)];mix=root['children'][fields.index('AbilityMixins')]
  assert mix['count']==3
  # Polymorphic mixins append configLocalID outside the MessagePack union.
  ends=[rd.leaves[f'ability.AbilityMixins[{i}].configLocalID']['span'][1] for i in range(3)]
  mix['children']=[dict(start=start,end=end) for start,end in zip([mix['start']+1]+ends[:2],ends)]
  mix['end']=ends[-1]
  def rewrite(node,replacements):
   raw=d[node['start']:node['end']];edits=[]
   for path,val in replacements.items():
    left,right=rd.leaves[path]['span'];assert node['start']<=left<right<=node['end'];edits.append((left-node['start'],right-node['start'],integer(val)))
   for left,right,value in sorted(edits,reverse=True):raw=raw[:left]+value+raw[right:]
   return raw
  pre='ability.AbilityMixins[0]<MoleMole.Config.AnimatorOverrideControllerMixin>.Override.'
  assert strings[b.baked.decode_integer(d,root['children'][0])]=='Equip_Pt1_Claymore_AuroraBlow'
  standby=rewrite(mix['children'][0],{pre+'OverrideClipName':strings.index(names[0])})
  combat=rewrite(mix['children'][0],{pre+'OverrideClipName':strings.index(names[1]),pre+'ClipContainerPath':strings.index(names[2]),'ability.AbilityMixins[0].configLocalID':9})
  state='ability.AbilityMixins[1]<MoleMole.Config.AttachAnimatorEventPatternToAnimatorStatesMixin>.AnimatorStates[0]'
  event_standby=rewrite(mix['children'][1],{state:strings.index(names[0])})
  event_combat=rewrite(mix['children'][1],{state:strings.index(names[1]),'ability.AbilityMixins[1].configLocalID':10})
  m2=mix['children'][2];replacement=b'\x95'+standby+combat+event_standby+event_combat+d[m2['start']:m2['end']]
  value=d[l:mix['start']]+replacement+d[mix['end']:r]
  check=b.BattleReader(value,strings,schema,True);check.class_value(b.ability.ABILITY,'ability');assert check.pos==len(value)
 after=story.reassemble(before,{identity:value});_,_,_,nd,_,ns=b.packed(after)
 for k,(start,end) in sp.items():
  nl,nr=ns[k];assert nd[nl:nr]==(value if k==identity else d[start:end])
 # String IDs already used by every deployed container remain stable.
 assert strings[:len(old_strings)]==old_strings
 candidate=OUT/'candidate';candidate.mkdir(exist_ok=True);(candidate/'bakedabilitydata').write_bytes(after);(candidate/'stringmap.txt').write_text('\x1f'.join(strings),encoding='utf-8')
 report=dict(status='PASS_original_reader_and_unselected_bytes',source_sha256=hashlib.sha256(before).hexdigest(),ability_sha256=hashlib.sha256(after).hexdigest(),stringmap_sha256=hashlib.sha256((candidate/'stringmap.txt').read_bytes()).hexdigest(),added_strings=names,changed_ability=identity[0],changed_roots=1,original_root_count=len(sp),old_string_ids_preserved=True,damage_and_modifiers_unchanged=True,deployed=False,human_acceptance='pending')
 (OUT/'repair-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':build()
