from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np

from burstwatch.recording import (
    RtlSdrCaptureRequest,
    build_rtl_sdr_command,
    convert_rtl_u8_to_complex64,
    record_rtl_sdr_capture,
)


class RecordingTests(unittest.TestCase):
    def test_build_rtl_sdr_command(self) -> None:
        request = RtlSdrCaptureRequest(
            output_path=Path("out.c64"),
            center_freq_hz=433_920_000,
            sample_rate_hz=2_400_000,
            duration_s=2.5,
            gain="28.0",
            ppm=1,
            rtl_sdr_path="/usr/bin/rtl_sdr",
        )
        command = build_rtl_sdr_command(request, Path("raw.u8"))
        self.assertEqual(command[0], "/usr/bin/rtl_sdr")
        self.assertIn("433920000", command)
        self.assertIn("6000000", command)
        self.assertIn("28.0", command)
        self.assertEqual(command[-1], "raw.u8")

    def test_convert_rtl_u8_to_complex64(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            raw_path = tmp_path / "raw.u8"
            output_path = tmp_path / "capture.c64"
            raw_path.write_bytes(bytes([255, 127, 0, 128]))

            sample_count = convert_rtl_u8_to_complex64(raw_path, output_path, chunk_bytes=3)
            samples = np.fromfile(output_path, dtype=np.complex64)

            self.assertEqual(sample_count, 2)
            self.assertEqual(samples.shape, (2,))
            self.assertGreater(samples[0].real, 0.99)
            self.assertLess(samples[1].real, -0.99)

    def test_record_rtl_sdr_capture_uses_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_path = tmp_path / "capture.c64"

            def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                Path(command[-1]).write_bytes(bytes([255, 127, 0, 128]))
                return subprocess.CompletedProcess(command, 0, "", "")

            result = record_rtl_sdr_capture(
                RtlSdrCaptureRequest(
                    output_path=output_path,
                    center_freq_hz=433_920_000,
                    sample_rate_hz=2,
                    duration_s=1,
                ),
                runner=fake_runner,
            )

            self.assertEqual(result.sample_count, 2)
            self.assertTrue(output_path.exists())
            self.assertIsNone(result.raw_path)

