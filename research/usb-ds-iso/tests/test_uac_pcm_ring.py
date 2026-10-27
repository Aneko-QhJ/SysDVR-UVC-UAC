"""Design checks for the UAC PCM ring / URB schedule model."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "pcm_model", Path(__file__).parents[1] / "tools/model_uac_pcm_ring.py"
)
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


class UacPcmRingTests(unittest.TestCase):
    def test_cursor_keeps_nominal_stream_contiguous(self):
        r = model.simulate(seconds=10)
        self.assertEqual(r["underrun_bytes"], 0)
        self.assertEqual(r["overrun_bytes"], 0)
        self.assertEqual(r["late_ms"], 0)
        self.assertEqual(r["max_gap_ms"], 0)
        self.assertEqual(r["posts"], 625)  # 10 s / 16 ms

    def test_timed_three_urbs_is_contiguous(self):
        r = model.simulate(seconds=10, timed_mode=True)
        self.assertEqual(r["underrun_bytes"], 0)
        self.assertEqual(r["overrun_bytes"], 0)
        self.assertEqual(r["max_gap_ms"], 0)
        self.assertEqual(r["posts"], 625)

    def test_a23_one_at_a_time_is_structural_underrun(self):
        r = model.simulate(seconds=10, a23_mode=True)
        self.assertEqual(r["max_gap_ms"], 32)
        self.assertGreater(r["overrun_bytes"], 0)
        self.assertLess(r["posts"], 625)
        # 16 ms of data per 48 ms wall => 33% of the source.
        self.assertEqual(r["posts"], 209)

    def test_source_pause_is_reported_as_underrun(self):
        r = model.simulate(seconds=10, source_pause=(3000, 3200))
        self.assertGreater(r["underrun_bytes"], 0)

    def test_poster_stall_is_late_but_covered_by_two_urbs(self):
        r = model.simulate(seconds=10, poster_stall=(5000, 5020))
        self.assertGreaterEqual(r["late_ms"], 10)
        self.assertEqual(r["underrun_bytes"], 0)

    def test_ring_never_exceeds_capacity(self):
        for kwargs in ({}, {"a23_mode": True}, {"source_pause": (1000, 1200)}):
            r = model.simulate(seconds=5, **kwargs)
            self.assertLessEqual(r["ring_max_bytes"], r["ring_bytes"])


if __name__ == "__main__":
    unittest.main()
