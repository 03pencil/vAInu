"""Trailing-trend extrapolation -> time-to-limit (Layer 1, item 3).

For every asset and limit-bearing channel, fits a robust linear drift
over a trailing window and solves where the trend first crosses the
channel's alarm limit ("vibration hits alarm in ~38 h"). The forecast
runs on a short-interval grid of RUNNING-row medians (default 10 min,
matching the benchmark detectability grid); fitting per telemetry row
would be far too large and adds nothing against the 10-min clock.

Limits come from two places:
- `assets.csv` per-asset columns (vibration alarm via ISO 10816-7
  category), see VIBRATION_LIMIT_COLUMNS,
- static channel limits from config [limits] (simulation_assumptions):
  bearing 85 C, winding 140 C.

Pure numpy/pandas (stack rule). NaN-safe: invalid bins and windows
without enough valid bins stay NaN and never stop the run.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import get_limits_config, get_trend_config

# Per-bin trend feature columns added by trend_forecast().
TREND_VALUE = "trend_value"
TREND_FIT = "trend_fit_value"
TREND_SLOPE = "trend_slope_per_h"
TREND_TTL = "trend_time_to_limit_h"
TREND_TTL_LOW = "trend_time_to_limit_low_h"
TREND_TTL_HIGH = "trend_time_to_limit_high_h"
TREND_LIMIT = "trend_limit_value"

TREND_KEY_COLUMNS = ("asset_id", "bin_start", "channel")

# Channels whose limit lives in an assets.csv column instead of config:
# channel -> alarm-limit column. (Trip limits are not projected yet; the
# alarm is the benchmark action deadline for vibration faults.)
VIBRATION_LIMIT_COLUMNS: dict[str, str] = {
    "vibration_rms_mm_s": "vibration_alarm_mm_s",
}

# Default channels to forecast: those with a conventional limit and a
# monotone failure story. Assets without the instrument are skipped.
DEFAULT_TREND_CHANNELS = (
    "vibration_rms_mm_s",
    "bearing_temp_c",
    "motor_winding_temp_c",
)

# Outlier rejection inside a fit window: residuals beyond
# REJECT_SIGMA * (1.4826 MAD) are dropped once, then the fit repeats.
REJECT_SIGMA = 3.0
# A fit needs at least this fraction of its window valid to be trusted.
MIN_FIT_FRACTION = 0.6


def default_trend_channels(df: pd.DataFrame) -> list[str]:
    """Limit-bearing channels that actually carry data in `df`."""
    return [c for c in DEFAULT_TREND_CHANNELS
            if c in df.columns and df[c].notna().any()]


def _mad_sigma(values: np.ndarray) -> float:
    """1.4826-scaled MAD of finite values (0.0 when degenerate)."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    mad = float(np.median(np.abs(finite - np.median(finite))))
    return 1.4826 * mad


def _robust_fit(
    xs: np.ndarray, ys: np.ndarray,
) -> tuple[float, float, float]:
    """Linear fit with one MAD outlier rejection pass.

    Returns (slope, intercept, residual_sigma). Slope is per x-unit, so
    per hour when `xs` are hours.
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    coef = np.polyfit(xs, ys, 1)
    residual = ys - np.polyval(coef, xs)
    sigma = _mad_sigma(residual)
    keep = np.ones(xs.size, dtype=bool)
    if sigma > 0:
        keep = np.abs(residual) <= REJECT_SIGMA * sigma
    # Only refit when the rejection actually trimmed something useful.
    if keep.sum() < xs.size and keep.sum() >= max(3, int(MIN_FIT_FRACTION * xs.size)):
        coef = np.polyfit(xs[keep], ys[keep], 1)
        residual = ys - np.polyval(coef, xs)
    dof = max(int(keep.sum()) - 2, 1)
    residual_sigma = float(np.sqrt(np.sum(residual[keep] ** 2) / dof))
    return float(coef[0]), float(coef[1]), residual_sigma


def binned_medians(
    df: pd.DataFrame, channels: list[str], bin_minutes: int = 10,
) -> pd.DataFrame:
    """Per asset x bin medians and counts of RUNNING rows.

    Returns a frame with asset_id, bin_start, one column per channel and
    one count_* column per channel (a bin's validity gate, e.g. T1
    wireless channels update every 300 s).
    """
    running = df.loc[df["operating_mode"] == "RUNNING"]
    if running.empty or not channels:
        return pd.DataFrame(
            columns=["asset_id", "bin_start", *channels,
                     *[f"count_{c}" for c in channels]],
        )
    bins = running["timestamp_utc"].dt.floor(f"{bin_minutes}min")
    keys = pd.concat(
        [running["asset_id"].reset_index(drop=True),
         bins.rename("bin_start").reset_index(drop=True)],
        axis=1,
    )
    values = running[list(channels)].reset_index(drop=True)
    joined = pd.concat([keys, values], axis=1)
    grouped = joined.groupby(["asset_id", "bin_start"], sort=True)
    medians = grouped[list(channels)].median().reset_index()
    counts = grouped[list(channels)].count().reset_index()
    counts.columns = ["asset_id", "bin_start"] + [f"count_{c}" for c in channels]
    return medians.merge(counts, on=["asset_id", "bin_start"], how="left")


def _channel_limit(value: "pd.Series | float") -> float:
    """Assets/settings cell -> positive float limit, else NaN."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out if out > 0 else np.nan


