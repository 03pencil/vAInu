"""Configuration loader for vAInu (stdlib tomllib, Python 3.11+)."""
from __future__ import annotations

import os
import tomllib

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.toml")


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


def get_asset_ids(cfg: dict | None = None) -> list[str]:
    if cfg is None:
        cfg = load_config()
    return cfg.get("assets", {}).get("ids", [])