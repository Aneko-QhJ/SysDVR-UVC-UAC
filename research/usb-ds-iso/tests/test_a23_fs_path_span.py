import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_a23_fs_path_span as a

class PathSpanTests(unittest.TestCase):
    def text(self):return (a.DEVICE/'disassembly.txt').read_text()
    def test_actual_linked_paths_have_identical_boundary_geometry(self):
        result=a.linked_layout(self.text());rows=list(result['paths'].values())
        self.assertEqual(rows[0]['geometry'],rows[1]['geometry'])
        self.assertEqual(rows[0]['geometry']['start_from_main_entry_sp'],-480)
        self.assertEqual(rows[0]['geometry']['end_exclusive_from_main_entry_sp'],289)
    def test_actual_descriptor_is_full_width(self):
        self.assertEqual(a.linked_layout(self.text())['span_bytes'],769)
    def test_changed_sdk_immediate_is_rejected(self):
        with self.assertRaises(ValueError):a.linked_layout(self.text().replace('w0, #0x3010000','w0, #0x6010000'))
    def test_changed_caller_offset_is_rejected(self):
        with self.assertRaises(ValueError):a.linked_layout(self.text().replace('x1, sp, #0x130','x1, sp, #0x120'))
    def test_unknown_mapping_is_not_claimed_as_measured(self):
        r=a.linked_layout(self.text());self.assertFalse(r['runtime_mapping_measured']);self.assertFalse(r['kernel_error_reproduced'])
    def test_mapping_slack_changes_modeled_crossing(self):
        self.assertTrue(a.geometry(128,496,144,slack=288)['crosses_assumed_upper_bound'])
        self.assertFalse(a.geometry(128,496,144,slack=289)['crosses_assumed_upper_bound'])
    def test_larger_lower_stack_does_not_change_upper_span(self):
        self.assertEqual(a.geometry(128,496,144)['end_exclusive_from_main_entry_sp'],289)
        with self.assertRaises(ValueError):a.geometry(128,496,496)
        with self.assertRaises(ValueError):a.geometry(-1,496,144)
    def test_guard_pages_and_all_path_lengths(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-path-span-') as folder:
            binary=Path(folder)/'model'
            subprocess.run(['clang','-std=c11','-D_DARWIN_C_SOURCE','-O2','-Wall','-Wextra','-Werror','-I'+str(a.b.ROOT/'device'),str(a.b.ROOT/'tests/a23_fs_path_span_fixture.c'),'-o',str(binary)],check=True,capture_output=True)
            r=json.loads(subprocess.check_output([str(binary)]));self.assertEqual(r['length_cases'],769)
            self.assertTrue(r['guarded_full_span_readable']);self.assertTrue(r['guarded_short_span_rejected']);self.assertFalse(r['kernel_emulated'])

if __name__=='__main__':unittest.main()
