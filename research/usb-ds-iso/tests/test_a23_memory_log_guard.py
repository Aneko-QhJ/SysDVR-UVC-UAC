"""SDK access ranges and failed-GetSize preservation, with exact logger bodies."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_memory_log_guard as audit
import analyze_a23_sdk_memory as m
from workflows.artifacts import verify


class MemoryLogGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verify(audit.SEALED);verify(audit.ELFS)
        p=audit.ELFS/'dormant';cls.blob=(p/'full.elf').read_bytes();cls.text=(p/'disassembly.txt').read_text()
        cls.catalog=json.loads((audit.SEALED/'linked-catalog.json').read_text())
        cls.fs,cls.meta,_,literals=audit.prior.prior.build_inputs(cls.blob,cls.text,cls.catalog);cls.address=next(iter(literals.values()))
        cls.tmp=tempfile.TemporaryDirectory();cls.folder=Path(cls.tmp.name);cls.commands=[]
        cls.native=audit.native_audit(cls.folder,cls.catalog,cls.commands)
        cls.objects=audit.arm_objects(cls.folder,cls.commands)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def model(self,helper='strlen',length=5,**kwargs):return m.MemoryMachine(self.fs,self.blob,self.meta,self.address,helper,length,**kwargs)

    def row(self,scenario='size-error',value=7,guard=True):
        return next(r for r in self.native['rows']['guarded' if guard else 'baseline'] if (r['scenario'],r['value'])==(scenario,value))

    def test_sdk_memory_helpers_are_static_leaf_frames_zero(self):
        for name in ('memcpy','memset','strlen'):
            f=next(f for f in self.fs.values() if f['name']==name);frame=m.fmt.scan.parser.arg.elf.frame_range(f,self.fs)
            self.assertEqual(frame['frame_bytes'],0);self.assertEqual(frame['edges'],[]);self.assertEqual(frame['unresolved'],[])

    def test_memcpy_boundary_sizes_preserve_destination_sentinels(self):
        for n in audit.COPY_LENGTHS:
            row=self.model('memcpy',n,source_offset=7,destination_offset=15).run_helper()
            self.assertTrue(row['stack_restored'])

    def test_memset_small_sizes_and_byte_truncation(self):
        for n in audit.SET_LENGTHS:
            self.model('memset',n,destination_offset=7,byte=0x1ff).run_helper()

    def test_strlen_page_end_and_vector_lengths_return_exact_length(self):
        for offset in (0xfe0,0xfe1,0xfff):
            for n in audit.STRING_LENGTHS:
                row=self.model('strlen',n,source_offset=offset).run_helper();self.assertEqual(row['return_value'],n)

    def test_strlen_reads_beyond_nul_and_page_aligned_prefix(self):
        after=self.model('strlen',0).run_helper();before=self.model('strlen',64,source_offset=0xfff).run_helper()
        self.assertGreater(after['logical_string_read_after_nul'],0);self.assertEqual(before['logical_string_read_before'],31)

    def test_strlen_missing_mapped_padding_fails_closed(self):
        model=self.model('strlen',0);del model.mem[model.source_address+1]
        with self.assertRaisesRegex(m.fmt.scan.ScanError,'Uninitialized'):model.run_helper()

    def test_large_memset_architectural_zeroing_stays_a_frontier(self):
        with self.assertRaisesRegex(m.MemoryError,'DCZID'):self.model('memset',192,byte=0).run_helper()

    def test_helper_budget_and_actual_instruction_byte_drift_reject(self):
        with self.assertRaisesRegex(m.MemoryError,'budget'):self.model().run_helper(budget=1)
        f=next(f for f in self.fs.values() if f['name']=='strlen');pc=f['start'];section=next(s for s in self.meta['sections'] if s['flags']&4 and s['address']<=pc<s['address']+s['size'])
        blob=bytearray(self.blob);blob[section['offset']+pc-section['address']]^=1
        with self.assertRaises(m.fmt.scan.parser.arg.elf.BoundaryError):audit.prior.prior.build_inputs(bytes(blob),self.text,self.catalog)

    def test_baseline_size_failure_can_modify_existing_log_at_zero(self):
        row=self.row(guard=False);self.assertEqual((row['writes'],row['write_offset']),(1,0));self.assertFalse(row['existing_file_unchanged'])

    def test_guard_rejects_unchanged_poison_negative_and_huge_error_outputs(self):
        for scenario in audit.SIZE_FAILURES:
            for n in (7,513):
                row=self.row(scenario,n);self.assertEqual((row['sizes'],row['writes'],row['closes']),(1,0,1));self.assertTrue(row['existing_file_unchanged'])

    def test_catalog_success_nonpositive_and_write_errors_are_unchanged(self):
        before={(r['scenario'],r['value']):r for r in self.native['rows']['baseline']}
        for row in self.native['rows']['guarded']:
            if row['scenario'] not in audit.SIZE_FAILURES:self.assertEqual(row,before[row['scenario'],row['value']])

    def test_partial_write_error_does_not_claim_rollback(self):
        for guard in (False,True):
            row=self.row('partial-write',7,guard=guard);self.assertFalse(row['existing_file_unchanged']);self.assertEqual(row['closes'],1)

    def test_arm_object_branches_size_error_directly_to_close(self):
        for profile in self.objects.values():
            self.assertFalse(profile['baseline']['size_failure_skips_write']);self.assertTrue(profile['guarded']['size_failure_skips_write'])
            self.assertEqual(profile['guarded']['logger_frame_bytes'],832)
            self.assertFalse(profile['guarded']['full_elf_linked']);self.assertFalse(profile['guarded']['arm_executed'])

    def test_object_guard_disassembly_or_byte_drift_is_rejected(self):
        p=self.folder/'dormant/guarded';blob=(p/'core.o').read_bytes();text=(p/'logger-disassembly.txt').read_text()
        with self.assertRaises(AssertionError):audit.object_certificate(blob,text.replace('cbnz','cbz'),True)
        with self.assertRaises(AssertionError):audit.object_certificate(blob,text.replace('cbz\tw0','cbnz\tw0'),True)
        meta=m.fmt.scan.parser.arg.elf.elf_metadata(blob);s=next(s for s in meta['sections'] if s['name']=='.text.LogFunctionImpl')
        changed=bytearray(blob);changed[s['offset']]^=1
        with self.assertRaises(AssertionError):audit.object_certificate(bytes(changed),text,True)

    def test_prior_sources_seals_and_hardware_ticket_preserved(self):
        verify(audit.SEALED);verify(audit.ELFS)
        old=json.loads((audit.SEALED/'audit.json').read_text())
        for name,h in old['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/name),h)
        for name,h in old['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.ELFS.parent/name),h)
        self.assertNotEqual(audit.logger_source(),audit.logger_source(True))


if __name__=='__main__':unittest.main()
