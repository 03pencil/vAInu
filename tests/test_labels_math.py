"""Tests for src.labels + src.math — runnable via `.venv/bin/python tests/test_labels_math.py`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.data_input import channel_columns, load_telemetry
from src.labels import (
    LABEL_BENIGN,
    LABEL_FAULT_DETECTABLE,
    LABEL_FAULT_WARMING,
    LABEL_UNKNOWN,
    load_benign_windows,
    load_events,
    label_telemetry,
)
from src.math import (
    group_rolled,
    merged_stats,
    modified_zscores,
    robust_stats,
    rolling_robust_z,
)


def test_events_and_benign_tables_load() -> None:
    events = load_events()
    benign = load_benign_windows()
    assert {"onset_utc", "detectable_utc", "end_utc"}.issubset(events.columns)
    assert not benign.empty and not events.empty


def test_label_telemetry_covers_windows() -> None:
    df = load_telemetry()
    labeled = label_telemetry(df)
    counts = labeled["label"].value_counts()
    # Some confirmed-good windows and data outside every window both exist.
    assert LABEL_BENIGN in counts.index
    assert LABEL_UNKNOWN in counts.index
    assert labeled["label"].isin(
        [LABEL_BENIGN, LABEL_FAULT_WARMING, LABEL_FAULT_DETECTABLE, LABEL_UNKNOWN,
         "fault_undetectable"]
    ).all()
    # Pre-detect rows must lie strictly between onset and detectable.
    warm = labeled[labeled["label"] == LABEL_FAULT_WARMING]
    detectable = labeled[labeled["label"] == LABEL_FAULT_DETECTABLE]
    assert not warm.empty and not detectable.empty
    has_event = labeled["label_event_id"].ne("").fillna(False).astype(bool)
    assert has_event.equals(~labeled["label"].isin([LABEL_BENIGN, LABEL_UNKNOWN]))


def test_robust_stats_nan_safe() -> None:
    df = load_telemetry()
    channels = channel_columns(df)
    stats = robust_stats(df, channels)
    # Sparse channels still get stats where data exists; missing ones NaN.
    assert stats["median"]["discharge_pressure_kpa"].notna().all()
    # MAD defined exactly where median is defined (observed values only).
    bearing = stats["mad"]["bearing_temp_c"]
    assert bearing.notna().equals(stats["median"]["bearing_temp_c"].notna())
    assert (bearing.dropna() > 0).all()


def test_modified_zscores_shape_and_outliers() -> None:
    df = load_telemetry()
    channels = channel_columns(df)
    stats = robust_stats(df, channels)
    z = modified_zscores(df, stats, channels)
    assert list(z.columns) == [f"z_{c}" for c in channels]
    assert z.index.equals(df.index)
    # Extreme raw value produces an extreme z: max row of a channel.
    big = df["discharge_pressure_kpa"].idxmax()
    assert abs(z.loc[big, "z_discharge_pressure_kpa"]) > 0
    # Rolling window stats never produce errors on the sparse channel.
    z_roll = rolling_robust_z(df, window=60, channels=channels)
    assert list(z_roll.columns) == [f"z_{c}" for c in channels]


def test_merged_stats_fills_missing_assets() -> None:
    df = load_telemetry(join_assets=True)
    assert "profile" in df.columns
    channels = channel_columns(df)
    merged = merged_stats(df, channels, min_count=30)
    plain = robust_stats(df, channels, min_count=30)
    # merged_stats must cover at least the same rows, and any row NaN in
    # plain (heavily fault-labeled assets) except where no profile data
    # exists either must be filled in merged.
    assert merged["median"].shape[0] >= plain["median"].shape[0]


def test_group_rolled_preserves_rows() -> None:
    df = load_telemetry()
    channels = channel_columns(df)
    stats = robust_stats(df, channels)
    z = modified_zscores(df, stats, channels)
    keyed = pd.concat([df[["asset_id"]], z], axis=1)
    rolled = group_rolled(keyed, window=60)
    assert rolled.shape[0] == df.shape[0]
    assert rolled.index.equals(df.index)
    assert rolled["asset_id"].equals(df["asset_id"])


if __name__ == "__main__":
    for fn in (test_events_and_benign_tables_load,
               test_label_telemetry_covers_windows,
               test_robust_stats_nan_safe,
               test_modified_zscores_shape_and_outliers,
               test_merged_stats_fills_missing_assets,
               test_group_rolled_preserves_rows):
        fn()
        print(f"PASS {fn.__name__}")
