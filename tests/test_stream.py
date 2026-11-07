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

"""Tests for the line-by-line stream — runnable via `.venv/bin/python tests/test_stream.py`."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.feed import StdinFeed, parse_frame, to_frame
from src.pilot import Envelope, PilotMonitor

CHANNELS = ["vibration_rms_mm_s", "motor_current_a"]


def _envelope() -> Envelope:
    envelope = Envelope(channels=CHANNELS)
    for asset in ("PUMP-A", "PUMP-B"):
        envelope.stats[(asset, "RUNNING")] = (np.array([2.0, 10.0]), np.array([0.2, 1.0]))
    return envelope


def _rows() -> pd.DataFrame:
    start = pd.Timestamp("2026-01-01", tz="UTC")
    rows = []
    for i in range(40):
        for asset in ("PUMP-A", "PUMP-B"):
            vibration = 2.0 + (3.0 if asset == "PUMP-A" and 10 <= i < 25 else 0.0)
            current = np.nan if i % 7 == 0 else 10.0 + 0.1 * (i % 3)
            rows.append({
                "asset_id": asset,
                "timestamp_utc": start + pd.Timedelta(seconds=10 * i),
                "operating_mode": "RUNNING",
                "vibration_rms_mm_s": vibration,
                "motor_current_a": current,
            })
    return pd.DataFrame(rows)


def test_frame_round_trip_keeps_values_and_nulls() -> None:
    row = _rows().iloc[0].to_dict()
    row["motor_current_a"] = np.nan
    line = json.dumps(to_frame(row, CHANNELS), allow_nan=False)
    sample = parse_frame(line)
    assert sample["asset_id"] == "PUMP-A"
    assert sample["timestamp_utc"] == pd.Timestamp(row["timestamp_utc"])
    assert sample["vibration_rms_mm_s"] == row["vibration_rms_mm_s"]
    assert pd.isna(sample["motor_current_a"])


def test_stdin_feed_skips_and_counts_bad_lines() -> None:
    good = json.dumps(to_frame(_rows().iloc[0].to_dict(), CHANNELS))
    text = "\n".join(["not json", good, "", '{"asset_id": "PUMP-A"}', good]) + "\n"
    feed = StdinFeed(io.StringIO(text))
    samples = list(feed)
    assert len(samples) == 2
    assert feed.bad_frames == 2
    assert feed.first_error is not None


def test_stream_gives_same_status_as_file_replay() -> None:
    rows = _rows()
    replay_monitor = PilotMonitor(_envelope(), z_threshold=3.0, smoothing=3,
                                  confirm_samples=2, escalate_samples=5)
    for row in rows.to_dict("records"):
        replay_monitor.push(row)

    lines = "\n".join(json.dumps(to_frame(row, CHANNELS), allow_nan=False)
                      for row in rows.to_dict("records")) + "\n"
    stream_monitor = PilotMonitor(_envelope(), z_threshold=3.0, smoothing=3,
                                  confirm_samples=2, escalate_samples=5)
    seen_alarm = False
    for sample in StdinFeed(io.StringIO(lines)):
        record = stream_monitor.push(sample)
        if sample["asset_id"] == "PUMP-A" and record["status"] == "alarm":
            seen_alarm = True

    assert replay_monitor.snapshot() == stream_monitor.snapshot()
    assert seen_alarm, "the injected fault should raise an alarm while streaming"


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS {name}")
