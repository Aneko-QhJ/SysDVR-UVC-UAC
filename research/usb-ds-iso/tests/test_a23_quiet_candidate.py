"""Quiet diagnostic generation and actual-body fault models, never hardware."""
import json
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_a23_quiet_candidate as candidate
from workflows.artifacts import verify


class QuietCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)/'candidate'
        cls.result=candidate.run(cls.output,arm=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_idle_and_streaming_never_capture_or_begin_after_expiry(self):
        for row in self.result['cases']['video'].values():
            self.assertEqual(row['capture_calls'],0)
            self.assertEqual(row['process_calls_started_after_expiry'],0)
        self.assertGreater(self.result['cases']['video']['streaming']['process_calls'],1000)

    def test_inflight_wait_is_not_misrepresented_as_bounded(self):
        cases=self.result['cases']['video']
        self.assertEqual(cases['process_returns_late']['elapsed_ms'],46000)
        self.assertEqual(cases['ready_returns_late']['elapsed_ms'],45000)
        self.assertFalse(self.result['synchronous_call_time_bound_verified'])

    def test_audio_is_idle_and_launch_failures_retain_quiet(self):
        rows=self.result['cases']['launch_audio']
        self.assertEqual([r['launches'] for r in rows],[2,1,2])
        self.assertEqual([r['audio_sleeps'] for r in rows],[3,0,0])
        self.assertTrue(all(r['quiet_retained'] for r in rows))

    def test_quiet_logger_skips_formatting_and_all_filesystem_calls(self):
        for name,row in self.result['cases']['logger'].items():
            if name.startswith('quiet-'):
                self.assertEqual([row[n] for n in ('formats','opens','sizes','writes','closes')],[0]*5)

    def test_logging_resumes_with_length_and_size_guards(self):
        rows=self.result['cases']['logger']
        self.assertEqual(rows['resumed-1024']['requested'],511)
        self.assertFalse(rows['resumed-1024']['span_exceeds_buffer'])
        self.assertEqual(rows['size-error-512']['writes'],0)
        self.assertEqual(rows['size-error-512']['closes'],1)

    def test_join_failure_keeps_gate_and_never_reads_or_saves(self):
        for row in self.result['cases']['lifecycle']:
            failed=row['primary_fault'] in ('video-join-error','audio-join-error')
            self.assertEqual(row['quiet_after_exit'],failed)
            self.assertEqual(row['quiet_clears'],0 if failed else 1)
            if failed:self.assertEqual((row['fs_open'],row['execution_bytes'],row['thread_closes']),(0,0,0))

    def test_identity_and_save_failure_retention_preserved(self):
        for row in self.result['cases']['lifecycle']:
            if row['primary_fault']=='identity-error':
                self.assertTrue(row['retained']);self.assertEqual(row['fs_open'],0)
            if row['execution_fault']=='commit-error':
                self.assertFalse(row['execution_save_acknowledged']);self.assertTrue(row['retained'])
            if row['kind']=='diagnostic':self.assertEqual(row['thread_closes'],0)

    def test_npdm_artifact_matches_explicit_8192_request(self):
        cfg=self.result['npdm']
        self.assertEqual(cfg['main_thread_stack_request_bytes'],8192)
        self.assertTrue(cfg['perturbation_control_verified'])
        self.assertFalse(cfg['actual_kernel_thread_budget_verified'])
        self.assertEqual(candidate.sha(self.output/'window-30s/main.npdm'),cfg['npdm_sha256'])

    def test_only_four_derived_sources_change_and_inputs_are_sealed(self):
        self.assertEqual(self.result['changed_files'],['core.c','core.h','sysmodule/main.c','uvc/ep0_candidate_recipe.h'])
        self.assertTrue(verify(self.output)['sha256_verified'])
        self.assertGreaterEqual(len(self.result['source_hashes']),168)
        with self.assertRaises(ValueError):candidate.run(self.output,arm=False)

    def test_no_new_hardware_authority_and_no_old_address_proof(self):
        for key in ('usb_accessed','sd_accessed','attempt_issued','arm_executed','firmware_packaged',
                    'deployed','host_receiver_rebound','root_cause_confirmed','whole_thread_stack_verified'):
            self.assertFalse(self.result[key])
        self.assertEqual(self.result['native_execution_count'],124)

    def test_fresh_elf_recipe_and_conditional_quiet_path(self):
        build=self.result['build'];bound=self.result['device_binding']
        self.assertEqual(build['object_count'],13)
        self.assertEqual(build['strict_format_units'],13)
        self.assertEqual(bound['runtime_recipe_sha256'],self.result['runtime_recipe_sha256'])
        self.assertEqual(bound['device_elf_sha256'],candidate.sha(self.output/'window-30s/full.elf'))
        check=build['linked_checks'];guard=check['quiet_guard_path']
        self.assertTrue(guard['acquire_load_and_release_store_verified'])
        self.assertEqual(guard['conditional_held_stack_bytes'],832)
        self.assertEqual(guard['quiet_true_path_calls'],[])
        self.assertFalse(check['old_address_certificates_reused'])
        for graph in check['worker_graphs'].values():self.assertFalse(graph['production_capture_on_direct_graph'])

    def test_quiet_instruction_drift_is_rejected(self):
        folder=self.output/'window-30s'
        functions,metadata=candidate.elf.build_functions((folder/'full.elf').read_bytes(),(folder/'disassembly.txt').read_text())
        logger=next(f for f in functions.values() if f['name']=='LogFunctionImpl')
        index=next(i for i,(_,op,_) in enumerate(logger['instructions']) if op=='ldarb')
        for which in ('load','return','symbol'):
            changed=copy.deepcopy(functions);meta=copy.deepcopy(metadata)
            if which=='load':
                pc,_,arg=changed[logger['start']]['instructions'][index]
                changed[logger['start']]['instructions'][index]=(pc,'ldrb',arg)
            elif which=='return':
                code=changed[logger['start']]['instructions']
                i=next(i for i,(_,op,_) in enumerate(code) if op=='ret')
                pc,_,_=code[i];code[i]=(pc,'bl','0 <forbidden>')
            else:
                next(s for s in meta['symbols'] if s['name']=='g_diagnosticQuiet')['address']+=1
            with self.assertRaises(ValueError):candidate.quiet_guard_certificate(changed,meta)


if __name__=='__main__':unittest.main()
