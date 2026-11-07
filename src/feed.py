"""Telemetry sources for the pilot: replay today, UART later.

Both sources yield one dict per asset sample, in timestamp order:
    {"asset_id": str, "timestamp_utc": pd.Timestamp,
     "operating_mode": str, "<channel>": float | NaN, ...}

The pilot monitor only depends on this shape, so a UART source can
replace the replay source without touching detection code.
"""
from __future__ import annotations

import json
import sys
from typing import Iterator

import pandas as pd

from .data_input import channel_columns, load_telemetry

UART_FRAME_KEYS = ("asset_id", "timestamp_utc", "operating_mode")


class ReplayFeed:
    """Replays a telemetry file (starter/full tier) as a sample stream."""

    def __init__(self, path: "str | None" = None) -> None:
        self.df = load_telemetry(path)
        self.channels = channel_columns(self.df)

    def __iter__(self) -> Iterator[dict]:
        for row in self.df.to_dict("records"):
            yield row

    def timestamps(self) -> "list[pd.Timestamp]":
        return sorted(self.df["timestamp_utc"].unique())


def parse_frame(line: str) -> dict:
    """Parse one UART frame (JSON line) into the sample shape.

    Frame contract (logic box -> UNO Q MCU, forwarded to MPU):
        {"asset_id": "PUMP-01", "timestamp_utc": "2026-01-01T00:00:00Z",
         "operating_mode": "RUNNING", "vibration_rms_mm_s": 2.1, ...}
    Missing channels are NaN. Raises ValueError on malformed frames.
    """
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed UART frame: {exc}") from exc
    missing = [key for key in UART_FRAME_KEYS if key not in raw]
    if missing:
        raise ValueError(f"UART frame missing keys: {missing}")
    sample = dict(raw)
    sample["timestamp_utc"] = pd.Timestamp(raw["timestamp_utc"], tz="UTC")
    return sample


def to_frame(row: dict, channels: list[str]) -> dict:
    """Build one UART frame (JSON-safe, NaN sent as null) from a telemetry row."""
    frame = {
        "asset_id": str(row["asset_id"]),
        "timestamp_utc": pd.Timestamp(row["timestamp_utc"]).isoformat(),
        "operating_mode": str(row["operating_mode"]),
    }
    for channel in channels:
        value = row.get(channel)
        frame[channel] = None if value is None or pd.isna(value) else float(value)
    return frame


class StdinFeed:
    """Reads frames (one JSON object per line) from a text stream, such as a pipe or serial port.

    Malformed lines are skipped and counted in `bad_frames`; the first error is kept
    in `first_error` so the operator can see what went wrong.
    """

    def __init__(self, stream=None) -> None:
        self.stream = stream if stream is not None else sys.stdin
        self.bad_frames = 0
        self.first_error: str | None = None

    def __iter__(self) -> Iterator[dict]:
        for line in self.stream:
            if not line.strip():
                continue
            try:
                yield parse_frame(line)
            except ValueError as exc:
                self.bad_frames += 1
                if self.first_error is None:
                    self.first_error = str(exc)


class UartFeed:
    """Placeholder for the logic-box UART link (not wired yet).

    Once hardware exists, iterate over lines read from the serial port and
    yield `parse_frame(line)`. Until then the pilot runs on ReplayFeed.
    """

    def __init__(self, port: str, baud: int = 9600) -> None:
        self.port = port
        self.baud = baud

    def __iter__(self) -> Iterator[dict]:
        raise NotImplementedError("UART input is not implemented yet; use ReplayFeed.")
