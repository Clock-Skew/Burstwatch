from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Capture:
    path: Path
    samples: Any
    sample_rate_hz: float
    center_freq_hz: float | None = None
    sample_kind: str = "complex64"


@dataclass(frozen=True)
class BurstSpan:
    index: int
    start_sample: int
    end_sample: int
    threshold: float
    peak: float
    mean_envelope: float


@dataclass(frozen=True)
class BurstFeatures:
    peak_amplitude: float
    rms_amplitude: float
    crest_factor: float
    envelope_variation: float
    duty_cycle: float
    bandwidth_hz: float
    spectral_flatness: float
    spectral_centroid_hz: float
    chirp_slope_hz_per_s: float
    frequency_trend_consistency: float
    frequency_track_error_ratio: float
    tone_count: int
    tone_separation_hz: float | None
    dominant_tones_hz: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BurstClassification:
    label: str
    confidence: float
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BurstEvent:
    capture_path: str
    sample_rate_hz: float
    center_freq_hz: float | None
    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float
    duration_s: float
    label: str
    confidence: float
    features: BurstFeatures
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScanEmitter:
    candidate_id: str
    approx_freq_hz: float | None
    dominant_label: str
    label_counts: dict[str, int]
    burst_count: int
    capture_count: int
    total_on_air_s: float
    duration_min_s: float
    duration_max_s: float
    mean_duration_s: float
    bandwidth_min_hz: float
    bandwidth_max_hz: float
    mean_bandwidth_hz: float
    mean_duty_cycle: float
    mean_confidence: float
    repetition_interval_mean_s: float | None
    repetition_interval_std_s: float | None
    source_paths: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScanSummary:
    kind: str
    input_paths: tuple[str, ...]
    event_count: int
    emitter_count: int
    label_counts: dict[str, int]
    emitters: tuple[ScanEmitter, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmitterFingerprint:
    fingerprint_id: str
    approx_freq_hz: float | None
    dominant_label: str
    burst_count: int
    duration_min_s: float
    duration_max_s: float
    mean_duration_s: float
    bandwidth_min_hz: float
    bandwidth_max_hz: float
    mean_bandwidth_hz: float
    mean_duty_cycle: float
    mean_confidence: float
    repetition_interval_mean_s: float | None
    repetition_interval_std_s: float | None
    source_paths: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FingerprintSummary:
    kind: str
    input_paths: tuple[str, ...]
    fingerprint_count: int
    fingerprints: tuple[EmitterFingerprint, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineRecord:
    baseline_id: str
    approx_freq_hz: float | None
    dominant_label: str
    scans_seen: int
    burst_count_mean: float
    burst_count_max: int
    duration_mean_s: float
    duration_std_s: float
    bandwidth_mean_hz: float
    bandwidth_std_hz: float
    duty_cycle_mean: float
    confidence_mean: float
    frequency_tolerance_hz: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineSummary:
    kind: str
    source_scan_paths: tuple[str, ...]
    record_count: int
    records: tuple[BaselineRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchAlert:
    candidate_id: str
    status: str
    message: str
    dominant_label: str
    approx_freq_hz: float | None
    baseline_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchSummary:
    kind: str
    baseline_path: str
    alert_count: int
    new_count: int
    changed_count: int
    alerts: tuple[WatchAlert, ...]
    scan: ScanSummary

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisConfig:
    smoothing_samples: int = 256
    threshold_sigma: float = 6.0
    min_burst_samples: int = 512
    merge_gap_samples: int = 256
    feature_window_count: int = 8
