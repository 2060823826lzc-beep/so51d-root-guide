"""Restore only a pending stay-awake setting recorded by this bundle."""
import json
from pathlib import Path
import re
import subprocess
from one_click import ProcessLock, ROOT, verify_bundle

def main():
    with ProcessLock(ROOT / 'running.lock'):
        verify_bundle()
        pending = []
        for path in sorted((ROOT / 'logs').glob('*/display-restore.json')):
            record = json.loads(path.read_text(encoding='utf-8'))
            if record.get('restore_required'):
                pending.append((path, record))
        if not pending:
            print('没有待恢复的临时亮屏设置。')
            return
        values = {r['original'] for _, r in pending}
        if len(values) != 1 or not re.fullmatch(r'[0-7]', next(iter(values))):
            raise RuntimeError('待恢复记录不一致，请先检查日志。')
        original = values.pop()
        def shell(command):
            p = subprocess.run([str(ROOT / 'platform-tools' / 'adb.exe'), '-d', 'shell', command],
                               capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if p.returncode:
                raise RuntimeError(p.stderr.strip() or p.stdout.strip())
            return p.stdout.strip()
        current = shell('settings get global stay_on_while_plugged_in')
        if current not in {original, '7'}:
            raise RuntimeError('当前设置与临时值不同，可能已被你修改，未覆盖。')
        if current != original:
            shell('settings put global stay_on_while_plugged_in ' + original)
        if shell('settings get global stay_on_while_plugged_in') != original:
            raise RuntimeError('未能确认恢复成功。')
        for path, record in pending:
            record['restore_required'] = False
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print('原亮屏设置已恢复为 ' + original + '。没有执行 Root。')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('停止：' + str(exc))
        raise SystemExit(2)
