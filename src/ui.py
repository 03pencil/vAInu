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