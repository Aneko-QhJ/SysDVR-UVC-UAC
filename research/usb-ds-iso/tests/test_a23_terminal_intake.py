from pathlib import Path
import collections,errno,json,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_terminal_intake as audit
s=audit.sampler;m=audit.model


class TerminalIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_TERMINAL_INTAKE_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-intake-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.previous.args_at(self.root/'inputs/jobs'/name)
    def row(self,name):return self.r['semantic'][name]
    def unit(self):
        args=self.args();directory=audit.prepare(Path(tempfile.mkdtemp(prefix='a23-intake-unit-',dir='/private/tmp')),args[2]);return args,directory
    def test_eighty_three_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),self.r['accepted_cases'],self.r['rejected_cases']),(83,83,63,20))
    def test_all_fifty_eight_original_snapshots_preserved(self):
        for case in audit.previous.previous.model.CASES:
            target=self.root/'work/cases/base'/case;self.assertEqual(audit.cache(target/'captured'),self.args(case)[2])
    def test_base_classification_counts(self):
        counts=collections.Counter(row['classification']['classification'] for name,row in self.r['semantic'].items() if name.startswith('base/'));self.assertEqual(counts,dict(commit_associated=6,incomplete=52))
    def test_empty_directory_is_absent(self):self.assertEqual(self.row('control/empty')['classification']['classification'],'absent')
    def test_unlisted_symlink_is_ignored(self):self.assertTrue(self.row('control/ignored-symlink')['accepted']);self.assertEqual(self.row('control/ignored-symlink')['classification']['classification'],'commit_associated')
    def test_current_hardlink_pair_does_not_restore_history(self):self.assertEqual(self.row('control/hardlinked-pair')['classification']['hardlink_identity_status'],'unknown')
    def test_stable_conflicting_bytes_are_still_conflict(self):self.assertTrue(self.row('control/stable-conflict')['accepted']);self.assertEqual(self.row('control/stable-conflict')['classification']['classification'],'conflict')
    def test_post_validation_change_does_not_claim_atomic_capture(self):
        row=self.row('control/post-validation-change');self.assertTrue(row['accepted']);self.assertFalse(row['atomic_directory_snapshot_verified']);target=self.root/'work/cases/control/post-validation-change';after=audit.f.load(target/'post-validation-live-files.json');self.assertNotEqual(after[audit.TARGET],m.sha(audit.a.read(target/'captured'/audit.TARGET)));self.assertFalse(row['classification']['task_complete'])
    def test_allowed_symlink_directory_and_fifo_rejected(self):
        for name in ('entry-symlink','entry-directory','entry-fifo'):self.assertFalse(self.row('control/'+name)['accepted'])
    def test_symlink_in_root_or_ancestor_rejected(self):
        for name in ('root-symlink','ancestor-symlink'):self.assertFalse(self.row('control/'+name)['accepted'])
    def test_file_and_total_size_limits_reject(self):
        self.assertEqual(self.row('control/oversized')['rejection_group'],'file_limit');self.assertEqual(self.row('control/aggregate-oversized')['rejection_group'],'total_limit')
    def test_replacements_between_stat_open_and_final_check_rejected(self):
        for name in ('replace-after-lstat','replace-after-validation'):self.assertEqual(self.row('control/'+name)['rejection_group'],'entry_changed')
    def test_fifo_race_is_opened_nonblocking_then_rejected(self):self.assertEqual(self.row('control/fifo-after-lstat')['rejection_group'],'opened_type')
    def test_in_read_content_drift_truncate_and_growth_rejected(self):
        for name in ('mutate-between-reads','truncate-between-reads','grow-after-open'):self.assertFalse(self.row('control/'+name)['accepted'])
    def test_cross_view_creation_deletion_and_mutation_rejected(self):
        for name in ('create-between-views','delete-between-views','mutate-between-views'):self.assertEqual(self.row('control/'+name)['rejection_group'],'view_changed')
    def test_directory_path_replacement_rejected(self):self.assertEqual(self.row('control/replace-directory-between-views')['rejection_group'],'directory_changed')
    def test_read_error_and_budget_reject(self):self.assertEqual(self.row('control/read-error')['rejection_group'],'io_error');self.assertEqual(self.row('control/read-budget')['rejection_group'],'read_budget')
    def test_rejected_cases_return_no_cached_artifact(self):
        for name in audit.REJECTS:
            target=self.root/'work/cases/control'/name;row=audit.f.load(target/'outcome.json');self.assertIsNone(row['classification']);self.assertFalse((target/'captured').exists());self.assertFalse((target/'report.json').exists())
    def test_readonly_flags_and_no_mutation_api_calls(self):
        args,directory=self.unit();opened=[];original=os.open
        def op(path,flags,*a,**kw):opened.append(flags);return original(path,flags,*a,**kw)
        with patch.object(os,'open',side_effect=op),patch.object(os,'write',side_effect=AssertionError('write')),patch.object(os,'link',side_effect=AssertionError('link')),patch.object(os,'unlink',side_effect=AssertionError('unlink')),patch.object(os,'fsync',side_effect=AssertionError('sync')):files,_,_=s.capture(directory,*args[:2])
        self.assertEqual(files,args[2]);self.assertTrue(opened)
        for flags in opened:self.assertEqual(flags&os.O_ACCMODE,os.O_RDONLY);self.assertTrue(flags&os.O_NOFOLLOW);self.assertFalse(flags&(os.O_CREAT|os.O_TRUNC))
    def test_all_descriptors_closed_after_read_failure(self):
        args,directory=self.unit();opened=[];closed=[];op=os.open;cl=os.close
        def track_open(*a,**kw):fd=op(*a,**kw);opened.append(fd);return fd
        def track_close(fd):closed.append(fd);return cl(fd)
        with patch.object(os,'open',side_effect=track_open),patch.object(os,'close',side_effect=track_close),patch.object(os,'read',side_effect=OSError(errno.EIO,'read failure')):
            with self.assertRaises(s.IntakeError):s.capture(directory,*args[:2])
        self.assertEqual(collections.Counter(opened),collections.Counter(closed))
    def test_short_reads_and_eintr_complete_within_budget(self):
        args,directory=self.unit();original=os.read;calls=[]
        def read(fd,size):
            calls.append(fd)
            if len(calls)==1:raise InterruptedError(errno.EINTR,'first interruption')
            return original(fd,min(size,256))
        with patch.object(os,'read',side_effect=read):files,_,_=s.capture(directory,*args[:2])
        self.assertEqual(files,args[2])
    def test_close_error_rejects_and_finishes_cleanup(self):
        args,directory=self.unit();op=os.open;cl=os.close;opened=[];closed=[];injected=[]
        def track_open(*a,**kw):fd=op(*a,**kw);opened.append(fd);return fd
        def track_close(fd):
            closed.append(fd);cl(fd)
            if not injected:injected.append(1);raise OSError(errno.EIO,'after actual close')
        with patch.object(os,'open',side_effect=track_open),patch.object(os,'close',side_effect=track_close):
            with self.assertRaises(s.IntakeError):s.capture(directory,*args[:2])
        self.assertEqual(collections.Counter(opened),collections.Counter(closed))
    def test_outside_and_noncanonical_paths_fail_before_open(self):
        args=self.args()
        with patch.object(os,'open',side_effect=AssertionError('open')):
            for path in ('/Volumes/not-opened','/tmp/not-canonical','relative','/private/tmp/a/../b','/private/tmp/a/'):
                with self.subTest(path=path),self.assertRaises(s.IntakeError):s.capture(path,*args[:2])
    def test_bad_anchor_pin_fails_before_open(self):
        args=self.args()
        with patch.object(os,'open',side_effect=AssertionError('open')):
            with self.assertRaises(ValueError):s.capture('/private/tmp/not-opened',args[0],'0'*64)
    def test_all_authority_and_history_inference_false(self):
        for row in self.r['semantic'].values():
            self.assertFalse(row['task_complete']);self.assertFalse(row['atomic_directory_snapshot_verified']);self.assertFalse(row['historical_sync_or_wait_inferred'])
            for key in m.FALSE:self.assertIs(row[key],False)
            if row['accepted']:
                for key in ('directory_sync_status','actor_wait_status','actual_process_exit_status','hardlink_identity_status'):self.assertEqual(row['classification'][key],'unknown')
    def test_no_new_fixture_process_jobs_or_process_queries(self):self.assertEqual((self.r['new_fixture_processes'],self.r['new_fixture_jobs'],self.r['process_queries']),(0,0,0));self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_source557_preserves554(self):v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(557,554))
    def test_readonly_verify_has_no_launch_or_resampling(self):
        import subprocess
        with patch.object(subprocess,'Popen',side_effect=AssertionError('process')),patch.object(s,'capture',side_effect=AssertionError('resample')):audit.verify(self.root,self.pin)
    def test_review_pin_required(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_accepted_reports_are_bounded_and_explicitly_nonatomic(self):
        for name,row in self.r['semantic'].items():
            if not row['accepted']:continue
            report=audit.f.load(self.root/'work/cases'/name/'report.json');self.assertLessEqual(report['file_count'],18);self.assertLessEqual(report['total_bytes'],131072);self.assertFalse(report['atomic_directory_snapshot_verified']);self.assertEqual(report['equal_views'],2)


if __name__=='__main__':unittest.main()
