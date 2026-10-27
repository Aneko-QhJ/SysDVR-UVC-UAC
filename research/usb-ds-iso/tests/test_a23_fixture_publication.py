from pathlib import Path
import os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_fixture_publication as audit
m=audit.model;p=audit.publication


class FixturePublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_FIXTURE_PUBLICATION_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-publication-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def test_forty_three_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(43,27,16))
    def test_only_normal_publication_completes(self):self.assertEqual({n for n,v in self.r['semantic'].items() if v['publication_model_complete']},{'normal'})
    def test_no_restart_or_physical_authority(self):
        for v in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for k in m.FALSE:self.assertIs(v[k],False)
    def test_all_eighteen_cut_prefixes_are_exact(self):
        for event in p.EVENTS:
            args=self.args('cut-'+event);trace=[m.parse(v) for v in args[2]['trace.jsonl'].splitlines()]
            self.assertEqual([v['event'] for v in trace],list(p.EVENTS[:p.EVENTS.index(event)+1]));self.assertTrue(self.r['semantic']['cut-'+event]['trace_prefix_valid'])
    def test_empty_attempt_remains_spent_and_reuse_refused(self):
        args=self.args('cut-attempt.open');self.assertEqual(args[2]['launch-attempt.json'],b'');self.assertFalse(self.r['semantic']['cut-attempt.open']['attempt_valid']);self.assertTrue(self.r['recovery']['cut-attempt.open']['exclusive_reuse_refused'])
    def test_partial_attempt_not_repaired(self):
        args=self.args('cut-attempt.partial')
        with self.assertRaises(ValueError):m.parse(args[2]['launch-attempt.json'])
        self.assertTrue(self.r['recovery']['cut-attempt.partial']['exclusive_reuse_refused']);self.assertFalse(self.r['semantic']['cut-attempt.partial']['restart_allowed'])
    def test_complete_attempt_before_sync_is_not_payload_permission(self):
        r=self.r['semantic']['cut-attempt.complete'];self.assertTrue(r['attempt_valid']);self.assertFalse(r['payload_barrier_recorded']);self.assertFalse(r['publication_model_complete'])
    def test_attempt_sync_failures_never_reach_payload(self):
        for label in ('attempt.open','attempt.file_sync','attempt.directory_sync','attempt.parent_directory_sync'):
            r=self.r['semantic']['fail-'+label];self.assertFalse(r['payload_barrier_recorded']);self.assertFalse(r['receipt_visible'])
    def test_partial_receipt_is_not_published(self):
        args=self.args('cut-receipt.partial');self.assertIn('result/receipt.json.part',args[2]);self.assertNotIn('result/receipt.json',args[2])
        with self.assertRaises(ValueError):m.parse(args[2]['result/receipt.json.part'])
    def test_receipt_visibility_begins_at_exclusive_link(self):
        self.assertFalse(self.r['semantic']['cut-receipt.close']['receipt_visible']);self.assertTrue(self.r['semantic']['cut-receipt.link']['receipt_visible'])
    def test_fully_emitted_report_and_receipt_do_not_override_interruption(self):
        r=self.r['semantic']['cut-stdout.emit'];self.assertTrue(r['receipt_binding_valid']);self.assertTrue(r['cached_materials_valid']);self.assertFalse(r['process_healthy']);self.assertFalse(r['publication_model_complete'])
    def test_recovery_has_no_filesystem_or_process_api(self):
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):
            with self.assertRaisesRegex(ValueError,'refuses restart'):p.recover(Path('/private/tmp/unused-publication-job'))
    def test_all_sixteen_reanchored_semantic_mutations_fail(self):
        for v in self.r['mutations'].values():self.assertFalse(v['publication_model_complete']);self.assertTrue(v['errors'])
    def test_external_publication_plan_pin_required(self):
        args=self.args();args[1]='0'*64
        with self.assertRaisesRegex(ValueError,'external publication plan'):m.assess(*args)
    def test_cached_sdk_bytes_retained_without_new_sdk(self):
        args=self.args();actual={n.removeprefix('result/materials/'):v for n,v in args[2].items() if n.startswith('result/materials/')}
        self.assertEqual(actual,audit.cache(self.root/'inputs/seed'));self.assertFalse(self.r['semantic']['normal']['cached_sdk_materials_generated_this_launch'])
    def test_pure_consumer_opens_no_files(self):
        saved=[self.args(n) for n in audit.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_existing_receipt_is_not_overwritten(self):
        job=Path(tempfile.mkdtemp(prefix='a23-link-collision-',dir='/private/tmp'))
        def checkpoint(label,phase):
            if label=='receipt.close' and phase=='after':(job/'result/receipt.json').write_bytes(b'existing receipt')
        with self.assertRaises(FileExistsError):p.publish(job,b'attempt',{'sample':b'model data'},b'new receipt',checkpoint)
        self.assertEqual((job/'result/receipt.json').read_bytes(),b'existing receipt');self.assertEqual((job/'result/receipt.json.part').read_bytes(),b'new receipt')
    def test_fsync_oserror_retains_attempt_and_stops_payload(self):
        job=Path(tempfile.mkdtemp(prefix='a23-sync-error-',dir='/private/tmp'));events=[]
        with patch.object(p.os,'fsync',side_effect=OSError('fixed fsync API rejection')):
            with self.assertRaises(OSError):p.publish(job,b'attempt',{},b'receipt',lambda label,phase:events.append((label,phase)))
        self.assertEqual((job/'launch-attempt.json').read_bytes(),b'attempt');self.assertNotIn(('payload.begin','after'),events);self.assertFalse((job/'result').exists())
    def test_short_writes_completed_and_zero_progress_rejected(self):
        received=[]
        def short(_fd,raw):received.append(bytes(raw[:2]));return min(2,len(raw))
        with patch.object(p.os,'write',side_effect=short):p.write_all(99,b'abcdefg')
        self.assertEqual(b''.join(received),b'abcdefg')
        with patch.object(p.os,'write',return_value=0):
            with self.assertRaises(OSError):p.write_all(99,b'x')
    def test_coherent_outer_forgery_remains_only_model_evidence(self):
        args=self.args('cut-stdout.emit');v=m.parse(args[0]);v['cut_after']=None;args[0]=m.encode(v);args[1]=m.sha(args[0]);args[2]['publication-plan.json']=args[0];args[5]['returncode']=0
        r=m.assess(*args);self.assertTrue(r['publication_model_complete']);self.assertFalse(r['process_origin_authenticated']);self.assertFalse(r['power_loss_recovery_verified'])
    def test_source517_preserves512_and_formal_namespace_absent(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(517,512));self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
