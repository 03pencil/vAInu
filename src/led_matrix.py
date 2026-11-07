"""LED matrix animation for the Arduino UNO Q 8x13 display.

Draws "vAInu" scrolling across the matrix over a sparkle background. Each
frame is sent to the MCU sketch (arduino/led_matrix/sketch.ino) through the
Bridge as 104 characters of '0' and '1'. Off the board there is no Bridge,
so callers can only preview the frames.

This module has no link to the web UI; scripts/led_matrix.py runs it.
"""
from __future__ import annotations

import random
from typing import Any

ROWS = 8
COLS = 13
TEXT = "vAInu"
TEXT_TOP = 1
SPARKLE_CHANCE = 0.06
BRIDGE_METHOD = "show_frame"

GLYPHS: dict[str, list[str]] = {
    "v": ["...", "#.#", "#.#", "#.#", ".#."],
    "A": [".#.", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "n": ["...", "##.", "#.#", "#.#", "#.#"],
    "u": ["...", "#.#", "#.#", "#.#", "###"],
}

Frame = list[list[bool]]


def build_strip(text: str = TEXT) -> list[list[bool]]:
    """Return the text as ROWS rows of booleans, followed by a blank screen-width gap."""
    rows: list[list[bool]] = [[] for _ in range(ROWS)]
    for char in text:
        glyph = GLYPHS[char]
        for row in range(ROWS):
            source = row - TEXT_TOP
            if 0 <= source < len(glyph):
                rows[row].extend(cell == "#" for cell in glyph[source])
            else:
                rows[row].extend([False] * len(glyph[0]))
            rows[row].append(False)
    for row in range(ROWS):
        rows[row].extend([False] * COLS)
    return rows


def make_frame(strip: list[list[bool]], step: int, rng: random.Random) -> Frame:
    """One frame: the text window at `step` plus random sparkles on dark pixels."""
    width = len(strip[0])
    frame: Frame = []
    for row in range(ROWS):
        line = []
        for col in range(COLS):
            on = strip[row][(step + col) % width]
            if not on and rng.random() < SPARKLE_CHANCE:
                on = True
            line.append(on)
        frame.append(line)
    return frame


def frame_to_bits(frame: Frame) -> str:
    """Flatten a frame row by row to the 104-character string the sketch expects."""
    return "".join("1" if on else "0" for row in frame for on in row)


def frame_to_text(frame: Frame) -> str:
    """Readable preview of a frame, one line per matrix row."""
    return "\n".join("".join("#" if on else "." for on in row) for row in frame)


def connect_bridge() -> Any | None:
    """Return the UNO Q Bridge, or None when this is not the board."""
    try:
        from arduino.bridge import Bridge  # type: ignore[import-not-found]
    except ImportError:
        return None
    return Bridge()


def send_frame(bridge: Any, frame: Frame) -> None:
    """Send one frame to the MCU. Fire-and-forget, no response expected."""
    bridge.notify(BRIDGE_METHOD, frame_to_bits(frame))
