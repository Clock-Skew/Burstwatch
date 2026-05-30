from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Callable

from .artifacts import read_json_document
from .capture import load_capture
from .models import (
    AnalysisConfig,
    BaselineRecord,
    BaselineSummary,
    BurstEvent,
    EmitterFingerprint,
    FingerprintSummary,
    ScanEmitter,
    ScanSummary,
    WatchAlert,
    WatchSummary,
)
from .pipeline import analyze_capture


def resolve_capture_paths(
    inputs: list[str | Path],
    *,
    recursive: bool = False,
    patterns: tuple[str, ...] = ("*.c64", "*.wav"),
) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for raw_input in inputs:
        path = Path(raw_input)
        if path.is_dir():
            iterator_name = "rglob" if recursive else "glob"
            for pattern in patterns:
                iterator = getattr(path, iterator_name)(pattern)
                for candidate in sorted(iterator):
                    resolved = candidate.resolve()
                    if resolved not in seen and candidate.is_file():
                        paths.append(candidate)
                        seen.add(resolved)
            continue

        resolved = path.resolve()
        if resolved not in seen:
            paths.append(path)
            seen.add(resolved)
    return paths


def scan_inputs(
    inputs: list[str | Path],
    *,
    sample_rate_hz: float | None,
    center_freq_hz: float | None,
    sample_format: str,
    config_factory: Callable[[float], AnalysisConfig],
    recursive: bool = False,
    patterns: tuple[str, ...] = ("*.c64", "*.wav"),
    freq_bin_hz: float = 25_000.0,
) -> tuple[ScanSummary, list[BurstEvent]]:
    paths = resolve_capture_paths(inputs, recursive=recursive, patterns=patterns)
    events: list[BurstEvent] = []
    for path in paths:
        capture = load_capture(
            path,
            sample_rate_hz=sample_rate_hz,
            center_freq_hz=center_freq_hz,
            sample_format=sample_format,
        )
        events.extend(analyze_capture(capture, config_factory(capture.sample_rate_hz)))

    emitters = _build_emitters(events, freq_bin_hz=freq_bin_hz)
    label_counts = Counter(event.label for event in events)
    summary = ScanSummary(
        kind="burstwatch.scan_summary.v1",
        input_paths=tuple(str(path) for path in paths),
        event_count=len(events),
        emitter_count=len(emitters),
        label_counts=dict(sorted(label_counts.items())),
        emitters=tuple(emitters),
    )
    return summary, events


def build_fingerprints(
    scan_summary: ScanSummary,
    *,
    name_prefix: str = "fp",
) -> FingerprintSummary:
    fingerprints: list[EmitterFingerprint] = []
    for index, emitter in enumerate(scan_summary.emitters, start=1):
        fingerprints.append(
            EmitterFingerprint(
                fingerprint_id=f"{name_prefix}-{index:03d}",
                approx_freq_hz=emitter.approx_freq_hz,
                dominant_label=emitter.dominant_label,
                burst_count=emitter.burst_count,
                duration_min_s=emitter.duration_min_s,
                duration_max_s=emitter.duration_max_s,
                mean_duration_s=emitter.mean_duration_s,
                bandwidth_min_hz=emitter.bandwidth_min_hz,
                bandwidth_max_hz=emitter.bandwidth_max_hz,
                mean_bandwidth_hz=emitter.mean_bandwidth_hz,
                mean_duty_cycle=emitter.mean_duty_cycle,
                mean_confidence=emitter.mean_confidence,
                repetition_interval_mean_s=emitter.repetition_interval_mean_s,
                repetition_interval_std_s=emitter.repetition_interval_std_s,
                source_paths=emitter.source_paths,
                notes=emitter.notes,
            )
        )

    return FingerprintSummary(
        kind="burstwatch.fingerprint_summary.v1",
        input_paths=scan_summary.input_paths,
        fingerprint_count=len(fingerprints),
        fingerprints=tuple(fingerprints),
    )


