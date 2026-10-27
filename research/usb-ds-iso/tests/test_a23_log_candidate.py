"""Sealed full logger candidate and adversarial machine-contract checks."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_log_candidate as m
from workflows.artifacts import verify

class A23LogCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review=ROOT/'private/analysis/A23-log-candidate-review-20261014'
        verify(cls.review);cls.audit=json.loads((cls.review/'audit.json').read_text())
        cls.original=json.loads((m.SEALED/'audit.json').read_text())

    def test_both_configurations_have_fresh_recipes_and_thirteen_linked_objects(self):
        recipes=[]
        for label,row in self.audit['builds'].items():
            self.assertEqual(row['object_count'],13);self.assertTrue(row['linked']);self.assertFalse(row['executed'])
            self.assertEqual(row['strict_format_units'],13);self.assertNotEqual(row['runtime_recipe_digest'],self.original['builds'][label]['runtime_recipe_digest'])
            self.assertEqual(m.base.ep0.sha(self.review/label/'full.elf'),row['elf_sha256']);recipes.append(row['runtime_recipe_digest'])
        self.assertNotEqual(*recipes)

    def test_only_three_fix_files_and_recipe_change_from_old_candidate(self):
        for label in self.audit['builds']:
            before=m.SEALED/label/'source';after=self.review/label/'source';changes=[]
            self.assertEqual({p.relative_to(before) for p in before.rglob('*') if p.is_file()},{p.relative_to(after) for p in after.rglob('*') if p.is_file()})
            for p in before.rglob('*'):
                if p.is_file() and p.read_bytes()!=(after/p.relative_to(before)).read_bytes():changes.append(p.relative_to(before).as_posix())
            self.assertEqual(sorted(changes),['core.c','core.h','uvc/ep0_candidate_recipe.h','uvc/uvc_device.c'])
            self.assertIn(m.logs.logger_source(True),(after/'core.c').read_text())

    def test_91_original_results_and_limits_are_preserved(self):
        for key in ('startup_cases','shutdown_cases','file_cases'):
            def raw(rows):return {r['case']:{k:v for k,v in r.items() if k not in ('session','disk_session','startup_journal')} for r in rows}
            self.assertEqual(raw(self.original[key]),raw(self.audit[key]))
        self.assertEqual(self.audit['limit_policy'],self.original['limit_policy']);self.assertEqual(self.audit['native_legacy_cases'],91)
        self.assertEqual([len(self.audit[k]) for k in ('startup_cases','shutdown_cases','file_cases')],[45,20,20])

    def test_final_machine_clamp_is_bound_to_elf_and_keeps_832_frame(self):
        for label,row in self.audit['builds'].items():
            p=self.review/label;actual=m.clamp_machine((p/'full.elf').read_bytes(),(p/'disassembly.txt').read_text())
            self.assertEqual(actual,row['logger_machine']);self.assertEqual(actual['max_write_bytes'],511);self.assertEqual(actual['logger_frame_bytes'],832)
            self.assertTrue(actual['nonpositive_returns_skip_filesystem']);self.assertTrue(actual['write_uses_signed_min_511'])

    def test_machine_rejects_altered_limit_selection_and_length_register(self):
        p=self.review/'dormant';blob=(p/'full.elf').read_bytes();text=(p/'disassembly.txt').read_text()
        start=text.index('<LogFunctionImpl>:');end=text.index('\n\n',start);body=text[start:end]
        for a,b in (('cmp\tw4, #0x1ff','cmp\tw4, #0x200'),('csel\tw3, w4, w3, le','csel\tw3, w4, w3, gt'),('sxtw\tx3, w3','sxtw\tx3, w4')):
            self.assertEqual(body.count(a),1)
            with self.assertRaises((AssertionError,m.boundaries.BoundaryError)):m.clamp_machine(blob,text[:start]+body.replace(a,b)+text[end:])

    def test_machine_rejects_changed_instruction_bytes(self):
        p=self.review/'dormant';blob=bytearray((p/'full.elf').read_bytes());text=(p/'disassembly.txt').read_text()
        _,meta=m.boundaries.build_functions(bytes(blob),text);pc=self.audit['builds']['dormant']['logger_machine']['clamp_instruction_addresses'][0]
        section=next(s for s in meta['sections'] if s['address']<=pc<s['address']+s['size'] and s['flags']&4)
        blob[section['offset']+pc-section['address']]^=1
        with self.assertRaises(m.boundaries.BoundaryError):m.clamp_machine(bytes(blob),text)

    def test_long_logs_are_capped_but_size_error_behavior_is_retained(self):
        n=self.audit['native_log_checks'];self.assertEqual(n['total_checks'],250)
        rows={(r['scenario'],r['input_length']):r for r in n['edges'] if r['control']}
        for length in (511,512,513,1024):
            row=rows['length',length];self.assertEqual(row['requested'],511);self.assertFalse(row['contains_nul']);self.assertFalse(row['span_exceeds_buffer'])
        row=rows['size-error',7];self.assertEqual((row['writes'],row['write_offset'],row['closes']),(1,0,1))
        self.assertTrue(self.audit['logger_native_uses_exact_candidate_body']);self.assertTrue(self.audit['startup_harness_log_is_noop'])

    def test_save_stack_remains_closed_and_wait_profiles_remain_conditional(self):
        for label,data in self.audit['stack_analysis'].items():
            root=data['roots']['Ep0SessionSaveJoined'];self.assertTrue(root['closed_direct_graph']);self.assertEqual(root['stack_bound_bytes'],768)
            self.assertEqual(data['roots']['session_capture']['stack_bound_bytes'],352);self.assertFalse(data['whole_thread_stack_verified'])
            self.assertEqual(self.audit['wait_audit'][label]['model']['profile_count'],156)
            cert=json.loads((self.review/label/'wait-site-certificate.json').read_text());self.assertEqual(len(cert['three_event_profiles']),32)
            self.assertFalse(cert['full_symbolic_proof']);self.assertFalse(cert['termination_bound_verified'])

    def test_live_production_and_ticket_hashes_match_without_acquisition(self):
        for n,h in self.audit['production_sources_sha256'].items():self.assertEqual(m.base.ep0.sha(m.logs.REPO/n),h)
        for n,h in self.audit['tickets_sha256'].items():self.assertEqual(m.base.ep0.sha(m.SEALED.parent/n),h)
        ticket=json.loads((m.SEALED.parent/'A23-IOUSBHost-burst-next-test.json').read_text());self.assertEqual(ticket['remaining'],0);self.assertFalse(ticket['acquisition_enabled'])
        for k in ('arm_executed','firmware_packaged','usb_accessed','sd_accessed','whole_thread_stack_verified','root_cause_confirmed','hardware_verified','production_modified'):self.assertFalse(self.audit[k])

if __name__=='__main__':unittest.main()
