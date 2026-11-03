"""Local-only desktop build settings and portable tool paths."""
import json
from pathlib import Path
from .core import BuildError, read_json

TITLE = '崩坏3·2017 独立版 · 构建器'
TOOLS = {'tools_root': 'android', 'zig': 'zig/zig.exe', 'ffmpeg': 'ffmpeg/ffmpeg.exe',
         'voice_decoder': 'vgmstream/vgmstream-cli.exe', 'wheelhouse': 'wheelhouse'}


def tool_paths(root):
    return {key: Path(root).resolve() / name for key, name in TOOLS.items()}


def check(settings):
    paths = {key: Path(settings.get(key, '')).expanduser() for key in
             ('client19', 'client24', 'resources7x', 'supplements', 'tools', 'output')}
    for key in ('client19', 'client24', 'supplements'):
        if not settings.get(key) or not paths[key].is_file():
            labels = {'client19': '1.9 客户端 APK', 'client24': '2.4 客户端 APK', 'supplements': '补充资源 ZIP'}
            raise BuildError('请选择有效的' + labels[key] + '文件')
    for name in ('Audio', 'Video'):
        if not (paths['resources7x'] / name).is_dir():
            raise BuildError('7.x 目录应直接包含 Audio 和 Video：缺少 ' + name)
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
        raise BuildError('离线工具包不完整：\n' + '\n'.join(missing))
    if not settings.get('output'):
        raise BuildError('请选择输出目录')
    output = paths['output'].resolve()
    app = Path(__file__).resolve().parents[1]
    for key in ('resources7x', 'tools'):
        source = paths[key].resolve()
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise BuildError('输出目录必须与输入资源、工具目录分开')
    if output == app or output.is_relative_to(app) or app.is_relative_to(output):
        raise BuildError('输出目录必须与程序源码分开')
    if settings.get('keystore') and not Path(settings['keystore']).is_file():
        raise BuildError('指定的签名密钥不存在')
    return {**{k: p.resolve() for k, p in paths.items()}, **tools}


def load_settings(base):
    defaults = {key: '' for key in ('client19', 'client24', 'resources7x', 'supplements', 'keystore')}
    defaults.update(tools=str(base / 'tools'), output=str(base / 'output'), key_alias='builder')
    path = base / 'user-data/settings.local.json'
    if path.is_file():
        defaults.update(json.loads(path.read_text(encoding='utf-8-sig')))
    return defaults
