"""Animate "vAInu" on the Arduino UNO Q LED matrix.

Usage:
    .venv/bin/python scripts/led_matrix.py                  # on the board: send frames to the MCU
    .venv/bin/python scripts/led_matrix.py --preview --duration 3   # on a PC: print frames

--duration 0 runs until Ctrl+C. The MCU needs the sketch in arduino/led_matrix_app/ flashed with Arduino App Lab.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.led_matrix import build_strip, connect_bridge, frame_to_text, make_frame, send_frame  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fps", type=float, default=6.0, help="Frames per second.")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Seconds to run; 0 = until Ctrl+C.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for the sparkles.")
    parser.add_argument("--preview", action="store_true",
                        help="Print frames to the terminal instead of sending them to the MCU.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bridge = None if args.preview else connect_bridge()
    if bridge is None and not args.preview:
        print("No Arduino Bridge found (not on the UNO Q). Use --preview to see the frames.",
              file=sys.stderr)
        return 1

    strip = build_strip()
    rng = random.Random(args.seed)
    interval = 1.0 / args.fps
    started = time.monotonic()
    step = 0
    try:
        while args.duration <= 0 or time.monotonic() - started < args.duration:
            frame = make_frame(strip, step, rng)
            if bridge is not None:
                send_frame(bridge, frame)
            else:
                print("\033[H\033[2J" + frame_to_text(frame), flush=True)
            step += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
