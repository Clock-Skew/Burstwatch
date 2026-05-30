from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Sequence

from .capture import load_capture
from .models import AnalysisConfig
from .pipeline import analyze_capture, summarize_events
from .store import write_jsonl, write_sqlite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="burstwatch",
        description="Passive RF burst detector and shape classifier.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a capture file and classify bursts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    analyze.add_argument("input", type=Path, help="Capture file to analyze")
    analyze.add_argument(
        "--sample-rate",
        type=float,
        default=None,
        help="Sample rate in Hz for complex64 captures",
    )
    analyze.add_argument(
        "--center-freq",
        type=float,
        default=None,
        help="Optional tuned center frequency in Hz",
    )
    analyze.add_argument(
        "--format",
        choices=("auto", "complex64", "wav"),
        default="auto",
        help="Input sample format",
    )
    analyze.add_argument(
        "--smoothing-samples",
        type=int,
        default=256,
        help="Moving-average window for burst detection",
    )
    analyze.add_argument(
        "--threshold-sigma",
        type=float,
        default=6.0,
        help="Envelope threshold in scaled MAD units",
    )
    analyze.add_argument(
        "--min-burst-ms",
        type=float,
        default=1.0,
        help="Minimum burst length in milliseconds",
    )
    analyze.add_argument(
        "--merge-gap-ms",
        type=float,
        default=0.5,
        help="Merge gaps shorter than this many milliseconds",
    )
    analyze.add_argument(
        "--feature-window-count",
        type=int,
        default=8,
        help="Number of windows used for chirp tracking",
    )
    analyze.add_argument(
        "--jsonl",
        type=Path,
        default=None,
        help="Write burst events as JSON Lines",
    )
    analyze.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="Write burst events to SQLite",
    )
    analyze.add_argument(
        "--json",
        action="store_true",
        help="Print the full event summary as JSON",
    )
    analyze.set_defaults(func=_analyze_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def _analyze_command(args: argparse.Namespace) -> int:
    capture = load_capture(
        args.input,
        sample_rate_hz=args.sample_rate,
        center_freq_hz=args.center_freq,
        sample_format=args.format,
    )

    min_burst_samples = max(1, int(round(capture.sample_rate_hz * args.min_burst_ms / 1000.0)))
    merge_gap_samples = max(0, int(round(capture.sample_rate_hz * args.merge_gap_ms / 1000.0)))
    config = AnalysisConfig(
        smoothing_samples=max(1, int(args.smoothing_samples)),
        threshold_sigma=float(args.threshold_sigma),
        min_burst_samples=min_burst_samples,
        merge_gap_samples=merge_gap_samples,
        feature_window_count=max(2, int(args.feature_window_count)),
    )

    events = analyze_capture(capture, config)
    if args.jsonl is not None:
        write_jsonl(events, args.jsonl)
    if args.sqlite is not None:
        write_sqlite(events, args.sqlite)

    summary = summarize_events(capture, events)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    _print_summary(summary)
    return 0


def _print_summary(summary: dict[str, object]) -> None:
    print(
        f"capture={summary['source_path']} sample_rate_hz={summary['sample_rate_hz']} "
        f"center_freq_hz={summary['center_freq_hz']}"
    )
    print(f"bursts={summary['burst_count']} labels={summary['label_counts']}")
    for index, event in enumerate(summary["events"], start=1):
        features = event["features"]
        print(
            f"{index:02d} start={event['start_time_s']:.6f}s "
            f"duration={event['duration_s']:.6f}s label={event['label']} "
            f"confidence={event['confidence']:.2f} "
            f"bw={features['bandwidth_hz']:.1f}Hz tones={features['tone_count']} "
            f"slope={features['chirp_slope_hz_per_s']:.1f}"
        )

