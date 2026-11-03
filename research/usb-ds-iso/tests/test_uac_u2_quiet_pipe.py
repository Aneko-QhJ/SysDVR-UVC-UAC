"""v29q quiet pipeline: stop measuring the pipeline from inside the pipeline.

Every v29 run kept `-DUAC_U2_CURSOR_DIAG` and the per-post `LOG` lines, so a
16 ms TD set carried three dmnt attaches and two SD log writes.  The cursor
advance between back-to-back posts in the v29p log was 17-19 frames instead of
the 16 of one set, i.e. the measurement itself was inserting the holes that
the controller reports as missed service.  The quiet build keeps counters in
RAM and writes one summary at the end; these tests pin that structure.  No
hardware is touched.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"

QUIET = "#if defined(UAC_U2_QUIET_PIPE)"
SUMMARY = 'LOG("UAC U2 pipe timing waits=%u timeouts=%u span_ms=%llu'


class UacU2QuietPipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()
        start = cls.text.index("u32 next = 0, posted = 0, completed = 0")
        end = cls.text.index('LOG("UAC U2 pipe end posted=%u completed=%u bytes=%u'
                             ' misses=%u recoveries=%u\\n"', start)
        cls.loop = cls.text[start:end]

    def test_quiet_macro_swallows_the_per_post_lines(self):
        self.assertIn(QUIET, self.text)
        self.assertIn("#define UAC_U2_PIPE_LOG(...) do { } while (0)", self.text)
        self.assertIn("#define UAC_U2_PIPE_LOG(...) LOG(__VA_ARGS__)", self.text)

    def test_hot_lines_go_through_the_macro(self):
        for call in ('UAC_U2_PIPE_LOG("UAC U2 pipe post buf=%u urb=%u rc=0x%x seq=%u',
                     'UAC_U2_PIPE_LOG("UAC U2 pipe done buf=%u urb=%u xfer=%u status=%u'):
            self.assertIn(call, self.loop, call)

    def test_no_raw_log_in_the_hot_loop(self):
        # every hot-loop line must be wrapped: "UAC_U2_PIPE_LOG(LOG(...)"
        # would still contain the bare LOG text, so check the prefix instead.
        for text in ("UAC U2 pipe post ", "UAC U2 pipe done "):
            index = self.loop.index(text)
            prefix = self.loop[:index]
            self.assertTrue(prefix.rstrip().endswith("UAC_U2_PIPE_LOG(\""),
                            text)

    def test_a_miss_still_names_the_lost_set(self):
        # rare, so it stays a plain line: it is the only attribution left
        # once the per-post lines are gone.
        self.assertIn('LOG("UAC U2 pipe miss buf=%u status=%u', self.loop)
        self.assertNotIn('UAC_U2_PIPE_LOG("UAC U2 pipe miss', self.loop)

    def test_counters_are_taken_in_ram(self):
        self.assertIn("u32 waits = 0, timeouts = 0;", self.loop)
        self.assertIn("u64 first_post_tick = 0, last_done_tick = 0;", self.loop)
        self.assertIn("u64 max_gap_tick = 0, max_react_tick = 0;", self.loop)
        self.assertIn("if (posted == 1) first_post_tick = svcGetSystemTick();",
                      self.loop)
        self.assertIn("const u64 done_tick = svcGetSystemTick();", self.loop)
        self.assertIn("last_done_tick = done_tick;", self.loop)
        self.assertIn("const u64 react = svcGetSystemTick() - last_done_tick;",
                      self.loop)
        self.assertIn("++waits;", self.loop)
        self.assertIn("++timeouts;", self.loop)

    def test_one_summary_line_after_the_standard_end(self):
        end = self.text.index('LOG("UAC U2 pipe end posted=%u completed=%u bytes=%u'
                              ' misses=%u recoveries=%u\\n"')
        summary = self.text.index(SUMMARY)
        self.assertLess(end, summary)
        self.assertIn("span / 19200", self.text)
        self.assertIn("max_gap_ms=%llu max_react_ms=%llu", self.text)
        self.assertIn("max_gap_tick / 19200", self.text)
        self.assertIn("max_react_tick / 19200", self.text)

    def test_timing_line_is_unconditional(self):
        # the counters are cheap and the line lands once at the end, so a
        # diagnostic build reports them too and no counter is set-but-unused.
        index = self.text.index("const u64 span = (last_done_tick")
        guard = self.text.rfind("#if defined(UAC_U2_QUIET_PIPE)", 0, index)
        endif = self.text.rfind("#endif", 0, index)
        self.assertGreater(endif, guard)
        self.assertNotIn("#endif\n    {\n        /* v29q: the pipeline",
                         self.text)

    def test_quiet_build_keeps_the_payload_out_of_it(self):
        # The quiet mode is an app define only: it must not appear in the
        # payload/cave builder, so a run stays comparable with v29m.
        for tool in ("tools/build_uac_u2_producer.py",
                     "tools/build_uac_u2_probe.py"):
            self.assertNotIn("UAC_U2_QUIET_PIPE", (ROOT / tool).read_text(), tool)


class UacU2StallLimitTests(unittest.TestCase):
    """v29r: the stall limit is a build define, default 100 ms.

    v29q showed the one miss cost 181 ms of silence: the app only cancels
    after 100 ms without progress and the next TD set starts 32 ms later.
    Waiting 100 ms to repair a 16 ms set is six times the damage.
    """

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_default_and_range(self):
        self.assertIn("#ifndef UAC_U2_STALL_MS", self.text)
        self.assertIn("#define UAC_U2_STALL_MS 100", self.text)
        self.assertIn('#error "UAC_U2_STALL_MS must be 16..1000"', self.text)

    def test_loop_uses_the_define_not_a_literal(self):
        self.assertIn("(u64)UAC_U2_STALL_MS * 19200", self.text)
        self.assertNotIn("> 100ULL * 19200", self.text)

    def test_recovery_lines_name_the_limit(self):
        self.assertIn("pipe stall recover cancelled=%u rc=0x%x limit_ms=%u",
                      self.text)
        self.assertIn("pipe stall posted=%u completed=%u limit_ms=%u",
                      self.text)


class UacU2InFlightTests(unittest.TestCase):
    """v29u: the in-flight depth is a build define (default 3, ring allows 6)."""

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_default_and_range(self):
        self.assertIn("#ifndef UAC_U2_IN_FLIGHT", self.text)
        self.assertIn("#define UAC_U2_IN_FLIGHT 3", self.text)
        self.assertIn('#error "UAC_U2_IN_FLIGHT must be 2..5', self.text)

    def test_loop_uses_the_define(self):
        self.assertIn("posted - completed < UAC_U2_IN_FLIGHT", self.text)
        self.assertNotIn("posted - completed < 3", self.text)


class UacU2MissRecoveryTests(unittest.TestCase):
    """v29t: a status=5 report cancels and reposts immediately.

    v29s showed the halt comes from completion code 23 (Missed Service) and
    that the driver only sets regs+0x50 for it, so prod/cons stay put and the
    cave cannot re-arm.  Waiting for the 100 ms stall timer only stretches the
    silence; a status=5 report is already the proof that nothing will complete.
    """

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_status5_is_remembered(self):
        self.assertIn("bool halt_miss = false; /* v29t: a status=5 report means",
                      self.text)
        self.assertIn("if (report.report[i].urb_status == 5) halt_miss = true;",
                      self.text)

    def test_recovery_cancels_before_the_stall_timer(self):
        index = self.text.index("if (halt_miss && recoveries < UAC_U2_MAX_RECOVERIES")
        block = self.text[index:index + 1600]
        self.assertIn("usbDsEndpoint_Cancel", block)
        self.assertIn("pipe miss recover cancelled=%u rc=0x%x", self.text)
        # the recovery comes after the report loop, before the loop's own
        # last_progress update, so it takes effect on the same iteration
        self.assertIn("continue;", block)

    def test_recovery_cap_is_a_define(self):
        self.assertIn("#ifndef UAC_U2_MAX_RECOVERIES", self.text)
        self.assertIn("#define UAC_U2_MAX_RECOVERIES 8", self.text)
        self.assertNotIn("recoveries < 8", self.text)


if __name__ == "__main__":
    unittest.main()
