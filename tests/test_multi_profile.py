"""Ensure an enabled button routes to the exact matching profile, never the old one."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import common
import device
import registry
import presentation
from test_detection_history import FakeDevice, BASE, BOOT, state

NEW_KERNEL = '5.15.189-android13-8-00016-g51bba4309aac-ab14546557'
NEW_ID = 'xperia1v-14546557-cpu0-1'
NEW_ENV = dict(BASE, hardware_device='XQ-DQ72', model='XQ-DQ72', kernel=NEW_KERNEL,
               build='67.2.A.3.178 release-keys', fingerprint='Sony/XQ-DQ72/fixture')


class MultiProfileTests(unittest.TestCase):
    def test_current_phone_matches_new_profile_without_ack(self):
        value = registry.assess(NEW_ENV, ROOT)
        self.assertTrue(value['eligible'])
        self.assertEqual(value['profile_id'], NEW_ID)
        self.assertEqual(value['profile_file'], 'profiles/xperia1v-14546557-cpu0-1.glk')
        self.assertFalse(value['requires_acknowledgement'])
        self.assertGreaterEqual(value['matching_record_count'], 0)
        self.assertFalse(value['pill_supported'])
        self.assertTrue(presentation.execution_available(state(NEW_ENV)))
        self.assertTrue(presentation.execution_available(state(NEW_ENV), True))

    def test_mismatching_kernel_tail_is_not_allowed(self):
        value = registry.assess(dict(NEW_ENV, kernel=NEW_KERNEL+'-different'), ROOT)
        self.assertTrue(value['attempt_allowed'])

    def test_wrong_model_cannot_reuse_new_profile(self):
        value = registry.assess(dict(NEW_ENV, hardware_device='OTHER'), ROOT)
        self.assertTrue(value['attempt_allowed'])

    def test_old_profile_and_known_record_still_work(self):
        value = registry.assess(BASE, ROOT)
        self.assertEqual(value['profile_id'], 'so51d-12915929-cpu3-4')
        self.assertFalse(value['requires_acknowledgement'])
        self.assertTrue(value['pill_supported'])

    def test_profile_bytes_contain_new_release_and_pinned_hash(self):
        profile = registry.profile_by_id(ROOT, NEW_ID)
        blob = (ROOT/profile['file']).read_bytes()
        magic, version, route, major, recommend, zero, length = struct.unpack('<IHBBBBH', blob[:12])
        self.assertEqual((magic,version,major),(0x0D000721,2,5))
        self.assertEqual(blob[12:12+length].decode(),NEW_KERNEL)
        self.assertEqual(hashlib.sha256(blob).hexdigest(),profile['sha256'])
        fields=json.loads((ROOT/'profiles/xperia1v-14546557-native-fields.json').read_text(encoding='utf-8'))
        self.assertEqual(fields['execution.recommended_main_cpu'],0)
        self.assertEqual(fields['execution.recommended_consumer_cpu'],1)
        self.assertEqual(fields['off_init_task'],46412800)
        old=json.loads((ROOT/'profiles/catalog.json').read_text(encoding='utf-8'))['profiles'][0]
        self.assertNotEqual(blob,(ROOT/old['file']).read_bytes())

    def test_confirmation_cannot_be_reused_for_other_profile(self):
        confirmation = registry.make_confirmation(state(BASE),False)
        with self.assertRaises(RuntimeError):
            registry.require_execution(NEW_ENV,ROOT,confirmation,BOOT)

    def test_common_checks_both_profiles(self):
        with patch.object(common,'verify') as verify:
            common.verify_payloads()
        checked = [str(call.args[0]) for call in verify.call_args_list]
        self.assertTrue(any('so51d-12915929-cpu3-4.glk' in name for name in checked))
        self.assertTrue(any('xperia1v-14546557-cpu0-1.glk' in name for name in checked))

    def run_route(self,env):
        profile=registry.profile_by_id(ROOT,registry.assess(env,ROOT)['profile_id'])
        class RoutedDevice(FakeDevice):
            def call(self,*args,**kwargs):
                if args[0]=='push':
                    self.commands.append(args)
                    return 'mock-pushed'
                if args[0]=='shell':
                    command=args[1]
                    if command.startswith('sha256sum '):
                        self.commands.append(args)
                        name=command.rsplit('/',1)[-1]
                        digest={'ghostlock':common.MANIFEST['packages'][0]['extract']['sha256'],
                                'ksud':device.MANAGER_PACKAGE['extract']['sha256'],
                                'selected-profile.glk':profile['sha256']}[name]
                        return digest+'  '+command.split(' ',1)[1]
                    if command.startswith('if [ -d ') or command.startswith('mkdir ') or command.startswith('chmod '):
                        self.commands.append(args)
                        return ''
                return super().call(*args,**kwargs)
        fake=RoutedDevice(env,overrides={'ps -A -o ARGS':'sh'})
        fake.confirmation=registry.make_confirmation(state(env),True)
        with patch.object(device,'verify_payloads'), patch.object(device,'prepare_manager',return_value={'state':'ready'}), \
             patch.object(device,'monitor_activation') as monitor:
            device.activate(fake)
        profile_pushes=[call for call in fake.commands if call[0]=='push' and call[1].endswith('.glk')]
        self.assertEqual(len(profile_pushes),1)
        self.assertEqual(Path(profile_pushes[0][1]),ROOT/profile['file'])
        launch=[call for call in fake.commands if 'nohup' in str(call)]
        self.assertEqual(len(launch),1)
        self.assertIn('--load-prebuilt-profile '+device.REMOTE+'/selected-profile.glk',launch[0][1])
        self.assertNotIn('so51d-12915929.glk',launch[0][1])
        monitor.assert_called_once()

    def test_new_device_pushes_only_14546557_profile(self):
        self.run_route(NEW_ENV)

    def test_old_device_still_pushes_12915929_profile(self):
        self.run_route(BASE)

    def test_unknown_device_is_launched_with_default_profile(self):
        self.run_route(dict(BASE,hardware_device='OTHER',kernel='unknown'))

    def test_same_kernel_other_model_uses_kernel_matched_profile(self):
        self.run_route(dict(NEW_ENV,hardware_device='OTHER'))

    def test_history_records_actual_selected_profile(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            out=root/'logs'/'one-new-attempt'
            out.mkdir(parents=True)
            (out/'before-state.json').write_text(json.dumps({'boot_id':BOOT}),encoding='utf-8')
            (out/'final-state.json').write_text(json.dumps({'boot_id':BOOT,'root':'uid=0(root)','kernelsu_loaded':True}),encoding='utf-8')
            result={'activation_calls':1,'environment':NEW_ENV,'assessment':registry.assess(NEW_ENV,ROOT)}
            path=registry.record_attempt(root,out,result,common.MANIFEST)
            row=json.loads(Path(path).read_text(encoding='utf-8'))
            self.assertEqual(row['profile_id'],NEW_ID)
            self.assertEqual(row['profile_sha256'],registry.profile_by_id(ROOT,NEW_ID)['sha256'])


if __name__=='__main__':
    unittest.main(verbosity=2)
