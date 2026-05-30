from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


@dataclass(frozen=True)
class ToolDefinition:
    key: str
    label: str
    command: tuple[str, ...]
    purpose: str
    install_hint: str
    launches_gui: bool = False


@dataclass(frozen=True)
class ToolStatus:
    key: str
    label: str
    command: tuple[str, ...]
    purpose: str
    install_hint: str
    available: bool
    path: str | None
    launches_gui: bool = False


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        key="rtl_test",
        label="RTL-SDR hardware test",
        command=("rtl_test", "-t"),
        purpose="Checks whether the USB SDR can be opened.",
        install_hint="sudo apt install -y rtl-sdr",
    ),
    ToolDefinition(
        key="rtl_sdr",
        label="RTL-SDR recorder",
        command=("rtl_sdr",),
        purpose="Records passive IQ samples for Burstwatch.",
        install_hint="sudo apt install -y rtl-sdr",
    ),
    ToolDefinition(
        key="gqrx",
        label="Gqrx visual receiver",
        command=("gqrx",),
        purpose="Opens a waterfall view for exploring signals visually.",
        install_hint="sudo apt install -y gqrx-sdr",
        launches_gui=True,
    ),
    ToolDefinition(
        key="gnuradio",
        label="GNU Radio Companion",
        command=("gnuradio-companion",),
        purpose="Opens GNU Radio Companion for custom capture flowgraphs.",
        install_hint="sudo apt install -y gnuradio",
        launches_gui=True,
    ),
)


def tool_statuses(definitions: Iterable[ToolDefinition] = TOOL_DEFINITIONS) -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for definition in definitions:
        path = shutil.which(definition.command[0])
        statuses.append(
            ToolStatus(
                key=definition.key,
                label=definition.label,
                command=definition.command,
                purpose=definition.purpose,
                install_hint=definition.install_hint,
                available=path is not None,
                path=path,
                launches_gui=definition.launches_gui,
            )
        )
    return statuses


def find_tool(key: str) -> ToolStatus:
    for status in tool_statuses():
        if status.key == key:
            return status
    raise ValueError(f"unknown tool: {key}")


def launch_tool(key: str) -> subprocess.Popen[bytes]:
    status = find_tool(key)
    if not status.available or status.path is None:
        raise FileNotFoundError(status.install_hint)
    command = [status.path, *status.command[1:]]
    return subprocess.Popen(command)


def run_tool_check(key: str, *, timeout_s: float = 10.0) -> subprocess.CompletedProcess[str]:
    status = find_tool(key)
    if not status.available or status.path is None:
        raise FileNotFoundError(status.install_hint)
    command = [status.path, *status.command[1:]]
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_s)
