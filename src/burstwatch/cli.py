from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifacts import write_json_document
from .capture import load_capture
from .dashboard import ArtifactSummary, summarize_artifacts
from .models import AnalysisConfig
from .pipeline import analyze_capture, summarize_events
from .recording import RtlSdrCaptureRequest, record_rtl_sdr_capture
from .store import write_jsonl, write_sqlite
from .workflows import build_baseline, build_fingerprints, scan_inputs, watch_against_baseline


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

    capture = subparsers.add_parser(
        "capture",
        help="Record passive RTL-SDR IQ to complex64 before analysis.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    capture.add_argument("output", type=Path, help="Output complex64 capture path")
    capture.add_argument("--center-freq", type=float, required=True, help="Tuned center frequency in Hz")
    capture.add_argument("--sample-rate", type=float, default=2_400_000.0, help="Sample rate in Hz")
    capture.add_argument("--duration", type=float, default=5.0, help="Capture duration in seconds")
    capture.add_argument("--gain", default="auto", help="RTL-SDR gain value, or auto")
    capture.add_argument("--device", type=int, default=0, help="RTL-SDR device index")
    capture.add_argument("--ppm", type=int, default=None, help="Optional oscillator correction in PPM")
    capture.add_argument("--rtl-sdr", default="rtl_sdr", help="rtl_sdr executable path")
    capture.add_argument("--keep-raw", type=Path, default=None, help="Optional path for raw unsigned 8-bit IQ")
    capture.add_argument(
        "--metadata-json",
        type=Path,
        default=None,
        help="Write capture metadata JSON",
    )
    capture.add_argument(
        "--then",
        choices=("none", "analyze", "scan"),
        default="none",
        help="Run a passive analysis step after recording",
    )
    capture.add_argument("--json", action="store_true", help="Print capture metadata as JSON")
    _add_detection_options(capture)
    capture.set_defaults(func=_capture_command)

    scan = subparsers.add_parser(
        "scan",
        help="Analyze one or more captures and cluster passive emitter candidates.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_capture_inputs(scan, allow_multiple=True)
    _add_analysis_options(scan)
    scan.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search directories for capture files",
    )
    scan.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="Directory glob pattern. Repeatable",
    )
    scan.add_argument(
        "--freq-bin-hz",
        type=float,
        default=25_000.0,
        help="Emitter grouping width in Hz",
    )
    scan.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write a scan summary JSON document",
    )
    scan.add_argument(
        "--event-jsonl",
        type=Path,
        default=None,
        help="Write raw burst events as JSON Lines",
    )
    scan.add_argument(
        "--event-sqlite",
        type=Path,
        default=None,
        help="Write raw burst events to SQLite",
    )
    scan.add_argument(
        "--json",
        action="store_true",
        help="Print the full scan summary as JSON",
    )
    scan.set_defaults(func=_scan_command)

    fingerprint = subparsers.add_parser(
        "fingerprint",
        help="Build passive RF fingerprints from one or more captures.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_capture_inputs(fingerprint, allow_multiple=True)
    _add_analysis_options(fingerprint)
    fingerprint.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search directories for capture files",
    )
    fingerprint.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="Directory glob pattern. Repeatable",
    )
    fingerprint.add_argument(
        "--freq-bin-hz",
        type=float,
        default=25_000.0,
        help="Emitter grouping width in Hz",
    )
    fingerprint.add_argument(
        "--name-prefix",
        default="fp",
        help="Prefix used for generated fingerprint IDs",
    )
    fingerprint.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write fingerprint JSON output",
    )
    fingerprint.add_argument(
        "--json",
        action="store_true",
        help="Print the full fingerprint summary as JSON",
    )
    fingerprint.set_defaults(func=_fingerprint_command)

    baseline = subparsers.add_parser(
        "baseline",
        help="Build a baseline from one or more scan summary JSON files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    baseline.add_argument("scan_json", nargs="+", type=Path, help="Scan summary JSON files")
    baseline.add_argument(
        "--freq-bin-hz",
        type=float,
        default=25_000.0,
        help="Grouping width used when building baseline records",
    )
    baseline.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write baseline JSON output",
    )
    baseline.add_argument(
        "--json",
        action="store_true",
        help="Print the full baseline summary as JSON",
    )
    baseline.set_defaults(func=_baseline_command)

    watch = subparsers.add_parser(
        "watch",
        help="Compare fresh passive scan results against a saved baseline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    watch.add_argument("baseline_json", type=Path, help="Baseline JSON file")
    _add_capture_inputs(watch, allow_multiple=True)
    _add_analysis_options(watch)
    watch.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search directories for capture files",
    )
    watch.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="Directory glob pattern. Repeatable",
    )
    watch.add_argument(
        "--freq-bin-hz",
        type=float,
        default=25_000.0,
        help="Emitter grouping width in Hz",
    )
    watch.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write watch JSON output",
    )
    watch.add_argument(
        "--json",
        action="store_true",
        help="Print the full watch report as JSON",
    )
    watch.set_defaults(func=_watch_command)

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Show saved burstwatch JSON outputs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    dashboard.add_argument("root", nargs="?", type=Path, default=Path("runs"), help="Directory containing saved JSON outputs")
    dashboard.add_argument("--no-recursive", action="store_true", help="Only inspect the top-level directory")
    dashboard.add_argument("--limit", type=int, default=12, help="Maximum artifacts to show")
    dashboard.add_argument("--json", action="store_true", help="Print artifact dashboard as JSON")
    dashboard.set_defaults(func=_dashboard_command)

    menu = subparsers.add_parser(
        "menu",
        help="Launch the guided Rich menu interface.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    menu.set_defaults(func=_menu_command)

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

    config = _config_from_args(args, capture.sample_rate_hz)

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


def _scan_command(args: argparse.Namespace) -> int:
    summary, events = scan_inputs(
        [str(path) for path in args.inputs],
        sample_rate_hz=args.sample_rate,
        center_freq_hz=args.center_freq,
        sample_format=args.format,
        config_factory=lambda sample_rate_hz: _config_from_args(args, sample_rate_hz),
        recursive=args.recursive,
        patterns=_patterns_from_args(args),
        freq_bin_hz=args.freq_bin_hz,
    )
    if args.event_jsonl is not None:
        write_jsonl(events, args.event_jsonl)
    if args.event_sqlite is not None:
        write_sqlite(events, args.event_sqlite)
    if args.json_out is not None:
        write_json_document(summary.to_dict(), args.json_out)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return 0
    _print_scan_summary(summary.to_dict())
    return 0


def _capture_command(args: argparse.Namespace) -> int:
    request = RtlSdrCaptureRequest(
        output_path=args.output,
        center_freq_hz=args.center_freq,
        sample_rate_hz=args.sample_rate,
        duration_s=args.duration,
        gain=args.gain,
        device_index=args.device,
        ppm=args.ppm,
        rtl_sdr_path=args.rtl_sdr,
        keep_raw_path=args.keep_raw,
    )
    result = record_rtl_sdr_capture(request)
    metadata = result.to_dict()
    if args.metadata_json is not None:
        write_json_document(metadata, args.metadata_json)

    if args.then == "analyze":
        capture = load_capture(
            result.output_path,
            sample_rate_hz=result.sample_rate_hz,
            center_freq_hz=result.center_freq_hz,
            sample_format="complex64",
        )
        events = analyze_capture(capture, _config_from_args(args, capture.sample_rate_hz))
        _print_summary(summarize_events(capture, events))
    elif args.then == "scan":
        summary, _events = scan_inputs(
            [result.output_path],
            sample_rate_hz=result.sample_rate_hz,
            center_freq_hz=result.center_freq_hz,
            sample_format="complex64",
            config_factory=lambda sample_rate_hz: _config_from_args(args, sample_rate_hz),
        )
        _print_scan_summary(summary.to_dict())
    elif args.json:
        print(json.dumps(metadata, indent=2, sort_keys=True))
    else:
        print(
            f"capture={result.output_path} samples={result.sample_count} "
            f"sample_rate_hz={result.sample_rate_hz} center_freq_hz={result.center_freq_hz}"
        )
    return 0


def _fingerprint_command(args: argparse.Namespace) -> int:
    scan_summary, _events = scan_inputs(
        [str(path) for path in args.inputs],
        sample_rate_hz=args.sample_rate,
        center_freq_hz=args.center_freq,
        sample_format=args.format,
        config_factory=lambda sample_rate_hz: _config_from_args(args, sample_rate_hz),
        recursive=args.recursive,
        patterns=_patterns_from_args(args),
        freq_bin_hz=args.freq_bin_hz,
    )
    summary = build_fingerprints(scan_summary, name_prefix=args.name_prefix)
    if args.json_out is not None:
        write_json_document(summary.to_dict(), args.json_out)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return 0
    _print_fingerprint_summary(summary.to_dict())
    return 0


def _baseline_command(args: argparse.Namespace) -> int:
    summary = build_baseline([str(path) for path in args.scan_json], freq_bin_hz=args.freq_bin_hz)
    if args.json_out is not None:
        write_json_document(summary.to_dict(), args.json_out)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return 0
    _print_baseline_summary(summary.to_dict())
    return 0


def _watch_command(args: argparse.Namespace) -> int:
    scan_summary, _events = scan_inputs(
        [str(path) for path in args.inputs],
        sample_rate_hz=args.sample_rate,
        center_freq_hz=args.center_freq,
        sample_format=args.format,
        config_factory=lambda sample_rate_hz: _config_from_args(args, sample_rate_hz),
        recursive=args.recursive,
        patterns=_patterns_from_args(args),
        freq_bin_hz=args.freq_bin_hz,
    )
    summary = watch_against_baseline(args.baseline_json, scan_summary)
    if args.json_out is not None:
        write_json_document(summary.to_dict(), args.json_out)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        return 0
    _print_watch_summary(summary.to_dict())
    return 0


def _dashboard_command(args: argparse.Namespace) -> int:
    artifacts = summarize_artifacts(args.root, recursive=not args.no_recursive, limit=args.limit)
    if args.json:
        print(json.dumps([artifact.to_dict() for artifact in artifacts], indent=2, sort_keys=True))
        return 0
    _print_dashboard_summary(artifacts)
    return 0


def _menu_command(args: argparse.Namespace) -> int:
    from .ui import run_menu

    return int(run_menu())


def _add_capture_inputs(parser: argparse.ArgumentParser, *, allow_multiple: bool) -> None:
    parser.add_argument(
        "inputs",
        nargs="+" if allow_multiple else None,
        type=Path,
        help="Capture files or directories to analyze",
    )


def _add_analysis_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=None,
        help="Sample rate in Hz for complex64 captures",
    )
    parser.add_argument(
        "--center-freq",
        type=float,
        default=None,
        help="Optional tuned center frequency in Hz",
    )
    parser.add_argument(
        "--format",
        choices=("auto", "complex64", "wav"),
        default="auto",
        help="Input sample format",
    )
    parser.add_argument(
        "--smoothing-samples",
        type=int,
        default=256,
        help="Moving-average window for burst detection",
    )
    parser.add_argument(
        "--threshold-sigma",
        type=float,
        default=6.0,
        help="Envelope threshold in scaled MAD units",
    )
    parser.add_argument(
        "--min-burst-ms",
        type=float,
        default=1.0,
        help="Minimum burst length in milliseconds",
    )
    parser.add_argument(
        "--merge-gap-ms",
        type=float,
        default=0.5,
        help="Merge gaps shorter than this many milliseconds",
    )
    parser.add_argument(
        "--feature-window-count",
        type=int,
        default=8,
        help="Number of windows used for chirp tracking",
    )


