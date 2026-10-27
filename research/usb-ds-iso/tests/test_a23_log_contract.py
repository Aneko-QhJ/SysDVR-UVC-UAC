"""Current logging formats, diagnosed mismatch and host-only reviewed corrections."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_log_contract as audit
import analyze_a23_log_contract as model
from workflows.artifacts import verify
class A23LogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output);cls.profile=cls.result['profiles']['dormant'];cls.native=cls.result['native']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def edges(self,control=False):return {(r['scenario'],r['input_length']):r for r in self.native['edges'] if r['control']==control}
    def test_all_13_preprocessed_units_have_76_narrow_static_calls(self):
        for p in self.result['profiles'].values():
            self.assertEqual(len(p['syntax_checks']),13);self.assertEqual(p['current_log_calls'],76);self.assertEqual(p['conversion_kinds'],['d','s','u','x'])
            self.assertEqual((p['max_conservative_output_bytes'],p['reviewed_max_output_bytes']),(219,229))
            self.assertTrue(all(r['max_output_bytes']<512 for r in p['reviewed_catalog']))
    def test_string_sources_have_explicit_literal_serial_and_build_bounds(self):
        strings=[c for r in self.profile['catalog'] for c in r['conversions'] if c['kind']=='s'];self.assertEqual(len(strings),3)
        bounds={c['argument']:c['max_output_bytes'] for c in strings};self.assertEqual(bounds['g_serialNumber'],31);self.assertEqual(bounds['build'],64);self.assertIn(5,bounds.values())
    def test_original_frequency_type_mismatch_is_kept_not_silenced(self):
        for label,p in self.result['profiles'].items():
            rows=[r for r in p['syntax_checks'] if r['original_printf_type_errors']];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['unit'],'uvc/uvc_device.c')
            report=(self.output/label/'format-diagnostics/uvc/uvc_device.txt').read_text();self.assertEqual(report.count('error: format '),1);self.assertIn('armGetSystemTickFreq',report);self.assertIn('u64',report)
            self.assertTrue(all(r['reviewed_printf_type_check_passed'] for r in p['syntax_checks']))
        self.assertFalse(self.result['original_printf_argument_types_valid'])
    def test_source_review_copy_changes_exactly_three_files(self):
        for label in self.result['profiles']:
            before=audit.ELFS/label/'source';after=self.output/label/'source-reviewed';changed=[]
            for p in before.rglob('*'):
                if p.is_file() and p.read_bytes()!=(after/p.relative_to(before)).read_bytes():changed.append(p.relative_to(before).as_posix())
            self.assertEqual(sorted(changed),['core.c','core.h','uvc/uvc_device.c'])
            self.assertIn('__attribute__((format(printf,1,2)))',(after/'core.h').read_text());self.assertIn('frequency=%llu trigger=%llu',(after/'uvc/uvc_device.c').read_text());self.assertIn('(unsigned long long)armGetSystemTickFreq()',(after/'uvc/uvc_device.c').read_text())
    def test_only_one_catalog_call_changes_format_and_frequency_argument(self):
        p=self.profile;diff=[(a,b) for a,b in zip(p['catalog'],p['reviewed_catalog']) if a['format']!=b['format']];self.assertEqual(len(diff),1)
        a,b=diff[0];self.assertEqual(b['max_output_bytes'],a['max_output_bytes']+10);self.assertIn('frequency=%u',a['format']);self.assertIn('frequency=%llu',b['format'])
        self.assertEqual(a['conversions'][2]['argument'],'armGetSystemTickFreq()');self.assertEqual(b['conversions'][2]['sample_type'],'unsigned long long')
    def test_current_samples_preserve_clamp_results_and_reviewed_samples_fit(self):
        n=self.native;self.assertEqual((n['catalog_cases'],n['boundary_cases'],n['reviewed_catalog_cases'],n['total_checks']),(152,22,76,250))
        before=[{k:v for k,v in r.items() if k!='control'} for r in n['catalog'] if not r['control']];after=[{k:v for k,v in r.items() if k!='control'} for r in n['catalog'] if r['control']];self.assertEqual(before,after)
        for r in (*n['catalog'],*n['reviewed_catalog']):self.assertFalse(r['span_exceeds_buffer']);self.assertFalse(r['text_truncated']);self.assertFalse(r['contains_nul'])
    def test_truncated_return_is_not_stored_length(self):
        a=self.edges();b=self.edges(True)
        for length in (511,512,513,1024):
            r=a['length',length];self.assertEqual(r['required_length'],length);self.assertEqual(r['requested'],length)
            self.assertEqual(r['span_exceeds_buffer'],length>512);self.assertEqual(r['contains_nul'],length>=512)
            q=b['length',length];self.assertEqual(q['required_length'],length);self.assertEqual(q['requested'],min(length,511));self.assertFalse(q['contains_nul']);self.assertFalse(q['span_exceeds_buffer'])
    def test_disabled_zero_and_formatter_error_do_not_open_file(self):
        for control in (False,True):
            rows=self.edges(control)
            for name,length in (('length',0),('unmounted',7),('format-error',7)):
                r=rows[name,length];self.assertEqual((r['opens'],r['sizes'],r['writes'],r['closes']),(0,0,0,0))
            self.assertEqual(rows['unmounted',7]['formats'],0);self.assertEqual(rows['format-error',7]['required_length'],-1)
    def test_existing_size_error_writes_zero_offset_and_still_closes(self):
        for control in (False,True):
            rows=self.edges(control);r=rows['size-error',7];self.assertEqual((r['writes'],r['write_offset'],r['closes']),(1,0,1))
            self.assertEqual(rows['open-error',7]['closes'],0);self.assertEqual(rows['write-error',7]['closes'],1)
        self.assertTrue(self.native['fs_read_size_error_originally_ignored'])
    def test_final_elf_flags_are_208_with_no_initial_growth_bits(self):
        for p in self.result['profiles'].values():
            m=p['machine_contract'];self.assertEqual((m['buffer_bytes'],m['max_stored_text_bytes'],m['logger_frame_bytes']),(512,511,832));self.assertEqual(m['file_flags'],0x208)
            for k in ('file_string_mode','file_write_mode','file_malloc_bit_initially_clear','file_growth_mask_initially_clear','initial_buffer_allocation_branch_not_taken','logger_uses_unclamped_required_length'):self.assertTrue(m[k])
            self.assertFalse(m['file_flags_preserved_at_runtime_verified']);self.assertFalse(m['whole_formatter_paths_pruned'])
    def test_dynamic_wide_float_positional_precision_and_unknown_string_reject(self):
        for fmt,args in (('%f',['x']),('%ls',['s']),('%*u',['n','x']),('%1$u',['x']),('%.3s',['s']),('%s',['unknown'])):
            with self.assertRaises(ValueError):model.format_contract(fmt,args)
    def test_catalog_handles_adjacent_strings_nested_arguments_and_escaped_percent(self):
        text='void LogFunctionImpl(const char *, ...); void f(void){LogFunctionImpl("V " "%08x %%\\n", (unsigned int)fn(1,2));}'
        rows=model.inventory(text,'fixture.c');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['format'],'V %08x %%\n');self.assertEqual(rows[0]['max_output_bytes'],13)
    def test_literal_argument_count_width_and_nul_reject(self):
        for expression in ('fmt','"x" + "y"','"\\0"','"é"'):
            with self.assertRaises(ValueError):model.literal(expression)
        for fmt,args in (('%u',[]),('%u',['a','b']),('%257u',['a'])):
            with self.assertRaises(ValueError):model.format_contract(fmt,args)
    def test_machine_or_stdio_flag_drift_rejects_contract(self):
        p=audit.ELFS/'dormant';blob=(p/'full.elf').read_bytes();text=(p/'disassembly.txt').read_text();h=(self.output/'stdio.h').read_text()
        with self.assertRaises(ValueError):model.machine_contract(blob,text,h.replace('__SMBF\t0x0080','__SMBF\t0x0100'))
        changed=text.replace('mov\tx1, #0x200','mov\tx1, #0x201')
        with self.assertRaises(ValueError):model.machine_contract(blob,changed,h)
    def test_actual_logger_body_matches_production_and_clamp_is_explicit(self):
        actual=audit.logger_source();self.assertIn('fsFileWrite(&file, offset, buf, len, FsWriteOption_Flush);',actual);self.assertNotIn('len >=',actual)
        self.assertEqual(audit.logger_source(True),actual.replace('    if (len <= 0) return;','    if (len <= 0) return;\n    if (len >= (int)sizeof(buf)) len = (int)sizeof(buf) - 1;'))
    def test_preserves_seals_sources_tickets_and_no_execution_claim(self):
        for p in (self.output,audit.SEALED,audit.ELFS):self.assertTrue(verify(p))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n),h)
        for k in ('all_linked_log_call_sites_bound','linked_dead_code_pruned','current_catalog_exceeds_capacity','file_flags_lifecycle_verified','formatter_cfg_pruned','whole_thread_stack_verified','thread_tls_lifecycle_verified','production_modified','prior_runtime_modified','prior_evidence_modified','clamp_control_in_arm_candidate','new_full_arm_build','arm_executed','firmware_packaged','usb_accessed','sd_accessed','actual_switch_threads_executed','cleanup_authorized','actual_buffer_overread_executed','hardware_verified','root_cause_confirmed','source_authenticated'):self.assertFalse(self.result[k],k)
        self.assertEqual(list(self.output.rglob('*.elf')),[]);self.assertEqual(list(self.output.rglob('*.o')),[])
if __name__=='__main__':unittest.main()
