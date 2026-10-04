"""Xperia toolbox: a compact home, verified state, and separate technical detail pages."""
import ctypes
import datetime
import json
import os
from pathlib import Path
import queue
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

BG, WHITE, INK, MUTED = '#f3f5f9', '#ffffff', '#18243b', '#64748b'
BLUE, GREEN, AMBER, RED = '#2563eb', '#15803d', '#a16207', '#b91c1c'
FONT = 'Microsoft YaHei UI'
TITLE = 'Xperia 工具箱 · 1.3.3 状态与界面修正版'
POLL_MS = 15000


class App(tk.Tk):
    def __init__(self, auto_check=True):
        super().__init__()
        self.title(TITLE)
        scale = max(1.0, self.winfo_fpixels('1i') / 96.0)
        width = min(round(1000 * scale), self.winfo_screenwidth() - 50)
        height = min(round(790 * scale), self.winfo_screenheight() - 70)
        self.geometry(f'{width}x{height}')
        self.minsize(min(round(720 * scale), width), min(round(580 * scale), height))
        self.configure(bg=BG)
        try:
            self.iconbitmap(str(ROOT / 'gui/app.ico'))
        except tk.TclError:
            pass
        self.events = queue.Queue()
        self.busy = self.polling = self.unlock_pending = False
        self.child = None
        self.phone = None
        self.queued_action = None
        self.current_logs = ROOT / 'logs'
        self.history_items = {}
        self.keep_awake = tk.BooleanVar(value=False)
        self.acknowledged = tk.BooleanVar(value=False)
        self.auto_check = auto_check
        self.display_last_result = '尚未执行常亮操作'
        self._build()
        self.reload_history()
        self.protocol('WM_DELETE_WINDOW', self.close_app)
        self.after(100, self.consume)
        if auto_check:
            self.after(250, lambda: self.start('status'))
            self.after(POLL_MS, self.poll_status)

    def label(self, parent, text, size=10, color=INK, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=(FONT, size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, font=(FONT, 10, 'bold'),
                         bg=BLUE if primary else '#edf2fd', fg=WHITE if primary else BLUE,
                         activebackground='#1d4ed8' if primary else '#dfe8fb',
                         activeforeground=WHITE if primary else BLUE, disabledforeground='#94a3b8',
                         relief='flat', bd=0, cursor='hand2', padx=14, pady=9, takefocus=True)

    def card(self, parent, title, subtitle=None):
        card = tk.Frame(parent, bg=WHITE, padx=16, pady=12, highlightbackground='#e2e8f0', highlightthickness=1)
        self.label(card, title, size=12, bold=True).pack(anchor='w')
        if subtitle:
            self.label(card, subtitle, size=9, color=MUTED, anchor='w', justify='left').pack(fill='x', pady=(3, 7))
        return card

    def _build(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', font=(FONT, 10), padding=(18, 9), background=BG, foreground=MUTED)
        style.map('TNotebook.Tab', background=[('selected', WHITE)], foreground=[('selected', BLUE)])
        style.configure('TProgressbar', background=BLUE, troughcolor='#e2e8f0', borderwidth=0)
        style.configure('Treeview', font=(FONT, 9), rowheight=30, background=WHITE, fieldbackground=WHITE)
        style.configure('Treeview.Heading', font=(FONT, 9, 'bold'), background='#eef2f7')
        top = tk.Frame(self, bg=BG)
        top.pack(fill='x', padx=20, pady=(15, 12))
        right = tk.Frame(top, bg=BG)
        right.pack(side='right')
        self.label(right, '1.3.3 · 状态与界面修正版', size=9, color=MUTED).pack(anchor='e')
        self.refresh_btn = self.button(right, '刷新状态', lambda: self.start('status'))
        self.refresh_btn.pack(anchor='e', pady=(4, 0))
        self.label(top, 'Xperia 工具箱', size=21, bold=True).pack(anchor='w')
        self.connection = self.label(top, '等待连接手机', size=10, color=MUTED)
        self.connection.pack(anchor='w', pady=(4, 0))

        footer = tk.Frame(self, bg=BG)
        footer.pack(side='bottom', fill='x', padx=20, pady=(6, 10))
        self.checked_note = self.label(footer, '尚未核验 · 空闲时每 15 秒自动刷新', size=9, color=MUTED)
        self.checked_note.pack(side='left')
        for text, fn in (('使用说明', self.open_help), ('日志文件夹', self.open_logs)):
            tk.Button(footer, text=text, command=fn, bg=BG, fg=BLUE, relief='flat',
                      font=(FONT, 9), cursor='hand2', padx=8).pack(side='right')

        self.task_card = tk.Frame(self, bg=WHITE, padx=14, pady=10, highlightthickness=1,
                                  highlightbackground='#e2e8f0')
        self.task_card.pack(side='bottom', fill='x', padx=20, pady=(8, 0))
        line = tk.Frame(self.task_card, bg=WHITE)
        line.pack(fill='x')
        self.stage_note = self.label(line, '准备就绪', size=9, color=BLUE, bold=True)
        self.stage_note.pack(side='left')
        tk.Button(line, text='查看执行日志 →', command=lambda: self.notebook.select(self.log_page),
                  bg=WHITE, fg=BLUE, relief='flat', font=(FONT, 9), cursor='hand2').pack(side='right')
        self.banner = self.label(self.task_card, '连接 USB，允许手机上的调试授权，然后刷新状态。',
                                 size=10, anchor='w', justify='left', wraplength=900)
        self.banner.pack(fill='x', pady=(3, 0))
        self.progress = ttk.Progressbar(self.task_card, mode='indeterminate')
        self.unlock_actions = tk.Frame(self.task_card, bg=WHITE)
        self.continue_btn = self.button(self.unlock_actions, '手机已解锁，继续', self.continue_unlock, True)
        self.continue_btn.pack(side='left')
        self.cancel_btn = self.button(self.unlock_actions, '取消本次操作', self.cancel_unlock)
        self.cancel_btn.pack(side='left', padx=(8, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=20)
        self.home_page = tk.Frame(self.notebook, bg=BG)
        self.details_page = tk.Frame(self.notebook, bg=BG)
        self.history_page = tk.Frame(self.notebook, bg=WHITE)
        self.log_page = tk.Frame(self.notebook, bg=WHITE)
        for page, title in ((self.home_page, '首页'), (self.details_page, '设备详情'),
                            (self.history_page, '历史记录'), (self.log_page, '执行日志')):
            self.notebook.add(page, text=title)
        self.home_canvas = tk.Canvas(self.home_page, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.home_page, orient='vertical', command=self.home_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.home_canvas.pack(side='left', fill='both', expand=True)
        self.home_canvas.configure(yscrollcommand=scrollbar.set)
        self.home_content = tk.Frame(self.home_canvas, bg=BG)
        self.home_window = self.home_canvas.create_window(0, 0, window=self.home_content, anchor='nw')
        self.home_content.bind('<Configure>', lambda e: self.home_canvas.configure(scrollregion=self.home_canvas.bbox('all')))
        self.home_canvas.bind('<Configure>', self.resize_home)
        self.bind_all('<MouseWheel>', self.scroll_home)

        states = tk.Frame(self.home_content, bg=BG)
        states.pack(fill='x', pady=(12, 10))
        self.values = {}
        for index, (key, name) in enumerate((('root', 'Root 权限'), ('module', 'KernelSU'), ('pill', '底部小白条'))):
            card = tk.Frame(states, bg=WHITE, padx=14, pady=11, highlightthickness=1, highlightbackground='#e2e8f0')
            states.columnconfigure(index, weight=1, uniform='badges')
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0 if index == 2 else 5))
            self.label(card, name, size=9, color=MUTED).pack(anchor='w')
            self.values[key] = self.label(card, '待检测', size=12, bold=True)
            self.values[key].pack(anchor='w', pady=(4, 0))

        actions = tk.Frame(self.home_content, bg=BG)
        actions.pack(fill='x')
        actions.columnconfigure(0, weight=1, uniform='operations')
        actions.columnconfigure(1, weight=1, uniform='operations')
        root = self.card(actions, '临时 Root')
        root.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        self.root_btn = self.button(root, '执行一次 Root', lambda: self.start('root'), True)
        self.root_btn.pack(fill='x', pady=(9, 6))
        self.awake_box = tk.Checkbutton(root, text='操作期间保持 USB 充电常亮', variable=self.keep_awake,
                                       bg=WHITE, activebackground=WHITE, fg=INK, font=(FONT, 9),
                                       anchor='w', wraplength=360, justify='left')
        self.awake_box.pack(fill='x')
        self.label(root, '默认不修改常亮；勾选后结束时恢复。', size=9, color=MUTED).pack(anchor='w', pady=(3, 0))
        pill = self.card(actions, '小白条', '保留手势导航，只调整底部手势条显示。')
        pill.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        row = tk.Frame(pill, bg=WHITE)
        row.pack(fill='x', pady=(3, 6))
        self.hide_btn = self.button(row, '隐藏', lambda: self.start('hide'))
        self.show_btn = self.button(row, '恢复显示', lambda: self.start('show'))
        self.hide_btn.pack(side='left', fill='x', expand=True, padx=(0, 4))
        self.show_btn.pack(side='left', fill='x', expand=True, padx=(4, 0))
        self.pill_hint = self.label(pill, '连接手机并取得 Root 后可操作。', size=9, color=MUTED,
                                    anchor='w', justify='left', wraplength=360)
        self.pill_hint.pack(fill='x')
        self.help_line = self.label(self.home_content, 'Root 可能失败、卡死或重启；每次开机最多尝试一次。',
                                    size=9, color=AMBER, anchor='w', justify='left', wraplength=900)
        self.help_line.pack(fill='x', pady=(7, 9))

        display = self.card(self.home_content, '充电常亮')
        display.pack(fill='x', pady=(0, 12))
        self.display_value = self.label(display, '状态未知', size=14, bold=True)
        self.display_value.pack(anchor='w', pady=(5, 2))
        self.label(display, '开启后仅在 USB 供电时保持唤醒，不会点亮屏幕或自动解锁。',
                   size=9, color=MUTED, anchor='w').pack(fill='x')
        row = tk.Frame(display, bg=WHITE)
        row.pack(fill='x', pady=(10, 7))
        self.display_enable_btn = self.button(row, '开启 USB 常亮', lambda: self.start('display-enable'))
        self.display_disable_btn = self.button(row, '关闭充电常亮', lambda: self.start('display-disable'))
        self.display_restore_btn = self.button(row, '恢复原设置', lambda: self.start('display-restore'))
        for button in (self.display_enable_btn, self.display_disable_btn, self.display_restore_btn):
            button.pack(side='left', padx=(0, 8))
        self.display_baseline = self.label(display, '尚无手动修改的恢复记录', size=9, color=MUTED, anchor='w')
        self.display_baseline.pack(fill='x')
        self.display_result = self.label(display, self.display_last_result, size=9, color=MUTED,
                                         anchor='w', justify='left', wraplength=870)
        self.display_result.pack(fill='x', pady=(4, 0))
        self.display_warning = self.label(display, '', size=9, color=AMBER, anchor='w', justify='left', wraplength=870)
        self.restore_display_btn = self.button(display, '恢复临时设置', lambda: self.start('restore-display'))

        detail = self.card(self.details_page, '手机与配置详情')
        detail.pack(fill='both', expand=True, pady=12)
        self.detail_text = tk.Text(detail, bg=WHITE, fg=INK, relief='flat', font=(FONT, 10),
                                   wrap='word', padx=0, pady=10, state='disabled')
        detail_scroll = ttk.Scrollbar(detail, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side='right', fill='y')
        self.detail_text.pack(fill='both', expand=True)

        self.label(self.history_page, 'Root 结果与观察结果分别记录；本机记录不会自动上传。',
                   size=9, color=MUTED).pack(anchor='w', padx=12, pady=(12, 8))
        tree_frame = tk.Frame(self.history_page, bg=WHITE)
        tree_frame.pack(fill='both', expand=True, padx=12)
        columns = ('source', 'model', 'build', 'root', 'module', 'five', 'date')
        self.history_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        for key, title, width in (('source', '来源', 85), ('model', '型号', 95), ('build', '固件', 135),
                                  ('root', 'Root', 75), ('module', 'KernelSU', 85),
                                  ('five', '五分钟观察', 110), ('date', '测试时间', 150)):
            self.history_tree.heading(key, text=title)
            self.history_tree.column(key, width=width, minwidth=55)
        vertical = ttk.Scrollbar(tree_frame, command=self.history_tree.yview)
        horizontal = ttk.Scrollbar(self.history_page, orient='horizontal', command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side='right', fill='y')
        self.history_tree.pack(side='left', fill='both', expand=True)
        horizontal.pack(fill='x', padx=12)
        self.history_detail = self.label(self.history_page, '选择一条记录查看详情。', size=9, color=MUTED,
                                         anchor='w', justify='left', wraplength=900)
        self.history_detail.pack(fill='x', padx=12, pady=(8, 12))
        self.history_tree.bind('<<TreeviewSelect>>', self.select_history)
        self.log = tk.Text(self.log_page, bg=WHITE, fg='#334155', relief='flat', font=(FONT, 9),
                           wrap='word', padx=12, pady=12, state='disabled')
        log_scroll = ttk.Scrollbar(self.log_page, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        self.bind('<Configure>', self.resize_wrap)
        self.update_buttons()

    def resize_home(self, event):
        self.home_canvas.itemconfigure(self.home_window, width=event.width)
        self.awake_box.configure(wraplength=max(200, event.width // 2 - 65))
        self.pill_hint.configure(wraplength=max(200, event.width // 2 - 65))

    def resize_wrap(self, event):
        if event.widget is self:
            for label in (self.help_line, self.banner, self.history_detail, self.display_result, self.display_warning):
                label.configure(wraplength=max(300, event.width - 100))

    def scroll_home(self, event):
        if self.notebook.select() == str(self.home_page) and self.home_content.winfo_height() > self.home_canvas.winfo_height():
            self.home_canvas.yview_scroll(-int(event.delta / 120), 'units')

    def reload_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        self.history_items.clear()
        try:
            rows, errors = history_rows(ROOT)
            for index, row in enumerate(rows):
                key = str(index)
                self.history_items[key] = row
                env = row.get('environment', {})
                observed = ('未进行' if row.get('observation_mode') == 'immediate' else '通过' if row.get('five_minute_passed')
                            else '有异常/未通过' if row.get('root_verified') else '未完成')
                self.history_tree.insert('', 'end', iid=key, values=(
                    '内置历史' if row['source'] == 'builtin' else '本机测试', env.get('hardware_device', ''),
                    env.get('build', ''), '已取得' if row.get('root_verified') else '未确认',
                    '已加载' if row.get('kernelsu_loaded') else '未确认', observed,
                    row.get('tested_at', '').replace('T', ' ')[:19]))
            if errors:
                self.append('部分历史无法读取：' + '; '.join(errors))
            if rows:
                self.history_tree.selection_set('0')
                self.select_history()
        except Exception as exc:
            self.history_detail.configure(text='历史记录读取失败：' + str(exc), fg=RED)

    def select_history(self, event=None):
        selected = self.history_tree.selection()
        if selected:
            row = self.history_items[selected[0]]
            self.history_detail.configure(text='内核：' + row.get('environment', {}).get('kernel', '未记录')
                + '\n配置：' + row.get('profile_id', '未记录') + '；' + row.get('note', '')
                + ('\n日志：' + row['log_directory'] if row.get('log_directory') else ''), fg=MUTED)

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
        display = (self.phone or {}).get('display', {})
        self.refresh_btn.configure(state='disabled' if self.busy else 'normal')
        self.awake_box.configure(state='disabled' if self.busy else 'normal')
        self.root_btn.configure(state='normal' if not self.busy and execution_available(self.phone) else 'disabled',
                                text='Root 已就绪' if rooted else '执行一次 Root')
        pill = bool(rooted and self.phone.get('pill_known') and self.phone.get('pill_supported') and not self.phone.get('locked'))
        self.hide_btn.configure(state='normal' if pill and self.phone.get('navigation_mode') == '2' else 'disabled')
        self.show_btn.configure(state='normal' if pill else 'disabled')
        for button in (self.display_enable_btn, self.display_disable_btn):
            button.configure(state='normal' if ready and display.get('known') else 'disabled')
        self.display_restore_btn.configure(state='normal' if ready and display.get('manual_restore_available') else 'disabled')
        self.restore_display_btn.configure(state='normal' if ready and display.get('temporary_restore_available') else 'disabled')

    def display_charging(self, state):
        if self.phone is not None:
            self.phone['display'] = state
        self.display_value.configure(text=state.get('label', '状态未知'), fg=INK if state.get('known') else AMBER)
        baseline = ('可恢复到：' + state.get('baseline_label', '未知') if state.get('manual_restore_available')
                    else '没有本工具的手动待恢复记录')
        self.display_baseline.configure(text=baseline)
        notices = []
        if state.get('error'):
            notices.append('当前设置读取失败，不影响 Root。')
        if state.get('temporary_restore_available'):
            notices.append('有 Root 临时常亮待恢复；手动恢复记录独立保留。')
        if state.get('legacy_restore_pending'):
            notices.append('旧版记录未绑定手机，请确认连接的是原手机后恢复。')
        if state.get('recovery_error'):
            notices.append(state['recovery_error'])
        self.display_warning.pack_forget()
        self.restore_display_btn.pack_forget()
        if notices:
            self.display_warning.configure(text=' '.join(notices))
            self.display_warning.pack(fill='x', pady=(5, 0))
        if state.get('temporary_restore_available'):
            self.restore_display_btn.pack(anchor='w', pady=(7, 0))
        self.update_buttons()

    def display_state(self, state):
        self.phone = state
        env, assessment = state['environment'], state['assessment']
        name = env.get('hardware_device') or env.get('model') or 'Android 手机'
        self.connection.configure(text=name + ' 已连接  ·  Android ' + env.get('android_release', env.get('android_api', '?'))
                                  + ('  ·  已锁屏' if state.get('locked') else '  ·  已解锁'), fg=INK)
        self.values['root'].configure(text='已取得 Root' if state['rooted'] else '尚未取得', fg=GREEN if state['rooted'] else MUTED)
        self.values['module'].configure(text='模块已加载' if state['kernelsu_loaded'] else
            state['manager']['label'] if state.get('modules_known') else '状态未知', fg=GREEN if state['kernelsu_loaded'] else MUTED)
        self.values['pill'].configure(text='状态未知' if not state.get('pill_known') else '已隐藏' if state['hidden']
                                     else '显示中' if state['navigation_mode'] == '2' else '非手势导航', fg=BLUE if state['hidden'] else INK)
        if state['kernelsu_loaded'] and not state['rooted']:
            self.help_line.configure(text='KernelSU 已加载，Shell 尚未授权。请在手机管理器授权后刷新。', fg=AMBER)
        elif state['rooted']:
            self.help_line.configure(text='Root 已就绪，已跳过重复激活。完整重启后临时 Root 会消失。', fg=GREEN)
        else:
            self.help_line.configure(text='Root 可能失败、卡死或重启；每次开机最多尝试一次，不会自动重试。', fg=AMBER)
        self.pill_hint.configure(text='请先解锁手机。' if state.get('locked') else
                                  '当前不是手势导航，隐藏功能不可用。' if state.get('navigation_mode') != '2' else
                                  '需要 Root 与手机的资源覆盖接口。' if not state['rooted'] else '可隐藏或恢复手势条。')
        self.display_charging(state.get('display', {'known': False, 'label': '状态未知'}))
        checked = state.get('checked_at') or datetime.datetime.now().astimezone().isoformat()
        self.checked_note.configure(text='最近核验 ' + checked[11:19] + ' · 空闲时每 15 秒自动刷新', fg=MUTED)
        lines = [('型号', env.get('model')), ('设备', env.get('hardware_device')), ('Android', env.get('android_release')),
                 ('固件', env.get('build')), ('完整内核', env.get('kernel')), ('安全补丁', env.get('security_patch')),
                 ('ABI / API', env.get('abi', '?') + ' / ' + env.get('android_api', '?')), ('SELinux', state.get('selinux')),
                 ('配置判断', assessment.get('message')), ('配置 ID', assessment.get('profile_id'))]
        text = '\n\n'.join(key + '：' + (value or '未确认') for key, value in lines)
        text += '\n\nRoot 属于实验功能，允许尝试不代表已适配或保证成功。'
        if state.get('diagnostics'):
            text += '\n\n未确认的检测项：\n' + '\n'.join(item['command'] + '：' + item['error'] for item in state['diagnostics'])
        self.detail_text.configure(state='normal')
        self.detail_text.delete('1.0', 'end')
        self.detail_text.insert('end', text)
        self.detail_text.configure(state='disabled')
        self.update_buttons()

    def connection_unknown(self, error):
        self.phone = None
        self.connection.configure(text='手机连接待确认', fg=AMBER)
        for value in self.values.values():
            value.configure(text='状态未知', fg=MUTED)
        self.display_charging({'known': False, 'label': '状态未知', 'error': error})
        self.checked_note.configure(text='最近核验失败 · 请检查连接与 USB 调试授权', fg=AMBER)
        self.help_line.configure(text=error, fg=AMBER)
        self.pill_hint.configure(text='连接并检测手机后可操作。')
        self.detail_text.configure(state='normal')
        self.detail_text.delete('1.0', 'end')
        self.detail_text.insert('end', '当前手机信息尚未确认。\n\n' + error + '\n\n请检查连接与 USB 调试授权后刷新。')
        self.detail_text.configure(state='disabled')
        self.update_buttons()

    def start(self, action, background=False):
        if self.busy:
            return
        if self.polling:
            if not background:
                self.queued_action = action
                self.banner.configure(text='正在完成状态核验，随后执行你选择的操作…', fg=BLUE)
            return
        if action == 'root' and not execution_available(self.phone):
            self.banner.configure(text='请先连接并检测手机；已有 Root 或模块已加载时跳过重复激活。', fg=AMBER)
            return
        runtime = ROOT / 'runtime/python.exe'
        if not runtime.is_file():
            if not background:
                self.banner.configure(text='缺少运行文件，请解压并保留整个工具文件夹。', fg=RED)
            return
        args = [str(runtime), '-B', '-u', '-X', 'utf8']
        if action == 'root':
            folder = ROOT / 'logs' / ('selection-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            folder.mkdir(parents=True)
            confirmation = folder / 'execution-choice.json'
            confirmation.write_text(json.dumps(make_confirmation(self.phone, False), ensure_ascii=False, indent=2), encoding='utf-8')
            args += [str(ROOT / 'scripts/one_click.py'), '--gui', '--confirmation', str(confirmation)]
            if self.keep_awake.get():
                args.append('--keep-awake')
        else:
            args += [str(ROOT / 'scripts/gui_bridge.py'), action]
            if background:
                args.append('--quiet')
        if background:
            self.polling = True
        else:
            self.busy = True
            self.unlock_pending = False
            self.update_buttons()
            labels = {'status': '正在核验手机状态…', 'root': '正在核对本次 Root 操作…', 'hide': '正在隐藏小白条…',
                      'show': '正在恢复小白条…', 'display-enable': '正在开启 USB 充电常亮并回读…',
                      'display-disable': '正在关闭充电常亮并回读…', 'display-restore': '正在恢复手动修改前的设置…',
                      'restore-display': '正在恢复 Root 临时常亮设置…'}
            self.stage_note.configure(text='检测中' if action == 'status' else '操作中')
            self.banner.configure(text=labels[action], fg=BLUE)
            self.append('[' + datetime.datetime.now().strftime('%H:%M:%S') + '] ' + labels[action])
            self.progress.pack(fill='x', pady=(7, 0))
            self.progress.start(12)
        threading.Thread(target=self.worker, args=(action, args, background), daemon=True).start()

    def poll_status(self):
        if not self.busy and not self.polling and self.queued_action is None:
            self.start('status', background=True)
        self.after(POLL_MS, self.poll_status)

    def worker(self, action, args, background=False):
        result, log_path, captured = None, None, []
        try:
            if background:
                # Bound read-only polling; a slow/disconnected phone must not stall queued actions.
                completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                for line in completed.stdout.splitlines():
                    if line.startswith('@@RESULT '):
                        result = json.loads(line[9:])
                self.events.put(('done', {'action': action, 'background': True,
                                          'code': completed.returncode, 'result': result}))
                return
            process = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW)
            if not background:
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
                elif not background:
                    self.events.put(('line', line))
            code = process.wait()
            process.stdout.close()
            process.stdin.close()
            if log_path:
                (log_path / 'gui-worker-console.txt').write_text(''.join(captured), encoding='utf-8')
            if action == 'root' and log_path and (log_path / 'result.json').is_file():
                result = json.loads((log_path / 'result.json').read_text(encoding='utf-8'))
            self.events.put(('done', {'action': action, 'background': background, 'code': code, 'result': result}))
        except Exception as exc:
            self.events.put(('done', {'action': action, 'background': background, 'code': 2,
                                      'result': {'ok': False, 'error': str(exc)}}))

    def continue_unlock(self):
        self.answer_unlock('\n', '正在核对解锁状态…')

    def cancel_unlock(self):
        self.answer_unlock('cancel\n', '正在取消；若修改过临时常亮，将恢复原设置…')

    def answer_unlock(self, answer, message):
        if self.child and self.unlock_pending:
            try:
                self.child.stdin.write(answer)
                self.child.stdin.flush()
                self.unlock_pending = False
                self.unlock_actions.pack_forget()
                self.banner.configure(text=message, fg=BLUE)
                self.update_buttons()
            except (OSError, ValueError) as exc:
                self.banner.configure(text='操作未送达：' + str(exc), fg=RED)

    def consume(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'line':
                    self.append(value)
                elif kind == 'ui':
                    event = value.get('event')
                    if event == 'unlock':
                        self.unlock_pending = True
                        self.stage_note.configure(text='等待解锁')
                        self.banner.configure(text='请解锁手机并保持桌面可见；也可以取消本次操作。', fg=AMBER)
                        self.unlock_actions.pack(anchor='w', pady=(8, 0))
                        self.update_buttons()
                    elif event == 'log_directory':
                        candidate = Path(value['path']).resolve()
                        if candidate.is_relative_to((ROOT / 'logs').resolve()):
                            self.current_logs = candidate
                    elif event == 'display':
                        self.display_charging(value['state'])
                        self.display_result.configure(text='本次 Root 辅助：' + value['state'].get('label', '状态未知'), fg=BLUE)
                    elif event == 'stage':
                        stage = value.get('stage')
                        self.stage_note.configure(text={'activate': 'Root 执行中', 'verify': '核验结果', 'restore': '恢复临时设置'}.get(stage, '操作中'))
                        self.banner.configure(text={'activate': '已启动一次 Root，请保持连接。', 'verify': '正在核验 Root、模块与服务状态。',
                                                    'restore': '正在回读核验恢复结果。'}.get(stage, '正在执行…'), fg=BLUE)
                elif kind == 'done':
                    self.finish(value)
        except queue.Empty:
            pass
        self.after(100, self.consume)

    def finish(self, done):
        result = done.get('result') or {'ok': False, 'error': '进程未返回完整结果，请查看日志。'}
        action = done['action']
        if done.get('background'):
            self.polling = False
            if result.get('ok'):
                self.display_state(result['state'])
            else:
                self.connection_unknown(result.get('error', '状态核验失败。'))
            queued, self.queued_action = self.queued_action, None
            if queued:
                self.after(1, lambda: self.start(queued))
            return
        self.busy = self.unlock_pending = False
        self.child = None
        self.unlock_actions.pack_forget()
        self.progress.stop()
        self.progress.pack_forget()
        if action == 'status':
            if result.get('ok'):
                self.display_state(result['state'])
                message, color = '状态已核验，可选择首页操作。', GREEN
            else:
                message, color = result.get('error', '未连接手机。'), AMBER
                self.connection_unknown(message)
        elif action == 'root':
            message, color = root_summary(result)
            if result.get('display_restore_error'):
                message += ' 临时常亮待恢复，记录已保留。'
                color = AMBER
            if result.get('history_error'):
                message += ' 历史写入失败，完整日志已保留。'
                color = AMBER
            helper = result.get('display_assistance', 'disabled')
            if result.get('display_restored'):
                from display_settings import setting_label
                self.display_last_result = '本次 Root 临时设置已恢复：' + setting_label(result['display_restored_value'])
            elif result.get('display_restore_error'):
                self.display_last_result = '本次 Root 临时常亮尚未恢复，请连接原手机后恢复。'
            elif helper == 'disabled':
                self.display_last_result = '本次 Root 未修改充电常亮设置。'
            elif helper == 'already_enabled':
                self.display_last_result = 'USB 常亮原本已开启，本次 Root 未修改设置。'
            else:
                self.display_last_result = '本次 Root 已跳过临时常亮，请手动保持亮屏。'
            self.display_result.configure(text=self.display_last_result, fg=AMBER if result.get('display_restore_error') else MUTED)
        else:
            message, color = ((result.get('message', '操作已完成。'), GREEN) if result.get('ok')
                              else (result.get('error', '操作未完成。'), RED))
            if result.get('state'):
                self.display_state(result['state'])
            if result.get('display'):
                self.display_charging(result['display'])
            if action.startswith('display-') or action == 'restore-display':
                self.display_last_result = message
                self.display_result.configure(text=message, fg=color)
        self.stage_note.configure(text='已完成' if color == GREEN else '需要处理')
        self.banner.configure(text=message, fg=color)
        self.append(message)
        self.reload_history()
        self.update_buttons()
        if action != 'status' and self.auto_check:
            self.after(250, lambda: self.start('status', background=True))

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
            messagebox.showinfo('任务仍在运行', '请等待当前任务结束再关闭。可以先最小化。', parent=self)
            return
        self.destroy()


def fixture_state():
    from registry import assess
    env = {'hardware_device': 'SO-51D', 'model': 'SO-51D', 'android_api': '35', 'android_release': '15',
           'kernel': '5.15.170-android13-8-00015-g52ccd9134339-ab12915929', 'owner_user': '0',
           'boot_completed': '1', 'build': '67.2.A.3.55 release-keys', 'fingerprint': 'fixture',
           'security_patch': '2025-01-01', 'abi': 'arm64-v8a'}
    return {'connected': True, 'compatible': True, 'rooted': False, 'kernelsu_loaded': False,
            'environment': env, 'manager': {'label': '未安装'}, 'assessment': assess(env, ROOT),
            'navigation_mode': '2', 'hidden': False, 'locked': False, 'pill_known': True,
            'modules_known': True, 'selinux': 'Enforcing', 'boot_id': 'fixture-boot', 'pill_supported': True,
            'checked_at': '2026-10-04T12:30:00+08:00',
            'display': {'known': True, 'raw': '0', 'label': '已关闭充电常亮',
                        'manual_restore_available': True, 'baseline_label': '无线供电时常亮',
                        'temporary_restore_available': False}}


def self_test(window):
    """UI routes and state transitions use fixtures only, with no ADB or worker calls."""
    import io
    from types import SimpleNamespace
    window.withdraw()
    state = fixture_state()
    actions = []
    original_start = window.start
    window.start = lambda action, **kwargs: actions.append((action, kwargs))
    window.display_state(state)
    assert not window.keep_awake.get()
    assert str(window.root_btn['state']) == 'normal'
    for button in (window.root_btn, window.display_enable_btn, window.display_disable_btn, window.display_restore_btn):
        button.invoke()
    state.update(rooted=True, kernelsu_loaded=True)
    window.display_state(state)
    assert str(window.root_btn['state']) == 'disabled'
    window.hide_btn.invoke()
    window.show_btn.invoke()
    window.refresh_btn.invoke()
    assert [a[0] for a in actions] == ['root', 'display-enable', 'display-disable', 'display-restore', 'hide', 'show', 'status']
    stream = io.StringIO()
    window.child = SimpleNamespace(stdin=stream)
    window.busy, window.unlock_pending = True, True
    window.cancel_btn.invoke()
    assert stream.getvalue() == 'cancel\n' and not window.unlock_pending
    window.busy, window.child = False, None
    window.finish({'action': 'status', 'background': True, 'result': {'ok': False, 'error': 'fixture disconnected'}})
    assert window.phone is None and window.display_value['text'] == '状态未知'
    assert '完整内核' not in window.detail_text.get('1.0', 'end')
    assert str(window.display_enable_btn['state']) == 'disabled'
    window.display_state(state)
    window.poll_status()
    assert actions[-1] == ('status', {'background': True})
    window.busy = True
    count = len(actions)
    window.poll_status()
    assert len(actions) == count
    window.busy = False
    window.polling = True
    window.start = original_start
    window.start('root')
    assert window.queued_action == 'root'
    window.queued_action, window.polling = None, False
    window.start = lambda action, **kwargs: actions.append((action, kwargs))
    window.deiconify()
    window.minsize(720, 580)
    layouts = []
    for width, height in ((1000, 790), (800, 620), (720, 580)):
        window.geometry(f'{width}x{height}')
        window.update()
        for page in (window.home_page, window.details_page, window.history_page, window.log_page):
            window.notebook.select(page)
            window.update()
            assert window.notebook.winfo_height() > 150
        window.notebook.select(window.home_page)
        window.home_canvas.yview_moveto(1)
        window.update()
        for widget in (window.display_restore_btn, window.banner, window.refresh_btn):
            assert widget.winfo_width() > 10 and widget.winfo_height() > 10
            assert widget.winfo_rootx() >= window.winfo_rootx()
            assert widget.winfo_rootx() + widget.winfo_width() <= window.winfo_rootx() + window.winfo_width()
            assert widget.winfo_rooty() + widget.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        layouts.append({'width': width, 'height': height, 'home_scrollable': window.home_content.winfo_height() > window.home_canvas.winfo_height()})
    report = {'ok': True, 'frozen_exe': bool(getattr(sys, 'frozen', False)), 'device_commands_executed': 0,
              'button_routes': [a[0] for a in actions], 'root_stay_awake_default': False,
              'cancel_unlock_restores_display_request': True, 'automatic_refresh': True,
              'disconnect_clears_stale_state': True, 'poll_serializes_user_action': True, 'layouts': layouts}
    (ROOT / 'logs').mkdir(exist_ok=True)
    (ROOT / 'logs/exe-ui-self-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
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
            raise RuntimeError('这个版本已经打开，请回到原窗口。') from exc
        if '--self-test' in sys.argv:
            self_test(App(auto_check=False))
        elif '--preview' in sys.argv:
            window = App(auto_check=False)
            window.display_state(fixture_state())
            window.banner.configure(text='界面预览 · 示例数据，不代表已连接真实手机。', fg=BLUE)
            window.mainloop()
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
