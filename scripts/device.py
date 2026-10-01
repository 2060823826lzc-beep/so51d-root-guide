"""SO-51D experiment runner. Default action is read-only; no boot flashing."""
import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from common import ROOT, KERNEL, PROFILE, DOWNLOADS, MANIFEST, verify, verify_payloads
from registry import require_execution, profile_by_id

REMOTE = '/data/local/tmp/codex-root-audit'
MANAGER_ID = 'me.weishu.kernelsu'
MANAGER_PACKAGE = next(p for p in MANIFEST['packages'] if p['name'].startswith('KernelSU_'))


class Device:
    def __init__(self, adb, serial=None):
        self.adb = adb
        self.selector = ['-s', serial] if serial else ['-d']
        self.confirmation = None
        self.selected_profile = None

    def call(self, *args, timeout=25, check=True):
        try:
            result = subprocess.run([self.adb, *self.selector, *args], capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=timeout,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('ADB/授权等待超时。检查连接或 KernelSU 的 Shell 授权；未自动重试。') from error
        output = (result.stdout + result.stderr).strip()
        if check and result.returncode:
            raise RuntimeError(output or f'ADB exit={result.returncode}')
        return output

    def shell(self, command, **kwargs):
        return self.call('shell', command, **kwargs)

    def modules(self):
        # A failed read must never be interpreted as "KernelSU absent".
        return self.shell('cat /proc/modules')

    def has_root(self):
        return 'uid=0(root)' in self.shell('su -c id', check=False)

    def inspect(self):
        """Read the environment of any connected device; never enforce a profile here."""
        if self.call('get-state') != 'device':
            raise RuntimeError('手机未连接或未授权 ADB。')
        values = {
            'hardware_device': self.shell('getprop ro.product.vendor.device'),
            'android_api': self.shell('getprop ro.build.version.sdk'),
            'kernel': self.shell('uname -r'),
            'owner_user': self.shell('am get-current-user'),
            'boot_completed': self.shell('getprop sys.boot_completed'),
            'build': self.shell('getprop ro.build.display.id'),
            'fingerprint': self.shell('getprop ro.build.fingerprint'),
            'model': self.shell('getprop ro.product.model'),
            'android_release': self.shell('getprop ro.build.version.release'),
            'security_patch': self.shell('getprop ro.build.version.security_patch'),
            'abi': self.shell('getprop ro.product.cpu.abi'),
        }
        return values

    def check(self):
        values = self.inspect()
        assessment = require_execution(values, ROOT, self.confirmation,
                                       boot_id(self) if self.confirmation is not None else None)
        self.selected_profile = profile_by_id(ROOT, assessment['profile_id'])
        return values


def module_loaded(text):
    return any(line.split() and line.split()[0] == 'kernelsu' for line in text.splitlines())


def activation_needed(device):
    if device.has_root():
        print('当前已有 Root；跳过激活，不改变 Shizuku 模式。')
        return False
    if module_loaded(device.modules()):
        raise RuntimeError('KernelSU 已加载，但 Shell 没有 Root 授权。请在管理器中检查授权，禁止重复提权。')
    return True


def boot_id(device):
    value = device.shell('cat /proc/sys/kernel/random/boot_id')
    if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', value):
        raise RuntimeError('无法确认本次开机 ID；停止。')
    return value


def confirm_same_boot(device, original):
    if device.call('get-state', check=False) != 'device':
        raise RuntimeError('ADB 已断开；可能是拔线、卡死或重启。已停止监控，不会再次启动提权。')
    if boot_id(device) != original:
        raise RuntimeError('检测到手机已重启。此次激活不计为成功，不会自动重试。')


class ActivationStopped(RuntimeError):
    """A classified attempt outcome, never permission to retry or kill workers."""


def activation_connection_failure(device, original, error):
    """Bounded read-only diagnosis after a launched attempt; never relaunch."""
    print('激活监控遇到中断；正在只读检查开机周期，不会再次启动提权。', flush=True)
    for attempt in range(12):
        if attempt:
            time.sleep(2)
        try:
            current = device.shell('cat /proc/sys/kernel/random/boot_id', timeout=3)
        except RuntimeError:
            continue
        if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', current):
            continue
        if current != original:
            try:
                reason = device.shell('getprop sys.boot.reason', timeout=3)
            except RuntimeError:
                reason = ''
            detail = '，系统报告内核崩溃' if 'kernel_panic' in reason else ''
            return ActivationStopped('激活期间手机已重启' + detail + '。本次 Root 未成功；已停止，不会自动重试。')
        return ActivationStopped('激活监控中断，手机仍在同一次开机。Root 结果未确认；'
                                 '请重新检查状态并保存日志，不要重复激活或强杀进程。原始信息：' + str(error))
    return ActivationStopped('ADB 持续不可用，暂时无法区分拔线、手机卡死或重启。Root 结果未确认；'
                             '已停止，不会重试。重新连接后先检查状态。原始信息：' + str(error))


def monitor_activation(device, original_boot):
    previous = ''
    for _ in range(48):
        time.sleep(5)
        confirm_same_boot(device, original_boot)
        tail = device.shell(f'tail -80 {REMOTE}/activation.log')
        clean = re.sub(r'\x1b\[[0-9;]*m', '', tail)
        if clean != previous:
            print(clean[len(previous):] if previous and clean.startswith(previous) else clean, flush=True)
            previous = clean
        if re.search(r'^\[-\]\s+Write [123] failed\s*$', clean, re.MULTILINE):
            raise ActivationStopped('原生程序已报告写入阶段失败，本次 Root 未成功。'
                                    '已停止监控，不会自动重试；请保留日志和本次开机标记。')
        if device.has_root() and module_loaded(device.modules()) and device.shell('getenforce') == 'Enforcing':
            confirm_same_boot(device, original_boot)
            print('已确认 Shell uid=0、KernelSU 模块存在、SELinux Enforcing。请再查看 KernelSU 工作状态。')
            print('这是本次开机的临时 Root；不会自动启动或切换 Shizuku。')
            return
    raise ActivationStopped('监控窗口结束，未确认成功。后台程序可能仍在运行；先保存日志，勿重复执行或强杀进程。')


def manager_status(device):
    """Read the owner user's actual APK, independently of kernel/Shell Root state."""
    packages = device.shell(f'pm list packages --user 0 {MANAGER_ID}')
    if f'package:{MANAGER_ID}' not in packages.splitlines():
        return {'state': 'missing', 'label': '未安装', 'version': ''}
    disabled = device.shell(f'pm list packages -d --user 0 {MANAGER_ID}')
    if f'package:{MANAGER_ID}' in disabled.splitlines():
        return {'state': 'disabled', 'label': '已安装但被停用', 'version': ''}
    paths = device.shell(f'pm path --user 0 {MANAGER_ID}').splitlines()
    if len(paths) != 1 or not paths[0].startswith('package:/'):
        raise RuntimeError('无法核对 KernelSU 安装包路径；未覆盖安装或激活。')
    path = paths[0][len('package:'):]
    result = device.shell('sha256sum ' + shlex.quote(path)).split()
    if not result or not re.fullmatch(r'[a-fA-F0-9]{64}', result[0]):
        raise RuntimeError('无法校验已安装 KernelSU；未覆盖安装或激活。')
    if result[0].lower() != MANAGER_PACKAGE['sha256']:
        return {'state': 'different', 'label': '已有其他版本，未覆盖', 'version': ''}
    return {'state': 'ready', 'label': '3.3.0 · 已校验', 'version': '3.3.0 (32601)'}


def prepare_manager(device):
    """Install only when absent; never downgrade, uninstall, or start the exploit."""
    device.check()
    original = boot_id(device)
    state = manager_status(device)
    if state['state'] == 'ready':
        print('KernelSU 管理器已是指定版本，复用现有安装。')
        return state
    if state['state'] != 'missing':
        raise RuntimeError('KernelSU ' + state['label'] + '。请先处理管理器状态；不会自动卸载、降级或清除数据。')
    apk = DOWNLOADS / MANAGER_PACKAGE['name']
    verify(apk, MANAGER_PACKAGE['sha256'])
    confirm_same_boot(device, original)
    print('正在安装 KernelSU 3.3.0 管理器；这一步不会激活 Root。', flush=True)
    # No -r/-d: a concurrently installed or different manager must not be replaced.
    result = device.call('install', '--user', '0', str(apk), timeout=120, check=False)
    if 'Success' not in result.splitlines():
        raise RuntimeError('KernelSU 安装未完成，未启动 Root。请查看手机安装提示、存储空间或应用安装限制。\n' + result)
    confirm_same_boot(device, original)
    installed = manager_status(device)
    if installed['state'] != 'ready':
        raise RuntimeError('安装后未确认 KernelSU 原件校验通过，未启动 Root。')
    print('KernelSU 管理器安装并校验完成。管理器已安装不等于已获得 Root。')
    return installed


def status(device):
    values = device.check()
    values.update(manager=manager_status(device), root=device.shell('su -c id', check=False),
                  selinux=device.shell('getenforce'),
                  kernelsu_loaded=module_loaded(device.modules()),
                  navigation_mode=device.shell('settings get secure navigation_mode'),
                  overlays=device.shell('cmd overlay list --user 0 com.android.systemui'),
                  bootloader=device.shell('getprop ro.boot.vbmeta.device_state'))
    print(json.dumps(values, ensure_ascii=False, indent=2))
    return values


def activate(device):
    device.check()
    selected = device.selected_profile
    profile_path = ROOT / selected['file']
    profile_sha256 = selected['sha256']
    if not activation_needed(device):
        return
    if device.shell('getenforce') != 'Enforcing':
        raise RuntimeError('SELinux 不是 Enforcing，停止激活。')
    verify_payloads()
    original_boot = boot_id(device)
    lock = f'{REMOTE}/guide-attempt-{original_boot}'
    if device.shell(f'if [ -d {lock} ]; then echo exists; fi') == 'exists':
        raise RuntimeError('本次开机已有一次教程脚本激活记录。先查日志，不允许同一开机周期重复启动。')
    processes = device.shell('ps -A -o ARGS')
    if any(line.strip().startswith(f'{REMOTE}/ghostlock') or 'libghostlock.so --ghostlock-app-call' in line
           for line in processes.splitlines()):
        raise RuntimeError('检测到已有 GhostLock 进程。不要强杀它，也不要再次启动。')
    print('准备一次临时 Root 尝试。可能卡死或重启；不会自动重试，也不会刷写分区。', flush=True)
    print('使用配置：' + profile_path.name + '；请勿同时运行其他 Root 工具。', flush=True)
    prepare_manager(device)
    device.shell(f'mkdir -p {REMOTE} && chmod 700 {REMOTE}')
    for local, remote in [(DOWNLOADS / 'ghostlock-arm64', 'ghostlock'),
                          (DOWNLOADS / 'ksud-arm64', 'ksud'), (profile_path, 'selected-profile.glk')]:
        device.call('push', str(local), f'{REMOTE}/{remote}')
    expected_files = {'ghostlock': MANIFEST['packages'][0]['extract']['sha256'],
                      'ksud': MANAGER_PACKAGE['extract']['sha256'],
                      'selected-profile.glk': profile_sha256}
    for name, sha in expected_files.items():
        value = device.shell(f'sha256sum {REMOTE}/{name}').split()
        if not value or value[0] != sha:
            raise RuntimeError(f'手机端 {name} 校验失败，未启动 Root。')
    device.shell(f'chmod 700 {REMOTE}/ghostlock {REMOTE}/ksud && sync')
    confirm_same_boot(device, original_boot)
    if not activation_needed(device):
        return
    # mkdir is an atomic per-boot exclusion. Never delete it or kill workers automatically.
    command = (
        f'mkdir {lock} || exit 73; '
        f'GHOSTLOCK_HOME={REMOTE} nohup {REMOTE}/ghostlock '
        f'--load-prebuilt-profile {REMOTE}/selected-profile.glk '
        f'>{REMOTE}/activation.log 2>&1 </dev/null &'
    )
    try:
        device.shell(command)
        monitor_activation(device, original_boot)
    except ActivationStopped:
        raise
    except RuntimeError as error:
        raise activation_connection_failure(device, original_boot, error) from error


def pill(device, action):
    environment = device.inspect()
    if environment.get('owner_user') != '0':
        raise RuntimeError('请切换到机主用户。')
    source = ROOT / 'scripts/gesture-pill.sh'
    checksums = json.loads((ROOT / 'checksums.json').read_text(encoding='utf-8'))
    verify(source, checksums['scripts/gesture-pill.sh'])
    remote_script = f'{REMOTE}/gesture-pill.sh'
    if action != 'status' and not device.has_root():
        raise RuntimeError('修改小白条需要 Root。请先恢复 Root，并给 Shell 授权；本操作不会自动提权。')
    device.shell(f'mkdir -p {REMOTE}')
    device.call('push', str(source), remote_script)
    if action == 'status':
        print(device.shell(f'sh {remote_script} status'))
        return
    helper = ROOT / 'artifacts/gesture-pill-overlay.jar'
    verify(helper, checksums['artifacts/gesture-pill-overlay.jar'])
    remote_helper = f'{REMOTE}/gesture-pill-overlay.jar'
    device.call('push', str(helper), remote_helper)
    command = f'sh {remote_script} {action} {remote_helper}'
    print(device.shell('su -c ' + shlex.quote(command)))


def logs(device):
    # Do not require the pre-activation kernel/root state to collect a failed run.
    folder = ROOT / 'logs' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True, exist_ok=True)
    for name in ['activation.log', '.ghostlock_native.log', '.ghostlock_ksu.log']:
        print(device.call('pull', f'{REMOTE}/{name}', str(folder / name), check=False))
    queries = {'kernel': 'uname -r', 'boot_reason': 'getprop ro.boot.bootreason',
               'selinux': 'getenforce', 'root': 'su -c id', 'modules': 'cat /proc/modules'}
    result = {key: device.shell(command, check=False) for key, command in queries.items()}
    (folder / 'status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'日志保存在 {folder}。目录已被 Git 忽略；提交 Issue 前先脱敏。')


def find_adb(explicit=None):
    candidates = [explicit, os.environ.get('ADB'),
                  str(ROOT / 'platform-tools' / ('adb.exe' if os.name == 'nt' else 'adb')),
                  shutil.which('adb')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError('找不到 ADB。将官方 platform-tools 放到仓库根目录，或使用 --adb 完整路径。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='check', choices=['check', 'prepare-manager', 'activate', 'hide', 'show', 'pill-status', 'logs'])
    parser.add_argument('--adb', help='ADB 可执行文件完整路径')
    parser.add_argument('--serial', help='显式指定 USB 序列号或无线地址；默认 -d 只选 USB')
    args = parser.parse_args()
    device = Device(find_adb(args.adb), args.serial)
    if args.action == 'check':
        status(device)
    elif args.action == 'prepare-manager':
        prepare_manager(device)
    elif args.action == 'activate':
        activate(device)
    elif args.action == 'logs':
        logs(device)
    else:
        pill(device, 'status' if args.action == 'pill-status' else args.action)


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(f'停止：{error or "用户中断；不会终止手机中的 Root 工作进程。"}', file=sys.stderr)
        sys.exit(1)
