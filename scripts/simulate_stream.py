# vAInu pump-sensor-project - frontmatter
#
# Part of the Since AI 2026 hackathon (RETROFIT AI challenge).
# Team vAInu 2026: Paavo Gaidach, Matias Hirvonen.
# Licensed under the MIT License, Copyright (c) 2026 P.Gaidach & M.Hirvonen.
# See the LICENSE file in the repository root for the full license text.
#
# Totally fictional: all data and scenarios are synthetic.
#
# Vibe coded. Not for real-world use as it is. This is a hackathon prototype:
# it is not safety-certified and must not be used to monitor real machines,
# make maintenance decisions, or protect people.

"""Replay telemetry as a live line-by-line stream, one JSON frame per line.

It imitates the logic-box UART link: frames arrive in timestamp order, paced by
the data's own time gaps, and missing channels arrive as null.

Usage:
    .venv/bin/python scripts/simulate_stream.py --speed 600 | .venv/bin/python scripts/pilot_run.py --stdin
    .venv/bin/python scripts/simulate_stream.py --speed 0 --max-samples 5000     # as fast as possible

--speed N: data seconds per wall second (600 = 10 minutes of data per second, 0 = no pause).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src.config import get_data_dir  # noqa: E402
from src.feed import ReplayFeed, to_frame  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=None,
                        help="Tier directory or telemetry file; defaults to [paths] data_dir.")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Data seconds per wall second; 0 = no pauses.")
    parser.add_argument("--max-samples", type=int, default=None, help="Stop after this many frames.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    feed = ReplayFeed(args.data or get_data_dir())
    frame_rows = feed.df.sort_values("timestamp_utc", kind="stable")
    previous = None
    sent = 0
    try:
        for row in frame_rows.to_dict("records"):
            if args.max_samples is not None and sent >= args.max_samples:
                break
            stamp = pd.Timestamp(row["timestamp_utc"])
            if previous is not None and stamp != previous and args.speed > 0:
                time.sleep(max(0.0, (stamp - previous).total_seconds() / args.speed))
            previous = stamp
            sys.stdout.write(json.dumps(to_frame(row, feed.channels), allow_nan=False) + "\n")
            sys.stdout.flush()
            sent += 1
    except BrokenPipeError:
        # The reader (pilot) stopped early; that is a normal way to end a stream.
        return 0
    print(f"simulate_stream: sent {sent} frames.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
