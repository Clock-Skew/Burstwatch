from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import read_json_document


@dataclass(frozen=True)
class ArtifactSummary:
    path: Path
    kind: str
    artifact_type: str
    metric: str
    modified_at: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "artifact_type": self.artifact_type,
            "metric": self.metric,
            "modified_at": self.modified_at,
            "size_bytes": self.size_bytes,
        }


def summarize_artifacts(
    root: str | Path,
    *,
    recursive: bool = True,
    limit: int = 12,
) -> list[ArtifactSummary]:
    root_path = Path(root)
    if not root_path.exists():
        return []
    paths = root_path.rglob("*.json") if recursive else root_path.glob("*.json")
    summaries: list[ArtifactSummary] = []
    for path in sorted(paths):
        try:
            document = read_json_document(path)
        except (OSError, ValueError):
            continue
        summary = _artifact_from_document(path, document)
        if summary is not None:
            summaries.append(summary)

    summaries.sort(key=lambda artifact: artifact.path.stat().st_mtime, reverse=True)
    return summaries[: max(0, int(limit))]


def _artifact_from_document(path: Path, document: dict[str, Any]) -> ArtifactSummary | None:
    kind = str(document.get("kind", ""))
    artifact_type = _artifact_type(kind)
    if artifact_type is None:
        return None
    stat = path.stat()
    return ArtifactSummary(
        path=path,
        kind=kind,
        artifact_type=artifact_type,
        metric=_artifact_metric(kind, document),
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        size_bytes=stat.st_size,
    )


def _artifact_type(kind: str) -> str | None:
    mapping = {
        "burstwatch.scan_summary.v1": "scan",
        "burstwatch.fingerprint_summary.v1": "fingerprints",
        "burstwatch.baseline_summary.v1": "baseline",
        "burstwatch.watch_summary.v1": "watch",
        "burstwatch.rtl_sdr_capture.v1": "capture",
    }
    return mapping.get(kind)


def _artifact_metric(kind: str, document: dict[str, Any]) -> str:
    if kind == "burstwatch.scan_summary.v1":
        return f"emitters={document.get('emitter_count', 0)} events={document.get('event_count', 0)}"
    if kind == "burstwatch.fingerprint_summary.v1":
        return f"fingerprints={document.get('fingerprint_count', 0)}"
    if kind == "burstwatch.baseline_summary.v1":
        return f"records={document.get('record_count', 0)}"
    if kind == "burstwatch.watch_summary.v1":
        return (
            f"alerts={document.get('alert_count', 0)} "
            f"new={document.get('new_count', 0)} changed={document.get('changed_count', 0)}"
        )
    if kind == "burstwatch.rtl_sdr_capture.v1":
        return (
            f"samples={document.get('sample_count', 0)} "
            f"freq={document.get('center_freq_hz', 'unknown')}"
        )
    return "recognized"
