import array
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import check_uac_wav


def write_wav(path, seconds=0.2, rate=48000, channels=2, width=2, value=None):
    frames = int(round(seconds * rate))
    samples = array.array("h")
    for i in range(frames * channels):
        samples.append(0 if value is None else value)
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())


class UacWavTest(unittest.TestCase):
    def test_valid_short_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "uac.wav"
            write_wav(path, seconds=0.2, value=123)
            result = check_uac_wav.check(path, 0.2, 48000, 2, 2)
        self.assertTrue(result["ok"])
        self.assertTrue(result["format_ok"])
        self.assertTrue(result["duration_ok"])
        self.assertEqual(result["frames"], 9600)
        self.assertNotIn("all_silence", result["warnings"])

    def test_all_silence_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "silence.wav"
            write_wav(path, seconds=0.1, value=0)
            result = check_uac_wav.check(path, 0.1, 48000, 2, 2)
        self.assertTrue(result["ok"])
        self.assertIn("all_silence", result["warnings"])

    def test_wrong_format_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mono.wav"
            write_wav(path, seconds=0.1, channels=1, value=10)
            result = check_uac_wav.check(path, 0.2, 48000, 2, 2)
        self.assertFalse(result["format_ok"])
        self.assertFalse(result["duration_ok"])
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
