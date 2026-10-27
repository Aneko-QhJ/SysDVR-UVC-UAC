"""Focused assertions over actual hook execution; no hardware entry point."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_rearm as a


class RearmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='a23-rearm-',dir='/private/tmp')
        cls.output=Path(cls.temporary.name)/'review'
        cls.result=a.run(cls.output);cls.audit=json.loads((cls.output/'audit.json').read_text())
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()
    def test_prior313_and_protected(self):self.assertEqual(len(a.sources()),317)
    def test_recovered_patch(self):
        b=self.audit['binding'];self.assertEqual(b['ips_sha256'],a.IPS_SUM);self.assertEqual(b['edits'],22)
    def test_all247_starts(self):
        rows=self.audit['arm'];self.assertEqual(sum(k.startswith('two-') for k in rows),247)
        for n in range(247):self.assertEqual(rows['two-'+str(n)]['completion_boundaries'],2)
    def test_error_retains(self):
        for n in range(16):self.assertTrue(self.audit['arm']['error-'+str(n)]['second_rejected'])
    def test_late_generation_alias(self):
        x=self.audit['arm']['old-generation-alias'];self.assertEqual(x['first_alias']['ordinal'],16)
        self.assertEqual(x['first_generation_only']['bitmap'],0xff80)
        self.assertEqual(x['first_generation_only']['total'],1728)
        self.assertEqual(x['genuine_current_success_events'],7)
    def test_two_epoch_host(self):
        x=self.audit['host']['cases']['normal'];self.assertEqual(x['submissions'],2);self.assertFalse(x['stopped'])
    def test_host_faults_stop(self):
        for k,x in self.audit['host']['cases'].items():self.assertEqual(x['stopped'],k!='normal')
    def test_no_hardware_or_full_urb_claim(self):
        for name in ('usb_requests','sd_accesses','real_sdk_objects','formal_reservations','remaining'):
            self.assertEqual(self.audit[name],0)
        self.assertFalse(self.audit['actual_URB_generation_service_emulated'])
        self.assertFalse(self.audit['device_package_reuse_established'])
    def test_current_capability_one_shot(self):
        self.assertTrue(self.audit['host_capability']['current_lease_one_burst'])
        self.assertFalse(self.audit['host_capability']['sdk_allocations_tested'])


if __name__=='__main__':unittest.main()
