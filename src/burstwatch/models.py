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
class AnalysisConfig:
    smoothing_samples: int = 256
    threshold_sigma: float = 6.0
    min_burst_samples: int = 512
    merge_gap_samples: int = 256
    feature_window_count: int = 8
