"""Fresh binding, rejection, and worker-return contracts from native evidence."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_live126_interepoch as b

class Fresh126(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(os.environ['A23_LIVE126_REVIEW']);b.core.verify_seal(p);cls.r=b.w.load(p/'report.json')
    def test_new_chain_and_scope(self):
        v=self.r['accepted']['normal'];self.assertEqual([x['first_sequence'] for x in v['sdk']['epochs']],[417,433,449]);self.assertEqual(v['sdk']['total_bytes'],9216)
        self.assertEqual(v['checked_export']['candidate_binding']['source_closure_sha256'],b.sha(b.encode(self.r['source_hashes'])))
    def test_spent369_and_new_source_rejected_before_open(self):
        for n in ('spent369-drift','spent369-extra','spent369-missing','new-source-pre','frozen-spent369','archive-new-main'):
            self.assertFalse(self.r['matrix'][n]['initial_core']);self.assertEqual(self.r['matrix'][n]['calls']['opens'],0)
    def test_old_scope_wrong_count_baseline_and_late_change(self):
        for n in ('old369-scope','count32-reservation'):self.assertEqual(self.r['matrix'][n]['calls']['opens'],0)
        self.assertEqual(self.r['matrix']['baseline126-pre']['calls']['iso_submissions'],0)
        self.assertEqual(self.r['matrix']['between-third-source']['calls']['iso_submissions'],2)
    def test_operator_ack_does_not_skip_worker_return(self):
        r=self.r['matrix']['exit-worker-ack'];self.assertTrue(r['worker_exit_deferred']);self.assertEqual(r['interepoch_guard']['worker_returns'],1);self.assertEqual(r['interepoch_guard']['resumed_polls'],0);self.assertTrue(r['loop']['finished'])
    def test_old_workflow_and_synthetic_upgrade_rejected(self):
        for n in ('old120-consumer','old120-workflow','synthetic-as-real','missing-authorization'):self.assertIn(n,self.r['rejections'])
    def test_file_modes_and_no_physical_mutation(self):
        self.assertEqual(self.r['source_count'],651);self.assertEqual(self.r['file_modes']['unissued']['returncode'],2)
        for n in ('formal_namespaces_added','formal_authorizations','formal_ranges','real_sdk_objects','usb_requests','sd_accesses','remaining'):self.assertEqual(self.r[n],0)

if __name__=='__main__':unittest.main()
