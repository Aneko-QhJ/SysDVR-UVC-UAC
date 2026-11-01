"""v24 gap probe: the per-burst dmnt dumps are gated, phase timing is logged.

The v23 run delivered 4 x 3072 B but with 160/162/142 ms gaps for 16 ms
bursts.  Every per-burst `_uacLogSubmitState` / `_uacLogRingState` /
`_uacLogInstallState` is a debug-process attach, so a light-log build keeps
only the cheap lines and adds svcGetSystemTick phase timing.  These tests pin
the source structure that the next build depends on; no hardware is needed.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"

GUARD = "#ifndef UAC_U2_LIGHT_LOG"
TIMING = ('LOG("UAC U2 timing seq=%u loop_ms=%u post_ms=%u wait_ms=%u '
          'report_ms=%u online_ms=%u\\n"')



class UacU2LightLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.source = SOURCE.read_text()

    def _block(self) -> str:
        """The U2 train loop region, from 'u32 posted = 0' to the train end."""
        start = self.source.index("u32 posted = 0, completed = 0;")
        end = self.source.index('LOG("UAC U2 train end posted=%u completed=%u pattern=%u', start)
        end = self.source.index("}", end)
        return self.source[start:end]

    def test_dmnt_dumps_are_behind_the_light_log_guard(self):
        block = self._block()
        self.assertGreaterEqual(block.count(GUARD), 3)
        for call in ('_uacLogSubmitState("pre", seq);',
                     '_uacLogSubmitState("post", seq);',
                     '_uacLogSubmitState("done", seq);'):
            index = block.index(call)
            # the nearest guard before the call must not be closed yet
            guard = block.rfind(GUARD, 0, index)
            endif = block.rfind("#endif", 0, index)
            self.assertGreater(guard, endif, call)

    def test_failure_paths_keep_their_dumps(self):
        block = self._block()
        timeout = block.index("no completion within 100ms")
        self.assertIn('_uacLogSubmitState("timeout", seq);', block[timeout:])
        report_fail = block.index("UAC U2 report rc=0x%x seq=%u")
        self.assertIn('_uacLogSubmitState("report-fail", seq);', block[report_fail:])

    def test_phase_timing_is_logged_after_the_completion(self):
        block = self._block()
        self.assertIn(TIMING, block)
        complete = block.index('LOG("UAC U2 complete rc=0x%x requested=%u transferred=%u seq=%u')
        timing = block.index(TIMING)
        self.assertLess(complete, timing)
        # svcGetSystemTick is 19.2 MHz on Horizon: 19200 ticks per ms.
        for expr in ("(tPre - tPrev) / 19200", "(tPost - tPre) / 19200",
                     "(tDone - tPost) / 19200", "(tReport - tDone) / 19200",
                     "(tReport - tPrev) / 19200"):
            self.assertIn(expr, block)
        self.assertIn("tPrev = tReport;", block)

    def test_timing_starts_before_the_loop_and_follows_the_report(self):
        block = self._block()
        loop = block.index("for (u32 n = 0; n < UAC_U2_TRAIN_POSTS; ++n)")
        self.assertLess(block.index("u64 tPrev = svcGetSystemTick();"), loop)
        post = block.index("usbDsEndpoint_PostBufferAsync(")
        tpre = block.index("const u64 tPre = svcGetSystemTick();")
        tpost = block.index("const u64 tPost = svcGetSystemTick();")
        wait = block.index("eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent")
        tdone = block.index("const u64 tDone = svcGetSystemTick();")
        report = block.index("usbDsEndpoint_GetReportData(")
        self.assertLess(tpre, post)
        self.assertLess(post, tpost)
        self.assertLess(tpost, wait)
        self.assertLess(wait, tdone)
        self.assertLess(tdone, report)

    def test_final_dumps_stay_outside_the_guard(self):
        block = self._block()
        tail = block[block.index("train end"):]
        self.assertIn("_uacLogInstallState();", tail)
        self.assertIn("_uacLogRingState();", tail)
        self.assertNotIn(GUARD, tail)


if __name__ == "__main__":
    unittest.main()
