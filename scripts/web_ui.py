"""Run the first-version vAInu web dashboard.

Usage:
    python scripts/web_ui.py
    python scripts/web_ui.py --data data/full --host 0.0.0.0 --port 8000

The default data tier comes from config.toml. Point --data at a tier directory
that contains the telemetry (data/full parquet partitions or starter csv.gz).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import (
    get_cache_dir,
    get_data_dir,
    get_web_ui_config,
    get_worker_count,
)
from src.web_ui import DashboardData, serve  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data", default=None,
        help="Tier directory or telemetry file; defaults to [paths] data_dir.",
    )
    parser.add_argument("--host", default=None, help="Bind address (default from config).")
    parser.add_argument("--port", type=int, default=None, help="Port (default from config).")
    parser.add_argument(
        "--workers", type=int, default=None,
        help="Processes for the per-asset math (default: [compute] workers, 0 = auto).",
    )
    parser.add_argument(
        "--cache-dir", default=None,
        help="Rebuild-cache directory (default from [web_ui] cache_dir); "
             "pass an empty string to disable the cache.",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Ignore any cached alarm surface and rebuild it.",
    )
    parser.add_argument(
        "--pilot-state", default=str(ROOT / "pilot" / "state.json"),
        help="Pilot snapshot written by scripts/pilot_run.py (shown in the pilot panel).",
    )
    parser.add_argument("--verbose", action="store_true", help="Log every HTTP request.")
    return parser.parse_args()


def main() -> None:
    """Load telemetry once, then serve the dashboard until interrupted."""
    args = parse_args()
    web_config = get_web_ui_config()
    data_path = args.data or get_data_dir()
    host = args.host or web_config["host"]
    port = args.port or web_config["port"]
    workers = args.workers if args.workers is not None else get_worker_count()
    if args.cache_dir is None:
        cache_dir = get_cache_dir()
    else:
        cache_dir = Path(args.cache_dir) if args.cache_dir else None

    print(f"Loading telemetry from {data_path} ...", flush=True)
    try:
        data = DashboardData.from_data_dir(
            data_path,
            watch_fraction=web_config["watch_fraction"],
            default_channel=web_config["default_channel"],
            alarm_mark=web_config["alarm_mark"],
            workers=workers,
            cache_dir=cache_dir,
            rebuild=args.rebuild,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("The repository copy may be missing telemetry.csv.gz (it is "
              "excluded by .gitignore). Point --data at a tier directory "
              "that contains the telemetry file.")
        raise SystemExit(1) from exc

    source = "cached surface" if data.cache_hit else "fresh build"
    print(
        f"Loaded {len(data.asset_ids)} assets and {len(data.channels)} channels "
        f"in {data.build_seconds:.1f}s ({source}).",
        flush=True,
    )
    serve(
        data,
        host=host,
        port=port,
        refresh_seconds=web_config["refresh_seconds"],
        history_samples=web_config["history_samples"],
        window_intervals=web_config["window_intervals"],
        verbose=args.verbose,
        pilot_state_path=Path(args.pilot_state),
    )


if __name__ == "__main__":
    main()
