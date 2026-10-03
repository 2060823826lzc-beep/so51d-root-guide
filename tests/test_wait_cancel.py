"""Regression checks for completion and cancellation; no live phone commands."""
import argparse
import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_detection_history import BASE, BOOT, FakeDevice, state
import one_click
import common
import device
import registry
import presentation


class WaitCancelTests(unittest.TestCase):
    def run_flow(self, locked=False, fail_restore=False, original_setting='0', fail_enable=False, pending=False, corrupt_pending=False):
        fake = FakeDevice(BASE, overrides={
            'getprop sys.boot.reason': 'normal', 'cat /proc/uptime': '100 200',
            'pm path --user 0 me.weishu.kernelsu': 'package:/data/test',
            'service check activity': 'Service activity: found',
            'pidof system_server zygote64 zygote': '1 2 3',
            'ps -A -o ARGS': 'sh',
            'settings get global stay_on_while_plugged_in': original_setting,
            'dumpsys window policy': 'showing=true' if locked else 'showing=false'})
        commands = []
        activated = []
        def call(self, *args, **kwargs):
            commands.append(args)
            if args[0] == 'pull':
                return ''
            if args[0] == 'shell':
                command = args[1]
                if command.startswith('if [ -d ') or command == 'su -c dmesg':
                    return ''
                if command.startswith('settings put global stay_on_while_plugged_in '):
                    value = command.rsplit(' ', 1)[-1]
                    if fail_enable and value == '7':
                        raise RuntimeError('Permission denied')
                    if fail_restore and value == '0':
                        raise RuntimeError('offline')
                    fake.values['settings get global stay_on_while_plugged_in'] = value
                    return ''
            return fake.call(*args, **kwargs)
        def activate(d):
            activated.append(True)
            fake.values.update({'su -c id': 'uid=0(root)', 'cat /proc/modules': 'kernelsu 1 0 - Live 0'})
        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, call(None, *argv[2:]), '')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(one_click.ROOT / 'profiles', root / 'profiles')
            shutil.copy2(one_click.ROOT / 'tools-manifest.json', root / 'tools-manifest.json')
            out = root / 'logs' / 'test'
            out.mkdir(parents=True)
            if pending or corrupt_pending:
                old = root / 'logs' / 'old'
                old.mkdir()
                (old / 'display-restore.json').write_text('{bad' if corrupt_pending else json.dumps(
                    {'original': '0', 'restore_required': True}), encoding='utf-8')
            choice = out / 'choice.json'
            choice.write_text(json.dumps(registry.make_confirmation(state(), False)), encoding='utf-8')
            args = argparse.Namespace(check=False, gui=True, confirmation=str(choice))
            with patch.object(one_click, 'ROOT', root), patch.object(one_click, 'verify_bundle'), \
                 patch.object(common, 'verify_payloads'), \
                 patch.object(one_click.subprocess, 'run', side_effect=fake_run), patch.object(device, 'activate', activate), \
                 patch('builtins.input', return_value='cancel'), \
                 patch.object(one_click.time, 'sleep', side_effect=AssertionError('Unexpected waiting')), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = one_click.run(args, out)
            result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
            restore_path = out / 'display-restore.json'
            restore = json.loads(restore_path.read_text(encoding='utf-8')) if restore_path.exists() else None
            history = list((root / 'history').glob('*.json'))
            row = json.loads(history[0].read_text(encoding='utf-8')) if history else None
            markers = list((root / 'attempts').glob('*.json'))
        return code, result, restore, row, markers, activated, commands

    def test_root_completes_without_wait_and_keeps_observation_honest(self):
        code, result, restore, row, markers, activated, _ = self.run_flow()
        self.assertEqual(code, 0)
        self.assertEqual(len(activated), 1)
        self.assertTrue(result['root_currently_verified'])
        self.assertFalse(restore['restore_required'])
        self.assertEqual(row['observation_mode'], 'immediate')
        self.assertFalse(row['five_minute_passed'])
        self.assertNotIn('五分钟观察有异常', presentation.root_summary(result)[0])

    def test_cancel_restores_display_without_activation_or_attempt_record(self):
        code, result, restore, row, markers, activated, _ = self.run_flow(locked=True)
        self.assertEqual(code, 0)
        self.assertEqual(result['outcome'], 'cancelled')
        self.assertFalse(restore['restore_required'])
        self.assertEqual(activated, [])
        self.assertEqual(markers, [])
        self.assertIsNone(row)

    def test_cancel_with_disconnect_keeps_recovery_record(self):
        _, result, restore, row, markers, activated, _ = self.run_flow(locked=True, fail_restore=True)
        self.assertTrue(restore['restore_required'])
        self.assertIn('display_restore_error', result)
        self.assertIn('恢复失败', presentation.root_summary(result)[0])
        self.assertEqual(activated, [])

    def test_unknown_original_values_never_block_root_or_write_settings(self):
        for value in ('null', '', 'Permission denied', '8'):
            with self.subTest(value=value):
                code, result, restore, _, _, activated, commands = self.run_flow(original_setting=value)
                self.assertEqual(code, 0)
                self.assertEqual(activated, [True])
                self.assertIsNone(restore)
                self.assertFalse(any('settings put' in str(command) for command in commands))

    def test_read_failure_never_blocks_root(self):
        code, result, restore, _, _, activated, commands = self.run_flow(original_setting=RuntimeError('ADB timeout'))
        self.assertEqual(code, 0)
        self.assertEqual(activated, [True])
        self.assertIsNone(restore)
        self.assertFalse(any('settings put' in str(command) for command in commands))

    def test_enable_failure_continues_root_and_attempts_restore(self):
        code, result, restore, _, _, activated, commands = self.run_flow(fail_enable=True)
        self.assertEqual(code, 0)
        self.assertEqual(activated, [True])
        self.assertFalse(restore['restore_required'])
        self.assertTrue(any('settings put global stay_on_while_plugged_in 0' in str(command) for command in commands))

    def test_pending_restore_does_not_block_root_or_overwrite_setting(self):
        code, result, restore, _, _, activated, commands = self.run_flow(pending=True)
        self.assertEqual(code, 0)
        self.assertEqual(activated, [True])
        self.assertIsNone(restore)
        self.assertFalse(any('settings put' in str(command) for command in commands))

    def test_corrupt_restore_record_does_not_block_root(self):
        code, result, restore, _, _, activated, commands = self.run_flow(corrupt_pending=True)
        self.assertEqual(code, 0)
        self.assertEqual(activated, [True])
        self.assertIsNone(restore)
        self.assertFalse(any('settings put' in str(command) for command in commands))

    def test_cancel_after_skipping_display_does_not_claim_restoration(self):
        code, result, restore, _, markers, activated, _ = self.run_flow(locked=True, original_setting='null')
        self.assertEqual(code, 0)
        self.assertEqual(activated, [])
        self.assertEqual(markers, [])
        self.assertIsNone(restore)
        self.assertIn('本次未修改', presentation.root_summary(result)[0])


if __name__ == '__main__':
    unittest.main()
