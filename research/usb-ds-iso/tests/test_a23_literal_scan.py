"""Initialization/scanner state continuity, TLS rejection and FILE alias boundaries."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_literal_scan as audit
import analyze_a23_literal_scan as m
from workflows.artifacts import verify


class LiteralScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verify(audit.ELFS);verify(audit.SEALED)
        folder=audit.ELFS/'dormant'
        cls.blob=(folder/'full.elf').read_bytes();cls.text=(folder/'disassembly.txt').read_text()
        cls.catalog=json.loads((audit.SEALED/'linked-catalog.json').read_text())
        cls.fs,cls.meta,cls.binding,cls.literals=audit.build_inputs(cls.blob,cls.text,cls.catalog)

    def model(self,format_text='grcdServiceBegin: 0x%x\n',**kwargs):
        return m.FirstScanMachine(self.fs,self.blob,self.meta,self.literals[format_text],**kwargs)

    def test_wrapper_builds_file_and_va_copy_before_formatter(self):
        model=self.model();row=model.run_first();file=row['file_initialization']
        self.assertEqual(file['address'],model.wrapper_sp+72)
        self.assertEqual((file['flags'],file['remaining']),(0x208,511))
        self.assertEqual(file['va_pointer'],model.wrapper_sp+32)
        self.assertNotEqual(row['parser_state']['va_pointer'],model.va)

    def test_actual_initialization_sets_first_index_and_cache_without_entry_reinjection(self):
        row=self.model().run_first()
        self.assertEqual((row['parser_state']['index'],row['parser_state']['cached'],row['parser_state']['position']),(0,0,0))
        self.assertEqual((row['fetch']['final_cached'],row['fetch']['next_index']),(1,1))
        self.assertFalse(row['index_cache_and_file_state_injected']);self.assertFalse(row['percent_pointer_injected'])
        self.assertFalse(row['fetch_state_reinjected'])

    def test_ascii_callback_scans_to_real_percent_and_leaves_file_fields_untouched(self):
        model=self.model();row=model.run_first()
        self.assertEqual(row['parser_state']['percent_offset'],20)
        self.assertEqual(len(row['callbacks']),21)
        self.assertEqual(row['callbacks'][-1]['byte'],ord('%'))
        for c in row['callbacks']:
            self.assertEqual((c['output_pointer'],c['state_pointer']),(model.sp+316,model.sp+344))
            self.assertEqual(c['state'],0)
            self.assertEqual([w['address'] for w in c['writes']],[model.sp+344,model.sp+316])

    def test_tls_getter_and_locale_helpers_are_actual_instruction_calls(self):
        row=self.model().run_first();names={c['name'] for c in row['calls']}
        self.assertTrue({'__getreent','__syscall_getreent','_localeconv_r','__locale_mb_cur_max','__utf8_mbtowc'}<=names)
        self.assertTrue(row['architectural_tls_and_reent_injected'])
        self.assertFalse(row['actual_sdk_memory_helpers_executed'])
        modeled=[c for c in row['calls'] if c.get('modeled')]
        self.assertTrue(modeled)
        for call in modeled:self.assertEqual(call['link_register_after_model'],call['at']+4)

    def test_bad_tls_magic_stops_at_diagnostic_frontier(self):
        with self.assertRaisesRegex(m.ScanError,'diagAbortWithResult'): self.model(tls_magic=0).run_first()

    def test_nonnull_unmapped_thread_locale_is_not_treated_as_default(self):
        with self.assertRaisesRegex(m.ScanError,'Uninitialized scan memory'): self.model(thread_locale=0x620000).run_first()

    def test_nonnull_locale_with_unknown_callback_is_rejected(self):
        model=self.model(thread_locale=0x620000)
        raw=m.parser.fmt.data_at(self.blob,self.meta,self.meta['locale']['global_locale_address'],656)
        for i,v in enumerate(raw): model.store(0x620000+i,v,1)
        model.store(0x620000+464,0,8)
        with self.assertRaisesRegex(m.ScanError,'Unknown locale callback'): model.run_first()

    def test_zero_one_and_full_capacity_preserve_literal_length_and_termination(self):
        text='Capture initialized\n'
        for capacity,stored in ((0,0),(1,0),(512,20)):
            row=self.model(text,capacity=capacity).run_first()
            self.assertEqual(row['outcome'],'literal-only-return');self.assertEqual(row['return_value'],20)
            self.assertEqual(row['stored_bytes'],stored);self.assertTrue(row['stack_restored'])
            if capacity:self.assertEqual(row['output'][stored],0)

    def test_first_fetch_handles_register_and_stack_arguments(self):
        for abi in ('register','stack'):
            row=self.model(abi=abi,value=0xffffffff).run_first()
            self.assertEqual(row['fetch']['result'],0xffffffff)
            self.assertTrue(row['fetch']['stack_held_unchanged'])

    def test_invalid_file_growth_flag_reaches_growth_frontier(self):
        model=self.model('Capture initialized\n',capacity=1)
        pc=next(pc for pc,(op,a) in model.code.items() if op=='mov' and a=='w1, #0xffff0208')
        model.code[pc]=('mov','w1, #0xffff0608')
        with self.assertRaisesRegex(m.ScanError,'FILE growth frontier'): model.run_first()

    def test_budget_and_missing_tls_storage_fail_closed(self):
        with self.assertRaisesRegex(m.ScanError,'budget'): self.model().run_first(budget=1)
        model=self.model();del model.mem[model.tls+480]
        with self.assertRaisesRegex(m.ScanError,'Uninitialized'): model.run_first()

    def test_actual_utf8_instruction_drift_fails_elf_binding(self):
        pc=self.meta['locale']['initial_callback_target'];section=next(s for s in self.meta['sections'] if s['flags']&4 and s['address']<=pc<s['address']+s['size'])
        blob=bytearray(self.blob);blob[section['offset']+pc-section['address']]^=1
        with self.assertRaises(m.parser.arg.elf.BoundaryError): audit.build_inputs(bytes(blob),self.text,self.catalog)

    def test_original_va_list_and_file_flags_are_preserved_after_fetch(self):
        model=self.model();row=model.run_first()
        self.assertEqual(model.load(model.va+24,4),(-56)&0xffffffff)
        self.assertEqual(model.load(model.wrapper_sp+32+24,4),(-48)&0xffffffff)
        self.assertEqual(model.load(model.file+16,2),0x208)
        self.assertFalse(row['whole_thread_stack_verified']);self.assertFalse(row['get_arg_globally_unreachable_proven'])

    def test_all_bound_formats_reach_correct_first_fetch_or_literal_return(self):
        for item in self.catalog:
            row=self.model(item['format']).run_first()
            self.assertEqual(row['outcome'],'first-fetch' if item['conversions'] else 'literal-only-return')
        self.assertEqual(sum(bool(x['conversions']) for x in self.catalog),50)


if __name__=='__main__': unittest.main()
