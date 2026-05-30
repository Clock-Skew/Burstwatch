from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

from burstwatch.capture import load_capture
from burstwatch.models import AnalysisConfig
from burstwatch.pipeline import analyze_capture, summarize_events
from burstwatch.store import write_jsonl, write_sqlite
from burstwatch.synth import make_ook_capture, write_complex64


class PipelineTests(unittest.TestCase):
    def test_analyze_and_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_path = tmp_path / "capture.c64"
            write_complex64(capture_path, make_ook_capture())

            capture = load_capture(capture_path, sample_rate_hz=20_000.0, sample_format="complex64")
            events = analyze_capture(capture, AnalysisConfig(min_burst_samples=100))
            self.assertGreaterEqual(len(events), 1)

            jsonl_path = tmp_path / "events.jsonl"
            sqlite_path = tmp_path / "events.sqlite3"
            self.assertEqual(write_jsonl(events, jsonl_path), len(events))
            self.assertEqual(write_sqlite(events, sqlite_path), len(events))

            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), len(events))
            payload = json.loads(lines[0])
            self.assertIn("label", payload)

            with sqlite3.connect(sqlite_path) as connection:
                row_count = connection.execute("SELECT COUNT(*) FROM bursts").fetchone()[0]
            self.assertEqual(row_count, len(events))

            summary = summarize_events(capture, events)
            self.assertIn("burst_count", summary)

