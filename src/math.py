"""Algorithmic / statistical computations for vAInu.

Pure functions over pandas DataFrames. Math is intentionally minimal
(stubs) for now; fill in during phases 2-4.
"""
from __future__ import annotations

import pandas as pd


def basic_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-channel descriptive statistics (empty-safe)."""
    if df.empty:
        return pd.DataFrame()
    return df.describe()


def rolling_trend(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Compute a rolling mean per channel (placeholder)."""
    return df.rolling(window=window).mean()