def _add_detection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--smoothing-samples",
        type=int,
        default=256,
        help="Moving-average window for burst detection",
    )
    parser.add_argument(
        "--threshold-sigma",
        type=float,
        default=6.0,
        help="Envelope threshold in scaled MAD units",
    )
    parser.add_argument(
        "--min-burst-ms",
        type=float,
        default=1.0,
        help="Minimum burst length in milliseconds",
    )
    parser.add_argument(
        "--merge-gap-ms",
        type=float,
        default=0.5,
        help="Merge gaps shorter than this many milliseconds",
    )
    parser.add_argument(
        "--feature-window-count",
        type=int,
        default=8,
        help="Number of windows used for chirp tracking",
    )


def _config_from_args(args: argparse.Namespace, sample_rate_hz: float) -> AnalysisConfig:
    min_burst_samples = max(1, int(round(sample_rate_hz * args.min_burst_ms / 1000.0)))
    merge_gap_samples = max(0, int(round(sample_rate_hz * args.merge_gap_ms / 1000.0)))
    return AnalysisConfig(
        smoothing_samples=max(1, int(args.smoothing_samples)),
        threshold_sigma=float(args.threshold_sigma),
        min_burst_samples=min_burst_samples,
        merge_gap_samples=merge_gap_samples,
        feature_window_count=max(2, int(args.feature_window_count)),
    )