def channel_limit(
    channel: str, assets_row: pd.Series, static_limits: dict,
) -> float:
    """Alarm limit for `channel` on one asset.

    Vibration limits come from the assets.csv column mapped in
    VIBRATION_LIMIT_COLUMNS, falling back to config [limits] when the
    assets cell is missing or NaN. NaN from both = no limit.
    """
    column = VIBRATION_LIMIT_COLUMNS.get(channel)
    if column is not None:
        asset_limit = _channel_limit(assets_row.get(column, np.nan))
        if np.isfinite(asset_limit):
            return asset_limit
    return _channel_limit(static_limits.get(channel, np.nan))


def _time_to_limit(
    fit_value: float, slope: float, slope_stderr: float, limit: float,
) -> dict[str, float]:
    """Solve crossing of `limit` for a linear trend, with a band.

    The band perturbs the slope by +/- 2 stderr and keeps variants that
    still head toward the limit. Returns NaN where the fitted value is
    already beyond the limit or the trend moves away from it.
    """
    toward = np.sign(limit - fit_value)
    time_to_limit = {"trend_time_to_limit_h": np.nan,
                     "trend_time_to_limit_low_h": np.nan,
                     "trend_time_to_limit_high_h": np.nan}
    if not np.isfinite(toward) or toward == 0:
        return time_to_limit
    if not np.isfinite(slope) or toward * slope <= 0:
        return time_to_limit
    horizon = (limit - fit_value) / slope
    if not np.isfinite(horizon) or horizon < 0:
        return time_to_limit
    variants = [horizon]
    for delta in (-2.0 * slope_stderr, 2.0 * slope_stderr):
        perturbed = slope + delta
        if np.isfinite(perturbed) and toward * perturbed > 0:
            variants.append((limit - fit_value) / perturbed)
    time_to_limit[TREND_TTL] = float(horizon)
    time_to_limit[TREND_TTL_LOW] = float(min(variants))
    time_to_limit[TREND_TTL_HIGH] = float(max(variants))
    return time_to_limit


