from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
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
class GuidedPreset:
    key: str
    label: str
    center_freq_hz: float
    sample_rate_hz: float = 2_400_000.0
    duration_s: float = 10.0
    freq_bin_hz: float = 25_000.0


BEGINNER_CONFIG = AnalysisPromptValues(
    smoothing_samples=256,
    threshold_sigma=6.0,
    min_burst_ms=1.0,
    merge_gap_ms=0.5,
    feature_window_count=8,
)

GUIDED_PRESETS = (
    GuidedPreset("1", "433.92 MHz ISM sensors/remotes", 433_920_000.0),
    GuidedPreset("2", "915 MHz US ISM sensors", 915_000_000.0),
    GuidedPreset("3", "315 MHz low-power devices", 315_000_000.0),
)


def run_menu() -> int:
    console = Console()
    actions = _menu_actions()
    while True:
        console.clear()
        console.print(render_menu_screen(console, actions))
        choice = Prompt.ask(
            "[bold cyan]Select action[/bold cyan]",
            choices=[action.key for action in actions],
            default="1",
            console=console,
        )
        action = next(action for action in actions if action.key == choice)
        if action.key == "9":
            console.print("[bold green]Exiting Burstwatch menu.[/bold green]")
            return 0

        console.clear()
        console.print(render_header(console, subtitle=action.title))
        try:
            action.runner(console)
        except Exception as exc:  # pragma: no cover - defensive UI path
            console.print(f"[bold red]Error:[/bold red] {exc}")
        _pause(console)


def render_menu_screen(console: Console, actions: list[MenuAction]):
    width = console.size.width
    header = render_header(console, subtitle="Passive RF workflow menu")
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
        Text("New users: choose 1. The menu creates captures, scans, and dashboard files for you.", style="bright_black"),
        box=box.ROUNDED,
        border_style="blue",
        expand=True,
        padding=(0, 1),
    )
    return Group(header, table, footer)


def render_header(console: Console, *, subtitle: str):
    width = console.size.width
    if width >= 70:
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
        MenuAction("1", "Start here", "Guided first run with defaults, automatic scan output, and next steps.", _run_start_here_menu),
        MenuAction("2", "Guided dashboard", "Show current project state and the next useful action.", _run_dashboard_menu),
        MenuAction("3", "Tools and receivers", "Check, test, or launch rtl_sdr, Gqrx, and GNU Radio.", _run_tools_menu),
        MenuAction("4", "Record and scan", "Record from RTL-SDR, save files, scan, and return to dashboard.", _run_capture_menu),
        MenuAction("5", "Use saved capture", "Analyze or scan an existing IQ/WAV file with guided defaults.", _run_existing_capture_menu),
        MenuAction("6", "Baseline and watch", "Build a baseline or compare fresh captures against one.", _run_baseline_watch_menu),
        MenuAction("7", "Advanced workflows", "Manual analyze, scan, fingerprint, baseline, and watch commands.", _run_advanced_menu),
        MenuAction("8", "Show help", "Plain-language explanation of the workflow and tools.", _run_help_menu),
        MenuAction("9", "Quit", "Exit the interactive menu.", lambda console: None),
    ]


def _run_start_here_menu(console: Console) -> None:
    _print_beginner_boundary(console)
    _print_tool_statuses(console, tool_statuses())
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Path", style="bold white")
    table.add_column("Use when", style="bright_black")
    table.add_row("1", "Record with RTL-SDR", "The USB SDR is plugged in and you want a fresh capture.")
    table.add_row("2", "Use an existing capture", "You already have a .c64 or .wav file/folder.")
    table.add_row("3", "Open Gqrx", "You want to visually explore the spectrum first.")
    table.add_row("4", "Open GNU Radio", "You want to build or edit a capture flowgraph.")
    table.add_row("5", "Return", "Go back to the main menu.")
    console.print(table)
    choice = Prompt.ask(
        "What do you want to do?",
        choices=["1", "2", "3", "4", "5"],
        default="1",
        console=console,
    )
    if choice == "1":
        _run_capture_menu(console)
    elif choice == "2":
        _run_existing_capture_menu(console)
    elif choice == "3":
        _launch_tool_from_menu(console, "gqrx")
    elif choice == "4":
        _launch_tool_from_menu(console, "gnuradio")
    else:
        return


