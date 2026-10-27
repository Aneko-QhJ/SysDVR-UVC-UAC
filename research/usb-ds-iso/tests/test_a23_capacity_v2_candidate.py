"""Isolated V2 candidate: larger real request windows, formats and file failures."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_a23_capacity_v2_candidate as v2
import analyze_ep0_trace as old_trace
import analyze_ep0_candidate_capture as old_own
import analyze_ep0_diagnostic as old_dia
import analyze_ep0_session as old_rel
from analyze_ep0_trace_v2 import decode as trace_v2
from workflows.artifacts import verify


class CapacityV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name) / 'candidate'
        cls.result = v2.run(cls.output)
        cls.rows = {(r['configuration'], r['candidate'], r['prelude'], r['mode']): r
                    for r in cls.result['cases']}
        cls.prior = json.loads((v2.PRIOR / 'audit.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def row(self, n=0, mode='healthy', candidate=True, label='dormant'):
        return self.rows[label, candidate, n, mode]

    def test_all_eight_queries_and_logged_prelude_fit_both_candidates(self):
        for label in v2.ready.LABELS:
            for n in range(9):
                row = self.row(n, label=label)
                self.assertEqual((row['records'], row['slots']), (66 + 23*n, 6 + 2*n))
                self.assertEqual((row['sequence'], row['iso_posts'], row['status_writes']), (1, 1, 2))
                self.assertTrue(row['normal_export'])
                self.assertEqual(row['trace_refusals'], 0)
            row = self.row(9, 'log-prefix', label=label)
            self.assertEqual((row['records'], row['slots']), (236, 15))
            self.assertEqual((row['prelude_dispatched'], row['target_setup_deliveries']), (9, 3))
            self.assertTrue(row['normal_export'])

    def test_capacity_expansion_changes_old_refusals_without_clearing_history(self):
        old = next(r for r in self.prior['cases'] if r['candidate'] and r['configuration']=='dormant' and r['mode']=='healthy' and r['prelude']==4)
        self.assertEqual((old['sequence'], old['iso_posts']), (0, 0))
        row = self.row(4)
        self.assertEqual((row['sequence'], row['iso_posts']), (1, 1))
        self.assertEqual(row['slots'], 14)
        self.assertEqual(self.row(8)['slots'], 22)

    def test_original_and_v2_service_observations_match_on_healthy_inputs(self):
        for label in v2.ready.LABELS:
            for mode in ('healthy', 'reconnect'):
                for n in range(9):
                    candidate, baseline = self.row(n, mode, label=label), self.row(n, mode, False, label)
                    for key in ('in_posts', 'out_posts', 'iso_posts', 'sequence', 'stalls', 'status_writes'):
                        self.assertEqual(candidate[key], baseline[key], (label,n,mode,key))

    def test_failures_and_missing_evidence_keep_original_classifications(self):
        for row in self.prior['cases']:
            if not row['candidate'] or row['prelude'] or row['mode']=='healthy':
                continue
            new = self.row(row['prelude'], row['mode'], label=row['configuration'])
            self.assertEqual(new['evidence_assessment'], row['evidence_assessment'])
            for key in ('sequence', 'iso_posts', 'pending', 'normal_export', 'records'):
                self.assertEqual(new[key], row[key], (row['mode'],key))
            self.assertFalse(new['evidence_assessment']['usb_strict_pass'])

    def test_257_record_offsets_accept_239_and_refuse_240_before_setup(self):
        cases = {r['input']:r for r in self.result['admission_cases'] if r['kind']=='records'}
        self.assertEqual(len(cases), 257)
        for n, row in cases.items():
            self.assertEqual(row['records'], n+17 if n<=239 else n)
            self.assertEqual(row['trace_refusals'], int(n>239))
        self.assertEqual(cases[239]['records'], 256)
        self.assertTrue(cases[240]['events_left_signaled'])

    def test_two_identity_slots_required_before_iso_mutation(self):
        cases = {r['input']:r for r in self.result['admission_cases'] if r['kind']=='identities'}
        self.assertEqual((cases[30]['slots'],cases[30]['iso_posts'],cases[30]['sequence']), (32,1,1))
        self.assertEqual((cases[31]['slots'],cases[31]['iso_posts'],cases[31]['sequence']), (31,0,0))
        self.assertEqual(cases[31]['guard_reason'], 4)

    def test_all_three_maxima_are_serialized_and_independently_decoded(self):
        values = self.result['files']['serialization']
        self.assertEqual((values['normal'],values['diagnostic'],values['session']), (13040,13056,14368))
        self.assertTrue(values['one_short_untouched'])
        self.assertTrue(values['old_receipt_rejected'])
        self.assertEqual(values['sink_limit_rejections_before_create'],6)
        for kind in ('ownership','diagnostic','session'):
            analysis = self.result['files']['maxima'][kind]['analysis']
            self.assertFalse(analysis['hardware_verified'])
            self.assertFalse(analysis['root_cause_confirmed'])

    def test_old_and_new_decoders_reject_each_others_envelopes(self):
        for kind, new, old in (('ownership',v2.decode_capture,old_own.decode_capture),
                               ('diagnostic',v2.decode_diagnostic,old_dia.decode_diagnostic),
                               ('session',v2.decode_session,old_rel.decode_session)):
            with self.assertRaises(ValueError):
                old((self.output/('maximum.'+kind+'.bin')).read_bytes())
        own = next(v2.PRIOR.glob('*.ownership.bin')).read_bytes()
        dia = next(v2.PRIOR.glob('*.diagnostic.bin')).read_bytes()
        with self.assertRaises(ValueError):v2.decode_capture(own)
        with self.assertRaises(ValueError):v2.decode_diagnostic(dia)
        old_session = next((v2.SEALED/'dormant-native').glob('*.rel')).read_bytes()
        with self.assertRaises(ValueError):v2.decode_session(old_session)

    def test_trace_versions_reject_even_when_outer_version_is_repaired(self):
        raw = bytearray((self.output/'dormant-candidate-prelude0-healthy.ownership.bin').read_bytes())
        count = struct.unpack_from('<I',raw,20)[0]
        offset = 112 + count*16
        with self.assertRaises(ValueError):old_trace.decode(bytes(raw[offset:]))
        # A V1 outer layout with valid outer CRC still cannot contain TRC2.
        raw[:8] = b'EP0OWN1\0';struct.pack_into('<4H',raw,8,1,112,16,16)
        raw[92:96] = bytes(4);struct.pack_into('<I',raw,92,zlib.crc32(raw[:112]))
        with self.assertRaises(ValueError):old_own.decode_capture(bytes(raw))

    def test_crc_recipe_and_nested_format_corruption_are_rejected(self):
        path = self.output/'maximum.session.bin'
        raw = bytearray(path.read_bytes());raw[-1] ^= 1
        with self.assertRaises(ValueError):v2.decode_session(bytes(raw))
        with self.assertRaises(ValueError):v2.decode_session(path.read_bytes(),'ff'*32)
        raw = bytearray((self.output/'maximum.ownership.bin').read_bytes())
        count = struct.unpack_from('<I',raw,20)[0];offset=112+count*16
        raw[offset+6]=ord('1')
        struct.pack_into('<I',raw,88,zlib.crc32(raw[offset:]));raw[92:96]=bytes(4)
        struct.pack_into('<I',raw,92,zlib.crc32(raw[:112]))
        with self.assertRaises(ValueError):v2.decode_capture(bytes(raw))

    def test_actual_file_adapters_cover_maximum_short_read_and_failures(self):
        rows = {(r['kind'],r['fault']):r for r in self.result['files']['file_cases']}
        for kind, size in (('normal',13040),('diagnostic',13056),('session',14368)):
            for fault in v2.FILE_CASES:
                row = rows[kind,fault]
                self.assertEqual(row['ok'],fault in ('ok','short-read'))
                self.assertTrue(row['no_retry'])
                if row['ok']:self.assertEqual(row['verified_bytes'],size)
            row=rows[kind,'commit-error']
            self.assertTrue(row['content_verified']);self.assertFalse(row['commit_acknowledged'])
            self.assertEqual(rows[kind,'collision']['write'],0)
        for kind in ('diagnostic','session'):
            for fault in ('video-join-error','audio-join-error'):
                self.assertEqual(rows[kind,fault]['fs_open'],0)

    def test_commit_failure_retains_valid_bytes_but_corrupt_write_does_not(self):
        for kind, decoder in (('normal',v2.decode_capture),('diagnostic',v2.decode_diagnostic),('session',v2.decode_session)):
            good=(self.output/(kind+'-commit-error.disk.bin')).read_bytes()
            self.assertFalse(decoder(good)['hardware_verified'])
            bad=(self.output/(kind+'-corrupt-write.disk.bin')).read_bytes()
            with self.assertRaises(ValueError):decoder(bad)

    def test_two_full_elfs_bind_new_recipes_and_protected_logger(self):
        recipes=[]
        for label, build in self.result['builds'].items():
            self.assertEqual(build['object_count'],13)
            self.assertTrue(build['linked']);self.assertFalse(build['executed'])
            self.assertEqual(build['strict_format_units'],13)
            self.assertEqual(build['delta_from_v1']['data'],0)
            self.assertGreater(build['delta_from_v1']['bss'],0)
            self.assertTrue(build['logger_machine']['signed_clamp_511_verified'])
            self.assertTrue(build['logger_machine']['size_failure_skips_write'])
            self.assertTrue(build['recipe_readonly_sections'])
            self.assertEqual(build['linked_storage_objects']['exported']['bytes'],13040)
            self.assertEqual(build['linked_storage_objects']['session_work']['bytes'],14176)
            recipes.append(build['runtime_recipe_digest'])
            self.assertEqual(build['window_boundary']['window_ms'],0 if label=='dormant' else 30000)
        self.assertNotEqual(*recipes)

    def test_only_capacity_format_sink_and_recipe_sources_change(self):
        expected={'uvc/ep0_trace.h','uvc/ep0_trace_owner.h','uvc/ep0_candidate_capture.h',
                  'uvc/ep0_diagnostic_capture.h','uvc/ep0_session_capture.h','uvc/ep0_candidate_sink.h',
                  'uvc/ep0_session_sink.h','uvc/ep0_session_file.c','uvc/ep0_candidate_recipe.h'}
        for build in self.result['builds'].values():
            self.assertEqual(set(build['changed_source_files']),expected)
        with self.assertRaises(ValueError):v2.revisions('ep0_trace.h','bad source')

    def test_manifests_source_snapshots_and_execution_limits(self):
        self.assertEqual((self.result['matrix_case_count'],self.result['admission_case_count']), (124,259))
        self.assertEqual(self.result['native_execution_count'],442)
        self.assertTrue(verify(self.output));self.assertTrue(verify(v2.SEALED));self.assertTrue(verify(v2.PRIOR))
        for name, expected in self.result['production_sources_sha256'].items():
            self.assertEqual(v2.ready.sha(v2.REPO/name),expected)
        for name, expected in self.result['tickets_sha256'].items():
            self.assertEqual(v2.ready.sha(v2.SEALED.parent/name),expected)
        for key in ('production_modified','formats_v1_modified','prior_runtime_modified','prior_evidence_modified',
                    'usb_accessed','sd_accessed','arm_executed','firmware_packaged','hardware_verified',
                    'root_cause_confirmed','whole_thread_stack_verified','full_formatter_replay_on_new_elf'):
            self.assertFalse(self.result[key])
        with self.assertRaises(ValueError):v2.run(self.output)


if __name__=='__main__':unittest.main()