def build_baseline(
    scan_paths: list[str | Path],
    *,
    freq_bin_hz: float = 25_000.0,
) -> BaselineSummary:
    grouped: dict[tuple[str, int | None], list[dict[str, object]]] = defaultdict(list)
    ordered_paths = tuple(str(Path(path)) for path in scan_paths)
    for path in scan_paths:
        document = read_json_document(path)
        if document.get("kind") != "burstwatch.scan_summary.v1":
            raise ValueError(f"{path} is not a burstwatch scan summary")
        for emitter in document.get("emitters", []):
            freq = emitter.get("approx_freq_hz")
            bucket = None if freq is None else int(round(float(freq) / freq_bin_hz))
            key = (str(emitter.get("dominant_label")), bucket)
            grouped[key].append(emitter)

    records: list[BaselineRecord] = []
    for index, entries in enumerate(grouped.values(), start=1):
        frequencies = [float(entry["approx_freq_hz"]) for entry in entries if entry.get("approx_freq_hz") is not None]
        burst_counts = [int(entry["burst_count"]) for entry in entries]
        duration_means = [float(entry["mean_duration_s"]) for entry in entries]
        bandwidth_means = [float(entry["mean_bandwidth_hz"]) for entry in entries]
        duty_means = [float(entry["mean_duty_cycle"]) for entry in entries]
        confidence_means = [float(entry["mean_confidence"]) for entry in entries]
        dominant_label = str(entries[0]["dominant_label"])
        if frequencies:
            approx_freq_hz = fmean(frequencies)
            freq_std = pstdev(frequencies) if len(frequencies) > 1 else 0.0
            frequency_tolerance_hz = max(freq_bin_hz, freq_std * 3.0, 100.0)
        else:
            approx_freq_hz = None
            frequency_tolerance_hz = freq_bin_hz
        records.append(
            BaselineRecord(
                baseline_id=f"baseline-{index:03d}",
                approx_freq_hz=approx_freq_hz,
                dominant_label=dominant_label,
                scans_seen=len(entries),
                burst_count_mean=fmean(burst_counts),
                burst_count_max=max(burst_counts),
                duration_mean_s=fmean(duration_means),
                duration_std_s=pstdev(duration_means) if len(duration_means) > 1 else 0.0,
                bandwidth_mean_hz=fmean(bandwidth_means),
                bandwidth_std_hz=pstdev(bandwidth_means) if len(bandwidth_means) > 1 else 0.0,
                duty_cycle_mean=fmean(duty_means),
                confidence_mean=fmean(confidence_means),
                frequency_tolerance_hz=frequency_tolerance_hz,
            )
        )

    records.sort(
        key=lambda record: (
            record.approx_freq_hz if record.approx_freq_hz is not None else float("inf"),
            record.dominant_label,
        )
    )
    return BaselineSummary(
        kind="burstwatch.baseline_summary.v1",
        source_scan_paths=ordered_paths,
        record_count=len(records),
        records=tuple(records),
    )


def watch_against_baseline(
    baseline_path: str | Path,
    scan_summary: ScanSummary,
) -> WatchSummary:
    document = read_json_document(baseline_path)
    if document.get("kind") != "burstwatch.baseline_summary.v1":
        raise ValueError(f"{baseline_path} is not a burstwatch baseline summary")

    baseline_records = list(document.get("records", []))
    alerts: list[WatchAlert] = []
    new_count = 0
    changed_count = 0
    for emitter in scan_summary.emitters:
        match = _find_best_baseline_match(emitter, baseline_records)
        if match is None:
            alerts.append(
                WatchAlert(
                    candidate_id=emitter.candidate_id,
                    status="new",
                    message="no baseline match within tolerance",
                    dominant_label=emitter.dominant_label,
                    approx_freq_hz=emitter.approx_freq_hz,
                )
            )
            new_count += 1
            continue

        issues = _compare_emitter_to_baseline(emitter, match)
        if issues:
            alerts.append(
                WatchAlert(
                    candidate_id=emitter.candidate_id,
                    status="changed",
                    message="; ".join(issues),
                    dominant_label=emitter.dominant_label,
                    approx_freq_hz=emitter.approx_freq_hz,
                    baseline_id=str(match["baseline_id"]),
                )
            )
            changed_count += 1

    return WatchSummary(
        kind="burstwatch.watch_summary.v1",
        baseline_path=str(baseline_path),
        alert_count=len(alerts),
        new_count=new_count,
        changed_count=changed_count,
        alerts=tuple(alerts),
        scan=scan_summary,
    )


