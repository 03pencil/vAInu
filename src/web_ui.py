"""First-version web dashboard for vAInu.

The dashboard is deliberately dependency-free on the server side: it uses
the standard library HTTP server plus the project's existing pandas/numpy
math. It loads one telemetry tier, builds the same robust-z alarm surface
as ``scripts/sanity_gate.py`` (without the optional physics channels), and
serves a small JSON API consumed by a vanilla HTML/JS page.

The UI is a prototype: it reports a deterministic alarm score and the
channels that drive it. It does not claim a fault diagnosis; the SmolLM
narration layer is a later milestone.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
import pandas as pd

from .config import get_smoothing_window, get_z_threshold
from .data_input import channel_columns, load_channel_units, load_telemetry
from .labels import (
    FAULT_LABELS,
    LABEL_COLUMN,
    LABEL_UNKNOWN,
    label_telemetry,
    load_benign_windows,
    load_events,
)
from .math import group_rolled, merged_stats, modified_zscores, rolling_robust_z

MAX_WINDOW = 5000
STATUS_OK = "OK"
STATUS_WATCH = "WATCH"
STATUS_ALARM = "ALARM"
STATUS_IDLE = "IDLE"
STATUS_UNKNOWN = "UNKNOWN"


def _text(value: Any) -> str:
    """Return a display string, mapping missing values to an empty string."""
    if value is None or pd.isna(value):
        return ""
    return str(value)


def json_safe(value: Any) -> Any:
    """Recursively convert numpy/pandas values to JSON-safe Python values.

    NaN and infinity become ``None`` so ``json.dumps(..., allow_nan=False)``
    never emits invalid JSON.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        return value
    return str(value)


def status_for(
    mode: str,
    alarm: bool,
    max_abs_z: float | None,
    z_threshold: float,
    watch_fraction: float,
) -> str:
    """Classify one sample as OK / WATCH / ALARM / IDLE / UNKNOWN."""
    if str(mode).upper() != "RUNNING":
        return STATUS_IDLE
    if alarm:
        return STATUS_ALARM
    if max_abs_z is None:
        return STATUS_UNKNOWN
    if max_abs_z >= z_threshold * watch_fraction:
        return STATUS_WATCH
    return STATUS_OK


