"""Configuration loader for vAInu (stdlib tomllib, Python 3.11+)."""
from __future__ import annotations

import os
import tomllib

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.toml")

_WEB_UI_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8000,
    "refresh_seconds": 2,
    "history_samples": 240,
    "watch_fraction": 0.5,
    "default_channel": "vibration_rms_mm_s",
}


def load_config(path: str = CONFIG_FILE) -> dict:
    """Load and return the project configuration as a dict."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def get_data_dir(cfg: dict | None = None) -> str:
    if cfg is None:
        cfg = load_config()
    return cfg.get("paths", {}).get("data_dir", "data/full")


def get_channels(cfg: dict | None = None) -> list[str]:
    if cfg is None:
        cfg = load_config()
    return cfg.get("channels", {}).get("names", ["pressure", "temperature", "vibration", "flow"])


def get_rolling_window(cfg: dict | None = None) -> int:
    if cfg is None:
        cfg = load_config()
    return cfg.get("analysis", {}).get("rolling_window", 5)


def get_z_threshold(cfg: dict | None = None) -> float:
    if cfg is None:
        cfg = load_config()
    return cfg.get("analysis", {}).get("z_threshold", 3.0)


def get_smoothing_window(cfg: dict | None = None) -> int:
    if cfg is None:
        cfg = load_config()
    return cfg.get("analysis", {}).get("smoothing_window", 60)


def get_trend_config(cfg: dict | None = None) -> dict:
    """[trend] section with defaults: bin_minutes, trailing_hours,
    min_bin_count, min_fit_points."""
    if cfg is None:
        cfg = load_config()
    section = cfg.get("trend", {})
    return {
        "bin_minutes": int(section.get("bin_minutes", 10)),
        "trailing_hours": float(section.get("trailing_hours", 12.0)),
        "min_bin_count": int(section.get("min_bin_count", 2)),
        "min_fit_points": int(section.get("min_fit_points", 36)),
    }


def get_limits_config(cfg: dict | None = None) -> dict:
    """[limits] section: static alarm limits per channel (key = channel)."""
    if cfg is None:
        cfg = load_config()
    return dict(cfg.get("limits", {}))


def get_debounce_config(cfg: dict | None = None) -> dict:
    """[debounce] section: confirm_samples, escalate_samples."""
    if cfg is None:
        cfg = load_config()
    section = cfg.get("debounce", {})
    return {
        "confirm_samples": int(section.get("confirm_samples", 18)),
        "escalate_samples": int(section.get("escalate_samples", 180)),
    }


def get_asset_ids(cfg: dict | None = None) -> list[str]:
    if cfg is None:
        cfg = load_config()
    return cfg.get("assets", {}).get("ids", [])


def get_tiers(cfg: dict | None = None) -> list[str]:
    if cfg is None:
        cfg = load_config()
    return cfg.get("paths", {}).get("tiers", ["full", "starter"])


def get_web_ui_config(cfg: dict | None = None) -> dict:
    """Web UI settings from [web_ui], with defaults for missing keys."""
    if cfg is None:
        cfg = load_config()
    values = dict(_WEB_UI_DEFAULTS)
    values.update(cfg.get("web_ui", {}))
    return values
