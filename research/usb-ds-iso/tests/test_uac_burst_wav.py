"""Synthetic checks for the U2 1 kHz burst WAV detector."""
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_uac_burst_wav import detect


def write_wav(path, frames, rate=48000, channels=2):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(struct.pack("<hh", *f) for f in frames))


def silence(rate, seconds):
    return [(0, 0)] * int(rate * seconds)


def square(rate, seconds, hz=1000, amplitude=0x4000):
    frames = []
    half = max(1, rate // (2 * hz))
    for n in range(int(rate * seconds)):
        value = amplitude if (n // half) % 2 == 0 else -amplitude
        frames.append((value, value))
    return frames


class UacBurstWavTests(unittest.TestCase):
    def test_detects_the_16ms_1khz_square(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "burst.wav"
            write_wav(path, silence(48000, 0.1) + square(48000, 0.016) +
                      silence(48000, 0.1))
            rate, frames = __import__("check_uac_burst_wav").read_wav(path)
            found, runs = detect(rate, frames)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found["duration_ms"], 16.0, delta=1.0)
        self.assertTrue(found["square_1khz"])
        self.assertGreaterEqual(found["peak"], 0x4000 // 2)
        self.assertTrue(1500 <= found["zero_crossings_per_s"] <= 2500)
        self.assertTrue(runs)

    def test_silence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "silence.wav"
            write_wav(path, silence(48000, 0.2))
            rate, frames = __import__("check_uac_burst_wav").read_wav(path)
            found, _runs = detect(rate, frames)
        self.assertIsNone(found)

    def test_500hz_square_is_not_mistaken_for_1khz(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "500hz.wav"
            write_wav(path, silence(48000, 0.05) + square(48000, 0.016, hz=500) +
                      silence(48000, 0.05))
            rate, frames = __import__("check_uac_burst_wav").read_wav(path)
            found, _runs = detect(rate, frames)
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
