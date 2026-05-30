from __future__ import annotations

from collections import Counter

from .capture import load_capture
from .detect import detect_bursts
from .features import classify_burst, extract_burst_features
from .models import AnalysisConfig, BurstEvent, Capture


def analyze_capture(capture: Capture, config: AnalysisConfig | None = None) -> list[BurstEvent]:
    config = config or AnalysisConfig()
    spans = detect_bursts(capture.samples, config)
    events: list[BurstEvent] = []

    for span in spans:
        burst_samples = capture.samples[span.start_sample : span.end_sample]
        features = extract_burst_features(
            burst_samples,
            sample_rate_hz=capture.sample_rate_hz,
            window_count=config.feature_window_count,
        )
        classification = classify_burst(features, sample_rate_hz=capture.sample_rate_hz)
        start_time_s = span.start_sample / capture.sample_rate_hz
        end_time_s = span.end_sample / capture.sample_rate_hz
        events.append(
            BurstEvent(
                capture_path=str(capture.path),
                sample_rate_hz=capture.sample_rate_hz,
                center_freq_hz=capture.center_freq_hz,
                start_sample=span.start_sample,
                end_sample=span.end_sample,
                start_time_s=start_time_s,
                end_time_s=end_time_s,
                duration_s=end_time_s - start_time_s,
                label=classification.label,
                confidence=classification.confidence,
                features=features,
                notes=classification.notes,
            )
        )

    return events


def analyze_path(
    path: str,
    *,
    sample_rate_hz: float | None = None,
    center_freq_hz: float | None = None,
    sample_format: str = "auto",
    config: AnalysisConfig | None = None,
) -> list[BurstEvent]:
    capture = load_capture(
        path,
        sample_rate_hz=sample_rate_hz,
        center_freq_hz=center_freq_hz,
        sample_format=sample_format,
    )
    return analyze_capture(capture, config=config)


def summarize_events(capture: Capture, events: list[BurstEvent]) -> dict[str, object]:
    counts = Counter(event.label for event in events)
    return {
        "source_path": str(capture.path),
        "sample_rate_hz": capture.sample_rate_hz,
        "center_freq_hz": capture.center_freq_hz,
        "burst_count": len(events),
        "label_counts": dict(sorted(counts.items())),
        "events": [event.to_dict() for event in events],
    }

