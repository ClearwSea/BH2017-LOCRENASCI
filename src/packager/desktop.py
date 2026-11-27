"""Offline GUI for the explicit original-input builder."""
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .desktop_runtime import TITLE, check, load_settings

STAGES = {
    'supplements': '读取补充资源包',
    'tables-from-originals': '提取客户端数据表',
    'native-from-original': '修补原生兼容库',
    'runtime-data-from-originals': '生成服务端运行数据',
    'client-resources-from-originals': '打包客户端基础资源',
    'voices-from-7x': '转换语音资源',
    'videos-from-7x-and-explicit-extras': '转换并补充视频',
    'v021-game-content': '写入商店与活动兼容数据',
    'v030-reviewed-content': '写入 V0.3.0 角色与技能更新',
    'v030-native-overlay': '叠加 V0.3.0 原生兼容补丁',
    'resource-packs': '打包客户端资源',
    'runtime-capabilities': '生成服务端运行时',
    'android-compile': '编译 Android 启动壳',
    'announcement-layout': '生成公告布局',
    'shop-artwork': '生成商店与图鉴图片',
    'v030-unity-overlay': '写入 V0.3.0 模型与界面资源',
    'v030-audio-overlay': '写入 V0.3.0-r1 音频资源包',
    'apk-compose': '组装 APK',
    'align': '对齐 APK',
    'sign': '签名 APK',
    'verify-signature': '校验 APK 签名',
}


def enable_dpi_awareness():
    if os.name == 'nt':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


