# vAInu pump-sensor-project - frontmatter
#
# Part of the Since AI 2026 hackathon (RETROFIT AI challenge).
# Team vAInu 2026: Paavo Gaidach, Matias Hirvonen.
# Licensed under the MIT License, Copyright (c) 2026 P.Gaidach & M.Hirvonen.
# See the LICENSE file in the repository root for the full license text.
#
# Totally fictional: all data and scenarios are synthetic.
#
# Vibe coded. Not for real-world use as it is. This is a hackathon prototype:
# it is not safety-certified and must not be used to monitor real machines,
# make maintenance decisions, or protect people.

"""Pilot monitor: causal, streaming per-asset status for the bench test.

Mirrors the sanity-gate detection (robust envelope z -> smoothed z ->
RUNNING-only alarm -> confirm/escalate debounce), but processes one sample
at a time so it can sit behind any feed (replay now, UART later).

Every value at time t uses only samples with timestamp <= t. The envelope
(median/MAD per asset x operating mode) is a fitted baseline from benign
windows, built once at start-up.

Output is advisory only: fault_type and event_class stay UNKNOWN until the
learned classifier (to-do Layer 2) exists.
"""
from __future__ import annotations

import json
import math
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import get_debounce_config, get_smoothing_window, get_z_threshold
from .data_input import channel_columns, load_telemetry
from .labels import FAULT_LABELS, label_telemetry, load_benign_windows, load_events
from .math import Z_CONSTANT, merged_stats

STATUS_OK = "ok"
STATUS_WATCH = "watch"
STATUS_ALARM = "alarm"
STATUS_IDLE = "idle"
STATUS_UNKNOWN = "unknown"


@dataclass
class Envelope:
    """Healthy baseline: median/MAD per (asset_id, operating_mode)."""

    channels: list[str]
    stats: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)


def build_envelope(data_path: "str | None" = None) -> Envelope:
    """Fit the healthy envelope on every row that is not a labeled fault."""
    df = load_telemetry(data_path, join_assets=True)
    df = label_telemetry(df, load_events(data_path), load_benign_windows(data_path))
    channels = channel_columns(df)
    stats = merged_stats(df[~df["label"].isin(FAULT_LABELS)], channels)
    envelope = Envelope(channels=channels)
    for key, median in stats["median"].iterrows():
        mad = stats["mad"].loc[key]
        envelope.stats[tuple(key)] = (median.to_numpy(dtype=float), mad.to_numpy(dtype=float))
    return envelope


class RollingMean:
    """Trailing mean over the last `window` rows, NaN-skipping like pandas.

    Matches pandas rolling(window, min_periods).mean(): the window counts
    rows (NaN included), the mean uses only non-NaN values, and fewer than
    `min_periods` valid values gives NaN. O(1) per update.
    """

    def __init__(self, window: int, min_periods: int) -> None:
        self.window = window
        self.min_periods = min_periods
        self.rows: deque[float] = deque()
        self.total = 0.0
        self.count = 0

    def push(self, value: float) -> None:
        self.rows.append(value)
        if not math.isnan(value):
            self.total += value
            self.count += 1
        if len(self.rows) > self.window:
            dropped = self.rows.popleft()
            if not math.isnan(dropped):
                self.total -= dropped
                self.count -= 1

    def mean(self) -> float:
        if self.count < self.min_periods:
            return float("nan")
        return self.total / self.count


@dataclass
class AssetState:
    rollers: dict[str, RollingMean]
    alarm_run: int = 0
    pending: dict = field(default_factory=dict)


