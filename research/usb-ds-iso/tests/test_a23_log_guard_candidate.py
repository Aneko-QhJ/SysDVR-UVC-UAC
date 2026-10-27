"""Linked GetSize guard, new recipe binding and preserved isolated lifecycle evidence."""
import json
import os
import re
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_a23_log_guard_candidate as m
from workflows.artifacts import verify


class LogGuardCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(os.environ.get('A23_LOG_GUARD_REVIEW', str(ROOT/'private/analysis/A23-log-guard-candidate-review-20261015')))
        verify(cls.folder)
        cls.audit = json.loads((cls.folder/'audit.json').read_text())
        cls.old = json.loads((m.SEALED/'audit.json').read_text())

    def test_new_recipes_link_thirteen_objects_and_are_present_in_readonly_elf(self):
        recipes = []
        for label, row in self.audit['builds'].items():
            self.assertEqual(row['object_count'], 13)
            self.assertTrue(row['linked'])
            self.assertFalse(row['executed'])
            self.assertEqual(row['strict_format_units'], 13)
            recipe = json.loads((self.folder/label/'recipe.json').read_text())
            self.assertEqual(m.digest(recipe['configuration']), row['runtime_recipe_digest'])
            self.assertNotEqual(row['runtime_recipe_digest'], self.old['builds'][label]['runtime_recipe_digest'])
            self.assertIn(bytes.fromhex(row['runtime_recipe_digest']), (self.folder/label/'full.elf').read_bytes())
            self.assertTrue(row['recipe_readonly_sections'])
            recipes.append(row['runtime_recipe_digest'])
        self.assertNotEqual(*recipes)

    def test_only_logger_and_recipe_header_change(self):
        for label in m.LABELS:
            before, after = m.SEALED/label/'source', self.folder/label/'source'
            a = {p.relative_to(before).as_posix(): p.read_bytes() for p in before.rglob('*') if p.is_file()}
            b = {p.relative_to(after).as_posix(): p.read_bytes() for p in after.rglob('*') if p.is_file()}
            self.assertEqual(a.keys(), b.keys())
            self.assertEqual(sorted(n for n in a if a[n] != b[n]), ['core.c', 'uvc/ep0_candidate_recipe.h'])
            self.assertEqual(b['core.c'].decode(), a['core.c'].decode().replace(m.guard.logger_source(False), m.guard.logger_source(True)))
            self.assertEqual(b['core.c'].decode().count(m.guard.logger_source(True)), 1)

    def test_final_linked_logger_guard_and_clamp_are_rederived_from_elf(self):
        for label, row in self.audit['builds'].items():
            p = self.folder/label
            actual = m.linked_logger((p/'full.elf').read_bytes(), (p/'disassembly.txt').read_text())
            self.assertEqual(actual, row['logger_machine'])
            self.assertEqual(actual['logger_frame_bytes'], 832)
            self.assertEqual(actual['max_write_bytes'], 511)
            for path in actual['result_paths']:
                self.assertEqual(path['calls'], ['fsFileWrite', 'fsFileClose'] if path['result'] == 0 else ['fsFileClose'])

    def mutated(self, pc, transform, old_text, new_text):
        p = self.folder/'dormant'
        blob = bytearray((p/'full.elf').read_bytes())
        text = (p/'disassembly.txt').read_text()
        meta = m.oldbuild.boundaries.elf_metadata(bytes(blob))
        section = next(s for s in meta['sections'] if s['flags'] & 4 and s['address'] <= pc < s['address']+s['size'])
        at = section['offset']+pc-section['address']
        word = int.from_bytes(blob[at:at+4], 'little')
        changed = transform(word)
        blob[at:at+4] = changed.to_bytes(4, 'little')
        pattern = re.compile(r'(^\s*'+format(pc, 'x')+r':\s+)'+format(word, '08x')+r'(\s+.*)$', re.M)
        text, count = pattern.subn(lambda x: x[1]+format(changed, '08x')+x[2].replace(old_text, new_text), text)
        self.assertEqual(count, 1)
        return bytes(blob), text

    def test_joint_byte_and_text_inversion_of_result_guard_rejects(self):
        pc = self.audit['builds']['dormant']['logger_machine']['calls']['fsFileGetSize']+8
        blob, text = self.mutated(pc, lambda word: word ^ (1 << 24), 'cbz\tw0', 'cbnz\tw0')
        with self.assertRaises(AssertionError):
            m.linked_logger(blob, text)

    def test_joint_byte_and_text_change_of_limit_rejects(self):
        pc = self.audit['builds']['dormant']['logger_machine']['calls']['fsFileWrite']-24
        blob, text = self.mutated(pc, lambda word: (word & ~(0xfff << 10)) | (512 << 10), '#0x1ff', '#0x200')
        with self.assertRaises(AssertionError):
            m.linked_logger(blob, text)

    def test_linked_call_target_tampering_rejects(self):
        pc = self.audit['builds']['dormant']['logger_machine']['calls']['fsFileClose']
        blob, text = self.mutated(pc, lambda word: word ^ 1, '<fsFileClose>', '<fsFileClose>')
        with self.assertRaises(AssertionError):
            m.linked_logger(blob, text)

    def test_disassembly_and_elf_byte_drift_rejects(self):
        p = self.folder/'dormant'
        blob, text = (p/'full.elf').read_bytes(), (p/'disassembly.txt').read_text()
        with self.assertRaises(m.oldbuild.boundaries.BoundaryError):
            m.linked_logger(blob, text.replace('34000080', '35000080', 1))

    def test_91_legacy_observations_preserved_for_each_configuration(self):
        def raw(rows):
            return {r['case']: {k: v for k, v in r.items() if k not in ('session', 'disk_session', 'startup_journal')} for r in rows}
        for row in self.audit['lifecycle'].values():
            self.assertEqual(row['native_checks'], 91)
            self.assertTrue(row['log_is_noop'])
            for key in ('startup_cases', 'shutdown_cases', 'file_cases'):
                self.assertEqual(raw(row[key]), raw(self.old[key]))
            self.assertEqual(row['limit_policy'], self.old['limit_policy'])
        self.assertEqual(self.audit['native_lifecycle_checks'], 182)

    def test_logger_faults_preserve_original_file_only_when_size_guard_succeeds(self):
        rows = self.audit['native_log_checks']['rows']
        baseline = {(r['scenario'], r['value']): r for r in rows['baseline']}
        for row in rows['guarded']:
            if row['scenario'] in m.guard.SIZE_FAILURES:
                self.assertEqual((row['writes'], row['closes']), (0, 1))
                self.assertTrue(row['existing_file_unchanged'])
            else:
                self.assertEqual(row, baseline[row['scenario'], row['value']])
        self.assertEqual(self.audit['native_log_checks']['total_checks'], 194)
        self.assertFalse(baseline['size-error', 7]['existing_file_unchanged'])
        partial = next(r for r in rows['guarded'] if (r['scenario'], r['value']) == ('partial-write', 7))
        self.assertFalse(partial['existing_file_unchanged'])

    def test_fixed_path_wait_and_closed_save_graph_remain_conditional(self):
        self.assertEqual(self.audit['path_policy'], self.old['path_policy'])
        for label, data in self.audit['stack_analysis'].items():
            for name, bound in (('Ep0SessionSaveJoined', 768), ('session_capture', 352)):
                self.assertTrue(data['roots'][name]['closed_direct_graph'])
                self.assertEqual(data['roots'][name]['stack_bound_bytes'], bound)
            self.assertFalse(data['whole_thread_stack_verified'])
            self.assertEqual(self.audit['wait_audit'][label]['model']['profile_count'], 156)

    def test_recipe_hashes_inputs_and_external_toolchain(self):
        recipe = json.loads((self.folder/'recipe.json').read_text())
        self.assertEqual(m.digest(recipe['inputs']), self.audit['recipe_digest'])
        for n, h in self.audit['source_hashes'].items():
            self.assertEqual(m.base.ep0.sha(ROOT/n), h)
        for path, h in recipe['inputs']['external_sha256'].items():
            self.assertEqual(m.base.ep0.sha(Path(path)), h)
        self.assertEqual(m.base.ep0.sha(m.SEALED/'SHA256SUMS'), recipe['inputs']['sealed_manifest_sha256'])

    def test_sealed_inputs_production_and_tickets_preserved_without_hardware(self):
        verify(m.SEALED)
        verify(m.GUARD)
        for n, h in self.audit['production_sources_sha256'].items():
            self.assertEqual(m.base.ep0.sha(m.REPO/n), h)
        for n, h in self.audit['tickets_sha256'].items():
            self.assertEqual(m.base.ep0.sha(m.SEALED.parent/n), h)
        ticket = json.loads((m.SEALED.parent/'A23-IOUSBHost-burst-next-test.json').read_text())
        self.assertEqual((ticket['stage'], ticket['remaining'], ticket['acquisition_enabled']), ('failed_no_retry', 0, False))
        for key in ('arm_executed', 'firmware_packaged', 'usb_accessed', 'sd_accessed', 'whole_thread_stack_verified', 'root_cause_confirmed', 'production_modified', 'prior_evidence_modified'):
            self.assertFalse(self.audit[key])


if __name__ == '__main__':
    unittest.main()
