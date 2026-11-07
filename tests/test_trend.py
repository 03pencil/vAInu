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

"""Tests for src.trend — runnable via `.venv/bin/python tests/test_trend.py`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.trend import (
    TREND_FIT,
    TREND_LIMIT,
    TREND_SLOPE,
    TREND_TTL,
    TREND_TTL_HIGH,
    TREND_TTL_LOW,
    TREND_VALUE,
    binned_medians,
    channel_limit,
    default_trend_channels,
    trend_forecast,
)

CFG = {"bin_minutes": 60, "trailing_hours": 12.0,
       "min_bin_count": 2, "min_fit_points": 6}
CHANNEL = "vibration_rms_mm_s"
LIMITS = {CHANNEL: 10.0}


def _binned(values: np.ndarray, asset: str = "PUMP-TEST") -> pd.DataFrame:
    base = pd.Timestamp("2026-01-01T00:00:00Z")
    return pd.DataFrame({
        "asset_id": asset,
        "bin_start": [base + pd.Timedelta(hours=i) for i in range(len(values))],
        CHANNEL: np.asarray(values, dtype=float),
        f"count_{CHANNEL}": np.full(len(values), 2),
    })


def _assets_row(asset: str = "PUMP-TEST") -> pd.DataFrame:
    # Minimal asset row: no vibration_alarm_mm_s, so limits resolve from
    # static_limits (assets.csv overrides static limits by design).
    return pd.DataFrame([{"asset_id": asset}])


def test_trend_crossing_math() -> None:
    # y = 20 - 0.05*i: fitted last value 14.05, limit 10, slope -0.05 ->
    # crossing in (14.05 - 10) / 0.05 = 81 h.
    values = 20.0 - 0.05 * np.arange(120.0)
    per_bin, latest = trend_forecast(
        _binned(values), _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    row = latest.iloc[0]
    assert abs(row[TREND_SLOPE] + 0.05) < 1e-9
    assert abs(row[TREND_TTL] - 81.0) < 1e-6


def test_band_brackets_horizon() -> None:
    rng = np.random.default_rng(7)
    values = 20.0 - 0.05 * np.arange(120.0) + rng.normal(0.0, 0.2, 120)
    per_bin, latest = trend_forecast(
        _binned(values), _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    row = latest.iloc[0]
    assert row[TREND_TTL_LOW] <= row[TREND_TTL] <= row[TREND_TTL_HIGH]


def test_trend_away_from_limit_is_nan() -> None:
    # Rising series already above the limit: fits exist but the trend
    # moves up and away -> never a future crossing.
    values = 12.0 + 0.05 * np.arange(120.0)
    per_bin, _ = trend_forecast(
        _binned(values), _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    assert per_bin[TREND_TTL].isna().all()
    # Falling series that already passed the limit: late fits sit below
    # the limit heading down -> no further crossing either.
    values = 20.0 - 0.3 * np.arange(120.0)
    per_bin, _ = trend_forecast(
        _binned(values), _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    late_fit = per_bin[per_bin[TREND_FIT] < LIMITS[CHANNEL]].dropna(subset=[TREND_SLOPE])
    assert not late_fit.empty
    assert late_fit[TREND_TTL].isna().all()


def test_nan_gaps_and_unfittable_windows() -> None:
    values = 20.0 - 0.05 * np.arange(120.0)
    values[30:60] = np.nan  # gap; later windows still hold >= 6 valid bins
    values[:3] = np.nan
    per_bin, latest = trend_forecast(
        _binned(values), _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    assert not per_bin.empty
    assert abs(latest.iloc[0][TREND_TTL] - 81.0) < 0.05
    # Only 4 valid bins left in total: no window reaches min_fit_points.
    starved = values.copy()
    starved[:116] = np.nan
    per_bin, latest = trend_forecast(
        _binned(starved), _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    assert per_bin.empty and latest.empty


def test_bin_count_gate_and_binned_medians() -> None:
    # T1-style sparse channel: a bin with < min_bin_count samples is
    # invalid, so nothing (except one lone bin) can be fit.
    frame = _binned(np.full(40, 1.2))
    frame[f"count_{CHANNEL}"] = [1] * 39 + [2]
    per_bin, _ = trend_forecast(
        frame, _assets_row(), channels=[CHANNEL],
        cfg=CFG, static_limits=LIMITS,
    )
    assert per_bin.empty
    # binned_medians: RUNNING rows only; B keeps its own bin.
    df = pd.DataFrame({
        "asset_id": ["A", "A", "A", "B"],
        "timestamp_utc": pd.to_datetime(
            ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z",
             "2026-01-01T00:07:00Z", "2026-01-01T00:01:00Z"], utc=True),
        "operating_mode": ["RUNNING", "RUNNING", "STOPPED", "RUNNING"],
        CHANNEL: [1.0, 3.0, 99.0, 7.0],
    })
    binned = binned_medians(df, [CHANNEL], bin_minutes=10)
    assert set(binned["asset_id"]) == {"A", "B"}
    a_row = binned[binned["asset_id"] == "A"].iloc[0]
    assert abs(a_row[CHANNEL] - 2.0) < 1e-9
    assert int(a_row[f"count_{CHANNEL}"]) == 2
    assert binned[binned["asset_id"] == "B"][CHANNEL].iloc[0] == 7.0


def test_channel_limit_lookup_real_assets() -> None:
    assets = pd.read_csv(
        Path(__file__).resolve().parents[1] / "data" / "starter" / "assets.csv")
    from src.config import get_limits_config
    limits = get_limits_config()
    assert limits.get("bearing_temp_c") == 85.0
    p4 = assets.loc[assets["asset_id"] == "PUMP-04"].iloc[0]
    # Vibration from assets.csv (ISO 10816-7 category II alarm).
    assert channel_limit(CHANNEL, p4, limits) == 6.4
    assert channel_limit("bearing_temp_c", p4, limits) == 85.0
    # Empty static map -> NaN even for a known limit channel.
    assert np.isnan(channel_limit("motor_winding_temp_c", p4, {}))
    # Static limit applies independent of instrumentation; whether the
    # asset actually carries the channel is a data question handled by
    # default_trend_channels / binned_medians.
    p1 = assets.loc[assets["asset_id"] == "PUMP-01"].iloc[0]
    assert channel_limit("motor_winding_temp_c", p1, limits) == 140.0


def test_forecast_on_real_data() -> None:
    from src.data_input import load_assets, load_telemetry
    df = load_telemetry(join_assets=True)
    assets = load_assets()
    channels = default_trend_channels(df)
    assert CHANNEL in channels
    binned = binned_medians(df, channels, bin_minutes=10)
    per_bin, latest = trend_forecast(binned, assets, channels=channels)
    assert not per_bin.empty and not latest.empty
    wear = per_bin[(per_bin["asset_id"] == "PUMP-04")
                   & (per_bin["channel"] == CHANNEL)]
    assert (wear[TREND_SLOPE] > 0.02).any()  # bearing wear ramps vibration
    valid_ttl = wear[TREND_TTL].dropna()
    assert not valid_ttl.empty and valid_ttl.between(0.0, 10_000.0).any()
    row = latest[(latest["asset_id"] == "PUMP-04")
                 & (latest["channel"] == CHANNEL)].iloc[0]
    assert row[TREND_LIMIT] == 6.4  # category II alarm from assets.csv
    assert row[TREND_VALUE] >= 0.0  # mm/s scale, non-negative


if __name__ == "__main__":
    for fn in (test_trend_crossing_math,
               test_band_brackets_horizon,
               test_trend_away_from_limit_is_nan,
               test_nan_gaps_and_unfittable_windows,
               test_bin_count_gate_and_binned_medians,
               test_channel_limit_lookup_real_assets,
               test_forecast_on_real_data):
        fn()
        print(f"PASS {fn.__name__}")
