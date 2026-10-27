"""Exercise the actual packagers, independent container checks and recovery claims."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_quiet_deployment as pkg


class DeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir='/private/tmp', prefix='a23-package-test-')
        cls.root = Path(cls.temp.name)/'review'
        cls.report = pkg.build(cls.root)
        cls.nso = (cls.root/'exefs/main').read_bytes()
        cls.pfs = (cls.root/'exefs.nsp').read_bytes()
        cls.elf = (pkg.DEVICE/'full.elf').read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_package_matches_exact_device_and_baseline(self):
        self.assertEqual(pkg.pfs_files(self.pfs), {'main': self.nso, 'main.npdm': (pkg.DEVICE/'main.npdm').read_bytes()})
        self.assertEqual(self.report['device_binding_sha256'], 'e56f949870b19d81a6bfff8bd6c8282beed0e8372fa850bd36ac8768a347a517')
        self.assertEqual(self.report['exefs_nsp_sha256'], '81314284637a81fd5a6f9564383533b14168a62cababb51b9a6d156c643080f3')
        for name in pkg.PATHS:
            before = (pkg.BASE/name).read_bytes()
            self.assertEqual((self.root/'rollback-review'/name).read_bytes(), before)
            self.assertEqual((self.root/'sd-review'/name).read_bytes(), self.pfs if name.endswith('exefs.nsp') else before)
        self.assertFalse(self.report['deployed'])
        self.assertFalse(pkg.verify_review(self.root)['hardware_verified'])
        self.assertEqual(self.report['remaining'], 0)
        with self.assertRaises(ValueError):
            pkg.build(self.root)

    def test_unlisted_review_file_rejected(self):
        extra = self.root/'extra'
        extra.write_bytes(b'unlisted')
        try:
            with self.assertRaises(ValueError):
                pkg.verify_review(self.root)
        finally:
            extra.unlink()

    def test_output_refuses_card_and_noncanonical_paths(self):
        for name in ['/Volumes/A23-review', '/tmp/A23-review', str(pkg.ROOT/'offline-review'),
                     str(pkg.device.DEVICE/'must-not-extend-sealed-input'), '/private/tmp/../tmp/review']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                pkg.output_path(Path(name))

    def test_nso_mutants_rejected(self):
        for offset in [4, 12, 0x14, 0x18, 0x3c, 0x40, 0xa0, 256, len(self.nso)-1]:
            raw = bytearray(self.nso); raw[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises((ValueError, IndexError, struct.error)):
                pkg.verify_nso(self.elf, bytes(raw))
        for raw in (self.nso[:200], self.nso[:-1], self.nso+b'x'):
            with self.assertRaises((ValueError, IndexError, struct.error)):
                pkg.verify_nso(self.elf, raw)

    def test_pfs_mutants_rejected(self):
        mutations = []
        for offset in [0, 4, 8, 12, 16, 24, 32, 36, 40, 48, 56, 60]:
            raw = bytearray(self.pfs); raw[offset] ^= 1; mutations.append(raw)
        # Duplicate names, path traversal and truncated/trailing payload.
        raw = bytearray(self.pfs); struct.pack_into('<I', raw, 56, 0); mutations.append(raw)
        raw = bytearray(self.pfs); raw[64:68] = b'../x'; mutations.append(raw)
        mutations += [self.pfs[:63], self.pfs[:-1], self.pfs+b'x']
        for i, raw in enumerate(mutations):
            with self.subTest(i=i), self.assertRaises((ValueError, UnicodeError, struct.error)):
                pkg.pfs_files(raw)

    def test_npdm_program_id_range_and_request_rejected(self):
        original = (pkg.DEVICE/'main.npdm').read_bytes()
        aci, _, acid, _ = struct.unpack_from('<4I', original, 0x70)
        for offset in (aci, acid+0x200, aci+0x10, acid+0x210, acid+0x218, 28, 14, 15, 0x70, 0x78):
            raw = bytearray(original); raw[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                pkg.verify_npdm(raw)

    def test_controller_requires_before_after_and_ips_identity(self):
        header = (pkg.DEVICE/'source/uvc/iso_runtime_payload.h').read_text()
        manifest = json.loads((pkg.BASE/'manifest.json').read_text())
        original = (pkg.ROOT/'private/module/exefs/main').read_bytes()
        patch = (pkg.BASE/pkg.PATCH).read_bytes()
        self.assertEqual(pkg.verify_controller(header, manifest, original, patch)['edits'], 22)
        for key, value in [('before', 'ffffffff'), ('after', 'ffffffff'), ('address', '0x1234')]:
            mutant = copy.deepcopy(manifest); mutant['edits'][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                pkg.verify_controller(header, mutant, original, patch)
        with self.assertRaises(ValueError):
            pkg.verify_controller(header, manifest, original, patch[:-1])


class RecoveryTests(unittest.TestCase):
    recipe = '03'+'00'*31  # Frozen native model, deliberately not the ARM runtime recipe.

    def assess(self, name, primary=True):
        root = pkg.device.DEVICE
        execution = (root/(name+'.execution.disk.bin')).read_bytes()
        raw = (root/(name+'.primary.disk.bin')).read_bytes() if primary else None
        return pkg.assess_saved(execution, raw, self.recipe)

    def test_normal_and_diagnostic_success_do_not_prove_exit(self):
        for kind in ('normal', 'diagnostic'):
            result = self.assess(kind+'-primary-ok-execution-ok')
            self.assertEqual(result['primary_file_relation'], 'matches')
            self.assertTrue(result['primary_receipt']['commit_acknowledged'])
            self.assertEqual(result['diagnostic_retains_even_if_saves_succeed'], kind == 'diagnostic')
            for field in ('execution_own_commit_authenticated', 'join_results_authenticated', 'physical_run_authenticated',
                          'clean_exit_authenticated', 'hardware_verified', 'cleanup_authorized'):
                self.assertIs(result[field], False)

    def test_primary_commit_failure_keeps_content_separate(self):
        result = self.assess('normal-primary-commit-error-execution-ok')
        self.assertEqual(result['primary_file_relation'], 'matches')
        self.assertTrue(result['primary_receipt']['content_verified'])
        self.assertFalse(result['primary_receipt']['commit_acknowledged'])

    def test_execution_commit_failure_cannot_be_detected_from_complete_bytes(self):
        result = self.assess('normal-primary-ok-execution-commit-error')
        self.assertTrue(result['execution_content_valid'])
        self.assertFalse(result['execution_own_commit_authenticated'])

    def test_missing_and_partial_primary_kept_distinct(self):
        name = 'normal-primary-ok-execution-ok'; root = pkg.device.DEVICE
        self.assertEqual(self.assess(name, False)['primary_file_relation'], 'missing')
        execution = (root/(name+'.execution.disk.bin')).read_bytes()
        primary = (root/(name+'.primary.disk.bin')).read_bytes()
        self.assertEqual(pkg.assess_saved(execution, primary[:-1], self.recipe)['primary_file_relation'], 'different_or_partial')

    def test_truncated_corrupt_wrong_recipe_rejected(self):
        raw = (pkg.device.DEVICE/'normal-primary-ok-execution-ok.execution.disk.bin').read_bytes()
        for mutant, recipe in [(raw[:-1], self.recipe), (raw[:200], self.recipe),
                               (raw, 'ae65e7036adba30cd839152299a51492b13ef0d94952921782fa2b0c938950a0'),
                               (raw[:-1]+bytes([raw[-1]^1]), self.recipe)]:
            with self.assertRaises(ValueError):
                pkg.assess_saved(mutant, None, recipe)


if __name__ == '__main__':
    unittest.main()