def _patterns_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    if getattr(args, "pattern", None):
        return tuple(args.pattern)
    return ("*.c64", "*.wav")


def _print_scan_summary(summary: dict[str, object]) -> None:
    print(
        f"inputs={len(summary['input_paths'])} events={summary['event_count']} "
        f"emitters={summary['emitter_count']}"
    )
    print(f"labels={summary['label_counts']}")
    for emitter in summary["emitters"]:
        freq_text = "unknown" if emitter["approx_freq_hz"] is None else f"{emitter['approx_freq_hz']:.1f}Hz"
        print(
            f"{emitter['candidate_id']} freq={freq_text} label={emitter['dominant_label']} "
            f"bursts={emitter['burst_count']} captures={emitter['capture_count']} "
            f"bw={emitter['mean_bandwidth_hz']:.1f}Hz dur={emitter['mean_duration_s']:.4f}s"
        )


def _print_fingerprint_summary(summary: dict[str, object]) -> None:
    print(f"inputs={len(summary['input_paths'])} fingerprints={summary['fingerprint_count']}")
    for fingerprint in summary["fingerprints"]:
        freq_text = (
            "unknown" if fingerprint["approx_freq_hz"] is None else f"{fingerprint['approx_freq_hz']:.1f}Hz"
        )
        print(
            f"{fingerprint['fingerprint_id']} freq={freq_text} label={fingerprint['dominant_label']} "
            f"bursts={fingerprint['burst_count']} "
            f"dur={fingerprint['duration_min_s']:.4f}-{fingerprint['duration_max_s']:.4f}s "
            f"bw={fingerprint['bandwidth_min_hz']:.1f}-{fingerprint['bandwidth_max_hz']:.1f}Hz"
        )


