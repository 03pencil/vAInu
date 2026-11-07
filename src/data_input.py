"""Data input helpers for the vAInu pump-sensor project.

Responsibility: load the synthetic pump benchmark telemetry and split it
into the channels of interest (pressure, temperature, ...). No analysis
happens here.
"""
from __future__ import annotations

import pandas as pd

# Path to the bundled test dataset (relative to project root).
DEFAULT_DATA_DIR = "data/full"


def load_telemetry(path: str = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Load telemetry as a single DataFrame.

    TODO: read parquet partitions under telemetry/ and concat.
    """
    # Placeholder for now.
    return pd.DataFrame()


def split_channels(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a telemetry frame into per-channel frames.

    Keys are channel names such as 'pressure', 'temperature', 'vibration'.
    """
    channels = ["pressure", "temperature", "vibration", "flow"]
    return {c: df[df.get("channel") == c] if "channel" in df else df for c in channels}