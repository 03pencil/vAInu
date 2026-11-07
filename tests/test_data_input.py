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

"""Tests for src.data_input — runnable via `.venv/bin/python tests/test_data_input.py`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.data_input import (
    FLAG_COMM_LOSS,
    FLAG_OUT_OF_RANGE,
    asset_channels,
    channel_columns,
    flag_counts,
    has_flag,
    load_assets,
    load_telemetry,
    split_assets,
    split_channels,
)


def test_load_telemetry_parsed_and_sorted() -> None:
    df = load_telemetry()
    assert not df.empty
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp_utc"])
    ordered = df.sort_values(["asset_id", "timestamp_utc"]).index
    assert (ordered == df.index).all()


def test_quality_flags_bitmask_helpers() -> None:
    df = load_telemetry()
    flags = flag_counts(df)
    clean = (df["quality_flags"] == 0)
    assert (flags == 0).equals(clean)
    # Any row with at least one bit set must be caught by some has_flag.
    any_flag = pd.Series(False, index=df.index)
    for bit in (FLAG_COMM_LOSS, FLAG_OUT_OF_RANGE, 4, 8, 16):
        any_flag |= has_flag(df, bit)
    assert any_flag.equals(~clean)


def test_channels_respect_config_and_nan_drop() -> None:
    df = load_telemetry()
    # Only channels that exist as columns are returned.
    assert "discharge_pressure_kpa" in channel_columns(df)
    # Sparse channel: dropna removes rows where the channel is NULL.
    frames = split_channels(df)
    bearing = frames.get("bearing_temp_c")
    if bearing is not None:  # exists in starter tier
        assert bearing["bearing_temp_c"].notna().all()
        assert len(bearing) <= len(df)


def test_assets_and_channel_masks() -> None:
    assets = load_assets()
    assert not assets.empty
    full = asset_channels("PUMP-02", assets)      # T2_FULL -> many channels
    legacy = asset_channels("PUMP-03", assets)    # T0_LEGACY -> few channels
    assert len(full) >= len(legacy)
    assert asset_channels("NOPE-99", assets) == []


def test_split_assets() -> None:
    df = load_telemetry()
    parts = split_assets(df)
    assert sum(len(p) for p in parts.values()) == len(df)


if __name__ == "__main__":
    for fn in (test_load_telemetry_parsed_and_sorted,
               test_quality_flags_bitmask_helpers,
               test_channels_respect_config_and_nan_drop,
               test_assets_and_channel_masks,
               test_split_assets):
        fn()
        print(f"PASS {fn.__name__}")
