"""Detect first, explain evidence, then run only the user's selected action."""
import ctypes
import datetime
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import traceback

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from registry import history_rows, make_confirmation
from presentation import root_summary, execution_available

BG, WHITE, INK, MUTED = '#f4f6fa', '#ffffff', '#172338', '#64748b'
BLUE, GREEN, AMBER, RED = '#2563eb', '#15803d', '#a16207', '#b91c1c'
FONT = 'Microsoft YaHei UI'
TITLE = 'Xperia 工具箱 · 1.3.1 等待与亮屏修正版'


class App(tk.Tk):
    def __init__(self, auto_check=True):
        super().__init__()
        self.title(TITLE)
        scale = max(1.0, self.winfo_fpixels('1i') / 96.0)
        width = min(round(1000 * scale), self.winfo_screenwidth() - 50)
        height = min(round(850 * scale), self.winfo_screenheight() - 70)
        self.geometry(f'{width}x{height}')
        self.minsize(min(round(900 * scale), width), min(round(800 * scale), height))
        self.configure(bg=BG)
        try:
            self.iconbitmap(str(ROOT / 'gui' / 'app.ico'))
        except tk.TclError:
            pass
        self.events = queue.Queue()
        self.busy = False
        self.child = None
        self.phone = None
        self.current_logs = ROOT / 'logs'
        self.unlock_pending = False
        self.saved_banner = None
        self.acknowledged = tk.BooleanVar(value=False)
        self.history_items = {}
        self._build()
        self.reload_history()
        self.protocol('WM_DELETE_WINDOW', self.close_app)
        self.after(100, self.consume)
        if auto_check:
            self.after(250, lambda: self.start('status'))

    def label(self, parent, text, size=10, color=INK, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=(FONT, size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, font=(FONT, 10, 'bold'),
                         bg=BLUE if primary else '#eaf0fc', fg=WHITE if primary else BLUE,
                         activebackground='#1d4ed8' if primary else '#dbe7fd',
                         activeforeground=WHITE if primary else BLUE, disabledforeground='#94a3b8',
                         relief='flat', bd=0, cursor='hand2', padx=16, pady=9, takefocus=True)

    def _build(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Blue.Horizontal.TProgressbar', background=BLUE, troughcolor='#e2e8f0', borderwidth=0)
        style.configure('Treeview', font=(FONT, 9), rowheight=30)
        style.configure('Treeview.Heading', font=(FONT, 9, 'bold'))
        top = tk.Frame(self, bg=BG)
        top.pack(fill='x', padx=24, pady=(16, 10))
        self.label(top, '手机检测与 Root 工具箱', size=21, bold=True).pack(anchor='w')
        self.label(top, '先看当前手机与历史测试记录，再自行选择执行。', color=MUTED).pack(anchor='w')
        self.label(top, '1.3.1 等待与亮屏修正版', size=9, color=BLUE).place(relx=1, y=7, anchor='ne')

        card = tk.Frame(self, bg=WHITE, padx=16, pady=12)
        card.pack(fill='x', padx=24)
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill='x')
        self.connection = self.label(row, '等待手机检测', size=14, bold=True)
        self.connection.pack(side='left')
        self.refresh_btn = self.button(row, '刷新检测', lambda: self.start('status'))
        self.refresh_btn.pack(side='right')
        self.device_note = self.label(card, '请连接 USB 数据线，允许 USB 调试。', color=MUTED, anchor='w')
        self.device_note.pack(fill='x', pady=(2, 4))
        self.kernel_note = self.label(card, '完整内核：待检测', size=9, color=MUTED,
                                      anchor='w', justify='left', wraplength=890)
        self.kernel_note.pack(fill='x')
        self.patch_note = self.label(card, '安全补丁：待检测', size=9, color=MUTED, anchor='w')
        self.patch_note.pack(fill='x', pady=(2, 6))
        badges = tk.Frame(card, bg=WHITE)
        badges.pack(fill='x')
        self.values = {}
        for index, (key, name) in enumerate([('root', 'Root 权限'), ('module', 'KernelSU'), ('pill', '底部小白条')]):
            col = tk.Frame(badges, bg=WHITE)
            col.grid(row=0, column=index, sticky='ew', padx=(0, 12))
            badges.columnconfigure(index, weight=1, uniform='states')
            self.label(col, name, size=9, color=MUTED).pack(anchor='w')
            value = self.label(col, '待检测', size=11, bold=True)
            value.pack(anchor='w')
            self.values[key] = value

        decision = tk.Frame(self, bg=BG)
        decision.pack(fill='x', padx=24, pady=(10, 0))
        self.match_note = self.label(decision, '检测后显示配置匹配情况。', size=10, bold=True,
                                     anchor='w', justify='left', wraplength=900)
        self.match_note.pack(fill='x')
        self.ack_box = tk.Checkbutton(decision, text='已了解此固件尚未测试；我选择使用匹配的内核配置尝试执行',
                                      variable=self.acknowledged, command=self.update_buttons,
                                      bg=BG, fg=AMBER, activebackground=BG, font=(FONT, 9), anchor='w')
        buttons = tk.Frame(decision, bg=BG)
        buttons.pack(fill='x', pady=(8, 0))
        self.root_btn = self.button(buttons, '执行一次 Root', lambda: self.start('root'), True)
        self.hide_btn = self.button(buttons, '隐藏小白条', lambda: self.start('hide'))
        self.show_btn = self.button(buttons, '恢复小白条', lambda: self.start('show'))
        for index, button in enumerate((self.root_btn, self.hide_btn, self.show_btn)):
            buttons.columnconfigure(index, weight=1, uniform='actions')
            button.grid(row=0, column=index, sticky='ew', padx=(0 if index == 0 else 5, 0 if index == 2 else 5))
        self.help_line = self.label(decision, 'Root 可能失败或重启。每次开机最多一次尝试，不会自动重试。',
                                    size=9, color=MUTED, anchor='w', justify='left', wraplength=900)
        self.help_line.pack(fill='x', pady=(5, 0))
        self.risk_line = self.label(decision, '风险提示：执行可能失败、卡死或重启。机型、固件和内核不作为电脑端执行门槛，是否尝试由你决定。',
                                    size=9, color=RED, anchor='w', justify='left', wraplength=900)
        self.risk_line.pack(fill='x', pady=(3, 0))

        task = tk.Frame(self, bg=WHITE, padx=14, pady=10)
        task.pack(fill='x', padx=24, pady=(10, 0))
        self.banner = self.label(task, '准备就绪', size=10, bold=True, anchor='w', justify='left', wraplength=890)
        self.banner.pack(fill='x')
        self.progress = ttk.Progressbar(task, style='Blue.Horizontal.TProgressbar', mode='indeterminate')
        self.progress.pack(fill='x', pady=(6, 0))
        self.continue_btn = self.button(task, '手机已解锁，继续', self.continue_unlock, True)
        self.cancel_btn = self.button(task, '取消并恢复亮屏', self.cancel_unlock)

        foot = tk.Frame(self, bg=BG)
        foot.pack(side='bottom', fill='x', padx=24, pady=(8, 12))
        self.label(foot, '全机型可尝试 · 风险自行决定 · 历史仅保存在本机', size=9, color=MUTED).pack(side='left')
        for text, fn in [('使用说明', self.open_help), ('打开日志', self.open_logs),
                         ('取消常亮 / 恢复设置', self.restore_or_cancel_display)]:
            button = tk.Button(foot, text=text, command=fn, bg=BG, fg=BLUE, activebackground=BG,
                               relief='flat', font=(FONT, 9), cursor='hand2', padx=8)
            button.pack(side='right')
            if text == '取消常亮 / 恢复设置':
                self.restore_display_btn = button

        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=24, pady=(10, 0))
        history = tk.Frame(notebook, bg=WHITE)
        log_page = tk.Frame(notebook, bg=WHITE)
        notebook.add(history, text='  历史测试记录  ')
        notebook.add(log_page, text='  本次执行日志  ')
        self.notebook = notebook
        self.label(history, '内置历史与本机测试分开标注。Root 成功与五分钟观察通过分别记录。',
                   size=9, color=MUTED, anchor='w').pack(fill='x', padx=10, pady=(7, 4))
        tree_frame = tk.Frame(history, bg=WHITE)
        tree_frame.pack(fill='both', expand=True, padx=10)
        columns = ('source', 'model', 'build', 'root', 'module', 'five', 'date')
        self.history_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=4, selectmode='browse')
        for key, title, width in [('source', '来源', 85), ('model', '型号', 95), ('build', '固件', 150),
                                  ('root', 'Root', 75), ('module', 'KernelSU', 90),
                                  ('five', '五分钟观察', 125), ('date', '测试时间', 170)]:
            self.history_tree.heading(key, text=title)
            self.history_tree.column(key, width=width, minwidth=55, stretch=True)
        vertical = ttk.Scrollbar(tree_frame, command=self.history_tree.yview)
        horizontal = ttk.Scrollbar(history, orient='horizontal', command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        self.history_tree.pack(side='left', fill='both', expand=True)
        horizontal.pack(fill='x', padx=10)
        self.history_detail = self.label(history, '选择记录可查看完整内核、配置和测试说明。',
                                         size=9, color=MUTED, anchor='w', justify='left', wraplength=890)
        self.history_detail.pack(fill='x', padx=10, pady=(4, 7))
        self.history_tree.bind('<<TreeviewSelect>>', self.select_history)
        self.log = tk.Text(log_page, height=6, bg=WHITE, fg='#334155', relief='flat', bd=0,
                           padx=10, pady=8, font=(FONT, 9), wrap='word', state='disabled')
        scroll = ttk.Scrollbar(log_page, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        self.bind('<Configure>', self.resize_wrap)
        self.update_buttons()

    def resize_wrap(self, event):
        if event.widget is self:
            for label in (self.kernel_note, self.match_note, self.help_line, self.risk_line, self.banner, self.history_detail):
                label.configure(wraplength=max(400, event.width - 100))

    def reload_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        self.history_items.clear()
        try:
            rows, errors = history_rows(ROOT)
            for index, row in enumerate(rows):
                key = str(index)
                self.history_items[key] = row
                env = row.get('environment', {})
                outcome = ('未进行' if row.get('observation_mode') == 'immediate' else
                           '通过' if row.get('five_minute_passed') else '有异常/未通过' if row.get('root_verified') else '未完成')
                self.history_tree.insert('', 'end', iid=key, values=(
                    '内置历史' if row['source'] == 'builtin' else '本机测试',
                    env.get('hardware_device', ''), env.get('build', ''),
                    '已取得' if row.get('root_verified') else '未确认',
                    '已加载' if row.get('kernelsu_loaded') else '未确认', outcome,
                    row.get('tested_at', '').replace('T', ' ')[:19]))
            if errors:
                self.append('部分历史文件无法读取：' + '; '.join(errors))
            if rows:
                self.history_tree.selection_set('0')
                self.select_history()
        except Exception as exc:
            self.history_detail.configure(text='历史记录读取失败：' + str(exc), fg=RED)

    def select_history(self, event=None):
        selected = self.history_tree.selection()
        if not selected:
            return
        row = self.history_items[selected[0]]
        self.history_detail.configure(text='内核：' + row.get('environment', {}).get('kernel', '未记录')
            + '\n配置：' + row.get('profile_id', '未记录') + '；' + row.get('note', '')
            + ('\n本机日志：' + row['log_directory'] if row.get('log_directory') else ''), fg=MUTED)

    def append(self, value):
        self.log.configure(state='normal')
        self.log.insert('end', value.rstrip() + '\n')
        if int(self.log.index('end-1c').split('.')[0]) > 550:
            self.log.delete('1.0', '120.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def update_buttons(self):
        ready = not self.busy and bool(self.phone and self.phone.get('connected'))
        rooted = bool(ready and self.phone.get('rooted'))
        self.refresh_btn.configure(state='disabled' if self.busy else 'normal')
        self.restore_display_btn.configure(state='disabled' if self.busy and not self.unlock_pending else 'normal')
        self.ack_box.configure(state='disabled' if self.busy else 'normal')
        self.root_btn.configure(state='normal' if not self.busy and execution_available(
            self.phone, self.acknowledged.get()) else 'disabled', text='Root 已就绪' if rooted else '执行一次 Root')
        self.hide_btn.configure(state='normal' if rooted and self.phone.get('navigation_mode') == '2'
                                 and self.phone.get('pill_known') and self.phone.get('pill_supported') else 'disabled')
        self.show_btn.configure(state='normal' if rooted and self.phone.get('pill_known')
                                 and self.phone.get('pill_supported') else 'disabled')

    def display_state(self, state):
        self.phone = state
        self.acknowledged.set(False)
        env, decision = state['environment'], state['assessment']
        self.connection.configure(text=(env.get('hardware_device') or env.get('model') or 'Android 手机') + ' 已连接', fg=INK)
        self.device_note.configure(text='Android ' + (env.get('android_release') or env.get('android_api', '?'))
            + '  ·  ' + env.get('build', '未知固件')
            + ('  ·  当前锁屏' if state.get('locked') else '  ·  已解锁'))
        self.kernel_note.configure(text='完整内核：' + env.get('kernel', '未读到'))
        self.patch_note.configure(text='安全补丁：' + (env.get('security_patch') or '未读到')
            + '  ·  ABI：' + (env.get('abi') or '未读到') + '  ·  API：' + env.get('android_api', '?'))
        self.values['root'].configure(text='已取得 Root' if state['rooted'] else '尚未取得', fg=GREEN if state['rooted'] else AMBER)
        self.values['module'].configure(text='模块已加载' if state['kernelsu_loaded'] else
            state['manager']['label'] if state.get('modules_known') else '模块状态未确认',
            fg=GREEN if state['kernelsu_loaded'] else MUTED)
        self.values['pill'].configure(text='未确认' if not state.get('pill_known') else '已隐藏' if state['hidden']
            else '显示中' if state['navigation_mode'] == '2' else '非手势导航', fg=BLUE if state['hidden'] else INK)
        color = GREEN if decision['level'] == 'recorded_build' else AMBER
        self.match_note.configure(text=decision['message'], fg=color)
        self.ack_box.pack_forget()
        if decision['eligible'] and decision['requires_acknowledgement'] and not state['rooted']:
            self.ack_box.pack(fill='x', after=self.match_note, pady=(3, 0))
        if state['kernelsu_loaded'] and not state['rooted']:
            self.help_line.configure(text='KernelSU 已加载但 Shell 未获授权，请在手机管理器检查授权后刷新。', fg=AMBER)
        elif not state.get('modules_known'):
            self.help_line.configure(text='未能确认内核模块状态，执行程序可能返回检查错误。详见日志。', fg=AMBER)
        elif state.get('selinux') != 'Enforcing':
            self.help_line.configure(text='SELinux 状态未确认或不是 Enforcing，原生执行流程可能停止并返回错误。', fg=AMBER)
        else:
            self.help_line.configure(text='Root 可能失败或重启。每次开机最多一次尝试，不会自动重试。隐藏小白条需要 Root。', fg=MUTED)
        for item in state.get('diagnostics', []):
            self.append('检测项未确认：' + item['command'] + '；' + item['error'])
        self.update_buttons()

    def start(self, action):
        if self.busy:
            return
        if action == 'root' and not execution_available(self.phone, self.acknowledged.get()):
            self.banner.configure(text='请先连接并检测手机；已有 Root 或已加载 KernelSU 时跳过重复激活。', fg=AMBER)
            return
        runtime = ROOT / 'runtime' / 'python.exe'
        if not runtime.is_file():
            self.banner.configure(text='缺少运行文件。请解压并保留整个工具文件夹。', fg=RED)
            return
        args = [str(runtime), '-B', '-u', '-X', 'utf8']
        if action == 'root':
            folder = ROOT / 'logs' / ('selection-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            folder.mkdir(parents=True)
            confirmation = folder / 'execution-choice.json'
            confirmation.write_text(json.dumps(make_confirmation(self.phone, self.acknowledged.get()),
                                               ensure_ascii=False, indent=2), encoding='utf-8')
            args += [str(ROOT / 'scripts' / 'one_click.py'), '--gui', '--confirmation', str(confirmation)]
        else:
            args += [str(ROOT / 'scripts' / 'gui_bridge.py'), action]
        self.busy, self.unlock_pending = True, False
        self.update_buttons()
        labels = {'status': '正在读取手机信息和测试记录…', 'root': '正在复核你选择执行的手机环境…',
                  'hide': '正在隐藏小白条并核验…', 'show': '正在恢复小白条并核验…',
                  'restore-display': '正在检查临时亮屏设置…'}
        self.banner.configure(text=labels[action], fg=BLUE)
        self.append('[' + datetime.datetime.now().strftime('%H:%M:%S') + '] ' + labels[action])
        self.progress.configure(mode='indeterminate', value=0)
        self.progress.start(12)
        if action != 'status':
            self.notebook.select(1)
        threading.Thread(target=self.worker, args=(action, args), daemon=True).start()

    def worker(self, action, args):
        result, log_path, captured = None, None, []
        try:
            process = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self.child = process
            for line in process.stdout:
                captured.append(line)
                if line.startswith('@@UI '):
                    event = json.loads(line[5:])
                    if event.get('event') == 'log_directory':
                        candidate = Path(event['path']).resolve()
                        if candidate.is_relative_to((ROOT / 'logs').resolve()):
                            log_path = candidate
                    self.events.put(('ui', event))
                elif line.startswith('@@RESULT '):
                    result = json.loads(line[9:])
                else:
                    self.events.put(('line', line))
            code = process.wait()
            process.stdout.close()
            process.stdin.close()
            if log_path:
                (log_path / 'gui-worker-console.txt').write_text(''.join(captured), encoding='utf-8')
            if action == 'root' and log_path and (log_path / 'result.json').is_file():
                result = json.loads((log_path / 'result.json').read_text(encoding='utf-8'))
            self.events.put(('done', {'action': action, 'code': code, 'result': result}))
        except Exception as exc:
            self.events.put(('line', traceback.format_exc()))
            self.events.put(('done', {'action': action, 'code': 2, 'result': {'ok': False, 'error': str(exc)}}))

    def continue_unlock(self):
        if self.child and self.unlock_pending:
            try:
                self.child.stdin.write('\n')
                self.child.stdin.flush()
                self.unlock_pending = False
                self.continue_btn.pack_forget()
                self.cancel_btn.pack_forget()
                self.update_buttons()
                self.banner.configure(text='正在重新核对解锁和手机状态…', fg=BLUE)
            except (OSError, ValueError) as exc:
                self.append('继续失败：' + str(exc))

    def restore_or_cancel_display(self):
        if self.unlock_pending:
            self.cancel_unlock()
        else:
            self.start('restore-display')

    def cancel_unlock(self):
        if self.child and self.unlock_pending:
            try:
                self.child.stdin.write('cancel\n')
                self.child.stdin.flush()
                self.unlock_pending = False
                self.continue_btn.pack_forget()
                self.cancel_btn.pack_forget()
                self.update_buttons()
                self.banner.configure(text='已请求取消，正在恢复原亮屏设置…', fg=BLUE)
            except (OSError, ValueError) as exc:
                self.append('取消失败：' + str(exc))

    def consume(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'line':
                    self.append(value)
                elif kind == 'ui':
                    if value.get('event') == 'unlock':
                        self.unlock_pending = True
                        self.banner.configure(text='请解锁手机并保持桌面可见，然后点击继续。', fg=AMBER)
                        self.continue_btn.pack(anchor='w', pady=(7, 0))
                        self.cancel_btn.pack(anchor='w', pady=(5, 0))
                        self.update_buttons()
                    elif value.get('event') == 'log_directory':
                        candidate = Path(value['path']).resolve()
                        if candidate.is_relative_to((ROOT / 'logs').resolve()):
                            self.current_logs = candidate
                elif kind == 'done':
                    self.finish(value)
        except queue.Empty:
            pass
        self.after(100, self.consume)

    def finish(self, done):
        self.busy, self.child, self.unlock_pending = False, None, False
        self.continue_btn.pack_forget()
        self.cancel_btn.pack_forget()
        self.progress.stop()
        result = done.get('result') or {'ok': False, 'error': '进程未返回完整结果，请查看日志。'}
        action = done['action']
        if action == 'status':
            if result.get('ok'):
                self.display_state(result['state'])
                message, color = self.saved_banner or ('检测完成，先查看匹配情况和历史记录。', GREEN)
            else:
                self.phone = None
                self.acknowledged.set(False)
                self.ack_box.pack_forget()
                self.connection.configure(text='手机连接待确认', fg=AMBER)
                self.device_note.configure(text='请检查连接和 USB 调试授权。')
                self.kernel_note.configure(text='完整内核：待检测')
                self.patch_note.configure(text='安全补丁：待检测')
                self.match_note.configure(text='尚未取得当前手机信息。', fg=MUTED)
                for label in self.values.values():
                    label.configure(text='未确认', fg=MUTED)
                message, color = result.get('error', '未连接手机'), AMBER
            self.saved_banner = None
        elif action == 'root':
            message, color = root_summary(result)
            if result.get('display_restore_error') and result.get('outcome') != 'cancelled':
                message += ' 原亮屏设置恢复失败，重新连接后请点击取消常亮。'
                color = AMBER
            if result.get('history_error'):
                message += ' 历史写入失败，完整日志已保留。'
                color = AMBER
            self.saved_banner = (message, color)
        else:
            message, color = (result.get('message', '操作完成。'), GREEN) if result.get('ok') else (result.get('error', '操作未完成。'), RED)
            if result.get('state'):
                self.display_state(result['state'])
            self.saved_banner = (message, color)
        self.banner.configure(text=message, fg=color)
        self.append(message)
        self.reload_history()
        self.update_buttons()
        if action != 'status':
            self.after(350, lambda: self.start('status'))

    def open_logs(self):
        self.current_logs.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.current_logs))

    def open_help(self):
        os.startfile(str(ROOT / '使用说明.txt'))

    def close_app(self):
        if self.unlock_pending:
            self.cancel_unlock()
            return
        if self.busy:
            messagebox.showinfo('任务仍在运行', '请等待当前任务结束再关闭窗口。你可以先最小化。', parent=self)
            return
        self.destroy()


def self_test(window):
    """Widget tests use fixtures only: no device commands and no worker process."""
    window.withdraw()
    from registry import assess
    env = {'hardware_device': 'SO-51D', 'model': 'SO-51D', 'android_api': '35', 'android_release': '15',
           'kernel': '5.15.170-android13-8-00015-g52ccd9134339-ab12915929', 'owner_user': '0',
           'boot_completed': '1', 'build': '67.2.A.3.55 release-keys', 'fingerprint': 'fixture',
           'security_patch': '2025-01-01', 'abi': 'arm64-v8a'}
    fixture = {'connected': True, 'compatible': True, 'rooted': False, 'kernelsu_loaded': False,
               'environment': env, 'manager': {'label': '未安装'}, 'assessment': assess(env, ROOT),
               'navigation_mode': '2', 'hidden': False, 'locked': False, 'pill_known': True,
               'modules_known': True, 'selinux': 'Enforcing', 'boot_id': 'fixture-boot', 'pill_supported': True}
    actions = []
    window.start = actions.append
    window.display_state(fixture)
    assert str(window.root_btn['state']) == 'normal'
    window.root_btn.invoke()
    env['build'] = '67.2.A.3.115 release-keys'
    fixture['assessment'] = assess(env, ROOT)
    window.display_state(fixture)
    assert str(window.root_btn['state']) == 'normal'
    window.root_btn.invoke()
    window.display_state(fixture)
    assert not window.acknowledged.get() and str(window.root_btn['state']) == 'normal'
    env['kernel'] = '5.15.170-other-build'
    fixture.update(assessment=assess(env, ROOT), compatible=False)
    window.display_state(fixture)
    window.acknowledged.set(True)
    window.update_buttons()
    assert str(window.root_btn['state']) == 'normal'
    window.root_btn.invoke()
    env['kernel'] = '5.15.170-android13-8-00015-g52ccd9134339-ab12915929'
    fixture.update(assessment=assess(env, ROOT), compatible=True, rooted=True, kernelsu_loaded=True)
    window.display_state(fixture)
    assert str(window.root_btn['state']) == 'disabled'
    assert str(window.hide_btn['state']) == 'normal'
    window.hide_btn.invoke()
    window.show_btn.invoke()
    window.refresh_btn.invoke()
    window.restore_display_btn.invoke()
    assert actions == ['root', 'root', 'root', 'hide', 'show', 'status', 'restore-display']
    import io
    from types import SimpleNamespace
    stream = io.StringIO()
    window.child = SimpleNamespace(stdin=stream)
    window.busy, window.unlock_pending = True, True
    window.update_buttons()
    assert str(window.restore_display_btn['state']) == 'normal'
    window.restore_display_btn.invoke()
    assert stream.getvalue() == 'cancel\n'
    assert not window.unlock_pending
    window.busy, window.child = False, None
    env.update(hardware_device='XQ-DQ72', model='XQ-DQ72', kernel='5.15.189-android13-8-00016-g51bba4309aac-ab14546557')
    fixture.update(assessment=assess(env, ROOT), compatible=False, pill_supported=True)
    window.display_state(fixture)
    assert str(window.hide_btn['state']) == 'normal'
    assert str(window.show_btn['state']) == 'normal'
    fixture.update(pill_supported=False)
    window.display_state(fixture)
    assert str(window.hide_btn['state']) == 'disabled'
    assert str(window.show_btn['state']) == 'disabled'
    fixture.update(rooted=False, kernelsu_loaded=True)
    window.display_state(fixture)
    assert str(window.root_btn['state']) == 'disabled'
    window.busy = True
    window.update_buttons()
    assert all(str(w['state']) == 'disabled' for w in (window.root_btn, window.hide_btn, window.show_btn,
                                                     window.refresh_btn, window.ack_box))
    window.busy = False
    window.append('自检完成：检测、勾选、历史记录和按钮状态。')
    window.deiconify()
    window.update()
    geometry = {}
    for name in ('root_btn', 'hide_btn', 'show_btn', 'refresh_btn', 'risk_line', 'log', 'banner', 'history_tree', 'history_detail'):
        widget = getattr(window, name)
        if not widget.winfo_ismapped():
            continue
        geometry[name] = {'width': widget.winfo_width(), 'height': widget.winfo_height(),
                          'y': widget.winfo_rooty() - window.winfo_rooty()}
        assert geometry[name]['width'] > 10 and geometry[name]['height'] > 10, name
        assert geometry[name]['y'] + geometry[name]['height'] <= window.winfo_height(), name
    report = {'ok': True, 'frozen_exe': bool(getattr(sys, 'frozen', False)), 'device_commands_executed': 0,
              'button_routes': actions, 'unknown_build_can_attempt_without_checkbox': True,
              'unknown_kernel_can_attempt': True, 'risk_notice_visible': True,
              'already_rooted_guard': True, 'layout': geometry}
    report['cancel_unlock_restores_display_request'] = True
    (ROOT / 'logs').mkdir(exist_ok=True)
    (ROOT / 'logs' / 'exe-ui-self-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    window.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    guard = None
    try:
        import msvcrt
        guard = (ROOT / 'gui.lock').open('a+b')
        if os.fstat(guard.fileno()).st_size == 0:
            guard.write(b'0')
            guard.flush()
        guard.seek(0)
        try:
            msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('这个版本的工具箱已经打开，请回到原窗口。') from exc
        if '--self-test' in sys.argv:
            self_test(App(auto_check=False))
        else:
            App().mainloop()
    except Exception as exc:
        (ROOT / 'gui-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        if '--self-test' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, str(exc), TITLE, 0x10)
        return 2
    finally:
        if guard is not None:
            guard.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
