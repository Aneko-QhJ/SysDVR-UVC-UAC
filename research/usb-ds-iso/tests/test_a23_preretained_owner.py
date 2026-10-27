from pathlib import Path
import copy
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_preretained_owner as audit
s=audit.candidate


class PreretainedOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_PRERETAINED_REVIEW')
        cls.root=Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-preretained-tests-',dir='/private/tmp'))/'review'
        if not saved:audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def row(self,name):return audit.f.load(self.root/'work/cases'/name/'observation.json')
    def test_twelve_cases_eight_children_all_directly_waited(self):self.assertEqual((self.r['model_cases'],self.r['actual_child_processes'],self.r['direct_child_waits']),(12,8,8))
    def test_normal_cached_bytes_and_classifier_preserved(self):
        args=audit.previous.previous.args_at(self.root/'inputs/normal');files=audit.previous.previous.previous.previous.cache(self.root/'work/cases/normal/captured');self.assertEqual(files,args[2]);self.assertFalse(audit.f.load(self.root/'work/cases/normal/classification.json')['task_complete'])
    def test_before_allocation_no_object_no_process(self):
        v=self.row('before-allocation');self.assertFalse(v['object_present']);self.assertEqual(v['actual_child_count'],0);self.assertTrue(v['lifecycle']['no_process_started_verified'])
    def test_allocated_before_init_is_not_a_started_child(self):
        v=self.row('allocated');self.assertTrue(v['object_present']);self.assertFalse(v['lifecycle']['direct_wait_verified']);self.assertTrue(v['lifecycle']['no_process_started_verified']);self.assertEqual(v['lifecycle']['owner_status'],'closed')
    def test_entered_initialization_without_pid_stays_unknown(self):
        v=self.row('before-initialize');self.assertTrue(v['lifecycle']['creation_unresolved']);self.assertTrue(v['lifecycle']['pending_handle_retained']);self.assertFalse(v['lifecycle']['no_process_started_verified'])
    def test_partial_constructor_model_is_not_treated_as_no_child(self):
        v=self.row('unregistered-model');self.assertEqual(v['actual_child_count'],0);self.assertEqual(v['lifecycle']['owner_status'],'creation_unresolved');self.assertFalse(v['lifecycle']['direct_wait_verified'])
    def test_after_initialize_same_object_is_already_retained(self):
        v=self.row('after-initialize');self.assertTrue(v['same_runtime_object_retained']);self.assertTrue(v['lifecycle']['direct_wait_verified'])
    def test_outer_child_store_interrupt_no_longer_loses_object(self):
        v=self.row('before-child-store');self.assertTrue(v['same_runtime_object_retained']);self.assertEqual(v['injected'],['opcode']);self.assertEqual(v['outer_rescue_waits'],0)
    def test_stream_store_interrupt_closes_all_retained_pipes(self):
        v=self.row('before-stream-store');self.assertEqual(v['actual_open_streams'],0);self.assertTrue(v['lifecycle']['direct_wait_verified'])
    def test_init_returns_then_interrupt_keeps_constructor_object(self):
        v=self.row('init-return-interrupt');self.assertTrue(v['original_exception_preserved']);self.assertTrue(v['same_runtime_object_retained']);self.assertTrue(v['lifecycle']['direct_wait_verified'])
    def test_init_returns_then_eio_is_failed_but_reaped(self):
        v=self.row('init-return-eio');self.assertFalse(v['accepted']);self.assertEqual(v['lifecycle']['reason'],'OSError');self.assertTrue(v['lifecycle']['direct_wait_verified'])
    def test_execute_child_return_interrupt_preserves_pid_object(self):
        v=self.row('after-execute-child');self.assertTrue(v['lifecycle']['pid_registered']);self.assertTrue(v['lifecycle']['direct_wait_verified']);self.assertTrue(v['original_exception_preserved'])
    def test_pid_registered_but_child_created_flag_false_is_still_reaped(self):
        v=self.row('pid-before-created-flag');self.assertFalse(v['child_created_flag']);self.assertTrue(v['lifecycle']['pid_registered']);self.assertTrue(v['lifecycle']['direct_wait_verified'])
    def test_non_normal_cases_have_no_artifacts(self):
        for n in audit.CASES:
            if n=='normal':continue
            for part in ('captured','report.json','classification.json'):self.assertFalse((self.root/'work/cases'/n/part).exists())
    def test_no_unregistered_pid_methods_called_by_finish(self):
        owner=s.SamplerOwner();owner._slot.started=True;owner._slot.child=s.POPEN.__new__(s.POPEN);owner._initialization_entered=True
        with patch.object(s.POPEN,'terminate',side_effect=AssertionError('terminate')),patch.object(s.POPEN,'kill',side_effect=AssertionError('kill')),patch.object(s.POPEN,'wait',side_effect=AssertionError('wait')):v=owner.finish()
        self.assertEqual(v['owner_status'],'creation_unresolved');self.assertIsNotNone(owner._slot.child)
    def test_unknown_handoff_does_not_downgrade_to_old_class(self):
        with self.assertRaises(ValueError):s.SamplerOwner().handoff()
    def test_all_actual_processes_use_same_reserved_runtime_object(self):
        for n in audit.ACTUAL:self.assertTrue(self.row(n)['same_runtime_object_retained'])
    def test_actual_wait_codes_are_integers(self):
        for n in audit.ACTUAL:
            v=self.row(n);self.assertIs(type(v['actual_returncodes'][0]),int);self.assertEqual(v['actual_returncodes'][0],v['lifecycle']['returncode'])
    def test_flags_cannot_promote_unknown_to_closed(self):
        v=self.row('unregistered-model');v['lifecycle']['creation_unresolved']=False
        with self.assertRaises(ValueError):audit.validate(v)
    def test_typed_exit_code_and_false_wait_mutations_rejected(self):
        for change in ('wait','exit','accepted'):
            v=copy.deepcopy(self.row('normal'))
            if change=='wait':v['lifecycle']['direct_wait_verified']=False
            if change=='exit':v['actual_returncodes']=[False];v['lifecycle']['returncode']=False
            if change=='accepted':v['accepted']=False
            with self.assertRaises(ValueError):audit.validate(v)
    def test_pure_validation_no_file_process_or_signal_calls(self):
        values=[self.row(n) for n in audit.CASES]
        with patch('builtins.open',side_effect=AssertionError('open')),patch.object(os,'open',side_effect=AssertionError('open')),patch.object(subprocess,'Popen',side_effect=AssertionError('spawn')):
            for v in values:audit.validate(v)
    def test_source_and_bytecode_runtime_recorded(self):
        info=audit.f.load(self.root/'runtime.json');self.assertEqual(set(info['opcode_targets']),{'before-child-store','before-stream-store','pid-before-created-flag'});self.assertEqual(audit.f.sha(audit.a.read(self.root/'runtime/subprocess.py')),info['subprocess_source_sha256'])
    def test_task_physical_authority_and_old_orphan_flags_false(self):
        for n in audit.CASES:
            v=self.row(n);self.assertFalse(v['task_complete'])
            for key in audit.FALSE:self.assertIs(v[key],False);self.assertIs(v['lifecycle'][key],False)
    def test_readonly_verify_does_not_construct_or_trace(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('spawn')),patch.object(sys,'settrace',side_effect=AssertionError('trace')),patch.object(audit,'exercise',side_effect=AssertionError('exercise')):audit.verify(self.root,self.pin)
    def test_external_pin_required(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_572_sources_preserve569(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(572,569))


if __name__=='__main__':unittest.main()
