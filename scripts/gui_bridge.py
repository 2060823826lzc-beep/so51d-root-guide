"""Small, serialized backend for status and reversible gesture-handle actions."""
import argparse
import datetime
import json
from pathlib import Path
import time

import common
import device
from registry import assess
from one_click import ProcessLock, ROOT, REMOTE, verify_bundle, locked

device.REMOTE = REMOTE

def emit(kind, value):
    print('@@' + kind + ' ' + json.dumps(value, ensure_ascii=False), flush=True)

def gesture_state(overlay_list, dark, light):
    enabled = '[x] android:CodexGesturePill' in overlay_list.splitlines()
    transparent = dark.lower() in {'#0', '#00000000'} and light.lower() in {'#0', '#00000000'}
    return {'hidden': transparent, 'own_overlay_enabled': enabled,
            'dark_color': dark, 'light_color': light}

def status(d):
    connection = d.call('get-state', check=False, timeout=6)
    if connection != 'device':
        if 'unauthorized' in connection.lower():
            raise RuntimeError('请在手机上允许 USB 调试，然后点击“刷新状态”。')
        if 'more than one' in connection.lower():
            raise RuntimeError('检测到多台 USB 设备，请只连接需要操作的这台手机。')
        raise RuntimeError('未连接手机。请连接数据线、开启 USB 调试，并在手机上允许此电脑。')
    environment = d.inspect()
    assessment = assess(environment, ROOT)
    diagnostics = []
    def read(command, timeout=8):
        try:
            return d.shell(command, timeout=timeout)
        except RuntimeError as exc:
            diagnostics.append({'command': command, 'error': str(exc)})
            return ''
    try:
        root = d.shell('su -c id', check=False, timeout=8)
    except RuntimeError as exc:
        root = ''
        diagnostics.append({'command': 'su -c id', 'error': str(exc)})
    modules = read('cat /proc/modules')
    try:
        manager = device.manager_status(d)
    except RuntimeError as exc:
        manager = {'state': 'unknown', 'label': '未确认', 'error': str(exc)}
        diagnostics.append({'command': 'manager_status', 'error': str(exc)})
    dark = read('cmd overlay lookup --user 0 com.android.systemui com.android.systemui:color/navigation_bar_home_handle_dark_color')
    light = read('cmd overlay lookup --user 0 com.android.systemui com.android.systemui:color/navigation_bar_home_handle_light_color')
    overlays = read('cmd overlay list --user 0 com.android.systemui')
    value = {'connected': True, 'compatible': assessment['profile_matched'],
             'attempt_allowed': True, 'environment': environment,
             'assessment': assessment, 'diagnostics': diagnostics,
             'pill_supported': bool(dark and light and overlays) and environment.get('owner_user') == '0',
             'rooted': 'uid=0(root)' in root, 'kernelsu_loaded': device.module_loaded(modules),
             'modules_known': bool(modules) or not any(x['command'] == 'cat /proc/modules' for x in diagnostics),
             'root_detail': root, 'manager': manager,
             'selinux': read('getenforce'), 'boot_id': read('cat /proc/sys/kernel/random/boot_id'),
             'navigation_mode': read('settings get secure navigation_mode'),
             'locked': locked(read('dumpsys window policy')),
             'pill_known': bool(dark and light and overlays)}
    value.update(gesture_state(overlays, dark, light))
    return value

def change_pill(d, action):
    before = status(d)
    if before.get('pill_supported') is False:
        raise RuntimeError('无法读取手势条颜色资源或覆盖接口，请确认处于机主用户并刷新检测。')
    if not before['rooted']:
        raise RuntimeError('隐藏或恢复小白条需要 Root。请先激活 Root；如模块已加载，请在 KernelSU 中检查 Shell 授权。')
    if before['locked']:
        raise RuntimeError('请先解锁手机、保持屏幕亮起，再点击此按钮。')
    if action == 'hide' and before['navigation_mode'] != '2':
        raise RuntimeError('当前不是手势导航。请先在手机设置中切换为手势导航。')
    original = before['boot_id']
    device.pill(d, action)
    after = None
    last_error = None
    for _ in range(5):
        try:
            after = status(d)
            break
        except RuntimeError as exc:
            last_error = exc
            time.sleep(1)
    if after is None:
        raise RuntimeError('操作已执行，但界面刷新后未能核验结果。请解锁后刷新状态。' + str(last_error))
    if after['boot_id'] != original:
        raise RuntimeError('期间手机发生了重启，未确认设置结果。请查看日志并刷新状态。')
    if after['navigation_mode'] != before['navigation_mode']:
        raise RuntimeError('导航模式发生变化，请检查手机设置；未确认操作成功。')
    if action == 'hide' and not (after['hidden'] and after['own_overlay_enabled']):
        raise RuntimeError('未确认两种手势条颜色均已透明，请查看日志。')
    if action == 'show' and after['own_overlay_enabled']:
        raise RuntimeError('本工具的覆盖仍启用，未确认恢复。')
    note = ('已隐藏小白条，手势导航保留。' if action == 'hide' else
            '已恢复小白条。' if not after['hidden'] else '已移除本工具的覆盖，但其他配置仍让手势条透明。')
    return {'action': action, 'message': note, 'before': before, 'state': after}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'hide', 'show', 'restore-display'])
    args = parser.parse_args()
    out = ROOT / 'logs' / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + args.action)
    out.mkdir(parents=True)
    emit('UI', {'event': 'log_directory', 'path': str(out)})
    class LoggedDevice(device.Device):
        def call(self, *command, **kwargs):
            record = {'time': datetime.datetime.now().astimezone().isoformat(), 'args': command}
            try:
                value = super().call(*command, **kwargs)
                record['output'] = value
                return value
            except Exception as exc:
                record['error'] = str(exc)
                raise
            finally:
                with (out / 'adb-events.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
    result = {'action': args.action}
    try:
        verify_bundle()
        d = LoggedDevice(str(ROOT / 'platform-tools' / 'adb.exe'))
        if args.action == 'restore-display':
            import restore_display
            restore_display.main()
            result.update(ok=True, message='临时亮屏设置已检查并恢复。')
        else:
            with ProcessLock(ROOT / 'running.lock'):
                if args.action == 'status':
                    result.update(ok=True, state=status(d))
                else:
                    result.update(ok=True, **change_pill(d, args.action))
        emit('RESULT', result)
        return 0
    except Exception as exc:
        result.update(ok=False, error=str(exc))
        emit('RESULT', result)
        return 2
    finally:
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    raise SystemExit(main())
