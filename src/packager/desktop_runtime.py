"""Local-only desktop build settings and portable tool paths."""
import json
from pathlib import Path
import zipfile
from .core import BuildError, read_json
from .supplements import SUPPORTED_KINDS

TITLE = '崩坏3·2017 离线构建器'
TOOLS = {'tools_root': 'android', 'zig': 'zig/zig.exe', 'ffmpeg': 'ffmpeg/ffmpeg.exe',
         'voice_decoder': 'vgmstream/vgmstream-cli.exe', 'wheelhouse': 'wheelhouse'}


def tool_paths(root):
    return {key: Path(root).resolve() / name for key, name in TOOLS.items()}


def _check_apk(path, label):
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise BuildError(f'{label} 不是有效的 APK 文件，请重新选择') from error
    if 'AndroidManifest.xml' not in names:
        raise BuildError(f'{label} 缺少 AndroidManifest.xml，请重新选择原版客户端 APK')


def _check_supplements(path):
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read('supplements.json'))
    except KeyError as error:
        raise BuildError('所选补充资源包缺少 supplements.json，请重新选择配套的补充资源 ZIP') from error
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildError('补充资源包无法读取，请重新选择有效的补充资源 ZIP') from error
    if manifest.get('schema') != 1 or manifest.get('kind') not in SUPPORTED_KINDS:
        raise BuildError('补充资源包格式不受支持，请重新选择配套的补充资源 ZIP')
    required = ('fuka601/v1/content/manifest.json', 'fuka601/v1/fuka601-v1-content.zip')
    if any(item not in names for item in required):
        raise BuildError('所选补充资源包版本不匹配，请选择适用于本版的补充资源 ZIP')


def check(settings):
    paths = {key: Path(settings.get(key, '')).expanduser() for key in
             ('client19', 'client24', 'resources7x', 'supplements', 'tools', 'output')}
    labels = {'client19': '1.9 客户端 APK', 'client24': '2.4 客户端 APK', 'supplements': '补充资源包 ZIP'}
    for key in ('client19', 'client24', 'supplements'):
        if not settings.get(key) or not paths[key].is_file():
            raise BuildError('找不到 ' + labels[key] + '，请重新选择文件')
    _check_apk(paths['client19'], labels['client19'])
    _check_apk(paths['client24'], labels['client24'])
    _check_supplements(paths['supplements'])
    if not settings.get('resources7x') or not paths['resources7x'].is_dir():
        raise BuildError('找不到 7.x 资源目录，请重新选择目录')
    for name in ('Audio', 'Video'):
        if not (paths['resources7x'] / name).is_dir():
            raise BuildError('7.x 资源目录必须直接包含 Audio 和 Video 文件夹：缺少 ' + name)
    tools = tool_paths(paths['tools'])
    needed = [tools['zig'], tools['ffmpeg'], tools['voice_decoder'],
              tools['tools_root'] / 'sdk/platforms/android-35/android.jar',
              tools['tools_root'] / 'sdk/build-tools/35.0.0/zipalign.exe',
              tools['tools_root'] / 'sdk/build-tools/35.0.0/apksigner.bat',
              tools['tools_root'] / 'sdk/build-tools/34.0.0/aapt.exe',
              tools['tools_root'] / 'python311/tools/python.exe',
              tools['tools_root'] / 'gradle/gradle-8.9/bin/gradle.bat']
    missing = [str(p) for p in needed if not p.is_file()]
    if not list((tools['tools_root'] / 'jdk').glob('*/bin/java.exe')):
        missing.append('tools/android/jdk/*/bin/java.exe')
    if not list(tools['wheelhouse'].glob('*.whl')):
        missing.append('tools/wheelhouse/*.whl')
    if missing:
        raise BuildError('离线工具目录缺少以下文件，请重新核对工具包完整性：\n' + '\n'.join(missing))
    if not settings.get('output'):
        raise BuildError('请选择输出目录')
    output = paths['output'].resolve()
    app = Path(__file__).resolve().parents[2]
    for key in ('resources7x', 'tools'):
        source = paths[key].resolve()
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise BuildError('输出目录不能与 7.x 资源目录或离线工具目录互相包含，请另选文件夹')
    if output == app or output.is_relative_to(app) or app.is_relative_to(output):
        raise BuildError('输出目录不能与构建器程序目录互相包含，请另选文件夹')
    if settings.get('keystore') and not Path(settings['keystore']).is_file():
        raise BuildError('找不到指定的签名密钥文件，请重新选择或清空该栏以使用自动生成的本机密钥')
    return {**{k: p.resolve() for k, p in paths.items()}, **tools}


def load_settings(base):
    defaults = {key: '' for key in ('client19', 'client24', 'resources7x', 'supplements', 'keystore')}
    defaults.update(tools=str(base / 'tools'), output=str(base / 'output'), key_alias='builder')
    path = base / 'user-data/settings.local.json'
    if path.is_file():
        defaults.update(json.loads(path.read_text(encoding='utf-8-sig')))
    return defaults
