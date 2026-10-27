"""Actual fetch/scanner regions, ABI transition and rejection boundaries."""
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_argument_cache as audit
import analyze_a23_argument_cache as m
from workflows.artifacts import verify

class A23ArgumentCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'private/analysis/A23-argument-cache-review-20261014';verify(cls.folder);cls.audit=json.loads((cls.folder/'audit.json').read_text())
        p=audit.ELFS/'dormant';cls.blob=(p/'full.elf').read_bytes();cls.text=(p/'disassembly.txt').read_text();cls.functions,cls.metadata=m.elf.build_functions(cls.blob,cls.text)
    def fetch(self,path='u32',**kwargs):return m.FetchMachine(self.functions,path,**kwargs)

    def test_bound_catalog_has_six_fetch_kinds_and_at_most_eight_arguments(self):
        self.assertEqual(self.audit['linked_format_count'],73);self.assertEqual(self.audit['linked_max_arguments'],8)
        self.assertEqual(self.audit['linked_argument_fetch_kinds'],['d32','s','u32','u64','x32','x64']);self.assertEqual(self.audit['linked_argument_conversions'],97)

    def test_cache_geometry_fills_last_512_bytes_of_local_formatter_frame(self):
        for p in self.audit['profiles'].values():
            c=p['certificate'];self.assertEqual((c['formatter_frame_bytes'],c['cache_base_offset'],c['cache_end_offset']),(1264,752,1264))
            self.assertEqual((c['cache_entries'],c['cache_stride']),(32,16));self.assertEqual(c['cache_base_offset']+c['cache_entries']*c['cache_stride'],c['cache_end_offset'])

    def test_position_slot_is_reused_and_global_zero_invariant_is_rejected(self):
        for p in self.audit['profiles'].values():
            c=p['certificate'];self.assertEqual(c['conversion_position_offset'],136);self.assertEqual(len(c['reused_position_slot_stores']),3)
            self.assertFalse(c['position_slot_global_zero_invariant_valid']);self.assertFalse(c['parser_reaches_injected_state_proven'])

    def test_current_index_profiles_preserve_value_and_counter_under_both_abi_modes(self):
        for p in self.audit['profiles'].values():
            rows=[r for r in p['fetch_profiles'] if r['category']=='catalog-index'];self.assertEqual(len(rows),112)
            for r in rows:
                self.assertFalse(r['get_arg_frontier']);self.assertEqual(r['result'],audit.expected_value(r['path'],r['input_value']))
                self.assertEqual(r['final_cached'],r['index']+1);self.assertEqual(r['next_index'],r['index']+1);self.assertTrue(r['stack_restored'])

    def test_seventh_to_eighth_argument_switches_from_saved_registers_to_stack(self):
        model=self.fetch(index=6);self.assertEqual(model.source,model.top-8);row=model.run();self.assertFalse(row['get_arg_frontier'])
        model=self.fetch(index=7);self.assertEqual(model.source,model.stack_arg);row=model.run();self.assertFalse(row['get_arg_frontier'])

    def test_cache_limit_31_writes_last_slot_but_32_bypasses_cache(self):
        for path in m.PATHS:
            before=self.fetch(path,index=31).run();after=self.fetch(path,index=32).run()
            self.assertEqual(before['final_cached'],32);self.assertEqual(len(before['cache_writes']),1)
            self.assertEqual(after['final_cached'],32);self.assertEqual(after['cache_writes'],[]);self.assertEqual(after['next_index'],33);self.assertFalse(after['get_arg_frontier'])

    def test_positional_cache_miss_reaches_helper_frontier_but_hit_does_not(self):
        for path in m.PATHS:
            self.assertTrue(self.fetch(path,index=0,cached=0,position=True).run()['get_arg_frontier'])
            row=self.fetch(path,index=0,cached=1,position=True).run();self.assertFalse(row['get_arg_frontier']);self.assertEqual(row['cache_writes'],[])

    def test_signed_32bit_values_are_sign_extended_while_unsigned_values_are_not(self):
        for value in (0x7fffffff,0x80000000,0xffffffff):
            signed=self.fetch('d32',value=value).run()['result'];unsigned=self.fetch('u32',value=value).run()['result']
            self.assertEqual(signed,audit.expected_value('d32',value));self.assertEqual(unsigned,value)
        self.assertEqual(self.fetch('d64',value=0x8000000000000000).run()['result'],0x8000000000000000)

    def test_uninitialized_argument_memory_is_rejected(self):
        model=self.fetch();del model.mem[model.source]
        with self.assertRaises(m.ArgumentError):model.run()

    def test_changed_cache_cap_attempts_out_of_bounds_write_and_is_rejected(self):
        model=self.fetch(index=32);pc=next(p for p,(o,a) in model.code.items() if p>model.pc and (o,a)==('cmp','w0, #0x1f'));model.code[pc]=('cmp','w0, #0x3f')
        with self.assertRaises(m.ArgumentError):model.run()

    def test_actual_instruction_byte_drift_is_rejected(self):
        pc=self.audit['profiles']['dormant']['certificate']['cache_count_initialization'];section=next(s for s in self.metadata['sections'] if s['flags']&4 and s['address']<=pc<s['address']+s['size']);blob=bytearray(self.blob);blob[section['offset']+pc-section['address']]^=1
        with self.assertRaises(m.elf.BoundaryError):m.certificate(bytes(blob),self.text)

    def test_numeric_widths_keep_position_mode_off(self):
        for token,width in (('2x',2),('4x',4),('8x',8),('12x',12),('0008x',8)):
            row=m.DecimalMachine(self.functions,token).run();self.assertEqual(row['outcome'],'width');self.assertEqual(row['position'],0);self.assertEqual(row['parsed_number'],width)

    def test_dollar_indices_one_and_thirty_two_are_converted_to_zero_based(self):
        for token,index in (('1$d',0),('32$u',31)):
            row=m.DecimalMachine(self.functions,token).run();self.assertEqual(row['outcome'],'position');self.assertEqual(row['position'],1);self.assertEqual(row['argument_index'],index)
        row=m.DecimalMachine(self.functions,'33$u').run();self.assertEqual(row['outcome'],'rejected-index');self.assertEqual(row['position'],0)

    def test_decimal_unknown_opcode_and_budget_fail_closed(self):
        model=m.DecimalMachine(self.functions,'2x');model.code[model.pc]=('unsupported','')
        with self.assertRaises(m.ArgumentError):model.run()
        with self.assertRaises(m.ArgumentError):m.DecimalMachine(self.functions,'12x').run(budget=1)

    def test_profiles_do_not_claim_full_parser_or_global_get_arg_exclusion(self):
        self.assertEqual((self.audit['instruction_profiles'],self.audit['fetch_profiles'],self.audit['decimal_profiles']),(338,322,16))
        for k in ('parser_reaches_injected_state_proven','get_arg_globally_unreachable_proven','full_parser_executed','get_arg_executed','formatter_cfg_pruned','whole_thread_stack_verified','arm_executed','hardware_verified','root_cause_confirmed'):self.assertFalse(self.audit[k])
        self.assertTrue(self.audit['parser_entry_state_injected'])

    def test_live_sources_tickets_and_old_seals_are_preserved(self):
        a=self.audit
        for n,h in a['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in a['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.ELFS.parent/n),h)
        self.assertEqual(a['sealed_inputs'],[verify(audit.SEALED),verify(audit.ELFS)])
        ticket=json.loads((audit.ELFS.parent/'A23-IOUSBHost-burst-next-test.json').read_text());self.assertEqual(ticket['remaining'],0);self.assertFalse(ticket['acquisition_enabled'])
        for k in ('production_modified','prior_runtime_modified','new_arm_build','firmware_packaged','usb_accessed','sd_accessed'):self.assertFalse(a[k])

if __name__=='__main__':unittest.main()
