import os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_guard_cadence as a


class CadenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse a completed sealed native audit, never silently launch a matrix.
        cls.path=Path(os.environ['A23_GUARD_CADENCE_REVIEW'])
        cls.report=a.verify(cls.path);cls.matrix=cls.report['native_matrix']

    def test_reduces_real_native_check_invocations(self):
        self.assertEqual(self.matrix['control-normal']['between_epoch_full_checks'],6)
        for n in ('normal','queued-delay'):
            self.assertEqual(self.matrix['candidate-'+n]['between_epoch_full_checks'],1)
            self.assertTrue(self.matrix['candidate-'+n]['snapshot_getters_pure'])

    def test_current_data_changes_cannot_reach_second_iso(self):
        for n in a.CASES:
            if n.startswith('between-epochs-'):
                self.assertEqual(self.matrix['candidate-'+n]['calls']['iso_submissions'],1)
                r=self.matrix['candidate-'+n]
                self.assertTrue(r['verifier']['failed'] or r['native']['permit']['stale'])

    def test_archive_corruption_cannot_open_fake_sdk(self):
        for n in a.ARCHIVES:
            r=self.matrix['candidate-'+n]
            self.assertFalse(r['initial_core']);self.assertEqual(r['calls']['opens'],0)

    def test_sticky_failure_survives_restoration(self):
        r=self.matrix['candidate-restored-after-observed']
        self.assertTrue(r['verifier']['failed']);self.assertEqual(r['calls']['iso_submissions'],0)

    def test_pending_io_skips_hashing_and_never_rearms_after_change(self):
        for n in ('during-pending-source','stopped-pending-source'):
            r=self.matrix['candidate-'+n]
            self.assertTrue(r['full_checks_skipped_while_pending'])
            self.assertEqual(r['calls']['iso_submissions'],1)

    def test_final_export_requires_explicit_fresh_check(self):
        for n in ('before-final-source','after-final-source','after-export-source'):
            r=self.matrix['candidate-'+n]
            self.assertFalse(r['export_accepted']);self.assertFalse(r['entry']['complete'])

    def test_status_evidence_kept_on_rejection(self):
        files=a.w.card.seal_verify(self.path/'cases/candidate-bad-status/host/status-after-epoch-0')
        self.assertEqual(len(files['raw.bin']),168)
        self.assertIn('transferred',a.json.loads(files['verdict.json'])['failed_checks'])

    def test_counts_and_timestamps_are_saved_for_each_full_check(self):
        for name,r in self.matrix.items():
            m=r['cadence'];self.assertEqual(m['full_invocations'],len(m['full_checks']))
            self.assertEqual(m['clock_domain'],'host_CLOCK_MONOTONIC_RAW')
            self.assertTrue(all(x['elapsed_ns']==x['end_ns']-x['begin_ns']>=0 for x in m['full_checks']))

    def test_archive_only_or_missing_full_check_cannot_authorize_live_job(self):
        for n in a.PROBES:
            r=self.matrix['candidate-'+n]
            self.assertFalse(r['live_job_accepted']);self.assertTrue(r['verifier']['failed'])
            self.assertEqual(r['cadence']['full_invocations'],0)
        self.assertTrue(self.matrix['candidate-proof-archive-only']['archive_checked'])

    def test_strict_payload_replay_and_no_hardware_adoption(self):
        self.assertEqual(len(self.report['accepted']),3)
        self.assertEqual(len(self.report['replay_rejections']),6)
        self.assertTrue(all(self.report['replay_rejections'].values()))
        self.assertTrue(all(v['sdk']['status_captures_verified'] and v['sdk']['total_bytes']==6144 for v in self.report['accepted'].values()))
        self.assertFalse(self.report['live_controller_adoption_implemented'])
        self.assertFalse(self.report['hardware_candidate_ready'])
        for key in ('usb_requests','sd_accesses','real_sdk_objects','actual_acquisition_invocations','formal_records','formal_reservations','remaining'):
            self.assertEqual(self.report[key],0)


if __name__=='__main__':unittest.main()
