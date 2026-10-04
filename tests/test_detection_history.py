"""Offline behavioral tests. Every device operation is a mock; no live ADB."""
import argparse
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import common
import device
import gui_bridge
import one_click
import registry
import presentation as gui

BASE = {'hardware_device': 'SO-51D', 'android_api': '35', 'kernel': common.KERNEL,
        'owner_user': '0', 'boot_completed': '1', 'build': '67.2.A.3.55 release-keys',
        'fingerprint': 'sony/fixture', 'model': 'SO-51D', 'android_release': '15',
        'security_patch': '2025-01-01', 'abi': 'arm64-v8a'}
BOOT = '00000000-0000-0000-0000-000000000001'


def state(env=None):
    env = dict(BASE if env is None else env)
    return {'environment': env, 'assessment': registry.assess(env, ROOT), 'boot_id': BOOT,
            'compatible': registry.assess(env, ROOT)['eligible'], 'connected': True,
            'rooted': False, 'kernelsu_loaded': False, 'modules_known': True,
            'selinux': 'Enforcing', 'navigation_mode': '2', 'pill_known': True}


class FakeDevice(device.Device):
    def __init__(self, environment=None, overrides=None):
        super().__init__('fake-adb')
        self.commands = []
        env = dict(BASE if environment is None else environment)
        self.values = {
            'getprop ro.product.vendor.device': env['hardware_device'],
            'getprop ro.build.version.sdk': env['android_api'], 'uname -r': env['kernel'],
            'am get-current-user': env['owner_user'], 'getprop sys.boot_completed': env['boot_completed'],
            'getprop ro.build.display.id': env['build'], 'getprop ro.build.fingerprint': env['fingerprint'],
            'getprop ro.product.model': env['model'], 'getprop ro.build.version.release': env['android_release'],
            'getprop ro.build.version.security_patch': env['security_patch'],
            'getprop ro.product.cpu.abi': env['abi'], 'getenforce': 'Enforcing',
            'su -c id': 'not found', 'cat /proc/modules': '',
            'cat /proc/sys/kernel/random/boot_id': BOOT, 'settings get secure navigation_mode': '2',
            'dumpsys window policy': 'showing=false',
            'settings get global stay_on_while_plugged_in': '0',
            'cmd overlay list --user 0 com.android.systemui': '[ ] android:CodexGesturePill',
            'cmd overlay lookup --user 0 com.android.systemui com.android.systemui:color/navigation_bar_home_handle_dark_color': '#ffffffff',
            'cmd overlay lookup --user 0 com.android.systemui com.android.systemui:color/navigation_bar_home_handle_light_color': '#ff000000',
        }
        self.values.update(overrides or {})

    def call(self, *args, **kwargs):
        self.commands.append(args)
        if args == ('get-state',):
            return 'device'
        if args == ('get-serialno',):
            return 'fixture-serial'
        if args[0] == 'shell' and args[1] in self.values:
            value = self.values[args[1]]
            if isinstance(value, Exception):
                raise value
            return value
        raise AssertionError('Unexpected command: ' + str(args))


