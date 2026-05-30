from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class RtlSdrCaptureRequest:
    output_path: Path
    center_freq_hz: float
    sample_rate_hz: float = 2_400_000.0
    duration_s: float = 5.0
    gain: str = "auto"
    device_index: int = 0
    ppm: int | None = None
    rtl_sdr_path: str = "rtl_sdr"
    keep_raw_path: Path | None = None


@dataclass(frozen=True)
class RtlSdrCaptureResult:
    output_path: Path
    raw_path: Path | None
    center_freq_hz: float
    sample_rate_hz: float
    duration_s: float
    sample_count: int
    command: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "burstwatch.rtl_sdr_capture.v1",
            "output_path": str(self.output_path),
            "raw_path": None if self.raw_path is None else str(self.raw_path),
            "center_freq_hz": self.center_freq_hz,
            "sample_rate_hz": self.sample_rate_hz,
            "duration_s": self.duration_s,
            "sample_count": self.sample_count,
            "command": list(self.command),
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]


def build_rtl_sdr_command(request: RtlSdrCaptureRequest, raw_path: Path) -> list[str]:
    sample_count = _sample_count(request.sample_rate_hz, request.duration_s)
    command = [
        request.rtl_sdr_path,
        "-d",
        str(request.device_index),
        "-f",
        str(int(round(request.center_freq_hz))),
        "-s",
        str(int(round(request.sample_rate_hz))),
        "-n",
        str(sample_count),
    ]
    gain = request.gain.strip()
    if gain and gain.lower() != "auto":
        command.extend(["-g", gain])
    if request.ppm is not None:
        command.extend(["-p", str(request.ppm)])
    command.append(str(raw_path))
    return command


def record_rtl_sdr_capture(
    request: RtlSdrCaptureRequest,
    *,
    runner: Runner = subprocess.run,
) -> RtlSdrCaptureResult:
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path, should_delete_raw = _raw_capture_path(request)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_rtl_sdr_command(request, raw_path)
    timeout_s = max(float(request.duration_s) + 10.0, float(request.duration_s) * 2.0)

    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(f"rtl_sdr exited with status {completed.returncode}{detail}")
        sample_count = convert_rtl_u8_to_complex64(raw_path, request.output_path)
    finally:
        if should_delete_raw and raw_path.exists():
            raw_path.unlink()

    return RtlSdrCaptureResult(
        output_path=request.output_path,
        raw_path=None if should_delete_raw else raw_path,
        center_freq_hz=float(request.center_freq_hz),
        sample_rate_hz=float(request.sample_rate_hz),
        duration_s=float(request.duration_s),
        sample_count=sample_count,
        command=tuple(command),
    )


def convert_rtl_u8_to_complex64(
    raw_path: str | Path,
    output_path: str | Path,
    *,
    chunk_bytes: int = 4 * 1024 * 1024,
) -> int:
    source = Path(raw_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sample_count = 0
    leftover = b""
    with source.open("rb") as raw_file, destination.open("wb") as output_file:
        while True:
            chunk = raw_file.read(chunk_bytes)
            if not chunk:
                break
            block = leftover + chunk
            if len(block) % 2:
                leftover = block[-1:]
                block = block[:-1]
            else:
                leftover = b""
            if not block:
                continue
            u8 = np.frombuffer(block, dtype=np.uint8).reshape(-1, 2).astype(np.float32)
            samples = ((u8[:, 0] - 127.5) / 127.5) + 1j * ((u8[:, 1] - 127.5) / 127.5)
            np.asarray(samples, dtype=np.complex64).tofile(output_file)
            sample_count += int(samples.size)
    return sample_count


def _raw_capture_path(request: RtlSdrCaptureRequest) -> tuple[Path, bool]:
    if request.keep_raw_path is not None:
        return request.keep_raw_path, False
    raw_file = tempfile.NamedTemporaryFile(prefix="burstwatch-", suffix=".u8", delete=False)
    try:
        return Path(raw_file.name), True
    finally:
        raw_file.close()


def _sample_count(sample_rate_hz: float, duration_s: float) -> int:
    return max(1, int(round(float(sample_rate_hz) * float(duration_s))))
