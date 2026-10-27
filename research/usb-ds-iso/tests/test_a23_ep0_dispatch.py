"""Distinguish actual-source pre-submit guards from post/ACK failure paths."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import audit_a23_ep0 as audit


class A23Ep0DispatchTests(unittest.TestCase):
    def test_actual_dispatch_and_synchronous_ack_with_injected_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = audit.source_probe(Path(tmp))
        self.assertEqual(result['scenario_count'], 17)
        cases = {r['scenario']:r for r in result['scenarios']}
        for name in ('post-failed', 'ack-post-failed', 'ack-timeout', 'ack-report-failed', 'ack-urb-failed'):
            self.assertEqual(cases[name]['sequence'], 1)
            self.assertFalse(cases[name]['status_unchanged'])
        self.assertEqual(cases['slow-log-kept']['posts'], 1)
        self.assertTrue(cases['slow-log-dropped']['status_unchanged'])
        self.assertTrue(cases['slow-log-replaced']['status_unchanged'])
        self.assertTrue(all(r['hardware_observation'] is False for r in result['scenarios']))

    def test_elf_binding_rejects_modified_code_bytes(self):
        legacy = audit.PRIVATE/'legacy-builds/root'
        nso = (legacy/'exefs-iso-A.nso').read_bytes()
        elf = (legacy/'exefs-iso-A.elf').read_bytes()
        self.assertEqual(len(audit.bind_elf(nso, elf)), 3)
        changed = bytearray(elf)
        # Change the first deployed .text byte, not an irrelevant debug section.
        import struct
        phoff = struct.unpack_from('<Q', elf, 32)[0]
        size, count = struct.unpack_from('<HH', elf, 54)
        for i in range(count):
            kind, _, offset, address, _, length, _, _ = struct.unpack_from('<II6Q', elf, phoff+i*size)
            if kind == 1 and address == 0 and length:
                changed[offset] ^= 1
                break
        else:
            self.fail('Missing text load segment')
        with self.assertRaisesRegex(ValueError, 'do not match deployed'):
            audit.bind_elf(nso, bytes(changed))


if __name__ == '__main__':
    unittest.main()
