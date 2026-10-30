"""Checks the path-corrected short24 package, recipe-bound entry and its audit."""
import hashlib
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import audit_a23_short24_entry
import audit_a23_short24_sdk
import build_a23_short24_entry
import package_a23_short24
from build_a23_short24_candidate import verify_tree

A = ROOT / "private/analysis"
CANDIDATE = A / "A23-short24-path-span-candidate-20261027-r1"
PACKAGE = A / "A23-short24-path-span-package-20261030-r1"
ENTRY = A / "A23-short24-path-span-entry-20261030-r1"
AUDIT = A / "A23-short24-path-span-entry-audit-20261030-r2"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class UacShort24PathSpanPackageTests(unittest.TestCase):
    def setUp(self):
        if not (PACKAGE / "package-report.json").is_file():
            self.skipTest(f"missing {PACKAGE}")

    def test_package_binds_the_path_corrected_recipe(self):
        report = json.loads((PACKAGE / "package-report.json").read_text())
        recipe = json.loads((CANDIDATE / "device/recipe.json").read_text())
        self.assertEqual(report["schema"], "A23-short24-path-span-package-1")
        self.assertEqual(report["recipe"], recipe["runtime_recipe_sha256"])
        self.assertEqual(report["candidate_manifest_sha256"], verify_tree(CANDIDATE))
        self.assertEqual(report["exefs_nsp_sha256"], sha(PACKAGE / "exefs.nsp"))
        ips = (CANDIDATE / "controller/A/atmosphere/exefs_patches/SysDVR-ISO"
               / (package_a23_short24.BUILD_ID + ".ips"))
        self.assertEqual(report["controller_ips_sha256"], sha(ips))

    def test_rollback_and_deployment_pairs_are_consistent(self):
        report = json.loads((PACKAGE / "package-report.json").read_text())
        files = report["deployment_files"]
        nsp = "atmosphere/contents/00FF0000A53BB666/exefs.nsp"
        flag = "atmosphere/contents/00FF0000A53BB666/flags/boot2.flag"
        self.assertTrue(files[nsp]["changed"])
        self.assertFalse(files[flag]["changed"])
        self.assertEqual(sha(PACKAGE / "sd-review" / nsp), report["exefs_nsp_sha256"])
        self.assertEqual(sha(PACKAGE / "sd-review" / flag),
                         files[flag]["before_sha256"])
        self.assertTrue(report["firmware_packaged"])
        self.assertFalse(report["deployed"])
        self.assertFalse(report["hardware_verified"])
        self.assertEqual((report["sd_accesses"], report["usb_operations"]), (0, 0))

    def test_entry_binds_package_recipe_and_one_burst(self):
        if not (ENTRY / "build.json").is_file():
            self.skipTest(f"missing {ENTRY}")
        report = json.loads((PACKAGE / "package-report.json").read_text())
        description = json.loads((ENTRY / "description.json").read_text())
        build = json.loads((ENTRY / "build.json").read_text())
        self.assertEqual(description["recipe"], report["recipe"])
        self.assertEqual(description["nsp_sha256"], report["exefs_nsp_sha256"])
        self.assertEqual(description["ips_sha256"], report["controller_ips_sha256"])
        self.assertEqual(description["baseline_manifest_sha256"],
                         report["snapshot_manifest_sha256"])
        self.assertEqual((description["first_sequence"], description["last_sequence"]),
                         (513, 528))
        self.assertEqual(description["max_bursts"], 1)
        self.assertFalse(description["current_authorization_issued"])
        self.assertEqual(build["package_manifest_sha256"], verify_tree(PACKAGE))
        self.assertEqual(build["receiver_sha256"],
                         sha(ENTRY / "short24-receiver"))

    def test_audit_checked_models_without_consuming_authority(self):
        if not (AUDIT / "report.json").is_file():
            self.skipTest(f"missing {AUDIT}")
        report = json.loads((AUDIT / "report.json").read_text())
        self.assertTrue(report["model_authorization_checked_not_consumed"])
        self.assertTrue(report["formal_scope_unchanged"])
        self.assertEqual(len(report["authorization_refusals"]), 10)
        self.assertEqual(report["native_runtime_scenarios"], 7)
        self.assertEqual(report["persistence_checks_passed"], 5)
        self.assertEqual(report["sdk_objects_created"], 0)
        self.assertEqual((report["usb_operations"], report["sd_accesses"]), (0, 0))
        self.assertFalse(report["real_authorization_issued"])
        self.assertFalse(report["hardware_verified"])

    def test_tools_take_the_candidate_and_sdk_as_parameters(self):
        package_params = inspect.signature(package_a23_short24.build).parameters
        self.assertIn("candidate", package_params)
        entry_params = inspect.signature(build_a23_short24_entry.build).parameters
        for name in ("package", "candidate", "sdk"):
            self.assertIn(name, entry_params)
        self.assertIn("build", inspect.signature(audit_a23_short24_sdk.run).parameters)
        self.assertIn("sdk", inspect.signature(audit_a23_short24_entry.run).parameters)


if __name__ == "__main__":
    unittest.main()
