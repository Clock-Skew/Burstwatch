from __future__ import annotations

import numpy as np

from .models import AnalysisConfig, BurstSpan


def detect_bursts(samples: np.ndarray, config: AnalysisConfig) -> list[BurstSpan]:
    envelope = np.abs(np.asarray(samples))
    if envelope.size == 0:
        return []

    smoothed = _moving_average(envelope.astype(np.float64, copy=False), config.smoothing_samples)
    baseline = float(np.quantile(smoothed, 0.25))
    background = smoothed[smoothed <= baseline]
    if background.size < 8:
        background = smoothed

    median = float(np.median(background))
    mad = float(np.median(np.abs(background - median)))
    scale = max(1.4826 * mad, median * 0.05, 1e-9)
    threshold = median + config.threshold_sigma * scale
    mask = smoothed > threshold

    runs = _merge_runs(_mask_runs(mask), config.merge_gap_samples)
    spans: list[BurstSpan] = []
    for index, (start, end) in enumerate(runs):
        if end - start < config.min_burst_samples:
            continue
        window = envelope[start:end]
        spans.append(
            BurstSpan(
                index=index,
                start_sample=int(start),
                end_sample=int(end),
                threshold=float(threshold),
                peak=float(np.max(window)),
                mean_envelope=float(np.mean(window)),
            )
        )

    return spans


def _moving_average(values: np.ndarray, window_samples: int) -> np.ndarray:
    window = max(1, min(int(window_samples), int(values.size)))
    kernel = np.ones(window, dtype=np.float64) / float(window)
    return np.convolve(values, kernel, mode="same")


def _mask_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return []

    runs: list[tuple[int, int]] = []
    start = int(indices[0])
    previous = int(indices[0])
    for value in indices[1:]:
        current = int(value)
        if current != previous + 1:
            runs.append((start, previous + 1))
            start = current
        previous = current
    runs.append((start, previous + 1))
    return runs


def _merge_runs(runs: list[tuple[int, int]], gap_samples: int) -> list[tuple[int, int]]:
    if not runs:
        return []

    merged: list[list[int]] = [[runs[0][0], runs[0][1]]]
    for start, end in runs[1:]:
        previous_start, previous_end = merged[-1]
        if start - previous_end <= gap_samples:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]
