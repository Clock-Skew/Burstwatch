from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import sys
from typing import Callable

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .artifacts import write_json_document
from .capture import load_capture
from .dashboard import ArtifactSummary, summarize_artifacts
from .models import AnalysisConfig
from .pipeline import analyze_capture, summarize_events
from .recording import RtlSdrCaptureRequest, record_rtl_sdr_capture
from .store import write_jsonl, write_sqlite
from .tools import ToolStatus, launch_tool, run_tool_check, tool_statuses
from .workflows import build_baseline, build_fingerprints, scan_inputs, watch_against_baseline

BANNER = """
 ______                        _  _  _                  _     
(____  \\                   _  (_)(_)(_)        _       | |    
 ____)  )_   _  ____ ___ _| |_ _  _  _ _____ _| |_ ____| |__  
|  __  (| | | |/ ___)___|_   _) || || (____ (_   _) ___)  _ \\ 
| |__)  ) |_| | |  |___ | | |_| || || / ___ | | |( (___| | | |
|______/|____/|_|  (___/   \\__)\\_____/\\_____|  \\__)____)_| |_|
""".strip("\n")


@dataclass(frozen=True)
class MenuAction:
    key: str
    title: str
    description: str
    runner: Callable[[Console], None]


@dataclass(frozen=True)
class AnalysisPromptValues:
    smoothing_samples: int
    threshold_sigma: float
    min_burst_ms: float
    merge_gap_ms: float
    feature_window_count: int


@dataclass(frozen=True)
class BandPreset:
    key: str
    label: str
    center_freq_hz: float
    sample_rate_hz: float = 2_400_000.0
    duration_s: float = 10.0
    freq_bin_hz: float = 25_000.0


@dataclass(frozen=True)
class SignalPath:
    key: str
    title: str
    center_freq_hz: float
    focus: str
    examples: str
    method: str
    boundary: str
    sample_rate_hz: float = 2_400_000.0
    duration_s: float = 10.0
    freq_bin_hz: float = 25_000.0

    def to_preset(self) -> BandPreset:
        return BandPreset(
            self.key,
            self.title,
            self.center_freq_hz,
            self.sample_rate_hz,
            self.duration_s,
            self.freq_bin_hz,
        )


DEFAULT_ANALYSIS_CONFIG = AnalysisPromptValues(
    smoothing_samples=256,
    threshold_sigma=6.0,
    min_burst_ms=1.0,
    merge_gap_ms=0.5,
    feature_window_count=8,
)

BAND_PRESETS = (
    BandPreset("1", "433.92 MHz ISM sensors/remotes", 433_920_000.0),
    BandPreset("2", "915 MHz US ISM sensors", 915_000_000.0),
    BandPreset("3", "315 MHz low-power devices", 315_000_000.0),
)

SIGNAL_PATHS = (
    SignalPath(
        "1",
        "433 MHz home/lab sensors",
        433_920_000.0,
        "Short OOK/ASK bursts and repeating IDs from owned sensors.",
        "Weather stations, contact sensors, outlet remotes, soil sensors.",
        "Burst timing, rough bandwidth, repeated center frequency, baseline changes.",
        "Owned or authorized devices only; do not decode a neighbor's telemetry.",
    ),
    SignalPath(
        "2",
        "315 MHz low-power devices",
        315_000_000.0,
        "Short bursts from older low-power remotes and some vehicle-adjacent sensors.",
        "Owned remotes, lab transmitters, your own vehicle TPMS presence checks.",
        "Burst count, duty cycle, OOK/ASK shape, time gaps between transmissions.",
        "Own equipment only; no key capture, replay, or third-party vehicle work.",
    ),
    SignalPath(
        "3",
        "902-928 MHz ISM activity",
        915_000_000.0,
        "FSK, chirp-like, and sensor telemetry activity in the US ISM band.",
        "Owned LoRa-style modules, lab sensors, smart plugs, hobby telemetry.",
        "Shape labels, channel occupancy, duty cycle, and new-emitter alerts.",
        "Metadata-only unless the device and protocol are yours or authorized.",
    ),
    SignalPath(
        "4",
        "137 MHz NOAA satellite practice",
        137_100_000.0,
        "Public weather satellite passes for receiver and antenna practice.",
        "NOAA APT passes recorded with Gqrx or GNU Radio.",
        "Waterfall review, Doppler awareness, pass timing, wide FM signal presence.",
        "Public broadcast reception; Burstwatch may only summarize energy bursts.",
        sample_rate_hz=1_024_000.0,
        duration_s=30.0,
        freq_bin_hz=50_000.0,
    ),
    SignalPath(
        "5",
        "1090 MHz ADS-B trust study",
        1_090_000_000.0,
        "Public aircraft broadcast visibility and receiver calibration.",
        "ADS-B/Mode S energy checks before using a purpose-built decoder.",
        "Signal presence, burst density, impossible-movement ideas for later analytics.",
        "Receive-only observation; no aviation interference or operational claims.",
        sample_rate_hz=2_400_000.0,
        duration_s=20.0,
        freq_bin_hz=100_000.0,
    ),
    SignalPath(
        "6",
        "FM broadcast receiver check",
        100_100_000.0,
        "Quick confidence check that the SDR, antenna, and gain are working.",
        "A known local FM station, viewed in Gqrx before deeper experiments.",
        "Waterfall shape, gain tuning, sample-rate sanity, antenna placement.",
        "Public broadcast calibration; not a security target.",
        sample_rate_hz=2_400_000.0,
        duration_s=8.0,
        freq_bin_hz=100_000.0,
    ),
    SignalPath(
        "7",
        "162 MHz NOAA weather radio",
        162_550_000.0,
        "Continuous public weather broadcast useful for receiver validation.",
        "NOAA Weather Radio in the 162.400-162.550 MHz range.",
        "Carrier presence, gain tuning, front-end overload checks, nearby interference.",
        "Public broadcast reception; do not treat voice/audio content as a target.",
        sample_rate_hz=1_024_000.0,
        duration_s=12.0,
        freq_bin_hz=25_000.0,
    ),
    SignalPath(
        "8",
        "868 MHz lab imports",
        868_300_000.0,
        "Imported or lab-only EU ISM captures when you have the hardware or files.",
        "Owned EU sensors, imported devices, or replay-free lab captures.",
        "Timing patterns, narrowband sensor activity, cross-region comparisons.",
        "Only for owned or authorized hardware/captures; regional legality varies.",
        sample_rate_hz=1_024_000.0,
        duration_s=10.0,
        freq_bin_hz=10_000.0,
    ),
    SignalPath(
        "9",
        "161.975 MHz AIS trust study",
        161_975_000.0,
        "Public maritime telemetry and receiver practice.",
        "AIS energy checks before using a purpose-built maritime decoder.",
        "Burst density, timing, receiver placement, and public-telemetry trust questions.",
        "Receive-only observation; no maritime interference or operational claims.",
        sample_rate_hz=1_024_000.0,
        duration_s=20.0,
        freq_bin_hz=25_000.0,
    ),
)


