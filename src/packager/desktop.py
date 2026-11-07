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
    'supplements': '读取补充资源包', 'tables-from-originals': '提取客户端与恢复表单',
    'native-from-original': '应用原生兼容补丁', 'runtime-data-from-originals': '生成服务端运行数据',
    'client-resources-from-originals': '转换客户端资源', 'voices-from-7x': '转换语音',
    'videos-from-7x-and-explicit-extras': '转换与补充视频', 'resource-packs': '生成资源包',
    'runtime-capabilities': '整理服务端运行包', 'android-compile': '编译 Android 启动组件',
    'announcement-layout': '适配公告布局', 'apk-compose': '组装 APK',
    'align': '对齐 APK', 'sign': '签名 APK', 'verify-signature': '验证签名'}


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
        root.geometry('1040x790')
        root.minsize(900, 710)
        root.configure(bg='#f3f5f8')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#f3f5f8')
        style.configure('TLabel', background='#f3f5f8', foreground='#263346')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 19, 'bold'))
        style.configure('Sub.TLabel', foreground='#64748b')
        style.configure('Link.TLabel', foreground='#2563eb', font=('Microsoft YaHei UI', 10, 'underline'))
        style.configure('TButton', padding=(13, 7))
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='崩坏3·2017 独立版', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='离线构建器  ·  选择客户端与资源，生成 APK 和配套资源包', style='Sub.TLabel').pack(anchor='w', pady=(3, 18))
        form = ttk.Frame(body)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        rows = [('client19', '1.9 客户端', 'apk'), ('client24', '2.4 客户端', 'apk'),
                ('resources7x', '7.x 资源目录', 'directory'), ('supplements', '补充资源包', 'zip'),
                ('tools', '离线工具目录', 'directory'), ('output', '输出目录', 'directory')]
        for row, (key, label, kind) in enumerate(rows):
            label_widget = ttk.Label(form, text=label, width=15)
            label_widget.grid(row=row, column=0, sticky='w', pady=5)
            if key in ('client19', 'client24', 'resources7x', 'supplements'):
                label_widget.configure(style='Link.TLabel', cursor='hand2', takefocus=True)
                label_widget.bind('<Button-1>', lambda event, k=key: self.open_reference(k))
                label_widget.bind('<Return>', lambda event, k=key: self.open_reference(k))
            var = tk.StringVar(value=self.settings.get(key, ''))
            self.fields[key] = var
            entry = ttk.Entry(form, textvariable=var)
            entry.grid(row=row, column=1, sticky='ew', padx=(0, 8), pady=5)
            button = ttk.Button(form, text='浏览…', command=lambda k=key, t=kind: self.browse(k, t))
            button.grid(row=row, column=2, pady=5)
            self.widgets.extend((entry, button))
        ttk.Label(body, text='点击左侧输入名称查看参考信息。', style='Sub.TLabel').pack(anchor='w', pady=(5, 10))
        advanced = ttk.LabelFrame(body, padding=10)
        self.signing_label = ttk.Label(advanced, text='签名设置', style='Link.TLabel', cursor='hand2', takefocus=True)
        advanced.configure(labelwidget=self.signing_label)
        self.signing_label.bind('<Button-1>', self.open_signing_help)
        self.signing_label.bind('<Return>', self.open_signing_help)
        self.signing_label.bind('<space>', self.open_signing_help)
        advanced.pack(fill='x', pady=(0, 12))
        advanced.columnconfigure(1, weight=1)
        for col, (key, label, default) in enumerate((('keystore', '密钥路径', ''), ('key_alias', '别名', 'builder'))):
            ttk.Label(advanced, text=label).grid(row=0, column=col * 2, padx=(0, 8), sticky='w')
            var = tk.StringVar(value=self.settings.get(key, default)); self.fields[key] = var
            widget = ttk.Entry(advanced, textvariable=var, width=22 if col else 58)
            widget.grid(row=0, column=col * 2 + 1, sticky='ew', padx=(0, 10)); self.widgets.append(widget)
        for col, (key, label) in enumerate((('store_password', '密钥库密码'), ('key_password', '密钥密码'))):
            ttk.Label(advanced, text=label).grid(row=1, column=col * 2, padx=(0, 8), sticky='w', pady=(8, 0))
            var = tk.StringVar(value='android'); self.fields[key] = var
            widget = ttk.Entry(advanced, textvariable=var, show='•', width=22)
            widget.grid(row=1, column=col * 2 + 1, sticky='ew', padx=(0, 10), pady=(8, 0)); self.widgets.append(widget)
        buttons = ttk.Frame(body); buttons.pack(fill='x')
        self.check_button = ttk.Button(buttons, text='检查路径', command=self.check_paths)
        self.check_button.pack(side='left')
        self.build_button = ttk.Button(buttons, text='开始构建', command=self.start)
        self.build_button.pack(side='left', padx=8)
        self.stop_button = ttk.Button(buttons, text='停止构建', command=self.stop, state='disabled')
        self.stop_button.pack(side='left')
        ttk.Button(buttons, text='打开输出目录', command=self.open_output).pack(side='right')
        ttk.Button(buttons, text='打开日志', command=self.open_log).pack(side='right', padx=8)
        self.status = tk.StringVar(value='就绪。')
        ttk.Label(body, textvariable=self.status).pack(anchor='w', pady=(14, 5))
        self.progress = ttk.Progressbar(body, maximum=len(STAGES))
        self.progress.pack(fill='x', pady=(0, 10))
        ttk.Label(body, text='生成的 APK、资源包和日志按构建时间分目录保存。', style='Sub.TLabel').pack(side='bottom', anchor='w', pady=(8, 0))
        log_frame = ttk.Frame(body); log_frame.pack(fill='both', expand=True)
        self.log = tk.Text(log_frame, font=('Consolas', 10), bg='#ffffff', fg='#273449',
                           relief='flat', wrap='word', height=6, padx=10, pady=10, state='disabled')
        self.log.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side='right', fill='y'); self.log.configure(yscrollcommand=scrollbar.set)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(120, self.poll)

    def browse(self, key, kind):
        current = self.fields[key].get()
        initial = str(Path(current).parent) if current else str(self.base)
        if kind == 'directory':
            result = filedialog.askdirectory(initialdir=current or str(self.base))
        else:
            result = filedialog.askopenfilename(initialdir=initial, filetypes=[('APK' if kind == 'apk' else 'ZIP', '*.' + kind)])
        if result: self.fields[key].set(result)

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
        window.geometry('760x650')
        window.minsize(650, 480)
        window.transient(self.root)
        body = ttk.Frame(window, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='签名设置', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Button(body, text='关闭', command=window.destroy).pack(side='bottom', anchor='e', pady=(12, 0))
        frame = ttk.Frame(body)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, wrap='word', font=('Microsoft YaHei UI', 10), relief='flat',
                       padx=12, pady=10, spacing1=4, spacing3=9)
        text.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side='right', fill='y')
        text.configure(yscrollcommand=scroll.set)
        sections = [
            ('全部留空也可以构建',
             '密钥路径留空时，首次构建会自动生成本机签名密钥，保存在 user-data/keys/local-build.jks；以后继续使用这个文件。全部留空时，别名为 builder，两个密码均为 android。保留该文件和相同的别名、密码，即可继续用同一签名构建。'),
            ('已有密钥时怎么填',
             '密钥路径：选择已有的 .jks 或 .keystore 文件。\n'
             '别名：填写该文件中用于签名的密钥别名。\n'
             '密钥库密码：填写打开该密钥库的密码。\n'
             '密钥密码：填写该别名对应密钥的密码，通常与密钥库密码相同。\n'
             '四项需与已有密钥对应；填错会导致签名失败。'),
            ('只填部分字段会怎样',
             '别名留空时使用 builder；密钥库密码留空时使用 android；密钥密码留空时使用密钥库密码。密钥路径留空但填写了其他字段时，自动生成或复用的本机密钥会使用这些值。已有密钥不会因修改填写内容而被重建或改密。'),
            ('覆盖安装与存档',
             '同一应用使用相同签名，可覆盖安装并保留已有数据。每次留空并不会生成一个新应用：本机密钥文件仍在且填写方式一致，就会继续复用。\n'
             '换了密钥，或丢失本机密钥后重新生成，签名就会不同，通常需要先卸载旧应用。卸载前请在应用内导出存档，并确认备份已保存到应用目录之外。导出的兼容存档仍可导入新签名的版本。'),
            ('下次使用',
             '密钥路径和别名会保留；密码不会保存，下次打开时默认显示 android。使用自有密码时需要重新填写。备份密钥文件，并记住对应别名和密码。'),
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
            values = self.values(); check(values); self.save(values)
            self.status.set('路径检查通过，可以开始构建。')
        except Exception as error: messagebox.showerror('路径检查', str(error))

    def append(self, line):
        self.log.configure(state='normal'); self.log.insert('end', line)
        if int(self.log.index('end-1c').split('.')[0]) > 1600: self.log.delete('1.0', '300.0')
        self.log.see('end'); self.log.configure(state='disabled')

    def busy(self, enabled):
        for widget in self.widgets + [self.check_button, self.build_button]:
            widget.configure(state='disabled' if enabled else 'normal')
        self.stop_button.configure(state='normal' if enabled else 'disabled')

    def start(self):
        if self.process is not None: return
        values = self.values()
        try:
            check(values); self.save(values)
            self.base.joinpath('user-data/logs').mkdir(parents=True, exist_ok=True)
            self.log_path = self.base / 'user-data/logs' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '.log')
            env = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'): env.pop(key, None)
            app = Path(__file__).resolve().parents[1]
            env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(app),
                       PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PIP_NO_INDEX='1')
            python = Path(sys.executable).with_name('python.exe')
            self.process = subprocess.Popen([str(python), '-B', '-s', '-u', '-m', 'packager.desktop_worker'],
                cwd=app, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.process.stdin.write(json.dumps({**values, 'base': str(self.base)}, ensure_ascii=False))
            self.process.stdin.close()
            self.stopped = False; self.job = None; self.progress['value'] = 0
            self.busy(True); self.status.set('正在启动构建……')
            self.append('\n开始构建\n')
            threading.Thread(target=self.read_output, args=(self.process, self.log_path), daemon=True).start()
        except Exception as error:
            if self.process is not None:
                self.process.kill(); self.process = None
            self.busy(False); messagebox.showerror('无法开始构建', str(error))

    def read_output(self, process, log_path):
        with log_path.open('w', encoding='utf-8') as log:
            for line in process.stdout:
                log.write(line); log.flush(); self.messages.put(('line', line))
        self.messages.put(('done', process.wait()))

    def poll(self):
        for _ in range(250):
            try: kind, value = self.messages.get_nowait()
            except queue.Empty: break
            if kind == 'line':
                if value.startswith('@@BUILDER '):
                    info = json.loads(value[len('@@BUILDER '):])
                    if info.get('job'): self.job = Path(info['job'])
                    if info.get('success'): self.progress['value'] = len(STAGES)
                else:
                    self.append(value)
                    tag = value[1:].split(']', 1)[0] if value.startswith('[') else ''
                    if tag in STAGES:
                        self.status.set(STAGES[tag] + '……')
                        self.progress['value'] = list(STAGES).index(tag)
            elif kind == 'done':
                self.process = None; self.busy(False)
                if self.stopped: self.status.set('构建已停止。日志和中间文件已保存。')
                elif value == 0:
                    self.progress['value'] = len(STAGES)
                    self.status.set('构建完成：' + str(self.job))
                    messagebox.showinfo('构建完成', 'APK 和配套资源包已生成。\n' + str(self.job))
                else:
                    self.status.set('构建失败，请查看日志。')
                    messagebox.showerror('构建失败', '请查看窗口日志或打开完整日志。\n' + str(self.log_path))
        self.root.after(120, self.poll)

    def stop(self):
        if self.process is None or self.process.poll() is not None: return
        self.stopped = True; self.status.set('正在停止构建……')
        subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def open_output(self):
        path = self.job or Path(self.fields['output'].get())
        path.mkdir(parents=True, exist_ok=True); os.startfile(path)

    def open_log(self):
        path = getattr(self, 'log_path', None)
        if path is not None and path.exists(): os.startfile(path)
        else: messagebox.showinfo('日志', '开始构建后生成日志。')

    def close(self):
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno('退出构建器', '构建仍在进行，是否停止构建并退出？'): return
            self.stop()
        self.root.destroy()


def main():
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
    enable_dpi_awareness()
    root = tk.Tk()
    Builder(root, base)
    root.mainloop()
