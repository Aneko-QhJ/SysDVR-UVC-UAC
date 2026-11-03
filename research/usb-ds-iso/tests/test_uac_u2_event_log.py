"""v29s event-code cave: find out which completion code halts the endpoint.

Every UAC cave since v14 pointed ISO_ENTRY at 0x270 (the DCI-7 A23 object).
The UAC configuration has no DCI 7, so iso_event bailed at `cbz x5` and the
cave never saw a DCI-9 event; the driver's event_original handled everything,
including the error codes that reach 0x30ff4 (3/4/5/9/10/14/15/31/0xdb/0xde)
and halt the endpoint.  v29s fixes the constant and replaces the event body
with a log-only stub; the enter path and the payload edits stay at v29q's.
"""
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
CAVE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_log.S"
BASE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")


class UacU2EventLogCaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CAVE.read_text()

    def test_uses_the_dci9_object(self):
        self.assertIn(".equ ISO_ENTRY, 0x300", self.text)
        self.assertNotIn(".equ ISO_ENTRY, 0x270", self.text)

    def test_event_path_is_log_only(self):
        start = self.text.index("iso_event:")
        end = self.text.index("iso_end:")
        body = self.text[start:end]
        self.assertNotIn("complete_original", body)
        self.assertNotIn("str x6, [x10, #0x20]", body)  # no cons = prod
        self.assertIn("b.ne event_original", body)
        self.assertIn("b.eq event_original", body)

    def test_record_is_written_after_the_original_call(self):
        start = self.text.index("iso_event:")
        end = self.text.index("iso_end:")
        body = self.text[start:end]
        call = body.index("bl event_original")
        count = body.index("#0xc10]")
        entries = body.index("#0xc20")
        self.assertLess(call, count)
        self.assertLess(call, entries)

    def test_enter_path_is_the_v29q_cave(self):
        base = BASE.read_text()
        head, _ = base.split("iso_event:", 1)
        # only ISO_ENTRY moved; the enter instructions are unchanged
        self.assertEqual(self.text.count("bl advance"), head.count("bl advance"))
        self.assertIn("b doorbell_tail", self.text)
        self.assertIn("ubfx w9, w9, #9, #2", self.text)

    def test_size_and_scratch_offsets(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from build_uac_u2_producer import assemble
        with tempfile.TemporaryDirectory() as tmp:
            code, symbols = assemble(TOOLCHAIN, Path(tmp), CAVE,
                                     require_report=False)
        self.assertEqual(len(code), 548)
        self.assertLessEqual(len(code), 0x69000 - 0x68D54)
        self.assertEqual(symbols["iso_enter"], 0x68D54)
        words = [int.from_bytes(code[i:i + 4], "little")
                 for i in range(0, len(code) - 3, 4)]
        self.assertIn(0xB94C114C, words)  # ldr w12, [x10, #0xc10]
        self.assertIn(0x91308149, words)  # add x9, x10, #0xc20
        self.assertIn(0xB90C114C, words)  # str w12, [x10, #0xc10]


class UacU2EventLogAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_helper_reads_count_and_entries(self):
        self.assertIn("static void _uacLogEventScratch(const char *tag)",
                      self.text)
        self.assertIn("ring + 0xC10", self.text)
        self.assertIn("ring + 0xC20", self.text)
        self.assertIn('LOG("UAC U2 evlog %s count=%u rc=0x%x\\n"', self.text)
        self.assertIn("word >> 24, word & 0xffffffu", self.text)

    def test_called_on_a_miss_and_at_the_end(self):
        self.assertIn('_uacLogEventScratch("miss");', self.text)
        self.assertIn('_uacLogEventScratch("end");', self.text)
        miss = self.text.index('_uacLogEventScratch("miss");')
        guard = self.text.rfind("#if defined(UAC_U2_EVENT_LOG)", 0, miss)
        endif = self.text.rfind("#endif", 0, miss)
        self.assertGreater(guard, endif)

    def test_opt_in_only(self):
        # the helper must not run in a build without the define
        index = self.text.index("static void _uacLogEventScratch")
        guard = self.text.rfind("#if defined(UAC_U2_EVENT_LOG)", 0, index)
        endif = self.text.rfind("#endif", 0, index)
        self.assertGreater(guard, endif)


if __name__ == "__main__":
    unittest.main()
