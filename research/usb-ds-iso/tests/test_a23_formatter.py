"""Formatter table guard, PIC relocation and conditional locale, including drift."""
import copy,json,re,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_formatter as audit
import analyze_a23_formatter as model
from workflows.artifacts import verify
class A23FormatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output);cls.profile=cls.result['profiles']['dormant']
        p=audit.ELFS/'dormant';cls.blob=(p/'full.elf').read_bytes();cls.text=(p/'disassembly.txt').read_text();cls.rows=json.loads((p/'stack-usage.json').read_text())
        cls.functions,cls.metadata=model.elf.build_functions(cls.blob,cls.text);cls.dispatch=cls.profile['dispatch'];cls.locale=cls.profile['default_locale']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def offset(self,address):
        s=next(s for s in self.metadata['sections'] if s['type']!=8 and s['address']<=address<s['address']+s['size']);return s['offset']+address-s['address']
    def instruction(self,pc,word,op,arg):
        b=bytearray(self.blob);struct.pack_into('<I',b,self.offset(pc),word)
        pattern=r'(?m)^\s*'+format(pc,'x')+r':\s+[0-9a-f]{8}\s+.*$'
        text=re.sub(pattern,f' {pc:x}: {word:08x} {op} {arg}',self.text,count=1);return bytes(b),text
    def test_signed_table_has_91_entries_28_internal_targets(self):
        for p in self.result['profiles'].values():
            d=p['dispatch'];self.assertEqual((len(d['entries']),len(d['targets']),d['table_bytes']),(91,28,182))
            self.assertTrue(all(d['formatter_start']<=t<d['formatter_end'] for t in d['targets']))
            for r in d['entries']:self.assertEqual(r['target'],d['jump_base']+4*r['halfword'])
    def test_all_256_input_bytes_and_unsigned_wrap_boundaries(self):
        d=self.dispatch;self.assertEqual(len(self.profile['dispatch_byte_cases']),256)
        for c in range(256):self.assertEqual(model.select_dispatch(d,c),d['entries'][c-32]['target'] if 32<=c<=122 else d['default_target'])
        for c in (0,31,123,255,0xffffffff):self.assertEqual(model.select_dispatch(d,c),d['default_target'])
        self.assertEqual(model.select_dispatch(d,0x100000020),d['entries'][0]['target'])
    def test_base_definitions_hold_on_all_resolved_cfg_paths(self):
        d=self.dispatch;self.assertEqual(d['x26_origins_at_load'],[d['x26_table_definition']]);self.assertEqual(d['x26_origins_at_add'],[d['x26_page_definition']])
        self.assertTrue(d['readonly_table_verified']);self.assertTrue(d['unsigned_guard_verified']);self.assertTrue(d['callee_saved_x26_abi_assumed']);self.assertFalse(d['guard_bypass_edges_found'])
    def test_relocations_match_readelf_and_keep_pic_bias_relation(self):
        l=self.locale;oracle=audit.relocation_oracle((self.output/'dormant/relocations.txt').read_text());self.assertEqual(l['relative_relocation_locations'],oracle);self.assertEqual(len(oracle),382)
        for address in (l['default_locale_got'],l['callback_slot']):self.assertIn(address,oracle)
        for bias in (0,0x100000000,0x7f0000000000):
            self.assertEqual(l['global_locale_address']+bias+464,l['callback_slot']+bias);self.assertEqual((l['initial_callback_target']+bias)-bias,l['initial_callback_target'])
    def test_default_utf8_pointer_is_initial_and_only_conditional(self):
        for p in self.result['profiles'].values():
            l=p['default_locale'];self.assertEqual((l['initial_callback_name'],l['initial_mb_cur_max'],l['initial_callback_user_frame']),('__utf8_mbtowc',6,16))
            for k in ('thread_locale_null_assumed','global_locale_unchanged_assumed','valid_reent_tls_assumed','load_bias_relocation_assumed'):self.assertTrue(l[k])
            self.assertFalse(l['nonnull_thread_locale_resolved']);self.assertFalse(l['runtime_locale_measured'])
    def test_jump_mode_keeps_callback_unknown_and_default_mode_expands_dependency_frontier(self):
        for p in self.result['profiles'].values():
            for n in ('main','LogFunctionImpl','VideoStreamThread','AudioStreamThread'):
                j=p['jump_stack']['roots'][n];c=p['default_locale_stack']['roots'][n]
                self.assertTrue(any('_svfprintf_r:' in s and 'indirect blr x23' in s for s in j['unresolved']))
                self.assertFalse(any('_svfprintf_r:' in s and 'indirect blr x23' in s for s in c['unresolved']))
                for r in (j,c):
                    self.assertFalse(any('_svfprintf_r:' in s and 'indirect br x1' in s for s in r['unresolved']))
                    self.assertTrue(any('_wcrtomb_r:' in s for s in r['unresolved']));self.assertTrue(any('get_arg:' in s for s in r['unresolved']));self.assertTrue(any('recursive call cycle' in s for s in r['unresolved']));self.assertIsNone(r['user_prefix_bound_bytes'])
                self.assertTrue(c['default_locale_conditions_required'])
    def test_old_capture_save_and_direct_utf8_frames_preserved(self):
        for p in self.result['profiles'].values():
            for kind in ('jump_stack','default_locale_stack'):
                for n,v in (('session_capture',352),('Ep0SessionSaveJoined',768),('__utf8_mbtowc',16)):
                    r=p[kind]['roots'][n];self.assertEqual(r['user_prefix_bound_bytes'],v);self.assertFalse(r['default_locale_conditions_required'])
    def test_table_cannot_be_writable(self):
        b=bytearray(self.blob);s=next(s for s in self.metadata['sections'] if s['name']=='.rodata');shoff=struct.unpack_from('<Q',b,40)[0];struct.pack_into('<Q',b,shoff+64*s['index']+8,s['flags']|1)
        with self.assertRaisesRegex(ValueError,'writable'):model.decode_dispatch(bytes(b),self.text)
    def test_table_target_outside_formatter_is_rejected(self):
        b=bytearray(self.blob);struct.pack_into('<h',b,self.offset(self.dispatch['table_address']),32767)
        with self.assertRaisesRegex(ValueError,'outside formatter'):model.decode_dispatch(bytes(b),self.text)
    def test_guard_immediate_machine_drift_is_rejected(self):
        pc=self.dispatch['at']-20;word=model.elf.raw_word(self.blob,self.metadata,pc);b,t=self.instruction(pc,word+1024,'cmp','w1, #0x5b')
        with self.assertRaisesRegex(ValueError,'instruction drift'):model.decode_dispatch(b,t)
    def test_direct_branch_bypassing_guard_is_rejected(self):
        pc=self.dispatch['guard_start']-0xb4;op,arg=next((o,a) for p,o,a in self.functions[self.dispatch['formatter_start']]['instructions'] if p==pc)
        self.assertEqual(op,'b');dst=self.dispatch['at']-12
        for op,prefix in (('b',0x14000000),('bl',0x94000000)):
            word=prefix|(((dst-pc)//4)&0x3ffffff);b,t=self.instruction(pc,word,op,f'{dst:x} <_svfprintf_r+0x230>')
            with self.assertRaisesRegex(ValueError,'bypasses'):model.decode_dispatch(b,t)
    def test_table_base_origin_drift_is_rejected(self):
        pc=self.dispatch['x26_table_definition'];word=model.elf.raw_word(self.blob,self.metadata,pc);b,t=self.instruction(pc,word+1024,'add','x26, x26, #0x80d')
        with self.assertRaises(ValueError):model.decode_dispatch(b,t)
    def test_default_callback_initial_slot_change_is_rejected(self):
        b=bytearray(self.blob);struct.pack_into('<Q',b,self.offset(self.locale['callback_slot']),self.locale['initial_callback_target']+4)
        with self.assertRaisesRegex(ValueError,'callback changed'):model.default_locale(bytes(b),self.text)
    def test_initial_nonnull_reent_locale_is_not_resolved_as_default(self):
        s=next(s for s in self.metadata['symbols'] if s['name']=='_impure_data');b=bytearray(self.blob);struct.pack_into('<Q',b,self.offset(s['address']+64),self.locale['global_locale_address'])
        with self.assertRaisesRegex(ValueError,'no longer null'):model.default_locale(bytes(b),self.text)
    def test_relr_bitmap_before_base_is_rejected(self):
        s=next(s for s in self.metadata['sections'] if s['type']==19);b=bytearray(self.blob);struct.pack_into('<Q',b,s['offset'],1)
        with self.assertRaisesRegex(ValueError,'bitmap before base'):model.relative_relocations(bytes(b),model.elf.elf_metadata(bytes(b)))
    def test_relocation_oracle_missing_and_duplicates_are_rejected(self):
        with self.assertRaises(ValueError):audit.relocation_oracle('missing')
        text=(self.output/'dormant/relocations.txt').read_text();line=next(l for l in text.splitlines() if re.match(r'^0000:',l))
        with self.assertRaisesRegex(ValueError,'duplicate'):audit.relocation_oracle(text+'\n'+line)
    def test_forged_dispatch_certificate_is_rejected(self):
        d=copy.deepcopy(self.dispatch);d['targets'][0]+=4
        with self.assertRaisesRegex(ValueError,'certificate drift'):model.analyze_formatter(self.blob,self.text,self.rows,roots=('__utf8_mbtowc',),dispatch=d)
    def test_locale_conditions_cannot_be_removed_from_certificate(self):
        l=copy.deepcopy(self.locale);l['thread_locale_null_assumed']=False
        with self.assertRaisesRegex(ValueError,'certificate drift'):model.analyze_formatter(self.blob,self.text,self.rows,roots=('__utf8_mbtowc',),locale=l)
    def test_sources_tickets_and_seals_are_preserved(self):
        for p in (self.output,audit.SEALED,audit.ELFS):self.assertTrue(verify(p))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n),h)
    def test_no_whole_thread_or_runtime_hardware_and_cleanup_claim(self):
        for k in ('all_indirect_targets_resolved','nonnull_thread_locale_resolved','runtime_locale_measured','whole_thread_stack_verified','exception_and_kernel_stack_included','actual_abort_executed','actual_recursion_observed','format_specific_pruning','thread_tls_lifecycle_verified','new_arm_build','arm_executed','firmware_packaged','prior_runtime_modified','production_modified','prior_evidence_modified','usb_accessed','sd_accessed','actual_switch_threads_executed','cleanup_authorized','hardware_verified','root_cause_confirmed','source_authenticated'):self.assertFalse(self.result[k],k)
        self.assertEqual(list(self.output.rglob('*.elf')),[])
if __name__=='__main__':unittest.main()
