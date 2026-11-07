"""Load explicitly supplied artwork/media without embedding it in the source."""
from pathlib import Path
import shutil
import stat
import zipfile
from .core import BuildError, read_json, safe_relative

IMAGES = ('bridge/celebration.png', 'bridge/github.png', 'gacha/dracula.png',
          'gacha/ziyuan.png', 'announcement/teaparty.png', 'announcement/update.png', 'launcher/app-icon.png')
VIDEOS = ('ExtraStory_BlackXuanyuan_01.mp4', 'ExtraStory_BlackXuanyuan_02.mp4',
          'ExtraStory_BlackXuanyuan_03.mp4', 'Sakura_4_CG12_SP_mux.mp4',
          'Season_CG01_Final_mux.mp4')
ALLOWED = {'supplements.json', 'README.md'} | {'images/' + n for n in IMAGES} | {'videos/' + n for n in VIDEOS}
PACKAGE_KIND = 'bh2017-locrenasci-external-supplements'
# Keep existing external archives readable when the project's display name changes.
SUPPORTED_KINDS = {PACKAGE_KIND, 'bh3-main-external-supplements'}


def validate(root):
    manifest = read_json(root / 'supplements.json')
    if manifest.get('schema') != 1 or manifest.get('kind') not in SUPPORTED_KINDS:
        raise BuildError('Unsupported supplemental resource package')
    for name in IMAGES:
        path = root / 'images' / name
        if not path.is_file() or path.is_symlink():
            raise BuildError('Missing supplemental image: ' + name)
        with path.open('rb') as stream:
            if stream.read(8) != b'\x89PNG\r\n\x1a\n':
                raise BuildError('Invalid supplemental PNG: ' + name)
    return root


def load(source, destination):
    source = Path(source)
    if source.is_dir():
        return validate(source)
    with zipfile.ZipFile(source) as package:
        names = set()
        size = 0
        for entry in package.infolist():
            name = entry.filename
            safe_relative(name)
            if name in names or stat.S_ISLNK(entry.external_attr >> 16):
                raise BuildError('Duplicate or linked supplemental member: ' + name)
            names.add(name)
            if entry.is_dir():
                continue
            if name not in ALLOWED:
                raise BuildError('Unexpected supplemental member: ' + name)
            size += entry.file_size
        if size > 2 * 1024**3:
            raise BuildError('Supplemental package exceeds the supported size')
        destination.mkdir(parents=True, exist_ok=True)
        for entry in package.infolist():
            if entry.is_dir():
                continue
            path = destination / str(safe_relative(entry.filename))
            path.resolve().relative_to(destination.resolve())
            path.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as src, path.open('wb') as dst:
                shutil.copyfileobj(src, dst)
    return validate(destination)
