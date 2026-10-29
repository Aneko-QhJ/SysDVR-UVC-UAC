import tempfile
import unittest
from pathlib import Path

import build_a23_urb_trace as trace


class UrbTraceBuildHeaderTest(unittest.TestCase):
    def test_runtime_header_roundtrip(self):
        manifest = {
            "build_id": "AB" * 32,
            "edits": [
                {"address": "0x68d54", "before": "00", "after": "01020304"},
                {"address": "0x30364", "before": "80010054", "after": "804f1c54"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "payload.h"
            trace.runtime_header(manifest, path)
            text = path.read_text()
        self.assertIn("isoRuntimeBuildId[32]", text)
        self.assertIn("isoRuntimeEdits[]", text)
        self.assertIn("{0x68d54,1,isoRuntime_0_before,isoRuntime_0_after}", text)
        self.assertIn("{0x30364,4,isoRuntime_1_before,isoRuntime_1_after}", text)

    def test_stream_stub_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stream.h"
            trace.stream_stub_header(bytes.fromhex("01020304"), path)
            text = path.read_text()
        self.assertIn("isoRuntimeStreamSame[4]={1,2,3,4}", text)
        self.assertIn("{0x68d54,4,isoRuntimeStreamSame,isoRuntimeStreamSame}", text)


if __name__ == "__main__":
    unittest.main()
