import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import audit_io_usb_host_framework as audit


class FrameworkAuditTest(unittest.TestCase):
    def test_bytes_with_labels_use_printed_unslid_address(self):
        text = 'method:\n0x1000: 01 02 03 04 \n0x1004: 05 06 07 08 \n'
        self.assertEqual(audit.parse_text_bytes(text), (0x1000, bytes(range(1, 9))))

    def test_missing_or_overlapping_bytes_rejected(self):
        for address in ('1008', '1000'):
            with self.assertRaises(ValueError):
                audit.parse_text_bytes(f'0x1000: 01 02 03 04\n0x{address}: 05 06\n')

    def test_malformed_or_empty_bytes_rejected(self):
        for text in ('label only', '0x1000: ZZ FF'):
            with self.assertRaises(ValueError):
                audit.parse_text_bytes(text)

    def test_function_ranges_and_hashes(self):
        metadata = '    -function_starts:\n        0x1000  first\n        0x1004  second\n    -objc:\n'
        rows = audit.function_ranges(metadata, 0x1000, bytes(range(8)))
        self.assertEqual([(r['addr'], r['end']) for r in rows], [(0x1000, 0x1004), (0x1004, 0x1008)])
        self.assertEqual(rows[1]['sha256'], audit.digest(bytes(range(4, 8))))

    def test_function_outside_text_rejected(self):
        metadata = '    -function_starts:\n        0x1000  first\n        0x1010  second\n'
        with self.assertRaises(ValueError):
            audit.function_ranges(metadata, 0x1000, bytes(8))

    def test_existing_evidence_refused_before_system_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                audit.export(Path(directory))


if __name__ == '__main__':
    unittest.main()