class CompatibilityTests(unittest.TestCase):
    def test_known_build_matches_real_root_record_without_stability_claim(self):
        value=registry.assess(BASE,ROOT)
        self.assertTrue(value['eligible'])
        rows,_=registry.history_rows(ROOT)
        row=next(x for x in rows if x['source']=='builtin')
        self.assertTrue(row['root_verified'])
        self.assertFalse(row['five_minute_passed'])

    def test_suffix_variants_match(self):
        for build in ('67.2.A.3.55',' 67.2.A.3.55  release-keys '):
            self.assertEqual(registry.assess(dict(BASE,build=build),ROOT)['matching_record_count'],1)

    def test_unknown_build_needs_no_checkbox(self):
        env=dict(BASE,build='67.2.A.3.115 release-keys')
        value=registry.assess(env,ROOT)
        self.assertTrue(value['eligible'])
        self.assertFalse(value['requires_acknowledgement'])
        self.assertTrue(registry.require_execution(env,ROOT)['attempt_allowed'])

    def test_all_models_apis_kernels_and_builds_can_attempt(self):
        for changes in ({'hardware_device':'OTHER'},{'android_api':'36'},{'kernel':'6.6.other'},
                        {'build':'unknown'},{'owner_user':'10'},{'boot_completed':'0'}):
            env=dict(BASE,**changes)
            d=FakeDevice(env)
            decision=registry.require_execution(env,ROOT)
            self.assertTrue(decision['attempt_allowed'])
            d.check()
            self.assertIsNotNone(d.selected_profile)
            self.assertEqual(d.inspect()['build'],env['build'])
            self.assertFalse(any(x[0] in ('install','push') for x in d.commands))

    def test_unknown_kernel_uses_named_default_and_displays_warning(self):
        value=registry.assess(dict(BASE,kernel='unknown'),ROOT)
        self.assertTrue(value['attempt_allowed'])
        self.assertFalse(value['profile_matched'])
        self.assertEqual(value['profile_id'],'so51d-12915929-cpu3-4')
        self.assertIn('默认实验配置',value['message'])

    def test_changed_environment_invalidates_user_choice(self):
        confirmation=registry.make_confirmation(state(),False)
        for changes in ({'build':'different'},{'fingerprint':'new'},{'owner_user':'10'}):
            with self.assertRaises(RuntimeError):
                registry.require_execution(dict(BASE,**changes),ROOT,confirmation,BOOT)

    def test_reboot_and_expired_confirmation_are_rejected(self):
        confirmation=registry.make_confirmation(state(),False)
        with self.assertRaisesRegex(RuntimeError,'重启'):
            registry.require_execution(BASE,ROOT,confirmation,'other-boot')
        confirmation['created_at_epoch']=time.time()-1000
        with self.assertRaisesRegex(RuntimeError,'过期'):
            registry.require_execution(BASE,ROOT,confirmation,BOOT)

    def test_profile_change_invalidates_choice(self):
        confirmation=registry.make_confirmation(state(),False)
        confirmation['profile_sha256']='0'*64
        with self.assertRaisesRegex(RuntimeError,'配置'):
            registry.require_execution(BASE,ROOT,confirmation,BOOT)

    def test_existing_root_skips_activation(self):
        d=FakeDevice(overrides={'su -c id':'uid=0(root)'})
        device.activate(d)
        self.assertFalse(any(x[0] in ('install','push') for x in d.commands))

    def test_loaded_module_without_shell_permission_stops(self):
        d=FakeDevice(overrides={'cat /proc/modules':'kernelsu 1 0 - Live 0'})
        with self.assertRaisesRegex(RuntimeError,'Shell'):
            device.activate(d)

    def test_inspection_failure_keeps_phone_environment_visible(self):
        d=FakeDevice(dict(BASE,hardware_device='OTHER',kernel='6.12-other'),overrides={
            'cat /proc/modules':RuntimeError('Permission denied'),
            'cmd overlay lookup --user 0 com.android.systemui com.android.systemui:color/navigation_bar_home_handle_dark_color':RuntimeError('missing resource')})
        with patch.object(device,'manager_status',return_value={'label':'未安装'}):
            value=gui_bridge.status(d)
        self.assertEqual(value['environment']['hardware_device'],'OTHER')
        self.assertFalse(value['compatible'])
        self.assertTrue(value['attempt_allowed'])
        self.assertFalse(value['modules_known'])
        self.assertFalse(value['pill_known'])

    def test_unknown_build_is_shown_without_blocking(self):
        d=FakeDevice(dict(BASE,build='67.2.A.3.115'))
        with patch.object(device,'manager_status',return_value={'label':'未安装'}):
            value=gui_bridge.status(d)
        self.assertFalse(value['assessment']['requires_acknowledgement'])
        self.assertTrue(value['attempt_allowed'])


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'profiles').mkdir()
        shutil.copy2(ROOT / 'profiles/catalog.json', self.root / 'profiles/catalog.json')
        shutil.copy2(ROOT / 'profiles/tested-records.json', self.root / 'profiles/tested-records.json')
        shutil.copy2(ROOT / 'tools-manifest.json', self.root / 'tools-manifest.json')
        self.out = self.root / 'logs' / 'test-one'
        self.out.mkdir(parents=True)
        self.result = {'activation_calls': 1, 'environment': dict(BASE, build='67.2.A.3.115'),
                       'root_currently_verified': True, 'all_health_samples_passed': True}
        self.final = {'boot_id': BOOT, 'root': 'uid=0(root)', 'kernelsu_loaded': True,
                      'healthy': True, 'elapsed_seconds': 301}
        self.samples = [dict(self.final, elapsed_seconds=0), self.final]
        self.write('before-state.json', {'boot_id': BOOT})

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        (self.out / name).write_text(json.dumps(value), encoding='utf-8')

    def record(self):
        self.write('observation.json', self.samples)
        self.write('final-state.json', self.final)
        path = registry.record_attempt(self.root, self.out, self.result, common.MANIFEST)
        return json.loads(Path(path).read_text(encoding='utf-8')) if path else None

    def test_success_records_separate_root_and_observation(self):
        row = self.record()
        self.assertTrue(row['root_verified'])
        self.assertTrue(row['five_minute_passed'])
        self.assertEqual(row['sample_count'], 2)
        self.assertNotIn('boot_id', json.dumps(row))
        self.assertNotIn('fingerprint', json.dumps(row))

    def test_partial_success_does_not_become_full_pass(self):
        self.samples[0]['healthy'] = False
        row = self.record()
        self.assertTrue(row['root_verified'])
        self.assertFalse(row['five_minute_passed'])

    def test_short_observation_is_not_pass(self):
        self.final['elapsed_seconds'] = 120
        self.assertFalse(self.record()['five_minute_passed'])

    def test_reboot_overrides_success_flag(self):
        self.final['boot_id'] = 'other-boot'
        row = self.record()
        self.assertFalse(row['root_verified'])
        self.assertFalse(row['five_minute_passed'])
        self.assertEqual(row['outcome'], 'rebooted')

    def test_missing_root_is_not_success_even_with_result_flag(self):
        self.final['root'] = 'permission denied'
        self.assertFalse(self.record()['root_verified'])

    def test_skipped_or_check_only_never_adds_success(self):
        self.result['activation_calls'] = 0
        self.assertIsNone(self.record())
        self.assertFalse((self.root / 'history').exists())

    def test_writing_same_attempt_is_idempotent(self):
        self.record()
        self.record()
        self.assertEqual(len(list((self.root / 'history').glob('*.json'))), 1)

    def test_local_success_becomes_known_build_only_for_matching_profile(self):
        self.record()
        value = registry.assess(self.result['environment'], self.root)
        self.assertFalse(value['requires_acknowledgement'])
        path = self.root / 'history/test-one.json'
        row = json.loads(path.read_text(encoding='utf-8'))
        row['profile_sha256'] = 'different'
        path.write_text(json.dumps(row), encoding='utf-8')
        self.assertEqual(registry.assess(self.result['environment'], self.root)['matching_record_count'],0)

    def test_failed_attempt_does_not_become_known_build(self):
        self.final['root'] = 'not found'
        self.record()
        self.assertEqual(registry.assess(self.result['environment'], self.root)['matching_record_count'],0)

    def test_corrupt_history_does_not_hide_builtin_records(self):
        (self.root / 'history').mkdir()
        (self.root / 'history/bad.json').write_text('{oops', encoding='utf-8')
        rows, errors = registry.history_rows(self.root)
        self.assertTrue(any(row['source'] == 'builtin' for row in rows))
        self.assertEqual(len(errors), 1)


