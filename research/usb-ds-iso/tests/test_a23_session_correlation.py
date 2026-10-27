"""Independent envelope, early bypass and immutable save receipt prototype."""
import json,struct,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_session_correlation as candidate
from analyze_ep0_session import decode_session
from analyze_ep0_startup import decode_startup
from analyze_ep0_diagnostic import decode_diagnostic
from analyze_ep0_candidate_capture import decode_capture
from workflows.artifacts import verify

class A23SessionCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=candidate.run(cls.output)
        cls.rows={r['case']:r for r in cls.result['cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def policy(self,name):return decode_session(self.raw(name))
    def raw(self,name):return (self.output/('policy-'+name+'.bin')).read_bytes()
    def changed(self,name,offset,value,width=4):
        data=bytearray(self.raw(name));struct.pack_into('<Q' if width==8 else '<I',data,offset,value)
        data[184:188]=bytes(4);struct.pack_into('<I',data,184,zlib.crc32(data[:192]));return data

    def test_all_old_video_service_results_are_preserved(self):
        old=json.loads((candidate.BOUNDED/'audit.json').read_text())
        self.assertEqual(self.result['case_count'],28)
        for row in old['cases']:
            self.assertEqual({k:v for k,v in row.items() if k not in ('candidate_recipe_digest','diagnostic','ownership')},
                             {k:v for k,v in self.rows[row['case']].items() if k!='session'})
        self.assertEqual(sum(r['session']['mode']=='startup_and_ep0' for r in self.rows.values()),19)

    def test_combined_ids_nonces_and_recipes_match_both_components(self):
        d=self.policy('combined');self.assertTrue(d['startup_ep0_locally_correlated'])
        self.assertEqual((d['starter'],d['ep0_writer']),(22,11))
        self.assertEqual(d['startup']['recipe_digest'],d['diagnostic']['recipe_digest'])
        self.assertEqual(d['boot_id_hex'],d['diagnostic']['trace']['boot_id_hex'])
        self.assertEqual(d['session_id_hex'],d['diagnostic']['trace']['session_id_hex'])

    def test_failed_joins_never_read_poison_ep0_or_sink_inputs(self):
        self.assertTrue(self.result['policy']['failed_join_poison_inputs_rejected'])
        for name,key,rc in (('video-join-failed','video_join',78),('audio-join-failed','audio_join',79)):
            d=self.policy(name);self.assertEqual((d['mode'],d['fallback_reason'],d[key]),('startup_only',1,rc))
            self.assertIsNone(d['diagnostic']);self.assertIsNone(d['admission']);self.assertIsNone(d['sink'])

    def test_missing_or_publishing_context_bypasses_all_ep0_inputs(self):
        for name in ('unbound','context-publishing'):
            d=self.policy(name);self.assertEqual(d['fallback_reason'],2);self.assertFalse(d['context_present'])
            self.assertIsNone(d['boot_id_hex']);self.assertIsNone(d['diagnostic'])

    def test_startup_only_live_prefix_does_not_require_seal_or_ep0(self):
        d=self.policy('live-startup');self.assertEqual(d['mode'],'startup_only');self.assertEqual(d['fallback_reason'],0)
        self.assertFalse(d['startup']['journal_sealed']);self.assertEqual(d['startup']['count'],1)
        self.assertEqual(len(d['startup']['unfinished_calls']),1);self.assertFalse(d['context_present'])

    def test_disabled_startup_metadata_has_no_fake_identity_or_journal(self):
        d=self.policy('metadata');self.assertEqual(len(self.raw('metadata')),192)
        self.assertEqual((d['startup_status'],d['startup_identity_result'],d['starter'],d['ep0_writer']),(3,97,0,0))
        self.assertIsNone(d['startup']);self.assertIsNone(d['diagnostic'])

    def test_ep0_only_retains_disabled_startup_without_claiming_association(self):
        d=self.policy('ep0-only');self.assertEqual(d['mode'],'ep0_only');self.assertEqual(d['starter'],0)
        self.assertIsNone(d['startup']);self.assertIsNotNone(d['diagnostic']);self.assertFalse(d['startup_ep0_locally_correlated'])

    def test_joined_normal_owner_is_not_relabelled_as_diagnostic(self):
        for name in ('complete','statuses-5','session-extra-2','ready-stop','window-wait'):
            d=self.rows[name]['session'];self.assertEqual((d['mode'],d['fallback_reason']),('startup_only',3))
            self.assertIsNone(d['admission']);self.assertIsNone(d['sink'])

    def test_budget_refusal_is_observable_without_hardware_cause_claim(self):
        d=self.rows['statuses-6']['session'];self.assertEqual(d['admission']['trace_refusals'],1)
        self.assertEqual(d['admission']['largest_request'],17);self.assertTrue(d['diagnostic']['fault'])
        self.assertFalse(d['root_cause_confirmed']);self.assertFalse(d['hardware_verified'])

    def test_sink_receipt_requires_return_and_immutable_publication(self):
        for name in ('combined','save-not-returned','receipt-publishing'):self.assertIsNone(self.policy(name)['sink'])
        d=self.policy('acknowledged');self.assertTrue(d['sink']['input_crc_matched']);self.assertTrue(d['sink']['commit_acknowledged'])
        self.assertFalse(d['envelope_own_save_result_recorded']);self.assertEqual(d['sink']['target'],'embedded EP0DIA1')

    def test_commit_failure_keeps_verified_content_separate_from_ack(self):
        s=self.policy('commit-error')['sink'];self.assertEqual((s['phase'],s['result']),(8,98))
        self.assertTrue(s['content_verified']);self.assertFalse(s['commit_acknowledged'])
        self.assertEqual(s['verified_bytes'],256)

    def test_maximum_and_rejections_leave_sources_and_output_intact(self):
        p=self.result['policy'];self.assertTrue(p['passed']);self.assertEqual(p['cases'],24)
        self.assertEqual((p['maximum'],p['work_bytes']),(7968,7776));self.assertTrue(p['source_immutable'])
        raw=self.raw('maximum');d=decode_session(raw);self.assertEqual(len(raw),7968)
        self.assertEqual(d['startup']['count'],64);self.assertEqual(len(d['diagnostic']['urbs']),16)
        self.assertEqual(len(d['diagnostic']['trace']['records']),128)

    def test_crc_repaired_cross_component_inconsistencies_are_rejected(self):
        for offset,value,width in ((96,23,8),(104,12,8),(112,9,4),(128,9,4),(144,4,4),(36,78,4),(44,3,4),(24,1,4),(68,129,4)):
            with self.subTest(offset=offset),self.assertRaises(ValueError):decode_session(self.changed('combined',offset,value,width))
        for offset,value in ((76,98),(188,1),(88,255)):
            with self.subTest(offset=offset),self.assertRaises(ValueError):decode_session(self.changed('acknowledged',offset,value))
        broken=bytearray(self.raw('combined'));broken[-1]^=1
        with self.assertRaises(ValueError):decode_session(broken)

    def test_legacy_formats_remain_distinct_and_are_embedded_unchanged(self):
        raw=self.raw('combined');ini,dia=struct.unpack_from('<2I',raw,28)
        self.assertEqual(decode_startup(raw[192:192+ini],self.policy('combined')['recipe_digest']),self.policy('combined')['startup'])
        self.assertEqual(decode_diagnostic(raw[192+ini:192+ini+dia],self.policy('combined')['recipe_digest']),self.policy('combined')['diagnostic'])
        for decoder in (decode_startup,decode_diagnostic,decode_capture):
            with self.assertRaises(ValueError):decoder(raw)

    def test_sealed_inputs_production_tickets_and_prototype_boundaries(self):
        for path in (self.output,candidate.SEALED,candidate.BOUNDED):self.assertTrue(verify(path))
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.base.ep0.PRIVATE/'analysis'/n),h)
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.startup.startup.REPO/n),h)
        for key in ('full_arm_candidate_integrated','device_filesystem_envelope_integrated','old_wire_modified','production_modified',
                    'prior_runtime_modified','usb_accessed','sd_accessed','arm_executed','firmware_packaged','actual_switch_threads_executed',
                    'actual_dma_executed','hardware_verified','root_cause_confirmed','source_authenticated','cleanup_authorized'):self.assertFalse(self.result[key])
        self.assertTrue(self.result['startup_transcript_synthetic']);self.assertTrue(self.result['save_outcome_injected'])
        self.assertEqual(self.result['policy']['fs_calls'],0);self.assertTrue((self.output/'session-arm.o').exists())
        self.assertEqual(list(self.output.rglob('*.elf')),[])
        for name in ('combined','acknowledged'):
            d=self.policy(name)
            for key in ('ownership_export_accepted','cleanup_authorized','source_authenticated','join_results_authenticated',
                        'save_return_authenticated','session_nonce_authenticated'):self.assertFalse(d[key])

if __name__=='__main__':unittest.main()
