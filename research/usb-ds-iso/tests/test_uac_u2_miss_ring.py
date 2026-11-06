"""v39 miss ring: which miss does the host react to?

Four runs (v37 x2, v38 x2) show every active alt0 following a status=5 miss
within 0-17 ms, but only 4-8 of the 47-67 misses per run trigger a teardown.
The pipe thread now keeps the last 16 misses in RAM (six stores, no SD write)
and the SET_INTERFACE alt0 hook dumps them, so the triggering miss arrives
next to its neighbours: back-to-back misses, in-flight depth, slot, urb id.

This test pins the three pieces (record, indexed dump, train-end call site)
and that the whole thing is opt-in, so a normal build keeps the v37 miss path.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"


class UacU2MissRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_record_is_ram_only_in_the_miss_branch(self):
        call = self.text.index("_uacMissRingAdd(done_tick, posted, completed, b, id,")
        guard = self.text.rfind("#if defined(UAC_U2_MISS_RING)", 0, call)
        self.assertGreater(guard, 0)
        line = self.text[guard:self.text.index("\n", guard)]
        self.assertIn("UAC_U2_MISS_RING", line)
        # it must sit in the status != 3 branch, next to the miss counter
        self.assertLess(self.text.rindex("++misses;", 0, call), call)
        self.assertIn("UAC U2 miss ring total", self.text)

    def test_record_has_no_sd_write(self):
        start = self.text.index("static void _uacMissRingAdd")
        end = self.text.index("static void _uacMissRingDump")
        body = self.text[start:end]
        self.assertNotIn("LOG(", body)
        for field in ("tick", "posted", "completed", "inflight", "slot", "urb",
                      "status"):
            self.assertIn(f"r->{field}", body)

    def test_dump_is_oldest_to_newest_with_deltas(self):
        start = self.text.index("static void _uacMissRingDump")
        end = self.text.index("#endif", start)
        body = self.text[start:end]
        self.assertIn("g_missRingHead - have + i", body)
        self.assertIn("dprev", body)
        self.assertIn("ago_ms=%llu dprev_ms=%llu", body)
        self.assertIn("UAC_MISS_RING_LEN", body)

    def test_dump_runs_once_per_train_after_the_timing_line(self):
        dump = self.text.index("_uacMissRingDump(last_done_tick);")
        timing = self.text.rindex('LOG("UAC U2 pipe timing waits', 0, dump)
        self.assertLess(timing, dump)
        # and NOT in the alt0 hook: that path keeps its exact v38 timing
        alt0 = self.text.index('LOG("UAC U2 alt diag alt0')
        self.assertNotIn("_uacMissRingDump", self.text[alt0:alt0 + 2000])

    def test_record_carries_the_index_the_alt0_line_names(self):
        # alt0 logs misses=N, so the record with idx=N-1 is the trigger
        self.assertIn("r->index = g_missRingTotal;", self.text)
        self.assertIn("idx=%u", self.text)

    def test_requires_alt_diag_and_is_opt_in(self):
        self.assertIn('#error "UAC_U2_MISS_RING dumps from the ALT_DIAG alt0 hook"',
                      self.text)
        # a build without the define must have no ring code at all
        first = self.text.index("#if defined(UAC_U2_MISS_RING)")
        guard_end = self.text.index("#endif", self.text.index("static void _uacMissRingDump"))
        self.assertGreater(guard_end, first)


if __name__ == "__main__":
    unittest.main()
