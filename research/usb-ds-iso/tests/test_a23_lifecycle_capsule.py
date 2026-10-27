import copy
import struct
import sys
import tempfile
import unittest
from pathlib import Path
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_a23_lifecycle_capsule as audit
import a23_lifecycle_capsule as fmt


class CapsuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-lifecycle-prototype-')
        cls.root=Path(cls.temp.name)/'review';cls.audit=audit.run(cls.root)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def decode(self,name):return fmt.decode((self.root/(name+'.bin')).read_bytes(),audit.MODEL_RECIPE)

    def test_prototype_keeps_old_device_and_failure_state(self):
        self.assertEqual(self.audit['prior_sources'],184);self.assertEqual(len(self.audit['source_hashes']),189)
        for flag in ('device_instrumentation_integrated','device_rebuilt','host_rebuilt','deployed','hardware_verified','root_cause_confirmed'):
            self.assertIs(self.audit[flag],False)
        self.assertEqual(self.audit['remaining'],0)

    def test_original_source_and_elf_points_are_bound(self):
        original=audit.original_review();self.assertEqual(original['elf_sha256'],'56778e5733b73e588eb6d31c1bf1ca29c97c6d400f215537ef54bc8c84fcfef6')
        self.assertEqual(original['iso_state4'],'retained');self.assertEqual(len(original['elf_functions']),6)
        self.assertEqual(len(original['insertion_points']),10)

    def test_window_and_blocked_join_prefixes_are_different(self):
        expected={'prepared-only':'prepared','window-not-observed':'quiet_enter','video-join-blocked':'video_join_call',
                  'audio-join-blocked':'audio_join_call','sd-open-blocked':'sd_open_call','create-blocked':'file_create_call'}
        for name,last in expected.items():
            with self.subTest(name=name):self.assertEqual(self.decode(name)['records'][-1]['stage'],last)

    def test_no_emission_during_window_and_poisoned_context_rejected_before_read(self):
        for case in self.audit['native_model_cases'].values():
            if case['scenario'] not in ('prepared-only',) and not case['disabled']:
                self.assertGreaterEqual(case['denied_without_io'],5)
        self.assertEqual(self.decode('video-join-failed')['supplied_join_success_mask'],2)
        self.assertNotIn('joined_context',[r['stage'] for r in self.decode('video-join-failed')['records']])

    def test_filesystem_failures_are_observations_and_do_not_authorize_cleanup(self):
        for name,rc in [('sd-open-failed',91),('create-failed',92)]:
            result=self.decode(name);self.assertEqual(result['records'][-1]['result'],rc)
            self.assertFalse(result['cleanup_authorized']);self.assertTrue(result['reported_closed'])

    def test_successful_diagnostic_remains_retained(self):
        result=self.decode('diagnostic-saved');self.assertEqual(result['records'][-1]['stage'],'retain')
        self.assertFalse(result['own_commit_authenticated']);self.assertFalse(result['hardware_verified'])
        self.assertEqual(result['supplied_join_success_mask'],3)

    def test_full_bytes_can_outlive_failed_commit_no_retry(self):
        count=0
        for name,row in self.audit['native_model_cases'].items():
            if name.startswith('write-failure-'):
                count+=1;self.assertTrue(row['disabled']);self.assertEqual(row['failures'],1)
                result=self.decode(name);self.assertEqual(result['valid_prefix_records'],row['acknowledged_records']+(row['writes']>1))
                self.assertFalse(result['own_commit_authenticated'])
        self.assertEqual(count,self.audit['native_model_cases']['diagnostic-saved']['writes'])

    def test_capacity_stops_without_overwrite(self):
        result=self.decode('capacity');self.assertEqual(result['valid_prefix_records'],40);self.assertEqual(result['tail'],'capacity_end')
        self.assertEqual(len((self.root/'capacity.bin').read_bytes()),3968)

    def test_header_corruption_and_wrong_recipe_rejected(self):
        raw=(self.root/'diagnostic-saved.bin').read_bytes()
        for off in (0,8,16,24,40,56,88,124):
            mutant=bytearray(raw);mutant[off]^=1
            with self.subTest(off=off),self.assertRaises(ValueError):fmt.decode(mutant,audit.MODEL_RECIPE)
        with self.assertRaises(ValueError):fmt.decode(raw,'00'*32)
        with self.assertRaises(ValueError):fmt.decode(raw[:127],audit.MODEL_RECIPE)

    def test_invalid_or_partial_tail_preserves_only_valid_prefix(self):
        raw=bytearray((self.root/'diagnostic-saved.bin').read_bytes());raw[fmt.HEADER+fmt.RECORD+20]^=1
        result=fmt.decode(raw,audit.MODEL_RECIPE);self.assertEqual(result['valid_prefix_records'],1);self.assertEqual(result['tail'],'invalid_record')
        raw=(self.root/'diagnostic-saved.bin').read_bytes();result=fmt.decode(raw[:fmt.HEADER+fmt.RECORD+7],audit.MODEL_RECIPE)
        self.assertEqual(result['valid_prefix_records'],1);self.assertEqual(result['tail'],'partial_record')

    def test_gap_and_reordered_stage_cannot_claim_complete_sequence(self):
        raw=bytearray((self.root/'diagnostic-saved.bin').read_bytes());off=fmt.HEADER+fmt.RECORD
        raw[off:off+fmt.RECORD]=bytes(fmt.RECORD);result=fmt.decode(raw,audit.MODEL_RECIPE)
        self.assertEqual(result['tail'],'gap_before_nonzero_tail');self.assertEqual(result['valid_prefix_records'],1)
        raw=bytearray((self.root/'diagnostic-saved.bin').read_bytes());struct.pack_into('<H',raw,off+8,22)
        struct.pack_into('<I',raw,off+92,zlib.crc32(raw[off:off+92]));result=fmt.decode(raw,audit.MODEL_RECIPE)
        self.assertEqual(result['tail'],'invalid_record');self.assertEqual(result['valid_prefix_records'],1)


if __name__=='__main__':unittest.main()
