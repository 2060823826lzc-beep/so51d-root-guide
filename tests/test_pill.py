import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import gui_bridge as bridge
import one_click
from registry import assess
import presentation as gui

class PillTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(compatible=True, rooted=True, locked=False, boot_id='boot', navigation_mode='2',
                           hidden=False, own_overlay_enabled=False)
        self.before['environment'] = {'hardware_device': 'SO-51D', 'android_api': '35',
            'kernel': bridge.common.KERNEL,
            'owner_user': '0', 'boot_completed': '1', 'build': '67.2.A.3.55'}
        self.before['assessment'] = assess(self.before['environment'], ROOT)
        self.d = Mock()

    def run_change(self, action, before, after=None):
        states = [before] + ([after] if after is not None else [])
        with patch.object(bridge, 'status', side_effect=states), patch.object(bridge.device, 'pill') as operation:
            value = bridge.change_pill(self.d, action)
        return value, operation

    def test_unmatched_root_profile_does_not_block_pill(self):
        self.before['compatible'] = False
        self.before['pill_supported'] = True
        self.before['environment']['hardware_device'] = 'XQ-DQ72'
        self.before['environment']['kernel'] = 'different-kernel'
        after = dict(self.before, hidden=True, own_overlay_enabled=True)
        result, operation = self.run_change('hide', self.before, after)
        operation.assert_called_once_with(self.d, 'hide')
        self.assertTrue(result['state']['hidden'])

    def test_missing_resources_blocks_before_mutation(self):
        self.before['pill_supported'] = False
        with patch.object(bridge, 'status', return_value=self.before), patch.object(bridge.device, 'pill') as operation:
            with self.assertRaisesRegex(RuntimeError, '颜色资源'):
                bridge.change_pill(self.d, 'hide')
            operation.assert_not_called()

    def test_no_root_never_changes_pill(self):
        self.before['rooted'] = False
        with patch.object(bridge, 'status', return_value=self.before), patch.object(bridge.device, 'pill') as action:
            with self.assertRaisesRegex(RuntimeError, '需要 Root'):
                bridge.change_pill(self.d, 'hide')
            action.assert_not_called()

    def test_locked_never_changes_pill(self):
        self.before['locked'] = True
        with patch.object(bridge, 'status', return_value=self.before), patch.object(bridge.device, 'pill') as action:
            with self.assertRaisesRegex(RuntimeError, '解锁'):
                bridge.change_pill(self.d, 'hide')
            action.assert_not_called()

    def test_buttons_navigation_rejected_before_hide(self):
        self.before['navigation_mode'] = '0'
        with patch.object(bridge, 'status', return_value=self.before), patch.object(bridge.device, 'pill') as action:
            with self.assertRaisesRegex(RuntimeError, '手势导航'):
                bridge.change_pill(self.d, 'hide')
            action.assert_not_called()

    def test_hide_verifies_actual_colors_and_overlay(self):
        after = dict(self.before, hidden=True, own_overlay_enabled=True)
        result, operation = self.run_change('hide', self.before, after)
        operation.assert_called_once_with(self.d, 'hide')
        self.assertTrue(result['state']['hidden'])

    def test_hidden_flag_alone_not_sufficient(self):
        after = dict(self.before, hidden=True, own_overlay_enabled=False)
        with self.assertRaisesRegex(RuntimeError, '未确认'):
            self.run_change('hide', self.before, after)

    def test_reboot_during_operation_is_not_success(self):
        after = dict(self.before, boot_id='new', hidden=True, own_overlay_enabled=True)
        with self.assertRaisesRegex(RuntimeError, '重启'):
            self.run_change('hide', self.before, after)

    def test_navigation_change_is_not_success(self):
        after = dict(self.before, navigation_mode='0', hidden=True, own_overlay_enabled=True)
        with self.assertRaisesRegex(RuntimeError, '导航模式'):
            self.run_change('hide', self.before, after)

    def test_restore_verifies_overlay_removed(self):
        before = dict(self.before, hidden=True, own_overlay_enabled=True)
        result, operation = self.run_change('show', before, self.before)
        operation.assert_called_once_with(self.d, 'show')
        self.assertIn('已恢复', result['message'])

    def test_other_transparent_overlay_is_reported(self):
        after = dict(self.before, hidden=True)
        result, _ = self.run_change('show', self.before, after)
        self.assertIn('其他配置', result['message'])

    def test_both_color_modes_required(self):
        overlay = '[x] android:CodexGesturePill'
        self.assertTrue(bridge.gesture_state(overlay, '#0', '#00000000')['hidden'])
        self.assertFalse(bridge.gesture_state(overlay, '#0', '#ffffffff')['hidden'])
        self.assertFalse(bridge.gesture_state('', '#0', '#0')['own_overlay_enabled'])

class ResultTests(unittest.TestCase):
    def test_partial_root_is_distinguished(self):
        text, color = gui.root_summary({'root_currently_verified': True, 'all_health_samples_passed': False})
        self.assertIn('异常', text)
        self.assertEqual(color, gui.AMBER)

    def test_no_result_is_not_success(self):
        self.assertEqual(gui.root_summary({})[1], gui.RED)

    def test_already_rooted_is_skip(self):
        self.assertIn('跳过', gui.root_summary({'outcome': 'already_rooted'})[0])

    def test_full_health_result_is_separate(self):
        self.assertEqual(gui.root_summary({'root_currently_verified': True, 'all_health_samples_passed': True})[1], gui.GREEN)

if __name__ == '__main__':
    unittest.main(verbosity=2)
