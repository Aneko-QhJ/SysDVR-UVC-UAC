"""Parser reset, byte-bound dispatch, correct hex region and shared fetch state."""
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import audit_a23_parser_bridge as audit
import analyze_a23_parser_bridge as m
from workflows.artifacts import verify


class ParserBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT/'private/analysis/A23-parser-bridge-review-20261015-final'
        verify(cls.folder)
        cls.audit = json.loads((cls.folder/'audit.json').read_text())
        p = audit.ELFS/'dormant'
        cls.blob, cls.text = (p/'full.elf').read_bytes(), (p/'disassembly.txt').read_text()
        cls.fs, cls.meta = m.arg.elf.build_functions(cls.blob, cls.text)
        cls.dispatch = m.fmt.decode_dispatch(cls.blob, cls.text)

    def model(self, spec='%u', **kwargs):
        return m.ConversionMachine(self.fs, self.blob, self.meta, spec, dispatch=self.dispatch, **kwargs)

    def test_all_bound_conversions_reach_fetch_in_both_abi_modes_with_dirty_slot(self):
        self.assertEqual((self.audit['linked_formats'], self.audit['linked_conversions'], self.audit['catalog_profiles']), (73, 97, 776))
        for p in self.audit['profiles'].values():
            self.assertEqual(p['catalog_profiles'], 388)
            for r in p['profiles']:
                self.assertEqual(r['parser_state']['position'], 0)
                self.assertFalse(r['fetch']['get_arg_frontier'])
                self.assertFalse(r['fetch_state_reinjected'])

    def test_true_hex_region_differs_from_prior_octally_dispatched_region(self):
        for spec, kind in (('%x', 'x32'), ('%llx', 'x64')):
            row = self.model(spec).bridge()
            p = self.audit['profiles']['dormant']['actual_conversion_paths'][kind]
            self.assertEqual(row['fetch']['visited'][0], p['entry'])
            self.assertNotEqual(p['entry'], self.dispatch['formatter_start'] + m.arg.PATHS[kind][0])
        self.assertEqual(m.fmt.select_dispatch(self.dispatch, ord('o')), self.dispatch['formatter_start'] + 0x18f0)

    def test_dirty_pointer_and_all_ones_are_overwritten_by_conversion_reset(self):
        for value in audit.POISONS:
            row = self.model('%04x', poison=value).bridge()
            self.assertEqual(row['position_slot_events'][0]['value'], 0)
            self.assertEqual(row['parser_state']['position'], 0)
            self.assertEqual([e['bytes'] for e in row['position_slot_events'] if e['kind'] == 'write'], [4])

    def test_removing_reset_reaches_helper_frontier(self):
        model = self.model('%u', poison=1)
        reset = model.start + 0x204
        self.assertEqual(model.code[reset], ('str', 'w3, [sp, #136]'))
        model.code[reset] = ('mov', 'w3, #0x0')
        row = model.bridge()
        self.assertEqual(row['parser_state']['position'], 1)
        self.assertTrue(row['fetch']['get_arg_frontier'])

    def test_real_position_tokens_reach_helper_but_33_is_rejected(self):
        for token, index in (('%1$d', 0), ('%32$u', 31)):
            row = self.model(token).bridge()
            self.assertEqual(row['parser_state']['positional_index'], index)
            self.assertEqual(row['parser_state']['position'], 1)
            self.assertTrue(row['fetch']['get_arg_frontier'])
        self.assertEqual(self.model('%33$u').bridge()['outcome'], 'rejected-index')

    def test_zero_padding_numeric_width_and_ll_are_parsed_from_bytes(self):
        for token, width, kind in (('%02x', 2, 'x32'), ('%0008x', 8, 'x32'), ('%12x', 12, 'x32'), ('%llu', 0, 'u64')):
            row = self.model(token).bridge()
            self.assertEqual((row['parser_state']['width'], row['parser_state']['path']), (width, kind))
            self.assertEqual(row['parser_state']['next_format_offset'], len(token))

    def test_index_seven_uses_stack_and_preserves_shared_counter(self):
        for token in ('%u', '%x', '%llx', '%d', '%s'):
            model = self.model(token, index=7)
            self.assertEqual(model.source, model.stack_arg)
            row = model.bridge()
            self.assertEqual(row['fetch']['next_index'], 8)
            self.assertEqual(row['fetch']['final_cached'], 8)

    def test_hex_signedness_uses_actual_path(self):
        row = self.model('%x', value=0xffffffff).bridge()
        self.assertEqual(row['fetch']['result'], 0xffffffff)
        row = self.model('%d', value=0xffffffff).bridge()
        self.assertEqual(row['fetch']['result'], m.arg.MASK)

    def test_uninitialized_register_or_memory_is_rejected(self):
        model = self.model()
        del model.reg['x12']
        with self.assertRaises(m.BridgeError): model.bridge()
        model = self.model()
        del model.mem[model.format_base + 1]
        with self.assertRaises(m.arg.ArgumentError): model.bridge()

    def test_instruction_budget_and_unsupported_opcode_fail_closed(self):
        with self.assertRaises(m.BridgeError): self.model('%0008x').bridge(budget=1)
        model = self.model()
        model.code[model.pc] = ('unknown', '')
        with self.assertRaises(m.BridgeError): model.bridge()

    def test_changed_actual_dispatch_byte_is_rejected(self):
        blob = bytearray(self.blob)
        pc = self.dispatch['at']
        section = next(s for s in self.meta['sections'] if s['flags'] & 4 and s['address'] <= pc < s['address'] + s['size'])
        blob[section['offset'] + pc - section['address']] ^= 1
        with self.assertRaises(m.arg.elf.BoundaryError): m.fmt.decode_dispatch(bytes(blob), self.text)

    def test_wide_stores_remain_in_inventory_and_no_global_liveness_claim(self):
        for p in self.audit['profiles'].values():
            wide = [r for r in p['slot_inventory']['direct_accesses'] if r['kind'] == 'write' and r['bytes'] >= 8]
            self.assertEqual(len(wide), 3)
            self.assertFalse(p['slot_inventory']['whole_function_slot_liveness_verified'])
            self.assertFalse(p['slot_inventory']['indirect_aliases_resolved'])

    def test_live_inputs_and_seals_remain_unchanged(self):
        for n, h in self.audit['production_sources_sha256'].items(): self.assertEqual(audit.base.ep0.sha(audit.REPO/n), h)
        for n, h in self.audit['tickets_sha256'].items(): self.assertEqual(audit.base.ep0.sha(audit.ELFS.parent/n), h)
        self.assertEqual(self.audit['sealed_inputs'], [verify(audit.SEALED), verify(audit.ELFS)])
        for k in ('full_parser_executed', 'get_arg_globally_unreachable_proven', 'formatter_cfg_pruned', 'whole_thread_stack_verified', 'new_arm_build', 'arm_executed', 'usb_accessed', 'sd_accessed', 'root_cause_confirmed'):
            self.assertFalse(self.audit[k])


if __name__ == '__main__':
    unittest.main()