def _print_baseline_summary(summary: dict[str, object]) -> None:
    print(f"source_scans={len(summary['source_scan_paths'])} records={summary['record_count']}")
    for record in summary["records"]:
        freq_text = "unknown" if record["approx_freq_hz"] is None else f"{record['approx_freq_hz']:.1f}Hz"
        print(
            f"{record['baseline_id']} freq={freq_text} label={record['dominant_label']} "
            f"scans={record['scans_seen']} tol={record['frequency_tolerance_hz']:.1f}Hz "
            f"bw={record['bandwidth_mean_hz']:.1f}Hz dur={record['duration_mean_s']:.4f}s"
        )


def _print_watch_summary(summary: dict[str, object]) -> None:
    print(
        f"baseline={summary['baseline_path']} alerts={summary['alert_count']} "
        f"new={summary['new_count']} changed={summary['changed_count']}"
    )
    if not summary["alerts"]:
        print("no alerts")
        return
    for alert in summary["alerts"]:
        freq_text = "unknown" if alert["approx_freq_hz"] is None else f"{alert['approx_freq_hz']:.1f}Hz"
        print(
            f"{alert['candidate_id']} status={alert['status']} freq={freq_text} "
            f"label={alert['dominant_label']} msg={alert['message']}"
        )


def _print_dashboard_summary(artifacts: list[ArtifactSummary]) -> None:
    if not artifacts:
        print("No JSON yet.")
        return
    for artifact in artifacts:
        print(
            f"{artifact.artifact_type} modified={artifact.modified_at} "
            f"metric=\"{artifact.metric}\" path={artifact.path}"
        )