def _build_emitters(events: list[BurstEvent], *, freq_bin_hz: float) -> list[ScanEmitter]:
    grouped: dict[int | None, list[BurstEvent]] = defaultdict(list)
    for event in events:
        approx_freq_hz = _event_frequency_hz(event)
        bucket = None if approx_freq_hz is None else int(round(approx_freq_hz / freq_bin_hz))
        grouped[bucket].append(event)

    emitters: list[ScanEmitter] = []
    for index, cluster in enumerate(grouped.values(), start=1):
        label_counts = Counter(event.label for event in cluster)
        dominant_label = label_counts.most_common(1)[0][0]
        source_paths = tuple(sorted({event.capture_path for event in cluster}))
        durations = [event.duration_s for event in cluster]
        bandwidths = [event.features.bandwidth_hz for event in cluster]
        duties = [event.features.duty_cycle for event in cluster]
        confidences = [event.confidence for event in cluster]
        frequencies = [
            freq for freq in (_event_frequency_hz(event) for event in cluster) if freq is not None
        ]
        intervals = _repetition_intervals(cluster)
        notes = tuple(
            sorted(
                {
                    note
                    for event in cluster
                    for note in event.notes
                    if note
                }
            )
        )
        emitters.append(
            ScanEmitter(
                candidate_id=f"emitter-{index:03d}",
                approx_freq_hz=fmean(frequencies) if frequencies else None,
                dominant_label=dominant_label,
                label_counts=dict(sorted(label_counts.items())),
                burst_count=len(cluster),
                capture_count=len(source_paths),
                total_on_air_s=sum(durations),
                duration_min_s=min(durations),
                duration_max_s=max(durations),
                mean_duration_s=fmean(durations),
                bandwidth_min_hz=min(bandwidths),
                bandwidth_max_hz=max(bandwidths),
                mean_bandwidth_hz=fmean(bandwidths),
                mean_duty_cycle=fmean(duties),
                mean_confidence=fmean(confidences),
                repetition_interval_mean_s=fmean(intervals) if intervals else None,
                repetition_interval_std_s=pstdev(intervals) if len(intervals) > 1 else None,
                source_paths=source_paths,
                notes=notes,
            )
        )

    emitters.sort(
        key=lambda emitter: (
            emitter.approx_freq_hz if emitter.approx_freq_hz is not None else float("inf"),
            emitter.dominant_label,
        )
    )
    for index, emitter in enumerate(emitters, start=1):
        emitters[index - 1] = ScanEmitter(
            candidate_id=f"emitter-{index:03d}",
            approx_freq_hz=emitter.approx_freq_hz,
            dominant_label=emitter.dominant_label,
            label_counts=emitter.label_counts,
            burst_count=emitter.burst_count,
            capture_count=emitter.capture_count,
            total_on_air_s=emitter.total_on_air_s,
            duration_min_s=emitter.duration_min_s,
            duration_max_s=emitter.duration_max_s,
            mean_duration_s=emitter.mean_duration_s,
            bandwidth_min_hz=emitter.bandwidth_min_hz,
            bandwidth_max_hz=emitter.bandwidth_max_hz,
            mean_bandwidth_hz=emitter.mean_bandwidth_hz,
            mean_duty_cycle=emitter.mean_duty_cycle,
            mean_confidence=emitter.mean_confidence,
            repetition_interval_mean_s=emitter.repetition_interval_mean_s,
            repetition_interval_std_s=emitter.repetition_interval_std_s,
            source_paths=emitter.source_paths,
            notes=emitter.notes,
        )
    return emitters


