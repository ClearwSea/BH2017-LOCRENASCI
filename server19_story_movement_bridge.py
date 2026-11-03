"""Move a reviewed fixed acceleration into original typed ability parameters."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import struct
from server19_story_shield_bridge import ShieldClosure
import server19_chapter1_resources as ch
import server19_avatar_battle_resources as batch
from server19_arm_lock_acceleration import KEY,STATE


class MovementClosure(ShieldClosure):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.schema.native_lock_acceleration_bridge=True

    def project(self,identity):
        visited=identity in self.records or identity in self.errors
        super().project(identity)
        if visited or identity in self.errors:return
        record=self.records[identity]
        values=[r for r in record['adaptations'] if r['operation']=='native_lock_acceleration_parameter']
        if not values:return
        try:
            if len(values)!=1 or not values[0]['path'].startswith('ability.AbilityMixins['):
                raise ValueError('Only one direct root lock-forward mixin has an isolated speed-state namespace')
            left,right=self.spans[identity];old=self.changes.get(identity,self.data[left:right])
            reader=ch.ChapterReader(old,self.strings,self.schema,True);root=reader.class_value(batch.ability.ABILITY,'ability')
            special=root['children'][4];items={r['key']:r for r in special.get('custom_items',[])}
            added=[]
            for key,encoded in ((KEY,values[0]['float_hex']),(STATE,'ca00000000')):
                if key in items:
                    q=batch.baked.MessagePackSpanReader(old);q.pos=items[key]['source_byte_span'][0]
                    q.node();dtype=q.node();value=q.node()
                    if ch.scalar(old,dtype)!=2 or old[value['start']:value['end']].hex()!=encoded:raise ValueError('Existing movement parameter differs')
                    continue
                if key not in self.strings:self.strings.append(key)
                added.append(batch.ability.integer_bytes(self.strings.index(key))+b'\x02'+bytes.fromhex(encoded))
            count=(0 if special['code']==0xc0 else special['count'])+len(added)
            head=bytes([0x80+count]) if count<16 else b'\xde'+struct.pack('>H',count)
            body=b'' if special['code']==0xc0 else old[special['header_end']:special['end']]
            value=old[:special['start']]+head+body+b''.join(added)+old[special['end']:]
            check=ch.ChapterReader(value,self.strings,self.schema,True);check.class_value(batch.ability.ABILITY,'ability')
            assert check.pos==len(value) and set(reader.leaves)==set(check.leaves)
            assert all(p=='ability.AbilitySpecials' or check.leaves[p]['sha256']==v['sha256'] for p,v in reader.leaves.items())
            self.changes[identity]=value;record.update(native_lock_acceleration=values,after_sha256=ch.monsters.sha(value),
                operation='source_acceleration_preserved_as_native_Special',retained_terminals_equal_except_explicit_acceleration_Specials=True)
            path=self.output/f'overlays/ability/{identity[0]}-{identity[1] if identity[1] is not None else "default"}.bin'
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            record['overlay']={'path':path.relative_to(self.output).as_posix(),'local_absolute_path':str(path.resolve()),
                               'bytes':len(value),'sha256':ch.monsters.sha(value)}
        except (ValueError,KeyError,IndexError) as err:self.errors[identity]=str(err);record['blocker']=str(err)