class Builder:
    def __init__(self, root, base):
        self.root, self.base = root, base
        self.settings = load_settings(base)
        self.process = None
        self.messages = queue.Queue()
        self.job = None
        self.stopped = False
        self.widgets = []
        self.fields = {}
        root.tk.call('tk', 'scaling', 4 / 3)
        root.title(TITLE)
        root.geometry('1080x810')
        root.minsize(920, 720)
        root.configure(bg='#f3f5f8')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#f3f5f8')
        style.configure('TLabelframe', background='#f3f5f8')
        style.configure('TLabelframe.Label', background='#f3f5f8', foreground='#263346', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('TLabel', background='#f3f5f8', foreground='#263346')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 18, 'bold'))
        style.configure('Sub.TLabel', foreground='#64748b')
        style.configure('TButton', padding=(12, 6))
        style.configure('Primary.TButton', padding=(14, 6), font=('Microsoft YaHei UI', 10, 'bold'))
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='崩坏3·2017 离线构建器', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='生成可安装的 Android APK 与配套视频资源包', style='Sub.TLabel').pack(anchor='w', pady=(4, 16))
        form = ttk.Frame(body)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        rows = [
            ('client19', '1.9 客户端 APK', 'apk', True),
            ('client24', '2.4 客户端 APK', 'apk', True),
            ('resources7x', '7.x 资源目录', 'directory', True),
            ('supplements', '补充资源包', 'zip', True),
            ('tools', '离线工具目录', 'directory', False),
            ('output', '输出目录', 'directory', False),
        ]
        for row, (key, label, kind, has_reference) in enumerate(rows):
            ttk.Label(form, text=label, width=16).grid(row=row, column=0, sticky='w', pady=5)
            var = tk.StringVar(value=self.settings.get(key, ''))
            self.fields[key] = var
            entry = ttk.Entry(form, textvariable=var)
            entry.grid(row=row, column=1, sticky='ew', padx=(0, 8), pady=5)
            browse_btn = ttk.Button(form, text='选择…', command=lambda k=key, t=kind: self.browse(k, t))
            browse_btn.grid(row=row, column=2, pady=5)
            self.widgets.extend((entry, browse_btn))
            if has_reference:
                ref_btn = ttk.Button(form, text='核对参考', command=lambda k=key: self.open_reference(k))
                ref_btn.grid(row=row, column=3, padx=(6, 0), pady=5)

        advanced = ttk.LabelFrame(body, text='签名设置', padding=12)
        advanced.pack(fill='x', pady=(14, 12))
        advanced.columnconfigure(1, weight=1)
        for col, (key, label, default) in enumerate((('keystore', '签名密钥路径', ''), ('key_alias', '密钥别名', 'builder'))):
            ttk.Label(advanced, text=label).grid(row=0, column=col * 2, padx=(0, 8), sticky='w')
            var = tk.StringVar(value=self.settings.get(key, default))
            self.fields[key] = var
            widget = ttk.Entry(advanced, textvariable=var, width=22 if col else 54)
            widget.grid(row=0, column=col * 2 + 1, sticky='ew', padx=(0, 10))
            self.widgets.append(widget)
        for col, (key, label) in enumerate((('store_password', '密钥库密码'), ('key_password', '密钥密码'))):
            ttk.Label(advanced, text=label).grid(row=1, column=col * 2, padx=(0, 8), sticky='w', pady=(8, 0))
            var = tk.StringVar(value='android')
            self.fields[key] = var
            widget = ttk.Entry(advanced, textvariable=var, show='•', width=22)
            widget.grid(row=1, column=col * 2 + 1, sticky='ew', padx=(0, 10), pady=(8, 0))
            self.widgets.append(widget)
        help_row = ttk.Frame(advanced)
        help_row.grid(row=2, column=0, columnspan=4, sticky='ew', pady=(8, 0))
        ttk.Label(help_row, text='密钥路径留空时，会在 user-data/keys/local-build.jks 自动生成本机密钥（默认别名 builder、密码 android）',
                  style='Sub.TLabel').pack(side='left')
        ttk.Button(help_row, text='签名说明', command=self.open_signing_help).pack(side='right')

        buttons = ttk.Frame(body)
        buttons.pack(fill='x', pady=(2, 0))
        self.check_button = ttk.Button(buttons, text='检查路径', command=self.check_paths)
        self.check_button.pack(side='left')
        self.build_button = ttk.Button(buttons, text='开始构建', style='Primary.TButton', command=self.start)
        self.build_button.pack(side='left', padx=8)
        self.stop_button = ttk.Button(buttons, text='停止构建', command=self.stop, state='disabled')
        self.stop_button.pack(side='left')
        ttk.Button(buttons, text='打开输出', command=self.open_output).pack(side='right')
        ttk.Button(buttons, text='打开日志', command=self.open_log).pack(side='right', padx=8)

        self.status = tk.StringVar(value='')
        ttk.Label(body, textvariable=self.status).pack(anchor='w', pady=(14, 5))
        self.progress = ttk.Progressbar(body, maximum=len(STAGES))
        self.progress.pack(fill='x', pady=(0, 10))

        log_frame = ttk.Frame(body)
        log_frame.pack(fill='both', expand=True)
        self.log = tk.Text(log_frame, font=('Consolas', 10), bg='#ffffff', fg='#273449',
                           relief='flat', wrap='word', height=8, padx=10, pady=10, state='disabled')
        self.log.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scrollbar.set)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(120, self.poll)

    def browse(self, key, kind):
        current = self.fields[key].get()
        initial = str(Path(current).parent) if current else str(self.base)
        if kind == 'directory':
            result = filedialog.askdirectory(initialdir=current or str(self.base))
        else:
            result = filedialog.askopenfilename(initialdir=initial, filetypes=[('APK' if kind == 'apk' else 'ZIP', '*.' + kind)])
        if result:
            self.fields[key].set(result)

    def open_reference(self, key):
        from .reference_window import ReferenceWindow
        ReferenceWindow(self.root, key, self.fields[key].get().strip())

    def open_signing_help(self, event=None):
        window = getattr(self, 'signing_help', None)
        if window is not None and window.winfo_exists():
            window.lift()
            return
        self.signing_help = window = tk.Toplevel(self.root)
        window.title('签名设置说明')
        window.geometry('760x620')
        window.minsize(640, 460)
        window.transient(self.root)
        body = ttk.Frame(window, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='签名设置说明', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Button(body, text='关闭说明', command=window.destroy).pack(side='bottom', anchor='e', pady=(12, 0))
        frame = ttk.Frame(body)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, wrap='word', font=('Microsoft YaHei UI', 10), relief='flat',
                       padx=12, pady=10, spacing1=4, spacing3=9)
        text.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        sections = [
            ('不填密钥也能构建',
             '如果留空签名密钥路径，首次构建会自动在 user-data/keys/local-build.jks 创建本机密钥；默认别名为 builder，两个密码均为 android。保留该文件及相同配置，之后构建会一直沿用同一签名。'),
            ('使用已有签名密钥',
             '签名密钥路径：选择已有的 .jks 或 .keystore 文件。\n'
             '密钥别名：填写密钥库内对应的别名。\n'
             '密钥库密码：填写打开该密钥库的密码。\n'
             '密钥密码：填写该别名的密钥密码（与密钥库密码相同时可留空）。'),
            ('覆盖安装与存档保留',
             '使用相同签名打出的 APK 可以直接覆盖安装并保留手机端数据。如果你更换了签名或丢失了本机密钥，系统将无法覆盖安装，只能先卸载旧应用。卸载前请在游戏启动页导出当前存档并保存到应用目录之外。'),
            ('信息保存范围',
             '密钥路径与别名会保存在本地配置中；密码仅传给当次构建进程，不会写入配置文件，下次打开窗口时需重新输入自有密码。'),
        ]
        text.tag_configure('heading', font=('Microsoft YaHei UI', 11, 'bold'), foreground='#263346')
        for heading, content in sections:
            text.insert('end', heading + '\n', 'heading')
            text.insert('end', content + '\n\n')
        text.configure(state='disabled')
        window.bind('<Escape>', lambda event: window.destroy())

    def values(self):
        return {key: var.get() if 'password' in key else var.get().strip() for key, var in self.fields.items()}

    def save(self, values):
        path = self.base / 'user-data/settings.local.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({k: v for k, v in values.items() if 'password' not in k}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check_paths(self):
        try:
            values = self.values()
            check(values)
            self.save(values)
            self.status.set('路径检查通过，可以开始构建')
        except Exception as error:
            self.status.set('路径检查未通过')
            messagebox.showerror('路径检查未通过', str(error))

    def append(self, line):
        self.log.configure(state='normal')
        self.log.insert('end', line)
        if int(self.log.index('end-1c').split('.')[0]) > 1600:
            self.log.delete('1.0', '300.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def busy(self, enabled):
        for widget in self.widgets + [self.check_button, self.build_button]:
            widget.configure(state='disabled' if enabled else 'normal')
        self.stop_button.configure(state='normal' if enabled else 'disabled')

    def start(self):
        if self.process is not None:
            return
        values = self.values()
        try:
            check(values)
            self.save(values)
            self.base.joinpath('user-data/logs').mkdir(parents=True, exist_ok=True)
            self.log_path = self.base / 'user-data/logs' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '.log')
            env = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'):
                env.pop(key, None)
            app = Path(__file__).resolve().parents[1]
            env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(app),
                       PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PIP_NO_INDEX='1')
            python = Path(sys.executable).with_name('python.exe')
            self.process = subprocess.Popen(
                [str(python), '-B', '-s', '-u', '-m', 'packager.desktop_worker'],
                cwd=app, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.process.stdin.write(json.dumps({**values, 'base': str(self.base)}, ensure_ascii=False))
            self.process.stdin.close()
            self.stopped = False
            self.job = None
            self.progress['value'] = 0
            self.busy(True)
            self.status.set('正在启动构建进程')
            self.append('\n--- 开始构建 ---\n')
            threading.Thread(target=self.read_output, args=(self.process, self.log_path), daemon=True).start()
        except Exception as error:
            if self.process is not None:
                self.process.kill()
                self.process = None
            self.busy(False)
            self.status.set('无法启动构建')
            messagebox.showerror('无法开始构建', str(error))

    def read_output(self, process, log_path):
        with log_path.open('w', encoding='utf-8') as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                self.messages.put(('line', line))
        self.messages.put(('done', process.wait()))

    def poll(self):
        stage_names = list(STAGES)
        total = len(stage_names)
        for _ in range(250):
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == 'line':
                if value.startswith('@@BUILDER '):
                    info = json.loads(value[len('@@BUILDER '):])
                    if info.get('job'):
                        self.job = Path(info['job'])
                    if info.get('success'):
                        self.progress['value'] = total
                else:
                    self.append(value)
                    tag = value[1:].split(']', 1)[0] if value.startswith('[') else ''
                    if tag in STAGES:
                        index = stage_names.index(tag)
                        self.status.set(f'第 {index + 1} / {total} 步：{STAGES[tag]}')
                        self.progress['value'] = index + (1 if 'reuse completed stage' in value else 0)
            elif kind == 'done':
                self.process = None
                self.busy(False)
                if self.stopped:
                    self.status.set('已停止构建，中间文件与日志已保留')
                elif value == 0:
                    self.progress['value'] = total
                    self.status.set('构建完成：' + str(self.job))
                    messagebox.showinfo('构建完成', f'已生成 APK 与配套资源包：\n{self.job}\n\n安装后请在启动页选择同目录中的 client-videos.zip')
                else:
                    self.status.set('构建失败，请打开日志查看报错详情')
                    messagebox.showerror('构建失败', f'构建过程中发生错误，完整日志位于：\n{self.log_path}')
        self.root.after(120, self.poll)

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        self.stopped = True
        self.status.set('正在停止构建')
        subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def open_output(self):
        path = self.job or Path(self.fields['output'].get() or str(self.base / 'output'))
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_log(self):
        path = getattr(self, 'log_path', None)
        if path is not None and path.exists():
            os.startfile(path)
        else:
            logs = self.base / 'user-data/logs'
            if logs.is_dir():
                os.startfile(logs)
            else:
                messagebox.showinfo('没有构建日志', '开始构建后会自动生成日志')

    def close(self):
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno('停止构建并退出？', '构建仍在进行。现在退出会中止当前任务，已完成的阶段会保留在输出目录中。'):
                return
            self.stop()
        self.root.destroy()


def main():
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
    enable_dpi_awareness()
    root = tk.Tk()
    Builder(root, base)
    root.mainloop()