def _event_frequency_hz(event: BurstEvent) -> float | None:
    offset = event.features.spectral_centroid_hz
    if event.center_freq_hz is None:
        return offset
    return event.center_freq_hz + offset


def _repetition_intervals(events: list[BurstEvent]) -> list[float]:
    grouped: dict[str, list[BurstEvent]] = defaultdict(list)
    for event in events:
        grouped[event.capture_path].append(event)

    intervals: list[float] = []
    for capture_events in grouped.values():
        ordered = sorted(capture_events, key=lambda event: event.start_time_s)
        for previous, current in zip(ordered, ordered[1:]):
            intervals.append(current.start_time_s - previous.start_time_s)
    return [interval for interval in intervals if interval > 0]


def _find_best_baseline_match(
    emitter: ScanEmitter,
    baseline_records: list[dict[str, object]],
) -> dict[str, object] | None:
    best_match: dict[str, object] | None = None
    best_score = float("inf")
    for record in baseline_records:
        record_freq = record.get("approx_freq_hz")
        tolerance = float(record.get("frequency_tolerance_hz", 0.0))
        if record_freq is None or emitter.approx_freq_hz is None:
            freq_delta = 0.0
        else:
            freq_delta = abs(emitter.approx_freq_hz - float(record_freq))
            if freq_delta > tolerance:
                continue

        label_penalty = 0.0 if emitter.dominant_label == record.get("dominant_label") else tolerance * 10.0 + 1.0
        score = freq_delta + label_penalty
        if score < best_score:
            best_score = score
            best_match = record
    return best_match


def _compare_emitter_to_baseline(
    emitter: ScanEmitter,
    record: dict[str, object],
) -> list[str]:
    issues: list[str] = []
    if emitter.dominant_label != record.get("dominant_label"):
        issues.append(
            f"label changed from {record.get('dominant_label')} to {emitter.dominant_label}"
        )

    if emitter.approx_freq_hz is not None and record.get("approx_freq_hz") is not None:
        tolerance = float(record.get("frequency_tolerance_hz", 0.0))
        freq_delta = abs(emitter.approx_freq_hz - float(record["approx_freq_hz"]))
        if freq_delta > tolerance * 0.75:
            issues.append(f"frequency drift {freq_delta:.1f}Hz")

    if _outside_tolerance(
        emitter.mean_bandwidth_hz,
        float(record["bandwidth_mean_hz"]),
        float(record["bandwidth_std_hz"]),
        relative_floor=0.35,
        absolute_floor=200.0,
    ):
        issues.append("bandwidth changed")

    if _outside_tolerance(
        emitter.mean_duration_s,
        float(record["duration_mean_s"]),
        float(record["duration_std_s"]),
        relative_floor=0.35,
        absolute_floor=0.01,
    ):
        issues.append("duration changed")

    if abs(emitter.mean_duty_cycle - float(record["duty_cycle_mean"])) > 0.20:
        issues.append("duty cycle changed")

    burst_count_threshold = max(
        int(record["burst_count_max"]) * 2,
        int(round(float(record["burst_count_mean"]) + 3.0)),
    )
    if emitter.burst_count > burst_count_threshold:
        issues.append("burst count increased")

    return issues


def _outside_tolerance(
    value: float,
    mean_value: float,
    std_value: float,
    *,
    relative_floor: float,
    absolute_floor: float,
) -> bool:
    tolerance = max(std_value * 3.0, abs(mean_value) * relative_floor, absolute_floor)
    return abs(value - mean_value) > tolerance
