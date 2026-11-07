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

"""Trend forecast report (Layer 1 item 3).

Prints, per asset and limit-bearing channel, where the trailing drift
is heading and how long it takes to reach the alarm limit with the
uncertainty band: "vibration hits alarm in ~38 h [33-49]". Then joins
the last forecast at or before each labeled event's action deadline to
show what a long-scale prediction would have claimed.

Run: `.venv/bin/python scripts/trend_forecast.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.config import get_limits_config, get_trend_config
from src.data_input import load_assets, load_telemetry
from src.labels import load_events
from src.trend import (
    TREND_LIMIT,
    TREND_SLOPE,
    TREND_TTL,
    TREND_TTL_HIGH,
    TREND_TTL_LOW,
    TREND_VALUE,
    forecast_events_within,
    trend_forecast,
)

UNITS = {
    "vibration_rms_mm_s": "mm/s",
    "bearing_temp_c": "C",
    "motor_winding_temp_c": "C",
}
EVENT_COLUMNS = ("event", "asset_id", "fault_type", "channel",
                 "forecast_bin", "trend_time_to_limit_h",
                 "trend_slope_per_h", "action_deadline_utc")


def evaluate() -> None:
    cfg = get_trend_config()
    static_limits = get_limits_config()
    df = load_telemetry(join_assets=True)
    assets = load_assets()
    per_bin, latest = trend_forecast(df, assets, static_limits=static_limits)
    if not latest.empty:
        window_ends = assets[["asset_id", "window_end_utc"]].copy()
        window_ends["window_end_utc"] = pd.to_datetime(
            window_ends["window_end_utc"], utc=True)
        latest = latest.merge(window_ends, on="asset_id", how="left")
        since = latest["window_end_utc"] - pd.Timedelta(
            hours=float(cfg["trailing_hours"]))
        recent = latest[latest["bin_start"].notna() & (latest["bin_start"] >= since)]
    else:
        recent = latest
    rows = [{
        "asset": row["asset_id"],
        "channel": row["channel"],
        "value": f"{row[TREND_VALUE]:.2f} {UNITS.get(row['channel'], '')}".strip(),
        "heading": f"{row[TREND_SLOPE]:+.3f}/h",
        "limit": f"{row[TREND_LIMIT]:.1f}",
        "time_left": (f"~{row[TREND_TTL]:.1f} h "
                      f"[{row[TREND_TTL_LOW]:.1f} - {row[TREND_TTL_HIGH]:.1f}]"
                      if pd.notna(row[TREND_TTL]) else "moving away"),
    } for _, row in recent.iterrows()]
    table = pd.DataFrame(rows)
    with pd.option_context("display.width", 160, "display.max_columns", 10):
        print("Latest time-to-limit forecast per asset/channel "
              f"({cfg['trailing_hours']:.0f} h trailing drift, "
              f"{cfg['bin_minutes']} min bins):")
        if table.empty:
            print("  (no limit-bearing channel had a fittable drift)")
        else:
            print(table.sort_values(["asset", "channel"]).to_string(index=False))

    joined = forecast_events_within(per_bin, load_events())
    if not joined.empty:
        print("\nLast forecast at or before each event's action deadline:")
        print(joined[["event", "fault_type", "channel", TREND_TTL,
                      TREND_SLOPE]].to_string(index=False))


if __name__ == "__main__":
    evaluate()
