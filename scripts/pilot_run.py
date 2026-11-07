"""Run the pilot monitor on replayed telemetry (UART input comes later).

Usage:
    .venv/bin/python scripts/pilot_run.py                     # fast replay
    .venv/bin/python scripts/pilot_run.py --speed 600         # 10 min of data per second
    .venv/bin/python scripts/pilot_run.py --data data/starter --out pilot
    .venv/bin/python scripts/simulate_stream.py --speed 600 | .venv/bin/python scripts/pilot_run.py --stdin

Writes <out>/state.json (latest status per asset, for the UI to poll) and
<out>/predictions.jsonl (one line per status change).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_data_dir  # noqa: E402
from src.feed import ReplayFeed, StdinFeed  # noqa: E402
from src.pilot import PilotMonitor, build_envelope, run_pilot  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=None,
                        help="Tier directory or telemetry file; defaults to [paths] data_dir.")
    parser.add_argument("--out", default=str(ROOT / "pilot"),
                        help="Output directory for state.json and predictions.jsonl.")
    parser.add_argument("--speed", type=float, default=0.0,
                        help="Data seconds per wall second; 0 = as fast as possible.")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Stop after this many samples (smoke tests).")
    parser.add_argument("--stdin", action="store_true",
                        help="Read UART-style frames (JSON lines) from stdin instead of replaying a file. "
                             "Pace the stream with scripts/simulate_stream.py --speed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_path = args.data or get_data_dir()

    print(f"Fitting healthy envelope from {data_path} ...", flush=True)
    envelope = build_envelope(data_path)
    monitor = PilotMonitor(envelope)
    if args.stdin:
        feed = StdinFeed()
        print("Reading frames from stdin (pacing comes from the sender).", flush=True)
        speed = 0.0
    else:
        replay = ReplayFeed(data_path)
        print(f"Replaying {len(replay.df):,} samples, {replay.df['asset_id'].nunique()} assets.",
              flush=True)
        feed = replay
        speed = args.speed

    snapshot = run_pilot(feed, monitor, Path(args.out),
                         speed=speed, max_samples=args.max_samples)
    if args.stdin and feed.bad_frames:
        print(f"Skipped {feed.bad_frames} malformed frame(s); first error: {feed.first_error}")
    print(f"Last data time: {snapshot['generated_utc']}")
    for record in snapshot["assets"]:
        print(f"{record['asset_id']:<9} {record['status']:<8} {record['debounce_state']:<10} "
              f"score_z={record['score_z']}  top={record['top_channel']}")
    print(f"State written to {Path(args.out) / 'state.json'}")


if __name__ == "__main__":
    main()
