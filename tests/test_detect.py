from __future__ import annotations

import unittest

from burstwatch.detect import detect_bursts
from burstwatch.models import AnalysisConfig
from burstwatch.synth import make_chirp_capture, make_fsk_capture, make_ook_capture


class DetectBurstsTests(unittest.TestCase):
    def test_detects_ook_burst(self) -> None:
        samples = make_ook_capture()
        config = AnalysisConfig(min_burst_samples=100)
        spans = detect_bursts(samples, config)
        self.assertGreaterEqual(len(spans), 1)

    def test_detects_multiple_signal_families(self) -> None:
        samples = make_fsk_capture()
        config = AnalysisConfig(min_burst_samples=100)
        spans = detect_bursts(samples, config)
        self.assertGreaterEqual(len(spans), 1)

        chirp_samples = make_chirp_capture()
        chirp_spans = detect_bursts(chirp_samples, config)
        self.assertGreaterEqual(len(chirp_spans), 1)

