import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from pitch_utils import detect_pitch_and_note


class PitchAnalysisTests(unittest.TestCase):
    def test_sustained_a4(self):
        sample_rate = 22050
        times = np.arange(sample_rate) / sample_rate
        audio = 0.5 * np.sin(2 * np.pi * 440 * times)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tone.wav"
            sf.write(path, audio, sample_rate)
            frequency, note, cents, accuracy, _, _, error, timeline = (
                detect_pitch_and_note(str(path), "Voice")
            )
        self.assertIsNone(error)
        self.assertEqual(note, "A4")
        self.assertAlmostEqual(frequency, 440, delta=3)
        self.assertLess(abs(cents), 15)
        self.assertGreater(accuracy, 90)
        self.assertTrue(timeline)

    def test_silence_returns_a_helpful_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silence.wav"
            sf.write(path, np.zeros(22050), 22050)
            result = detect_pitch_and_note(str(path), "Voice")
        self.assertEqual(len(result), 8)
        self.assertIn("No audible audio", result[6])

    def test_missing_file_returns_a_helpful_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = detect_pitch_and_note(str(Path(directory) / "missing.wav"), "Voice")
        self.assertEqual(len(result), 8)
        self.assertIn("Could not load audio", result[6])


if __name__ == "__main__":
    unittest.main()
