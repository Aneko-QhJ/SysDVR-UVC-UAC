"""v34 alt-churn diagnostic: who tears alt1 down?

macOS drives 18-19 alt1/alt0 cycles in 20 s while the pipe runs on the arm
thread.  v34 keeps the v30h behaviour and only adds `-DUAC_U2_ALT_DIAG`:
the pipe loop keeps a small snapshot (posted/completed/misses, last status,
last post/done ticks, active flag) and the SET_INTERFACE handler stamps the
alt0/alt1 arrivals with the age of that snapshot.  The log then answers
whether alt0 arrives on a running pipe, how long since the last completion
and whether a miss just happened.

These tests check the guarded source and, if the diagnostic build exists,
that the two log strings are present in its ELF.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
WORK = ROOT / "private/analysis/UAC-u2-v34-alt-diag-20261106"

ALT0_FIELDS = (
    "active=%u", "inflight=%u", "posted=%u", "completed=%u", "misses=%u",
    "last_status=%u", "dt_done_ms=%llu", "dt_post_ms=%llu",
    "since_alt1_ms=%llu",
)


class UacU2AltDiagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_the_whole_diag_is_guarded(self):
        self.assertIn("#if defined(UAC_U2_ALT_DIAG)", self.text)
        self.assertIn("UacAltDiag g_altDiag", self.text)
        # every g_altDiag reference sits inside a guard block
        lines = self.text.splitlines()
        depth = 0
        unguarded = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#if"):
                depth += 1
            elif stripped.startswith("#endif"):
                depth -= 1
            elif "g_altDiag" in stripped and depth == 0 and "UacAltDiag" not in stripped:
                unguarded.append(stripped)
        self.assertEqual(unguarded, [])

    def test_alt0_snapshot_has_the_diagnostic_fields(self):
        start = self.text.index("UAC U2 alt diag alt0")
        line = self.text[start:self.text.index("\n", start)]
        for field in ALT0_FIELDS:
            self.assertIn(field, line)
        # the snapshot is taken before the stop handler changes any state
        case = self.text.index("case UAC_ACT_STOP:")
        self.assertLess(self.text.index("UAC U2 alt diag alt0"), case + 2000)
        self.assertLess(self.text.index("UAC U2 alt diag alt0"),
                        self.text.index("g_uacCtx.streaming = false;", case))

    def test_alt1_arrival_is_stamped(self):
        self.assertIn('LOG("UAC U2 alt diag alt1 n=%u since_alt0_ms=%llu',
                      self.text)
        self.assertIn("g_altDiag.alt1_tick = now;", self.text)
        self.assertIn("g_altDiag.alt0_tick = now;", self.text)

    def test_pipe_loop_updates_the_snapshot(self):
        for needle in ("g_altDiag.posted = posted;",
                       "g_altDiag.completed = completed;",
                       "g_altDiag.misses = misses;",
                       "g_altDiag.last_status = report.report[i].urb_status;",
                       "g_altDiag.last_done_tick = done_tick;",
                       "g_altDiag.active = 0;",
                       "g_altDiag.active = 1;"):
            self.assertIn(needle, self.text)

    def test_built_image_has_the_markers(self):
        elf = WORK / "build/outputs/exefs.elf"
        if not elf.is_file():
            self.skipTest(f"missing {elf}")
        data = elf.read_bytes()
        self.assertIn(b"UAC U2 alt diag alt0", data)
        self.assertIn(b"UAC U2 alt diag alt1", data)
        # the diagnostic build keeps the v30h behaviour (no keep-ring marker)
        self.assertNotIn(b"UAC U2 pipe keep-ring", data)


if __name__ == "__main__":
    unittest.main()
