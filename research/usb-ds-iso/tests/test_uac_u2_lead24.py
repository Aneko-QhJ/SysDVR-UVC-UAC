"""v37 lead-24 cave, and the two miss-path SD writes compiled out.

v36 left the post-miss hole at react 22 ms + lead 32 ms, just above the ~40 ms
of silence that makes macOS drop alt1 (v34).  v33 (global 16 ms) and v35
(16 ms only for the post-miss re-arm) both doubled status=5, so 16 is too
tight; v37 moves the lead to the midpoint, 24 ms, and takes the two remaining
SD writes out of the miss path (v36 removed the evlog dump there; the per-miss
"pipe miss" and "miss recover" lines were still two writes between the
completion and the replacement post).

The cave change is the single `add w9, w9, #32` -> `#24`; the test assembles
both caves and pins the one word.  The app change is opt-in: without
-DUAC_U2_MISS_LOG neither line is compiled, and the counters keep working.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
CAVE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_lead24.S"
BASE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_log.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

ADD_LEAD32 = 0x11008129  # add w9, w9, #0x20
ADD_LEAD24 = 0x11006129  # add w9, w9, #0x18
ADD_LEAD16 = 0x11004129  # add w9, w9, #0x10


def _words(code):
    return [int.from_bytes(code[i:i + 4], "little")
            for i in range(0, len(code) - 4 + 1, 4)]


class UacU2Lead24CaveTests(unittest.TestCase):
    def test_source_has_the_24ms_lead_only(self):
        text = CAVE.read_text()
        self.assertIn("add w9, w9, #24", text)
        self.assertNotIn("add w9, w9, #32", text)
        self.assertNotIn("add w9, w9, #16", text)
        self.assertNotIn("add w9, w9, #40", text)
        # the rest of the v30h log cave is untouched
        self.assertIn(".equ ISO_ENTRY, 0x300", text)
        self.assertIn("b doorbell_tail", text)
        self.assertIn("ubfx w9, w9, #9, #2", text)

    def test_assembles_to_the_v30h_size(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, symbols = assemble(TOOLCHAIN, Path(tmp), CAVE,
                                     require_report=False)
        self.assertEqual(symbols["iso_enter"], 0x68D54)
        # one changed immediate: same length as the lead-32 cave
        with tempfile.TemporaryDirectory() as tmp:
            base, _ = assemble(TOOLCHAIN, Path(tmp), BASE,
                               require_report=False)
        self.assertEqual(len(code), len(base))
        self.assertEqual(len(code), 548)
        self.assertLessEqual(len(code), 0x69000 - 0x68D54)

    def test_the_lead_word_is_24(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = assemble(TOOLCHAIN, Path(tmp), CAVE,
                               require_report=False)
        words = _words(code)
        self.assertIn(ADD_LEAD24, words)
        self.assertNotIn(ADD_LEAD32, words)
        self.assertNotIn(ADD_LEAD16, words)


class UacU2QuietMissLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def _guard_above(self, needle):
        index = self.text.index(needle)
        guard = self.text.rfind("#if", 0, index)
        line = self.text[guard:self.text.index("\n", guard)]
        closing = self.text.index("#endif", index)
        return line, self.text[index:closing]

    def test_pipe_miss_line_is_opt_in(self):
        line, _ = self._guard_above('LOG("UAC U2 pipe miss buf=%u status=%u\\n"')
        self.assertIn("UAC_U2_MISS_LOG", line)

    def test_miss_recover_line_is_opt_in(self):
        line, body = self._guard_above(
            'LOG("UAC U2 pipe miss recover cancelled=%u rc=0x%x\\n"')
        self.assertIn("UAC_U2_MISS_LOG", line)
        self.assertIn("freed", body)

    def test_counters_survive_the_removed_lines(self):
        # the miss still increments its counter and still frees the slot
        start = self.text.index("++misses;")
        self.assertLess(start, self.text.index("UAC_U2_MISS_LOG", start))
        self.assertIn("++recoveries;", self.text)
        # the cancel result stays used, so -Wall -Werror is clean either way
        self.assertIn("(void)cancel; /* v37", self.text)
        self.assertIn("(void)freed; /* v37", self.text)

    def test_end_line_still_reports_both_counts(self):
        self.assertIn("misses=%u recoveries=%u", self.text)


if __name__ == "__main__":
    unittest.main()
