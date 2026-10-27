from pathlib import Path
import errno,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_parent_crash as audit
m=audit.model


class ParentCrashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_PARENT_CRASH_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-parent-crash-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def test_twenty_seven_cases_and_authority_always_false(self):
        self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(27,11,16))
        for row in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for key in m.FALSE:self.assertIs(row[key],False)
    def test_only_normal_outer_completion(self):self.assertEqual({n for n,v in self.r['semantic'].items() if v['parent_crash_model_complete']},{'normal'})
    def test_before_popen_has_no_worker_handshake_or_exit_note(self):
        r=self.r['semantic']['before-popen'];self.assertFalse(r['worker_handshake_valid']);self.assertFalse(r['worker_exit_note_valid']);self.assertFalse(self.args('before-popen')[4]['worker_seen'])
    def test_absent_owner_is_not_absent_worker(self):
        r=self.r['semantic']['after-popen-unrecorded'];self.assertFalse(r['owner_record_valid']);self.assertTrue(r['worker_handshake_valid']);self.assertTrue(r['unrecorded_worker_gap_observed'])
    def test_partial_owner_does_not_hide_worker(self):
        args=self.args('owner-partial')
        with self.assertRaises(ValueError):m.parse(args[2]['owner.json'])
        self.assertTrue(self.r['semantic']['owner-partial']['unrecorded_worker_gap_observed'])
    def test_synced_owner_does_not_authorize_restart_or_signal(self):
        r=self.r['semantic']['owner-synced'];self.assertTrue(r['owner_record_valid']);self.assertFalse(r['parent_crash_model_complete']);self.assertFalse(r['restart_allowed']);self.assertFalse(r['journal_pid_signal_authorized'])
    def test_four_parent_sigkill_windows_abort_worker_on_lifeline_eof(self):
        for name in m.CASES:
            if not name.startswith('child-'):continue
            args=self.args(name);self.assertEqual(args[3]['returncode'],-9);self.assertEqual(args[5][-1]['exit_code'],86);self.assertEqual(args[5][-1]['reason'],'parent_pipe_eof');self.assertTrue(self.r['semantic'][name]['worker_exit_note_valid'])
    def test_completed_inner_report_cannot_override_parent_exit(self):
        r=self.r['semantic']['after-parent-report'];self.assertTrue(r['parent_inner_completion']);self.assertEqual(self.args('after-parent-report')[3]['returncode'],79);self.assertFalse(r['parent_crash_model_complete'])
    def test_closed_guardian_gate_refuses_payload(self):
        args=self.args('gate-closed');self.assertEqual(args[5][-1]['exit_code'],87);self.assertEqual(args[5][-1]['reason'],'guardian_closed');self.assertFalse(self.r['semantic']['gate-closed']['parent_inner_completion']);self.assertFalse((self.root/'work/cases/gate-closed/result').exists())
    def test_proc_exit_is_not_guardian_wait_or_orphan_reaping(self):
        self.assertEqual((self.r['python_fixture_parent_processes'],self.r['python_fixture_worker_processes'],self.r['direct_parent_waits'],self.r['worker_proc_exit_notes']),(11,10,11,10))
        self.assertEqual((self.r['workers_reaped_by_original_parent'],self.r['interrupted_parent_orphan_workers'],self.r['guardian_worker_waits']),(3,7,0))
        for name in m.CASES:
            if name=='before-popen':continue
            guard=self.args(name)[4];self.assertEqual(guard['waitpid_errno'],errno.ECHILD);self.assertFalse(guard['worker_waited_by_guardian']);self.assertFalse(self.r['semantic'][name]['orphan_reaping_verified'])
    def test_no_worker_pid_signals(self):
        self.assertEqual(self.r['worker_pid_signals'],0)
        for name in m.CASES:self.assertEqual(self.args(name)[4]['worker_pid_signals'],0)
    def test_retry_and_recovery_refusals_preserve_all_evidence(self):
        for name in m.CASES:self.assertTrue(all(audit.f.load(self.root/'work/cases'/name/'recovery.json').values()))
    def test_sixteen_semantic_mutants_rejected(self):
        for row in self.r['mutations'].values():self.assertFalse(row['parent_crash_model_complete']);self.assertTrue(row['errors'])
    def test_external_parent_crash_plan_pin_required(self):
        args=self.args();args[1]='0'*64
        with self.assertRaisesRegex(ValueError,'external parent crash'):m.assess(*args)
    def test_pure_consumer_has_no_filesystem_or_process_queries(self):
        saved=[self.args(n) for n in m.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.os,'waitpid',side_effect=AssertionError('wait')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_six_runtime_pins_and_source528_preserves523(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(528,523));self.assertEqual(len(self.r['code_sha256']),6);self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_coherent_outer_forgery_remains_only_model_evidence(self):
        args=self.args('after-parent-report');v=m.parse(args[0]);v['scenario']='normal';args[0]=m.encode(v);args[1]=m.sha(args[0]);args[2]['crash-plan.json']=args[0];args[3]['returncode']=0
        owner=m.parse(args[2]['owner.json']);owner['crash_plan_sha256']=args[1];args[2]['owner.json']=m.encode(owner)
        for msg in args[5]:msg['crash_plan_sha256']=args[1]
        r=m.assess(*args);self.assertTrue(r['parent_crash_model_complete']);self.assertFalse(r['process_origin_authenticated']);self.assertFalse(r['orphan_reaping_verified'])
    def test_historical_sdk_materials_not_regenerated(self):
        files=self.args()[2];actual={n.removeprefix('result/materials/'):v for n,v in files.items() if n.startswith('result/materials/')}
        self.assertEqual(actual,audit.cache(self.root/'inputs/seed'));self.assertFalse(self.r['semantic']['normal']['cached_sdk_materials_generated_this_launch'])
    def test_bool_pids_and_returncodes_rejected(self):
        for name in ('owner-pid-bool','ready-pid-bool','parent-return-bool'):self.assertTrue(self.r['mutations'][name]['errors']);self.assertFalse(self.r['mutations'][name]['parent_crash_model_complete'])


if __name__=='__main__':unittest.main()
