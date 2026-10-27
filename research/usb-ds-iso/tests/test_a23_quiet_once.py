"""File-only issuance and existing consume-before-launch gate, using temporary records."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_a23_quiet_once as once


class OnceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/private/tmp', prefix='a23-issuance-model-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'A23-quiet-once-model.json'
        self.before = once.build.plain(once.OFFLINE)

    def tearDown(self):
        self.assertEqual(once.build.plain(once.OFFLINE), self.before)

    def test_preview_does_not_write_or_launch(self):
        with patch.object(once.gate.subprocess, 'Popen') as launch:
            result = once.prepare(self.path)
        self.assertFalse(result['record_written']); self.assertFalse(self.path.exists())
        self.assertEqual(result['remaining'], 0); launch.assert_not_called()
        self.assertEqual(result['scope']['exefs_nsp_sha256'], '81314284637a81fd5a6f9564383533b14168a62cababb51b9a6d156c643080f3')

    def test_temporary_issue_is_accepted_by_existing_gate_without_launch(self):
        with patch.object(once.gate.subprocess, 'Popen') as launch:
            result = once.prepare(self.path, issue=True)
            record = once.build.load(self.path)
            checked = once.gate.capture(self.path, dry_run=True)
        launch.assert_not_called(); self.assertTrue(result['record_written'])
        self.assertEqual(record['remaining'], checked['remaining']); self.assertEqual(record['remaining'], 1)
        self.assertNotEqual(record['preparation_id'], once.build.load(once.OFFLINE)['preparation_id'])
        self.assertEqual(record['issuance']['scope']['device_binding_sha256'], record['device_binding_sha256'])
        self.assertFalse(record['issuance']['automatic_retry'])

    def test_existing_and_consumed_records_cannot_be_refilled(self):
        once.prepare(self.path, issue=True)
        for consumed in (False, True):
            if consumed:
                record = once.build.load(self.path); record.update(stage='failed_no_retry', remaining=0, acquisition_enabled=False)
                self.path.write_bytes(once.build.canonical(record))
            before = self.path.read_bytes()
            with self.assertRaises(ValueError): once.prepare(self.path, issue=True)
            self.assertEqual(self.path.read_bytes(), before)

    def test_partial_output_preserved(self):
        self.path.write_bytes(b'{partial')
        with self.assertRaises(ValueError): once.prepare(self.path, issue=True)
        self.assertEqual(self.path.read_bytes(), b'{partial')

    def test_bad_destination_rejected_before_material_reads(self):
        for path in (once.OFFLINE, once.PACKAGE/'A23-quiet-once-new.json', Path('/Volumes/A23-quiet-once-new.json'),
                     self.path.with_name('A23-next-test.json'), Path('/tmp/A23-quiet-once-model.json')):
            with self.subTest(path=path), patch.object(once, 'materials') as check, self.assertRaises(ValueError):
                once.prepare(path, issue=True)
            check.assert_not_called()

    def test_changed_materials_cannot_issue(self):
        source, scope = once.materials(); changed = copy.deepcopy(scope); changed['exefs_nsp_sha256'] = '00'*32
        with patch.object(once, 'materials', side_effect=[(source, scope), (source, changed)]):
            with self.assertRaises(ValueError): once.prepare(self.path, issue=True)
        self.assertFalse(self.path.exists())

    def test_wrong_validation_cannot_issue(self):
        with patch.object(once.gate, 'verify_validation', side_effect=ValueError('wrong validation')):
            with self.assertRaises(ValueError): once.prepare(self.path, issue=True)
        self.assertFalse(self.path.exists())

    def test_exclusive_create_race_keeps_other_record(self):
        original = once.build.write
        def race(path, record):
            path.write_bytes(b'other-writer')
            return original(path, record)
        with patch.object(once.build, 'write', side_effect=race):
            with self.assertRaises(FileExistsError): once.prepare(self.path, issue=True)
        self.assertEqual(self.path.read_bytes(), b'other-writer')


if __name__ == '__main__': unittest.main()
