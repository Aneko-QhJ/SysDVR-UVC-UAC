"""Actual host publication races, cooperative interruptions and ELF SP gaps."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_session_concurrency as audit
import analyze_a23_session_stack as stack
from analyze_ep0_session import decode_session
from workflows.artifacts import verify

class A23SessionConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output)
        cls.rows={(r['sanitizer'],r['case']):r for r in cls.result['runtime_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def row(self,name,sanitizer='thread'):return self.rows[sanitizer,name]
    def sample(self,name,sanitizer='thread'):return decode_session((self.output/sanitizer/('publish-'+name+'.bin')).read_bytes())

    def test_two_publishers_have_one_winner_per_object_under_both_sanitizers(self):
        for name,p in self.result['policy'].items():
            self.assertTrue(p['passed']);self.assertEqual(p['cases'],10);self.assertEqual(p['cpu_threads_per_race'],3)
            self.assertEqual((p['context_objects'],p['context_winners'],p['receipt_objects'],p['receipt_winners']),(32,32,32,32))
            self.assertGreaterEqual(p['context_reads'],32);self.assertGreaterEqual(p['receipt_reads'],32)
            self.assertGreaterEqual(p['unbound_reads'],32);self.assertGreaterEqual(p['unpublished_receipt_reads'],32)

    def test_final_publications_have_coherent_context_and_receipt_values(self):
        for sanitizer in self.result['policy']:
            for i in range(32):
                d=self.sample('context-'+str(i),sanitizer);w=d['ep0_writer'];self.assertIn(w,(11,12))
                self.assertEqual(bytes.fromhex(d['boot_id_hex'])[0],w-10);self.assertEqual(bytes.fromhex(d['session_id_hex'])[0],w-9)
                s=self.sample('receipt-'+str(i),sanitizer)['sink'];self.assertTrue(s['input_crc_matched'])
                self.assertIn((s['phase'],s['result'],s['commit_acknowledged']),((9,0,True),(8,98,False)))

    def test_pre_release_and_interrupted_core_context_stays_unbound(self):
        for name in ('context-before-release','context-interrupted'):
            d=self.sample(name);self.assertFalse(d['context_present']);self.assertIsNone(d['boot_id_hex']);self.assertIsNone(d['diagnostic'])
        self.assertEqual(self.result['policy']['thread']['interrupted_phase'],1)
        self.assertTrue(self.result['policy']['thread']['poison_bypasses_passed'])

    def test_pre_release_and_interrupted_receipt_is_omitted(self):
        for name in ('receipt-before-release','receipt-interrupted'):
            d=self.sample(name);self.assertEqual(d['mode'],'startup_and_ep0');self.assertIsNone(d['sink'])
        for p in self.result['policy'].values():self.assertTrue(p['owner_immutable'])

    def test_runtime_busy_capture_has_no_early_bytes_and_publishes_once(self):
        for sanitizer in self.result['policy']:
            r=self.row('capture-busy',sanitizer);self.assertEqual((r['phase'],r['winners'],r['bytes']),(2,1,320))
            self.assertEqual((r['owner_reads'],r['receipt_reads']),(0,0));self.assertTrue(r['immutable_output'])

    def test_interrupted_runtime_capture_stays_unpublished_and_cannot_retry(self):
        r=self.row('capture-interrupted');self.assertEqual((r['phase'],r['winners'],r['bytes']),(1,0,0))
        self.assertNotIn('session',r);self.assertEqual(r['owner_reads'],0)

    def test_rejected_capture_stays_rejected_without_fabricated_metadata(self):
        r=self.row('capture-rejected');self.assertEqual((r['phase'],r['bytes']),(3,0));self.assertNotIn('session',r)

    def test_failed_join_and_incomplete_context_bypass_poison_getters(self):
        for name,reason in (('failed-join',1),('context-publishing',2)):
            r=self.row(name);self.assertEqual(r['session']['fallback_reason'],reason)
            self.assertEqual((r['owner_reads'],r['receipt_reads']),(0,0));self.assertIsNone(r['session']['diagnostic'])

    def test_receipt_publishing_and_nonreturned_do_not_imply_save_success(self):
        for name in ('receipt-publishing','nonreturned-receipt'):
            r=self.row(name);self.assertEqual(r['session']['mode'],'startup_and_ep0');self.assertIsNone(r['session']['sink'])
        self.assertEqual(self.row('receipt-publishing')['receipt_phase'],1);self.assertEqual(self.row('nonreturned-receipt')['receipt_reads'],0)

    def test_competing_runtime_captures_publish_one_immutable_result(self):
        r=self.row('full-race');self.assertEqual((r['winners'],r['phase'],r['owner_reads'],r['receipt_reads']),(1,2,1,1))
        self.assertTrue(r['session']['sink']['commit_acknowledged']);self.assertEqual(r['bytes'],576)

    def test_startup_snapshot_during_binding_and_before_binding_cannot_upgrade(self):
        for name in ('startup-during-bind','pre-bind-snapshot'):
            r=self.row(name);self.assertEqual(r['session']['mode'],'startup_only');self.assertEqual(r['owner_reads'],0)
        self.assertFalse(self.row('pre-bind-snapshot')['session']['context_present'])
        r=self.row('failed-bind');self.assertEqual((r['identity_queries'],r['bytes']),(0,192));self.assertEqual(r['session']['startup_status'],0)

    def test_complete_direct_capture_graph_has_352_byte_bound_in_both_elves(self):
        for label,r in self.result['stack_analysis'].items():
            for name in ('session_capture','Ep0SessionStartupOnly','Ep0SessionJoined'):
                row=r['roots'][name];self.assertTrue(row['closed_direct_graph']);self.assertEqual(row['stack_bound_bytes'],352)
            self.assertFalse(r['whole_thread_stack_verified']);self.assertFalse(r['runtime_peak_measured'])

    def test_dynamic_or_indirect_calls_and_recursive_graphs_never_get_bounds(self):
        for r in self.result['stack_analysis'].values():
            self.assertIsNone(r['roots']['Ep0SessionSaveJoined']['stack_bound_bytes'])
            self.assertTrue(any('_svfprintf_r' in s and 'indirect' in s for s in r['roots']['Ep0SessionSaveJoined']['unresolved']))
            self.assertTrue(any('waitObjects' in s and 'nonconstant SP' in s for s in r['roots']['VideoStreamThread']['unresolved']))
        text='00000010 <root>:\n 10: d10043ff sub sp, sp, #0x10\n 14: 94000000 bl 10 <root>\n 18: 910043ff add sp, sp, #0x10\n 1c: d65f03c0 ret\n'
        with patch.object(stack,'ROOTS',('root',)):
            r=stack.analyze(text,[dict(function='root',bytes=16,kind='static')])
        self.assertIsNone(r['roots']['root']['stack_bound_bytes']);self.assertTrue(any('recursive' in s for s in r['roots']['root']['unresolved']))
        duplicate='00000010 <root>:\n 10: d10043ff sub sp, sp, #0x10\n 14: 94000000 bl 30 <helper>\n 18: 910043ff add sp, sp, #0x10\n 1c: d65f03c0 ret\n00000030 <helper>:\n 30: d65f03c0 ret\n00000040 <helper>:\n 40: d10043ff sub sp, sp, #0x10\n 44: 910043ff add sp, sp, #0x10\n 48: d65f03c0 ret\n'
        with patch.object(stack,'ROOTS',('root',)):r=stack.analyze(duplicate,[])
        self.assertEqual(r['roots']['root']['stack_bound_bytes'],16);self.assertIn('helper@30',r['functions']);self.assertNotIn('helper@40',r['functions'])
        f=stack.parse_disassembly(text);r=stack.frame(f[16],f,32)
        self.assertIsNone(r['frame_bytes']);self.assertTrue(any('disagreement' in s for s in r['unresolved']))

    def test_sources_seals_tickets_and_nonhardware_boundaries(self):
        for p in (self.output,audit.SEALED):self.assertTrue(verify(p))
        old=json.loads((audit.SEALED/'audit.json').read_text())
        for label,r in self.result['stack_analysis'].items():self.assertEqual(r['elf_sha256'],old['builds'][label]['elf_sha256'])
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.candidate.startup.startup.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n),h)
        self.assertEqual(self.result['native_cases_per_sanitizer'],21);self.assertEqual(self.result['native_sanitizer_runs'],42)
        for key in ('runtime_modified','production_modified','prior_evidence_modified','old_wire_modified','new_full_arm_elf_built',
                    'arm_executed','firmware_packaged','usb_accessed','sd_accessed','hardware_verified','root_cause_confirmed','source_authenticated','cleanup_authorized','whole_thread_stack_verified','runtime_peak_measured','actual_switch_threads_executed'):self.assertFalse(self.result[key])
        self.assertTrue(self.result['actual_host_pthreads']);self.assertTrue(self.result['cooperative_host_interruption_only'])
        for row in self.result['runtime_cases']:
            self.assertTrue(row['passed']);self.assertEqual((row['usb_calls'],row['fs_calls']),(0,0))

if __name__=='__main__':unittest.main()
