"""Linked log coverage, CFG rejection and final-SDK append profiles."""
import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_linked_logs as audit
import analyze_a23_linked_logs as m
from workflows.artifacts import verify

class A23LinkedLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review=ROOT/'private/analysis/A23-linked-logs-review-20261014';verify(cls.review);cls.result=json.loads((cls.review/'audit.json').read_text())
        cls.folder=audit.ELFS/'dormant';cls.blob=(cls.folder/'full.elf').read_bytes();cls.text=(cls.folder/'disassembly.txt').read_text();cls.functions,cls.metadata=m.elf.build_functions(cls.blob,cls.text)
    def model(self,capacity=511,flags=0x208):return m.StringAppendMachine(self.blob,self.text,capacity,flags,self.functions)
    def synthetic(self,body):return dict(start=0x100,end=max(p for p,_,_ in body)+4,name='synthetic',instructions=body)

    def test_direct_call_coverage_differs_by_window_and_has_seventy_three_formats(self):
        for label,n in (('dormant',79),('window-30s',80)):
            row=self.result['profiles'][label]['linked_calls'];self.assertEqual(row['direct_sites'],n);self.assertEqual(row['unique_linked_formats'],73)
            self.assertEqual(len(row['caller_functions_sha256']),18);self.assertEqual(row['max_declared_linked_output_bytes'],229);self.assertTrue(row['all_direct_log_call_sites_bound'])
            self.assertFalse(row['indirect_log_invocations_excluded'])

    def test_source_only_formats_are_three_uac_setup_messages(self):
        for row in self.result['profiles'].values():
            formats=row['linked_calls']['catalog_only_formats'];self.assertEqual([r['case'] for r in formats],[43,44,45]);self.assertTrue(all(r['unit']=='uvc/uvc_device.c' for r in formats))
            self.assertIn('AC interface',formats[0]['format']);self.assertIn('AS interface',formats[1]['format']);self.assertIn('UAC audio',formats[2]['format'])

    def test_bound_formats_are_readonly_terminated_literals(self):
        for row in self.result['profiles']['dormant']['linked_calls']['sites']:
            self.assertEqual([m.literal_at(self.blob,self.metadata,p) for p in row['format_addresses']],row['formats'])

    def test_caller_saved_format_register_is_invalidated_by_calls(self):
        f=self.synthetic([(0x100,'adrp','x0, 21000 <literal>'),(0x104,'bl','400 <helper>'),(0x108,'bl','920 <LogFunctionImpl>')])
        with self.assertRaises(m.LinkedLogError):m.LiteralResolver(f).values(0x108,'x0')

    def test_callee_saved_format_register_survives_calls(self):
        f=self.synthetic([(0x100,'adrp','x20, 21000 <literal>'),(0x104,'bl','400 <helper>'),(0x108,'mov','x0, x20'),(0x10c,'bl','920 <LogFunctionImpl>')])
        self.assertEqual(m.LiteralResolver(f).values(0x10c,'x0'),{0x21000})

    def test_cfg_join_keeps_both_possible_literal_origins(self):
        f=self.synthetic([(0x100,'cbz','w1, 110 <synthetic+0x10>'),(0x104,'adrp','x0, 21000 <literal>'),(0x108,'b','114 <synthetic+0x14>'),(0x110,'adrp','x0, 22000 <literal2>'),(0x114,'bl','920 <LogFunctionImpl>')])
        self.assertEqual(m.LiteralResolver(f).values(0x114,'x0'),{0x21000,0x22000})

    def test_cfg_join_with_unknown_input_does_not_guess_literal(self):
        f=self.synthetic([(0x100,'cbz','w1, 110 <synthetic+0x10>'),(0x104,'adrp','x0, 21000 <literal>'),(0x108,'b','114 <synthetic+0x14>'),(0x110,'nop',''),(0x114,'bl','920 <LogFunctionImpl>')])
        with self.assertRaises(m.LinkedLogError):m.LiteralResolver(f).values(0x114,'x0')

    def test_unresolved_internal_branch_is_rejected(self):
        f=self.synthetic([(0x100,'br','x2'),(0x104,'bl','920 <LogFunctionImpl>')])
        with self.assertRaises(m.LinkedLogError):m.LiteralResolver(f).values(0x104,'x0')

    def test_writable_or_unterminated_format_is_rejected(self):
        address=self.result['profiles']['dormant']['linked_calls']['sites'][0]['format_addresses'][0];metadata=copy.deepcopy(self.metadata)
        section=next(s for s in metadata['sections'] if s['address']<=address<s['address']+s['size'] and s['flags']&2);section['flags']|=1
        with self.assertRaises(m.LinkedLogError):m.literal_at(self.blob,metadata,address)
        blob=bytearray(self.blob);s=next(s for s in self.metadata['sections'] if s['address']<=address<s['address']+s['size'] and s['flags']&2);n=min(2048,s['address']+s['size']-address);start=s['offset']+address-s['address'];blob[start:start+n]=b'A'*n
        with self.assertRaises(m.LinkedLogError):m.literal_at(bytes(blob),self.metadata,address)

    def test_machine_instruction_byte_change_is_rejected(self):
        pc=self.result['profiles']['dormant']['linked_calls']['sites'][0]['at'];s=next(s for s in self.metadata['sections'] if s['address']<=pc<s['address']+s['size'] and s['flags']&4);blob=bytearray(self.blob);blob[s['offset']+pc-s['address']]^=1
        with self.assertRaises(m.elf.BoundaryError):m.file_state(bytes(blob),self.text)

    def test_two_file_flag_stores_have_four_cfg_proven_error_definitions(self):
        for profile in self.result['profiles'].values():
            row=profile['file_state'];self.assertEqual((row['initial_flags'],row['error_flags'],row['growth_mask']),(0x208,0x248,0x480));stores=row['formatter_local_flag_stores']
            self.assertEqual(len(stores),2);self.assertEqual(sum(len(s['updates']) for s in stores),4);self.assertTrue(all(s['reaching_definitions_verified'] for s in stores));self.assertFalse(row['file_flags_lifecycle_verified'])

    def test_changed_error_flag_or_growth_guard_is_rejected(self):
        for a,b in (('orr\tw0, w0, #0x40','orr\tw0, w0, #0x80'),('mov\tw1, #0x480','mov\tw1, #0x400')):
            self.assertIn(a,self.text)
            with self.assertRaises(m.LinkedLogError):m.file_state(self.blob,self.text.replace(a,b))

    def test_append_long_and_repeated_chunks_stop_at_capacity_and_restore_sp(self):
        for flags in (0x208,0x248):
            model=self.model(flags=flags);steps=[model.append(n) for n in (64,)*20]
            self.assertEqual(steps[-1]['stored'],511);self.assertEqual(steps[-1]['remaining'],0);self.assertEqual(steps[-1]['flags'],flags)
            self.assertTrue(all(s['stack_restored'] and not s['growth_frontier'] for s in steps));self.assertEqual(sum(c['bytes'] for c in model.copies),511)

    def test_unknown_append_opcode_and_oversized_copy_are_rejected(self):
        model=self.model();model.code[model.function['start']]=('unsupported','')
        with self.assertRaises(m.LinkedLogError):model.append(1)
        model=self.model();pc=next(p for p,ins in model.code.items() if ins==('mov','x2, x20'));model.code[pc]=('mov','x2, #0x1000')
        with self.assertRaises(m.LinkedLogError):model.append(1)

    def test_growth_bit_controls_stop_at_allocator_frontier_without_execution(self):
        for flags in (0x288,0x608,0x688,0x2c8,0x648,0x6c8):
            self.assertTrue(self.model(flags=flags).append(512)['growth_frontier'])
        for row in self.result['profiles'].values():
            p=row['append_profiles'];self.assertEqual((p['nongrowth_scenarios'],p['growth_frontier_scenarios']),(60,6));self.assertFalse(p['allocation_executed']);self.assertFalse(p['actual_sdk_memcpy_executed']);self.assertFalse(p['full_symbolic_proof'])

    def test_error_bit_preserves_growth_mask_for_all_sixteen_bit_states(self):
        for flags in range(65536):self.assertEqual((flags|64)&0x480,flags&0x480)

    def test_new_elf_frontiers_keep_get_arg_and_unknown_whole_thread_bounds(self):
        for profile in self.result['profiles'].values():
            self.assertEqual(len(profile['get_arg_direct_call_sites']),28);self.assertFalse(profile['get_arg_unreachable_for_catalog_proven'])
            self.assertEqual(len(profile['dispatch']['entries']),91);self.assertEqual(len(profile['dispatch']['targets']),28);self.assertEqual(profile['default_locale']['relative_relocation_count'],382)
            g=profile['conditional_stack'];self.assertEqual(g['roots']['Ep0SessionSaveJoined']['user_prefix_bound_bytes'],768)
            for name in ('main','LogFunctionImpl','VideoStreamThread','AudioStreamThread'):self.assertIsNone(g['roots'][name]['whole_thread_stack_bound_bytes']);self.assertTrue(g['roots'][name]['unresolved'])

    def test_live_source_tickets_and_prior_evidence_are_preserved(self):
        a=self.result
        for n,h in a['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in a['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.ELFS.parent/n),h)
        ticket=json.loads((audit.ELFS.parent/'A23-IOUSBHost-burst-next-test.json').read_text());self.assertEqual(ticket['remaining'],0);self.assertFalse(ticket['acquisition_enabled'])
        self.assertEqual(a['sealed_inputs'],[verify(audit.ELFS),verify(audit.CATALOG)])
        for k in ('new_arm_build','arm_executed','firmware_packaged','usb_accessed','sd_accessed','file_flags_lifecycle_verified','formatter_cfg_pruned','whole_thread_stack_verified','actual_recursion_observed','production_modified','hardware_verified','root_cause_confirmed'):self.assertFalse(a[k])

if __name__=='__main__':unittest.main()
