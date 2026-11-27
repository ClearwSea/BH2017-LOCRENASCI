"""Nonmodal, cancellable reference viewer; independent of build controls."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
from .core import ROOT, read_json
from .input_reference import ComparisonCancelled, compare_file, quick_directory, references


class ReferenceWindow(tk.Toplevel):
    def __init__(self, parent, key, selected):
        super().__init__(parent)
        self.key, self.selected = key, selected
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.running = False
        self.reference = references()[key]
        if key == 'resources7x':
            self.reference = read_json(ROOT / 'profiles/resources7x-reference.json')
        self.title('参考输入核对 · ' + self.reference['label'])
        self.geometry('820x590')
        self.minsize(700, 480)
        self.configure(bg='#f3f5f8')
        body = ttk.Frame(self, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=self.reference['label'], font=('Microsoft YaHei UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(body, text='当前路径：' + (selected or '尚未选择'), wraplength=770).pack(anchor='w', pady=(8, 4))
        ttk.Label(body, text='参考数据仅用于核对原包版本，不一致时仍可继续构建',
                  foreground='#64748b', wraplength=770).pack(anchor='w', pady=(0, 10))
        if key == 'resources7x':
            count = len(self.reference['files'])
            size = sum(row['bytes'] for row in self.reference['files'])
            summary = f'参考范围：Windows 版 Audio 与 Video，共 {count} 个文件（{size / 1024**3:.2f} GiB），仅比对文件名与字节大小。'
            ttk.Label(body, text=summary).pack(anchor='w', pady=(0, 8))
            initial = '\n'.join(f"{row['path']}\t{row['bytes']} bytes" for row in self.reference['files'])
        else:
            ttk.Label(body, text='参考 SHA-256：').pack(anchor='w')
            self.sha_value = tk.StringVar(value=self.reference['sha256'])
            ttk.Entry(body, textvariable=self.sha_value, state='readonly', font=('Consolas', 10)).pack(fill='x', pady=(4, 9))
            initial = f"参考文件大小：{self.reference['bytes']} bytes"
        toolbar = ttk.Frame(body)
        toolbar.pack(fill='x', pady=(0, 8))
        action_label = '检查目录清单' if key == 'resources7x' else '校验文件 SHA-256'
        self.start_button = ttk.Button(toolbar, text=action_label, command=self.start)
        self.start_button.pack(side='left')
        self.cancel_button = ttk.Button(toolbar, text='取消校验', command=self.cancel.set, state='disabled')
        self.cancel_button.pack(side='left', padx=8)
        if key != 'resources7x':
            ttk.Button(toolbar, text='复制参考 SHA-256', command=self.copy_reference).pack(side='right')
        self.status = tk.StringVar(value='')
        ttk.Label(body, textvariable=self.status, wraplength=770).pack(anchor='w', pady=(0, 6))
        self.progress = ttk.Progressbar(body, maximum=100)
        self.progress.pack(fill='x', pady=(0, 9))
        frame = ttk.Frame(body)
        frame.pack(fill='both', expand=True)
        self.result = tk.Text(frame, font=('Consolas', 10), wrap='word', relief='flat', padx=8, pady=8, height=10)
        self.result.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, command=self.result.yview)
        scroll.pack(side='right', fill='y')
        self.result.configure(yscrollcommand=scroll.set)
        self.show(initial)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.timer = self.after(100, self.poll)

    def show(self, text):
        self.result.configure(state='normal')
        self.result.delete('1.0', 'end')
        self.result.insert('end', text)
        self.result.configure(state='disabled')

    def copy_reference(self):
        self.clipboard_clear()
        self.clipboard_append(self.reference['sha256'])
        self.status.set('已复制参考 SHA-256')

    def start(self):
        if self.running:
            return
        self.cancel.clear()
        self.running = True
        self.start_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.status.set('正在读取并计算……')
        self.progress['value'] = 0
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            if not self.selected:
                raise ValueError('主窗口尚未选择该输入，请先选择文件或目录')
            action = quick_directory if self.key == 'resources7x' else compare_file
            value = action(Path(self.selected), self.reference, self.cancel,
                           lambda done, total: self.events.put(('progress', (done, total))))
            if self.cancel.is_set():
                raise ComparisonCancelled()
            self.events.put(('result', value))
        except ComparisonCancelled:
            self.events.put(('cancelled', None))
        except Exception as error:
            self.events.put(('error', str(error)))

    def poll(self):
        for _ in range(300):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                done, total = value
                self.progress['value'] = 100 * done / max(total, 1)
                if self.key == 'resources7x':
                    self.status.set(f'已扫描 {done} 个文件')
                else:
                    self.status.set(f'已校验 {done / 1024**2:.0f} / {total / 1024**2:.0f} MiB')
                continue
            self.running = False
            self.start_button.configure(state='normal')
            self.cancel_button.configure(state='disabled')
            if kind == 'cancelled':
                self.status.set('已取消校验')
            elif kind == 'error':
                self.status.set('校验失败：' + value)
            else:
                self.progress['value'] = 100
                self.status.set('校验结果：与参考一致' if value['matches_reference'] else '校验结果：与参考不同（仍可继续构建）')
                if self.key == 'resources7x':
                    lines = [f"缺少 {len(value['missing'])} 个，大小不同 {len(value['different_size'])} 个，多出 {len(value['additional'])} 个", '']
                    lines += ['缺少：' + n for n in value['missing']]
                    lines += ['大小不同：' + r['path'] + f"（参考 {r['reference_bytes']}，当前 {r['actual_bytes']} bytes）" for r in value['different_size']]
                    lines += ['多出：' + n for n in value['additional']]
                    self.show('\n'.join(lines))
                else:
                    self.show('当前 SHA-256：\n' + value['actual_sha256'] + '\n\n参考 SHA-256：\n' + value['reference_sha256'])
        self.timer = self.after(100, self.poll)

    def close(self):
        self.cancel.set()
        self.destroy()
