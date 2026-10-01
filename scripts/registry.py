"""Read-only compatibility assessment and local evidence index. No ADB on import."""
import datetime
import json
import os
from pathlib import Path
import time

ENVIRONMENT_KEYS = ('hardware_device', 'android_api', 'kernel', 'build', 'fingerprint',
                    'owner_user', 'boot_completed')


def canonical_build(value):
    parts = str(value or '').split()
    if len(parts) == 2 and parts[1] == 'release-keys':
        return parts[0]
    return ' '.join(parts)


def load_catalog(root):
    catalog = json.loads((Path(root) / 'profiles' / 'catalog.json').read_text(encoding='utf-8'))
    if catalog.get('schema_version') != 1 or not catalog.get('profiles'):
        raise RuntimeError('当前工具的配置目录格式不正确。')
    manifest = json.loads((Path(root) / 'tools-manifest.json').read_text(encoding='utf-8'))
    ids, targets = set(), set()
    for entry in catalog['profiles']:
        if entry['id'] in ids:
            raise RuntimeError('配置目录包含重复ID。')
        ids.add(entry['id'])
        file = (Path(root) / entry['file']).resolve()
        if not file.is_relative_to((Path(root) / 'profiles').resolve()):
            raise RuntimeError('配置路径超出配置目录。')
        for model in entry.get('hardware_devices', [entry['hardware_device']]):
            target = (model, entry['kernel'], entry['android_api'])
            if target in targets:
                raise RuntimeError('同一手机内核匹配到了多个配置。')
            targets.add(target)
    profile = catalog['profiles'][0]
    # History never selects a native profile; only this pinned descriptor may do so.
    if (profile['kernel'] != manifest['kernel'] or profile['file'] != manifest['profile']
            or profile['sha256'] != manifest['profile_sha256']):
        raise RuntimeError('配置目录与原生文件清单不一致。')
    return catalog


def profile_by_id(root, profile_id):
    for profile in load_catalog(root)['profiles']:
        if profile['id'] == profile_id:
            return profile
    raise RuntimeError('找不到选中的内核配置。')


def history_rows(root):
    root = Path(root)
    builtin = json.loads((root / 'profiles' / 'tested-records.json').read_text(encoding='utf-8'))
    rows = [dict(row, source='builtin') for row in builtin['records']]
    errors = []
    for path in sorted((root / 'history').glob('*.json'), reverse=True):
        try:
            row = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(row, dict) or row.get('schema_version') != 1:
                raise ValueError('记录格式不正确')
            rows.append(dict(row, source='local'))
        except (ValueError, OSError) as exc:
            errors.append(f'{path.name}: {exc}')
    return rows, errors


def root_evidence(row):
    return (row.get('activation_calls') == 1 and row.get('root_verified') is True
            and row.get('kernelsu_loaded') is True and row.get('same_boot') is True
            and row.get('reboot_observed') is not True)


def assess(environment, root):
    catalog = load_catalog(root)
    matches = [entry for entry in catalog['profiles'] if environment.get('kernel') == entry['kernel']]
    profile = matches[0] if matches else catalog['profiles'][0]
    mismatches = []
    models = profile.get('hardware_devices', [profile['hardware_device']])
    if environment.get('hardware_device') not in models:
        mismatches.append({'field': 'hardware_device', 'actual': environment.get('hardware_device', ''),
                           'expected': '/'.join(models)})
    for key, expected in [('kernel', profile['kernel']), ('android_api', profile['android_api'])]:
        if environment.get(key) != expected:
            mismatches.append({'field': key, 'actual': environment.get(key, ''), 'expected': expected})
    operational = []
    if environment.get('owner_user') != '0':
        operational.append('请切换到机主用户。')
    if environment.get('boot_completed') != '1':
        operational.append('系统尚未完成启动，请稍后刷新。')
    if not environment.get('build', '').strip():
        operational.append('没有读到固件号，无法核对执行环境。')
    rows, history_errors = history_rows(root)
    known = [row for row in rows if root_evidence(row)
             and row.get('profile_id') == profile['id']
             and row.get('profile_sha256') == profile['sha256']
             and row.get('environment', {}).get('hardware_device') == environment.get('hardware_device')
             and row.get('environment', {}).get('kernel') == environment.get('kernel')
             and row.get('environment', {}).get('android_api') == environment.get('android_api')
             and canonical_build(row.get('environment', {}).get('build')) == canonical_build(environment.get('build'))]
    matched = bool(matches)
    if not matched:
        message = ('未找到对应内核配置，将使用默认实验配置：' + profile['label']
                   + '。仍可点击尝试；原生程序可能返回内核不匹配或失败。')
        level = 'experimental_default'
    elif not known:
        message = '已按完整内核选中：' + profile['label'] + '。此手机没有本机成功记录，可自行选择尝试。'
        if profile.get('evidence_note'):
            message += ' ' + profile['evidence_note']
        level = 'untested_build'
    else:
        message = f'型号、内核和固件已有 {len(known)} 条 Root 成功记录；具体观察结果见历史记录。'
        level = 'recorded_build'
    if operational:
        message += ' 检测提示：' + ' '.join(operational)
    return {'profile_matched': matched, 'eligible': True, 'attempt_allowed': True, 'level': level,
            'requires_acknowledgement': False, 'message': message,
            'profile_id': profile['id'], 'profile_sha256': profile['sha256'],
            'profile_file': profile['file'], 'profile_label': profile['label'],
            'pill_supported': not mismatches and profile.get('pill_supported', False),
            'mismatches': mismatches, 'operational_reasons': operational,
            'matching_record_count': len(known), 'history_errors': history_errors}


