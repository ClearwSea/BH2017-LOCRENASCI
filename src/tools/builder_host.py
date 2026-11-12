"""Offline main-package import and launcher; supplied by the stable base."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

HOST_API = 1
MAX_BYTES = 128 * 1024 * 1024


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not name or '\\' in name or ':' in name or name.startswith('/') or any(
            p in ('.', '..') or p.endswith((' ', '.')) for p in name.split('/')):
        raise ValueError('主包包含无效路径：' + name)
    if len(parts) < 2 or parts[0] != 'app':
        raise ValueError('主包只能包含 app 目录：' + name)
    return name


def validate_manifest(manifest, base):
    if manifest.get('format') != 'BH2017-main' or manifest.get('schema') != 1:
        raise ValueError('请选择构建主包 ZIP')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?', manifest.get('version', '')):
        raise ValueError('主包版本无效')
    if type(manifest.get('host_api')) is not int or manifest['host_api'] != HOST_API:
        raise ValueError('此主包需要更新构建器基础包')
    if read(base / 'base-manifest.json')['toolchain_id'] != manifest.get('toolchain_id'):
        raise ValueError('工具链版本不匹配，请使用该主包要求的基础包：' + str(manifest.get('toolchain_id')))
    rows = manifest.get('files')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError('主包文件清单无效')
    seen, total = set(), 0
    for row in rows:
        name = safe_name(row['path'])
        if name.casefold() in seen or type(row['size']) is not int or row['size'] < 0 or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('主包文件清单重复或损坏')
        seen.add(name.casefold())
        total += row['size']
    if total > MAX_BYTES or 'app/launch_gui.py' not in {r['path'] for r in rows}:
        raise ValueError('主包大小或入口无效')
    return rows


def state_path(base):
    return base / 'user-data/main-package.json'


def package_dir(base, identity):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?-[0-9a-f]{64}', identity or ''):
        raise ValueError('已导入主包的标识无效')
    return base / 'packages' / identity


def verify_installed(base, identity):
    path = package_dir(base, identity)
    manifest = read(path / 'main-manifest.json')
    rows = validate_manifest(manifest, base)
    for row in rows:
        raw = (path / row['path']).read_bytes()
        if len(raw) != row['size'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('主包文件校验失败：' + row['path'])
    return path, manifest


def import_main(base, archive):
    base = Path(base).resolve()
    packages = base / 'packages'
    packages.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        if len(infos) > 10001 or len({i.filename.casefold() for i in infos}) != len(infos):
            raise ValueError('主包包含重复文件或文件过多')
        info = source.getinfo('main-manifest.json')
        if info.file_size > 4 * 1024 * 1024:
            raise ValueError('主包清单过大')
        manifest_raw = source.read(info)
        manifest = json.loads(manifest_raw)
        rows = validate_manifest(manifest, base)
        if {i.filename for i in infos} != {'main-manifest.json'} | {r['path'] for r in rows}:
            raise ValueError('主包内容与清单不一致')
        identity = manifest['version'] + '-' + hashlib.sha256(manifest_raw).hexdigest()
        target = package_dir(base, identity)
        with tempfile.TemporaryDirectory(prefix='.import-', dir=packages) as temporary:
            stage = Path(temporary)
            for row in rows:
                info = source.getinfo(row['path'])
                if info.file_size != row['size'] or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('主包大小不一致或包含符号链接')
                raw = source.read(info)
                if hashlib.sha256(raw).hexdigest() != row['sha256']:
                    raise ValueError('主包文件校验失败：' + row['path'])
                path = stage / row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            (stage / 'main-manifest.json').write_bytes(manifest_raw)
            if target.exists():
                verify_installed(base, identity)
            else:
                # Keep TemporaryDirectory's own root for its cleanup context.
                payload = packages / ('.ready-' + identity)
                os.replace(stage, payload)
                os.replace(payload, target)
                stage.mkdir()
    previous = read(state_path(base)) if state_path(base).is_file() else {}
    if previous.get('current') != identity:
        write(state_path(base), dict(current=identity, previous=previous.get('current')))
    return identity


def rollback(base):
    state = read(state_path(base))
    previous = state.get('previous')
    if not previous:
        raise ValueError('没有可恢复的上一版主包')
    verify_installed(base, previous)
    write(state_path(base), dict(current=previous, previous=state['current']))


def main():
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    # One host owns import/rollback while its build window is running.
    lock_path = base / 'user-data/host.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open('a+b')
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            messagebox.showinfo('构建器已打开', '请使用已经打开的构建器窗口。')
            return
    root = tk.Tk()
    root.title('崩坏3·2017 · 构建器')
    root.geometry('650x300')
    status = tk.StringVar()
    busy = [False]
    def refresh():
        state = read(state_path(base)) if state_path(base).is_file() else {}
        current = state.get('current')
        version = verify_installed(base, current)[1]['version'] if current else '尚未导入'
        status.set('当前构建主包：' + version + '\n基础包：' + read(base / 'base-manifest.json')['toolchain_id'])
    ttk.Label(root, text='崩坏3·2017 离线构建器', font=('Microsoft YaHei UI', 18)).pack(pady=18)
    ttk.Label(root, textvariable=status, justify='center').pack(pady=8)
    ttk.Label(root, text='首次导入构建主包；工具链未变更时，后续只需导入新版主包。').pack(pady=8)
    controls = ttk.Frame(root)
    controls.pack(pady=14)
    buttons = []
    def task(action):
        busy[0] = True
        for button in buttons: button.configure(state='disabled')
        status.set('正在校验或运行，请稍候……')
        def worker():
            error = None
            try: action()
            except Exception as exc: error = str(exc)
            def finish():
                busy[0] = False
                for button in buttons: button.configure(state='normal')
                try: refresh()
                except Exception as exc: status.set(str(exc))
                if error: messagebox.showerror('操作未完成', error, parent=root)
            root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()
    def choose():
        path = filedialog.askopenfilename(title='导入构建主包', filetypes=[('构建主包', '*.zip')])
        if path: task(lambda: import_main(base, path))
    def launch():
        state = read(state_path(base)) if state_path(base).is_file() else {}
        if not state.get('current'):
            messagebox.showinfo('导入主包', '请先导入构建主包。', parent=root)
            return
        def run():
            path, manifest = verify_installed(base, state['current'])
            env = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY'): env.pop(key, None)
            env.update(PYTHONNOUSERSITE='1', PYTHONUTF8='1')
            result = subprocess.run([str(base / 'tools/python/pythonw.exe'), '-B', '-s',
                                     str(path / 'app/launch_gui.py'), str(base)], cwd=path / 'app', env=env)
            if result.returncode: raise ValueError('构建界面退出异常，请查看 user-data/logs 中的日志。')
        task(run)
    for title, command in [('导入构建主包', choose), ('打开构建界面', launch), ('恢复上一版', lambda: task(lambda: rollback(base)))]:
        button = ttk.Button(controls, text=title, command=command)
        button.pack(side='left', padx=7)
        buttons.append(button)
    root.protocol('WM_DELETE_WINDOW', lambda: root.destroy() if not busy[0] else messagebox.showinfo(
        '正在运行', '请先关闭构建界面或等待导入完成。', parent=root))
    try: refresh()
    except Exception as exc: status.set(str(exc))
    root.mainloop()


if __name__ == '__main__':
    main()
