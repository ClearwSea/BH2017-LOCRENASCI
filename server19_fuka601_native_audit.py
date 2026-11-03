"""Inspect actual 1.9/2.0/2.4 Fuka runtime gaps without deploying anything."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import argparse
import json
import struct
import zipfile
from pathlib import Path
import analyze19 as original
import server19_resources as resources

ROOT=Path(__file__).resolve().parent


def metadata_rows(blob, old=False):
    if old:
        if blob!=original.B:
            raise ValueError('Original APK metadata differs from the pinned 1.9 input')
        return original.string,original.type_name,original.T,original.M
    header=struct.unpack_from('<64I',blob)
    def string(index):
        start=header[6]+index
        return blob[start:blob.index(0,start)].decode('utf-8')
    size,fmt=(120,'<24I8H2I') if old else (104,'<20I8H2I')
    types=[struct.unpack_from(fmt,blob,header[40]+i)
           for i in range(0,header[41],size)]
    methods=[struct.unpack_from('<12I4H',blob,header[12]+i)
             for i in range(0,header[13],56)]
    def typename(index):
        row=types[index]
        return '.'.join(x for x in (string(row[1]),string(row[0])) if x)
    return string,typename,types,methods


def audit(output):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError('Use a fresh workspace evidence directory')
    output.mkdir(parents=True)
    versions={
        '1.9':resources.DEFAULT19,
        '2.0':ROOT/'.local-baseline/original-apks/bh3-2.0-original-reference.apk',
        '2.4':resources.DEFAULT24,
    }
    rows={}
    for version,package in versions.items():
        with zipfile.ZipFile(package) as archive:
            blob=archive.read('assets/bin/Data/Managed/Metadata/global-metadata.dat')
        string,typename,types,methods=metadata_rows(blob,old=version=='1.9')
        names={typename(i) for i in range(len(types))}
        relevant=[{'index':i,'owner':typename(m[1]),'name':string(m[0]),'native_index':m[6]}
                  for i,m in enumerate(methods)
                  if typename(m[1]) in ('MoleMole.MonoFuka',
                     'MoleMole.AbilityAvatarSkillButtonHoldModeExMixin')
                  or typename(m[1])=='MoleMole.AvatarActor' and
                     string(m[0]) in ('SetAttackButtonHoldMode','SetSkillButtonHoldMode',
                                      'IsSkillButtonHoldMode')]
        rows[version]={
            'package':str(package),'methods':relevant,
            'hold_ex_config':'MoleMole.Config.AvatarSkillButtonHoldModeExMixin' in names,
            'restrict_damage_config':'MoleMole.Config.ModifyDamageTakenWithRestrictMixin' in names,
            'consume_with_property_name_present':b'ConsumeWithProperty\0' in blob,
        }
    assert not rows['1.9']['hold_ex_config'] and rows['2.0']['hold_ex_config']
    assert not any(m['name']=='SetSkillButtonHoldMode' for m in rows['1.9']['methods'])
    assert any(m['name']=='SetSkillButtonHoldMode' for m in rows['2.0']['methods'])
    assert not rows['2.0']['restrict_damage_config']
    assert not rows['2.0']['consume_with_property_name_present']
    assert rows['2.4']['restrict_damage_config']
    # These inspect the stock x86 implementation only. No device diagnostic.
    for mid in (47522,48860,48861):
        (output/(str(mid)+'.asm')).write_text(original.disasm(mid),encoding='utf-8')
    report={'versions':rows,'status':'NATIVE_COMPATIBILITY_BLOCKED',
        'conclusion':'Current 2.4 Fuka data needs later runtime behavior; table omission alone is not the blocker',
        'limits':['Method presence is not a full behavior-equivalence proof',
                  'No later runtime or ability is silently removed or replaced',
                  'No live device, account, service or resource modified']}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.output)
    print(json.dumps({'status':result['status'],'output':str(args.output)}))
