import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_lifecycle_candidate as candidate


class LifecycleCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-life-device-')
        cls.root=Path(cls.tmp.name)/'review';cls.result=candidate.run(cls.root)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_new_identity_and_complete_arm_link(self):
        row=self.result;self.assertEqual(row['prior_sources'],189);self.assertEqual(len(row['source_hashes']),195)
        self.assertNotEqual(row['runtime_recipe_sha256'],candidate.b.load(candidate.DEVICE/'recipe.json')['input_digest'])
        self.assertEqual(row['build']['object_count'],14);self.assertEqual(row['build']['strict_format_units'],14)
        self.assertTrue(row['real_sdk_adapter_source_integrated'])

    def test_new_files_are_isolated_and_npdm_unchanged(self):
        self.assertEqual(len(self.result['changed_files']),8)
        self.assertEqual((self.root/'candidate/main.npdm').read_bytes(),(candidate.DEVICE/'main.npdm').read_bytes())
        self.assertEqual((self.root/'candidate/sysmodule.json').read_bytes(),(candidate.DEVICE/'sysmodule.json').read_bytes())
        self.assertEqual((self.root/'candidate/source/core.c').read_bytes(),(candidate.DEVICE/'source/core.c').read_bytes())
        with self.assertRaises(ValueError):candidate.run(self.root)

    def test_prepare_failure_never_initializes_usb_or_launches(self):
        row=self.result['models']['startup']['prepare-error'];self.assertEqual(row['usb_calls'],0);self.assertEqual(row['launches'],0)
        self.assertEqual(self.result['models']['startup']['usb-error']['launches'],0)
        self.assertEqual(self.result['models']['startup']['ok']['launches'],2)

    def test_actual_sdk_adapter_closes_only_its_own_handles(self):
        for row in self.result['models']['adapter'].values():
            self.assertLessEqual(row['creates'],1)
            self.assertEqual(row['fs_open']-(row['prepare_result']==91),row['fs_close'])
        self.assertEqual(self.result['models']['adapter']['ok']['prepare_result'],0)

    def test_short_reads_and_bad_readbacks_are_distinguished(self):
        rows=self.result['models']['adapter'];self.assertEqual(rows['short-read']['prepare_result'],0)
        self.assertGreater(rows['short-read']['reads'],rows['ok']['reads'])
        for name in ('zero-read','oversize-read','short-size','corrupt-write'):
            self.assertNotEqual(rows[name]['prepare_result'],0)

    def test_header_bytes_do_not_authenticate_failed_commit(self):
        row=self.result['models']['adapter']['header-commit-error'];self.assertEqual(row['prepare_result'],98)
        self.assertTrue(row['header_valid']);self.assertFalse(row['decoded']['own_commit_authenticated'])
        self.assertEqual(row['decoded']['valid_prefix_records'],0)
        late=self.result['models']['adapter']['record-commit-error'];self.assertEqual(late['prepare_result'],0)
        self.assertEqual(late['last_result'],98);self.assertEqual(late['decoded']['valid_prefix_records'],2)
        self.assertFalse(late['decoded']['own_commit_authenticated'])

    def test_record_write_error_disables_notes_without_retry(self):
        row=self.result['models']['adapter']['record-write-error'];self.assertEqual(row['prepare_result'],0)
        self.assertEqual(row['writes'],34);self.assertEqual(row['last_result'],94)
        self.assertEqual(row['decoded']['tail'],'invalid_record')

    def test_failed_joins_never_read_owner_or_emit_owner_context(self):
        for name,row in self.result['models']['lifecycle'].items():
            if 'join-error' in name:
                self.assertEqual(row['fs_open'],0);self.assertEqual(row['thread_closes'],0)
                self.assertNotIn('joined_context',[r['stage'] for r in row['capsule']['records']])
                self.assertEqual(row['capsule']['records'][-1]['stage'],'retain')

    def test_primary_failure_still_attempts_independent_execution_save(self):
        rows=self.result['models']['lifecycle']
        for kind in ('normal','diagnostic'):
            row=rows[kind+'-fs-open-error-ok'];self.assertEqual(row['fs_open'],2)
            self.assertIn('execution_save_result',[r['stage'] for r in row['capsule']['records']])
            self.assertTrue(row['retained'])

    def test_journal_failure_does_not_change_original_cleanup_decision(self):
        rows=self.result['models']['lifecycle']
        for kind in ('normal','diagnostic'):
            row=rows[kind+'-ok-journal-write-error'];control=rows[kind+'-ok-ok']
            for field in ('retained','thread_closes','fs_open','execution_save_acknowledged'):
                self.assertEqual(row[field],control[field],(kind,field))

    def test_diagnostic_always_retains_and_normal_requires_both_saves(self):
        rows=self.result['models']['lifecycle']
        self.assertEqual(rows['normal-ok-ok']['thread_closes'],2)
        self.assertEqual(rows['diagnostic-ok-ok']['thread_closes'],0)
        self.assertTrue(rows['diagnostic-ok-ok']['retained'])
        self.assertEqual(rows['normal-ok-commit-error']['thread_closes'],0)

    def test_new_elf_keeps_quiet_logger_and_workers_capture_free(self):
        linked=self.result['build']['linked_checks'];self.assertEqual(linked['quiet_guard_path']['quiet_true_path_calls'],[])
        for graph in linked['worker_graphs'].values():self.assertFalse(graph['production_capture_on_direct_graph'])
        for graph in linked['worker_graphs'].values():
            self.assertFalse(any(name.startswith('Ep0Life') for name in graph['direct_reachable_functions']))
        self.assertEqual(len(self.result['build']['lifecycle_machine_review']),7)
        for flag in ('arm_executed','actual_fs_service_verified','firmware_packaged','deployed','host_receiver_rebound','attempt_issued','root_cause_confirmed','whole_thread_stack_verified'):
            self.assertIs(self.result[flag],False)
        self.assertEqual(self.result['remaining'],0)


if __name__=='__main__':unittest.main()
