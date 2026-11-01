"""v26A: the pipeline cave and the 16 ms double-buffered app loop.

The cave writes the next TD set at prod when the ring is non-empty (no
0x2feb0 replay, no memset); the app keeps two buffers in flight on a 16 ms
tick so the ring never runs dry.  These tests pin the source structure and
assemble the new cave; no hardware is needed.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

PIPE = ROOT / "patches/iso_burst_uac84_dci9_pipe.S"
REARM = ROOT / "patches/iso_burst_uac84_dci9_rearm.S"
SOURCE = REPO / "source/uvc/uvc_device.c"
BUILDER = ROOT / "tools/build_uac_u2_probe.py"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")


class UacU2PipeCaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PIPE.read_text()

    def test_gate_branches_to_the_nonempty_path(self):
        self.assertIn("b.ne pipe_nonempty", self.text)
        self.assertNotIn("b.ne fail_accept\n    /* Empty ring", self.text)
        self.assertIn("pipe_nonempty:", self.text)
        self.assertIn("b installed", self.text)

    def test_empty_path_rearms_and_nonempty_keeps_the_ring(self):
        empty = self.text.index("b.ne pipe_nonempty")
        nonempty = self.text.index("pipe_nonempty:")
        installed = self.text.index("installed:")
        head = self.text[empty:nonempty]
        self.assertIn("bl rearm_endpoint", head)
        tail = self.text[nonempty:installed]
        self.assertIn("add x6, x0, #0x22, lsl #12", tail)
        self.assertIn("ldr x10, [x1, #0x10]", tail)
        self.assertIn("add x13, x10, #0xf70", tail)
        self.assertNotIn("rearm_endpoint", tail)
        self.assertNotIn("memset", tail)

    def test_cave_fits_and_only_the_entry_grows(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pipe, symbols = assemble(TOOLCHAIN, tmp / "p", PIPE,
                                     require_report=False)
            rearm, _ = assemble(TOOLCHAIN, tmp / "r", REARM,
                                require_report=False)
        self.assertLessEqual(len(pipe), 0x69000 - 0x68D54)
        self.assertEqual(len(pipe), len(rearm) + 16)
        self.assertEqual(symbols["iso_enter"], 0x68D54)
        # exactly one call into the driver setup path
        hits = 0
        for i in range(0, len(pipe) - 4, 4):
            w = int.from_bytes(pipe[i:i + 4], "little")
            if (w & 0xFC000000) != 0x94000000:
                continue
            imm = w & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if (0x68D54 + i + (imm << 2)) & 0xFFFFFFFF == 0x2FEB0:
                hits += 1
        self.assertEqual(hits, 1)


class UacU2PipeAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def _pipeline(self):
        start = self.text.index("#if defined(UAC_U2_PIPELINE)\n    /* v26A: 16 ms")
        end = self.text.index("#else", start)
        return self.text[start:end]

    def test_two_buffers_stay_in_flight(self):
        block = self._pipeline()
        self.assertIn("posted - completed < 2", block)
        self.assertIn("UAC U2 pipe post buf=%u urb=%u", block)
        self.assertIn("UAC U2 pipe done buf=%u urb=%u", block)
        self.assertIn("UAC U2 pipe end posted=%u completed=%u bytes=%u", block)

    def test_pending_requests_are_cancelled(self):
        block = self._pipeline()
        cancel = block.index("usbDsEndpoint_Cancel(")
        guard = block.index("if (completed < posted)")
        self.assertLess(guard, cancel)
        self.assertIn("pipe cancel pending=%u", block)

    def test_burst_limit_allows_eight_and_submit_dump_is_guarded(self):
        self.assertIn("#if defined(UAC_U2_PIPELINE)", self.text)
        self.assertIn("UAC_U2_PIPELINE needs UAC_U2_BURSTS 2..8", self.text)
        self.assertIn("#if !defined(UAC_U2_PIPELINE)", self.text)

    def test_probe_builder_accepts_the_pipeline_marker(self):
        builder = BUILDER.read_text()
        self.assertIn('if "UAC_U2_PIPELINE" in args.define:', builder)
        self.assertIn('markers.append(b"UAC U2 pipe end")', builder)


if __name__ == "__main__":
    unittest.main()
