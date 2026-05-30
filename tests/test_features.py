from __future__ import annotations

import unittest

from burstwatch.detect import detect_bursts
from burstwatch.features import classify_burst, extract_burst_features
from burstwatch.models import AnalysisConfig
from burstwatch.synth import (
    make_chirp_capture,
    make_fm_like_capture,
    make_fsk_capture,
    make_ook_capture,
)


class FeatureClassificationTests(unittest.TestCase):
    def test_classifies_ook(self) -> None:
        features = self._features_for_burst(make_ook_capture())
        classification = classify_burst(features, sample_rate_hz=20_000.0)
        self.assertEqual(classification.label, "ook_ask")

    def test_classifies_fsk(self) -> None:
        features = self._features_for_burst(make_fsk_capture())
        classification = classify_burst(features, sample_rate_hz=20_000.0)
        self.assertEqual(classification.label, "fsk")

    def test_classifies_chirp(self) -> None:
        features = self._features_for_burst(make_chirp_capture())
        classification = classify_burst(features, sample_rate_hz=20_000.0)
        self.assertEqual(classification.label, "chirp")

    def test_classifies_fm_like(self) -> None:
        features = self._features_for_burst(make_fm_like_capture())
        classification = classify_burst(features, sample_rate_hz=20_000.0)
        self.assertEqual(classification.label, "fm_like")

    def _features_for_burst(self, samples):
        spans = detect_bursts(samples, AnalysisConfig(min_burst_samples=100))
        self.assertGreaterEqual(len(spans), 1)
        span = spans[0]
        segment = samples[span.start_sample : span.end_sample]
        return extract_burst_features(segment, sample_rate_hz=20_000.0)