def top_deviations(
    z_scores: dict[str, np.ndarray],
    values: dict[str, np.ndarray],
    units: dict[str, str],
    index: int,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return the strongest finite |z| channels at one sample index."""
    rows: list[dict[str, Any]] = []
    for channel, scores in z_scores.items():
        score = float(scores[index])
        if not math.isfinite(score):
            continue
        value = float(values[channel][index])
        rows.append({
            "channel": channel,
            "z": score,
            "value": value if math.isfinite(value) else None,
            "unit": units.get(channel, "-"),
        })
    rows.sort(key=lambda row: abs(row["z"]), reverse=True)
    return rows[:limit]


def max_abs_z(series: "AssetSeries", index: int, channels: list[str]) -> float | None:
    """Largest finite |z| across channels at one sample index."""
    scores = [
        abs(float(series.z[channel][index]))
        for channel in channels
        if math.isfinite(float(series.z[channel][index]))
    ]
    return max(scores) if scores else None


@dataclass(frozen=True)
class AssetSeries:
    """Per-asset arrays used by the dashboard API."""

    asset_id: str
    profile: str
    control: str
    instrumentation_tier: str
    timestamps: pd.DatetimeIndex
    modes: np.ndarray
    values: dict[str, np.ndarray]
    z: dict[str, np.ndarray]
    alarm: np.ndarray

    @property
    def n(self) -> int:
        return len(self.timestamps)


@dataclass
class DashboardData:
    """Prepared telemetry + alarm surface served by the dashboard."""

    series: list[AssetSeries]
    channels: list[str]
    units: dict[str, str]
    z_threshold: float
    watch_fraction: float
    default_channel: str
    warning: str | None = None

    def __post_init__(self) -> None:
        self._by_id = {item.asset_id: item for item in self.series}

    @classmethod
    def from_data_dir(cls, data_dir: str | Path, **kwargs: Any) -> "DashboardData":
        """Load a tier (or explicit telemetry file) and build the alarm surface."""
        path = Path(data_dir)
        tier_dir = path.parent if path.is_file() else path
        frame = load_telemetry(str(path), join_assets=True)
        warning = None
        try:
            events = load_events(str(tier_dir))
            benign = load_benign_windows(str(tier_dir))
            frame = label_telemetry(frame, events, benign)
        except FileNotFoundError:
            frame = frame.copy()
            frame[LABEL_COLUMN] = LABEL_UNKNOWN
            warning = ("Event/benign label tables were not found; the healthy "
                       "envelope was fitted on all rows.")

        channels = channel_columns(frame)
        if not channels:
            raise ValueError("No telemetry channels found in the selected data tier.")

        smoothing = get_smoothing_window()
        z_threshold = get_z_threshold()
        envelope = merged_stats(frame[~frame[LABEL_COLUMN].isin(FAULT_LABELS)], channels)
        z = modified_zscores(frame, envelope, channels)
        z_keyed = pd.concat([frame[["asset_id"]], z], axis=1)
        z_smooth = group_rolled(z_keyed, window=smoothing)
        z_cols = [column for column in z_smooth.columns if column.startswith("z_")]
        z_rolled = rolling_robust_z(frame, window=smoothing, channels=channels)
        env_missing = z_smooth[z_cols].isna().all(axis=1)
        z_smooth.loc[env_missing, z_cols] = z_rolled.loc[env_missing, z_cols]

        alarm = (
            (z_smooth[z_cols].abs() > z_threshold).any(axis=1)
            & (frame["operating_mode"] == "RUNNING")
        )
        units = load_channel_units(str(tier_dir / "data_dictionary.csv"))

        series: list[AssetSeries] = []
        for asset_id, group in frame.groupby("asset_id", sort=True):
            index = group.index
            meta = group.iloc[0]
            series.append(AssetSeries(
                asset_id=str(asset_id),
                profile=_text(meta.get("profile")),
                control=_text(meta.get("control")),
                instrumentation_tier=_text(meta.get("instrumentation_tier")),
                timestamps=pd.DatetimeIndex(group["timestamp_utc"]),
                modes=group["operating_mode"].astype(str).to_numpy(),
                values={channel: group[channel].to_numpy(dtype=float)
                        for channel in channels},
                z={channel: z_smooth.loc[index, f"z_{channel}"].to_numpy(dtype=float)
                   for channel in channels},
                alarm=alarm.loc[index].to_numpy(dtype=bool),
            ))

        return cls(
            series=series,
            channels=channels,
            units=units,
            z_threshold=z_threshold,
            watch_fraction=kwargs.get("watch_fraction", 0.5),
            default_channel=kwargs.get("default_channel", "vibration_rms_mm_s"),
            warning=warning,
        )

    @property
    def asset_ids(self) -> list[str]:
        return [item.asset_id for item in self.series]

    def overview(self) -> dict[str, Any]:
        """One status row per asset, evaluated at its latest sample."""
        assets = []
        for item in self.series:
            index = item.n - 1
            score = max_abs_z(item, index, self.channels)
            status = status_for(
                item.modes[index], bool(item.alarm[index]), score,
                self.z_threshold, self.watch_fraction,
            )
            top = top_deviations(item.z, item.values, self.units, index, limit=1)
            assets.append({
                "asset_id": item.asset_id,
                "profile": item.profile,
                "control": item.control,
                "instrumentation_tier": item.instrumentation_tier,
                "mode": str(item.modes[index]),
                "status": status,
                "alarm_score": score,
                "last_update": item.timestamps[index].isoformat(),
                "top": top[0] if top else None,
            })
        return {
            "assets": assets,
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "warning": self.warning,
        }

    def asset_payload(
        self,
        asset_id: str,
        channel: str | None = None,
        cursor: int | None = None,
        window: int = 240,
    ) -> dict[str, Any]:
        """Chart window + latest values + top deviations for one asset."""
        item = self._by_id.get(asset_id)
        if item is None:
            raise KeyError(f"Unknown asset: {asset_id}")

        total = item.n
        cursor = total - 1 if cursor is None else int(cursor)
        cursor = max(0, min(cursor, total - 1))
        channel = self._resolve_channel(item, channel, cursor)
        if channel is None:
            raise ValueError(f"No channels with data for {asset_id}.")

        window = max(2, min(int(window), MAX_WINDOW, total))
        start = max(0, cursor - window + 1)

        timestamps = [
            timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
            for timestamp in item.timestamps[start:cursor + 1]
        ]
        values = item.values[channel][start:cursor + 1]
        z_values = item.z[channel][start:cursor + 1]
        alarm = item.alarm[start:cursor + 1]
        score = max_abs_z(item, cursor, self.channels)
        status = status_for(
            item.modes[cursor], bool(item.alarm[cursor]), score,
            self.z_threshold, self.watch_fraction,
        )
        latest = {
            name: {
                "value": item.values[name][cursor],
                "z": item.z[name][cursor],
                "unit": self.units.get(name, "-"),
            }
            for name in self.channels
        }
        return {
            "asset_id": item.asset_id,
            "profile": item.profile,
            "control": item.control,
            "instrumentation_tier": item.instrumentation_tier,
            "mode": str(item.modes[cursor]),
            "status": status,
            "alarm_score": score,
            "last_update": item.timestamps[cursor].isoformat(),
            "total": total,
            "cursor": cursor,
            "window": len(values),
            "channel": channel,
            "unit": self.units.get(channel, "-"),
            "timestamps": timestamps,
            "values": values.tolist(),
            "z": z_values.tolist(),
            "alarm": alarm.tolist(),
            "available_channels": [
                {"name": name, "unit": self.units.get(name, "-")}
                for name in self.channels
            ],
            "latest": latest,
            "top": top_deviations(item.z, item.values, self.units, cursor, limit=3),
            "z_threshold": self.z_threshold,
            "watch_fraction": self.watch_fraction,
        }

    def _resolve_channel(
        self,
        item: AssetSeries,
        channel: str | None,
        index: int,
    ) -> str | None:
        """Pick the requested channel, else a channel that explains this sample.

        The configured default wins when it has a reading at ``index``.
        Sparse retrofit assets (e.g. no vibration sensor) fall back to the
        channel with the largest finite |z| so the chart shows what drives
        the current status.
        """
        if channel and channel in item.values:
            return channel
        if (
            self.default_channel in item.values
            and math.isfinite(float(item.values[self.default_channel][index]))
        ):
            return self.default_channel

        best_channel: str | None = None
        best_score = -1.0
        for name, scores in item.z.items():
            score = float(scores[index])
            if math.isfinite(score) and abs(score) > best_score:
                best_channel = name
                best_score = abs(score)
        if best_channel is not None:
            return best_channel

        for name in item.values:
            if np.isfinite(item.values[name]).any():
                return name
        return None


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve the dashboard page and its JSON endpoints."""

    protocol_version = "HTTP/1.1"
    server_version = "vAInuUI/0.1"
    data: DashboardData
    web_config: dict[str, Any]
    verbose = False

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        try:
            if parsed.path in ("/", "/index.html"):
                self._send_html(HTML_PAGE)
            elif parsed.path == "/api/config":
                self._send_json({
                    "refresh_seconds": self.web_config["refresh_seconds"],
                    "history_samples": self.web_config["history_samples"],
                    "z_threshold": self.data.z_threshold,
                    "watch_fraction": self.data.watch_fraction,
                    "default_channel": self.data.default_channel,
                })
            elif parsed.path == "/api/overview":
                self._send_json(self.data.overview())
            elif parsed.path.startswith("/api/asset/"):
                asset_id = unquote(parsed.path[len("/api/asset/"):])
                query = parse_qs(parsed.query)
                channel = query.get("channel", [None])[0] or None
                cursor = self._optional_int(query, "cursor")
                window = self._optional_int(query, "window")
                if window is None:
                    window = int(self.web_config["history_samples"])
                self._send_json(self.data.asset_payload(
                    asset_id, channel=channel, cursor=cursor, window=window,
                ))
            else:
                self._send_json({"error": "Not found"}, status=404)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - report server errors as JSON
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=500)

    @staticmethod
    def _optional_int(query: dict[str, list[str]], name: str) -> int | None:
        raw = query.get(name, [None])[0]
        if raw in (None, ""):
            return None
        return int(raw)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(
            json_safe(payload), allow_nan=False, separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.verbose:
            super().log_message(fmt, *args)


class DashboardServer(ThreadingHTTPServer):
    """Threaded server that stays quiet when a browser drops a connection."""

    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def serve(
    data: DashboardData,
    host: str = "127.0.0.1",
    port: int = 8000,
    refresh_seconds: float = 2.0,
    history_samples: int = 240,
    verbose: bool = False,
) -> None:
    """Start the dashboard server (blocking)."""
    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardRequestHandler,),
        {
            "data": data,
            "web_config": {
                "refresh_seconds": refresh_seconds,
                "history_samples": history_samples,
            },
            "verbose": verbose,
        },
    )
    server = DashboardServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"vAInu web UI: {url}", flush=True)
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: the dashboard has no authentication. "
              "Use it only on a trusted local network.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web UI.", flush=True)
    finally:
        server.server_close()


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vAInu - Pump Health</title>
<style>
:root {
  --bg: #0b1020;
  --panel: #141b2d;
  --panel-2: #1b2438;
  --line: #2a3650;
  --text: #e8eefc;
  --muted: #8b9bb4;
  --accent: #5aa9ff;
  --ok: #35d07f;
  --watch: #f5b84b;
  --alarm: #ff5c6c;
  --idle: #6b7a90;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 14px;
}
.app { display: grid; grid-template-columns: 300px 1fr; min-height: 100vh; }
.sidebar {
  background: #0e1526;
  border-right: 1px solid var(--line);
  padding: 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.brand { padding: 4px 8px 10px; }
.logo { font-size: 26px; font-weight: 700; letter-spacing: 0.5px; }
.tagline { color: var(--muted); font-size: 12px; margin-top: 2px; }
.sidebar-title {
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 0 8px;
}
.asset-list { display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
.asset {
  width: 100%;
  text-align: left;
  background: var(--panel);
  color: var(--text);
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  font: inherit;
}
.asset:hover { border-color: var(--line); }
.asset.active { border-color: var(--accent); background: var(--panel-2); }
.asset-head { display: flex; align-items: center; gap: 8px; }
.asset-id { font-weight: 600; }
.asset-status { margin-left: auto; color: var(--muted); font-size: 10px; letter-spacing: 0.6px; }
.asset-meta { color: var(--muted); font-size: 11px; margin-top: 5px; }
.asset-top { color: var(--muted); font-size: 11px; margin-top: 4px; display: block; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--idle); }
.dot.ok { background: var(--ok); }
.dot.watch { background: var(--watch); }
.dot.alarm { background: var(--alarm); box-shadow: 0 0 8px var(--alarm); }
.dot.idle, .dot.unknown { background: var(--idle); }
.sidebar-foot { margin-top: auto; display: flex; flex-direction: column; gap: 8px; padding: 8px; }
.conn { color: var(--muted); font-size: 11px; }
.main { padding: 24px 28px; max-width: 1400px; width: 100%; }
.topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
h1 { margin: 0; font-size: 28px; }
h2 { margin: 0; font-size: 15px; font-weight: 600; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.status {
  display: inline-block;
  padding: 5px 11px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  border: 1px solid var(--line);
  color: var(--muted);
}
.status.ok { color: var(--ok); border-color: rgba(53, 208, 127, 0.5); background: rgba(53, 208, 127, 0.08); }
.status.watch { color: var(--watch); border-color: rgba(245, 184, 75, 0.5); background: rgba(245, 184, 75, 0.08); }
.status.alarm { color: var(--alarm); border-color: rgba(255, 92, 108, 0.6); background: rgba(255, 92, 108, 0.1); }
.status.idle, .status.unknown { color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.card, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px 16px;
}
.label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; }
.value { font-size: 20px; font-weight: 600; margin-top: 6px; }
.panel { margin-bottom: 16px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.controls { display: flex; gap: 8px; }
.select, .btn, .slider {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 7px 10px;
  font: inherit;
}
.select:focus, .btn:focus, .slider:focus { outline: 1px solid var(--accent); }
.btn { cursor: pointer; }
.btn:hover { border-color: var(--accent); }
.btn.active { border-color: var(--accent); color: var(--accent); }
.btn.ghost { background: transparent; }
.chart { width: 100%; min-height: 260px; }
.chart svg { width: 100%; height: auto; display: block; }
.grid { stroke: #22304a; stroke-width: 1; }
.axis { fill: var(--muted); font-size: 10px; }
.line { fill: none; stroke: var(--accent); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.last-dot { fill: var(--accent); }
.alarm-band { fill: rgba(255, 92, 108, 0.13); }
.empty { color: var(--muted); padding: 40px 0; text-align: center; }
.replay { display: flex; align-items: center; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
.slider { flex: 1; min-width: 140px; padding: 0; accent-color: var(--accent); }
.grid-2 { display: grid; grid-template-columns: 1.35fr 1fr; gap: 16px; }
.values { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.value-card { background: var(--panel-2); border: 1px solid var(--line); border-radius: 9px; padding: 9px 10px; }
.value-name { color: var(--muted); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.value-main { font-size: 16px; font-weight: 600; margin-top: 4px; }
.value-z { color: var(--muted); font-size: 11px; margin-top: 3px; }
.deviations { display: flex; flex-direction: column; gap: 8px; }
.deviation {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 9px 10px;
}
.deviation-z { font-size: 15px; font-weight: 700; }
.z-alarm { color: var(--alarm); }
.z-watch { color: var(--watch); }
.hint { color: var(--muted); font-size: 11px; margin-top: 10px; }
.error {
  background: rgba(255, 92, 108, 0.12);
  border: 1px solid rgba(255, 92, 108, 0.5);
  color: #ffd7db;
  border-radius: 9px;
  padding: 10px 12px;
  margin-bottom: 14px;
}
.hidden { display: none; }
.foot { color: var(--muted); font-size: 11px; margin-top: 8px; }
@media (max-width: 900px) {
  .app { grid-template-columns: 1fr; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--line); }
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-2 { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="logo">vAInu</div>
      <div class="tagline">Pump health prototype</div>
    </div>
    <div class="sidebar-title">Assets <span id="asset-count"></span></div>
    <div id="asset-list" class="asset-list"></div>
    <div class="sidebar-foot">
      <div id="conn" class="conn">Connecting...</div>
      <button id="refresh-btn" class="btn ghost">Refresh</button>
    </div>
  </aside>
  <main class="main">
    <div id="error" class="error hidden"></div>
    <header class="topbar">
      <div>
        <h1 id="asset-title">-</h1>
        <div id="asset-subtitle" class="muted">-</div>
      </div>
      <div class="topbar-right">
        <span id="status-badge" class="status unknown">UNKNOWN</span>
        <span id="live-label" class="muted"></span>
      </div>
    </header>
    <section class="cards">
      <div class="card"><div class="label">Operating mode</div><div id="mode" class="value">-</div></div>
      <div class="card"><div class="label">Last sample</div><div id="last-update" class="value small">-</div></div>
      <div class="card"><div class="label">Alarm score</div><div id="alarm-score" class="value">-</div></div>
      <div class="card"><div class="label">Channel</div><div id="channel-label" class="value small">-</div></div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>Signal</h2>
        <div class="controls">
          <select id="channel-select" class="select"></select>
          <select id="window-select" class="select">
            <option value="60">10 min</option>
            <option value="240" selected>40 min</option>
            <option value="720">2 h</option>
            <option value="2160">6 h</option>
          </select>
        </div>
      </div>
      <div id="chart" class="chart"></div>
      <div class="replay">
        <button id="play-btn" class="btn">&#9654; Replay</button>
        <select id="speed-select" class="select">
          <option value="1">Slow</option>
          <option value="5" selected>Normal</option>
          <option value="20">Fast</option>
        </select>
        <input id="cursor-slider" class="slider" type="range" min="0" max="1" value="1">
        <button id="latest-btn" class="btn ghost">Latest</button>
        <span id="cursor-label" class="muted"></span>
      </div>
    </section>
    <div class="grid-2">
      <section class="panel">
        <div class="panel-head"><h2>Latest values</h2></div>
        <div id="latest-values" class="values"></div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Top deviations</h2></div>
        <div id="top-deviations" class="deviations"></div>
        <div class="hint">Robust modified z-score; alarm threshold <span id="threshold-label">-</span>.</div>
      </section>
    </div>
    <footer class="foot">Prototype: deterministic robust z-score alarm, not a fault diagnosis. SmolLM narration is not wired yet.</footer>
  </main>
</div>
<script>
const state = {
  config: null,
  overview: [],
  assetId: null,
  channel: null,
  cursor: null,
  playing: false,
  speed: 5,
  window: 240,
  asset: null,
  warning: null,
  timer: null,
  fetchSeq: 0,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function api(path) {
  const response = await fetch(path, {cache: "no-store"});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || ("HTTP " + response.status));
  return payload;
}

function showError(message) {
  const element = $("error");
  if (!message) {
    element.classList.add("hidden");
    element.textContent = "";
    return;
  }
  element.textContent = message;
  element.classList.remove("hidden");
}

function statusClass(status) {
  return String(status || "unknown").toLowerCase();
}

function formatNumber(value, unit) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  const digits = abs >= 100 ? 1 : abs >= 10 ? 2 : 3;
  const suffix = unit && unit !== "-" ? " " + unit : "";
  return Number(value).toFixed(digits) + suffix;
}

function formatTime(timestamp) {
  if (!timestamp) return "-";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return date.toLocaleString([], {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function formatZ(score) {
  if (score === null || score === undefined || Number.isNaN(score)) return "-";
  return (score >= 0 ? "+" : "") + Number(score).toFixed(2) + "s";
}

function zClass(score, threshold) {
  if (score === null || score === undefined || Number.isNaN(score)) return "";
  const abs = Math.abs(score);
  if (abs > threshold) return "z-alarm";
  if (abs > threshold * 0.5) return "z-watch";
  return "";
}

async function loadConfig() {
  state.config = await api("/api/config");
  $("threshold-label").textContent = Number(state.config.z_threshold).toFixed(1) + "s";
  state.window = state.config.history_samples || state.window;
  $("window-select").value = String(state.window);
}

async function loadOverview() {
  const payload = await api("/api/overview");
  state.overview = payload.assets || [];
  state.warning = payload.warning;
  renderSidebar();
  showError(state.warning || "");
}

function renderSidebar() {
  const list = $("asset-list");
  list.innerHTML = "";
  $("asset-count").textContent = "(" + state.overview.length + ")";
  for (const asset of state.overview) {
    const button = document.createElement("button");
    button.className = "asset" + (asset.asset_id === state.assetId ? " active" : "");
    button.onclick = () => selectAsset(asset.asset_id);
    const top = asset.top
      ? '<span class="asset-top">' + escapeHtml(asset.top.channel) + " " + formatZ(asset.top.z) + "</span>"
      : "";
    button.innerHTML =
      '<div class="asset-head">' +
        '<span class="dot ' + statusClass(asset.status) + '"></span>' +
        '<span class="asset-id">' + escapeHtml(asset.asset_id) + "</span>" +
        '<span class="asset-status">' + escapeHtml(asset.status) + "</span>" +
      "</div>" +
      '<div class="asset-meta">' + escapeHtml(asset.mode) + " &middot; " + formatTime(asset.last_update) + "</div>" +
      top;
    list.appendChild(button);
  }
}

async function selectAsset(assetId) {
  if (state.assetId !== assetId) {
    state.assetId = assetId;
    state.cursor = null;
    state.playing = false;
    state.channel = null;
    updatePlayButton();
  }
  renderSidebar();
  await fetchAsset();
}

async function fetchAsset() {
  if (!state.assetId) return;
  const requestId = ++state.fetchSeq;
  const params = new URLSearchParams();
  params.set("channel", state.channel || "");
  params.set("window", String(state.window));
  if (state.cursor !== null) params.set("cursor", String(state.cursor));
  const payload = await api("/api/asset/" + encodeURIComponent(state.assetId) + "?" + params.toString());
  if (requestId !== state.fetchSeq) return;
  state.asset = payload;
  if (state.cursor === null) state.cursor = payload.cursor;
  state.channel = payload.channel;
  render();
}

function render() {
  const data = state.asset;
  if (!data) return;
  $("asset-title").textContent = data.asset_id;
  $("asset-subtitle").textContent =
    [data.profile, data.control, data.instrumentation_tier].filter(Boolean).join(" . ") || "-";
  const badge = $("status-badge");
  badge.textContent = data.status;
  badge.className = "status " + statusClass(data.status);
  $("mode").textContent = data.mode || "-";
  $("last-update").textContent = formatTime(data.last_update);
  $("alarm-score").textContent = data.alarm_score === null
    ? "-" : Number(data.alarm_score).toFixed(2) + "s";
  $("channel-label").textContent = data.channel + " (" + (data.unit || "-") + ")";
  $("live-label").textContent = state.playing
    ? "REPLAY" : (state.cursor >= data.total - 1 ? "LATEST" : "PAUSED");

  const select = $("channel-select");
  const optionNames = [...select.options].map((option) => option.value);
  const channelNames = data.available_channels.map((channel) => channel.name);
  if (optionNames.join("|") !== channelNames.join("|")) {
    select.innerHTML = "";
    for (const channel of data.available_channels) {
      const option = document.createElement("option");
      option.value = channel.name;
      option.textContent = channel.unit && channel.unit !== "-"
        ? channel.name + " (" + channel.unit + ")" : channel.name;
      select.appendChild(option);
    }
  }
  select.value = data.channel;

  renderChart(data);
  renderLatest(data);
  renderTop(data);

  const slider = $("cursor-slider");
  slider.max = String(Math.max(0, data.total - 1));
  slider.value = String(data.cursor);
  $("cursor-label").textContent = (data.cursor + 1) + " / " + data.total;
}

function renderLatest(data) {
  const container = $("latest-values");
  container.innerHTML = "";
  for (const channel of data.available_channels) {
    const item = data.latest[channel.name] || {};
    const card = document.createElement("div");
    card.className = "value-card";
    card.innerHTML =
      '<div class="value-name">' + escapeHtml(channel.name) + "</div>" +
      '<div class="value-main">' + escapeHtml(formatNumber(item.value, channel.unit)) + "</div>" +
      '<div class="value-z ' + zClass(item.z, data.z_threshold) + '">' + formatZ(item.z) + "</div>";
    container.appendChild(card);
  }
}

function renderTop(data) {
  const container = $("top-deviations");
  container.innerHTML = "";
  if (!data.top || data.top.length === 0) {
    container.innerHTML = '<div class="muted">No finite z-scores at this sample.</div>';
    return;
  }
  for (const row of data.top) {
    const element = document.createElement("div");
    element.className = "deviation";
    element.innerHTML =
      "<div>" +
        '<div class="value-name">' + escapeHtml(row.channel) + "</div>" +
        '<div class="muted">' + escapeHtml(formatNumber(row.value, row.unit)) + "</div>" +
      "</div>" +
      '<div class="deviation-z ' + zClass(row.z, data.z_threshold) + '">' + formatZ(row.z) + "</div>";
    container.appendChild(element);
  }
}

function renderChart(data) {
  const container = $("chart");
  const values = data.values || [];
  const finite = values.filter((value) => value !== null && Number.isFinite(value));
  if (finite.length === 0) {
    container.innerHTML = '<div class="empty">No data for this channel in the selected window.</div>';
    return;
  }
  const width = 800;
  const height = 260;
  const pad = {left: 56, right: 12, top: 14, bottom: 30};
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  min -= span * 0.06;
  max += span * 0.06;
  const x = (index) => pad.left + (values.length <= 1 ? 0 : (index / (values.length - 1)) * plotW);
  const y = (value) => pad.top + plotH - ((value - min) / (max - min)) * plotH;

  let svg = '<svg viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="' + escapeHtml(data.channel) + ' chart">';
  for (let i = 0; i <= 4; i++) {
    const gy = pad.top + (plotH * i) / 4;
    const label = max - ((max - min) * i) / 4;
    svg += '<line x1="' + pad.left + '" y1="' + gy + '" x2="' + (width - pad.right) + '" y2="' + gy + '" class="grid"/>';
    svg += '<text x="' + (pad.left - 8) + '" y="' + (gy + 4) + '" class="axis" text-anchor="end">' + label.toFixed(2) + "</text>";
  }
  let runStart = null;
  for (let i = 0; i <= data.alarm.length; i++) {
    const active = i < data.alarm.length && data.alarm[i];
    if (active && runStart === null) runStart = i;
    if (!active && runStart !== null) {
      const x1 = x(runStart);
      const x2 = x(Math.max(runStart, i - 1));
      svg += '<rect x="' + x1 + '" y="' + pad.top + '" width="' + Math.max(1, x2 - x1) +
        '" height="' + plotH + '" class="alarm-band"/>';
      runStart = null;
    }
  }
  let path = "";
  let started = false;
  for (let i = 0; i < values.length; i++) {
    const value = values[i];
    if (value === null || !Number.isFinite(value)) { started = false; continue; }
    path += (started ? "L" : "M") + x(i).toFixed(2) + "," + y(value).toFixed(2) + " ";
    started = true;
  }
  svg += '<path d="' + path + '" class="line"/>';
  const last = values.length - 1;
  if (values[last] !== null && Number.isFinite(values[last])) {
    svg += '<circle cx="' + x(last) + '" cy="' + y(values[last]) + '" r="3.5" class="last-dot"/>';
  }
  svg += '<text x="' + pad.left + '" y="' + (height - 8) + '" class="axis">' + formatTime(data.timestamps[0]) + "</text>";
  svg += '<text x="' + (width - pad.right) + '" y="' + (height - 8) + '" class="axis" text-anchor="end">' +
    formatTime(data.timestamps[data.timestamps.length - 1]) + "</text>";
  svg += "</svg>";
  container.innerHTML = svg;
}

function updatePlayButton() {
  $("play-btn").textContent = state.playing ? "Pause" : "Replay";
  $("play-btn").classList.toggle("active", state.playing);
}

async function tick() {
  try {
    await loadOverview();
    if (state.playing && state.asset) {
      const next = Math.min(state.cursor + state.speed, state.asset.total - 1);
      state.cursor = next;
      if (next >= state.asset.total - 1) {
        state.playing = false;
        updatePlayButton();
      }
      await fetchAsset();
    }
    $("conn").textContent = "Connected . " + new Date().toLocaleTimeString();
    showError(state.warning || "");
  } catch (error) {
    $("conn").textContent = "Disconnected";
    showError(error.message);
  }
}

async function init() {
  try {
    await loadConfig();
    await loadOverview();
    if (state.overview.length) await selectAsset(state.overview[0].asset_id);
    $("conn").textContent = "Connected";
    const seconds = state.config.refresh_seconds || 2;
    state.timer = setInterval(tick, seconds * 1000);
  } catch (error) {
    showError(error.message);
    $("conn").textContent = "Disconnected";
  }
}

$("channel-select").addEventListener("change", async (event) => {
  state.channel = event.target.value;
  await fetchAsset();
});
$("window-select").addEventListener("change", async (event) => {
  state.window = Number(event.target.value);
  await fetchAsset();
});
$("play-btn").addEventListener("click", () => {
  state.playing = !state.playing;
  if (state.playing && state.asset && state.cursor >= state.asset.total - 1) state.cursor = 0;
  updatePlayButton();
});
$("speed-select").addEventListener("change", (event) => {
  state.speed = Number(event.target.value);
});
$("cursor-slider").addEventListener("input", async (event) => {
  state.playing = false;
  updatePlayButton();
  state.cursor = Number(event.target.value);
  await fetchAsset();
});
$("latest-btn").addEventListener("click", async () => {
  state.playing = false;
  updatePlayButton();
  state.cursor = null;
  await fetchAsset();
});
$("refresh-btn").addEventListener("click", tick);

init();
</script>
</body>
</html>
"""