class ButtonTests(unittest.TestCase):
    def test_connected_phone_can_be_selected(self):
        self.assertTrue(gui.execution_available(state()))

    def test_unknown_build_requires_no_checkbox(self):
        self.assertTrue(gui.execution_available(state(dict(BASE,build='unknown'))))

    def test_unknown_model_kernel_api_cannot_disable_button(self):
        value=state(dict(BASE,hardware_device='OTHER',kernel='different',android_api='30'))
        value['compatible']=False
        self.assertTrue(gui.execution_available(value))

    def test_missing_optional_diagnostics_do_not_disable_button(self):
        for change in ({'modules_known':False},{'selinux':'Permissive'},{'boot_id':''}):
            self.assertTrue(gui.execution_available(dict(state(),**change)))

    def test_existing_root_or_loaded_module_prevents_duplicate_activation(self):
        for change in ({'rooted':True},{'kernelsu_loaded':True},{'connected':False}):
            self.assertFalse(gui.execution_available(dict(state(),**change)))


class RunnerTests(unittest.TestCase):
    def run_mock(self, env, check, confirmation=None, rooted=False, loaded=False):
        fake = FakeDevice(env)
        fake.values.update({'su -c id': 'uid=0(root)' if rooted else 'not found',
            'cat /proc/modules': 'kernelsu 1 0 - Live 0' if loaded else '',
            'getprop sys.boot.reason': 'normal', 'cat /proc/uptime': '100 200',
            'pm path --user 0 me.weishu.kernelsu': 'package:/data/test',
            'service check activity': 'Service activity: found',
            'pidof system_server zygote64 zygote': '1 2 3',
            'ps -A -o ARGS': '/data/local/tmp/other/ghostlock x'})
        def fake_run(argv, **kwargs):
            output = fake.call(*argv[2:])
            return subprocess.CompletedProcess(argv, 0, output, '')
        (ROOT / 'logs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'logs') as temp:
            out = Path(temp)
            choice = None
            if confirmation:
                choice = out / 'choice.json'
                choice.write_text(json.dumps(confirmation), encoding='utf-8')
            args = argparse.Namespace(check=check, gui=True, confirmation=str(choice) if choice else None)
            with patch.object(one_click, 'verify_bundle'), patch.object(common, 'verify_payloads'), patch.object(one_click.subprocess, 'run', side_effect=fake_run), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = one_click.run(args, out)
            result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
        self.assertFalse(any(x[0] in ('install', 'push') or 'settings put' in str(x) or 'nohup' in str(x)
                             for x in fake.commands))
        return code, result

    def test_check_only_unknown_phone_is_allowed(self):
        _, result = self.run_mock(dict(BASE, hardware_device='OTHER', kernel='other'), True)
        self.assertEqual(result['outcome'], 'read_only_check')
        self.assertTrue(result['assessment']['attempt_allowed'])

    def test_gui_without_choice_stops_before_mutations(self):
        _, result = self.run_mock(BASE, False)
        self.assertEqual(result['outcome'], 'stopped')
        self.assertEqual(result['activation_calls'], 0)

    def test_untested_without_ack_reaches_duplicate_worker_check(self):
        env = dict(BASE, build='67.2.A.3.115')
        _, result = self.run_mock(env, False, registry.make_confirmation(state(env), False))
        self.assertEqual(result['outcome'], 'stopped')
        self.assertIn('已有 GhostLock', result['error'])

    def test_untested_ack_still_preserves_duplicate_worker_guard(self):
        env = dict(BASE, build='67.2.A.3.115')
        _, result = self.run_mock(env, False, registry.make_confirmation(state(env), True))
        self.assertIn('已有 GhostLock', result['error'])
        self.assertEqual(result['activation_calls'], 0)

    def test_existing_root_skipped_and_not_added_to_history(self):
        _, result = self.run_mock(BASE, False, registry.make_confirmation(state(), False), rooted=True, loaded=True)
        self.assertEqual(result['outcome'], 'already_rooted')
        self.assertNotIn('history_file', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
