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
import device
import common
import registry
import presentation


class WaitCancelTests(unittest.TestCase):
    def run_flow(self, locked=False, fail_restore=False):
        fake = FakeDevice(BASE, overrides={
            'getprop sys.boot.reason': 'normal', 'cat /proc/uptime': '100 200',
            'pm path --user 0 me.weishu.kernelsu': 'package:/data/test',
            'service check activity': 'Service activity: found',
            'pidof system_server zygote64 zygote': '1 2 3',
            'ps -A -o ARGS': 'sh',
            'settings get global stay_on_while_plugged_in': '0',
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
            choice = out / 'choice.json'
            choice.write_text(json.dumps(registry.make_confirmation(state(), False)), encoding='utf-8')
            args = argparse.Namespace(check=False, gui=True, confirmation=str(choice))
            with patch.object(one_click, 'ROOT', root), patch.object(one_click, 'verify_bundle'), patch.object(common, 'verify_payloads'), \
                 patch.object(one_click.subprocess, 'run', side_effect=fake_run), patch.object(device, 'activate', activate), \
                 patch('builtins.input', return_value='cancel'), \
                 patch.object(one_click.time, 'sleep', side_effect=AssertionError('Unexpected waiting')), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = one_click.run(args, out)
            result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
            restore = json.loads((out / 'display-restore.json').read_text(encoding='utf-8'))
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


if __name__ == '__main__':
    unittest.main()
