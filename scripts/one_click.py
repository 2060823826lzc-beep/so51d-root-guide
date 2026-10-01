"""Double-click entry for the pinned SO-51D diagnostic build. No automatic retry."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/data/local/tmp/so51d-diag-20260929-01'

def now():
    return datetime.datetime.now().astimezone().isoformat()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def verify_bundle():
    entries = json.loads((ROOT / 'bundle-sha256.json').read_text(encoding='utf-8'))
    for name, expected in entries.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise RuntimeError('文件清单包含目录外路径。')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('文件缺失或校验失败：' + name + '。请使用完整原件。')

class ProcessLock:
    def __init__(self, path):
        self.path = path
        self.stream = None

    def __enter__(self):
        import msvcrt
        self.stream = self.path.open('a+b')
        try:
            if os.fstat(self.stream.fileno()).st_size == 0:
                self.stream.write(b'0')
                self.stream.flush()
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.stream.close()
            raise RuntimeError('另一个脚本窗口正在运行。请回到原窗口，不要重复启动。') from exc
        return self

    def __exit__(self, *args):
        import msvcrt
        self.stream.seek(0)
        msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()

def health(state, original):
    return (state.get('boot_id') == original and 'uid=0(root)' in state.get('root', '')
            and state.get('kernelsu_loaded') is True and state.get('selinux') == 'Enforcing'
            and state.get('package_service', '').startswith('package:/')
            and state.get('activity_service') == 'Service activity: found')

def active_ghostlock(processes):
    return any(re.search(r'(^|/)ghostlock(?:-arm64)?(?:\s|$)', s.strip())
               or 'libghostlock.so --ghostlock-app-call' in s for s in processes.splitlines())

def locked(policy):
    return bool(re.search(r'^\s*(showing|mInputRestricted)=true\s*$', policy, re.MULTILINE))

def run(args, out):
    verify_bundle()
    import common
    import device
    from registry import assess, require_execution, record_attempt
    device.REMOTE = REMOTE

    class RecordedDevice(device.Device):
        def call(self, *command, timeout=25, check=True):
            event = {'time': now(), 'args': command}
            start = time.monotonic()
            try:
                p = subprocess.run([self.adb, *self.selector, *command], capture_output=True,
                                   text=True, encoding='utf-8', errors='replace', timeout=timeout,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                event.update(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
                value = (p.stdout + p.stderr).strip()
                if check and p.returncode:
                    raise RuntimeError(value or 'ADB 返回错误 ' + str(p.returncode))
                return value
            except subprocess.TimeoutExpired as exc:
                event['error'] = 'ADB timeout'
                raise RuntimeError('ADB 等待超时；请检查连接或 Shell 授权。不会重新激活。') from exc
            finally:
                event['elapsed_seconds'] = round(time.monotonic() - start, 3)
                with (out / 'adb-events.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')

    d = RecordedDevice(str(ROOT / 'platform-tools' / 'adb.exe'))
    confirmation_path = getattr(args, 'confirmation', None)
    if confirmation_path:
        path = Path(confirmation_path).resolve()
        if not path.is_relative_to((ROOT / 'logs').resolve()):
            raise RuntimeError('执行确认文件必须位于本工具日志目录。')
        d.confirmation = json.loads(path.read_text(encoding='utf-8'))
    result = {'started_at': now(), 'mode': 'check' if args.check else 'activate', 'activation_calls': 0}
    display_original = None
    samples = []

    def snapshot():
        state = {'time': now(), 'boot_id': device.boot_id(d)}
        for key, command in {
            'root': 'su -c id', 'selinux': 'getenforce', 'boot_reason': 'getprop sys.boot.reason',
            'uptime': 'cat /proc/uptime', 'package_service': 'pm path --user 0 me.weishu.kernelsu',
            'activity_service': 'service check activity', 'framework_pids': 'pidof system_server zygote64 zygote',
        }.items():
            state[key] = d.shell(command, check=False, timeout=8)
        state['kernelsu_loaded'] = device.module_loaded(d.modules())
        return state

    def collect():
        if d.call('get-state', check=False, timeout=4) != 'device':
            return
        for name in ['activation.log', '.ghostlock_native.log', '.ghostlock_ksu.log']:
            d.call('pull', REMOTE + '/' + name, str(out / name.lstrip('.')), check=False, timeout=12)
        state = snapshot()
        save(out / 'final-state.json', state)
        if 'uid=0(root)' in state.get('root', ''):
            (out / 'kernel.log').write_text(d.shell('su -c dmesg', check=False, timeout=15), encoding='utf-8')

    try:
        print('检测手机信息，核对匹配配置和执行选择……', flush=True)
        common.verify_payloads()
        result['environment'] = d.inspect()
        result['assessment'] = assess(result['environment'], ROOT)
        print(result['assessment']['message'], flush=True)
        print('风险提示：执行可能失败、卡死或重启；允许尝试不代表此手机已适配。', flush=True)
        before = snapshot()
        save(out / 'before-state.json', before)
        original = before['boot_id']
        if args.check:
            result['outcome'] = 'read_only_check'
            print(json.dumps(before, ensure_ascii=False, indent=2))
            return 0
        # Bind the user's choice to this exact environment and boot before mutations.
        require_execution(result['environment'], ROOT, d.confirmation, original)
        if getattr(args, 'gui', False) and d.confirmation is None:
            raise RuntimeError('请先在界面检测手机信息，然后自行选择执行 Root。')
        if 'uid=0(root)' in before['root']:
            result['outcome'] = 'already_rooted'
            print('手机已经有 Root，本次没有执行激活。')
            print('KernelSU 模块：' + str(before['kernelsu_loaded']) + '；SELinux：' + before['selinux'])
            return 0
        if before['kernelsu_loaded']:
            raise RuntimeError('KernelSU 已加载，但 Shell 未获授权。请在管理器检查 Shell 授权；不重复激活。')
        if before['selinux'] != 'Enforcing':
            raise RuntimeError('当前 SELinux 状态异常，停止激活，请先检查既有日志。')
        for pending in (ROOT / 'logs').glob('*/display-restore.json'):
            if json.loads(pending.read_text(encoding='utf-8')).get('restore_required'):
                raise RuntimeError('上次的临时亮屏设置尚未恢复。请先双击“恢复亮屏设置.cmd”，再检查手机状态。')
        if active_ghostlock(d.shell('ps -A -o ARGS')):
            raise RuntimeError('已有 GhostLock 程序运行。停止本次启动，不强杀已有进程。')
        for directory in ['/data/local/tmp/codex-root-audit', REMOTE]:
            if d.shell(f'if [ -d {directory}/guide-attempt-{original} ]; then echo exists; fi') == 'exists':
                raise RuntimeError('本次开机已有激活记录。请先保留和检查日志，不在本次开机重复尝试。')
        markers = ROOT / 'attempts'
        markers.mkdir(exist_ok=True)
        marker = markers / (original + '.json')
        if marker.exists():
            raise RuntimeError('电脑已有本次开机的执行记录，停止重复启动。')
        display_original = d.shell('settings get global stay_on_while_plugged_in')
        if not re.fullmatch(r'[0-7]', display_original):
            display_original = None
            raise RuntimeError('无法确认原亮屏设置，未启动。')
        save(out / 'display-restore.json', {'original': display_original, 'restore_required': True})
        d.shell('settings put global stay_on_while_plugged_in 7')
        while locked(d.shell('dumpsys window policy')):
            if getattr(args, 'gui', False):
                print('@@UI ' + json.dumps({'event': 'unlock'}, ensure_ascii=False), flush=True)
                if input().strip().lower() == 'cancel':
                    result['outcome'] = 'cancelled'
                    print('已取消，未执行 Root；正在恢复原亮屏设置。', flush=True)
                    return 0
            else:
                input('请在手机上解锁并保持桌面可见，完成后按回车继续；Ctrl+C 取消：')
            device.confirm_same_boot(d, original)
        device.confirm_same_boot(d, original)
        with marker.open('x', encoding='utf-8') as f:
            json.dump({'time': now(), 'log_directory': str(out), 'no_automatic_retry': True}, f)
        result['activation_calls'] = 1
        print('开始一次诊断版激活。可能触发系统界面重载或重启；请勿同时运行其他 Root 工具。', flush=True)
        try:
            device.activate(d)
            result['immediate'] = snapshot()
            result['immediate_verified'] = health(result['immediate'], original)
        except RuntimeError as exc:
            result['activation_error'] = str(exc)
            print('激活监控提示：' + str(exc), flush=True)
        save(out / 'result.json', result)
        print('正在核验当前 Root 状态，不再进行五分钟等待。', flush=True)
        result['observation_mode'] = 'immediate'
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            try:
                state = snapshot()
                state['healthy'] = health(state, original)
            except RuntimeError as exc:
                state = {'time': now(), 'healthy': False, 'error': str(exc)}
            state['elapsed_seconds'] = round(elapsed, 2)
            samples.append(state)
            save(out / 'observation.json', samples)
            print('当前核验：' + ('Root、模块及服务正常' if state['healthy'] else '存在异常，已记录'), flush=True)
            if state.get('boot_id') and state['boot_id'] != original:
                result['reboot_observed'] = True
                print('检测到整机重启，结束本次测试，不重试。')
                break
            break
        final = samples[-1]
        result['root_currently_verified'] = (final.get('boot_id') == original
            and 'uid=0(root)' in final.get('root', '') and final.get('kernelsu_loaded') is True)
        result['all_health_samples_passed'] = False
        result['immediate_health_passed'] = final['healthy']
        result['outcome'] = 'root_verified' if result['root_currently_verified'] else 'root_not_confirmed'
        print('当前 Root：' + ('已确认' if result['root_currently_verified'] else '未确认'))
        print('核验完成，完整记录已保存。')
        return 0 if result['root_currently_verified'] else 2
    except KeyboardInterrupt:
        result['outcome'] = 'interrupted'
        print('\n已停止电脑端等待。不会强杀手机上的程序；不要立即重复启动。')
        return 2
    except Exception as exc:
        result.update(outcome='stopped', error=str(exc))
        print('停止：' + str(exc))
        return 2
    finally:
        if result['activation_calls']:
            try:
                collect()
            except Exception as exc:
                result['collection_error'] = str(exc)
        if display_original is not None:
            try:
                d.shell('settings put global stay_on_while_plugged_in ' + display_original, timeout=5)
                if d.shell('settings get global stay_on_while_plugged_in', timeout=5) != display_original:
                    raise RuntimeError('恢复后回读不一致')
                save(out / 'display-restore.json', {'original': display_original, 'restore_required': False, 'restored_at': now()})
                print('已恢复原亮屏设置。')
            except Exception as exc:
                result['display_restore_error'] = str(exc)
                print('手机连接不可用，亮屏设置尚未恢复。重新连接后双击“恢复亮屏设置.cmd”。')
        result['finished_at'] = now()
        save(out / 'result.json', result)
        try:
            history_file = record_attempt(ROOT, out, result, common.MANIFEST)
            if history_file:
                result['history_file'] = history_file
                print('本次测试结果已加入本机历史记录。', flush=True)
        except Exception as exc:
            result['history_error'] = str(exc)
            print('历史记录写入失败；本次完整日志仍保存在日志目录：' + str(exc), flush=True)
        save(out / 'result.json', result)

class Tee:
    def __init__(self, console, file):
        self.console, self.file = console, file
    def write(self, value):
        self.console.write(value)
        self.file.write(value)
        self.flush()
        return len(value)
    def flush(self):
        self.console.flush()
        self.file.flush()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='只读检查，不激活')
    parser.add_argument('--gui', action='store_true', help='输出图形界面事件')
    parser.add_argument('--confirmation', help='用户在界面选择执行时生成的环境确认文件')
    args = parser.parse_args()
    out = ROOT / 'logs' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    print('本次日志：' + str(out))
    if args.gui:
        print('@@UI ' + json.dumps({'event': 'log_directory', 'path': str(out)}, ensure_ascii=False), flush=True)
    with (out / 'console.txt').open('w', encoding='utf-8') as stream:
        original_out, original_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Tee(original_out, stream), Tee(original_err, stream)
        try:
            with ProcessLock(ROOT / 'running.lock'):
                return run(args, out)
        except Exception as exc:
            print('停止：' + str(exc))
            return 2
        finally:
            sys.stdout, sys.stderr = original_out, original_err

if __name__ == '__main__':
    raise SystemExit(main())
