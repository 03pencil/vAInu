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

"""Tests for src.pilot and src.feed — runnable via `.venv/bin/python tests/test_pilot.py`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import math

import numpy as np
import pandas as pd

from src.feed import parse_frame
from src.pilot import (
    STATUS_ALARM,
    STATUS_IDLE,
    STATUS_OK,
    STATUS_UNKNOWN,
    STATUS_WATCH,
    Envelope,
    PilotMonitor,
    RollingMean,
)


def test_rolling_mean_matches_pandas_with_nans() -> None:
    rng = np.random.default_rng(0)
    values = rng.normal(size=300)
    values[rng.random(300) < 0.4] = np.nan
    window, min_periods = 60, 30
    mine = RollingMean(window, min_periods)
    got = []
    for value in values:
        mine.push(value)
        got.append(mine.mean())
    expected = pd.Series(values).rolling(window, min_periods=min_periods).mean().to_numpy()
    for a, b in zip(got, expected):
        assert (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def _monitor(confirm: int = 3, escalate: int = 6) -> PilotMonitor:
    envelope = Envelope(channels=["vibration_rms_mm_s"])
    envelope.stats[("PUMP-T", "RUNNING")] = (np.array([2.0]), np.array([0.1]))
    return PilotMonitor(
        envelope, z_threshold=3.0, smoothing=1, confirm_samples=confirm,
        escalate_samples=escalate,
    )


def _sample(value: float, mode: str = "RUNNING", index: int = 0) -> dict:
    return {
        "asset_id": "PUMP-T",
        "timestamp_utc": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(seconds=10 * index),
        "operating_mode": mode,
        "vibration_rms_mm_s": value,
    }


def test_debounce_ring_then_confirm_then_escalate() -> None:
    monitor = _monitor(confirm=3, escalate=6)
    states = []
    for i in range(8):
        record = monitor.push(_sample(5.0, index=i))
        states.append((record["status"], record["debounce_state"]))
    assert states[0] == (STATUS_WATCH, "ringing")
    assert states[2] == (STATUS_ALARM, "confirmed")
    assert states[5] == (STATUS_ALARM, "escalated")


def test_healthy_running_is_ok_and_idle_is_not_alarmed() -> None:
    monitor = _monitor()
    assert monitor.push(_sample(2.0, index=0))["status"] == STATUS_OK
    assert monitor.push(_sample(9.0, mode="STOPPED", index=1))["status"] == STATUS_IDLE


def test_nan_only_channel_reports_unknown() -> None:
    monitor = _monitor()
    assert monitor.push(_sample(float("nan"), index=0))["status"] == STATUS_UNKNOWN


def test_snapshot_contract_fields() -> None:
    monitor = _monitor()
    monitor.push(_sample(5.0, index=0))
    snap = monitor.snapshot()
    record = snap["assets"][0]
    for key in ("asset_id", "timestamp_utc", "status", "debounce_state", "score_z",
                "top_channel", "evidence", "fault_type", "event_class", "confidence",
                "recommended_action"):
        assert key in record, key
    assert record["fault_type"] == "UNKNOWN"
    assert snap["generated_utc"] == record["timestamp_utc"]


def test_parse_frame_roundtrip_and_errors() -> None:
    line = ('{"asset_id": "PUMP-01", "timestamp_utc": "2026-01-01T00:00:00Z", '
            '"operating_mode": "RUNNING", "vibration_rms_mm_s": 2.1}')
    sample = parse_frame(line)
    assert sample["asset_id"] == "PUMP-01"
    assert sample["timestamp_utc"].tzinfo is not None
    assert sample["vibration_rms_mm_s"] == 2.1
    for bad in ("not json", '{"asset_id": "PUMP-01"}'):
        try:
            parse_frame(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS {name}")
