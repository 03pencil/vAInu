"""Tests for src.debounce — runnable via `.venv/bin/python tests/test_debounce.py`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src.debounce import (
    STATE_CONFIRMED,
    STATE_ESCALATED,
    STATE_RINGING,
    confirmed_mask,
    debounce_states,
    escalated_mask,
)

CFG = {"confirm_samples": 3, "escalate_samples": 6}


def _group(n: int, asset: str = "PUMP-TEST") -> pd.Series:
    return pd.Series([asset] * n)


def test_blips_never_confirm() -> None:
    alarm = pd.Series([True, False, True, False, True, False] * 4)
    confirmed = confirmed_mask(alarm, _group(len(alarm)), window=3)
    assert not confirmed.any()  # 1-of-2 ringing cannot hold 3 rows


def test_sustained_alarm_confirms_after_window() -> None:
    # 2 quiet rows, then a run of 10 alarm rows, then quiet.
    alarm = pd.Series([False, False] + [True] * 10 + [False, False])
    confirmed = confirmed_mask(alarm, _group(len(alarm)), window=3)
    assert list(confirmed[:4]) == [False, False, False, False]  # window fills on 5th row
    assert confirmed.iloc[4:12].all()  # rows 2..11 are True -> filled from row 4
    assert not confirmed.iloc[12:].any()  # release when alarm stops


def test_groups_are_independent() -> None:
    alarm = pd.Series([False, True, True, True, True, True])
    groups = pd.Series(["A", "A", "A", "A", "B", "B"])
    confirmed = confirmed_mask(alarm, groups, window=3)
    # A confirms once three True rows have passed (index 3);
    # B has only two rows and never reaches the window.
    assert not bool(confirmed.iloc[2])
    assert bool(confirmed.iloc[3])
    assert not bool(confirmed.iloc[4])


def test_states_ring_confirm_escalate() -> None:
    alarm = pd.Series([False] * 2 + [True] * 10)
    states = debounce_states(alarm, _group(len(alarm)), cfg=CFG)
    assert states.iloc[0] == ""
    assert states.iloc[3] == STATE_RINGING  # alarm up, window not full
    assert states.iloc[4] == STATE_CONFIRMED
    assert states.iloc[7] == STATE_ESCALATED  # 6 alarm rows sustained
    assert set(states.unique()) <= {"", STATE_RINGING, STATE_CONFIRMED,
                                    STATE_ESCALATED}


def test_noise_bursts_collapse() -> None:
    # iid noisy alarms: requiring 2 consecutive rows collapses the
    # alerted share roughly p^2 -> debounce is a real FAR surface.
    rng = np.random.default_rng(11)
    noisy = pd.Series(rng.random(20000) < 0.2)
    groups = pd.Series(["A"] * len(noisy))
    raw_rate = noisy.mean()
    debounced_rate = confirmed_mask(noisy, groups, window=2).mean()
    assert debounced_rate < raw_rate / 4.0


def test_escalate_and_confirm_defaults_from_config() -> None:
    from src.config import get_debounce_config
    cfg = get_debounce_config()
    assert set(cfg) == {"confirm_samples", "escalate_samples"}
    alarm = pd.Series([True] * 10)
    esc = escalated_mask(alarm, _group(10), window=2)
    assert not bool(esc.iloc[0])  # window cannot fill on the first row
    assert esc.iloc[1:].all()
    assert confirmed_mask(alarm, _group(10), window=2).iloc[1:].all()


if __name__ == "__main__":
    for fn in (test_blips_never_confirm,
               test_sustained_alarm_confirms_after_window,
               test_groups_are_independent,
               test_states_ring_confirm_escalate,
               test_noise_bursts_collapse,
               test_escalate_and_confirm_defaults_from_config):
        fn()
        print(f"PASS {fn.__name__}")
