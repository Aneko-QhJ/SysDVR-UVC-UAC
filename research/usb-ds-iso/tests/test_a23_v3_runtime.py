"""Final V3 static layout and exact logger body; no device execution."""
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_v3_runtime as audit


class V3RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name).resolve();cls.review=cls.base/'review'
        cls.result=audit.run(cls.review)
        cls.cert=json.loads((cls.review/'certificate.json').read_text())
        cls.models=json.loads((cls.review/'logger-models.json').read_text())
        cls.graph=json.loads((cls.review/'reachability.json').read_text())

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def clone(self):
        folder=Path(tempfile.mkdtemp(dir=self.base))
        for n in ('full.elf','symbols.txt','disassembly.txt','recipe.json'):
            shutil.copyfile(audit.DEVICE/'window-30s'/n,folder/n)
        return folder

    def test_worker_backing_does_not_equal_usable_stack(self):
        for name,total,initial,entry in (('video',20480,19840,19792),('audio',12288,11648,11600)):
            row=self.cert['workers'][name]
            self.assertEqual((row['backing_array_bytes'],row['initial_sp_offset'],row['user_entry_remaining_bytes']),(total,initial,entry))
            self.assertEqual(row['tls_offset'],initial+48)
            self.assertEqual(row['reent_offset'],row['tls_offset']+16)
            self.assertEqual(row['reent_offset']+576,total)
            self.assertEqual(row['thread_stack_sz_field'],initial)

    def test_machine_operand_change_cannot_keep_the_certificate(self):
        for before,after in (('add\tx0, x3, #0x23f','add\tx0, x3, #0x24f'),
                             ('str\tx1, [x20, #112]','str\tx1, [x20, #120]'),
                             ('mov\tw4, #0x5000','mov\tw4, #0x6000')):
            with self.subTest(before=before):
                folder=self.clone();p=folder/'disassembly.txt';text=p.read_text();self.assertIn(before,text)
                p.write_text(text.replace(before,after,1))
                with self.assertRaises(ValueError):audit.certificate(folder)

    def test_getreent_got_target_change_is_rejected(self):
        folder=self.clone();elf=audit.Elf(folder/'full.elf');data=bytearray(elf.raw)
        section=next(s for s in elf.sections if s[1]!=8 and s[3]<=0x274e0<s[3]+s[5])
        struct.pack_into('<Q',data,section[4]+0x274e0-section[3],0)
        (folder/'full.elf').write_bytes(data)
        with self.assertRaises(AssertionError):audit.certificate(folder)

    def test_main_and_worker_tls_paths_are_static_evidence_only(self):
        self.assertTrue(self.cert['main_newlib_setup_before_app_init'])
        self.assertTrue(self.cert['worker_reent_install_before_user_entry'])
        self.assertTrue(self.cert['child_standard_stream_pointers_inherited'])
        self.assertTrue(self.cert['thread_exit_tls_destructor_indirect'])
        self.assertFalse(self.cert['direct_reclaim_reent_call_present'])
        self.assertFalse(self.cert['all_reent_allocations_reclaimed_verified'])
        self.assertFalse(self.cert['tls_runtime_integrity_verified'])
        self.assertTrue(self.result['abi_static_assertions_compiled'])

    def test_three_threads_reach_logger_but_graph_has_no_stack_bound(self):
        for name,own in (('main',112),('VideoStreamThread',160),('AudioStreamThread',80)):
            row=self.graph['roots'][name];self.assertEqual(row['own_frame_bytes'],own)
            self.assertTrue(row['logger_direct_path']);self.assertGreater(row['unresolved_count'],0)
            self.assertIsNone(row['stack_bound_bytes'])
        self.assertFalse(self.graph['old_formatter_certificate_reused'])
        self.assertFalse(self.graph['stack_bound_verified'])

    def test_file_branch_is_extracted_verbatim(self):
        core=(audit.DEVICE/'window-30s/source/core.c').read_text()
        template=(ROOT/'tests/a23_v3_logger_fixture.c').read_text();rendered,body=audit.logger_source(core,template)
        self.assertIn(body,core);self.assertIn(body,rendered);self.assertIn('FsWriteOption_Flush',body)
        self.assertNotIn('sendto',body);self.assertNotIn('mutex',body)
        self.assertEqual(self.result['logger_body_sha256'],audit.storage.sha(body.encode()))

    def test_per_command_serialization_allows_different_service_outcomes(self):
        offset=self.models['offset'];append=self.models['append'];busy=self.models['busy']
        self.assertEqual(offset['offsets'],[0,0]);self.assertEqual(append['offsets'],[0,0])
        self.assertEqual((offset['writes'],offset['file_bytes']),(2,4))
        self.assertEqual((append['writes'],append['file_bytes']),(2,8))
        self.assertEqual((busy['opens'],busy['writes'],busy['closes']),(2,1,1))
        self.assertFalse(self.cert['fs_service_open_sharing_semantics_verified'])
        self.assertFalse(self.cert['fs_service_append_semantics_verified'])

    def test_file_failures_do_not_create_an_acknowledgement(self):
        expected={'open-failure':(1,0,0,0),'size-failure':(1,1,0,1),'write-failure':(1,1,1,1)}
        for name,counts in expected.items():
            row=self.models[name];self.assertEqual(tuple(row[k] for k in ('opens','sizes','writes','closes')),counts)
            self.assertEqual(row['file_bytes'],0)
        self.assertEqual(self.models['unmounted']['format_calls'],0)
        for name in ('empty','format-failure'):self.assertEqual(self.models[name]['opens'],0)

    def test_truncation_and_embedded_nul_preserve_reported_byte_length(self):
        for n in (1,510,511,512,2048):self.assertEqual(self.models['length-'+str(n)]['file_bytes'],min(n,511))
        self.assertEqual(self.models['binary']['file_bytes'],2)
        self.assertEqual(self.result['native_cases'],16)

    def test_old_sources_production_tickets_and_seals_remain_unchanged(self):
        for name,h in self.result['source_hashes'].items():self.assertEqual(audit.sha(audit.REPO/name),h)
        for name,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.sha(audit.REPO/name),h)
        for name,h in self.result['tickets_sha256'].items():self.assertEqual(audit.sha(audit.PARENT.parent/name),h)
        for entry in self.result['sealed_inputs']:audit.verify(entry['folder'])
        audit.verify(self.review)

    def test_no_runtime_or_hardware_authority(self):
        for flag in ('real_concurrency_verified','tls_runtime_integrity_verified','whole_thread_stack_verified',
                     'synchronous_log_latency_bound_verified','full_formatter_replayed_on_new_elf',
                     'device_candidate_modified','new_device_elf_built','arm_executed','attempt_issued',
                     'hardware_verified','root_cause_confirmed'):
            self.assertIs(self.result[flag],False)
        for name in ('native_sdk_calls','usb_requests','sd_accesses'):self.assertEqual(self.result[name],0)
        self.assertTrue(all(r['mock_fs_only'] and not r['real_concurrency_verified'] for r in self.models.values()))

    def test_parent_recipe_is_not_the_linked_execution_recipe(self):
        ids=self.result['recipe_identities']
        self.assertEqual(ids['parent_input_digest'],ids['receiver_record_recipe_sha256'])
        self.assertEqual(ids['runtime_input_digest'],self.cert['recipe_sha256'])
        self.assertNotEqual(ids['parent_input_digest'],ids['runtime_input_digest'])
        self.assertEqual(len(ids['linked_recipe_addresses']),2)
        self.assertTrue(ids['linked_recipe_bytes_verified'])
        self.assertFalse(ids['use_receiver_record_as_expected_execution_recipe_valid'])
        self.assertFalse(ids['receiver_capture_failure_proven'])


if __name__=='__main__':unittest.main()
