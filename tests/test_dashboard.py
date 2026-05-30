from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from burstwatch.artifacts import write_json_document
from burstwatch.dashboard import summarize_artifacts


class DashboardTests(unittest.TestCase):
    def test_summarize_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            write_json_document(
                {
                    "kind": "burstwatch.scan_summary.v1",
                    "event_count": 4,
                    "emitter_count": 2,
                },
                tmp_path / "scan.json",
            )
            write_json_document(
                {
                    "kind": "burstwatch.watch_summary.v1",
                    "alert_count": 1,
                    "new_count": 1,
                    "changed_count": 0,
                },
                tmp_path / "nested" / "watch.json",
            )
            write_json_document({"kind": "not.burstwatch"}, tmp_path / "ignored.json")

            artifacts = summarize_artifacts(tmp_path, recursive=True, limit=10)
            artifact_types = {artifact.artifact_type for artifact in artifacts}

            self.assertEqual(len(artifacts), 2)
            self.assertEqual(artifact_types, {"scan", "watch"})
            self.assertTrue(any("emitters=2" in artifact.metric for artifact in artifacts))
