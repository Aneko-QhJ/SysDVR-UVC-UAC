"""Full current format paths, native byte oracle and state continuity boundaries."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_format_loop as audit
import analyze_a23_format_loop as m
from workflows.artifacts import verify


class FormatLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verify(audit.SEALED);verify(audit.ELFS)
        p=audit.ELFS/'dormant';cls.blob=(p/'full.elf').read_bytes();cls.text=(p/'disassembly.txt').read_text()
        cls.catalog=json.loads((audit.SEALED/'linked-catalog.json').read_text())
        cls.fs,cls.meta,_,cls.literals=audit.prior.build_inputs(cls.blob,cls.text,cls.catalog);cls.oracle=audit.NativeOracle()

    def item(self,predicate=lambda r:len(r['conversions'])==8):return next(r for r in self.catalog if predicate(r))

    def model(self,item=None,scenario='limits',values=None,capacity=512,abi='register'):
        item=self.item() if item is None else item
        return m.FormatMachine(self.fs,self.blob,self.meta,self.literals[item['format']],
            audit.values_for(item,scenario) if values is None else values,capacity=capacity,abi=abi)

    def check(self,item,scenario='limits',values=None,capacity=512,abi='register'):
        values=audit.values_for(item,scenario) if values is None else values
        machine=self.model(item,values=values,capacity=capacity,abi=abi);row=machine.run_full()
        required,text=self.oracle.format(item,values)
        audit.check_result(machine,row,item,values,required,text,abi,capacity)
        return machine,row

    def test_all_73_complete_outputs_match_independent_typed_native_printf(self):
        for item in self.catalog:self.check(item)

    def test_eight_actual_fetches_and_scan_entries_advance_without_reinjection(self):
        _,row=self.check(self.item())
        self.assertEqual([r['index'] for r in row['fetches']],list(range(8)))
        self.assertEqual([r['index'] for r in row['scan_entries']],list(range(9)))
        self.assertEqual([r['cached'] for r in row['scan_entries']],list(range(9)))
        self.assertFalse(row['index_cache_percent_and_file_state_reinjected'])

    def test_seventh_to_eighth_abi_boundary_and_original_va_preservation(self):
        for abi in ('register','stack'):
            machine,row=self.check(self.item(),abi=abi)
            self.assertEqual(row['copied_stack_pointer'],machine.stack_arg+(8 if abi=='register' else 64))
            self.assertEqual(machine.load(machine.va,8),machine.stack_arg)

    def test_zero_one_32_and_512_capacity_use_same_required_length(self):
        item=self.item();lengths=[]
        for capacity in audit.CAPACITIES:
            _,row=self.check(item,capacity=capacity);lengths.append(row['return_value'])
        self.assertEqual(len(set(lengths)),1)

    def test_signed_min_max_minus_one_and_zero_match_decimal_native_output(self):
        item=self.item(lambda r:any(c['kind']=='d' for c in r['conversions']))
        index=next(i for i,c in enumerate(item['conversions']) if c['kind']=='d')
        for value in (-2147483648,-1,0,2147483647):
            values=audit.values_for(item,'mixed');values[index]=value;self.check(item,values=values)

    def test_unsigned_64_max_decimal_and_hex_are_rendered_as_full_values(self):
        for kind in ('u','x'):
            item=self.item(lambda r:any(c['kind']==kind and c['length']=='ll' for c in r['conversions']))
            self.check(item)

    def test_current_narrow_strings_include_percent_without_reparsing(self):
        item=self.item(lambda r:any(c['kind']=='s' and c['argument']=='g_serialNumber' for c in r['conversions']))
        _,row=self.check(item,scenario='mixed')
        self.assertEqual(len(row['fetches']),len(item['conversions']))
        self.assertIn(ord('%'),row['output'][:row['stored_bytes']])

    def test_decimal_wide_slot_reuse_is_observed_then_reset_before_next_fetch(self):
        _,row=self.check(self.item())
        wide=[e for e in row['slot_events'] if e['kind']=='write' and e['bytes']>=8]
        self.assertTrue(wide)
        self.assertTrue(all(r['position']==0 for r in row['fetches']))
        self.assertEqual(len(row['resets']),8)

    def test_vector_flushes_and_output_capacity_exhaustion_preserve_flags(self):
        _,row=self.check(self.item(),capacity=32)
        self.assertGreater(len(row['vector_flushes']),1)
        self.assertEqual(row['final_file_flags'],0x208)
        self.assertEqual(row['remaining'],0)

    def test_position_reset_fault_reaches_unexecuted_helper_frontier(self):
        machine=self.model();pc=machine.start+0x1fc;self.assertEqual(machine.code[pc],('mov','w3, #0x0'))
        machine.code[pc]=('mov','w3, #0x1')
        with self.assertRaisesRegex(m.LoopError,'get_arg frontier'):machine.run_full()

    def test_missing_eighth_argument_memory_fails_closed(self):
        machine=self.model();del machine.mem[machine.stack_arg]
        with self.assertRaisesRegex(m.scan.ScanError,'Uninitialized'):machine.run_full()

    def test_unknown_opcode_and_instruction_budget_fail_closed(self):
        machine=self.model();machine.code[machine.pc]=('unsupported','')
        with self.assertRaises(m.scan.parser.BridgeError):machine.run_full()
        with self.assertRaisesRegex(m.LoopError,'budget'):self.model().run_full(budget=1)

    def test_rendering_instruction_byte_drift_is_rejected(self):
        pc=self.meta['dispatch']['formatter_start']+0x2aa4
        section=next(s for s in self.meta['sections'] if s['flags']&4 and s['address']<=pc<s['address']+s['size'])
        blob=bytearray(self.blob);blob[section['offset']+pc-section['address']]^=1
        with self.assertRaises(m.scan.parser.arg.elf.BoundaryError):audit.prior.build_inputs(bytes(blob),self.text,self.catalog)

    def test_changed_numeric_rendering_is_detected_by_native_oracle(self):
        item=self.item(lambda r:r['format']=='grcdServiceBegin: 0x%x\n');machine=self.model(item)
        pc=machine.start+0x2aac;self.assertEqual(machine.code[pc],('lsr','x1, x1, #4'))
        machine.code[pc]=('lsr','x1, x1, #5');row=machine.run_full()
        _,text=self.oracle.format(item,audit.values_for(item,'limits'))
        self.assertNotEqual(bytes(row['output'][:row['stored_bytes']]),text)

    def test_offline_limits_remain_explicit_and_prior_seals_are_preserved(self):
        _,row=self.check(self.item())
        self.assertTrue(row['formatter_conversion_loop_executed_in_model'])
        for key in ('actual_sdk_memory_helpers_executed','whole_thread_stack_verified','get_arg_globally_unreachable_proven','formatter_cfg_pruned'):self.assertFalse(row[key])
        verify(audit.SEALED);verify(audit.ELFS)
        ticket=json.loads((audit.ELFS.parent/'A23-IOUSBHost-burst-next-test.json').read_text())
        self.assertEqual(ticket['remaining'],0);self.assertFalse(ticket['acquisition_enabled'])


if __name__=='__main__':unittest.main()
