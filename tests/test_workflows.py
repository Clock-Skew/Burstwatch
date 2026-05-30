from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from burstwatch.artifacts import write_json_document
from burstwatch.models import AnalysisConfig
from burstwatch.synth import make_chirp_capture, make_ook_capture, write_complex64
from burstwatch.workflows import build_baseline, build_fingerprints, scan_inputs, watch_against_baseline


class WorkflowTests(unittest.TestCase):
    def test_scan_and_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ook_path = tmp_path / "ook.c64"
            chirp_path = tmp_path / "chirp.c64"
            write_complex64(ook_path, make_ook_capture(carrier_hz=1_200.0))
            write_complex64(chirp_path, make_chirp_capture(start_hz=3_200.0, stop_hz=4_600.0))

            summary, _events = scan_inputs(
                [ook_path, chirp_path],
                sample_rate_hz=20_000.0,
                center_freq_hz=433_920_000.0,
                sample_format="complex64",
                config_factory=lambda sample_rate_hz: AnalysisConfig(min_burst_samples=100),
                freq_bin_hz=200.0,
            )
            self.assertEqual(summary.emitter_count, 2)

            fingerprints = build_fingerprints(summary, name_prefix="lab")
            self.assertEqual(fingerprints.fingerprint_count, 2)
            self.assertEqual(fingerprints.fingerprints[0].fingerprint_id, "lab-001")

    def test_baseline_and_watch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            baseline_capture = tmp_path / "baseline-ook.c64"
            current_ook = tmp_path / "current-ook.c64"
            current_chirp = tmp_path / "current-chirp.c64"
            write_complex64(baseline_capture, make_ook_capture(carrier_hz=1_200.0, seed=11))
            write_complex64(current_ook, make_ook_capture(carrier_hz=1_200.0, seed=12))
            write_complex64(current_chirp, make_chirp_capture(start_hz=3_200.0, stop_hz=4_600.0, seed=13))

            baseline_scan, _baseline_events = scan_inputs(
                [baseline_capture],
                sample_rate_hz=20_000.0,
                center_freq_hz=433_920_000.0,
                sample_format="complex64",
                config_factory=lambda sample_rate_hz: AnalysisConfig(min_burst_samples=100),
                freq_bin_hz=200.0,
            )
            baseline_scan_path = tmp_path / "baseline-scan.json"
            write_json_document(baseline_scan.to_dict(), baseline_scan_path)

            baseline = build_baseline([baseline_scan_path], freq_bin_hz=200.0)
            baseline_path = tmp_path / "baseline.json"
            write_json_document(baseline.to_dict(), baseline_path)

            current_scan, _current_events = scan_inputs(
                [current_ook, current_chirp],
                sample_rate_hz=20_000.0,
                center_freq_hz=433_920_000.0,
                sample_format="complex64",
                config_factory=lambda sample_rate_hz: AnalysisConfig(min_burst_samples=100),
                freq_bin_hz=200.0,
            )
            watch = watch_against_baseline(baseline_path, current_scan)
            self.assertEqual(watch.new_count, 1)
            self.assertEqual(watch.changed_count, 0)
            self.assertEqual(watch.alerts[0].status, "new")
