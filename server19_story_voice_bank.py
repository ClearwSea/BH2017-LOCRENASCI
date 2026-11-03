"""Real reference voice media in an original113-format, PCM sound bank.

No later HIRC layouts are copied. Event/action/sound/mixer templates are from
the original APK; media is decoded to standard PCM to avoid codec-version ABI.
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
import hashlib
import json
import struct
import subprocess
import wave
from server19_story_voice_audit import event_hash
from server19_story_all_resources import WORK, ROOT

OUT = WORK/'act2-batch-failures-v1'
SOURCE = ROOT/'7.0-HONKAI3-OFFLINE/BH3/BH3_Data/StreamingAssets/Audio/GeneratedSoundBanks/Windows/AUDIO_Main_Story_1_CN_0.pck'
TOOL = ROOT/'.local-baseline/server19-dev/story-voice-tools/vgmstream-cli.exe'
NAME = 'server19_story_voice'


def chunks(raw):
    result = {}; pos = 0
    while pos < len(raw):
        kind, size = struct.unpack_from('<4sI', raw, pos)
        result[kind] = raw[pos+8:pos+8+size]; pos += 8 + size
    assert pos == len(raw)
    return result


def objects(hirc):
    result = {}; pos = 4
    for _ in range(struct.unpack_from('<I', hirc)[0]):
        kind = hirc[pos]; size = struct.unpack_from('<I', hirc, pos+1)[0]
        data = hirc[pos+5:pos+5+size]
        identity = struct.unpack_from('<I', data)[0]
        assert identity not in result
        result[identity] = (kind, data); pos += 5 + size
    assert pos == len(hirc)
    return result


def u(value): return struct.pack('<I', value)


def order_streaming_voice_bank(raw):
    """Keep sound children before their actor/mixer, as in the original template.

    Merging new sounds after an existing actor must not leave forward child
    references in its serialized child list. Object payloads remain exact.
    """
    bank = chunks(raw)
    assert set(bank) == {b'BKHD', b'HIRC'}
    entries = objects(bank[b'HIRC'])
    ordered = [v for v in entries.values() if v[0] != 7]
    ordered += [v for v in entries.values() if v[0] == 7]
    hirc = u(len(ordered)) + b''.join(bytes([k])+u(len(v))+v for k,v in ordered)
    assert objects(hirc) == entries
    return b''.join(k+u(len(v))+v for k,v in ((b'BKHD',bank[b'BKHD']),(b'HIRC',hirc)))


def pcm_wem(wav):
    """Wrap unchanged PCM frames in legacy Wwise PCMEX channel metadata."""
    assert wav[:4] == b'RIFF' and wav[8:12] == b'WAVE'
    source = chunks(wav[12:])
    tag, channels, rate, average, align, bits = struct.unpack('<HHIIHH', source[b'fmt '])
    assert tag == 1 and bits == 16 and channels in (1, 2)
    assert align == channels * 2 and average == rate * align
    fmt = struct.pack('<HHIIHHHHI', 0xfffe, channels, rate, average,
                      align, bits, 6, 0, 4 if channels == 1 else 3)
    body = b'WAVE' + b'fmt ' + u(len(fmt)) + fmt + b'data' + u(len(source[b'data'])) + source[b'data']
    return b'RIFF' + u(len(body)) + body


def build(*, reuse_bank=None):
    target_rows = json.loads((OUT/'voice-targets.json').read_bytes())['dialogs']
    targets = {event_hash(r['audioID']):r['audioID'] for r in target_rows if r['audioID']}
    media = {}; evidence = []
    if reuse_bank is not None:
        reuse_bank = Path(reuse_bank)
        previous = json.loads((reuse_bank.parent/'voice-bank-report.json').read_bytes())
        assert Path(previous['source']).resolve() == SOURCE.resolve()
        prior_evidence = {r['event']:r for r in previous['events']}
        prior = chunks(reuse_bank.read_bytes()); prior_objects = objects(prior[b'HIRC'])
        prior_index = {i:(off,n) for i,off,n in struct.iter_unpack('<III',prior[b'DIDX'])}
        for key in targets.keys() & prior_objects.keys():
            kind,event = prior_objects[key]; assert kind==4 and len(event)==12
            action = prior_objects[struct.unpack_from('<I',event,8)[0]][1]
            sound = prior_objects[struct.unpack_from('<I',action,6)[0]][1]
            off,size = prior_index[struct.unpack_from('<I',sound,9)[0]]
            media[key] = prior[b'DATA'][off:off+size]
            evidence.append(prior_evidence[targets[key]])
        del prior,prior_objects
    pcm = OUT/'voice-media'; pcm.mkdir(exist_ok=True)
    with SOURCE.open('rb') as source:
        head = source.read(28); assert head[:4] == b'AKPK'
        source.seek(28 + struct.unpack_from('<I', head, 12)[0])
        entries = [struct.unpack('<5I', source.read(20)) for _ in range(struct.unpack('<I', source.read(4))[0])]
        for bank, block, size, offset, language in entries:
            if language != 1: continue
            start = block*offset; pos = 0; hirc = None
            while pos < size:
                source.seek(start+pos); kind, length = struct.unpack('<4sI', source.read(8))
                if kind == b'HIRC': hirc = source.read(length)
                pos += 8 + length
            if hirc is None: continue
            obj = objects(hirc); selected = (set(obj) & set(targets)) - set(media)
            if not selected: continue
            source.seek(start); bank_raw = source.read(size); ch = chunks(bank_raw)
            didx = {i:(off,n) for i,off,n in struct.iter_unpack('<III',ch[b'DIDX'])}
            for key in selected:
                name = targets[key]; kind,event = obj[key]
                assert kind == 4 and len(event) == 9 and event[4] == 1
                action_key = struct.unpack_from('<I',event,5)[0]; kind,action = obj[action_key]
                assert kind == 3 and len(action) == 18 and action[4:6] == b'\x03\x04'
                sound_key = struct.unpack_from('<I',action,6)[0]; kind,sound = obj[sound_key]
                assert kind == 2 and sound[8] == 0
                source_media = struct.unpack_from('<I',sound,9)[0]; off,length = didx[source_media]
                payload = ch[b'DATA'][off:off+length]; assert payload[:4] == b'RIFF'
                wem = pcm/(name+'.wem'); wav = pcm/(name+'.wav'); wem.write_bytes(payload)
                run = subprocess.run([str(TOOL),'-i','-o',str(wav),str(wem)],capture_output=True,text=True,timeout=60)
                assert run.returncode == 0, run.stderr
                with wave.open(str(wav)) as audio:
                    assert audio.getsampwidth() == 2 and audio.getnchannels() in (1,2)
                    samples = audio.readframes(audio.getnframes())
                    assert any(samples), 'Silent decoded media'
                    duration = audio.getnframes()/audio.getframerate()
                    channels,rate = audio.getnchannels(),audio.getframerate()
                # vgmstream WAV contains the decoder's original PCM frames.
                data = wav.read_bytes(); fmt = chunks(data[12:])[b'fmt ']
                assert struct.unpack_from('<H',fmt)[0] == 1
                media[key] = pcm_wem(data)
                evidence.append({'event':name,'event_id':key,'source_bank':bank,'source_sound':sound_key,
                    'source_media':source_media,'source_wem_sha256':hashlib.sha256(payload).hexdigest(),
                    'pcm_sha256':hashlib.sha256(data).hexdigest(),'seconds':duration,'channels':channels,'rate':rate})
    assert set(media) == set(targets), sorted(set(targets)-set(media))
    original = chunks((OUT/'original-dialog-bank.bnk').read_bytes())
    assert struct.unpack_from('<I',original[b'BKHD'])[0] == 113
    template = objects(original[b'HIRC'])
    event = template[event_hash('VO_Dialog_1')][1]
    action = template[struct.unpack_from('<I',event,8)[0]][1]
    sound = template[struct.unpack_from('<I',action,6)[0]][1]
    assert len(sound) == 46 and struct.unpack_from('<I',sound,4)[0] == 0x40001
    parent_id = struct.unpack_from('<I',sound,25)[0]
    parent = template[parent_id][1]
    root_id = struct.unpack_from('<I',parent,11)[0]
    root = template[root_id][1]
    assert len(parent) == 76 and len(root) == 62 and struct.unpack_from('<I',parent,32)[0] == 10
    bank_id, actor_id, mixer_id = [event_hash(NAME+x) for x in ('','_actor','_mixer')]
    didx = bytearray(); data = bytearray(); records = []; sounds = []
    for key in sorted(media):
        event_name = targets[key]; mid = event_hash(event_name+'_server19_media')
        sid,aid = event_hash(event_name+'_server19_sound'),event_hash(event_name+'_server19_action')
        sounds.append(sid)
        data.extend(bytes((-len(data))%16)); didx.extend(struct.pack('<III',mid,len(data),len(media[key])));data.extend(media[key])
        value = bytearray(sound)
        value[0:4]=u(sid);value[4:8]=u(0x10001);value[9:13]=u(mid)
        value[13:17]=u(len(media[key]));value[25:29]=u(actor_id)
        records.append((2,bytes(value)))
        value = bytearray(action);value[0:4]=u(aid);value[6:10]=u(sid);value[14:18]=u(bank_id)
        records.extend(((3,bytes(value)),(4,struct.pack('<III',key,1,aid))))
    value=bytearray(parent[:32]);value[0:4]=u(actor_id);value[11:15]=u(mixer_id)
    value.extend(u(len(sounds))+b''.join(map(u,sounds)));records.append((7,bytes(value)))
    value=bytearray(root);value[0:4]=u(mixer_id);assert value[58:62]==u(parent_id);value[58:62]=u(actor_id);records.append((7,bytes(value)))
    hirc=u(len(records))+b''.join(bytes([kind])+u(len(value))+value for kind,value in records)
    header=bytearray(original[b'BKHD']);header[4:8]=u(bank_id)
    result=b''.join(kind+u(len(value))+value for kind,value in ((b'BKHD',header),(b'DIDX',didx),(b'DATA',data),(b'HIRC',hirc)))
    final=OUT/(NAME+'.bnk');final.write_bytes(result)
    verify=objects(chunks(result)[b'HIRC']);assert all(verify[k][0]==4 for k in targets)
    report={'status':'prepared_human_pending','source':str(SOURCE),'source_version':'reference7.0_not_proven_historical1.9',
            'bank_version':113,'codec':'PCM16, decoded real reference media','bank_name':NAME,'bank_id':bank_id,
            'bytes':len(result),'events':evidence,'no_generated_voice':True,'native_playback_pending':True}
    (OUT/'voice-bank-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'voices':len(media),'bytes':len(result),'output':str(final)}))


if __name__ == '__main__': build()
