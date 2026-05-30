from __future__ import annotations

import numpy as np

from .models import BurstClassification, BurstFeatures


def extract_burst_features(
    samples: np.ndarray,
    *,
    sample_rate_hz: float,
    window_count: int = 8,
) -> BurstFeatures:
    signal = np.asarray(samples)
    if signal.size == 0:
        raise ValueError("cannot extract features from empty samples")

    envelope = np.abs(signal)
    peak_amplitude = float(np.max(envelope))
    rms_amplitude = float(np.sqrt(np.mean(np.square(envelope))))
    crest_factor = peak_amplitude / max(rms_amplitude, 1e-12)
    envelope_mean = float(np.mean(envelope))
    envelope_variation = float(np.std(envelope) / max(envelope_mean, 1e-12))
    duty_cycle = float(np.mean(envelope >= peak_amplitude * 0.5)) if peak_amplitude > 0 else 0.0

    freqs, power = _spectrum(signal, sample_rate_hz)
    total_power = float(np.sum(power))
    if total_power <= 0:
        spectral_centroid_hz = 0.0
        bandwidth_hz = 0.0
        spectral_flatness = 0.0
        dominant_tones_hz: tuple[float, ...] = ()
        tone_separation_hz = None
    else:
        spectral_centroid_hz = float(np.sum(freqs * power) / total_power)
        bandwidth_hz = _power_bandwidth(freqs, power, fraction=0.90)
        spectral_flatness = _spectral_flatness(power)
        dominant_tones_hz = _dominant_tones(freqs, power, limit=4)
        tone_separation_hz = None
        if len(dominant_tones_hz) >= 2:
            tone_separation_hz = float(abs(dominant_tones_hz[1] - dominant_tones_hz[0]))

    track = _frequency_track(signal, sample_rate_hz, window_count=window_count)
    chirp_slope_hz_per_s, trend_consistency, track_error_ratio = _trend_metrics(track)

    return BurstFeatures(
        peak_amplitude=peak_amplitude,
        rms_amplitude=rms_amplitude,
        crest_factor=crest_factor,
        envelope_variation=envelope_variation,
        duty_cycle=duty_cycle,
        bandwidth_hz=float(bandwidth_hz),
        spectral_flatness=float(spectral_flatness),
        spectral_centroid_hz=float(spectral_centroid_hz),
        chirp_slope_hz_per_s=float(chirp_slope_hz_per_s),
        frequency_trend_consistency=float(trend_consistency),
        frequency_track_error_ratio=float(track_error_ratio),
        tone_count=len(dominant_tones_hz),
        tone_separation_hz=tone_separation_hz,
        dominant_tones_hz=dominant_tones_hz,
    )


def classify_burst(features: BurstFeatures, *, sample_rate_hz: float) -> BurstClassification:
    slope = abs(features.chirp_slope_hz_per_s)

    if (
        features.crest_factor >= 1.30
        and features.envelope_variation >= 0.70
        and features.duty_cycle <= 0.70
    ):
        return BurstClassification(
            label="ook_ask",
            confidence=0.88,
            notes=("bursty amplitude gating",),
        )

    if (
        slope >= sample_rate_hz * 0.05
        and features.frequency_trend_consistency >= 0.80
        and features.frequency_track_error_ratio <= 0.05
    ):
        return BurstClassification(
            label="chirp",
            confidence=0.96,
            notes=("strong monotonic frequency sweep",),
        )

    if (
        features.tone_count >= 2
        and features.tone_separation_hz is not None
        and features.tone_separation_hz >= sample_rate_hz * 0.006
        and features.bandwidth_hz >= sample_rate_hz * 0.04
        and features.bandwidth_hz <= sample_rate_hz * 0.25
        and features.envelope_variation < 0.60
        and features.frequency_track_error_ratio > 0.05
    ):
        return BurstClassification(
            label="fsk",
            confidence=0.88,
            notes=("multiple stable tones",),
        )

    if (
        features.bandwidth_hz >= sample_rate_hz * 0.08
        and features.crest_factor < 1.5
        and features.envelope_variation < 0.70
        and features.frequency_track_error_ratio >= 0.20
    ):
        return BurstClassification(
            label="fm_like",
            confidence=0.80,
            notes=("wide continuous occupied band",),
        )

    if features.bandwidth_hz <= sample_rate_hz * 0.03 and features.crest_factor < 1.8:
        return BurstClassification(
            label="narrowband_digital",
            confidence=0.72,
            notes=("single narrow carrier",),
        )

    return BurstClassification(
        label="unknown",
        confidence=0.50,
        notes=("no shape rule matched strongly",),
    )


