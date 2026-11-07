"""Data input helpers for the vAInu pump-sensor project.

Responsibility: load the synthetic pump benchmark telemetry (bundled tier
under data/) and expose helpers to split it by asset and channel, plus
the supporting label tables (assets). No analysis happens here.

Everything under data/ is read-only (see skill_data.md): this module only
reads from it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import get_channels, get_data_dir

# quality_flags bit definitions (data_dictionary.csv / skill_data.md).
FLAG_COMM_LOSS = 1
FLAG_OUT_OF_RANGE = 2
FLAG_STALE = 4
FLAG_BAD_SENSOR_STATUS = 8
FLAG_STARTUP_INHIBIT = 16

FLAG_NAMES: dict[int, str] = {
    FLAG_COMM_LOSS: "COMM_LOSS",
    FLAG_OUT_OF_RANGE: "OUT_OF_RANGE",
    FLAG_STALE: "STALE",
    FLAG_BAD_SENSOR_STATUS: "BAD_SENSOR_STATUS",
    FLAG_STARTUP_INHIBIT: "STARTUP_INHIBIT",
}

# Columns kept alongside a channel when splitting a wide-format frame.
_ID_COLUMNS = (
    "asset_id",
    "timestamp_utc",
    "operating_mode",
    "quality_flags",
    "sensor_source",
    "sample_interval_s",
)

_TELEMETRY_FILENAMES = ("telemetry.csv.gz", "telemetry.csv")
_PARQUET_GLOB = "telemetry/asset_id=*/day=*/part-*.parquet"


def _resolve_telemetry_file(path: str | None = None) -> Path:
    """Locate the telemetry file for a tier directory or explicit path."""
    target = Path(path) if path is not None else Path(get_data_dir())
    if not target.exists():
        raise FileNotFoundError(f"Telemetry path not found: {target}")
    if target.is_file():
        return target
    for name in _TELEMETRY_FILENAMES:
        candidate = target / name
        if candidate.is_file():
            return candidate
    if _parquet_parts(target):
        return target
    raise FileNotFoundError(
        f"No telemetry.csv.gz, telemetry.csv or telemetry/ parquet partitions "
        f"under {target}. Check [paths] data_dir in config.toml."
    )


def _parquet_parts(tier_dir: Path) -> list[Path]:
    """Partitioned parquet telemetry files (full tier), sorted by asset and day."""
    return sorted(tier_dir.glob(_PARQUET_GLOB))


def _read_parquet_partitions(tier_dir: Path) -> pd.DataFrame:
    """Concatenate per-asset/per-day parquet partitions into one wide frame.

    The asset id lives in the ``asset_id=`` folder name, not in the files, so
    it is added here. Numeric columns are widened to float64 so the full tier
    matches the CSV starter tier's dtypes and downstream math.
    """
    frames = []
    for part in _parquet_parts(tier_dir):
        asset_id = part.parents[1].name.removeprefix("asset_id=")
        frame = pd.read_parquet(part)
        frame.insert(0, "asset_id", asset_id)
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    float_cols = df.select_dtypes(include="float32").columns
    df[float_cols] = df[float_cols].astype("float64")
    df["operating_mode"] = df["operating_mode"].astype(str)
    return df


# Asset metadata columns joined onto telemetry when join_assets=True.
_ASSET_JOIN_COLUMNS = ("profile", "control", "instrumentation_tier")


def load_telemetry(path: str | None = None, join_assets: bool = False) -> pd.DataFrame:
    """Load telemetry as one DataFrame, sorted by asset then timestamp.

    `path` may be a tier directory (containing telemetry.csv.gz/.csv) or
    an explicit file. Nullable channels stay NaN (never filled), and rows
    are never dropped here: quality_flags carries the reason for any
    missing/odd values so downstream code can decide.

    With `join_assets=True`, nameplate columns from assets.csv (profile,
    control, instrumentation_tier) are merged onto every row, keyed by
    asset_id — used e.g. for fate/fleet-level fallback statistics.
    """
    file = _resolve_telemetry_file(path)
    if file.is_dir():
        tier_dir = file
        df = _read_parquet_partitions(tier_dir)
    else:
        tier_dir = file.parent
        df = pd.read_csv(file)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["quality_flags"] = (
        pd.to_numeric(df["quality_flags"], errors="coerce").fillna(0).astype("int16")
    )
    if join_assets:
        assets = load_assets(str(tier_dir / "assets.csv"))
        join_cols = [c for c in _ASSET_JOIN_COLUMNS if c in assets.columns]
        df = df.merge(assets[["asset_id"] + join_cols], on="asset_id", how="left")
    return df.sort_values(["asset_id", "timestamp_utc"]).reset_index(drop=True)


def channel_columns(df: pd.DataFrame, channels: "list[str] | None" = None) -> list[str]:
    """Return the sensor channels that exist as columns in `df`.

    Channels with no data at all (e.g. flow on T0 legacy pumps) simply do
    not appear; per-asset availability is handled by `asset_channels`.
    """
    wanted = channels if channels is not None else get_channels()
    return [c for c in wanted if c in df.columns]


def split_channels(df: pd.DataFrame, channels: "list[str] | None" = None) -> dict[str, pd.DataFrame]:
    """Split a wide-format telemetry frame into per-channel frames.

    Each returned frame carries the id columns plus the one channel,
    with rows where the channel is NULL removed (sparse retrofit
    channels produce much shorter frames).
    """
    id_cols = [c for c in _ID_COLUMNS if c in df.columns]
    frames: dict[str, pd.DataFrame] = {}
    for channel in channel_columns(df, channels):
        frames[channel] = df[id_cols + [channel]].dropna(subset=[channel]).reset_index(drop=True)
    return frames


def split_assets(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split telemetry into one frame per asset (PUMP-01 ... PUMP-12)."""
    return {asset_id: asset_df.reset_index(drop=True)
            for asset_id, asset_df in df.groupby("asset_id", sort=True)}


