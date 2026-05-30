from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import BurstEvent


def write_jsonl(events: Iterable[BurstEvent], path: str | Path) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), sort_keys=True))
            handle.write("\n")
            count += 1
    return count


def write_sqlite(events: Iterable[BurstEvent], path: str | Path) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination) as connection:
        _ensure_schema(connection)
        count = 0
        for event in events:
            connection.execute(
                """
                INSERT INTO bursts (
                    source_path,
                    sample_rate_hz,
                    center_freq_hz,
                    start_sample,
                    end_sample,
                    start_time_s,
                    end_time_s,
                    duration_s,
                    label,
                    confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.capture_path,
                    event.sample_rate_hz,
                    event.center_freq_hz,
                    event.start_sample,
                    event.end_sample,
                    event.start_time_s,
                    event.end_time_s,
                    event.duration_s,
                    event.label,
                    event.confidence,
                    json.dumps(event.to_dict(), sort_keys=True),
                ),
            )
            count += 1
        connection.commit()
    return count


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS bursts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            sample_rate_hz REAL NOT NULL,
            center_freq_hz REAL,
            start_sample INTEGER NOT NULL,
            end_sample INTEGER NOT NULL,
            start_time_s REAL NOT NULL,
            end_time_s REAL NOT NULL,
            duration_s REAL NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_bursts_source_path ON bursts(source_path)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_bursts_label ON bursts(label)"
    )