def run_menu() -> int:
    console = _build_menu_console()
    actions = _menu_actions()
    while True:
        _screen_break(console)
        console.print(render_menu_screen(console, actions))
        choice = _ask_choice(console, "Select action", [action.key for action in actions], default="1")
        action = next(action for action in actions if action.key == choice)
        if action.key == "9":
            console.print("[bold green]Exiting Burstwatch menu.[/bold green]")
            return 0

        _screen_break(console)
        console.print(render_header(console, subtitle=action.title, compact=True))
        try:
            action.runner(console)
        except Exception as exc:  # pragma: no cover - defensive UI path
            console.print(f"[bold red]Error:[/bold red] {exc}")
        _pause(console)


def _build_menu_console() -> Console:
    # Keep the interactive menu on simple styled terminal output only. Avoid
    # line-editing and live-render features, but allow static ANSI styling so
    # the menu still has color.
    width = shutil.get_terminal_size((100, 30)).columns
    return Console(
        width=width,
        color_system="standard",
        highlight=False,
        soft_wrap=True,
        emoji=False,
        force_terminal=True,
    )


def render_menu_screen(console: Console, actions: list[MenuAction]):
    width = console.size.width
    header = render_header(console, subtitle="Burstwatch signal workspace")
    table = Table(
        box=box.SIMPLE_HEAVY if width >= 72 else box.SIMPLE,
        expand=True,
        show_header=True,
        header_style="bold bright_cyan",
        pad_edge=False,
    )
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Action", style="bold white", ratio=2, overflow="fold")
    if width >= 72:
        table.add_column("Description", style="bright_black", ratio=4, overflow="fold")
    for action in actions:
        if width >= 72:
            table.add_row(action.key, action.title, action.description)
        else:
            table.add_row(action.key, action.title)

    footer = Panel(
        Text("Pick a path. Burstwatch records, scans, saves, and brings the results back here.", style="bright_black"),
        box=box.ROUNDED,
        border_style="blue",
        expand=True,
        padding=(0, 1),
    )
    return Group(header, table, footer)


def render_header(console: Console, *, subtitle: str, compact: bool = False):
    width = console.size.width
    if width >= 70 and not compact:
        banner = _render_banner()
    else:
        title = Text("Burstwatch", style="bold bright_cyan")
        title.stylize("bold magenta", 0, 1)
        title_panel = Panel(
            Align.center(title),
            title="Passive RF",
            box=box.ROUNDED,
            border_style="bright_blue",
            padding=(0, 1),
            expand=True,
        )
        subtitle_panel = Panel(
            Text(subtitle, style="bold white"),
            box=box.SQUARE,
            border_style="cyan",
            padding=(0, 1),
            expand=True,
        )
        return Group(title_panel, subtitle_panel)

    subtitle_panel = Panel(
        Text(subtitle, style="bold white"),
        box=box.SQUARE,
        border_style="cyan",
        padding=(0, 1),
        expand=True,
    )
    return Group(banner, subtitle_panel)


def _render_banner() -> Panel:
    styles = [
        "bold bright_cyan",
        "bold cyan",
        "bold bright_blue",
        "bold magenta",
        "bold bright_magenta",
        "bold bright_white",
    ]
    banner_text = Text()
    for index, line in enumerate(BANNER.splitlines()):
        banner_text.append(line, style=styles[index % len(styles)])
        if index != len(BANNER.splitlines()) - 1:
            banner_text.append("\n")
    return Panel(
        Align.center(banner_text),
        box=box.DOUBLE_EDGE,
        border_style="bright_blue",
        padding=(0, 1),
        expand=True,
    )


def _menu_actions() -> list[MenuAction]:
    return [
        MenuAction("1", "Start a session", "Choose a practical RF path and let Burstwatch handle the files.", _run_start_here_menu),
        MenuAction("2", "Signal board", "Review saved results and choose the next move.", _run_dashboard_menu),
        MenuAction("3", "Signal ideas", "Explore passive paths, bands, examples, and detection methods.", _run_signal_paths_menu),
        MenuAction("4", "Receiver tools", "Check, test, or launch rtl_sdr, Gqrx, and GNU Radio.", _run_tools_menu),
        MenuAction("5", "Record from SDR", "Capture from RTL-SDR, save files, scan, and return to results.", _run_capture_menu),
        MenuAction("6", "Open a capture", "Scan an existing IQ/WAV file or folder with sensible defaults.", _run_existing_capture_menu),
        MenuAction("7", "Baseline and watch", "Learn a local RF baseline and flag changes later.", _run_baseline_watch_menu),
        MenuAction("8", "Advanced tools", "Manual analyze, scan, fingerprint, baseline, and watch commands.", _run_advanced_menu),
        MenuAction("9", "Quit", "Exit the interactive menu.", lambda console: None),
    ]