class PilotMonitor:
    """Feeds samples one by one and returns the latest status per asset."""

    def __init__(
        self,
        envelope: Envelope,
        z_threshold: "float | None" = None,
        smoothing: "int | None" = None,
        confirm_samples: "int | None" = None,
        escalate_samples: "int | None" = None,
    ) -> None:
        debounce = get_debounce_config()
        self.envelope = envelope
        self.z_threshold = get_z_threshold() if z_threshold is None else z_threshold
        self.smoothing = get_smoothing_window() if smoothing is None else smoothing
        self.confirm = debounce["confirm_samples"] if confirm_samples is None else confirm_samples
        self.escalate = (
            debounce["escalate_samples"] if escalate_samples is None else escalate_samples
        )
        self.min_periods = min(max(2, self.smoothing // 2), self.smoothing)
        self.assets: dict[str, AssetState] = {}

    def _state(self, asset_id: str) -> AssetState:
        if asset_id not in self.assets:
            self.assets[asset_id] = AssetState(rollers={
                channel: RollingMean(self.smoothing, self.min_periods)
                for channel in self.envelope.channels
            })
        return self.assets[asset_id]

    def push(self, sample: dict) -> dict:
        """Ingest one sample; returns the asset's pending state (see `snapshot`)."""
        asset_id = str(sample["asset_id"])
        mode = str(sample.get("operating_mode", ""))
        state = self._state(asset_id)
        envelope = self.envelope.stats.get((asset_id, mode))

        for index, channel in enumerate(self.envelope.channels):
            value = _as_float(sample.get(channel))
            z = float("nan")
            if envelope is not None and not math.isnan(value):
                median, mad = envelope[0][index], envelope[1][index]
                if not math.isnan(mad) and mad > 0:
                    z = Z_CONSTANT * (value - median) / mad
            state.rollers[channel].push(z)

        smoothed = {c: r.mean() for c, r in state.rollers.items()}
        known = {c: v for c, v in smoothed.items() if not math.isnan(v)}
        running = mode == "RUNNING"
        alarm = running and any(abs(v) > self.z_threshold for v in known.values())
        state.alarm_run = state.alarm_run + 1 if alarm else 0
        status, debounce_state = _classify(
            running, alarm, state.alarm_run, self.confirm, self.escalate, bool(known),
        )
        state.pending = {
            "timestamp": sample["timestamp_utc"],
            "mode": mode,
            "status": status,
            "debounce_state": debounce_state,
            "known": known,
        }
        return state.pending

    def snapshot(self) -> dict:
        """Latest record per asset, sorted by asset_id."""
        records = [
            _record(asset_id, state.pending, self.z_threshold)
            for asset_id, state in sorted(self.assets.items()) if state.pending
        ]
        generated = max((r["timestamp_utc"] for r in records), default=None)
        return {"generated_utc": generated, "assets": records}


def _record(asset_id: str, pending: dict, threshold: float) -> dict:
    """Full status record (the contract the UI reads)."""
    known = pending["known"]
    status = pending["status"]
    ranked = sorted(known.items(), key=lambda item: abs(item[1]), reverse=True)
    score = abs(ranked[0][1]) if ranked else None
    top = ranked[0][0] if ranked else None
    return {
        "asset_id": asset_id,
        "timestamp_utc": _iso(pending["timestamp"]),
        "operating_mode": pending["mode"],
        "status": status,
        "debounce_state": pending["debounce_state"],
        "score_z": round(score, 2) if score is not None else None,
        "top_channel": top,
        "evidence": [{"channel": c, "z": round(v, 2)} for c, v in ranked[:3]],
        "fault_type": "UNKNOWN",
        "event_class": "UNKNOWN",
        "confidence": _confidence(status, score, threshold),
        "recommended_action": _action(status, asset_id, top),
    }


def _as_float(value) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _iso(timestamp) -> str:
    return pd.Timestamp(timestamp).isoformat()


def _classify(running, alarm, alarm_run, confirm, escalate, has_data):
    if not running:
        return STATUS_IDLE, ""
    if not has_data:
        return STATUS_UNKNOWN, ""
    if alarm and alarm_run >= escalate:
        return STATUS_ALARM, "escalated"
    if alarm and alarm_run >= confirm:
        return STATUS_ALARM, "confirmed"
    if alarm:
        return STATUS_WATCH, "ringing"
    return STATUS_OK, ""


def _confidence(status, score, threshold):
    """Heuristic only (distance over threshold); not a calibrated probability."""
    if status not in (STATUS_WATCH, STATUS_ALARM) or score is None:
        return None
    return round(min(1.0, score / (2 * threshold)), 2)


def _action(status, asset_id, top):
    if status == STATUS_ALARM:
        return f"Inspect {top} on {asset_id} and verify on site. Advisory only."
    if status == STATUS_WATCH:
        return "Keep watching; no action yet."
    if status == STATUS_UNKNOWN:
        return "No usable readings; check instrumentation."
    return "None."


def write_state(snapshot: dict, out_dir: Path) -> None:
    """Atomically replace state.json so a UI can poll it safely."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "state.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, allow_nan=False))
    tmp.replace(target)


class TransitionLog:
    """Appends one JSON line whenever an asset's status or debounce state changes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.last: dict[str, tuple] = {}

    def update(self, records: Iterable[dict]) -> None:
        lines = []
        for record in records:
            key = (record["status"], record["debounce_state"])
            if self.last.get(record["asset_id"]) != key:
                self.last[record["asset_id"]] = key
                lines.append(json.dumps(record, allow_nan=False))
        if lines:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")


def run_pilot(
    feed: Iterable[dict],
    monitor: PilotMonitor,
    out_dir: Path,
    speed: float = 0.0,
    publish_every_s: float = 60.0,
    max_samples: "int | None" = None,
) -> dict:
    """Drive the monitor from a feed and publish state every `publish_every_s` of data time.

    speed: data seconds per wall second (0 = as fast as possible).
    """
    log = TransitionLog(out_dir / "predictions.jsonl")
    last_published = None
    count = 0
    for sample in feed:
        if max_samples is not None and count >= max_samples:
            break
        stamp = pd.Timestamp(sample["timestamp_utc"])
        if last_published is None:
            last_published = stamp
        elif (stamp - last_published).total_seconds() >= publish_every_s:
            if speed > 0:
                time.sleep((stamp - last_published).total_seconds() / speed)
            snapshot = monitor.snapshot()
            write_state(snapshot, out_dir)
            log.update(snapshot["assets"])
            last_published = stamp
        monitor.push(sample)
        count += 1
    snapshot = monitor.snapshot()
    write_state(snapshot, out_dir)
    log.update(snapshot["assets"])
    return snapshot
