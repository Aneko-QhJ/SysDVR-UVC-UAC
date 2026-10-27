"""Current ELF profiles remain observations, even with closed composed edges."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_v3_stack_profiles as audit
from model_a23_v3_logger_stack import LoggerMachine,LoggerModelError,PathSnprintfMachine


class V3StackProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name).resolve();cls.review=cls.base/'review';cls.result=audit.run(cls.review)
        cls.blob=(audit.DEVICE/'full.elf').read_bytes();cls.text=(audit.DEVICE/'disassembly.txt').read_text()
        cls.fs,cls.meta=audit.elf.build_functions(cls.blob,cls.text)
        cls.meta['dispatch']=audit.linked.fmt.decode_dispatch(cls.blob,cls.text);cls.meta['locale']=audit.linked.fmt.default_locale(cls.blob,cls.text)
        cls.logs=json.loads((cls.review/'linked-calls.json').read_text());cls.catalog=json.loads((cls.review/'catalog.json').read_text())
        cls.profiles=json.loads((cls.review/'logger-profiles.json').read_text());cls.waits=json.loads((cls.review/'wait-profiles.json').read_text())
        cls.controls=json.loads((cls.review/'controls.json').read_text());cls.graph=json.loads((cls.review/'profile-composition.json').read_text())

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def machine(self,fmt_contains=None,**kwargs):
        sites=[s for s in self.logs['sites'] if any(fmt_contains is None or fmt_contains in f for f in s['formats'])]
        site=sites[0];idx=next(i for i,f in enumerate(site['formats']) if fmt_contains is None or fmt_contains in f)
        item=next(r for r in self.catalog if r['format']==site['formats'][idx]);values=audit.formats.values_for(item,'limits')
        return LoggerMachine(self.fs,self.blob,self.meta,site['format_addresses'][idx],values,**kwargs)

    def test_every_linked_direct_log_literal_is_rebound_on_current_elf(self):
        self.assertEqual((self.result['preprocessed_units'],self.result['linked_log_sites'],self.result['linked_formats']),(13,79,73))
        self.assertEqual(self.result['linked_conversions'],97)
        self.assertEqual(self.result['logger_profile_count'],219)
        self.assertFalse(self.result['old_address_certificates_reused'])
        self.assertEqual(self.result['elf_sha256'],audit.storage.load(audit.PARENT/'offline-record.json')['device_binding']['device_elf_sha256'])

    def test_continuous_logger_includes_outer_wrapper_and_restores_abi(self):
        for row in self.profiles:
            self.assertEqual(row['observed_user_stack_bytes'],2592)
            self.assertTrue(row['stack_restored'] and row['callee_saved_restored'] and row['stack_arguments_preserved'])
            self.assertIn('vsnprintf',row['executed_function_names']);self.assertIn('_vsnprintf_r',row['executed_function_names'])
            self.assertIn('LogFunctionImpl',row['executed_function_names']);self.assertIn('__syscall_getreent',row['executed_function_names'])
            self.assertFalse(row['formatter_state_reinjected']);self.assertFalse(row['actual_arm_executed'])

    def test_register_exhaustion_runs_through_real_logger_va_setup(self):
        m=self.machine('ISO timing seq=');row=m.run();self.assertEqual(len(m.argument_words),8)
        self.assertEqual(len(m.stack_argument_snapshot),1);self.assertTrue(row['stack_arguments_preserved'])
        item=next(r for r in self.catalog if 'ISO timing seq=' in r['format']);values=audit.formats.values_for(item,'limits')
        n,expected=audit.formats.NativeOracle().format(item,values)
        self.assertEqual((row['required'],bytes.fromhex(row['rendered_hex'])),(n,expected))

    def test_fs_failures_still_follow_actual_logger_error_edges(self):
        expected={'open':['fsFsOpenFile'],'size':['fsFsOpenFile','fsFileGetSize','fsFileClose'],
            'write':['fsFsOpenFile','fsFileGetSize','fsFileWrite','fsFileClose'],'unmounted':[]}
        for row in self.controls:
            if row['case'] in expected:self.assertEqual([c['name'] for c in row['fs_calls']],expected[row['case']])
        unmounted=next(r for r in self.controls if r['case']=='unmounted');self.assertEqual(unmounted['observed_user_stack_bytes'],832)
        for case in ('invalid-tls','instruction-budget'):self.assertTrue(next(r for r in self.controls if r['case']==case)['rejected'])

    def test_frame_and_capacity_instruction_changes_do_not_keep_the_same_profile(self):
        m=self.machine('Video stream thread started');pc=m.functions['LogFunctionImpl']['start']
        self.assertEqual(m.code[pc],('sub','sp, sp, #0x340'));m.code[pc]=('sub','sp, sp, #0x350')
        with self.assertRaises((AssertionError,ValueError)):m.run()

    def test_invalid_tls_and_position_mode_remain_frontiers(self):
        with self.assertRaisesRegex(ValueError,'diagAbortWithResult'):self.machine('ISO timing seq=',tls_magic=0).run()
        m=self.machine('ISO timing seq=');p=m.start+0x1fc;self.assertEqual(m.code[p],('mov','w3, #0x0'));m.code[p]=('mov','w3, #0x1')
        with self.assertRaisesRegex(ValueError,'get_arg'):m.run()

    def test_string_memory_preconditions_are_not_proved_by_success(self):
        m=self.machine('Serial: %s',string_offset=4095);row=m.run();self.assertTrue(row['tls_register_reent_locale_and_valid_arguments_injected'])
        self.assertTrue(any(h['name']=='strlen' for h in row['helper_calls']))
        m=self.machine('Serial: %s',string_offset=1,mapped_string_pages=False)
        del m.mem[m.string_objects[0]['pointer']+1]
        with self.assertRaisesRegex(ValueError,'Uninitialized'):m.run()

    def test_sdk_fs_prefix_bounds_are_separate_from_injected_results(self):
        fs=json.loads((self.review/'fs-stack.json').read_text())
        expected={'fsFsOpenFile':224,'fsFileGetSize':192,'fsFileWrite':224,'fsFileClose':176}
        for name,n in expected.items():self.assertEqual(fs['roots'][name]['user_prefix_bound_bytes'],n)
        self.assertEqual(self.result['logger_fs_user_profile_envelope_bytes'],2592)
        for row in self.profiles:
            self.assertTrue(row['fs_results_injected']);self.assertFalse(row['fs_sdk_instructions_executed'])

    def test_handle_wait_profiles_are_bound_to_two_current_call_sites(self):
        self.assertEqual(self.waits['profile_count'],40);self.assertEqual(len(self.waits['sites']),2)
        self.assertEqual({s['caller'] for s in self.waits['sites']},{'eventWait','UvcDeviceProcessRequests'})
        for row in self.waits['profiles']:
            self.assertTrue(row['stack_restored']);self.assertFalse(row['indirect_callbacks_reached'])
            self.assertLessEqual(row['peak_user_stack_bytes'],{1:304,3:400}[row['count']])

    def test_profile_composition_never_becomes_whole_thread_bound(self):
        for name,row in self.graph['roots'].items():self.assertIsNone(row['whole_thread_stack_bound_bytes'])
        for name in ('VideoStreamThread','AudioStreamThread'):
            row=self.graph['roots'][name]
            self.assertEqual(row['with_worker_wrapper_profile_estimate_bytes'],row['profile_path_estimate_bytes']+48)
            self.assertIn('logger-observed-profile',row['substitutions'])
        self.assertTrue(self.graph['profile_estimates_are_not_bounds'])
        self.assertFalse(self.graph['whole_thread_stack_verified'])

    def test_sources_tickets_and_seals_unchanged(self):
        for n,h in self.result['source_hashes'].items():self.assertEqual(audit.storage.sha(audit.storage.plain(audit.REPO/n)),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.storage.sha(audit.storage.plain(audit.PARENT.parent/n)),h)
        for s in self.result['sealed_inputs']:audit.verify(s['folder'])
        audit.verify(self.review)

    def test_no_time_or_hardware_authority(self):
        for key in ('synchronous_log_latency_bound_verified','whole_thread_stack_verified','actual_arm_executed','device_modified',
            'new_device_elf_built','attempt_issued','hardware_verified','root_cause_confirmed'):self.assertIs(self.result[key],False)
        for key in ('native_sdk_calls','usb_requests','sd_accesses'):self.assertEqual(self.result[key],0)
        self.assertTrue(self.result['nonlogger_snprintf_observed_profiles_only'])

    def test_two_actual_filename_sites_use_continuous_snprintf_profiles(self):
        value=json.loads((self.review/'path-snprintf.json').read_text())
        self.assertEqual(len(value['sites']),2);self.assertEqual(len(value['profiles']),6)
        self.assertEqual({s['caller'] for s in value['sites']},{'Ep0CandidateSaveCapture','Ep0CandidateSaveDiagnostic'})
        for row in value['profiles']:
            self.assertEqual(row['observed_user_stack_bytes'],1904);self.assertTrue(row['stack_restored'])
            self.assertLess(row['required'],96);self.assertFalse(row['formatter_state_reinjected'])
        self.assertFalse(self.graph['roots']['main']['unresolved'])

    def test_unreviewed_nonce_and_waiter_object_types_are_not_accepted(self):
        value=json.loads((self.review/'path-snprintf.json').read_text());literal=value['sites'][0]['format']
        addresses=[a for f in self.fs.values() for pc,op,arg in f['instructions'] if op=='bl' and arg.endswith('<snprintf>')
            for a in audit.linked.LiteralResolver(f).values(pc,'x2') if audit.linked.literal_at(self.blob,self.meta,a)==literal]
        for bad in (b'0'*63,b'G'*64,b'\x00'*64):
            with self.assertRaises(ValueError):PathSnprintfMachine(self.fs,self.blob,self.meta,addresses[0],bad)
        with self.assertRaises(ValueError):audit.HandleWaitMachine(self.text,count=1,types=(2,),timeout=0).run()


if __name__=='__main__':unittest.main()
