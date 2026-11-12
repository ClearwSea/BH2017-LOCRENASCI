"""Split Windows builder distribution; no game inputs or user data included."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def toolchain_id(source):
    with zipfile.ZipFile(source) as archive:
        rows = sorted((i.filename.split('/tools/', 1)[1], i.file_size, i.CRC)
                      for i in archive.infolist() if '/tools/' in i.filename and not i.is_dir())
    return 'windows-x64-' + hashlib.sha256(encoded(rows)).hexdigest()[:16]


def main_package(app, output, version, tools):
    rows = []
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app.rglob('*')):
            relative = path.relative_to(app)
            if not path.is_file() or '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo'):
                continue
            if any(p in ('.git', 'user-data', 'work', 'inputs', 'dist') for p in relative.parts) or path.suffix in ('.jks', '.keystore'):
                raise ValueError('Source export contains private or generated files: ' + str(relative))
            raw = path.read_bytes()
            name = 'app/' + relative.as_posix()
            rows.append(dict(path=name, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
            archive.writestr(name, raw)
        if 'app/launch_gui.py' not in {r['path'] for r in rows}:
            raise ValueError('Source export is missing launch_gui.py')
        archive.writestr('main-manifest.json', encoded(dict(format='BH2017-main', schema=1,
            version=version, host_api=1, toolchain_id=tools, files=rows)))
    return dict(files=len(rows), bytes=output.stat().st_size)


def copy_member(source, raw, target, item):
    """Preserve existing compressed tool/source/license bytes exactly."""
    info = copy.copy(item)
    if info.flag_bits not in (0, 2048):
        raise ValueError('Unsupported ZIP flags')
    raw.seek(item.header_offset)
    header = struct.unpack('<4s5H3I2H', raw.read(30))
    if header[0] != b'PK\x03\x04': raise ValueError('Invalid ZIP header')
    length = 30 + header[-2] + header[-1] + item.compress_size
    raw.seek(item.header_offset)
    info.header_offset = target.fp.tell()
    while length:
        block = raw.read(min(length, 8 * 1024 * 1024))
        if not block: raise ValueError('Truncated source ZIP')
        target.fp.write(block)
        length -= len(block)
    target.filelist.append(info)
    target.NameToInfo[info.filename] = info
    target._didModify = True
    target.start_dir = target.fp.tell()


def base_package(source, output, host, launcher):
    identity = toolchain_id(source)
    with zipfile.ZipFile(source) as old, source.open('rb') as raw, zipfile.ZipFile(
            output, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as new:
        root = old.infolist()[0].filename.split('/')[0] + '/'
        for item in old.infolist():
            relative = item.filename[len(root):]
            if relative.startswith('app/') or relative in ('app', 'README.md', 'CHANGELOG.md') or relative.endswith('.exe') and '/' not in relative:
                continue
            copy_member(old, raw, new, item)
        new.writestr(root + 'builder_host.py', host.read_bytes())
        new.writestr(root + '构建器.exe', launcher.read_bytes())
        new.writestr(root + 'base-manifest.json', encoded(dict(format='BH2017-base', schema=1,
            host_api=1, toolchain_id=identity)))
        new.writestr(root + 'README.md', '# BH2017-LOCRENASCI 构建器基础包\n\n解压后运行构建器.exe，导入配套构建主包 ZIP，再打开构建界面。工具链不变时只需更新主包。补充资源 ZIP 在构建界面独立选择。user-data 中的设置、日志和签名密钥请妥善保留。\n\nOffline base: import the matching main-package ZIP, then open the build interface. Update only the main package while the toolchain remains compatible. Preserve user-data and its signing keys.\n')
    return dict(toolchain_id=identity, bytes=output.stat().st_size)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--tools-from', type=Path)
    parser.add_argument('--base-manifest', type=Path)
    parser.add_argument('--main-only', action='store_true')
    parser.add_argument('--launcher', type=Path)
    parser.add_argument('--host', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.main_only:
        if not args.base_manifest:
            parser.error('--main-only requires --base-manifest from the reusable base')
        base = json.loads(args.base_manifest.read_bytes())
        if base.get('format') != 'BH2017-base' or base.get('schema') != 1 or base.get('host_api') != 1:
            parser.error('Unsupported base manifest')
        identity = base['toolchain_id']
        result = {}
    else:
        if not all((args.tools_from, args.host, args.launcher)):
            parser.error('Base packaging requires --tools-from, --host and --launcher')
        identity = toolchain_id(args.tools_from)
        result = dict(base=base_package(args.tools_from, args.output / 'BH2017-LOCRENASCI-Builder-Base-Windows-x64.zip', args.host, args.launcher))
    result['main'] = main_package(args.app, args.output / ('BH2017-LOCRENASCI-Builder-Main-v' + args.version + '.zip'), args.version, identity)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