def _run_start_here_menu(console: Console) -> None:
    _print_session_boundary(console)
    _print_tool_statuses(console, tool_statuses())
    _print_session_examples(console)
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Path", style="bold white")
    table.add_column("Best fit", style="bright_black")
    table.add_row("1", "Pick from signal ideas", "Choose a band by device type or experiment goal.")
    table.add_row("2", "Record a common band", "The USB SDR is plugged in and you want a fresh capture.")
    table.add_row("3", "Open an existing capture", "You already have a .c64 or .wav file/folder.")
    table.add_row("4", "Open receiver tools", "Use Gqrx, GNU Radio, or rtl_test from here.")
    table.add_row("5", "Return", "Go back to the main menu.")
    console.print(table)
    choice = _ask_choice(console, "Choose a path", ["1", "2", "3", "4", "5"], default="1")
    if choice == "1":
        _run_signal_paths_menu(console)
    elif choice == "2":
        _run_capture_menu(console)
    elif choice == "3":
        _run_existing_capture_menu(console)
    elif choice == "4":
        _run_tools_menu(console)
    else:
        return


def _run_capture_menu(console: Console, preset: BandPreset | None = None) -> None:
    if not _require_tool(console, "rtl_sdr"):
        return
    if _ask_confirm(console, "Run USB SDR hardware test first?", default=True):
        _run_rtl_test(console)
    if preset is None:
        _print_recording_examples(console)
        preset = _ask_band_preset(console)
    else:
        _print_selected_path(console, preset)
    center_freq_hz = preset.center_freq_hz
    sample_rate_hz = _ask_float(console, "Sample rate Hz", default=preset.sample_rate_hz)
    duration_s = _ask_float(console, "Duration seconds", default=preset.duration_s)
    output_path = _ask_path_default(console, "Saved IQ capture path", _default_capture_path(center_freq_hz))
    gain = _ask_text(console, "Gain", default="auto")
    device_index = _ask_int(console, "RTL-SDR device index", default=0)
    ppm = _ask_optional_int(console, "PPM correction", default="")
    rtl_sdr_path = _ask_text(console, "rtl_sdr executable", default="rtl_sdr")
    keep_raw_path = None
    if _ask_confirm(console, "Keep raw unsigned 8-bit IQ?", default=False):
        keep_raw_path = Path(_ask_required(console, "Raw IQ output path"))

    request = RtlSdrCaptureRequest(
        output_path=output_path,
        center_freq_hz=center_freq_hz,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
        gain=gain,
        device_index=device_index,
        ppm=ppm,
        rtl_sdr_path=rtl_sdr_path,
        keep_raw_path=keep_raw_path,
    )
    console.print("Recording passive IQ and converting to complex64...")
    result = record_rtl_sdr_capture(request)

    _print_capture_summary(console, result.to_dict())
    metadata_path = _default_artifact_path(output_path, "capture")
    write_json_document(result.to_dict(), metadata_path)
    console.print(f"[green]Saved capture metadata:[/green] {metadata_path}")
    _scan_saved_capture_with_defaults(
        console,
        result.output_path,
        sample_rate_hz=result.sample_rate_hz,
        center_freq_hz=result.center_freq_hz,
        freq_bin_hz=preset.freq_bin_hz,
    )
    _print_next_steps(console)


def _run_existing_capture_menu(console: Console) -> None:
    _print_capture_import_examples(console)
    capture_path = Path(_ask_required(console, "Capture file or folder"))
    sample_format = _ask_choice(console, "Input format", ["auto", "complex64", "wav"], default="auto")
    sample_rate_hz = None
    if sample_format != "wav":
        sample_rate_hz = _ask_float(console, "Sample rate Hz", default=2_400_000.0)
    center_freq_hz = _ask_optional_float(console, "Center frequency Hz", default="")
    freq_bin_hz = _ask_float(console, "Frequency grouping Hz", default=25_000.0)
    recursive = capture_path.is_dir()
    summary, events = scan_inputs(
        [capture_path],
        sample_rate_hz=sample_rate_hz,
        center_freq_hz=center_freq_hz,
        sample_format=sample_format,
        config_factory=lambda actual_sample_rate_hz: _analysis_config_from_prompt_values(
            DEFAULT_ANALYSIS_CONFIG,
            actual_sample_rate_hz,
        ),
        recursive=recursive,
        freq_bin_hz=freq_bin_hz,
    )
    _print_scan_summary(console, summary.to_dict())
    scan_path = _default_artifact_path(_artifact_source_stem(capture_path), "scan")
    event_path = _default_artifact_path(_artifact_source_stem(capture_path), "events", ".jsonl")
    write_json_document(summary.to_dict(), scan_path)
    write_jsonl(events, event_path)
    console.print(f"[green]Saved result JSON:[/green] {scan_path}")
    console.print(f"[green]Saved burst events:[/green] {event_path}")
    _print_next_steps(console)


