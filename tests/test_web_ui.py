"""Tests for src.web_ui — runnable via `.venv/bin/python tests/test_web_ui.py`."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.web_ui import (
    STATUS_ALARM,
    STATUS_IDLE,
    STATUS_OK,
    STATUS_UNKNOWN,
    STATUS_WATCH,
    AssetSeries,
    DashboardData,
    json_safe,
    status_for,
    top_deviations,
)


def _fake_asset() -> AssetSeries:
    """Asset whose default vibration channel is missing (sparse retrofit)."""
    timestamps = pd.DatetimeIndex(
        pd.date_range("2025-01-01", periods=5, freq="10s", tz="UTC")
    )
    values = {
        "vibration_rms_mm_s": np.array([np.nan] * 5),
        "discharge_pressure_kpa": np.array([100.0, 101.0, 102.0, 103.0, 104.0]),
        "suction_pressure_kpa": np.array([30.0, 31.0, 32.0, 33.0, 34.0]),
    }
    z = {
        "vibration_rms_mm_s": np.array([np.nan] * 5),
        "discharge_pressure_kpa": np.zeros(5),
        "suction_pressure_kpa": np.array([0.0, 0.0, 0.0, 0.0, -4.5]),
    }
    return AssetSeries(
        asset_id="PUMP-X",
        profile="TEST",
        control="VFD",
        instrumentation_tier="T1",
        timestamps=timestamps,
        modes=np.array(["RUNNING"] * 5),
        values=values,
        z=z,
        alarm=np.zeros(5, dtype=bool),
    )


def _fake_dashboard() -> DashboardData:
    item = _fake_asset()
    return DashboardData(
        series=[item],
        channels=list(item.values),
        units={"suction_pressure_kpa": "kPa(g)"},
        z_threshold=3.0,
        watch_fraction=0.5,
        default_channel="vibration_rms_mm_s",
    )


def test_json_safe_handles_missing_and_numpy() -> None:
    assert json_safe(float("nan")) is None
    assert json_safe(float("inf")) is None
    assert json_safe(np.float64("nan")) is None
    assert json_safe(np.int64(3)) == 3
    assert json_safe(np.bool_(True)) is True
    assert json_safe([1.0, np.nan, float("-inf")]) == [1.0, None, None]
    assert json_safe({"a": np.nan, "b": np.float64(2.5)}) == {"a": None, "b": 2.5}


def test_status_for_covers_all_states() -> None:
    assert status_for("STOPPED", False, None, 3.0, 0.5) == STATUS_IDLE
    assert status_for("RUNNING", True, 4.0, 3.0, 0.5) == STATUS_ALARM
    assert status_for("RUNNING", False, 2.0, 3.0, 0.5) == STATUS_WATCH
    assert status_for("RUNNING", False, 1.0, 3.0, 0.5) == STATUS_OK
    assert status_for("RUNNING", False, None, 3.0, 0.5) == STATUS_UNKNOWN


def test_top_deviations_sorts_by_absolute_z() -> None:
    z_scores = {
        "a": np.array([0.1, 4.0]),
        "b": np.array([np.nan, 3.5]),
        "c": np.array([0.0, -5.0]),
    }
    values = {
        "a": np.array([10.0, 11.0]),
        "b": np.array([np.nan, 12.0]),
        "c": np.array([13.0, 14.0]),
    }
    units = {"a": "bar", "b": "C", "c": "mm/s"}
    top = top_deviations(z_scores, values, units, index=1, limit=2)
    assert [row["channel"] for row in top] == ["c", "a"]
    assert top[0]["z"] == -5.0
    assert top[0]["value"] == 14.0
    assert top[0]["unit"] == "mm/s"


def test_asset_payload_falls_back_to_channel_with_data() -> None:
    payload = _fake_dashboard().asset_payload("PUMP-X", window=3)
    assert payload["channel"] == "suction_pressure_kpa"
    assert payload["values"] == [32.0, 33.0, 34.0]
    assert payload["cursor"] == 4
    assert payload["window"] == 3
    assert payload["unit"] == "kPa(g)"


def test_asset_payload_keeps_explicit_empty_channel() -> None:
    payload = _fake_dashboard().asset_payload(
        "PUMP-X", channel="vibration_rms_mm_s", window=3,
    )
    assert payload["channel"] == "vibration_rms_mm_s"
    assert all(math.isnan(value) for value in payload["values"])


if __name__ == "__main__":
    for function in (
        test_json_safe_handles_missing_and_numpy,
        test_status_for_covers_all_states,
        test_top_deviations_sorts_by_absolute_z,
        test_asset_payload_falls_back_to_channel_with_data,
        test_asset_payload_keeps_explicit_empty_channel,
    ):
        function()
        print(f"PASS {function.__name__}")
