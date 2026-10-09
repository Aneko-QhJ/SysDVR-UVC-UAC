"""A22 scheduling contrast, executed from the actual patched AArch64 code."""
import hashlib
import json
import subprocess
import sys
import unittest
from test_patch import Machine, ROOT, PACKAGES, RING, MMIO, ENTRY
from build_patch import build
from package_experiment import validate_revision


class FollowupSiaTests(unittest.TestCase):
    def setUp(self):
        self.meta = json.loads((PACKAGES / 'A/manifest.json').read_text())
        if not self.meta.get('followup_sia'):
            self.skipTest('requires A22 followup-SIA package')

    def test_first_explicit_following_asap_at_all_microframe_phases(self):
        for frame in (0, 2015, 2047):
            for phase in range(8):
                for slot in (0, 246):
                    for cycle in (0, 1):
                        m = Machine('A')
                        for offset in (0x18, 0x20):
                            m.write(ENTRY + offset, '<Q', RING + slot * 16)
                        m.write(ENTRY + 0x40, '<B', cycle)
                        m.write(MMIO + 0x48, '<I', frame * 8 + phase)
                        self.assertEqual(m.submit(3072), 0)
                        for td in range(16):
                            logical = slot + td * 2
                            cursor = RING + logical % 247 * 16
                            control = m.read(cursor + 12, '<I')[0]
                            self.assertEqual(control & 1, cycle ^ (logical >= 247))
                            self.assertEqual(control >> 31, int(td != 0))
                            self.assertEqual((control >> 20) & 2047, 0 if td else (frame + 32) & 2047)
                            self.assertEqual(control & 0xffffe, 0x1410)
                            self.assertEqual(m.read(cursor + 8, '<I')[0], 192)

    def test_only_two_loop_instructions_change_from_confirmed_a21(self):
        old = ROOT / 'private/packages-A21-context-audit/A'
        before = (old / 'inject.bin').read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(),
                         '2617a61ce8cf57836c5d8afa4d5fe8278bf3c0aecfbce95c6f5e7bb25f599d09')
        after = (PACKAGES / 'A/inject.bin').read_bytes()
        self.assertEqual(len(before), len(after))
        differences = [i for i in range(0, len(before), 4) if before[i:i+4] != after[i:i+4]]
        self.assertEqual(len(differences), 2)
        self.assertEqual(differences[1], differences[0] + 4)
        baseline = json.loads((old / 'manifest.json').read_text())
        self.assertEqual(baseline['symbols'], self.meta['symbols'])
        self.assertEqual(baseline['edits'][1:], self.meta['edits'][1:])
        for key in ('diagnostics_magic', 'frame_lead', 'mps', 'burst_packets',
                    'retain_success', 'prepublication_context_snapshot',
                    'publication_mfi_snapshot', 'doorbell_tail_mfi_snapshot'):
            self.assertEqual(baseline[key], self.meta[key])

    def test_cli_and_builder_reject_followup_without_iso6_baseline(self):
        with self.assertRaisesRegex(ValueError, 'requires the ISO6'):
            build(None, 1, None, None, followup_sia=True)
        result = subprocess.run([sys.executable, str(ROOT / 'tools/build_patch.py'),
                                 '--followup-sia'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--followup-sia requires --context-audit', result.stderr)

    def test_package_revision_cannot_mislabel_scheduling_policy(self):
        flags = validate_revision(self.meta, 'A22', True)
        self.assertEqual(flags, (True, False, False, True, True))
        for revision in ('A18', 'A19', 'A20', 'A21'):
            with self.assertRaises(ValueError):
                validate_revision(self.meta, revision, True)
        baseline = dict(self.meta, followup_sia=False)
        self.assertEqual(validate_revision(baseline, 'A21', True),
                         (True, False, False, True, False))
        with self.assertRaises(ValueError):
            validate_revision(baseline, 'A22', True)
        with self.assertRaises(ValueError):
            validate_revision(self.meta, 'A22', False)
