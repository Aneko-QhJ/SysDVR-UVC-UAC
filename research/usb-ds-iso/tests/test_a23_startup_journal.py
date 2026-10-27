"""Independent startup-only wire, API observations and published prefix checks."""
import json,struct,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_startup_journal as journal
from analyze_ep0_startup import decode_startup
from analyze_ep0_diagnostic import decode_diagnostic
from analyze_ep0_candidate_capture import decode_capture
from workflows.artifacts import verify

def repair(data):
    data=bytearray(data);struct.pack_into('<I',data,72,zlib.crc32(data[96:]));data[76:80]=bytes(4)
    struct.pack_into('<I',data,76,zlib.crc32(data[:96]));return bytes(data)

class A23StartupJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=journal.run(cls.output)
        cls.rows={r['case']:r for r in cls.result['cases']};cls.recipe=cls.result['recipe_digest']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def policy(self,name):return decode_startup((self.output/('policy-'+name+'.bin')).read_bytes())

    def test_all_40_service_results_and_resource_observations_are_preserved(self):
        previous=json.loads((journal.SEALED/'audit.json').read_text())
        self.assertEqual(len(self.rows),40)
        for row in previous['cases']:
            actual={k:v for k,v in self.rows[row['case']].items() if k!='startup_journal'};self.assertEqual(actual,row)
        self.assertLessEqual(max(r['startup_journal']['count'] for r in self.rows.values()),64)

    def test_partial_capture_failure_retains_raw_audio_result_and_prior_successes(self):
        d=self.rows['core-audio-error']['startup_journal']
        successful=[r['step'] for r in d['successful_api_results']]
        self.assertIn('fs_initialize',successful);self.assertIn('sd_open',successful);self.assertIn('video_open',successful)
        failed={r['step']:r['result'] for r in d['failed_api_results']};self.assertEqual(failed['audio_open'],72)
        self.assertEqual(failed['core_initialize'],72);self.assertNotIn('fs_exit',[r['step'] for r in d['records']])

    def test_created_and_started_are_separate_api_observations(self):
        d=self.rows['video-start-error']['startup_journal'];ok=[r['step'] for r in d['successful_api_results']]
        self.assertIn('video_create',ok);self.assertNotIn('video_start',ok)
        self.assertEqual(d['fatal']['result'],82)
        d=self.rows['audio-create-error']['startup_journal'];self.assertIn('video_start',[r['step'] for r in d['successful_api_results']])
        self.assertEqual(d['fatal']['result'],81);self.assertFalse(d['thread_liveness_authenticated'])

    def test_retry_is_retained_as_repeated_history_without_reset(self):
        d=self.rows['retry-partial']['startup_journal']
        events=[r for r in d['records'] if r['step']=='fs_initialize' and r['event']=='result']
        self.assertEqual(len(events),2);self.assertTrue(d['complete_journal'])
        self.assertEqual(self.rows['retry-partial']['fs_refs'],1)

    def test_void_close_return_is_not_a_fabricated_success_result(self):
        d=self.policy('void');self.assertEqual(d['records'][1]['event'],'void_return')
        self.assertIsNone(d['records'][1]['result']);self.assertEqual(d['successful_api_results'],[])
        self.assertFalse(d['cleanup_authorized'])

    def test_full_capacity_retains_prefix_and_marks_overflow(self):
        d=self.policy('full');self.assertEqual(d['count'],64);self.assertTrue(d['overflow']);self.assertTrue(d['journal_sealed'])
        self.assertFalse(d['complete_journal']);self.assertEqual((self.output/'policy-full.bin').stat().st_size,1120)

    def test_busy_writer_snapshot_contains_only_published_prefix(self):
        d=self.policy('busy-prefix');self.assertEqual(d['count'],1);self.assertTrue(d['writer_in_progress'])
        self.assertEqual(d['unfinished_calls'],['fs_initialize']);self.assertFalse(d['journal_sealed'])
        self.assertEqual(d['records'][0]['event'],'call')

    def test_wrong_writer_invalid_event_and_immutable_seal_policy(self):
        for name in ('wrong-writer','invalid','mismatch'):
            d=self.policy(name);self.assertTrue(d['invalid']);self.assertEqual(d['count'],0)
        d=self.policy('failure');self.assertTrue(d['journal_sealed']);self.assertEqual(d['fatal']['result'],82)
        self.assertEqual(self.policy('terminal')['count'],1);self.assertTrue(self.result['policy']['passed']);self.assertEqual(self.result['policy']['cases'],15)

    def test_real_cpu_reader_writer_threads_see_committed_ordinals_only(self):
        p=self.result['policy'];self.assertEqual((p['cpu_threads'],p['journals'],p['published_records']),(2,32,2048))
        self.assertGreater(p['concurrent_reads'],0);self.assertGreater(p['live_prefix_reads'],0)
        self.assertFalse(p['switch_threads_executed']);self.assertTrue(self.result['thread_sanitizer_policy']['passed']);d=self.policy('concurrent-final')
        self.assertEqual(d['count'],64);self.assertTrue(d['complete_journal']);self.assertFalse(d['invalid'])

    def test_startup_wire_is_rejected_by_existing_normal_and_diagnostic_decoders(self):
        data=(self.output/'policy-failure.bin').read_bytes()
        for decoder in (decode_capture,decode_diagnostic):
            with self.assertRaises(ValueError):decoder(data)
        d=decode_startup(data);self.assertTrue(d['startup_only']);self.assertFalse(d['ownership_export_accepted'])

    def test_crc_size_reserved_and_recipe_mismatch_reject(self):
        data=(self.output/'policy-failure.bin').read_bytes()
        for p in (0,40,96,len(data)-1):
            damaged=bytearray(data);damaged[p]^=1
            with self.assertRaises(ValueError):decode_startup(damaged)
        with self.assertRaises(ValueError):decode_startup(data[:-1])
        with self.assertRaises(ValueError):decode_startup(data+b'\0')
        with self.assertRaises(ValueError):decode_startup(data,'00'*32)
        for p in (28,80,108):
            damaged=bytearray(data);damaged[p]=1
            with self.assertRaises(ValueError):decode_startup(repair(damaged))

    def test_semantic_corruptions_reject_even_with_recomputed_crc(self):
        data=(self.output/'policy-failure.bin').read_bytes()
        mutations=((20,4,2),(20,4,9),(96,2,27),(98,2,4),(104,4,2),(112,2,13))
        for at,width,value in mutations:
            damaged=bytearray(data);damaged[at:at+width]=value.to_bytes(width,'little')
            with self.subTest(at=at,value=value):
                with self.assertRaises(ValueError):decode_startup(repair(damaged))
        damaged=bytearray(data);struct.pack_into('<H',damaged,98,2)
        with self.assertRaises(ValueError):decode_startup(repair(damaged))

    def test_arm_object_is_compiled_without_firmware_integration_or_cleanup(self):
        self.assertTrue((self.output/'startup-arm.o').exists());self.assertEqual(list(self.output.rglob('*.elf')),[])
        self.assertTrue(self.result['header_arm_compiled']);self.assertFalse(self.result['full_arm_candidate_integrated'])
        self.assertTrue(self.result['native_api_adapter_hooks_only']);self.assertFalse(self.result['cleanup_authorized'])
        self.assertFalse(self.result['diagnostic_wire_modified']);self.assertFalse(self.result['actual_switch_threads_executed'])

    def test_sources_tickets_evidence_and_offline_boundary(self):
        self.assertTrue(verify(self.output));self.assertTrue(verify(journal.SEALED))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(journal.base.ep0.sha(journal.startup.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(journal.base.ep0.sha(journal.base.ep0.PRIVATE/'analysis'/n),h)
        for key in ('production_modified','prior_runtime_modified','usb_accessed','sd_accessed','arm_executed','firmware_packaged',
                    'actual_switch_threads_executed','actual_dma_executed','initialization_rollback_implemented','hardware_verified','root_cause_confirmed'):
            self.assertFalse(self.result[key])

if __name__=='__main__':unittest.main()
