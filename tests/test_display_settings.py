"""Device-bound manual baselines, readback checks, and independent temporary recovery."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import display_settings as display


class Phone:
    def __init__(self, value='0', serial='test-phone-a'):
        self.value, self.serial = value, serial
        self.selector = ['-d']
        self.commands = []
        self.fail_read = self.fail_write = self.ignore_write = False

    def call(self, *args, **kwargs):
        if args == ('get-serialno',):
            return self.serial
        raise AssertionError(args)

    def shell(self, command, **kwargs):
        self.commands.append(command)
        if command == display.GET:
            if self.fail_read:
                raise RuntimeError('offline')
            return self.value
        if self.fail_write:
            raise RuntimeError('write timeout')
        if not self.ignore_write:
            self.value = 'null' if command.startswith('settings delete') else command.rsplit(' ', 1)[-1]
        return ''


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.phone = Phone('4')
        self.out = self.root / 'logs/test'
        self.out.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def manual_record(self):
        key = hashlib.sha256(self.phone.serial.encode()).hexdigest()
        return display.load_record(display.manual_path(self.root, key))

    def test_manual_repeated_toggles_preserve_first_baseline(self):
        display.change_manual(self.phone, self.root, 'display-enable')
        display.change_manual(self.phone, self.root, 'display-disable')
        display.change_manual(self.phone, self.root, 'display-enable')
        self.assertEqual(self.manual_record()['original'], '4')
        result = display.change_manual(self.phone, self.root, 'display-restore')
        self.assertEqual(self.phone.value, '4')
        self.assertFalse(self.manual_record()['restore_required'])
        self.assertIn('无线', result['message'])

    def test_next_manual_session_captures_new_baseline(self):
        display.change_manual(self.phone, self.root, 'display-enable')
        display.change_manual(self.phone, self.root, 'display-restore')
        self.phone.value = '1'
        display.change_manual(self.phone, self.root, 'display-disable')
        self.assertEqual(self.manual_record()['original'], '1')

    def test_unset_original_is_restored_by_deleting_setting(self):
        self.phone.value = 'null'
        display.change_manual(self.phone, self.root, 'display-enable')
        display.change_manual(self.phone, self.root, 'display-restore')
        self.assertEqual(self.phone.value, 'null')
        self.assertIn('settings delete global ' + display.SETTING, self.phone.commands)

    def test_manual_noop_does_not_create_false_recovery(self):
        self.phone.value = '2'
        result = display.change_manual(self.phone, self.root, 'display-enable')
        self.assertFalse(result['changed'])
        self.assertFalse(result['display']['manual_restore_available'])

    def test_restore_without_record_does_not_claim_restored(self):
        result = display.change_manual(self.phone, self.root, 'display-restore')
        self.assertFalse(result['changed'])
        self.assertIn('没有', result['message'])
        self.assertEqual(self.phone.value, '4')

    def test_write_without_matching_readback_retains_recovery(self):
        self.phone.ignore_write = True
        with self.assertRaisesRegex(RuntimeError, '回读不一致'):
            display.change_manual(self.phone, self.root, 'display-enable')
        self.assertTrue(self.manual_record()['restore_required'])

    def test_failed_write_retains_recovery_before_command(self):
        self.phone.fail_write = True
        with self.assertRaises(RuntimeError):
            display.change_manual(self.phone, self.root, 'display-enable')
        self.assertEqual(self.manual_record()['original'], '4')
        self.assertTrue(self.manual_record()['restore_required'])

    def test_unreadable_setting_never_written(self):
        self.phone.fail_read = True
        state = display.status(self.phone, self.root)
        self.assertFalse(state['known'])
        self.assertEqual(state['label'], '状态未知')
        with self.assertRaises(RuntimeError):
            display.change_manual(self.phone, self.root, 'display-enable')
        self.assertFalse(any('settings put' in c for c in self.phone.commands))

    def test_manual_records_are_isolated_between_phones(self):
        display.change_manual(self.phone, self.root, 'display-enable')
        other = Phone('0', 'test-phone-b')
        self.assertFalse(display.status(other, self.root)['manual_restore_available'])
        display.change_manual(other, self.root, 'display-restore')
        self.assertEqual(other.value, '0')

    def test_temporary_record_cannot_restore_on_other_phone(self):
        record = display.begin_temporary(self.phone, self.root, self.out)
        other = Phone('6', 'test-phone-b')
        with self.assertRaisesRegex(RuntimeError, '不一致'):
            display.restore_record(other, self.out / 'display-restore.json', record)
        self.assertEqual(other.value, '6')

    def test_root_temporary_does_not_replace_manual_baseline(self):
        display.change_manual(self.phone, self.root, 'display-disable')
        record = display.begin_temporary(self.phone, self.root, self.out)
        self.assertEqual(self.phone.value, '2')
        display.restore_record(self.phone, self.out / 'display-restore.json', record)
        self.assertEqual(self.phone.value, '0')
        self.assertEqual(self.manual_record()['original'], '4')
        display.change_manual(self.phone, self.root, 'display-restore')
        self.assertEqual(self.phone.value, '4')

    def test_temporary_preserves_other_power_modes(self):
        record = display.begin_temporary(self.phone, self.root, self.out)
        self.assertEqual(self.phone.value, '6')
        display.restore_record(self.phone, self.out / 'display-restore.json', record)
        self.assertEqual(self.phone.value, '4')

    def test_external_changes_not_overwritten_on_restore(self):
        display.change_manual(self.phone, self.root, 'display-enable')
        self.phone.value = '1'
        with self.assertRaisesRegex(RuntimeError, '工具外'):
            display.change_manual(self.phone, self.root, 'display-restore')
        self.assertEqual(self.phone.value, '1')

    def test_pending_temporary_blocks_only_manual_changes(self):
        display.begin_temporary(self.phone, self.root, self.out)
        with self.assertRaisesRegex(RuntimeError, '临时常亮待恢复'):
            display.change_manual(self.phone, self.root, 'display-disable')
        result = display.restore_temporary(self.phone, self.root)
        self.assertTrue(result['changed'])
        self.assertFalse(result['display']['temporary_restore_available'])

    def test_legacy_recovery_retains_existing_value_semantics(self):
        record = {'original': '0', 'restore_required': True}
        display.save_record(self.out / 'display-restore.json', record)
        self.phone.value = '7'
        state = display.status(self.phone, self.root)
        self.assertTrue(state['legacy_restore_pending'])
        display.restore_temporary(self.phone, self.root)
        self.assertEqual(self.phone.value, '0')

    def test_corrupt_record_is_unknown_and_does_not_claim_restored(self):
        (self.out / 'display-restore.json').write_text('[]', encoding='utf-8')
        self.assertIn('无法读取', display.status(self.phone, self.root)['recovery_error'])
        with self.assertRaisesRegex(RuntimeError, '无法读取'):
            display.restore_temporary(self.phone, self.root)
        self.assertEqual(self.phone.value, '4')

    def test_no_temporary_record_is_not_restore_success(self):
        result = display.restore_temporary(self.phone, self.root)
        self.assertFalse(result['changed'])
        self.assertIn('没有', result['message'])

    def test_all_power_masks_have_readable_labels(self):
        self.assertEqual(display.setting_label('0'), '已关闭充电常亮')
        self.assertEqual(display.setting_label('2'), 'USB供电时常亮')
        self.assertIn('底座', display.setting_label('8'))
        self.assertIn('系统默认', display.setting_label('null'))
        self.assertEqual(display.setting_label('16'), '状态未知')


if __name__ == '__main__':
    unittest.main()