def make_confirmation(state, acknowledged):
    return {'schema_version': 1, 'created_at_epoch': time.time(),
            'environment': {key: state['environment'].get(key, '') for key in ENVIRONMENT_KEYS},
            'boot_id': state['boot_id'],
            'profile_id': state['assessment']['profile_id'],
            'profile_sha256': state['assessment']['profile_sha256'],
            'acknowledged_untested_build': bool(acknowledged)}


def require_execution(environment, root, confirmation=None, current_boot=None):
    decision = assess(environment, root)
    if confirmation is not None:
        if confirmation.get('schema_version') != 1:
            raise RuntimeError('执行确认格式不正确，请刷新状态。')
        age = time.time() - confirmation.get('created_at_epoch', 0)
        if not 0 <= age <= 900:
            raise RuntimeError('检测结果已过期，请刷新状态后重新选择执行。')
        if confirmation.get('boot_id') != current_boot:
            raise RuntimeError('手机已重启或更换，请刷新状态后重新选择执行。')
        current = {key: environment.get(key, '') for key in ENVIRONMENT_KEYS}
        if confirmation.get('environment') != current:
            raise RuntimeError('手机信息已改变，请刷新状态后重新选择执行。')
        if (confirmation.get('profile_id') != decision['profile_id']
                or confirmation.get('profile_sha256') != decision['profile_sha256']):
            raise RuntimeError('所选配置已改变，请刷新状态。')
    return decision


def record_attempt(root, log_folder, result, manifest):
    """One summary per actual invocation; skipped/check-only runs never become successes."""
    if result.get('activation_calls') != 1:
        return None
    samples = []
    observation = Path(log_folder) / 'observation.json'
    if observation.is_file():
        samples = json.loads(observation.read_text(encoding='utf-8'))
    before_path = Path(log_folder) / 'before-state.json'
    before = json.loads(before_path.read_text(encoding='utf-8')) if before_path.is_file() else {}
    final_path = Path(log_folder) / 'final-state.json'
    final = json.loads(final_path.read_text(encoding='utf-8')) if final_path.is_file() else (samples[-1] if samples else {})
    same_boot = bool(before.get('boot_id') and final.get('boot_id') == before['boot_id'])
    reboot = result.get('reboot_observed') is True or bool(
        before.get('boot_id') and final.get('boot_id') and final['boot_id'] != before['boot_id'])
    root_verified = (same_boot and not reboot and 'uid=0(root)' in final.get('root', '')
                     and final.get('kernelsu_loaded') is True)
    observed = max((sample.get('elapsed_seconds', 0) for sample in samples), default=0)
    passed = bool(root_verified and samples and observed >= 300
                  and result.get('all_health_samples_passed') is True
                  and all(sample.get('healthy') is True for sample in samples))
    selected = result.get('assessment') or assess(result.get('environment', {}), root)
    row = {'schema_version': 1, 'id': Path(log_folder).name,
           'tested_at': result.get('finished_at') or datetime.datetime.now().astimezone().isoformat(),
           'environment': {key: result.get('environment', {}).get(key, '') for key in
                           ('hardware_device', 'android_api', 'kernel', 'build')},
           'profile_id': selected.get('profile_id'), 'profile_sha256': selected.get('profile_sha256'),
           'profile_matched': selected.get('profile_matched') is True,
           'execution_policy': 'user_choice_all_models',
           'native_sha256': manifest['packages'][0]['extract']['sha256'],
           'activation_calls': 1, 'root_verified': root_verified,
           'kernelsu_loaded': final.get('kernelsu_loaded') is True,
           'same_boot': same_boot, 'reboot_observed': reboot,
           'observation_seconds': observed, 'sample_count': len(samples),
           'observation_mode': result.get('observation_mode', 'five_minute'),
           'five_minute_passed': passed,
           'outcome': 'rebooted' if reboot else 'root_verified' if root_verified else 'root_not_confirmed',
           'note': ('Root 已取得，当前状态已核验；未进行五分钟观察。' if root_verified and result.get('observation_mode') == 'immediate' else
                    'Root 已取得，五分钟采样通过；不代表长期稳定。' if passed else
                    'Root 已取得，观察有异常或未完整通过。' if root_verified else
                    '执行期间检测到重启。' if reboot else 'Root 未确认，详见本机日志。'),
           'log_directory': 'logs/' + Path(log_folder).name}
    folder = Path(root) / 'history'
    folder.mkdir(exist_ok=True)
    destination = folder / (Path(log_folder).name + '.json')
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, destination)
    return str(destination)
