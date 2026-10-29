"""Static checks for the UAC_DESCRIPTOR_PATCH build wiring."""
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

    def test_payload_is_included_under_its_own_flag(self):
        include = '#include "uac_descriptor_payload.h"'
        self.assertIn(include, self.src)
        start = self.src.rindex("#ifdef UAC_DESCRIPTOR_PATCH", 0, self.src.index(include))
        end = self.src.index("#endif", self.src.index(include))
        self.assertIn(include, self.src[start:end])

    def test_patch_runs_before_enable_and_fails_closed(self):
        self.assertLess(
            self.src.index("static bool _applyUacDescriptorPatch"),
            self.src.index("Result UvcDeviceInitialize"),
        )
        call = self.src.index("if (!_applyUacDescriptorPatch())")
        self.assertLess(call, self.src.index("rc = usbDsEnable();"))
        guard = self.src.rindex("#ifdef UAC_DESCRIPTOR_PATCH", 0, call)
        block = self.src[guard:self.src.index("#endif", call)]
        self.assertIn("goto cleanup", block)
        self.assertIn("LibnxError_BadInput", block)

    def test_applier_uses_the_descriptor_payload_only(self):
        start = self.src.index("static bool _applyUacDescriptorPatch")
        body = self.src[start:self.src.index("\n}\n", start)]
        self.assertIn("isoApplyRuntimePatch(uacRuntimeEdits", body)
        self.assertIn("uacRuntimeBuildId", body)
        self.assertIn("0x369000", body)
        self.assertNotIn("isoRuntimeEdits", body)
        self.assertNotIn("isoRuntimeStreamEdits", body)

    def test_enable_log_is_present(self):
        self.assertIn("UAC descriptor patch failed; refusing to enable the device", self.src)


if __name__ == "__main__":
    unittest.main()
