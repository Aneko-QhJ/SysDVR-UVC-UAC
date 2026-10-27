import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_lead32_receiver as b
import a23_lead32_binding as binding
import path_span_card_workflow as card


class Lead32Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review=b.ROOT/'private/analysis/A23-lead32-receiver-review-20261017-r4'
        cls.result=b.load(cls.review/'audit.json');cls.record=cls.result['offline_record'];cls.build=Path(cls.record['build'])
        cls.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');cls.root=Path(cls.tmp.name).resolve()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_new_plan_and_description_are_native_bound(self):
        self.assertEqual(b.verify_build(self.record),self.build)
        described=json.loads(subprocess.check_output([str(self.build/'receiver'),'--describe']))
        self.assertEqual(described,b.description(self.record['device_binding']))
        self.assertEqual(described['entry_plan']['sdk_plan']['first_frame_lead'],32)
        self.assertEqual(described['host_configuration'],'host-lead32-window-1')

    def test_budget_sum_and_deadlines(self):
        sdk=b.WAIT_PLAN['sdk_plan'];budget=sdk['runtime_budget']
        self.assertEqual(budget['max_frame_age_ns']+budget['max_enqueue_call_ns']+sdk['max_trigger_gap_ns'],sdk['max_trigger_age_ns'])
        self.assertEqual(sdk['max_trigger_age_ns']+sdk['control_deadline_ns'],sdk['max_trigger_end_age_ns'])
        self.assertEqual(sdk['max_trigger_end_age_ns']+budget['reserve_ns'],32000000)
        self.assertEqual(sdk['control_deadline_ns'],16000000)
        self.assertEqual(sdk['iso_deadline_ns'],2000000000)

    def test_device_bytes_identical_and_record_dormant(self):
        parent=b.load(b.ROOT/'private/analysis/A23-path-span-receiver-review-20261016/offline-record.json')
        self.assertEqual(parent['device_binding'],self.record['device_binding'])
        self.assertEqual(self.record['remaining'],0);self.assertFalse(self.record['acquisition_enabled'])
        self.assertNotEqual(parent['receiver_sha256'],self.record['receiver_sha256'])

    def test_old_or_mixed_receipts_rejected_without_claim(self):
        for name,row in self.result['claim_cases'].items():
            if name!='matching':self.assertEqual(row['process_returncode'],2,name)
        good=self.result['claim_cases']['matching']
        self.assertEqual(good['sdk_returncode'],0)
        self.assertEqual(good['repeat_process_returncode'],2);self.assertEqual(good['repeat_sdk_returncode'],2)

    def test_injected_waiting_and_driver_cases_present(self):
        cases=self.result['native_cases'];self.assertEqual(len(cases['loop']),12);self.assertEqual(len(cases['driver']),34)
        self.assertTrue(cases['loop']['normal']['result']['finished'])
        self.assertEqual(cases['driver']['iso-first']['transfer']['active_indices'],list(range(512,528)))
        self.assertIsNone(cases['driver']['foreign-pointer']['transfer'])
        self.assertEqual(cases['driver']['foreign-pointer']['result']['exit_code'],1)

    def test_exact_boundary_model_passed(self):
        self.assertEqual(self.result['policy_boundary_assertions'],11)
        self.assertIn('11 exact boundary',(self.review/'policy.log').read_text())

    def test_receipts_do_not_share_mutable_plan(self):
        receipt=binding.receipt(self.record);receipt['plan']['sdk_plan']['first_frame_lead']=64
        self.assertEqual(binding.WAIT_PLAN['sdk_plan']['first_frame_lead'],32)

    def test_generated_sources_and_closure_bound(self):
        meta=b.load(self.build/'manifest.json');self.assertEqual(len(meta['generated_hashes']),11)
        self.assertEqual(len(meta['source_hashes']),241)
        self.assertIn('A23Lead32Trigger',(self.build/'generated/io_usb_host_burst_sdk_transport.m').read_text())

    def test_old_record_cannot_pass_new_build_verifier(self):
        old=b.load(b.ROOT/'private/analysis/A23-path-span-receiver-review-20261016/offline-record.json')
        with self.assertRaises(ValueError):b.verify_build(old)
        bad={**self.record,'plan':binding.PREVIOUS_PLAN}
        with self.assertRaises(ValueError):b.verify_build(bad)

    def test_resealed_generated_change_fails_native_check(self):
        target=self.root/'resealed';shutil.copytree(self.build,target)
        p=target/'generated/io_usb_host_burst_sdk_transport.m';p.write_bytes(p.read_bytes()+b' ')
        for n in ('SHA256SUMS','COMMITTED'):(target/n).unlink()
        b.seal(target)
        r=subprocess.run([str(target/'receiver'),'--check-build',str(target)],capture_output=True,text=True)
        self.assertEqual(r.returncode,2)

    def test_noninteger_or_boolean_lead_rejected(self):
        for value in (True,32.0,64):
            bad={**self.record,'plan':json.loads(json.dumps(self.record['plan']))}
            bad['plan']['sdk_plan']['first_frame_lead']=value
            with self.assertRaises(ValueError):b.verify_build(bad)

    def test_no_live_authority_or_new_device_artifacts(self):
        for flag in ('attempt_issued','receiver_acquire_invoked','device_rebuilt','firmware_packaged','hardware_verified','issuer_ready','collection_analyzer_ready'):
            self.assertIs(self.result[flag],False)
        for name,h in self.result['live_records_sha256'].items():self.assertEqual(b.sha(b.plain(b.ROOT/'private/analysis'/name)),h)
        self.assertEqual(self.result['remaining'],0)


if __name__=='__main__':unittest.main()