def _run_signal_paths_menu(console: Console) -> None:
    console.print(
        Panel(
            (
                "These are starting points for receive-only RF work. "
                "Pick one to see examples, detection ideas, and a matching capture setup."
            ),
            title="Signal Ideas",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Path", style="bold white", overflow="fold")
    table.add_column("Center", justify="right", style="cyan", no_wrap=True)
    if console.size.width >= 92:
        table.add_column("Look for", style="bright_black", overflow="fold")
    for path in SIGNAL_PATHS:
        row = [path.key, path.title, f"{path.center_freq_hz / 1_000_000:.3f} MHz"]
        if console.size.width >= 92:
            row.append(path.focus)
        table.add_row(*row)
    return_row = ["0", "Return", "-"]
    if console.size.width >= 92:
        return_row.append("Back to the main menu.")
    table.add_row(*return_row)
    console.print(table)
    choice = _ask_choice(console, "Choose signal idea", [path.key for path in SIGNAL_PATHS] + ["0"], default="1")
    if choice == "0":
        return

    signal_path = next(path for path in SIGNAL_PATHS if path.key == choice)
    _print_signal_path_detail(console, signal_path)
    action = _ask_choice(console, "Next", ["1", "2", "3"], default="1")
    if action == "1":
        _run_capture_menu(console, preset=signal_path.to_preset())
    elif action == "2":
        _launch_tool_from_menu(console, "gqrx")


def _run_baseline_watch_menu(console: Console) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Workflow", style="bold white")
    table.add_column("Meaning", style="bright_black")
    table.add_row("1", "Build baseline", "Learn a local pattern from saved scan JSON.")
    table.add_row("2", "Watch against baseline", "Compare a new capture set against a saved baseline.")
    table.add_row("3", "Return", "Go back.")
    console.print(table)
    choice = _ask_choice(console, "Baseline workflow", ["1", "2", "3"], default="1")
    if choice == "1":
        scan_paths = _recent_artifact_paths("scan")
        if not scan_paths:
            console.print("[yellow]No scan JSON found yet. Start a session or open a capture first.[/yellow]")
            return
        baseline_path = Path("runs") / "baseline.json"
        summary = build_baseline(scan_paths)
        write_json_document(summary.to_dict(), baseline_path)
        _print_baseline_summary(console, summary.to_dict())
        console.print(f"[green]Saved baseline:[/green] {baseline_path}")
    elif choice == "2":
        _run_watch_menu(console)
    else:
        return


def _run_advanced_menu(console: Console) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Advanced action", style="bold white")
    table.add_row("1", "Analyze one capture")
    table.add_row("2", "Scan captures")
    table.add_row("3", "Build fingerprints")
    table.add_row("4", "Build baseline")
    table.add_row("5", "Watch against baseline")
    table.add_row("6", "Return")
    console.print(table)
    choice = _ask_choice(console, "Advanced workflow", ["1", "2", "3", "4", "5", "6"], default="1")
    if choice == "1":
        _run_analyze_menu(console)
    elif choice == "2":
        _run_scan_menu(console)
    elif choice == "3":
        _run_fingerprint_menu(console)
    elif choice == "4":
        _run_baseline_menu(console)
    elif choice == "5":
        _run_watch_menu(console)



def _run_analyze_menu(console: Console) -> None:
    capture_path = Path(_ask_required(console, "Capture path"))
    sample_format = _ask_choice(console, "Input format", ["auto", "complex64", "wav"], default="auto")
    sample_rate_hz = _ask_optional_float(console, "Sample rate Hz", default="2400000") if sample_format != "wav" else None
    center_freq_hz = _ask_optional_float(console, "Center frequency Hz", default="")
    prompt_values = _prompt_analysis_values(console)
    capture = load_capture(
        capture_path,
        sample_rate_hz=sample_rate_hz,
        center_freq_hz=center_freq_hz,
        sample_format=sample_format,
    )
    config = _analysis_config_from_prompt_values(prompt_values, capture.sample_rate_hz)
    events = analyze_capture(capture, config)
    summary = summarize_events(capture, events)
    _print_analyze_summary(console, summary)
    if _ask_confirm(console, "Write JSONL event output?", default=False):
        write_jsonl(events, Path(_ask_required(console, "JSONL output path")))
    if _ask_confirm(console, "Write SQLite event output?", default=False):
        write_sqlite(events, Path(_ask_required(console, "SQLite output path")))


def _run_scan_menu(console: Console) -> None:
    summary, events = _prompt_scan(console)
    _print_scan_summary(console, summary.to_dict())
    if _ask_confirm(console, "Write scan summary JSON?", default=True):
        write_json_document(summary.to_dict(), Path(_ask_required(console, "Summary JSON path")))
    if _ask_confirm(console, "Write raw event JSONL?", default=False):
        write_jsonl(events, Path(_ask_required(console, "Event JSONL path")))
    if _ask_confirm(console, "Write raw event SQLite?", default=False):
        write_sqlite(events, Path(_ask_required(console, "Event SQLite path")))


def _run_fingerprint_menu(console: Console) -> None:
    summary, _events = _prompt_scan(console)
    name_prefix = _ask_text(console, "Fingerprint ID prefix", default="fp")
    fingerprints = build_fingerprints(summary, name_prefix=name_prefix)
    _print_fingerprint_summary(console, fingerprints.to_dict())
    if _ask_confirm(console, "Write fingerprint JSON?", default=True):
        write_json_document(fingerprints.to_dict(), Path(_ask_required(console, "Fingerprint JSON path")))


def _run_baseline_menu(console: Console) -> None:
    scan_paths = _ask_path_list(console, "Scan summary JSON paths (comma separated)")
    freq_bin_hz = _ask_optional_float(console, "Frequency bin Hz", default="25000") or 25_000.0
    summary = build_baseline(scan_paths, freq_bin_hz=freq_bin_hz)
    _print_baseline_summary(console, summary.to_dict())
    if _ask_confirm(console, "Write baseline JSON?", default=True):
        write_json_document(summary.to_dict(), Path(_ask_required(console, "Baseline JSON path")))


def _run_watch_menu(console: Console) -> None:
    baseline_path = Path(_ask_required(console, "Baseline JSON path"))
    summary, _events = _prompt_scan(console)
    watch = watch_against_baseline(baseline_path, summary)
    _print_watch_summary(console, watch.to_dict())
    if _ask_confirm(console, "Write watch JSON?", default=True):
        write_json_document(watch.to_dict(), Path(_ask_required(console, "Watch JSON path")))


def _run_dashboard_menu(console: Console) -> None:
    root = Path("runs")
    artifacts = summarize_artifacts(root, recursive=True, limit=12)
    console.print(
        Panel(
            "This board reads saved Burstwatch results from runs/. To add data, record from the SDR or open an existing capture.",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    _print_dashboard_summary(console, artifacts)
    _print_frequency_reference(console)
    _print_authorized_tracks(console)
    _print_tool_statuses(console, tool_statuses())
    if artifacts:
        _print_dashboard_choices(console, with_artifacts=True)
        choice = _ask_choice(console, "Next action", ["1", "2", "3", "4"], default="1")
        if choice == "1":
            _run_capture_menu(console)
        elif choice == "2":
            _run_baseline_watch_menu(console)
        elif choice == "3":
            _run_existing_capture_menu(console)
        return

    _print_dashboard_choices(console, with_artifacts=False)
    choice = _ask_choice(console, "Next action", ["1", "2", "3"], default="1")
    if choice == "1":
        _run_start_here_menu(console)
    elif choice == "2":
        _run_tools_menu(console)


def _run_help_menu(console: Console) -> None:
    console.print(
        Panel(
            (
                "Suggested path:\n"
                "1. Start a session\n"
                "2. Pick a signal idea, record from RTL-SDR, or open an existing capture\n"
                "3. Burstwatch saves scan JSON and event logs in runs/\n"
                "4. Signal board shows the saved result and the next useful move\n\n"
                "Use Receiver tools to open Gqrx, GNU Radio Companion, or rtl_test."
            ),
            title="How Burstwatch Works",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _run_tools_menu(console: Console) -> None:
    statuses = tool_statuses()
    _print_tool_statuses(console, statuses)
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Action", style="white")
    table.add_row("1", "Run RTL-SDR hardware test")
    table.add_row("2", "Open Gqrx visual receiver")
    table.add_row("3", "Open GNU Radio Companion")
    table.add_row("4", "Show install commands")
    table.add_row("5", "Return")
    console.print(table)
    choice = _ask_choice(console, "Tool action", ["1", "2", "3", "4", "5"], default="1")
    if choice == "1":
        _run_rtl_test(console)
    elif choice == "2":
        _launch_tool_from_menu(console, "gqrx")
    elif choice == "3":
        _launch_tool_from_menu(console, "gnuradio")
    elif choice == "4":
        _print_install_hints(console, statuses)


def _prompt_scan(console: Console):
    inputs = _ask_path_list(console, "Capture paths or directories (comma separated)")
    sample_format = _ask_choice(console, "Input format", ["auto", "complex64", "wav"], default="auto")
    sample_rate_hz = _ask_optional_float(console, "Sample rate Hz", default="2400000") if sample_format != "wav" else None
    center_freq_hz = _ask_optional_float(console, "Center frequency Hz", default="")
    recursive = _ask_confirm(console, "Recurse into directories?", default=True)
    freq_bin_hz = _ask_optional_float(console, "Frequency bin Hz", default="25000") or 25_000.0
    prompt_values = _prompt_analysis_values(console)
    return scan_inputs(
        inputs,
        sample_rate_hz=sample_rate_hz,
        center_freq_hz=center_freq_hz,
        sample_format=sample_format,
        config_factory=lambda actual_sample_rate_hz: _analysis_config_from_prompt_values(
            prompt_values,
            actual_sample_rate_hz,
        ),
        recursive=recursive,
        freq_bin_hz=freq_bin_hz,
    )


def _scan_saved_capture_with_defaults(
    console: Console,
    capture_path: Path,
    *,
    sample_rate_hz: float,
    center_freq_hz: float | None,
    freq_bin_hz: float,
) -> None:
    console.print("Scanning saved capture and writing result files...")
    summary, events = scan_inputs(
        [capture_path],
        sample_rate_hz=sample_rate_hz,
        center_freq_hz=center_freq_hz,
        sample_format="complex64",
        config_factory=lambda actual_sample_rate_hz: _analysis_config_from_prompt_values(
            DEFAULT_ANALYSIS_CONFIG,
            actual_sample_rate_hz,
        ),
        freq_bin_hz=freq_bin_hz,
    )
    _print_scan_summary(console, summary.to_dict())
    scan_path = _default_artifact_path(capture_path, "scan")
    event_path = _default_artifact_path(capture_path, "events", ".jsonl")
    write_json_document(summary.to_dict(), scan_path)
    write_jsonl(events, event_path)
    console.print(f"[green]Saved result JSON:[/green] {scan_path}")
    console.print(f"[green]Saved burst events:[/green] {event_path}")


def _ask_band_preset(console: Console) -> BandPreset:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Band", style="bold white")
    table.add_column("Center", justify="right", style="cyan")
    for preset in BAND_PRESETS:
        table.add_row(preset.key, preset.label, f"{preset.center_freq_hz / 1_000_000:.3f} MHz")
    table.add_row("4", "Custom frequency", "manual")
    console.print(table)
    choice = _ask_choice(console, "Choose band", ["1", "2", "3", "4"], default="1")
    if choice == "4":
        center_freq_hz = _ask_float(console, "Center frequency Hz", default=433_920_000.0)
        return BandPreset("4", "Custom frequency", center_freq_hz)
    return next(preset for preset in BAND_PRESETS if preset.key == choice)


def _print_session_boundary(console: Console) -> None:
    console.print(
        Panel(
            (
                "Burstwatch is passive. Use it only with your own devices, your own lab, "
                "public/broadcast signals you are allowed to receive, or written authorization.\n\n"
                "The workflow saves files first, then scans those files. It does not transmit."
            ),
            title="Operating Boundary",
            box=box.ROUNDED,
            border_style="yellow",
            expand=True,
        )
    )


def _print_session_examples(console: Console) -> None:
    table = Table(box=box.SIMPLE, expand=True, header_style="bold bright_cyan")
    table.add_column("Good first session", style="bold white", overflow="fold")
    table.add_column("What it teaches", style="bright_black", overflow="fold")
    table.add_row("433.92 MHz owned sensor", "Short OOK/ASK bursts, repeated IDs, baseline changes.")
    table.add_row("FM broadcast check", "Receiver/gain sanity before deeper RF work.")
    table.add_row("Existing GNU Radio capture", "File handoff without remembering CLI flags.")
    console.print(table)


def _print_recording_examples(console: Console) -> None:
    console.print(
        Panel(
            (
                "Examples:\n"
                "- 433.920 MHz, 10 seconds: owned ISM sensors/remotes\n"
                "- 915.000 MHz, 10 seconds: owned US ISM telemetry experiments\n"
                "- 315.000 MHz, 10 seconds: owned low-power devices or your own TPMS presence checks\n\n"
                "If you are unsure, start with 433.920 MHz and keep the default sample rate."
            ),
            title="Capture Examples",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _print_capture_import_examples(console: Console) -> None:
    console.print(
        Panel(
            (
                "Examples:\n"
                "- captures/433920000-lab.c64 from Burstwatch\n"
                "- captures/ism-433/ as a folder of related captures\n"
                "- a GNU Radio complex64 File Sink output\n"
                "- a WAV recording exported from a receiver tool\n\n"
                "For complex64, provide the sample rate. For WAV, Burstwatch reads the sample rate from the file."
            ),
            title="Open A Capture",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _print_selected_path(console: Console, preset: BandPreset) -> None:
    console.print(
        Panel(
            (
                f"Path: {preset.label}\n"
                f"Center: {preset.center_freq_hz / 1_000_000:.3f} MHz\n"
                f"Default sample rate: {preset.sample_rate_hz:.0f} Hz\n"
                f"Default duration: {preset.duration_s:.0f} seconds"
            ),
            title="Selected Signal Path",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _print_signal_path_detail(console: Console, signal_path: SignalPath) -> None:
    console.print(
        Panel(
            (
                f"Center: {signal_path.center_freq_hz / 1_000_000:.3f} MHz\n"
                f"Examples: {signal_path.examples}\n"
                f"Look for: {signal_path.focus}\n"
                f"Detection method: {signal_path.method}\n"
                f"Boundary: {signal_path.boundary}"
            ),
            title=signal_path.title,
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    table = Table(box=box.SIMPLE, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Next move", style="bold white")
    table.add_row("1", "Record this center frequency with RTL-SDR")
    table.add_row("2", "Open Gqrx to view it first")
    table.add_row("3", "Return")
    console.print(table)


def _print_tool_statuses(console: Console, statuses: list[ToolStatus]) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Tool", style="bold white", overflow="fold")
    table.add_column("Status", style="bold", no_wrap=True)
    if console.size.width >= 86:
        table.add_column("Purpose", style="bright_black", overflow="fold")
    table.add_column("Command", style="cyan", overflow="fold")
    for status in statuses:
        row = [
            status.label,
            "[green]ready[/green]" if status.available else "[yellow]missing[/yellow]",
        ]
        if console.size.width >= 86:
            row.append(status.purpose)
        row.append(status.path or status.install_hint)
        table.add_row(*row)
    console.print(table)


def _print_frequency_reference(console: Console) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Band", style="bold yellow", overflow="fold")
    table.add_column("Center", style="magenta", no_wrap=True)
    if console.size.width >= 100:
        table.add_column("Use", style="white", overflow="fold")
        table.add_column("Look for", style="bright_black", overflow="fold")
    references = [
        ("315 MHz", "315.000", "Owned low-power devices", "Short OOK/ASK bursts"),
        ("433.92 MHz", "433.920", "Owned home/lab sensors", "Repeating IDs, narrow bursts"),
        ("868.3 MHz", "868.300", "Imported/lab EU ISM gear", "Narrow telemetry activity"),
        ("915 MHz", "915.000", "Owned US ISM telemetry", "FSK/chirp-like devices"),
        ("100.1 MHz", "100.100", "FM receiver check", "Wide FM broadcast shape"),
        ("137.1 MHz", "137.100", "NOAA APT practice", "Wide public satellite energy"),
        ("162.55 MHz", "162.550", "NOAA weather radio", "Continuous public carrier"),
        ("161.975 MHz", "161.975", "AIS trust study", "Public maritime bursts"),
        ("1090 MHz", "1090.000", "ADS-B trust study", "Dense public telemetry bursts"),
    ]
    for band, center, use, look_for in references:
        row = [band, f"{center} MHz"]
        if console.size.width >= 100:
            row.extend([use, look_for])
        table.add_row(*row)
    console.print(Panel(table, title="Band Reference", box=box.ROUNDED, border_style="bright_blue", expand=True))


def _print_authorized_tracks(console: Console) -> None:
    console.print(
        Panel(
            (
                "Sharper next tracks, still permission-first:\n"
                "- correlate RF captures with owned-lab network inventory\n"
                "- collect firmware, manuals, FCC IDs, and update metadata\n"
                "- compare time-of-day baselines and drift in emitter behavior\n"
                "- review companion apps and exported captures in one evidence trail"
            ),
            title="Authorized Research Tracks",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _print_install_hints(console: Console, statuses: list[ToolStatus]) -> None:
    commands = sorted({status.install_hint for status in statuses if not status.available})
    if not commands:
        console.print("[green]All known third-party tools are installed.[/green]")
        return
    for command in commands:
        console.print(f"[yellow]Install:[/yellow] {command}")


def _require_tool(console: Console, key: str) -> bool:
    for status in tool_statuses():
        if status.key == key and status.available:
            return True
        if status.key == key:
            console.print(f"[yellow]{status.label} is not installed.[/yellow]")
            console.print(f"[yellow]Install:[/yellow] {status.install_hint}")
            return False
    console.print(f"[yellow]Unknown tool:[/yellow] {key}")
    return False


def _launch_tool_from_menu(console: Console, key: str) -> None:
    try:
        process = launch_tool(key)
    except FileNotFoundError as exc:
        console.print(f"[yellow]Tool missing.[/yellow] {exc}")
        return
    console.print(f"[green]Launched process {process.pid}.[/green]")


def _run_rtl_test(console: Console) -> None:
    try:
        result = run_tool_check("rtl_test", timeout_s=10.0)
    except FileNotFoundError as exc:
        console.print(f"[yellow]Tool missing.[/yellow] {exc}")
        return
    except Exception as exc:
        console.print(f"[red]RTL-SDR test failed to run:[/red] {exc}")
        return
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    console.print(
        Panel(
            output or f"rtl_test exited with status {result.returncode}",
            title=f"RTL-SDR Test: exit {result.returncode}",
            box=box.ROUNDED,
            border_style="green" if result.returncode == 0 else "yellow",
            expand=True,
        )
    )


def _print_dashboard_choices(console: Console, *, with_artifacts: bool) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Next action", style="bold white")
    if with_artifacts:
        table.add_row("1", "Record and scan another capture")
        table.add_row("2", "Build baseline or watch for changes")
        table.add_row("3", "Open an existing capture")
        table.add_row("4", "Return")
    else:
        table.add_row("1", "Start a signal session")
        table.add_row("2", "Check or launch third-party tools")
        table.add_row("3", "Return")
    console.print(table)


def _print_next_steps(console: Console) -> None:
    console.print(
        Panel(
            (
                "Next: open Signal board to review saved outputs.\n"
                "After you have a few scans, use Baseline and watch to learn your local RF pattern."
            ),
            title="Next Step",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _recent_artifact_paths(artifact_type: str) -> list[Path]:
    return [
        artifact.path
        for artifact in summarize_artifacts("runs", recursive=True, limit=100)
        if artifact.artifact_type == artifact_type
    ]


def _prompt_analysis_values(console: Console) -> AnalysisPromptValues:
    return AnalysisPromptValues(
        smoothing_samples=_ask_int(console, "Smoothing samples", default=256),
        threshold_sigma=_ask_float(console, "Threshold sigma", default=6.0),
        min_burst_ms=_ask_float(console, "Minimum burst ms", default=1.0),
        merge_gap_ms=_ask_float(console, "Merge gap ms", default=0.5),
        feature_window_count=_ask_int(console, "Feature window count", default=8),
    )


def _analysis_config_from_prompt_values(
    values: AnalysisPromptValues,
    sample_rate_hz: float,
) -> AnalysisConfig:
    return _analysis_config_from_values(
        sample_rate_hz,
        smoothing_samples=values.smoothing_samples,
        threshold_sigma=values.threshold_sigma,
        min_burst_ms=values.min_burst_ms,
        merge_gap_ms=values.merge_gap_ms,
        feature_window_count=values.feature_window_count,
    )


def _analysis_config_from_values(
    sample_rate_hz: float,
    *,
    smoothing_samples: int,
    threshold_sigma: float,
    min_burst_ms: float,
    merge_gap_ms: float,
    feature_window_count: int,
) -> AnalysisConfig:
    min_burst_samples = max(1, int(round(sample_rate_hz * min_burst_ms / 1000.0)))
    merge_gap_samples = max(0, int(round(sample_rate_hz * merge_gap_ms / 1000.0)))
    return AnalysisConfig(
        smoothing_samples=max(1, int(smoothing_samples)),
        threshold_sigma=float(threshold_sigma),
        min_burst_samples=min_burst_samples,
        merge_gap_samples=merge_gap_samples,
        feature_window_count=max(2, int(feature_window_count)),
    )


def _ask_required(console: Console, label: str) -> str:
    while True:
        value = _ask_text(console, label).strip()
        if value:
            return value
        console.print("[bold red]Value is required.[/bold red]")


def _ask_optional_float(console: Console, label: str, *, default: str) -> float | None:
    while True:
        raw = _ask_text(console, label, default=default).strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            console.print("[bold red]Enter a numeric value or leave blank.[/bold red]")


def _ask_optional_int(console: Console, label: str, *, default: str) -> int | None:
    while True:
        raw = _ask_text(console, label, default=default).strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            console.print("[bold red]Enter an integer value or leave blank.[/bold red]")


def _ask_path_list(console: Console, label: str) -> list[str]:
    raw = _ask_required(console, label)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _ask_path_default(console: Console, label: str, default: Path) -> Path:
    return Path(_ask_text(console, label, default=str(default)))


def _pause(console: Console) -> None:
    _read_prompt_line(console, "[bright_black]Press Enter to continue[/bright_black] ")


def _screen_break(console: Console) -> None:
    console.print()
    console.rule("[bright_black]Burstwatch[/bright_black]")


# Use direct stdin reads instead of input()/readline-backed prompt helpers so
# the menu never enters terminal line-editing modes that can disturb keypad state.
def _read_prompt_line(console: Console, prompt_markup: str) -> str:
    console.print(Text.from_markup(prompt_markup), end="")
    console.file.flush()
    raw = sys.stdin.readline()
    if raw == "":
        return ""
    return raw.rstrip("\n")


def _ask_text(console: Console, label: str, *, default: str | None = None) -> str:
    suffix = f" ({default})" if default is not None else ""
    raw = _read_prompt_line(console, f"[bold cyan]{label}[/bold cyan]{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def _ask_choice(console: Console, label: str, choices: list[str], *, default: str | None = None) -> str:
    choice_suffix = "/".join(choices)
    default_suffix = f" ({default})" if default is not None else ""
    while True:
        raw = _read_prompt_line(
            console,
            f"[bold cyan]{label}[/bold cyan] [{choice_suffix}]{default_suffix}: ",
        ).strip()
        if not raw and default is not None:
            return default
        if raw in choices:
            return raw
        console.print(f"[bold red]Choose one of:[/bold red] {', '.join(choices)}")


def _ask_confirm(console: Console, label: str, *, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        raw = _read_prompt_line(console, f"[bold cyan]{label}[/bold cyan] [{default_text}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        console.print("[bold red]Enter y or n.[/bold red]")


def _ask_float(console: Console, label: str, *, default: float) -> float:
    while True:
        raw = _ask_text(console, label, default=str(default)).strip()
        try:
            return float(raw)
        except ValueError:
            console.print("[bold red]Enter a numeric value.[/bold red]")


def _ask_int(console: Console, label: str, *, default: int) -> int:
    while True:
        raw = _ask_text(console, label, default=str(default)).strip()
        try:
            return int(raw)
        except ValueError:
            console.print("[bold red]Enter an integer value.[/bold red]")


def _default_capture_path(center_freq_hz: float) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("captures") / f"{int(round(center_freq_hz))}-{timestamp}.c64"


def _default_artifact_path(capture_path: Path, label: str, suffix: str = ".json") -> Path:
    return Path("runs") / f"{capture_path.stem}-{label}{suffix}"


def _artifact_source_stem(path: Path) -> Path:
    if path.is_dir():
        return Path(path.name or "captures")
    return path


def _print_capture_summary(console: Console, summary: dict[str, object]) -> None:
    console.print(
        Panel(
            (
                f"capture={summary['output_path']}\n"
                f"samples={summary['sample_count']}\n"
                f"sample_rate_hz={summary['sample_rate_hz']}\n"
                f"center_freq_hz={summary['center_freq_hz']}"
            ),
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )


def _print_analyze_summary(console: Console, summary: dict[str, object]) -> None:
    console.print(
        Panel(
            f"capture={summary['source_path']}\nbursts={summary['burst_count']}\nlabels={summary['label_counts']}",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Idx", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Label", style="white", no_wrap=True)
    table.add_column("Dur s", justify="right", style="green")
    table.add_column("BW Hz", justify="right", style="magenta")
    table.add_column("Conf", justify="right", style="cyan")
    for index, event in enumerate(summary["events"], start=1):
        features = event["features"]
        table.add_row(
            str(index),
            str(event["label"]),
            f"{event['duration_s']:.4f}",
            f"{features['bandwidth_hz']:.1f}",
            f"{event['confidence']:.2f}",
        )
    console.print(table)


def _print_scan_summary(console: Console, summary: dict[str, object]) -> None:
    console.print(
        Panel(
            f"inputs={len(summary['input_paths'])}\nevents={summary['event_count']}\nemitters={summary['emitter_count']}",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Emitter", style="bold yellow", no_wrap=True)
    table.add_column("Freq", style="magenta", no_wrap=True)
    table.add_column("Label", style="white", no_wrap=True)
    table.add_column("Bursts", justify="right", style="green")
    table.add_column("Mean BW", justify="right", style="cyan")
    if console.size.width >= 96:
        table.add_column("Mean Dur", justify="right", style="bright_white")
    for emitter in summary["emitters"]:
        freq_text = "unknown" if emitter["approx_freq_hz"] is None else f"{emitter['approx_freq_hz']:.1f}Hz"
        row = [
            str(emitter["candidate_id"]),
            freq_text,
            str(emitter["dominant_label"]),
            str(emitter["burst_count"]),
            f"{emitter['mean_bandwidth_hz']:.1f}",
        ]
        if console.size.width >= 96:
            row.append(f"{emitter['mean_duration_s']:.4f}s")
        table.add_row(*row)
    console.print(table)


def _print_fingerprint_summary(console: Console, summary: dict[str, object]) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Fingerprint", style="bold yellow", no_wrap=True)
    table.add_column("Freq", style="magenta", no_wrap=True)
    table.add_column("Label", style="white", no_wrap=True)
    table.add_column("Dur Range", style="green")
    table.add_column("BW Range", style="cyan")
    for fingerprint in summary["fingerprints"]:
        freq_text = "unknown" if fingerprint["approx_freq_hz"] is None else f"{fingerprint['approx_freq_hz']:.1f}Hz"
        table.add_row(
            str(fingerprint["fingerprint_id"]),
            freq_text,
            str(fingerprint["dominant_label"]),
            f"{fingerprint['duration_min_s']:.4f}-{fingerprint['duration_max_s']:.4f}s",
            f"{fingerprint['bandwidth_min_hz']:.1f}-{fingerprint['bandwidth_max_hz']:.1f}Hz",
        )
    console.print(table)


def _print_baseline_summary(console: Console, summary: dict[str, object]) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Baseline", style="bold yellow", no_wrap=True)
    table.add_column("Freq", style="magenta", no_wrap=True)
    table.add_column("Label", style="white", no_wrap=True)
    table.add_column("Scans", justify="right", style="green")
    table.add_column("Tolerance", justify="right", style="cyan")
    for record in summary["records"]:
        freq_text = "unknown" if record["approx_freq_hz"] is None else f"{record['approx_freq_hz']:.1f}Hz"
        table.add_row(
            str(record["baseline_id"]),
            freq_text,
            str(record["dominant_label"]),
            str(record["scans_seen"]),
            f"{record['frequency_tolerance_hz']:.1f}Hz",
        )
    console.print(table)


def _print_watch_summary(console: Console, summary: dict[str, object]) -> None:
    console.print(
        Panel(
            f"alerts={summary['alert_count']}\nnew={summary['new_count']}\nchanged={summary['changed_count']}",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Emitter", style="bold yellow", no_wrap=True)
    table.add_column("Status", style="white", no_wrap=True)
    table.add_column("Freq", style="magenta", no_wrap=True)
    table.add_column("Label", style="green", no_wrap=True)
    table.add_column("Message", style="cyan", overflow="fold")
    for alert in summary["alerts"]:
        freq_text = "unknown" if alert["approx_freq_hz"] is None else f"{alert['approx_freq_hz']:.1f}Hz"
        table.add_row(
            str(alert["candidate_id"]),
            str(alert["status"]),
            freq_text,
            str(alert["dominant_label"]),
            str(alert["message"]),
        )
    if not summary["alerts"]:
        table.add_row("-", "ok", "-", "-", "No alert conditions matched.")
    console.print(table)


def _print_dashboard_summary(console: Console, artifacts: list[ArtifactSummary]) -> None:
    if not artifacts:
        console.print(
            Panel(
                "No saved results yet.\nRecord from the SDR or open a capture, and Burstwatch will write result files into runs/.",
                title="Signal Board",
                box=box.ROUNDED,
                border_style="yellow",
                expand=True,
            )
        )
        return

    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Type", style="bold yellow", no_wrap=True)
    table.add_column("Metric", style="white", overflow="fold")
    if console.size.width >= 86:
        table.add_column("Modified", style="green", no_wrap=True)
    table.add_column("Path", style="cyan", overflow="fold")
    for artifact in artifacts:
        row = [artifact.artifact_type, artifact.metric]
        if console.size.width >= 86:
            row.append(artifact.modified_at)
        row.append(str(artifact.path))
        table.add_row(*row)
    console.print(table)
