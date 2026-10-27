"""Offline review must preserve native failures and immutable evidence."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_a23_offline as audit


class OfflineAuditTests(unittest.TestCase):
    def test_saved_native_failure_is_not_salvaged_by_correct_raw(self):
        run = ROOT / 'private/runs/A-A23-HS-matched-serial-20261011-221215'
        audit.verify_manifest(run)
        e = audit.saved_transfer(run)
        self.assertEqual(len(e['attempts']), 1)
        a = e['attempts'][0]
        self.assertTrue(a['exact_raw'] and a['terminal'])
        self.assertEqual(audit.classify(a), 'native_error_with_correct_raw_and_device_completion')
        batches = audit.native_batches(audit.rows(run / 'native-stderr.txt'))
        self.assertEqual(len(batches), 1)
        self.assertEqual(sum(r['status'] == 0xE000400E for r in batches[0]), 293)

    def test_saved_cc23_failure_remains_a_separate_failure_class(self):
        run = ROOT / 'private/runs/A-A23-HS-matched-serial-20261009-223428'
        audit.verify_manifest(run)
        e = audit.saved_transfer(run)
        self.assertEqual(len(e['attempts']), 4)
        self.assertTrue(all(a['passed'] for a in e['attempts'][:3]))
        self.assertEqual(audit.classify(e['attempts'][3]), 'incomplete_device_completion')
        self.assertEqual(len(e['attempts'][3]['indices']), 14)

    def test_tampered_or_outside_manifest_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            raw = folder / 'raw.bin'
            raw.write_bytes(b'original')
            (folder / 'SHA256SUMS').write_text(audit.sha(raw) + '  raw.bin\n')
            raw.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Frozen evidence mismatch'):
                audit.verify_manifest(folder)
            (folder / 'SHA256SUMS').write_text('0' * 64 + '  ../outside\n')
            with self.assertRaisesRegex(ValueError, 'Unsafe manifest path'):
                audit.verify_manifest(folder)

    def test_existing_output_is_rejected_before_any_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'keep.txt'
            marker.write_text('keep')
            with patch.object(sys, 'argv', ['audit', '--output', tmp]), \
                    patch.object(audit, 'source_review') as source, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    audit.main()
                source.assert_not_called()
            self.assertEqual(marker.read_text(), 'keep')

    def test_scheduling_replacement_cannot_be_reported_as_pure_observation(self):
        old = 'frame += 64;\nReadIsochPipeAsync();\n'
        changed = 'frame += 32;\nReadIsochPipeAsync();\n'
        self.assertFalse(audit.insertions(old, changed)['only_insertions'])


if __name__ == '__main__':
    unittest.main()
