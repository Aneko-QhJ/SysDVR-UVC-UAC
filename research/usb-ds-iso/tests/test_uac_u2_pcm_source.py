"""v43: feed the U2 burst producer with real grc:d game audio.

The device used to fill every 3072-byte set with a synthetic 1 kHz square.
The capture side already existed (CaptureReadAudioFrame reads 4096 B =
1024 stereo frames = 21.3 ms from grc:d); v43 adds the missing middle: a
single-producer/single-consumer ring, drained 3072 B (16 ms) per posted set,
zero-filled on underrun, oldest-dropped on overflow, reset at alt0 so a re-arm
never replays stale audio.  The audio thread must gate on the UAC stream, not
on the video stream (a host may open only the audio function).
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
UVC = REPO / "source/uvc/uvc_device.c"
MAIN = REPO / "source/sysmodule/main.c"
HEADER = REPO / "source/uvc/uvc_device.h"
RING = REPO / "source/uvc/pcm_ring.c"


class UacU2PcmSourceTests(unittest.TestCase):
    def setUp(self):
        for path in (UVC, MAIN, HEADER, RING):
            if not path.is_file():
                self.skipTest(f"missing {path}")
        self.uvc = UVC.read_text()
        self.main = MAIN.read_text()
        self.header = HEADER.read_text()

    def test_ring_is_opt_in_and_sized_for_jitter(self):
        self.assertIn("#if defined(UAC_U2_PCM_SOURCE)", self.uvc)
        self.assertIn("#define UAC_PCM_RING_BYTES 0x10000", self.uvc)
        self.assertIn("PcmRingInit(&g_pcmRing", self.uvc)
        self.assertIn("PcmRingInit", RING.read_text())

    def test_producer_drains_the_ring_instead_of_the_pattern(self):
        # the continuous path and the bounded train both read the ring
        self.assertEqual(self.uvc.count(
            "PcmRingReadFill(&g_pcmRing, buf, UAC_U2_BURST_BYTES);"), 2)
        # the synthetic pattern survives only in the #else branch
        self.assertEqual(self.uvc.count("((frame / 24) & 1) ? 0x4000"), 2)
        start = self.uvc.index("PcmRingReadFill(&g_pcmRing")
        self.assertLess(self.uvc.rindex("#else", 0, start), start)
        self.assertLess(self.uvc.rindex("#if defined(UAC_U2_PCM_SOURCE)", 0, start),
                        start)

    def test_alt0_drops_the_backlog(self):
        stop = self.uvc.index("case UAC_ACT_STOP:")
        reset = self.uvc.index("PcmRingReset(&g_pcmRing);")
        self.assertGreater(reset, stop)
        self.assertLess(reset, self.uvc.index("case UAC_ACT_ACK:", stop))

    def test_audio_thread_gates_on_the_uac_stream(self):
        start = self.main.index("#if defined(UAC_U2_PCM_SOURCE)")
        body = self.main[start:self.main.index("#else", start)]
        self.assertIn("UacDeviceIsStreaming()", body)
        self.assertNotIn("UvcDeviceIsStreaming()", body)
        self.assertIn("CaptureReadAudioFrame(&frame)", body)
        self.assertIn("UacDevicePushPcm(frame.Data, frame.DataSize)", body)
        # the old per-packet sender is gone from the PCM path
        self.assertNotIn("UacDeviceSendAudio(", body)

    def test_video_thread_primes_grc_for_uac_only_streams(self):
        # grc:d starts on the first Video transfer; a UAC-only host never opens
        # the camera, so the video thread must keep the pipeline alive.
        mark = self.main.index("v44: grc:d only starts producing")
        self.assertIn("UacDeviceIsStreaming()", self.main[mark:mark + 900])
        self.assertIn("CaptureReadVideoFrame(&frame);", self.main[mark:mark + 900])
        self.assertLess(mark, self.main.index("svcSleepThread(50E+6);  // 50ms"))

    def test_push_api_is_declared_and_defined_guarded(self):
        self.assertIn("void UacDevicePushPcm(const void* data, size_t size);",
                      self.header)
        self.assertIn("void UacDevicePushPcm(const void* data, size_t size)",
                      self.uvc)
        # the grc:d thread logs nothing per push (SD writes would pace USB)
        body = self.uvc[self.uvc.index("void UacDevicePushPcm"):
                        self.uvc.index("bool UacDeviceSendAudio")]
        self.assertNotIn("LOG(", body)


if __name__ == "__main__":
    unittest.main()
