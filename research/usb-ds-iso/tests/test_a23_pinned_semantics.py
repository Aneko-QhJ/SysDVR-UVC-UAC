from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_a23_pinned_semantics as audit


class PinnedSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = None
        if os.environ.get('A23_SEMANTICS_REVIEW'):
            cls.root = Path(os.environ['A23_SEMANTICS_REVIEW'])
        else:
            cls.tmp = tempfile.TemporaryDirectory(prefix='a23-semantic-test-', dir='/private/tmp')
            cls.root = Path(cls.tmp.name) / 'review'
            audit.run(cls.root)
        audit.a.sealed(cls.root)
        cls.report = audit.f.load(cls.root / 'audit.json')
        cls.rows = cls.report['cases']

    @classmethod
    def tearDownClass(cls):
        if cls.tmp: cls.tmp.cleanup()

    def test_frozen413_preserves410(self):
        self.assertEqual(len(audit.sources()), 413)
        self.assertEqual(self.report['prior_sources_unchanged'], 410)

    def test_baseline_is_consistent_partial_only(self):
        row = audit.f.load(self.root / 'models/normal/analysis.json')
        self.assertTrue(row['selected_relations_consistent'])
        self.assertEqual(row['classification'], 'consistent_partial_model_bytes')
        for name in audit.model.FALSE: self.assertIs(row[name], False)

    def test_valid_bytes_do_not_imply_valid_semantics(self):
        failures = [r for r in self.rows.values() if r['errors']]
        self.assertEqual(len(failures), 19)
        self.assertTrue(all(r['byte_scope_verified'] and r['disk_view_verified'] for r in failures))

    def test_malformed_duplicate_nonobject_deep_json_refused(self):
        for name in ('marker-malformed', 'marker-duplicate', 'marker-nonobject', 'marker-deep'):
            self.assertEqual(self.rows[name]['errors'], ['attempt_shape'])

    def test_bool_pid_and_build_count_cannot_substitute_integer(self):
        for name in ('bool-pid', 'bool-build-count'):
            self.assertEqual(self.rows[name]['errors'], ['attempt_shape'])

    def test_authority_and_unknown_fields_refused(self):
        for name in ('authority', 'unknown-attempt-field', 'unknown-event-field', 'unknown-job-field'):
            self.assertTrue(self.rows[name]['errors'])

    def test_nonce_paths_and_declared_build_mismatch_refused(self):
        for name in ('nonce', 'overlapping-paths', 'volume-path', 'mismatched-build'):
            self.assertEqual(self.rows[name]['errors'], ['attempt_shape'])

    def test_copy_and_first_event_links_checked(self):
        self.assertEqual(self.rows['attempt-copy']['errors'], ['attempt_copies'])
        for name in ('bool-event-index', 'event-link'):
            self.assertEqual(self.rows[name]['errors'], ['first_event_link'])

    def test_job_shape_and_raw_size_checked(self):
        self.assertEqual(self.rows['job-id']['errors'], ['job_id_shape'])
        self.assertEqual(self.rows['short-raw']['errors'], ['raw_size'])

    def test_raw_change_remains_explicitly_opaque(self):
        row = audit.f.load(self.root / 'models/opaque-raw-change/analysis.json')
        self.assertTrue(row['selected_relations_consistent'])
        self.assertFalse(row['epoch_payload_verified'])
        self.assertFalse(row['transactions_verified'])
        self.assertEqual(row['raw_interpretation'], 'opaque_without_transactions_or_status')

    def test_logical_paths_are_not_followed(self):
        self.assertEqual(self.rows['nonexistent-logical-roots']['errors'], [])
        self.assertEqual(self.report['semantic_consumer_filesystem_opens'], [])
        self.assertGreater(self.report['semantic_consumer_read_calls'], 130)

    def test_disk_mutations_leave_cached_semantics_unchanged(self):
        self.assertEqual(len(self.report['storage_mutations']), 3)
        self.assertTrue(all(r['cached_analysis_unchanged'] and r['fresh_load_refused']
                            for r in self.report['storage_mutations'].values()))

    def test_seven_scope_and_cache_rejections(self):
        self.assertEqual(len(self.report['scope_rejections']), 7)
        self.assertTrue(all(self.report['scope_rejections'].values()))
        raw = (self.root / 'bundle/origin-SHA256SUMS').read_bytes()
        duplicate = raw + raw.splitlines(keepends=True)[0]
        with self.assertRaisesRegex(ValueError, 'duplicate manifest name'):
            audit.model.manifest_entries(duplicate, audit.f.sha(duplicate))

    def test_no_hardware_or_formal_namespace(self):
        for name in ('usb_requests', 'sd_accesses', 'real_sdk_objects', 'formal_records', 'formal_reservations'):
            self.assertEqual(self.report[name], 0)
        self.assertFalse(self.report['native_build_used'])
        self.assertFalse((ROOT / 'private/sequence-reservations32').exists())


if __name__ == '__main__': unittest.main()
