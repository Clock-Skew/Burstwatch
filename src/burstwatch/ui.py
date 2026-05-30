from __future__ import annotations

from dataclasses import dataclass
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
from .models import AnalysisConfig
from .pipeline import analyze_capture, summarize_events
from .store import write_jsonl, write_sqlite
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
        if action.key == "7":
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
        Text("Use the scripted subcommands for automation. Use the menu for guided runs.", style="bright_black"),
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
        MenuAction("1", "Analyze one capture", "Classify bursts in a single IQ or WAV file.", _run_analyze_menu),
        MenuAction("2", "Scan captures", "Cluster bursts into passive emitter candidates.", _run_scan_menu),
        MenuAction("3", "Build fingerprints", "Generate reusable passive RF fingerprints.", _run_fingerprint_menu),
        MenuAction("4", "Build baseline", "Learn normal emitter profiles from prior scan JSON.", _run_baseline_menu),
        MenuAction("5", "Watch against baseline", "Flag new or changed emitters from a fresh scan.", _run_watch_menu),
        MenuAction("6", "Show help", "Display the command surface and menu guidance.", _run_help_menu),
        MenuAction("7", "Quit", "Exit the interactive menu.", lambda console: None),
    ]


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


def _run_help_menu(console: Console) -> None:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold bright_cyan")
    table.add_column("Command", style="bold yellow", ratio=2)
    table.add_column("Purpose", style="white", ratio=4)
    table.add_row("analyze", "Classify bursts in one capture.")
    table.add_row("scan", "Group bursts into passive emitter candidates.")
    table.add_row("fingerprint", "Build reusable profiles from emitters.")
    table.add_row("baseline", "Learn normal emitters from prior scans.")
    table.add_row("watch", "Compare a fresh scan against a saved baseline.")
    table.add_row("menu", "Launch this guided Rich interface.")
    console.print(table)


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


def _ask_path_list(console: Console, label: str) -> list[str]:
    raw = _ask_required(console, label)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _pause(console: Console) -> None:
    console.input("[bright_black]Press Enter to continue[/bright_black]")


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
