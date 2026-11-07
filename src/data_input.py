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
    """Split a telemetry frame into per-channel frames using configured channels."""
    channels = get_channels()
    return {c: df[df.get("channel") == c] if "channel" in df else df for c in channels}