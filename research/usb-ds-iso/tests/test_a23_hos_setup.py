"""Keep shared-setup hypotheses separate from bound firmware and saved timing."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_hos_setup as audit


class A23HosSetupTests(unittest.TestCase):
    def setUp(self):
        self.nso=audit.validate_module((audit.PRIVATE/'module/exefs/main').read_bytes())

    def test_actual_client_reads_latest_setup_under_explicit_scheduling(self):
        timing=audit.host_timing()
        self.assertAlmostEqual(timing['after_status_begin_ms'],30.56533333333333)
        self.assertFalse(timing['host_begin_is_bus_arrival'])
        with tempfile.TemporaryDirectory() as tmp:
            probe=audit.source_probe(Path(tmp),timing)
        cases={r['scenario']:r for r in probe['scenarios']}
        self.assertEqual(len(cases),6)
        for name in ('20ms-kept','28ms-kept','32ms-delayed-arrival','32ms-no-replacement'):
            self.assertEqual(cases[name]['sequence'],1)
            self.assertEqual(cases[name]['posts'],1)
        replaced=cases['32ms-replaced']
        self.assertEqual(replaced['first_requests'],[0x54,0x54,0x51])
        self.assertEqual(replaced['setup_reads'],[2,2,1])
        self.assertTrue(replaced['status_unchanged'])
        self.assertGreaterEqual(replaced['status_reply_ns']/1e6,timing['after_status_begin_ms'])
        self.assertLessEqual(replaced['status_reply_ns']/1e6,timing['after_status_end_ms'])
        self.assertFalse(probe['hardware_observation'])
        self.assertFalse(probe['hos_machine_code_emulated'])

    def test_changed_store_instruction_is_rejected(self):
        section=self.nso.sections[0]
        content=bytearray(section['content']);content[0x2a12c]^=1;section['content']=bytes(content)
        with self.assertRaisesRegex(ValueError,'Machine anchor mismatch'):
            audit.machine_checks(self.nso)

    def test_changed_setup_vtable_is_rejected(self):
        section=self.nso.sections[2]
        content=bytearray(section['content'])
        struct.pack_into('<Q',content,0x8fed0+0x30-section['vaddr'],0x27d70)
        section['content']=bytes(content)
        with self.assertRaisesRegex(ValueError,'vtable mismatch'):
            audit.machine_checks(self.nso)

    def test_ep0_patch_overlap_is_rejected_but_transfer_hook_is_allowed(self):
        self.assertTrue(audit.check_paths(self.nso,[(0x30898,b'abcd')])['reviewed_paths_unchanged'])
        for address in (0x2a12c,0x2a194,0x2cfb0,0x8ff00,0x308cc,0x308d4):
            with self.subTest(address=hex(address)):
                with self.assertRaisesRegex(ValueError,'reviewed EP0 path'):
                    audit.check_paths(self.nso,[(address,b'abcd')])

    def test_ips_rejects_overlapping_records_and_malformed_input(self):
        one=struct.pack('>IH',0x110,4)+b'abcd'
        self.assertEqual(audit.parse_ips(b'IPS32'+one+b'EEOF'),[(0x10,b'abcd')])
        for blob in (b'IPS32'+one+one+b'EEOF',b'IPS32'+one+b'EEOFjunk',
                     b'IPS32'+struct.pack('>IH',0x110,0)+b'EEOF',b'IPS32'+one[:-1],
                     b'IPS32'+struct.pack('>IH',0x10,4)+b'abcdEEOF'):
            with self.subTest(blob=blob):
                with self.assertRaises(ValueError):audit.parse_ips(blob)


if __name__=='__main__':unittest.main()
