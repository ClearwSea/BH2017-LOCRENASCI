"""Prepare original113 streaming sounds with external, unchanged PCM WEM files.

Original Android libAkSoundEngine contains the %u.wem filename formatter.
SourceType2 and absent bank DATA media IDs are present in original113 banks.
Native playback/IO remains pending device acceptance; embedded source is kept.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import json
import struct
import hashlib
import os
from server19_story_voice_bank import chunks, objects, u


def prepare(source, output, *, reuse_media_dir=None):
    source, output = Path(source), Path(output)
    output.mkdir(exist_ok=False)
    bank = chunks(source.read_bytes())
    assert struct.unpack_from('<I', bank[b'BKHD'])[0] == 113
    index = {mid:(off,size) for mid,off,size in struct.iter_unpack('<III',bank[b'DIDX'])}
    records, files = [], []
    for identity,(kind,raw) in objects(bank[b'HIRC']).items():
        if kind==2:
            assert len(raw)==46 and raw[8]==0
            mid=struct.unpack_from('<I',raw,9)[0];off,size=index[mid]
            media=bank[b'DATA'][off:off+size]
            assert len(media)==size and media[:4]==b'RIFF'
            path=output/(str(mid)+'.wem')
            reuse=Path(reuse_media_dir)/path.name if reuse_media_dir else None
            if reuse is not None and reuse.is_file() and reuse.stat().st_size==size and hashlib.sha256(reuse.read_bytes()).digest()==hashlib.sha256(media).digest():
                os.link(reuse,path)  # immutable prepared media; no repeated copy
            else:path.write_bytes(media)
            value=bytearray(raw)
            value[8]=2  # original113 streaming SourceType, same PCM plugin
            # Pure external streams have no bank-resident media. Keeping the
            # embedded length here makes LoadBank seek missing DATA bytes.
            value[13:17]=u(0)
            value[17]&=~1  # base-path files, no language subdirectory
            assert value[:8]==raw[:8] and value[9:13]==raw[9:13] and value[18:]==raw[18:]
            raw=bytes(value)
            files.append({'media_id':mid,'filename':path.name,'bytes':size,
                          'sha256':hashlib.sha256(media).hexdigest()})
        records.append((kind,raw))
    hirc=u(len(records))+b''.join(bytes([k])+u(len(v))+v for k,v in records)
    # No bank-resident media: omit media chunks instead of asking the legacy
    # loader to allocate/register an empty DATA section.
    result=b''.join(k+u(len(v))+v for k,v in ((b'BKHD',bank[b'BKHD']), (b'HIRC',hirc)))
    dest=output/'server19_story_voice.bnk';dest.write_bytes(result)
    final=objects(chunks(result)[b'HIRC'])
    assert {i for i,(t,v) in final.items() if t==4}=={i for i,(t,v) in objects(bank[b'HIRC']).items() if t==4}
    assert len(files)==len(index)
    report={'status':'prepared_native_streaming_IO_pending','embedded_source':str(source.resolve()),
            'bank_bytes':len(result),'media_bytes':sum(r['bytes'] for r in files),'media_count':len(files),
            'all_PCM_WEM_bytes_unchanged':True,'streaming_source_type':2,
            'bank_resident_media_bytes':0,
            'base_path_language_subdirectory':False,'files':files,'human_acceptance':'pending'}
    (output/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');a=p.parse_args()
    r=prepare(a.source,a.output)
    print(json.dumps({k:r[k] for k in ('status','bank_bytes','media_bytes','media_count')}))
