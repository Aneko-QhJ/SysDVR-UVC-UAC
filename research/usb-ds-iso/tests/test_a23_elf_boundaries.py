"""ELF size/type/byte binding and explicit abort contracts, with negative cases."""
import copy,json,re,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_elf_boundaries as audit
import analyze_a23_elf_boundaries as stack
from workflows.artifacts import verify
class A23ElfBoundariesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output)
        p=audit.ELFS/'dormant';cls.blob=(p/'full.elf').read_bytes();cls.text=(p/'disassembly.txt').read_text();cls.rows=json.loads((p/'stack-usage.json').read_text())
        cls.functions,cls.metadata=stack.build_functions(cls.blob,cls.text);cls.names={n:a for a,f in cls.functions.items() for n in f['aliases']}
        cls.policy=cls.result['profiles']['dormant']['no_return_policy'];cls.headers={n:(cls.output/'sdk-headers'/n).read_text() for n in audit.HEADERS}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def root(self,n,kind='conditional_stack'):return self.result['profiles']['dormant'][kind]['roots'][n]
    def test_raw_decoder_readelf_oracle_and_aliases(self):
        for p in self.result['profiles'].values():self.assertEqual((p['function_count'],p['readelf_function_symbols_checked']),(394,396))
        self.assertEqual(self.names['memmove'],self.names['memcpy']);self.assertEqual(self.names['fsFileGetSize'],self.names['fsFileGetSize.localalias'])
        self.assertEqual(self.functions[self.names['memcpy']]['symbol_size'],556)
    def test_local_cache_flush_loop_merges_into_zero_size_ceiling(self):
        f=self.functions[self.names['armDCacheFlush']];self.assertEqual((f['range_kind'],f['symbol_size']),('next-function-ceiling',0))
        self.assertIn('armDCacheFlush_L0',{s['name'] for s in f['local_labels']});self.assertNotIn('armDCacheFlush_L0',self.names)
        self.assertEqual(self.root('armDCacheFlush','typed_stack')['user_prefix_bound_bytes'],0)
    def test_abort_size_excludes_udf_padding(self):
        f=self.functions[self.names['diagAbortWithResult']];self.assertEqual(f['symbol_size'],28);self.assertEqual(f['instructions'][-1][0]+4,f['end'])
        self.assertEqual(stack.raw_word(self.blob,self.metadata,f['end']),0);self.assertNotIn('udf',[r[1] for r in f['instructions']])
    def test_without_contract_abort_tls_and_fatal_remain_unknown(self):
        for n in ('diagAbortWithResult','__syscall_getreent','fatalThrow'):
            r=self.root(n,'typed_stack');self.assertIsNone(r['user_prefix_bound_bytes']);self.assertTrue(any('falls outside symbol range' in v for v in r['unresolved']))
    def test_contract_numbers_are_only_prefixes_with_assumptions(self):
        for n,v in (('diagAbortWithResult',32),('__syscall_getreent',48),('fatalThrow',224)):
            r=self.root(n,'contract_stack');self.assertEqual(r['user_prefix_bound_bytes'],v);self.assertTrue(r['sdk_no_return_contracts']);self.assertIsNone(r['whole_thread_stack_bound_bytes'])
        self.assertTrue(self.result['sdk_no_return_contract_assumed']);self.assertFalse(self.result['kernel_contract_measured'])
    def test_break_and_fatal_policy_are_not_no_return(self):
        contracts={c['name'] for c in self.policy['contracts'].values()};self.assertNotIn('svcBreak',contracts);self.assertNotIn('fatalThrowWithPolicy',contracts)
        self.assertEqual(self.root('svcBreak','contract_stack')['sdk_no_return_contracts'],[])
        self.assertEqual([op for _,op,_ in self.functions[self.names['svcBreak']]['instructions']],['svc','ret'])
    def test_formatter_still_blocks_main_and_workers(self):
        for p in self.result['profiles'].values():
            roots=p['conditional_stack']['roots'];self.assertEqual(len(roots['main']['unresolved']),2)
            for n in ('main','VideoStreamThread','AudioStreamThread'):
                r=roots[n];self.assertIsNone(r['user_prefix_bound_bytes']);self.assertEqual(sum('_svfprintf_r:' in v and 'indirect' in v for v in r['unresolved']),2)
    def test_recursion_and_wait_profiles_are_not_proof(self):
        for n in ('VideoStreamThread','AudioStreamThread'):
            r=self.root(n);self.assertTrue(any('recursive call cycle' in v for v in r['unresolved']));self.assertTrue(r['contains_wait_profile_substitution']);self.assertIsNone(r['user_prefix_bound_bytes'])
        self.assertEqual(len(self.root('VideoStreamThread')['wait_sites']),2)
    def test_old_capture_and_save_bounds_need_no_new_contracts(self):
        for p in self.result['profiles'].values():
            for kind in ('typed_stack','contract_stack','conditional_stack'):
                for n,v in (('session_capture',352),('Ep0SessionSaveJoined',768)):
                    r=p[kind]['roots'][n];self.assertEqual(r['user_prefix_bound_bytes'],v);self.assertEqual(r['sdk_no_return_contracts'],[])
    def test_truncated_wrong_endian_and_wrong_machine_elf_reject(self):
        for b in (self.blob[:60],self.blob[:5]+b'\x02'+self.blob[6:],self.blob[:18]+b'\x3e\x00'+self.blob[20:]):
            with self.assertRaises(stack.BoundaryError):stack.elf_metadata(b)
    def test_disassembly_words_are_bound_to_binary(self):
        line=next(l for l in self.text.splitlines() if re.match(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}',l));changed=re.sub(r'(:\s+)[0-9a-f]{8}',r'\g<1>ffffffff',line,count=1)
        with self.assertRaisesRegex(stack.BoundaryError,'byte drift'):stack.build_functions(self.blob,self.text.replace(line,changed,1))
    def test_readelf_oracle_size_drift_reject(self):
        text=(self.output/'dormant/symbols.txt').read_text();line=next(l for l in text.splitlines() if l.rstrip().endswith('diagAbortWithResult'));changed=line.replace('    28 FUNC','    32 FUNC');self.assertNotEqual(line,changed)
        with self.assertRaisesRegex(ValueError,'disagreement'):audit.compare_readelf_functions(text.replace(line,changed),self.metadata)
    def test_symbol_cannot_cross_next_function(self):
        b=bytearray(self.blob);s=next(s for s in self.metadata['sections'] if s['type']==2);i=next(i for i,t in enumerate(self.metadata['symbols']) if t['name']=='diagAbortWithResult');struct.pack_into('<Q',b,s['offset']+i*24+16,128)
        with self.assertRaisesRegex(stack.BoundaryError,'Overlapping'):stack.build_functions(bytes(b),self.text)
    def test_local_label_changed_to_function_is_not_forced_to_merge(self):
        b=bytearray(self.blob);s=next(s for s in self.metadata['sections'] if s['type']==2);i=next(i for i,t in enumerate(self.metadata['symbols']) if t['name']=='armDCacheFlush_L0');b[s['offset']+i*24+4]=2
        g=stack.analyze(bytes(b),self.text,self.rows,roots=('armDCacheFlush',));self.assertIsNone(g['roots']['armDCacheFlush']['user_prefix_bound_bytes']);self.assertTrue(g['roots']['armDCacheFlush']['unresolved'])
    def test_sdk_declaration_macro_or_returning_break_drift_reject(self):
        for h,a,b in (('switch/types.h','__attribute__((noreturn))','__attribute__((unused))'),('switch/kernel/svc.h','void NX_NORETURN svcExitProcess(void);','void svcExitProcess(void);'),('switch/kernel/svc.h','Result svcBreak(','void NX_NORETURN svcBreak(')):
            headers=dict(self.headers);headers[h]=headers[h].replace(a,b)
            with self.assertRaises(stack.BoundaryError):stack.no_return_policy(self.blob,self.text,headers)
    def test_policy_cannot_hide_returning_func_or_claim_kernel_measurement(self):
        for mutation in ('break','measured','syscall'):
            p=copy.deepcopy(self.policy)
            if mutation=='break':p['contracts'][str(self.names['svcBreak'])]=dict(name='svcBreak',function_sha256=stack.function_digest(self.functions[self.names['svcBreak']]))
            elif mutation=='measured':p['kernel_contract_measured']=True
            else:p['contracts'][str(self.names['svcExitProcess'])]['syscall']=10
            with self.assertRaises(stack.BoundaryError):stack.analyze(self.blob,self.text,self.rows,p,roots=('svcBreak',))
    def test_missing_instruction_dynamic_sp_and_su_disagreement_stay_unknown(self):
        f=copy.deepcopy(self.functions[self.names['armDCacheFlush']]);f['instructions']=[r for r in f['instructions'] if r[0]!=f['start']+4];self.assertTrue(stack.frame_range(f,self.functions)['unresolved'])
        f=dict(name='fixture',start=4,end=16,instructions=[(4,'sub','sp, sp, x1'),(8,'mov','sp, x2'),(12,'ret','')]);self.assertTrue(stack.frame_range(f,{4:f})['unresolved'])
        f=dict(name='fixture',start=4,end=8,instructions=[(4,'ret','')]);self.assertTrue(stack.frame_range(f,{4:f},16)['unresolved'])
    def test_reachable_trap_or_ret_in_no_return_func_stay_unknown(self):
        f=dict(name='fixture',start=4,end=8,instructions=[(4,'udf','#0')]);self.assertIsNone(stack.frame_range(f,{4:f})['frame_bytes'])
        f=dict(name='fixture',start=4,end=8,instructions=[(4,'ret','')]);self.assertTrue(any('reachable ret' in v for v in stack.frame_range(f,{4:f},contracts={4:{'name':'fixture'}})['unresolved']))
    def test_sources_tickets_headers_and_seals_preserved(self):
        for p in (self.output,audit.SEALED,audit.ELFS):self.assertTrue(verify(p))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n),h)
        for n,h in self.result['sdk_headers_sha256'].items():self.assertEqual(audit.base.ep0.sha(self.output/'sdk-headers'/n),h)
    def test_no_new_build_execution_hardware_or_cleanup_claim(self):
        for k in ('formatter_indirect_targets_resolved','capture_recursion_bounded_in_graph','whole_thread_stack_verified','exception_and_kernel_stack_included','kernel_contract_measured','actual_abort_executed','wait_profile_is_full_proof','new_arm_build','arm_executed','firmware_packaged','prior_runtime_modified','production_modified','prior_evidence_modified','usb_accessed','sd_accessed','actual_switch_threads_executed','cleanup_authorized','hardware_verified','root_cause_confirmed','source_authenticated'):self.assertFalse(self.result[k],k)
        self.assertEqual(list(self.output.rglob('*.elf')),[])
if __name__=='__main__':unittest.main()
