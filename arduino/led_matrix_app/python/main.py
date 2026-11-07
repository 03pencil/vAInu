"""App Lab entry point: send the vAInu LED animation to the MCU sketch.

Runs on the UNO Q Linux side. The animation code lives in the project
(src/led_matrix.py), so the project must be copied to PROJECT_DIR on the board.
"""
import random
import sys
import time
from pathlib import Path

PROJECT_DIR = Path("/home/arduino/pump-sensor-project")
FPS = 6.0

sys.path.insert(0, str(PROJECT_DIR))

from src.led_matrix import build_strip, connect_bridge, make_frame, send_frame  # noqa: E402


def main() -> None:
    bridge = connect_bridge()
    if bridge is None:
        print("No Arduino Bridge found. Check that this app runs on the UNO Q.", flush=True)
        return
    strip = build_strip()
    rng = random.Random()
    interval = 1.0 / FPS
    step = 0
    while True:
        send_frame(bridge, make_frame(strip, step, rng))
        step += 1
        time.sleep(interval)


if __name__ == "__main__":
    main()
