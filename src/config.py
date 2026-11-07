"""Configuration loader for vAInu (stdlib only, Python 3 compatible)."""
from __future__ import annotations

import configparser
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.ini")


def load_config(path: str = CONFIG_FILE) -> configparser.ConfigParser:
    """Load and return the project configuration."""
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


def get_data_dir(cfg: configparser.ConfigParser | None = None) -> str:
    if cfg is None:
        cfg = load_config()
    return cfg.get("paths", "data_dir", fallback="data/full")


def get_channels(cfg: configparser.ConfigParser | None = None) -> list[str]:
    if cfg is None:
        cfg = load_config()
    raw = cfg.get("channels", "names", fallback="pressure,temperature,vibration,flow")
    return [c.strip() for c in raw.split(",") if c.strip()]


def get_rolling_window(cfg: configparser.ConfigParser | None = None) -> int:
    if cfg is None:
        cfg = load_config()
    return cfg.getint("analysis", "rolling_window", fallback=5)