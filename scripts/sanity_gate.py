"""Sanity gate: do robust z-scores beat the benchmark's own detection clock?

Answers two questions on the labeled starter-tier telemetry:

1. FALSE-ALARM RATE: what fraction of confirmed-benign rows carry an alarm?
2. LEAD TIME: for each observable event with a conventional limit, how
   long before `action_deadline_utc` does our smoothed z-score alarm fire
   first (vs the benchmark's own `detectable_utc` = 3-sigma on a 10-min
   mean)?

Method (matches the benchmark's definition as closely as it is simple):
- envelope = robust median/MAD per asset x channel x operating_mode,
  computed from rows NOT labeled fault_* (benign + unknown),
- z-scores per row, smoothed with a group-aware rolling mean over
  `smoothing_window` samples (60 x 10 s = 10 min),
- alarm = smoothed |z| > z_threshold on any channel (RUNNING rows only,
  because rampsর/inrush pollute short modes),
- event detection = first alarmed (asset, timestamp) in [onset, deadline].

Run: `.venv/bin/python scripts/sanity_gate.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.config import (
    get_debounce_config,
    get_smoothing_window,
    get_z_threshold,
)
from src.data_input import channel_columns, load_assets, load_telemetry
from src.debounce import confirmed_mask
from src.labels import (
    FAULT_LABELS,
    LABEL_BENIGN,
    load_benign_windows,
    load_events,
    label_telemetry,
)
from src.math import group_rolled, merged_stats, modified_zscores, rolling_robust_z
from src.physics import PHYSICS_FEATURES, add_physics_features


def z_cols_of(channels: "list[str]") -> list[str]:
    """Map evidence channel names to their smoothed z columns."""
    return [f"z_{channel}" for channel in channels]


def evaluate() -> None:
    z_threshold = get_z_threshold()
    smoothing = get_smoothing_window()

    df = load_telemetry(join_assets=True)
    events = load_events()
    benign = load_benign_windows()
    df = label_telemetry(df, events, benign)
    # Layer 1 item 2: physics residuals as extra scoring channels; their
    # evidence may light up before any raw channel does.
    df = add_physics_features(df, load_assets())
    channels = channel_columns(df) + [c for c in PHYSICS_FEATURES if c in df.columns]

    # Envelope from everything that is not a labeled fault; profile-level
    # fallback fills gaps for heavily fault-labeled assets.
    envelope = merged_stats(df[~df["label"].isin(FAULT_LABELS)], channels)
    z = modified_zscores(df, envelope, channels)
    z_keyed = pd.concat([df[["asset_id"]], z], axis=1)  # key needed for grouping
    z_smooth = group_rolled(z_keyed, window=smoothing)  # asset_id + z_<channel>
    z_cols = [c for c in z_smooth.columns if c.startswith("z_")]

    # Surface 2: self-adaptive trailing z (for assets with no clean
    # envelope: whole window fault-labeled and alone in their profile).
    z_rolled = rolling_robust_z(df, window=smoothing, channels=channels)
    env_missing = z_smooth[z_cols].isna().all(axis=1)
    z_smooth.loc[env_missing, z_cols] = z_rolled.loc[env_missing, z_cols]

    # Alarm on RUNNING rows only (STARTING inrush / STOPPING ramps pollute).
    running = df["operating_mode"] == "RUNNING"
    alarmed_env = running & (z_smooth[z_cols].abs() > z_threshold).any(axis=1)
    alarmed_roll = running & (z_rolled.abs() > z_threshold).any(axis=1)
    alarmed = alarmed_env | alarmed_roll
    surface = pd.Series("", index=df.index, dtype="string")
    surface[alarmed_env] = "envelope"
    surface[alarmed_roll & ~alarmed_env] = "rolling"

    # Debounced surface: an alarm must hold for confirm_samples rows
    # inside one asset before it counts (FAR-reduction, to-do M4).
    confirm = int(get_debounce_config()["confirm_samples"])
    confirmed = (
        confirmed_mask(alarmed_env, df["asset_id"], confirm)
        | confirmed_mask(alarmed_roll, df["asset_id"], confirm)
    )

    # --- KPI 1: false-alarm rate on confirmed-benign rows -------------
    benign_rows = df["label"] == LABEL_BENIGN
    n_benign = int(benign_rows.sum())
    for name, mask in (("envelope+rolling", alarmed), ("envelope only", alarmed_env),
                       ("rolling only", alarmed_roll),
                       (f"debounced (confirmed >= {confirm} rows)", confirmed)):
        hits = int((mask & benign_rows).sum())
        print(f"KPI 1  benign false-alarm rate [{name}]: {hits / max(n_benign, 1):.1%} "
              f"({hits:,} of {n_benign:,} benign rows)")

    # --- KPI 2: lead time per event -----------------------------------
    rows = []
    max_ts = df["timestamp_utc"].max()
    for _, event in events.iterrows():
        if not bool(event["observable"]) or pd.isna(event["detectable_utc"]):
            continue  # not scored by the benchmark either
        evidence = [c for c in str(event["evidence_channels"]).split(",") if c in channels]
        if not evidence:
            continue  # GATEWAY events etc.: alarm via quality_flags later
        onset = event["onset_utc"]
        deadline = event["action_deadline_utc"]
        span_end = deadline if pd.notna(deadline) else event["end_utc"]
        if pd.isna(span_end):
            span_end = max_ts
        scope = (
            (df["asset_id"] == event["asset_id"])
            & (df["timestamp_utc"] >= onset)
            & (df["timestamp_utc"] <= span_end)
            & running
        )
        detected_ts = alarmed[scope & alarmed].index.min() if bool((scope & alarmed).any()) else None
        if detected_ts is not None:
            first_alarm = df.loc[detected_ts, "timestamp_utc"]
            if pd.notna(deadline):
                lead_h = (deadline - first_alarm).total_seconds() / 3600
                result = "EARLY" if lead_h > 0 else "LATE"
            else:
                lead_h = float("nan")
                result = "NO-DEADLINE"
            match = z_smooth[(z_smooth.index == detected_ts)
                             & (z_smooth["asset_id"] == event["asset_id"])]
            at_detection = match[z_cols_of(evidence)].abs().max(axis=0)
            if at_detection.notna().any():
                first_channel = str(at_detection.idxmax()).removeprefix("z_")
            else:  # all-NaN (e.g. sparse channel at that instant): report first evidence
                first_channel = evidence[0]
        else:
            first_alarm, lead_h, result, first_channel = None, None, "MISSED", None
        rows.append({
            "event": event["event_id"],
            "asset": event["asset_id"],
            "fault": event["fault_type"],
            "benchmark_detectable": event["detectable_utc"],
            "deadline": deadline,
            "our_detection": first_alarm,
            "lead_h": round(lead_h, 1) if lead_h is not None else None,
            "result": result,
            "surface": surface.loc[detected_ts] if detected_ts is not None else None,
            "first_channel": first_channel,
        })

    table = pd.DataFrame(rows)
    with pd.option_context("display.width", 200, "display.max_columns", 10):
        print("\nKPI 2  lead time per event (our smoothed-z detection vs deadline):")
        print(table.to_string(index=False))

    scored = table[table["result"].isin(["EARLY", "LATE"])]
    if not scored.empty:
        caught = scored[scored["result"] == "EARLY"]
        print(f"\nSummary: {len(caught)}/{len(scored)} events caught before deadline; "
              f"median lead {caught['lead_h'].median():.1f} h "
              f"(benchmark-only events: {len(scored) - len(caught)} late, "
              f"{len(table) - len(scored)} without deadline)")


if __name__ == "__main__":
    evaluate()
