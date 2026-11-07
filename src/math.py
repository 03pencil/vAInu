"""Algorithmic / statistical computations for vAInu.

Pure numpy/pandas functions. Phase-1 focus: robust (median/MAD)
statistics, modified z-scores and group-aware smoothing. Everything is
NaN-safe: sparse channels (e.g. bearing temp every 300 s on wireless
retrofit sensors) are masked, never filled or dropped globally.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data_input import channel_columns

# Robust-statistics constants: MAD of a normal sample relates to sigma as
# sigma ~ MAD_TO_SIGMA * MAD, and the modified z-score scale constant is
# Z_CONSTANT = 0.6745 (i.e. |z| > 3.5 ~ 3-sigma convention).
MAD_TO_SIGMA = 1.4826
Z_CONSTANT = 0.6745


def basic_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-channel descriptive statistics (empty-safe)."""
    if df.empty:
        return pd.DataFrame()
    return df.describe()


def robust_stats(
    df: pd.DataFrame,
    channels: "list[str] | None" = None,
    by: "tuple[str, ...]" = ("asset_id", "operating_mode"),
    min_count: int = 0,
) -> dict[str, pd.DataFrame]:
    """Per-group median and MAD per channel (NaN-safe).

    Returns {"median": DataFrame, "mad": DataFrame}, both indexed by the
    `by` keys with one column per channel. Cells from groups with fewer
    than `min_count` observations or no data at all are NaN (no data ->
    no statistics -> no z-scores for those channels).
    """
    if channels is None:
        channels = channel_columns(df)
    keys = list(by)
    counts = df.groupby(keys)[channels].count()
    median = df.groupby(keys)[channels].median()
    mad = df.groupby(keys)[channels].agg(_mad_of_series)
    if min_count > 0:
        enough = counts >= min_count
        median = median.where(enough)
        mad = mad.where(enough)
    return {"median": median, "mad": mad}


def merged_stats(
    df: pd.DataFrame,
    channels: "list[str] | None" = None,
    min_count: int = 30,
) -> dict[str, pd.DataFrame]:
    """Robust envelope with fleet-level fallback.

    Primary statistics are per (asset_id, operating_mode); any cell with
    too little data (or none) for the asset is filled from the SAME
    profile's (profile, operating_mode) statistics — an under-instrumented
    or heavily fault-labeled pump inherits the behaviour of sister pumps
    of the same profile (e.g. PUMP-08 inherits from PUMP-01, both
    SHIP_SW_COOLING). Requires a `profile` column on `df`
    (load_telemetry(join_assets=True) provides it).
    """
    if channels is None:
        channels = channel_columns(df)
    stats = robust_stats(df, channels, min_count=min_count)
    if "profile" not in df.columns:
        return stats
    fallback = robust_stats(
        df.loc[df["profile"].notna()], channels,
        by=("profile", "operating_mode"), min_count=min_count,
    )
    asset_profiles = (
        df[["asset_id", "profile"]].drop_duplicates().set_index("asset_id")["profile"]
    )
    added = []
    for (profile, mode), fb_med in fallback["median"].iterrows():
        fb_mad = fallback["mad"].loc[(profile, mode)]
        for asset_id, asset_profile in asset_profiles.items():
            if asset_profile != profile:
                continue
            key = (asset_id, mode)
            if key in stats["median"].index:
                missing = stats["median"].loc[key].isna()
                if not missing.any():
                    continue
                stats["median"].loc[key, missing] = fb_med[missing]
                stats["mad"].loc[key, missing] = fb_mad[missing]
            else:
                # Asset has no rows of its own here (e.g. fully fault-labeled
                # window): synthesize the envelope row from the profile.
                added.append(pd.DataFrame({"median": [fb_med], "mad": [fb_mad]},
                                          index=pd.MultiIndex.from_tuples(
                                              [(key[0], key[1])],
                                              names=["asset_id", "operating_mode"])))
    if added:
        med_extra = pd.concat([a["median"] for a in added])
        mad_extra = pd.concat([a["mad"] for a in added])
        stats["median"] = pd.concat([stats["median"], med_extra]).sort_index()
        stats["mad"] = pd.concat([stats["mad"], mad_extra]).sort_index()
    return stats


