"""Alarm debouncing: ringing -> confirmed -> escalating (FAR surface).

Raw smoothed z alarms ring on every excursion; the benchmark penalizes
alert bursts and repeats, and benign false-alarm rate is a KPI with a
< 2 % target (to-do M4). A state becomes CONFIRMED only after the raw
alarm held for `confirm_samples` consecutive rows inside one asset
([debounce] confirm_samples; 3 min on the 10 s grid), and ESCALATED
after `escalate_samples`. Rows before the window fills stay RINGING.

Pure pandas. Group-consecutive: the alarm series must be in row order
per asset (load_telemetry guarantees asset,timestamp sort).
"""
from __future__ import annotations

import pandas as pd

from .config import get_debounce_config

STATE_QUIET = ""
STATE_RINGING = "ringing"
STATE_CONFIRMED = "confirmed"
STATE_ESCALATED = "escalated"


def _rolling_all(alarm: pd.Series, groups: pd.Series, window: int) -> pd.Series:
    """True where the last `window` rows in each group are all True."""
    frame = pd.concat(
        {"alarm": alarm.astype(bool).reset_index(drop=True),
         "group": groups.reset_index(drop=True)},
        axis=1,
    )
    confirmed = pd.Series(False, index=alarm.index)
    for _, part in frame.groupby("group", sort=False):
        if window <= 1:
            confirmed.loc[part.index] = part["alarm"].to_numpy()
            continue
        rolled = part["alarm"].rolling(window=window, min_periods=window).sum()
        confirmed.loc[part.index] = (rolled == window).to_numpy()
    return confirmed


def confirmed_mask(
    alarm: pd.Series, groups: pd.Series, window: "int | None" = None,
) -> pd.Series:
    """Boolean confirmed-alarm surface (the debounced detector output)."""
    if window is None:
        window = get_debounce_config()["confirm_samples"]
    return _rolling_all(alarm, groups, int(window))


def escalated_mask(
    alarm: pd.Series, groups: pd.Series, window: "int | None" = None,
) -> pd.Series:
    """Boolean escalated surface (alarm sustained much longer)."""
    if window is None:
        window = get_debounce_config()["escalate_samples"]
    return _rolling_all(alarm, groups, int(window))


def debounce_states(
    alarm: pd.Series, groups: pd.Series, cfg: "dict | None" = None,
) -> pd.Series:
    """Per-row state machine state from a raw alarm surface.

    Returns "", "ringing", "confirmed" or "escalated"; confirmed rows
    are the ones allowed to raise an alert.
    """
    if cfg is None:
        cfg = get_debounce_config()
    alarm_bool = alarm.astype(bool).reset_index(drop=True)
    confirmed = _rolling_all(alarm_bool, groups, int(cfg["confirm_samples"]))
    escalated = _rolling_all(alarm_bool, groups, int(cfg["escalate_samples"]))
    states = pd.Series(STATE_QUIET, index=alarm.index, dtype="string")
    states.loc[alarm_bool.to_numpy() & ~confirmed.to_numpy()] = STATE_RINGING
    states.loc[confirmed.to_numpy() & ~escalated.to_numpy()] = STATE_CONFIRMED
    states.loc[escalated.to_numpy()] = STATE_ESCALATED
    return states
