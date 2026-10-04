"""Verified charging stay-awake settings with separate, device-bound recovery records."""
import datetime
import hashlib
import json
from pathlib import Path
import re

SETTING = 'stay_on_while_plugged_in'
GET = 'settings get global ' + SETTING


def now():
    return datetime.datetime.now().astimezone().isoformat()


def setting_value(raw):
    if not isinstance(raw, str):
        raise RuntimeError('充电常亮设置格式异常。')
    raw = raw.strip()
    if raw == 'null' or re.fullmatch(r'(?:[0-9]|1[0-5])', raw):
        return raw
    raise RuntimeError('无法确认充电常亮设置：' + (raw or '空返回值'))


def setting_label(value):
    if value == 'null':
        return '系统默认（未显式设置）'
    try:
        value = setting_value(str(value))
    except RuntimeError:
        return '状态未知'
    number = int(value)
    if not number:
        return '已关闭充电常亮'
    sources = [name for bit, name in ((1, '电源适配器'), (2, 'USB'), (4, '无线'), (8, '底座')) if number & bit]
    return '、'.join(sources) + '供电时常亮'


def bind_device(d):
    serial = d.call('get-serialno', timeout=5).strip()
    if not serial or serial.lower() in {'unknown', 'null'} or any(c.isspace() for c in serial):
        raise RuntimeError('无法确认当前手机，未修改常亮设置。')
    # Subsequent commands cannot accidentally select another newly attached phone.
    d.selector = ['-s', serial]
    return hashlib.sha256(serial.encode('utf-8')).hexdigest()


def read_value(d):
    return setting_value(d.shell(GET, timeout=5))


def write_value(d, value):
    value = setting_value(value)
    command = ('settings delete global ' + SETTING if value == 'null' else
               'settings put global ' + SETTING + ' ' + value)
    d.shell(command, timeout=5)
    actual = read_value(d)
    if actual != value:
        raise RuntimeError('设置命令已执行，但回读不一致；当前为“' + setting_label(actual) + '”。')
    return actual


def save_record(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def load_record(path):
    record = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(record, dict):
        raise RuntimeError('恢复记录格式异常。')
    if record.get('restore_required'):
        setting_value(record['original'])
        setting_value(record.get('last_applied', '7'))
    return record


def pending_records(root, key=None):
    pending, errors = [], []
    for path in sorted((Path(root) / 'logs').glob('*/display-restore.json')):
        try:
            record = load_record(path)
            if record.get('restore_required') and (key is None or record.get('device_key') in {None, key}):
                pending.append((path, record))
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            errors.append(str(path))
    return pending, errors


def manual_path(root, key):
    return Path(root) / 'display-state' / (key + '.json')


def status(d, root):
    result = {'known': False, 'label': '状态未知', 'raw': None, 'checked_at': now(),
              'manual_restore_available': False, 'temporary_restore_available': False,
              'baseline_label': '', 'recovery_error': ''}
    try:
        value = read_value(d)
        result.update(known=True, raw=value, label=setting_label(value))
    except RuntimeError as exc:
        result['error'] = str(exc)
    try:
        key = bind_device(d)
        path = manual_path(root, key)
        if path.is_file():
            record = load_record(path)
            if record.get('device_key') != key:
                raise RuntimeError('手动恢复记录与当前手机不一致。')
            result.update(manual_restore_available=bool(record.get('restore_required')),
                          baseline_label=setting_label(record.get('original')))
        pending, errors = pending_records(root, key)
        result['temporary_restore_available'] = bool(pending)
        result['legacy_restore_pending'] = any(not r.get('device_key') for _, r in pending)
        if errors:
            result['recovery_error'] = '有恢复记录无法读取，已保留原文件。'
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        result['recovery_error'] = str(exc)
    return result


def change_manual(d, root, action):
    key = bind_device(d)
    pending, errors = pending_records(root, key)
    if pending or errors:
        raise RuntimeError('有临时常亮待恢复或记录异常，请先检查并恢复临时设置。')
    path = manual_path(root, key)
    current = read_value(d)
    record = load_record(path) if path.is_file() else None
    if record and record.get('device_key') != key:
        raise RuntimeError('恢复记录与当前手机不一致，未修改设置。')
    if action == 'display-restore':
        if not record or not record.get('restore_required'):
            return {'message': '没有本工具的手动待恢复记录；当前为“' + setting_label(current) + '”。',
                    'display': status(d, root), 'changed': False}
        target = record['original']
        # Preserve a setting the user changed outside this tool.
        if current not in {target, record['last_applied']}:
            raise RuntimeError('常亮设置已在工具外发生变化，未覆盖；请检查手机设置。')
    else:
        target = '2' if action == 'display-enable' else '0'
        if current == target:
            return {'message': '当前已经是“' + setting_label(target) + '”，未修改设置。',
                    'display': status(d, root), 'changed': False}
        if not record or not record.get('restore_required'):
            record = {'original': current, 'device_key': key, 'created_at': now()}
        record.update(restore_required=True, last_applied=target)
        # Record BEFORE writing; a timeout can occur after the phone applies the setting.
        save_record(path, record)
    write_value(d, target)
    if action == 'display-restore':
        record.update(restore_required=False, restored_at=now())
        save_record(path, record)
    message = ('已恢复原设置：' if action == 'display-restore' else '已核验：') + setting_label(target) + '。'
    return {'message': message, 'display': status(d, root), 'changed': True}


def begin_temporary(d, root, out):
    key = bind_device(d)
    pending, errors = pending_records(root, key)
    if pending or errors:
        raise RuntimeError('存在待恢复或异常记录，跳过临时常亮。')
    original = read_value(d)
    # Keep system-default behavior unchanged when its effective value is unknown.
    if original == 'null':
        raise RuntimeError('当前使用系统默认，跳过临时常亮。')
    if int(original) & 2:
        return None  # USB stay-awake already enabled; no mutation or recovery needed.
    target = str(int(original) | 2)
    record = {'device_key': key, 'original': original, 'last_applied': target,
              'restore_required': True, 'created_at': now()}
    save_record(Path(out) / 'display-restore.json', record)
    write_value(d, target)
    return record


def restore_record(d, path, record):
    key = bind_device(d)
    if record.get('device_key') and record['device_key'] != key:
        raise RuntimeError('连接的手机与恢复记录不一致，未修改设置。')
    original = setting_value(record['original'])
    current = read_value(d)
    if current not in {original, record.get('last_applied', '7')}:
        raise RuntimeError('当前常亮设置已变化，未覆盖；原恢复记录已保留。')
    if current != original:
        write_value(d, original)
    record.update(restore_required=False, restored_at=now())
    save_record(path, record)
    return original


def restore_temporary(d, root):
    key = bind_device(d)
    pending, errors = pending_records(root, key)
    if errors:
        raise RuntimeError('有临时恢复记录无法读取，未覆盖手机设置；请查看日志。')
    if not pending:
        return {'changed': False, 'message': '没有本工具的临时待恢复记录。', 'display': status(d, root)}
    targets = {r['original'] for _, r in pending}
    applied = {r.get('last_applied', '7') for _, r in pending}
    if len(targets) != 1 or len(applied) != 1:
        raise RuntimeError('临时恢复记录不一致，未修改设置。')
    for path, record in pending:
        value = restore_record(d, path, record)
    return {'changed': True, 'message': '临时设置已恢复为：' + setting_label(value) + '。',
            'display': status(d, root)}
