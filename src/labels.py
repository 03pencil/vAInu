"""Labeled-window alignment for vAInu.

Responsibility: join event and benign-window definitions onto telemetry
rows so every row knows what it is:

- ``benign``               inside a confirmed-good window (strong negative)
- ``fault_warming``        fault onset -> detectable (early-warning target)
- ``fault_detectable``     detectable -> end (benchmark says this is visible)
- ``fault_undetectable``   observable=False or no detectable time (excluded
                           from positives AND from envelope statistics)
- ``unknown``              everything else (treated as not-confirmed-bad)

No analysis happens here either; this only enriches rows with labels.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import get_data_dir

LABEL_BENIGN = "benign"
LABEL_FAULT_WARMING = "fault_warming"
LABEL_FAULT_DETECTABLE = "fault_detectable"
LABEL_FAULT_UNDETECTABLE = "fault_undetectable"
LABEL_UNKNOWN = "unknown"

FAULT_LABELS = (
    LABEL_FAULT_WARMING,
    LABEL_FAULT_DETECTABLE,
    LABEL_FAULT_UNDETECTABLE,
)

LABEL_COLUMN = "label"
EVENT_ID_COLUMN = "label_event_id"


def load_events(path: str | None = None) -> pd.DataFrame:
    """Load events_train + events_validation, timestamps parsed as UTC."""
    data = Path(path) if path is not None else Path(get_data_dir())
    frames: list[pd.DataFrame] = []
    for name in ("events_train.csv", "events_validation.csv"):
        file = data / name
        if file.is_file():
            events = pd.read_csv(file)
            events["source_file"] = name
            frames.append(events)
    if not frames:
        raise FileNotFoundError(f"No events_train.csv / events_validation.csv under {data}")
    events = pd.concat(frames, ignore_index=True)
    for col in ("onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"):
        events[col] = pd.to_datetime(events[col], utc=True)
    return events


def load_benign_windows(path: str | None = None) -> pd.DataFrame:
    """Load confirmed-good windows with start/end parsed as UTC."""
    data = Path(path) if path is not None else Path(get_data_dir())
    benign = pd.read_csv(data / "benign_windows_train_validation.csv")
    benign["start_utc"] = pd.to_datetime(benign["start_utc"], utc=True)
    benign["end_utc"] = pd.to_datetime(benign["end_utc"], utc=True)
    return benign


def label_telemetry(
    df: pd.DataFrame,
    events: "pd.DataFrame | None" = None,
    benign: "pd.DataFrame | None" = None,
) -> pd.DataFrame:
    """Return a copy of `df` with `label` and `label_event_id` columns.

    Benign windows are applied first; fault episodes second (a labeled
    fault always wins in the unlikely case of overlap). Events still open
    at the end of the telemetry window are clipped to the last timestamp.
    """
    if events is None:
        events = load_events()
    if benign is None:
        benign = load_benign_windows()

    out = df.copy()
    ts = out["timestamp_utc"]
    label = pd.Series(LABEL_UNKNOWN, index=out.index, dtype="string")
    event_id = pd.Series("", index=out.index, dtype="string")

    # 1) confirmed-good windows (strong negatives)
    for _, window in benign.iterrows():
        mask = (
            (out["asset_id"] == window["asset_id"])
            & (ts >= window["start_utc"])
            & (ts <= window["end_utc"])
        )
        label[mask] = LABEL_BENIGN

    # 2) fault episodes; open-ended events run to the end of the data
    max_ts = ts.max()
    onset = events["onset_utc"].fillna(max_ts)
    end = events["end_utc"].fillna(max_ts)
    for i, event in events.iterrows():
        base = (
            (out["asset_id"] == event["asset_id"])
            & (ts >= onset[i])
            & (ts <= end[i])
        )
        event_id[base] = event["event_id"]
        detectable = event["detectable_utc"]
        if (not bool(event["observable"])) or pd.isna(detectable):
            label[base] = LABEL_FAULT_UNDETECTABLE
            continue
        label[base & (ts < detectable)] = LABEL_FAULT_WARMING
        label[base & (ts >= detectable)] = LABEL_FAULT_DETECTABLE

    out[LABEL_COLUMN] = label
    out[EVENT_ID_COLUMN] = event_id
    return out
