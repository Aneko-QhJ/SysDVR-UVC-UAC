"""Static checks for the UAC usb:ds patch build wiring."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "source/uvc/uvc_device.c"


class UacDescriptorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.src = SOURCE.read_text()

    def test_payloads_are_included_under_their_own_flags(self):
        for include, flag in (
            ('#include "uac_descriptor_payload.h"', "UAC_DESCRIPTOR_PATCH"),
            ('#include "uac_u2_base_payload.h"', "UAC_U2_BASE_PATCH"),
        ):
            self.assertIn(include, self.src)
            start = self.src.rindex(f"#ifdef {flag}", 0, self.src.index(include))
            end = self.src.index("#endif", self.src.index(include))
            self.assertIn(include, self.src[start:end])

    def test_patch_runs_before_enable_and_fails_closed(self):
        self.assertLess(
            self.src.index("static bool _applyUacPatch"),
            self.src.index("Result UvcDeviceInitialize"),
        )
        call = self.src.index("patch_ok = _applyUacDescriptorPatch();")
        self.assertLess(call, self.src.index("rc = usbDsEnable();"))
        guard = self.src.rindex(
            "#if defined(UAC_DESCRIPTOR_PATCH) || defined(UAC_U2_BASE_PATCH)",
            0,
            call,
        )
        end = self.src.index("#endif", self.src.index("if (!patch_ok)", call))
        block = self.src[guard:end]
        self.assertIn("goto cleanup", block)
        self.assertIn("LibnxError_BadInput", block)
        self.assertIn("patch_ok = _applyUacU2BasePatch();", self.src)

    def test_applier_uses_the_payload_only(self):
        start = self.src.index("static bool _applyUacPatch(")
        body = self.src[start:self.src.index("\n}\n", start)]
        self.assertIn("isoApplyRuntimePatch(edits, edit_count", body)
        self.assertIn("build_id", body)
        self.assertIn("0x369000", body)
        self.assertNotIn("isoRuntimeEdits", body)
        self.assertNotIn("isoRuntimeStreamEdits", body)
        self.assertIn("_applyUacPatch(uacRuntimeEdits", self.src)
        self.assertIn("_applyUacPatch(uacU2BaseEdits", self.src)

    def test_enable_log_is_present(self):
        self.assertIn(
            "UAC patch failed; refusing to enable the device", self.src
        )


if __name__ == "__main__":
    unittest.main()
