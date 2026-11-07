"""Keep fixed source shield caps as original AbilitySpecials for the ARM hook."""

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
import re
from pathlib import Path
import server19_chapter1_resources as ch
import server19_avatar_battle_resources as batch
import server19_story_all_resources as story
from server19_arm_shield_cap import KEY


class ShieldClosure(story.StoryClosure):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schema.native_shield_cap_bridge = True

    def project(self, identity):
        visited = identity in self.records or identity in self.errors
        super().project(identity)
        if visited or identity in self.errors: return
        record = self.records[identity]
        caps = [r for r in record['adaptations'] if r['operation']=='native_shield_cap_parameter']
        try:
            # Earlier accepted roots already removed their proven nonbinding
            # cap. Recover the cap from the pinned source, not the old output.
            if not caps and identity[0] in (15599,15671):
                l,r = self.source_spans[identity]
                reader = ch.ChapterReader(self.source_data,self.strings,self.schema)
                reader.pos=l;reader.class_value(batch.ability.ABILITY,'ability')
                if reader.pos != r: raise ValueError('Source shield root boundary differs')
                caps=[r for r in reader.records if r['operation']=='native_shield_cap_parameter']
            if not caps: return
            # Both direct and modifier mixins carry the same original
            # instancedAbility pointer. A root-wide Special is exact when
            # every fixed cap in this root has the same value; differing caps
            # still require distinct namespaces and remain blocked.
            if len({r['float_hex'] for r in caps}) != 1:
                raise ValueError('Different caps within one ability cannot share one Special')
            l,r=self.spans[identity];old=self.changes.get(identity,self.data[l:r])
            reader=ch.ChapterReader(old,self.strings,self.schema,True)
            root=reader.class_value(batch.ability.ABILITY,'ability')
            special=root['children'][4]
            existing=next((r for r in special.get('custom_items',[]) if r['key']==KEY),None)
            if existing:
                q=batch.baked.MessagePackSpanReader(old);q.pos=existing['source_byte_span'][0]
                q.node();dtype=q.node();atom=q.node()
                if ch.scalar(old,dtype)!=2 or old[atom['start']:atom['end']].hex()!=caps[0]['float_hex']:
                    raise ValueError('Existing native shield marker differs from source fixed cap')
                record['native_shield_cap']=caps
                return
            if KEY not in self.strings:self.strings.append(KEY)
            item=batch.ability.integer_bytes(self.strings.index(KEY))+b'\x02'+bytes.fromhex(caps[0]['float_hex'])
            if special['code']==0xc0:
                replacement=b'\x81'+item
            else:
                count=special['count']+1
                header=bytes([0x80+count]) if count<16 else b'\xde'+struct.pack('>H',count)
                replacement=header+old[special['header_end']:special['end']]+item
            value=old[:special['start']]+replacement+old[special['end']:]
            check=ch.ChapterReader(value,self.strings,self.schema,True)
            check.class_value(batch.ability.ABILITY,'ability')
            assert check.pos==len(value)
            assert set(check.leaves)==set(reader.leaves)
            assert all(p=='ability.AbilitySpecials' or check.leaves[p]['sha256']==v['sha256'] for p,v in reader.leaves.items())
            self.changes[identity]=value
            record.update(native_shield_cap=caps,after_sha256=ch.monsters.sha(value),
                          operation='source_shield_cap_preserved_as_native_Special',
                          retained_terminals_equal_except_explicit_cap_Special=True)
            path=self.output/f'overlays/ability/{identity[0]}-{identity[1] if identity[1] is not None else "default"}.bin'
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            record['overlay']={'path':path.relative_to(self.output).as_posix(),
                               'local_absolute_path':str(path.resolve()),'bytes':len(value),
                               'sha256':ch.monsters.sha(value)}
        except (ValueError,KeyError,IndexError) as err:
            self.errors[identity]=str(err);record['blocker']=str(err)
