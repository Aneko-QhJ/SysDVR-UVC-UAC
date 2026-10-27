"""Continuous new-ELF formatter/helper state, typed output oracle and mapped-memory rejection."""
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import audit_a23_integrated_memory as audit
import analyze_a23_integrated_memory as m
from workflows.artifacts import verify


class IntegratedMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verify(audit.ELFS)
        p = audit.ELFS/'dormant'
        cls.blob, cls.text = (p/'full.elf').read_bytes(), (p/'disassembly.txt').read_text()
        cls.catalog = json.loads((audit.SEALED/'linked-catalog.json').read_text())
        cls.fs, cls.meta, cls.binding, cls.literals = audit.formats.prior.build_inputs(cls.blob, cls.text, cls.catalog)
        cls.oracle = audit.formats.NativeOracle()

    def item(self, predicate=lambda r: len(r['conversions']) == 8):
        return next(r for r in self.catalog if predicate(r))

    def machine(self, item=None, scenario='limits', **kwargs):
        item = item or self.item()
        return m.IntegratedMachine(self.fs, self.blob, self.meta, self.literals[item['format']],
                                   audit.formats.values_for(item, scenario), **kwargs)

    def check(self, item=None, scenario='limits', capacity=512, abi='register', **kwargs):
        item = item or self.item()
        machine = self.machine(item, scenario=scenario, capacity=capacity, abi=abi, **kwargs)
        row = machine.run_full()
        values = audit.formats.values_for(item, scenario)
        required, text = self.oracle.format(item, values)
        audit.formats.check_result(machine, row, item, values, required, text, abi, capacity)
        return machine, row

    def serial(self):
        return self.item(lambda r: any(c['kind'] == 's' and c['argument'] == 'g_serialNumber' for c in r['conversions']))

    def test_all_73_outputs_match_typed_native_reference_with_real_sdk_instructions(self):
        for item in self.catalog:
            self.check(item)

    def test_no_abstract_memory_model_and_helper_instructions_are_in_continuous_trace(self):
        machine, row = self.check()
        self.assertFalse(row['memory_helper_abstract_models_used'])
        self.assertFalse(row['helper_state_reinjected'])
        self.assertEqual({h['name'] for h in row['helper_calls']}, {'strlen', 'memset', 'memcpy'})
        for h in row['helper_calls']:
            self.assertIn(machine.functions[h['name']]['start'], row['visited'])
            self.assertGreater(h['instruction_count'], 0)
            self.assertTrue(h['stack_restored'])
        self.assertFalse(any(c.get('modeled') for c in row['calls']))
        with self.assertRaises(m.IntegratedError):
            machine.modeled_call('memcpy')

    def test_capacities_and_abis_preserve_full_required_length_and_sentinels(self):
        lengths = []
        for abi in ('register', 'stack'):
            for capacity in audit.formats.CAPACITIES:
                _, row = self.check(abi=abi, capacity=capacity)
                lengths.append(row['return_value'])
        self.assertEqual(len(set(lengths)), 1)

    def test_all_current_string_formats_cover_page_end_and_vector_offsets(self):
        for item in self.catalog:
            if not any(c['kind'] == 's' for c in item['conversions']):
                continue
            for offset in (0, *audit.STRING_OFFSETS):
                for scenario in ('zero', 'limits'):
                    self.check(item, scenario=scenario, string_offset=offset)

    def test_strlen_padding_reads_are_recorded_including_prefix_and_after_nul(self):
        _, zero = self.check(self.serial(), scenario='zero')
        long_string = self.item(lambda r: any(c['kind'] == 's' and c['max_output_bytes'] == 64 for c in r['conversions']))
        _, prefix = self.check(long_string, string_offset=4095)
        self.assertTrue(any(h.get('read_after_nul', 0) > 0 for h in zero['helper_calls']))
        self.assertTrue(any(h.get('read_before_string', 0) == 31 for h in prefix['helper_calls']))

    def test_missing_padding_byte_fails_without_synthetic_fill(self):
        machine = self.machine(self.serial(), scenario='zero')
        del machine.mem[machine.string_objects[0]['pointer']+1]
        with self.assertRaisesRegex(m.sdk.fmt.scan.ScanError, 'Uninitialized'):
            machine.run_full()

    def test_no_page_padding_is_an_explicit_rejected_input(self):
        machine = self.machine(self.serial(), scenario='zero', mapped_string_pages=False)
        with self.assertRaisesRegex(m.sdk.fmt.scan.ScanError, 'Uninitialized'):
            machine.run_full()

    def test_locale_strlen_uses_bound_readonly_elf_bytes(self):
        _, row = self.check()
        readonly = [s for s in row['string_objects'] if s.get('readonly_elf_object')]
        self.assertTrue(readonly)
        for s in readonly:
            self.assertFalse(s['mapped_padding_injected'])
            self.assertTrue(any(h['name'] == 'strlen' and h['source'] == s['pointer'] for h in row['helper_calls']))

    def test_skipping_actual_memcpy_is_detected_by_output_contract(self):
        machine = self.machine(self.item(lambda r: not r['conversions']))
        machine.code[machine.functions['memcpy']['start']] = ('ret', '')
        with self.assertRaises(AssertionError):
            machine.run_full()

    def test_wrong_strlen_return_is_detected_before_formatter_resumes(self):
        machine = self.machine()
        pc = machine.functions['strlen']['start']
        machine.code[pc], machine.code[pc+4] = ('mov', 'x0, #0x0'), ('ret', '')
        with self.assertRaises(AssertionError):
            machine.run_full()

    def test_actual_copy_accesses_stay_in_declared_source_and_destination(self):
        _, row = self.check(capacity=32)
        for helper in row['helper_calls']:
            if helper['name'] == 'memcpy':
                self.assertTrue(all(helper['source'] <= r['address'] and r['address']+r['bytes'] <= helper['source']+helper['length'] for r in helper['reads']))
            if helper['name'] != 'strlen':
                self.assertTrue(all(helper['destination'] <= w['address'] and w['address']+w['bytes'] <= helper['destination']+helper['length'] for w in helper['writes']))

    def test_position_fault_reaches_unexecuted_get_arg_frontier(self):
        machine = self.machine()
        machine.code[machine.start+0x1fc] = ('mov', 'w3, #0x1')
        with self.assertRaisesRegex(m.sdk.fmt.LoopError, 'get_arg'):
            machine.run_full()

    def test_budget_unknown_opcode_and_large_memset_remain_frontiers(self):
        with self.assertRaisesRegex(m.sdk.fmt.LoopError, 'budget'):
            self.machine().run_full(budget=1)
        machine = self.machine()
        machine.code[machine.pc] = ('unsupported', '')
        with self.assertRaises(m.sdk.fmt.scan.parser.BridgeError):
            machine.run_full()
        with self.assertRaisesRegex(m.sdk.MemoryError, 'DCZID'):
            m.sdk.MemoryMachine(self.fs, self.blob, self.meta, self.literals[self.catalog[0]['format']], 'memset', 192, byte=0).run_helper()

    def test_helper_instruction_byte_drift_rejects_new_binding(self):
        pc = next(f['start'] for f in self.fs.values() if f['name'] == 'memcpy')
        s = next(s for s in self.meta['sections'] if s['flags'] & 4 and s['address'] <= pc < s['address']+s['size'])
        blob = bytearray(self.blob)
        blob[s['offset']+pc-s['address']] ^= 1
        with self.assertRaises(m.sdk.fmt.scan.parser.arg.elf.BoundaryError):
            audit.formats.prior.build_inputs(bytes(blob), self.text, self.catalog)

    def test_eight_parameters_and_cache_advance_without_helper_reinjection(self):
        _, row = self.check(abi='register')
        self.assertEqual([f['index'] for f in row['fetches']], list(range(8)))
        self.assertEqual([s['cached'] for s in row['scan_entries']], list(range(9)))
        self.assertFalse(row['index_cache_percent_and_file_state_reinjected'])
        self.assertFalse(row['helper_state_reinjected'])

    def test_binding_is_new_elf_and_offline_boundaries_and_tickets_stay_explicit(self):
        new = json.loads((audit.ELFS/'audit.json').read_text())
        self.assertEqual(self.binding['elf_sha256'], new['builds']['dormant']['elf_sha256'])
        self.assertEqual(self.binding['direct_sites'], 79)
        _, row = self.check()
        self.assertTrue(row['actual_sdk_memory_helpers_executed_in_model'])
        self.assertTrue(row['string_page_mapping_is_injected'])
        self.assertFalse(row['actual_sdk_helpers_executed_natively'])
        self.assertFalse(row['whole_thread_stack_verified'])
        verify(audit.ELFS)
        ticket = json.loads((audit.ELFS.parent/'A23-IOUSBHost-burst-next-test.json').read_text())
        self.assertEqual((ticket['stage'], ticket['remaining'], ticket['acquisition_enabled']), ('failed_no_retry', 0, False))


if __name__ == '__main__':
    unittest.main()
