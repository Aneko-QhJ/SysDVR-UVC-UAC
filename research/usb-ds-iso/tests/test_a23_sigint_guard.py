from pathlib import Path
import copy
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_sigint_guard as audit
s=audit.candidate


class SigintGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_SIGINT_GUARD_REVIEW')
        cls.root=Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-sigint-tests-',dir='/private/tmp'))/'review'
        if not saved:audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def row(self,name):return audit.f.load(self.root/'work/cases'/name/'observation.json')
    def test_nine_cases_six_candidate_waits_three_audit_waits(self):self.assertEqual((self.r['model_cases'],self.r['actual_child_processes'],self.r['candidate_direct_waits'],self.r['audit_native_return_waits']),(9,9,6,3))
    def test_normal_capture_preserves_bytes(self):
        args=audit.previous.previous.previous.args_at(self.root/'inputs/normal');files=audit.previous.previous.previous.previous.previous.cache(self.root/'work/cases/normal/captured');self.assertEqual(files,args[2])
    def test_unmasked_native_return_sigint_leaves_real_child_unregistered(self):
        v=self.row('unguarded-sigint-native-return');self.assertTrue(v['lifecycle']['creation_unresolved']);self.assertFalse(v['candidate_direct_wait']);self.assertTrue(v['native_return_token_waited']);self.assertEqual(v['native_return_waitcode'],2)
    def test_masked_native_return_sigint_waits_via_retained_object(self):
        v=self.row('guarded-sigint-native-return');self.assertTrue(v['candidate_direct_wait']);self.assertFalse(v['native_return_token_waited']);self.assertEqual(v['exception_type'],'KeyboardInterrupt')
    def test_process_directed_self_sigint_is_also_deferred_in_fixture(self):
        v=self.row('guarded-process-sigint-native-return');self.assertTrue(v['candidate_direct_wait']);self.assertEqual(v['pending_after_injection'],[True])
    def test_actual_pid_store_opcode_sigint_is_deferred(self):
        v=self.row('guarded-sigint-pid-store');self.assertEqual(v['injected'],['pid-store-sigint']);self.assertEqual(v['pending_after_injection'],[True]);self.assertTrue(v['candidate_pid_registered'])
    def test_synchronous_python_exception_is_not_masked(self):
        v=self.row('guarded-synchronous-pid-store');self.assertTrue(v['lifecycle']['creation_unresolved']);self.assertTrue(v['native_return_token_waited']);self.assertTrue(v['primary_exception_identity_preserved'])
    def test_sigint_before_initialization_does_not_interrupt_creation(self):
        v=self.row('guarded-sigint-before-init');self.assertEqual(v['injected'],['before-init-sigint']);self.assertEqual(v['pending_after_injection'],[True]);self.assertTrue(v['candidate_direct_wait'])
    def test_preblocked_signal_remains_pending_and_mask_stays_blocked(self):
        v=self.row('preblocked-sigint');self.assertTrue(v['accepted']);self.assertTrue(v['pending_sigint_after_capture']);self.assertIn(int(signal.SIGINT),v['original_mask']);self.assertTrue(v['lifecycle']['original_sigint_blocked'])
    def test_primary_exception_not_replaced_by_restore_sigint(self):
        v=self.row('primary-plus-pending-sigint');self.assertTrue(v['primary_exception_identity_preserved']);self.assertIn('KeyboardInterrupt',v['lifecycle']['mask_restore_exceptions']);self.assertTrue(v['native_return_token_waited'])
    def test_all_masks_restored(self):
        for n in audit.CASES:self.assertTrue(self.row(n)['mask_restored_to_original'])
    def test_guarded_async_sigint_cases_record_pending_kernel_signal(self):
        for n in ('guarded-sigint-native-return','guarded-process-sigint-native-return','guarded-sigint-pid-store','guarded-sigint-before-init','preblocked-sigint','primary-plus-pending-sigint'):self.assertEqual(self.row(n)['pending_after_injection'],[True])
    def test_all_failed_cases_have_no_cache(self):
        for n in set(audit.CASES)-audit.ACCEPTED:
            for part in ('captured','report.json','classification.json'):self.assertFalse((self.root/'work/cases'/n/part).exists())
    def test_actual_wait_codes_are_integers(self):
        for n in audit.CASES:self.assertIs(type(self.row(n)['actual_exitcode']),int)
    def test_native_rescue_is_not_promoted_to_candidate_wait(self):
        for n in audit.UNRESOLVED:
            v=self.row(n);self.assertFalse(v['lifecycle']['direct_wait_verified']);self.assertTrue(v['lifecycle']['creation_unresolved']);self.assertTrue(v['lifecycle']['pending_handle_retained'])
    def test_requires_single_python_main_thread_before_mask_change(self):
        owner=s.SamplerOwner()
        with patch.object(threading,'active_count',return_value=2),patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')):
            with self.assertRaises(ValueError):owner._create(['not-started'])
    def test_requires_default_handler_without_replacing_it(self):
        with patch.object(signal,'getsignal',return_value=signal.SIG_IGN),patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')),patch.object(signal,'signal',side_effect=AssertionError('handler')):
            with self.assertRaises(ValueError):s.SamplerOwner()._create(['not-started'])
    def test_unverified_restore_retains_saved_mask_for_explicit_retry(self):
        owner=s.SamplerOwner();owner._saved_mask=set();owner._mask_thread=threading.get_ident()
        with patch.object(signal,'pthread_sigmask',side_effect=[OSError('restore'),{signal.SIGINT}]):error=owner._restore_mask()
        self.assertIsInstance(error,OSError);self.assertIsNotNone(owner._saved_mask);self.assertFalse(owner.observation()['mask_restore_verified'])
        with patch.object(signal,'pthread_sigmask',side_effect=[{signal.SIGINT},set()]):self.assertIsNone(owner._restore_mask())
        self.assertIsNone(owner._saved_mask);self.assertTrue(owner.observation()['mask_restore_verified'])
    def test_restore_query_failure_does_not_claim_success(self):
        owner=s.SamplerOwner();owner._saved_mask=set();owner._mask_thread=threading.get_ident()
        with patch.object(signal,'pthread_sigmask',side_effect=[set(),OSError('query')]):self.assertIsInstance(owner._restore_mask(),OSError)
        self.assertFalse(owner.observation()['mask_restore_verified']);self.assertIsNotNone(owner._saved_mask);owner._saved_mask=None
    def test_wrong_thread_restore_refused_before_os_call(self):
        owner=s.SamplerOwner();owner._saved_mask=set();owner._mask_thread=threading.get_ident()+1
        with patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')):
            with self.assertRaises(ValueError):owner.finish()
        owner._saved_mask=None
    def test_runtime_native_image_source_and_bytecode_pinned(self):
        info=audit.f.load(self.root/'runtime.json');self.assertEqual(audit.f.sha(audit.a.read(self.root/'runtime/posixsubprocess.bin')),info['native_binary_sha256']);self.assertEqual(audit.f.sha(audit.a.read(self.root/'runtime/subprocess.py')),info['subprocess_source_sha256']);self.assertIs(type(info['pid_store_opcode']),int)
    def test_pure_validation_uses_no_io_or_signal_calls(self):
        rows=[self.row(n) for n in audit.CASES]
        with patch('builtins.open',side_effect=AssertionError('open')),patch.object(os,'waitpid',side_effect=AssertionError('wait')),patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')):
            for row in rows:audit.validate(row)
    def test_promoted_signal_failure_rejected(self):
        for key in ('accepted','candidate_direct_wait','native_return_token_waited','mask_restored_to_original'):
            v=copy.deepcopy(self.row('unguarded-sigint-native-return'));v[key]=not v[key]
            with self.assertRaises(ValueError):audit.validate(v)
    def test_all_task_and_hardware_authority_still_false(self):
        for n in audit.CASES:
            v=self.row(n);self.assertFalse(v['task_complete'])
            for key in audit.FALSE:self.assertIs(v[key],False);self.assertIs(v['lifecycle'][key],False)
    def test_readonly_verify_no_launch_trace_mask_or_wait(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('spawn')),patch.object(sys,'settrace',side_effect=AssertionError('trace')),patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')),patch.object(os,'waitpid',side_effect=AssertionError('wait')):audit.verify(self.root,self.pin)
    def test_external_pin_and_575_source_count(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(575,572))


if __name__=='__main__':unittest.main()
