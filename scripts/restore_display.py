"""Restore only a pending stay-awake setting recorded by this bundle."""
from one_click import ProcessLock, ROOT, verify_bundle
from device import Device
from display_settings import restore_temporary

def main():
    with ProcessLock(ROOT / 'running.lock'):
        verify_bundle()
        result = restore_temporary(Device(str(ROOT / 'platform-tools' / 'adb.exe')), ROOT)
        print(result['message'])
        return result

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('停止：' + str(exc))
        raise SystemExit(2)
