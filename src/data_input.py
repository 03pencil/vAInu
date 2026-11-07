"""Data input helpers for the vAInu pump-sensor project.

Responsibility: load the synthetic pump benchmark telemetry and split it
into the channels of interest (pressure, temperature, ...). No analysis
happens here.
"""
from __future__ import annotations

import pandas as pd

from .config import get_channels, get_data_dir


def load_telemetry(path: str | None = None) -> pd.DataFrame:
    """Load telemetry as a single DataFrame.

    TODO: read parquet partitions under telemetry/ and concat.
    """
    if path is None:
        path = get_data_dir()
    # Placeholder for now.
    return pd.DataFrame()


def split_channels(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a telemetry frame into per-channel frames.

    If `df` has a `channel` column, each entry is filtered to that channel.
    Otherwise the same frame is returned for every configured channel.
    """
    channels = get_channels()
    if "channel" in df.columns:
        return {c: df[df["channel"] == c] for c in channels}
    return {c: df for c in channels}