def trend_forecast(
    df: pd.DataFrame,
    assets: pd.DataFrame,
    channels: "list[str] | None" = None,
    cfg: "dict | None" = None,
    static_limits: "dict | None" = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trailing-drift extrapolation -> time-to-limit per asset x channel.

    `df` is raw telemetry or already-binned medians (binned_medians
    output gives counts; raw input rows count as one sample per bin).
    Returns (per_bin, latest): the full per-bin forecast series and the
    last fit per (asset, channel) sorted by time-to-limit.

    Bin validity: at least `min_bin_count` samples per bin; a fit needs
    at least `min_fit_points` valid bins inside `trailing_hours`.
    """
    cfg = cfg if cfg is not None else get_trend_config()
    static_limits = static_limits if static_limits is not None else get_limits_config()

    bin_minutes = int(cfg["bin_minutes"])
    trailing_bins = max(2, int(round(float(cfg["trailing_hours"]) * 60.0 / bin_minutes)))
    min_bin_count = int(cfg["min_bin_count"])
    min_fit_points = max(3, int(cfg["min_fit_points"]))

    channels = list(channels) if channels is not None else default_trend_channels(df)
    binned = df if "bin_start" in df.columns else binned_medians(
        df, [c for c in channels if c in df.columns], bin_minutes,
    )
    rows: list[dict] = []
    for asset_id, part in binned.groupby("asset_id", sort=True):
        candidates = assets.loc[assets["asset_id"] == asset_id]
        if candidates.empty:
            continue
        params = candidates.iloc[0]
        xs = ((part["bin_start"] - part["bin_start"].iloc[0])
              .dt.total_seconds() / 3600.0).to_numpy(dtype=float)
        for channel in channels:
            limit = channel_limit(channel, params, static_limits)
            if not np.isfinite(limit) or channel not in part.columns:
                continue
            values = part[channel].to_numpy(dtype=float).copy()
            count_column = f"count_{channel}"
            if count_column in part.columns:
                values[part[count_column].to_numpy(dtype=float) < min_bin_count] = np.nan
            for i in range(len(part)):
                if not np.isfinite(values[i]):
                    continue
                lo = max(0, i - trailing_bins + 1)
                ys_window = values[lo:i + 1]
                xs_window = xs[lo:i + 1]
                valid = np.isfinite(ys_window)
                if int(valid.sum()) < min_fit_points:
                    continue
                slope, intercept, sigma = _robust_fit(
                    xs_window[valid], ys_window[valid],
                )
                if not np.isfinite(slope):
                    continue
                fit_last = intercept + slope * xs_window[-1]
                ttl = _time_to_limit(fit_last, slope, sigma / max(
                    np.sqrt(np.sum((xs_window[valid] - xs_window[valid].mean()) ** 2)), 1e-9,
                ), limit)
                rows.append({
                    "asset_id": asset_id,
                    "bin_start": part["bin_start"].iloc[i],
                    "channel": channel,
                    TREND_LIMIT: limit,
                    TREND_VALUE: float(values[i]),
                    TREND_FIT: float(fit_last),
                    TREND_SLOPE: float(slope),
                    **ttl,
                })
    per_bin = pd.DataFrame(rows)
    if per_bin.empty:
        latest = per_bin
    else:
        fitted = per_bin.dropna(subset=[TREND_SLOPE])
        latest = (
            fitted.sort_values("bin_start")
            .groupby(["asset_id", "channel"], as_index=False, sort=True)
            .tail(1)
            .reset_index(drop=True)
        )
    return per_bin, latest


def forecast_events_within(
    per_bin: pd.DataFrame, events: pd.DataFrame, deadline_column: str = "action_deadline_utc",
) -> pd.DataFrame:
    """Join per-bin forecasts against labeled events.

    For every observable event with an alarm-limit-bearing channel in
    its evidence list, take the last forecast at or before the event's
    action deadline on that asset/channel, so the report can compare
    "trend said X h left" with the deadline actually in Y h.
    """
    if per_bin.empty:
        return pd.DataFrame()
    rows = []
    for _, event in events.iterrows():
        if not bool(event.get("observable", True)):
            continue
        deadline = event.get(deadline_column)
        if pd.isna(deadline):
            continue
        scope = (
            (per_bin["asset_id"] == event["asset_id"])
            & (per_bin["bin_start"] <= deadline)
        )
        evidence = [c for c in str(event.get("evidence_channels", "")).split(",") if c]
        for channel in evidence:
            matches = per_bin.loc[scope & (per_bin["channel"] == channel)].tail(1)
            for _, row in matches.iterrows():
                rows.append({
                    "event": event["event_id"],
                    "asset_id": event["asset_id"],
                    "fault_type": event["fault_type"],
                    "channel": channel,
                    "forecast_bin": row["bin_start"],
                    TREND_TTL: row[TREND_TTL],
                    TREND_SLOPE: row[TREND_SLOPE],
                    deadline_column: deadline,
                })
    return pd.DataFrame(rows)