def _mad_of_series(series: pd.Series) -> float:
    """Median absolute deviation of a Series, NaN-safe."""
    values = series.to_numpy(dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return np.nan
    return float(np.median(np.abs(values - np.median(values))))


def modified_zscores(
    df: pd.DataFrame,
    stats: dict[str, pd.DataFrame],
    channels: "list[str] | None" = None,
) -> pd.DataFrame:
    """Per-row modified z-scores against the envelope in `stats`.

    Rows are matched to envelope statistics by the group keys the stats
    were computed with (asset_id + operating_mode by default). A constant
    channel (MAD = 0) yields NaN for that channel: unknown spread means
    unknown deviation. Output columns are named `z_<channel>`.
    """
    if channels is None:
        channels = list(stats["median"].columns)
    envelope_keys = stats["median"].index
    keys = pd.MultiIndex.from_frame(
        df[[column for column in envelope_keys.names]]
    )
    positions = envelope_keys.get_indexer(keys)  # -1 = group missing from stats
    values = df[channels].to_numpy(dtype=float)
    median = np.full(values.shape, np.nan)
    mad = np.full_like(median, np.nan)
    valid = positions >= 0
    if valid.any():
        group_median = stats["median"].to_numpy()
        group_mad = stats["mad"].to_numpy()
        median[valid] = group_median[positions[valid]]
        mad[valid] = group_mad[positions[valid]]

    with np.errstate(divide="ignore", invalid="ignore"):
        z = Z_CONSTANT * (values - median) / mad
    safe = np.where((mad > 0) & valid[:, None], z, np.nan)
    z_frame = pd.DataFrame(safe, index=df.index, columns=[f"z_{c}" for c in channels])
    return z_frame


def group_rolled(
    frame: pd.DataFrame,
    window: int,
    by: "tuple[str, ...]" = ("asset_id",),
    min_periods: "int | None" = None,
    func: str = "mean",
) -> pd.DataFrame:
    """Apply a rolling aggregation inside each group, preserving rows.

    Keeps the original row count and index (unlike a plain resample), so
    the result aligns 1:1 with the input. Only numeric columns are
    rolled; the group-by key columns are re-attached unchanged so the
    output still identifies each group. Default min_periods = window/2
    so early rows still get a (noisy) value instead of NaN.
    """
    if min_periods is None:
        min_periods = max(2, window // 2)
    parts = []
    for key, part in frame.groupby(list(by), sort=False):
        numeric = part.select_dtypes(include="number")
        rolled = numeric.rolling(window=window, min_periods=min_periods).agg(func)
        if not isinstance(key, tuple):
            key = (key,)
        for column, value in zip(by, key):
            rolled[column] = value
        parts.append(rolled)
    return pd.concat(parts).sort_index()


def rolling_robust_z(
    df: pd.DataFrame,
    window: int = 60,
    channels: "list[str] | None" = None,
    by: "tuple[str, ...]" = ("asset_id",),
) -> pd.DataFrame:
    """Self-referential rolling z-scores (asset-adaptive envelope).

    Uses a trailing median/MAD over the last `window` samples per asset
    (10 s grid -> 60 samples = 10 min). Slower to react than the benign
    envelope in `modified_zscores` but needs no training data; slow
    drifts are invisible to it by construction.
    """
    if channels is None:
        channels = channel_columns(df)
    parts = []
    min_periods = max(2, window // 2)
    for _, part in df.groupby(list(by), sort=False):
        scores = {}
        for channel in channels:
            values = part[channel].astype(float)
            median = values.rolling(window=window, min_periods=min_periods).median()
            mad = (values - median).abs().rolling(window=window, min_periods=min_periods).median()
            scores[f"z_{channel}"] = Z_CONSTANT * (values - median) / mad.where(mad > 0)
        parts.append(pd.DataFrame(scores, index=part.index))
    return pd.concat(parts).sort_index()