def _spectrum(samples: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    signal = np.asarray(samples)
    n = int(signal.size)
    if n == 0:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    window = np.hanning(n) if n > 1 else np.ones(1, dtype=np.float64)
    spectrum = np.fft.fft(signal * window)
    power = np.abs(spectrum) ** 2
    freqs = np.fft.fftfreq(n, d=1.0 / sample_rate_hz)
    order = np.argsort(freqs)
    return freqs[order].astype(np.float64, copy=False), power[order].astype(np.float64, copy=False)


def _power_bandwidth(freqs: np.ndarray, power: np.ndarray, *, fraction: float) -> float:
    total = float(np.sum(power))
    if total <= 0 or freqs.size == 0:
        return 0.0

    cumulative = np.cumsum(power)
    lower_target = total * (1.0 - fraction) / 2.0
    upper_target = total * (1.0 + fraction) / 2.0
    lower_index = int(np.searchsorted(cumulative, lower_target, side="left"))
    upper_index = int(np.searchsorted(cumulative, upper_target, side="left"))
    lower_index = min(max(lower_index, 0), freqs.size - 1)
    upper_index = min(max(upper_index, 0), freqs.size - 1)
    return float(max(0.0, freqs[upper_index] - freqs[lower_index]))


def _spectral_flatness(power: np.ndarray) -> float:
    if power.size == 0:
        return 0.0
    eps = 1e-12
    return float(np.exp(np.mean(np.log(power + eps))) / np.mean(power + eps))


def _dominant_tones(freqs: np.ndarray, power: np.ndarray, *, limit: int) -> tuple[float, ...]:
    if freqs.size == 0 or power.size == 0:
        return ()

    order = np.argsort(power)[::-1]
    span = float(freqs[-1] - freqs[0]) if freqs.size > 1 else 0.0
    min_gap = max(span / 2000.0, 1.0)
    tones: list[float] = []
    for index in order:
        candidate = float(freqs[int(index)])
        if all(abs(candidate - tone) >= min_gap for tone in tones):
            tones.append(candidate)
        if len(tones) >= limit:
            break
    tones.sort()
    return tuple(tones)


def _frequency_track(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    window_count: int,
) -> list[tuple[float, float]]:
    signal = np.asarray(samples)
    n = int(signal.size)
    if n < 2:
        return []

    windows = max(4, min(int(window_count), max(4, n // 16)))
    window_size = max(16, n // windows)
    if window_size > n:
        window_size = n

    track: list[tuple[float, float]] = []
    for start in range(0, n - window_size + 1, window_size):
        segment = signal[start : start + window_size]
        freqs, power = _spectrum(segment, sample_rate_hz)
        if power.size == 0 or float(np.sum(power)) <= 0:
            continue
        dominant_index = int(np.argmax(power))
        dominant_freq = float(freqs[dominant_index])
        mid_point_s = (start + window_size / 2.0) / sample_rate_hz
        track.append((mid_point_s, dominant_freq))
    return track


def _trend_metrics(track: list[tuple[float, float]]) -> tuple[float, float, float]:
    if len(track) < 2:
        return 0.0, 0.0, 0.0

    times = np.array([item[0] for item in track], dtype=np.float64)
    freqs = np.array([item[1] for item in track], dtype=np.float64)
    slope, intercept = np.polyfit(times, freqs, 1)
    slope = float(slope)
    intercept = float(intercept)
    predicted = slope * times + intercept
    rmse = float(np.sqrt(np.mean(np.square(freqs - predicted))))
    span = float(max(np.max(freqs) - np.min(freqs), 1.0))
    error_ratio = rmse / span

    diffs = np.diff(freqs)
    if diffs.size == 0:
        consistency = 0.0
    else:
        increasing = float(np.mean(diffs >= 0))
        decreasing = float(np.mean(diffs <= 0))
        consistency = max(increasing, decreasing)
    return slope, consistency, error_ratio
