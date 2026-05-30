from __future__ import annotations

from pathlib import Path

import numpy as np


def make_ook_capture(
    *,
    sample_rate_hz: float = 20_000.0,
    burst_duration_s: float = 0.12,
    carrier_hz: float = 1_250.0,
    symbol_duration_s: float = 0.004,
    noise_std: float = 0.02,
    seed: int = 1,
) -> np.ndarray:
    burst = _make_ook_burst(
        sample_rate_hz=sample_rate_hz,
        burst_duration_s=burst_duration_s,
        carrier_hz=carrier_hz,
        symbol_duration_s=symbol_duration_s,
        noise_std=noise_std,
        seed=seed,
    )
    return _pad_with_noise(burst, sample_rate_hz=sample_rate_hz, seed=seed)


def make_fsk_capture(
    *,
    sample_rate_hz: float = 20_000.0,
    burst_duration_s: float = 0.12,
    tone_a_hz: float = 900.0,
    tone_b_hz: float = 1_900.0,
    symbol_duration_s: float = 0.004,
    noise_std: float = 0.02,
    seed: int = 2,
) -> np.ndarray:
    burst = _make_fsk_burst(
        sample_rate_hz=sample_rate_hz,
        burst_duration_s=burst_duration_s,
        tone_a_hz=tone_a_hz,
        tone_b_hz=tone_b_hz,
        symbol_duration_s=symbol_duration_s,
        noise_std=noise_std,
        seed=seed,
    )
    return _pad_with_noise(burst, sample_rate_hz=sample_rate_hz, seed=seed)


def make_chirp_capture(
    *,
    sample_rate_hz: float = 20_000.0,
    burst_duration_s: float = 0.12,
    start_hz: float = 700.0,
    stop_hz: float = 3_500.0,
    noise_std: float = 0.02,
    seed: int = 3,
) -> np.ndarray:
    burst = _make_chirp_burst(
        sample_rate_hz=sample_rate_hz,
        burst_duration_s=burst_duration_s,
        start_hz=start_hz,
        stop_hz=stop_hz,
        noise_std=noise_std,
        seed=seed,
    )
    return _pad_with_noise(burst, sample_rate_hz=sample_rate_hz, seed=seed)


def make_fm_like_capture(
    *,
    sample_rate_hz: float = 20_000.0,
    burst_duration_s: float = 0.12,
    carrier_hz: float = 1_300.0,
    deviation_hz: float = 1_200.0,
    mod_hz: float = 38.0,
    noise_std: float = 0.02,
    seed: int = 4,
) -> np.ndarray:
    burst = _make_fm_like_burst(
        sample_rate_hz=sample_rate_hz,
        burst_duration_s=burst_duration_s,
        carrier_hz=carrier_hz,
        deviation_hz=deviation_hz,
        mod_hz=mod_hz,
        noise_std=noise_std,
        seed=seed,
    )
    return _pad_with_noise(burst, sample_rate_hz=sample_rate_hz, seed=seed)


def write_complex64(path: str | Path, samples: np.ndarray) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(samples, dtype=np.complex64).tofile(destination)


def _pad_with_noise(
    burst: np.ndarray,
    *,
    sample_rate_hz: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pad_samples = int(sample_rate_hz * 0.05)
    prefix = _complex_noise(pad_samples, std=0.02, rng=rng)
    suffix = _complex_noise(pad_samples, std=0.02, rng=rng)
    return np.concatenate([prefix, burst, suffix]).astype(np.complex64, copy=False)


def _make_ook_burst(
    *,
    sample_rate_hz: float,
    burst_duration_s: float,
    carrier_hz: float,
    symbol_duration_s: float,
    noise_std: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    count = int(sample_rate_hz * burst_duration_s)
    t = np.arange(count, dtype=np.float64) / sample_rate_hz
    envelope = np.zeros(count, dtype=np.float64)
    symbol_samples = max(1, int(sample_rate_hz * symbol_duration_s))
    gate = True
    for start in range(0, count, symbol_samples):
        if gate:
            envelope[start : start + symbol_samples] = 1.0
        gate = not gate
    carrier = np.exp(1j * 2.0 * np.pi * carrier_hz * t)
    return (envelope * carrier + _complex_noise(count, std=noise_std, rng=rng)).astype(np.complex64)


def _make_fsk_burst(
    *,
    sample_rate_hz: float,
    burst_duration_s: float,
    tone_a_hz: float,
    tone_b_hz: float,
    symbol_duration_s: float,
    noise_std: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    count = int(sample_rate_hz * burst_duration_s)
    t = np.arange(count, dtype=np.float64) / sample_rate_hz
    symbol_samples = max(1, int(sample_rate_hz * symbol_duration_s))
    phase = np.zeros(count, dtype=np.float64)
    current = tone_a_hz
    phase_index = 0
    for start in range(0, count, symbol_samples):
        stop = min(count, start + symbol_samples)
        segment_t = t[start:stop]
        phase[start:stop] = 2.0 * np.pi * current * segment_t
        current = tone_b_hz if current == tone_a_hz else tone_a_hz
        phase_index = stop
    return np.exp(1j * phase).astype(np.complex64) + _complex_noise(count, std=noise_std, rng=rng)


def _make_chirp_burst(
    *,
    sample_rate_hz: float,
    burst_duration_s: float,
    start_hz: float,
    stop_hz: float,
    noise_std: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    count = int(sample_rate_hz * burst_duration_s)
    t = np.arange(count, dtype=np.float64) / sample_rate_hz
    slope = (stop_hz - start_hz) / max(burst_duration_s, 1e-9)
    phase = 2.0 * np.pi * (start_hz * t + 0.5 * slope * t**2)
    return np.exp(1j * phase).astype(np.complex64) + _complex_noise(count, std=noise_std, rng=rng)


def _make_fm_like_burst(
    *,
    sample_rate_hz: float,
    burst_duration_s: float,
    carrier_hz: float,
    deviation_hz: float,
    mod_hz: float,
    noise_std: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    count = int(sample_rate_hz * burst_duration_s)
    t = np.arange(count, dtype=np.float64) / sample_rate_hz
    modulation = np.sin(2.0 * np.pi * mod_hz * t)
    frequency = carrier_hz + deviation_hz * modulation
    phase = 2.0 * np.pi * np.cumsum(frequency) / sample_rate_hz
    return np.exp(1j * phase).astype(np.complex64) + _complex_noise(count, std=noise_std, rng=rng)


def _complex_noise(count: int, *, std: float, rng: np.random.Generator) -> np.ndarray:
    real = rng.normal(0.0, std, count)
    imag = rng.normal(0.0, std, count)
    return (real + 1j * imag).astype(np.complex64)

