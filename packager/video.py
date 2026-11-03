"""Convert supplied 7.x USM files and import explicitly declared missing media."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
from .core import BuildError, read_json


def plan(resources7x, tables, extra_videos=None):
    paths = {p.stem.lower(): p for p in (resources7x / 'Video').glob('*.usm')}
    names = sorted({r['CgPath'] for r in read_json(tables / 'cgdata')} - {'start', 'Story_01'})
    result, missing = [], []
    for name in names:
        candidates = [paths[name.lower()]] if name.lower() in paths else []
        if not candidates:
            candidates = [paths[name.lower() + '_' + str(i)] for i in (1, 2, 3) if name.lower() + '_' + str(i) in paths]
        if not candidates and name[-2:] in ('_1', '_2', '_3') and name[:-2].lower() in paths:
            candidates = [paths[name[:-2].lower()]]
        supplied = extra_videos / (name + '.mp4') if extra_videos else None
        if len(candidates) == 1:
            result.append({'name': name + '.mp4', 'source': candidates[0], 'mode': 'usm-conversion'})
        elif not candidates and supplied is not None and supplied.is_file():
            result.append({'name': name + '.mp4', 'source': supplied, 'mode': 'explicit-extra-video'})
        else:
            missing.append(name + '.mp4')
    if missing:
        raise BuildError('Supplied 7.x input lacks required CG media; provide extra_videos explicitly: ' + ', '.join(missing))
    return result


def prepare(resources7x, tables, ffmpeg, output, logs, extra_videos=None, jobs=4):
    items = plan(resources7x, tables, extra_videos)
    output.mkdir(parents=True, exist_ok=False)
    logs.mkdir(parents=True, exist_ok=True)
    def convert(item):
        target = output / item['name']
        if item['mode'] == 'explicit-extra-video':
            shutil.copyfile(item['source'], target)
            return
        with (logs / (item['name'] + '.log')).open('w', encoding='utf-8') as log:
            run = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-n',
                '-i', str(item['source']), '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '192k', '-sn', '-dn', '-movflags', '+faststart', str(target)],
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            raise BuildError('Video conversion failed; inspect ' + item['name'] + '.log')
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        for count, _ in enumerate(executor.map(convert, items), 1):
            if count % 12 == 0:
                print('[videos] %d/%d' % (count, len(items)), flush=True)
    version = ''.join('Video/' + item['name'] + '\t1\n' for item in items)
    (output / 'Version.txt').write_text(version, encoding='utf-8')
    return {'videos': len(items), 'converted': sum(i['mode'] == 'usm-conversion' for i in items),
            'extra_videos': [i['name'] for i in items if i['mode'] == 'explicit-extra-video']}
