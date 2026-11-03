"""Convert selected 7.x voice media to the original Android Wwise format."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import struct
import subprocess
import zipfile
from .core import ROOT, BuildError, read_json


def u(value):
    return struct.pack('<I', value)


def event_hash(value):
    result = 2166136261
    for byte in value.lower().encode():
        result = ((result * 16777619) ^ byte) & 0xffffffff
    return result


def chunks(raw):
    output = {}
    pos = 0
    while pos < len(raw):
        kind, size = struct.unpack_from('<4sI', raw, pos)
        output[kind] = raw[pos + 8:pos + 8 + size]
        pos += 8 + size
    if pos != len(raw):
        raise BuildError('Malformed sound bank chunks')
    return output


def objects(raw):
    output = {}
    pos = 4
    for _ in range(struct.unpack_from('<I', raw)[0]):
        kind, size = struct.unpack_from('<BI', raw, pos)
        value = raw[pos + 5:pos + 5 + size]
        output[struct.unpack_from('<I', value)[0]] = (kind, value)
        pos += 5 + size
    return output


def pck_entries(stream):
    head = stream.read(28)
    if head[:4] != b'AKPK':
        raise BuildError('Unsupported Wwise package')
    stream.seek(28 + struct.unpack_from('<I', head, 12)[0])
    count = struct.unpack('<I', stream.read(4))[0]
    return [struct.unpack('<5I', stream.read(20)) for _ in range(count)]


def voice_index(resources7x, required):
    folder = resources7x / 'Audio/GeneratedSoundBanks/Windows'
    files = sorted(folder.glob('*.pck'), key=lambda p: ('_CN' not in p.name, p.name))
    found = {}
    for path in files:
        if '_JP' in path.name:
            continue
        with path.open('rb') as stream:
            for _, block, size, offset, language in pck_entries(stream):
                if language != 1:
                    continue
                start, pos, hirc, didx, data_offset = block * offset, 0, None, None, None
                while pos < size:
                    stream.seek(start + pos)
                    kind, length = struct.unpack('<4sI', stream.read(8))
                    if kind == b'HIRC':
                        hirc = stream.read(length)
                    elif kind == b'DIDX':
                        didx = {i: (off, n) for i, off, n in struct.iter_unpack('<III', stream.read(length))}
                    elif kind == b'DATA':
                        data_offset = start + pos + 8
                    pos += 8 + length
                if hirc is None:
                    continue
                records = objects(hirc)
                selected = (set(records) & required) - set(found)
                for identity in selected:
                    kind, event = records[identity]
                    if kind != 4 or len(event) != 9 or event[4] != 1:
                        raise BuildError('Unsupported voice event layout: ' + str(identity))
                    _, action = records[struct.unpack_from('<I', event, 5)[0]]
                    _, sound = records[struct.unpack_from('<I', action, 6)[0]]
                    media = struct.unpack_from('<I', sound, 9)[0]
                    if didx is None or data_offset is None or media not in didx:
                        raise BuildError('Voice media is not embedded in the supplied bank')
                    off, count = didx[media]
                    found[identity] = (path, data_offset + off, count)
        if set(found) == required:
            break
    missing = required - set(found)
    if missing:
        raise BuildError('7.x voice resources are missing %d required events: %s' % (len(missing), sorted(missing)[:8]))
    return found


def original_templates(client19):
    import io
    with zipfile.ZipFile(client19) as package:
        raw = package.read('assets/Audio/GeneratedSoundBanks/Android/AUDIO_Default.pck')
    stream = io.BytesIO(raw)
    for _, block, size, offset, _ in pck_entries(stream):
        bank = chunks(raw[block * offset:block * offset + size])
        if b'HIRC' not in bank:
            continue
        records = objects(bank[b'HIRC'])
        if event_hash('VO_Dialog_1') not in records:
            continue
        event = records[event_hash('VO_Dialog_1')][1]
        action = records[struct.unpack_from('<I', event, 8)[0]][1]
        sound = records[struct.unpack_from('<I', action, 6)[0]][1]
        parent = records[struct.unpack_from('<I', sound, 25)[0]][1]
        root = records[struct.unpack_from('<I', parent, 11)[0]][1]
        return bank[b'BKHD'], action, sound, parent, root
    raise BuildError('Original sound bank template is missing')


def pcm_wem(raw):
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise BuildError('Decoder did not produce WAV')
    parts = chunks(raw[12:])
    tag, channels, rate, average, align, bits = struct.unpack_from('<HHIIHH', parts[b'fmt '])
    if tag != 1 or bits != 16 or channels not in (1, 2):
        raise BuildError('Decoder did not produce PCM16')
    fmt = struct.pack('<HHIIHHHHI', 0xfffe, channels, rate, average, align, bits, 6, 0, 4 if channels == 1 else 3)
    body = b'WAVEfmt ' + u(len(fmt)) + fmt + b'data' + u(len(parts[b'data'])) + parts[b'data']
    return b'RIFF' + u(len(body)) + body


def prepare(client19, resources7x, decoder, output, scratch, jobs=4):
    events = read_json(ROOT / 'rules/voice-events.json')['events']
    selected = voice_index(resources7x, {r['event_id'] for r in events})
    output.mkdir(parents=True, exist_ok=False)
    scratch.mkdir(parents=True, exist_ok=False)
    def convert(row):
        identity, media = row['event_id'], row['media_id']
        source, offset, count = selected[identity]
        compressed = scratch / (str(identity) + '.wem')
        wave = scratch / (str(identity) + '.wav')
        with source.open('rb') as stream:
            stream.seek(offset)
            compressed.write_bytes(stream.read(count))
        run = subprocess.run([str(decoder), '-i', '-o', str(wave), str(compressed)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            raise BuildError('Voice decode failed: ' + str(identity))
        (output / (str(media) + '.wem')).write_bytes(pcm_wem(wave.read_bytes()))
        compressed.unlink()
        wave.unlink()
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for count, _ in enumerate(executor.map(convert, events), 1):
            if count % 200 == 0:
                print('[voices] %d/%d' % (count, len(events)), flush=True)
    header, action, sound, parent, root = original_templates(client19)
    bank_id = event_hash('server19_story_voice')
    actor_id, mixer_id = event_hash('server19_story_voice_actor'), event_hash('server19_story_voice_mixer')
    records, sound_ids = [], []
    for row in events:
        sid, aid = row['sound_id'], row['action_id']
        sound_ids.append(sid)
        value = bytearray(sound)
        value[0:4], value[4:8], value[9:13] = u(sid), u(0x10001), u(row['media_id'])
        value[8], value[13:17], value[25:29] = 2, u(0), u(actor_id)
        value[17] &= ~1
        records.append((2, bytes(value)))
        value = bytearray(action)
        value[0:4], value[6:10], value[14:18] = u(aid), u(sid), u(bank_id)
        records.extend(((3, bytes(value)), (4, struct.pack('<III', row['event_id'], 1, aid))))
    value = bytearray(parent[:32])
    value[0:4], value[11:15] = u(actor_id), u(mixer_id)
    value.extend(u(len(sound_ids)) + b''.join(map(u, sound_ids)))
    records.append((7, bytes(value)))
    value = bytearray(root)
    value[0:4], value[58:62] = u(mixer_id), u(actor_id)
    records.append((7, bytes(value)))
    hirc = u(len(records)) + b''.join(bytes([kind]) + u(len(value)) + value for kind, value in records)
    header = bytearray(header)
    header[4:8] = u(bank_id)
    (output / 'server19_story_voice.bnk').write_bytes(b'BKHD' + u(len(header)) + header + b'HIRC' + u(len(hirc)) + hirc)
    return len(events)
