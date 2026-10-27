from pathlib import Path
import copy
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_spawn_boundary as audit


class SpawnBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_SPAWN_BOUNDARY_REVIEW')
        cls.root=Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-spawn-tests-',dir='/private/tmp'))/'review'
        if not saved:audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.result=audit.verify(cls.root,cls.pin)
    def gap(self,name):return audit.f.load(self.root/'work/gap'/name/'observation.json')
    def topology(self,name):return audit.f.load(self.root/'work/topology'/name/'observation.json')
    def test_sixteen_cases_twenty_two_direct_waits(self):self.assertEqual((self.result['model_cases'],self.result['actual_child_processes'],self.result['direct_child_waits']),(16,22,22))
    def test_before_constructor_no_child(self):self.assertEqual(self.gap('before-call')['spawned'],0)
    def test_constructor_return_exception_hides_live_child_from_slot(self):
        v=self.gap('constructor-return');self.assertEqual(v['spawned'],1);self.assertFalse(v['owner_slot_present']);self.assertEqual(v['outer_rescue_waits'],1)
    def test_actual_store_child_opcode_interrupted_before_assignment(self):
        v=self.gap('before-child-store');self.assertTrue(v['opcode_hook_fired']);self.assertFalse(v['owner_slot_present']);self.assertEqual(v['outer_rescue_waits'],1)
    def test_partial_slot_waited_child_but_left_two_streams_open(self):
        v=self.gap('before-stream-store');self.assertTrue(v['owner_direct_wait']);self.assertEqual(v['owner_reported_pending_streams'],0);self.assertEqual(v['actual_open_streams_before_outer_cleanup'],2);self.assertTrue(v['false_closed_observation'])
    def test_isolated_repair_closes_retained_child_streams(self):
        v=self.gap('repaired-stream-store');self.assertTrue(v['owner_direct_wait']);self.assertEqual(v['actual_open_streams_before_outer_cleanup'],0);self.assertFalse(v['false_closed_observation'])
    def test_initialized_streams_control_has_no_stream_leak(self):self.assertEqual(self.gap('before-spawn-flag')['actual_open_streams_before_outer_cleanup'],0)
    def test_reported_spawned_flag_is_not_handle_existence(self):
        v=self.gap('before-spawn-flag');self.assertFalse(v['owner_reported_spawned']);self.assertTrue(v['owner_slot_present']);self.assertTrue(v['owner_direct_wait'])
    def test_after_spawn_control_cleaned_by_owner(self):
        v=self.gap('after-spawn');self.assertTrue(v['owner_direct_wait']);self.assertEqual(v['outer_rescue_waits'],0)
    def test_all_gap_exceptions_keep_original_identity(self):
        for n in audit.GAPS:self.assertTrue(self.gap(n)['exception_identity_preserved'])
    def test_normal_direct_owner_model_can_sample(self):
        v=self.topology('normal');self.assertTrue(v['diagnostic_model_complete']);self.assertEqual(v['worker_returncode'],0);self.assertEqual(v['requester_returncode'],0)
    def test_dead_requester_before_request_creates_no_worker(self):self.assertFalse(self.topology('before-request')['worker_created'])
    def test_dead_requester_after_request_creates_no_worker(self):self.assertFalse(self.topology('after-request')['worker_created'])
    def test_missing_partial_or_complete_record_does_not_change_handle_wait(self):
        for n,label in (('before-owner','absent'),('partial-owner','partial'),('after-owner','complete')):
            v=self.topology(n);self.assertEqual(v['record_state'],label);self.assertTrue(v['worker_direct_wait']);self.assertEqual(v['worker_returncode'],86)
            record=self.root/'work/topology'/n/'owner-record.bin'
            self.assertEqual(record.exists(),label!='absent')
            if label=='partial':self.assertEqual(audit.a.read(record),b'{"fixture_owner_record":true}'[:len(b'{"fixture_owner_record":true}')//2])
    def test_requester_exit_during_read_rejects(self):
        v=self.topology('during-read');self.assertIn('worker_checkpoint',v['events']);self.assertEqual(v['worker_returncode'],86);self.assertFalse(v['sample_cache_accepted'])
    def test_requester_exit_after_validation_still_rejects(self):
        v=self.topology('after-validation');self.assertIn('worker_checkpoint',v['events']);self.assertEqual(v['worker_returncode'],86);self.assertEqual(v['worker_wire_size'],0)
    def test_complete_wire_and_wait_do_not_promote_failed_requester(self):
        v=self.topology('after-worker-wait');self.assertGreater(v['worker_wire_size'],0);self.assertEqual(v['worker_returncode'],0);self.assertFalse(v['diagnostic_model_complete']);self.assertFalse(v['sample_cache_accepted']);self.assertLess(v['events'].index('worker_wait0'),v['events'].index('requester_wait79'))
    def test_full_wire_recomputed_from_same_historical_bytes(self):
        args=audit.previous.args_at(self.root/'inputs/normal')
        for n in ('normal','after-worker-wait'):
            wire=audit.a.read(self.root/'work/topology'/n/'worker-wire.bin');files,_,classified=audit.previous.candidate.prior.decode_response(wire,*args[:2]);self.assertEqual(files,args[2]);self.assertFalse(classified['task_complete'])
    def test_all_children_record_actual_wait_not_only_end_message(self):
        self.assertEqual(sum(self.topology(n)['requester_direct_wait'] for n in audit.TOPOLOGY),9);self.assertEqual(sum(self.topology(n)['worker_direct_wait'] for n in audit.TOPOLOGY),7)
    def test_runtime_source_and_opcode_bindings_saved(self):
        runtime=audit.f.load(self.root/'runtime.json');self.assertEqual(audit.f.sha(audit.a.read(self.root/'runtime/subprocess.py')),runtime['subprocess_source_sha256']);self.assertEqual(set(runtime['opcode_targets']),{'before-child-store','before-stream-store','before-spawn-flag'});self.assertTrue((self.root/'runtime/owner-capture.dis').exists())
    def test_pure_verdict_validation_needs_no_file_or_process_io(self):
        gaps=[self.gap(n) for n in audit.GAPS];rows=[(self.topology(n),audit.a.read(self.root/'work/topology'/n/'worker-wire.bin')) for n in audit.TOPOLOGY]
        with patch('builtins.open',side_effect=AssertionError('open')),patch.object(os,'open',side_effect=AssertionError('open')),patch.object(subprocess,'Popen',side_effect=AssertionError('launch')):
            for v in gaps:audit.validate_gap(v)
            for v,wire in rows:audit.validate_topology(v,wire)
    def test_promoted_waits_and_acceptance_claims_rejected(self):
        values=[]
        for key in ('worker_direct_wait','requester_direct_wait','sample_cache_accepted','diagnostic_model_complete','worker_wire_size','worker_returncode'):
            v=copy.deepcopy(self.topology('after-worker-wait'));v[key]=False if key.endswith('wait') else True if key in ('sample_cache_accepted','diagnostic_model_complete') else 0 if key=='worker_wire_size' else 86;values.append(v)
        v=copy.deepcopy(self.topology('after-worker-wait'));v['worker_returncode']=False;values.append(v)
        wire=audit.a.read(self.root/'work/topology/after-worker-wait/worker-wire.bin')
        for v in values:
            with self.assertRaises(ValueError):audit.validate_topology(v,wire)
    def test_no_production_hardware_or_old_orphan_authority_upgraded(self):
        for v in [*(self.gap(n) for n in audit.GAPS),*(self.topology(n) for n in audit.TOPOLOGY)]:
            self.assertFalse(v['task_complete'])
            for key in audit.FALSE:self.assertIs(v[key],False)
    def test_readonly_verify_does_not_launch_trace_or_resample(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('launch')),patch.object(sys,'settrace',side_effect=AssertionError('trace')),patch.object(audit,'exercise',side_effect=AssertionError('exercise')):audit.verify(self.root,self.pin)
    def test_external_pin_required(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_569sources_preserve565(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(569,565))


if __name__=='__main__':unittest.main()
