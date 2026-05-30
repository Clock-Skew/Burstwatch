from __future__ import annotations

from pathlib import Path
import wave

import numpy as np

from .models import Capture


def load_capture(
    path: str | Path,
    *,
    sample_rate_hz: float | None = None,
    center_freq_hz: float | None = None,
    sample_format: str = "auto",
) -> Capture:
    path = Path(path)
    fmt = sample_format.lower().strip()
    if fmt == "auto":
        fmt = "wav" if path.suffix.lower() == ".wav" else "complex64"

    if fmt == "wav":
        samples, wav_rate = _load_wav(path)
        return Capture(
            path=path,
            samples=samples,
            sample_rate_hz=float(wav_rate),
            center_freq_hz=center_freq_hz,
            sample_kind="wav",
        )

    if fmt == "complex64":
        if sample_rate_hz is None:
            raise ValueError("sample_rate_hz is required for complex64 captures")
        samples = np.fromfile(path, dtype=np.complex64)
        return Capture(
            path=path,
            samples=samples,
            sample_rate_hz=float(sample_rate_hz),
            center_freq_hz=center_freq_hz,
            sample_kind="complex64",
        )

    raise ValueError(f"unsupported sample_format: {sample_format}")


def _load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width == 1:
        data = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        data = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV sample width: {sample_width} bytes")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    return data.astype(np.float32, copy=False), sample_rate