def load_assets(path: str | None = None) -> pd.DataFrame:
    """Load the asset metadata table (nameplates, limits, splits)."""
    if path is None:
        path = Path(get_data_dir()) / "assets.csv"
    return pd.read_csv(path)


def load_channel_units(path: str | None = None) -> dict[str, str]:
    """Map telemetry channel names to their units from data_dictionary.csv.

    Units are presentation metadata (e.g. "kPa(g)", "mm/s"); an empty dict
    is returned when the dictionary is absent so callers can fall back to
    a neutral "-" label.
    """
    if path is None:
        path = Path(get_data_dir()) / "data_dictionary.csv"
    dictionary = Path(path)
    if not dictionary.is_file():
        return {}
    rows = pd.read_csv(dictionary)
    telemetry = rows.loc[rows["table"] == "telemetry"]
    units: dict[str, str] = {}
    for row in telemetry.itertuples(index=False):
        unit = getattr(row, "unit", "-")
        units[str(row.column)] = "-" if pd.isna(unit) else str(unit)
    return units


def asset_channels(asset_id: str, assets: "pd.DataFrame | None" = None) -> list[str]:
    """Channels instrumented on `asset_id` (from assets.channels_available)."""
    if assets is None:
        assets = load_assets()
    rows = assets.loc[assets["asset_id"] == asset_id]
    if rows.empty:
        return []
    raw = str(rows.iloc[0]["channels_available"])
    return [c for c in raw.split("|") if c]


def has_flag(df: pd.DataFrame, bit: int) -> pd.Series:
    """True where quality_flags contains `bit` (see FLAG_NAMES)."""
    return (df["quality_flags"].astype(int) & int(bit)) != 0


def flag_counts(df: pd.DataFrame) -> pd.Series:
    """Per-row number of set quality-flag bits (0 = clean row)."""
    flags = df["quality_flags"].to_numpy(dtype=int)
    counts = np.zeros(len(flags), dtype=int)
    for bit in FLAG_NAMES:
        counts += ((flags & bit) != 0).astype(int)
    return pd.Series(counts, index=df.index, name="flag_count")