def _run_capture_menu(console: Console) -> None:
    if not _require_tool(console, "rtl_sdr"):
        return
    if Confirm.ask("Run USB SDR hardware test first?", default=True, console=console):
        _run_rtl_test(console)
    preset = _ask_guided_preset(console)
    center_freq_hz = preset.center_freq_hz
    sample_rate_hz = FloatPrompt.ask("Sample rate Hz", default=preset.sample_rate_hz, console=console)
    duration_s = FloatPrompt.ask("Duration seconds", default=preset.duration_s, console=console)
    output_path = _ask_path_default(console, "Saved IQ capture path", _default_capture_path(center_freq_hz))
    gain = Prompt.ask("Gain", default="auto", console=console)
    device_index = IntPrompt.ask("RTL-SDR device index", default=0, console=console)
    ppm = _ask_optional_int(console, "PPM correction", default="")
    rtl_sdr_path = Prompt.ask("rtl_sdr executable", default="rtl_sdr", console=console)
    keep_raw_path = None
    if Confirm.ask("Keep raw unsigned 8-bit IQ?", default=False, console=console):
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
    with console.status("Recording passive IQ and converting to complex64...", spinner="dots"):
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
    capture_path = Path(_ask_required(console, "Capture file or folder"))
    sample_format = Prompt.ask(
        "Input format",
        choices=["auto", "complex64", "wav"],
        default="auto",
        console=console,
    )
    sample_rate_hz = None
    if sample_format != "wav":
        sample_rate_hz = FloatPrompt.ask("Sample rate Hz", default=2_400_000.0, console=console)
    center_freq_hz = _ask_optional_float(console, "Center frequency Hz", default="")
    freq_bin_hz = FloatPrompt.ask("Frequency grouping Hz", default=25_000.0, console=console)
    recursive = capture_path.is_dir()
    summary, events = scan_inputs(
        [capture_path],
        sample_rate_hz=sample_rate_hz,
        center_freq_hz=center_freq_hz,
        sample_format=sample_format,
        config_factory=lambda actual_sample_rate_hz: _analysis_config_from_prompt_values(
            BEGINNER_CONFIG,
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
    console.print(f"[green]Saved dashboard JSON:[/green] {scan_path}")
    console.print(f"[green]Saved burst events:[/green] {event_path}")
    _print_next_steps(console)


def _run_baseline_watch_menu(console: Console) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Workflow", style="bold white")
    table.add_column("Meaning", style="bright_black")
    table.add_row("1", "Build baseline", "Learn what normal looks like from saved scan JSON.")
    table.add_row("2", "Watch against baseline", "Compare a new capture set against a saved baseline.")
    table.add_row("3", "Return", "Go back.")
    console.print(table)
    choice = Prompt.ask(
        "Baseline workflow",
        choices=["1", "2", "3"],
        default="1",
        console=console,
    )
    if choice == "1":
        scan_paths = _recent_artifact_paths("scan")
        if not scan_paths:
            console.print("[yellow]No scan JSON found yet. Run Start here or Use saved capture first.[/yellow]")
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
    choice = Prompt.ask(
        "Advanced workflow",
        choices=["1", "2", "3", "4", "5", "6"],
        default="1",
        console=console,
    )
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
    sample_format = Prompt.ask(
        "Input format",
        choices=["auto", "complex64", "wav"],
        default="auto",
        console=console,
    )
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
    if Confirm.ask("Write JSONL event output?", default=False, console=console):
        write_jsonl(events, Path(_ask_required(console, "JSONL output path")))
    if Confirm.ask("Write SQLite event output?", default=False, console=console):
        write_sqlite(events, Path(_ask_required(console, "SQLite output path")))


def _run_scan_menu(console: Console) -> None:
    summary, events = _prompt_scan(console)
    _print_scan_summary(console, summary.to_dict())
    if Confirm.ask("Write scan summary JSON?", default=True, console=console):
        write_json_document(summary.to_dict(), Path(_ask_required(console, "Summary JSON path")))
    if Confirm.ask("Write raw event JSONL?", default=False, console=console):
        write_jsonl(events, Path(_ask_required(console, "Event JSONL path")))
    if Confirm.ask("Write raw event SQLite?", default=False, console=console):
        write_sqlite(events, Path(_ask_required(console, "Event SQLite path")))


def _run_fingerprint_menu(console: Console) -> None:
    summary, _events = _prompt_scan(console)
    name_prefix = Prompt.ask("Fingerprint ID prefix", default="fp", console=console)
    fingerprints = build_fingerprints(summary, name_prefix=name_prefix)
    _print_fingerprint_summary(console, fingerprints.to_dict())
    if Confirm.ask("Write fingerprint JSON?", default=True, console=console):
        write_json_document(fingerprints.to_dict(), Path(_ask_required(console, "Fingerprint JSON path")))


def _run_baseline_menu(console: Console) -> None:
    scan_paths = _ask_path_list(console, "Scan summary JSON paths (comma separated)")
    freq_bin_hz = _ask_optional_float(console, "Frequency bin Hz", default="25000") or 25_000.0
    summary = build_baseline(scan_paths, freq_bin_hz=freq_bin_hz)
    _print_baseline_summary(console, summary.to_dict())
    if Confirm.ask("Write baseline JSON?", default=True, console=console):
        write_json_document(summary.to_dict(), Path(_ask_required(console, "Baseline JSON path")))


def _run_watch_menu(console: Console) -> None:
    baseline_path = Path(_ask_required(console, "Baseline JSON path"))
    summary, _events = _prompt_scan(console)
    watch = watch_against_baseline(baseline_path, summary)
    _print_watch_summary(console, watch.to_dict())
    if Confirm.ask("Write watch JSON?", default=True, console=console):
        write_json_document(watch.to_dict(), Path(_ask_required(console, "Watch JSON path")))


def _run_dashboard_menu(console: Console) -> None:
    root = Path("runs")
    artifacts = summarize_artifacts(root, recursive=True, limit=12)
    console.print(
        Panel(
            "This dashboard reads saved Burstwatch outputs. It does not scan by itself.",
            box=box.ROUNDED,
            border_style="bright_blue",
            expand=True,
        )
    )
    _print_dashboard_summary(console, artifacts)
    _print_tool_statuses(console, tool_statuses())
    if artifacts:
        _print_dashboard_choices(console, with_artifacts=True)
        choice = Prompt.ask("Next action", choices=["1", "2", "3", "4"], default="1", console=console)
        if choice == "1":
            _run_capture_menu(console)
        elif choice == "2":
            _run_baseline_watch_menu(console)
        elif choice == "3":
            _run_existing_capture_menu(console)
        return

    _print_dashboard_choices(console, with_artifacts=False)
    choice = Prompt.ask("Next action", choices=["1", "2", "3"], default="1", console=console)
    if choice == "1":
        _run_start_here_menu(console)
    elif choice == "2":
        _run_tools_menu(console)


def _run_help_menu(console: Console) -> None:
    console.print(
        Panel(
            (
                "Normal path:\n"
                "1. Start here\n"
                "2. Record with RTL-SDR or choose an existing capture\n"
                "3. Burstwatch saves scan JSON in runs/\n"
                "4. Dashboard shows what was found and what to do next\n\n"
                "Use Tools and receivers to open Gqrx, GNU Radio Companion, or rtl_test."
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
    choice = Prompt.ask("Tool action", choices=["1", "2", "3", "4", "5"], default="1", console=console)
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
    sample_format = Prompt.ask(
        "Input format",
        choices=["auto", "complex64", "wav"],
        default="auto",
        console=console,
    )
    sample_rate_hz = _ask_optional_float(console, "Sample rate Hz", default="2400000") if sample_format != "wav" else None
    center_freq_hz = _ask_optional_float(console, "Center frequency Hz", default="")
    recursive = Confirm.ask("Recurse into directories?", default=True, console=console)
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
    with console.status("Scanning saved capture and writing dashboard files...", spinner="dots"):
        summary, events = scan_inputs(
            [capture_path],
            sample_rate_hz=sample_rate_hz,
            center_freq_hz=center_freq_hz,
            sample_format="complex64",
            config_factory=lambda actual_sample_rate_hz: _analysis_config_from_prompt_values(
                BEGINNER_CONFIG,
                actual_sample_rate_hz,
            ),
            freq_bin_hz=freq_bin_hz,
        )
    _print_scan_summary(console, summary.to_dict())
    scan_path = _default_artifact_path(capture_path, "scan")
    event_path = _default_artifact_path(capture_path, "events", ".jsonl")
    write_json_document(summary.to_dict(), scan_path)
    write_jsonl(events, event_path)
    console.print(f"[green]Saved dashboard JSON:[/green] {scan_path}")
    console.print(f"[green]Saved burst events:[/green] {event_path}")


def _ask_guided_preset(console: Console) -> GuidedPreset:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Key", style="bold yellow", width=4, no_wrap=True)
    table.add_column("Band", style="bold white")
    table.add_column("Center", justify="right", style="cyan")
    for preset in GUIDED_PRESETS:
        table.add_row(preset.key, preset.label, f"{preset.center_freq_hz / 1_000_000:.3f} MHz")
    table.add_row("4", "Custom frequency", "manual")
    console.print(table)
    choice = Prompt.ask("Choose band", choices=["1", "2", "3", "4"], default="1", console=console)
    if choice == "4":
        center_freq_hz = FloatPrompt.ask("Center frequency Hz", default=433_920_000.0, console=console)
        return GuidedPreset("4", "Custom frequency", center_freq_hz)
    return next(preset for preset in GUIDED_PRESETS if preset.key == choice)


def _print_beginner_boundary(console: Console) -> None:
    console.print(
        Panel(
            (
                "Burstwatch is passive. Use it only with your own devices, your own lab, "
                "public/broadcast signals you are allowed to receive, or written authorization.\n\n"
                "The guided flow saves files first, then scans those files. It does not transmit."
            ),
            title="Before You Start",
            box=box.ROUNDED,
            border_style="yellow",
            expand=True,
        )
    )


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
        table.add_row("3", "Use an existing capture")
        table.add_row("4", "Return")
    else:
        table.add_row("1", "Start guided first capture")
        table.add_row("2", "Check or launch third-party tools")
        table.add_row("3", "Return")
    console.print(table)


def _print_next_steps(console: Console) -> None:
    console.print(
        Panel(
            (
                "Next: open Guided dashboard to review saved outputs.\n"
                "After you have a few scans, use Baseline and watch to learn normal activity."
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
        smoothing_samples=IntPrompt.ask("Smoothing samples", default=256, console=console),
        threshold_sigma=FloatPrompt.ask("Threshold sigma", default=6.0, console=console),
        min_burst_ms=FloatPrompt.ask("Minimum burst ms", default=1.0, console=console),
        merge_gap_ms=FloatPrompt.ask("Merge gap ms", default=0.5, console=console),
        feature_window_count=IntPrompt.ask("Feature window count", default=8, console=console),
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
        value = Prompt.ask(f"[bold cyan]{label}[/bold cyan]", console=console).strip()
        if value:
            return value
        console.print("[bold red]Value is required.[/bold red]")


def _ask_optional_float(console: Console, label: str, *, default: str) -> float | None:
    while True:
        raw = Prompt.ask(f"[bold cyan]{label}[/bold cyan]", default=default, console=console).strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            console.print("[bold red]Enter a numeric value or leave blank.[/bold red]")


def _ask_optional_int(console: Console, label: str, *, default: str) -> int | None:
    while True:
        raw = Prompt.ask(f"[bold cyan]{label}[/bold cyan]", default=default, console=console).strip()
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
    return Path(Prompt.ask(label, default=str(default), console=console))


def _pause(console: Console) -> None:
    console.input("[bright_black]Press Enter to continue[/bright_black]")


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
                "No JSON yet.",
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
