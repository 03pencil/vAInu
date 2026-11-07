"""Minimal UI / plotting helpers for vAInu (matplotlib)."""
from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd


def plot_channel(df: pd.DataFrame, channel: str) -> None:
    """Plot a single channel over time."""
    if channel in df.columns:
        df[channel].plot()
        plt.title(channel)
        plt.show()