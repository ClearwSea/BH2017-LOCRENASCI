"""Inventory the real original fake-avatar models and constant ability roots."""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
import hashlib
import struct
from pathlib import Path
import server19_avatar_battle_resources as batch
import server19_resources as resources
from server19_stage_monsters import decode_integer


def collect(names, strings, original_map, original):
    raw=batch.AVATARS.read_bytes();data,spans=batch.packed(raw)[3::2];records=[]
    for name in names:
        if not name.startswith('Fake_'):raise ValueError('Unreviewed fake-avatar registry')
        left,right=spans[strings.index(name),None]
        q=batch.baked.MessagePackSpanReader(data);q.pos=left;root=q.node()
        if q.pos!=right or root['count']!=25 or root['children'][8]['count']!=0:
            raise ValueError('Fake avatar must retain original25 layout and no conditional unlock references')
        model='entities/avatar/'+name.lower()+'/avatar_'+name.lower()
        if model not in original_map:raise ValueError('Original fake-avatar model absent: '+model)
        ref=original_map[model];blob=original.read('assets/bin/Data/'+ref['file']);layout=resources.serialized(blob)
        controllers=[]
        for obj in layout['objects'].values():
            if obj['class']!=95:continue
            fid,pid=struct.unpack_from('<iq',blob,obj['offset']+28)
            fn=layout['externals'][fid-1].rsplit('/',1)[-1] if fid else ref['file']
            if fn=='globalgamemanagers.assets':fn='globalgamemanagers'
            controller=resources.serialized(original.read('assets/bin/Data/'+fn))['objects'].get(pid)
            if controller is None or controller['class'] not in (91,221):raise ValueError('Invalid original fake-avatar Animator controller PPtr')
            controllers.append({'file':fn,'path_id':pid,'class':controller['class']})
        if not controllers:raise ValueError('Original fake-avatar Animator missing')
        dependencies=[]
        for value in root['children'][9]['children'][1::2]:
            if value['count']!=2:raise ValueError('Fake-avatar constant ability shape differs')
            key=decode_integer(data,value['children'][0]);variant=None if value['children'][1]['code']==0xc0 else decode_integer(data,value['children'][1])
            if variant is not None and strings[variant]=='Default':variant=None
            dependencies.append((key,variant))
        groups=[]
        for node in root['children'][0]['children'][15]['children']:
            group=strings[decode_integer(data,node)];encoded=group.encode();needle=struct.pack('<I',len(encoded))+encoded
            hits=[]
            for path,entry in original_map.items():
                if path.startswith('effect/data/'):
                    _,payload=resources.object_bytes(original,entry)
                    if needle in payload:hits.append(path)
            if not hits:raise ValueError('Original fake-avatar effect group absent: '+group)
            groups.append({'group':group,'original_paths':hits})
        records.append({'registry':name,'model':model,'original_model':ref,'animator_controllers':controllers,
                        'effect_groups':groups,'dependencies':dependencies,'original25_root_sha256':hashlib.sha256(data[left:right]).hexdigest(),
                        'required_existing_avatar_container_sha256':hashlib.sha256(raw).hexdigest(),
                        'no_dress_override':True,'Normal_SP_path':'original CreateFakeAdhocAvatar66013, three original arguments'})
    return records
