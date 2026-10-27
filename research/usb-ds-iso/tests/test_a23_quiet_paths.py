"""Fresh quiet ELF paths retain all explicit model and hardware limits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_quiet_paths as audit
from model_a23_quiet_paths import QuietLoggerMachine,JoinWaitMachine,main_handoff_certificate


class QuietPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.folder=Path(cls.tmp.name).resolve()/'review';cls.result=audit.run(cls.folder)
        cls.blob=(audit.DEVICE/'full.elf').read_bytes();cls.text=(audit.DEVICE/'disassembly.txt').read_text()
        cls.functions,cls.meta=audit.elf.build_functions(cls.blob,cls.text)
        cls.meta['dispatch']=audit.linked.fmt.decode_dispatch(cls.blob,cls.text);cls.meta['locale']=audit.linked.fmt.default_locale(cls.blob,cls.text)
        cls.catalog=cls.load('catalog.json');cls.logs=cls.load('linked-calls.json');cls.graph=cls.load('composition.json')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    @classmethod
    def load(cls,name):return json.loads((cls.folder/name).read_text())

    def machine(self,*,quiet=False,**kwargs):
        site=next(s for s in self.logs['sites'] if 'ISO timing seq=' in s['formats'][0])
        item=next(r for r in self.catalog if r['format']==site['formats'][0])
        return QuietLoggerMachine(self.functions,self.blob,self.meta,site['format_addresses'][0],
            audit.formats.values_for(item,'limits'),quiet=quiet,**kwargs)

    def test_new_receiver_and_six_material_identity_match(self):
        record=audit.storage.load(audit.PARENT/'offline-record.json')
        self.assertEqual(self.result['elf_sha256'],record['device_binding']['device_elf_sha256'])
        self.assertEqual(self.result['runtime_recipe_sha256'],record['recipe_sha256'])
        self.assertEqual(len(self.result['device_binding']['artifact_hashes']),6)
        self.assertEqual(self.result['main_npdm_request_bytes'],8192)
        self.assertFalse(self.result['old_address_certificates_reused'])

    def test_catalog_and_resumed_formats_are_rebound(self):
        self.assertEqual(self.result['preprocessed_units'],13)
        self.assertEqual(self.result['resumed_profile_count'],self.result['linked_formats']*3)
        self.assertGreater(self.result['linked_log_sites'],60)
        for row in self.load('resumed-logger.json'):
            self.assertTrue(row['stack_restored'] and row['callee_saved_restored'])
            self.assertFalse(row['quiet']);self.assertIn('vsnprintf',row['executed_function_names'])
            self.assertEqual(row['observed_user_stack_bytes'],2592)

    def test_quiet_profiles_make_no_calls_and_still_allocate_a_frame(self):
        self.assertEqual(self.result['quiet_profile_count'],self.result['resumed_profile_count'])
        for row in self.load('quiet-logger.json'):
            self.assertEqual(row['executed_function_names'],['LogFunctionImpl'])
            self.assertEqual(row['fs_calls'],[]);self.assertEqual(row['helper_calls'],[])
            self.assertEqual(row['observed_user_stack_bytes'],832)
            self.assertEqual(row['instruction_count'],32)
            self.assertTrue(row['atomic_reads'][0]['value'])
            self.assertFalse(row['memory_order_and_scheduler_executed'])

    def test_quiet_guard_skips_invalid_format_and_tls(self):
        rows=[r for r in self.load('controls.json') if r['case']=='quiet-invalid-format-and-tls']
        self.assertEqual({r['mounted'] for r in rows},{False,True})
        for row in rows:self.assertEqual(row['executed_function_names'],['LogFunctionImpl'])
        self.assertTrue(next(r for r in self.load('controls.json') if r['case']=='resumed-invalid-tls')['rejected'])

    def test_register_exhaustion_and_original_length_guard_still_work(self):
        m=self.machine();row=m.run()
        self.assertEqual(len(m.argument_words),8);self.assertEqual(len(m.stack_argument_snapshot),1)
        self.assertTrue(row['stack_arguments_preserved'])
        self.assertLessEqual(row['fs_calls'][2]['length'],511)
        rows={r['case']:r for r in self.load('controls.json') if r['case'] in ('open','size','write')}
        self.assertEqual([r['name'] for r in rows['size']['fs_calls']],['fsFsOpenFile','fsFileGetSize','fsFileClose'])

    def test_quiet_frame_and_acquire_address_changes_reject(self):
        m=self.machine(quiet=True);pc=m.functions['LogFunctionImpl']['start'];m.code[pc]=('sub','sp, sp, #0x350')
        with self.assertRaises((AssertionError,ValueError)):m.run()
        m=self.machine(quiet=True);pc=next(p for p,(op,_) in m.code.items() if op=='ldarb')
        m.code[pc]=('ldarb','w1, [x9]')
        with self.assertRaisesRegex(ValueError,'acquire'):m.run()

    def test_new_main_handoff_checks_both_successful_joins(self):
        gate=self.load('main-handoff.json')
        for name in ('quiet_enable_dominates_worker_launches','both_joins_dominate_quiet_clear',
                     'failed_join_cannot_reach_quiet_clear','quiet_clear_dominates_joined_saves'):self.assertTrue(gate[name])
        self.assertEqual(len(gate['joined_save_sites']),4)

    def test_main_argument_and_join_branch_drift_reject(self):
        gate=self.load('main-handoff.json');a=gate['main_address']
        for kind in ('enable','branch','bad-edge','overwritten-join-result'):
            fs=copy.deepcopy(self.functions);code=fs[a]['instructions'];mapping={p:i for i,(p,_,_) in enumerate(code)}
            pc=gate['quiet_enable_at']-4 if kind=='enable' else gate['join_success_branch']
            if kind=='enable':new=('mov','w0, #0x0')
            elif kind=='branch':new=('cbnz',code[mapping[pc]][2])
            elif kind=='bad-edge':
                pc+=4;new=('b',f'{gate["quiet_disable_at"]-8:x} <main+0x0>')
            else:
                pc=gate['join_success_branch']-8;new=('mov','w20, #0x0')
            code[mapping[pc]]=(pc,*new)
            with self.assertRaises(ValueError):main_handoff_certificate(fs)

    def test_event_wait_profiles_bind_current_one_and_three_object_sites(self):
        waits=self.load('wait-profiles.json');self.assertEqual(waits['profile_count'],40)
        self.assertEqual({r['count'] for r in waits['sites']},{1,3})
        for row in waits['profiles']:
            self.assertTrue(row['stack_restored']);self.assertFalse(row['indirect_callbacks_reached'])
            self.assertLessEqual(row['peak_user_stack_bytes'],{1:304,3:400}[row['count']])

    def test_join_infinite_timeout_paths_have_no_termination_claim(self):
        joins=self.load('join-profiles.json');self.assertEqual(len(joins['profiles']),5)
        for row in joins['profiles']:
            self.assertEqual(row['peak_user_stack_bytes'],96)
            self.assertEqual(row['svc_calls'][0]['handles'],[101])
            self.assertTrue(row['callee_saved_restored'])
        self.assertFalse(joins['termination_time_bound_verified'])
        with self.assertRaisesRegex(ValueError,'exhausted'):JoinWaitMachine(self.text,results=(0xec01,)).run()

    def test_filename_profiles_use_two_new_elf_call_sites(self):
        paths=self.load('path-snprintf.json')
        self.assertEqual(len(paths['sites']),2);self.assertEqual(len(paths['profiles']),6)
        self.assertEqual({s['caller'] for s in paths['sites']},{'Ep0CandidateSaveCapture','Ep0CandidateSaveDiagnostic'})
        for row in paths['profiles']:
            self.assertEqual(row['observed_user_stack_bytes'],1904);self.assertTrue(row['stack_restored'])
            self.assertFalse(row['actual_arm_executed'])

    def test_quiet_workers_have_no_capture_recursion(self):
        for name in ('VideoStreamThread','AudioStreamThread','UvcDeviceProcessRequests'):
            row=self.graph['roots'][name];self.assertTrue(row['quiet_assumed'])
            self.assertEqual(row['unresolved'],[])
            self.assertIsNone(row['whole_thread_stack_bound_bytes'])
        self.assertNotIn('resumed-logger-profiles',self.graph['roots']['VideoStreamThread']['substitutions'])
        self.assertIn('resumed-logger-profiles',self.graph['roots']['main']['substitutions'])

    def test_static_prefixes_remain_separate_from_profile_composition(self):
        static=self.load('static-prefixes.json')
        self.assertEqual(static['roots']['threadWaitForExit']['user_prefix_bound_bytes'],128)
        self.assertEqual(static['roots']['AudioStreamThread']['user_prefix_bound_bytes'],32)
        for row in self.graph['roots'].values():self.assertIsNone(row['whole_thread_stack_bound_bytes'])
        self.assertTrue(self.graph['estimates_are_not_whole_thread_bounds'])

    def test_sources_and_sealed_inputs_preserved(self):
        for n,h in self.result['source_hashes'].items():self.assertEqual(audit.candidate.sha(audit.REPO/n),h)
        for item in self.result['sealed_inputs']:self.assertTrue(audit.verify(item['folder'])['sha256_verified'])
        self.assertTrue(audit.verify(self.folder)['sha256_verified'])

    def test_no_new_hardware_or_time_authority(self):
        for name in ('actual_kernel_thread_budget_verified','whole_thread_stack_verified','synchronous_call_time_bound_verified',
                     'actual_arm_executed','device_modified','new_device_elf_built','attempt_issued','hardware_verified','root_cause_confirmed'):
            self.assertIs(self.result[name],False)
        for name in ('native_sdk_calls','usb_requests','sd_accesses'):self.assertEqual(self.result[name],0)


if __name__=='__main__':unittest.main()
