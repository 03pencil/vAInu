"""Generate a video with the Pruna AI API (p-video model).

Usage:
    1. Paste your API key into pruna_api_key.txt (one line)
    2. python pruna_video.py "A cozy Finnish sauna by a lake at dusk"
"""

import os
import sys
import time

import requests

API_URL = "https://api.pruna.ai/v1/predictions"
STATUS_URL = "https://api.pruna.ai/v1/predictions/status/{id}"

_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruna_api_key.txt")

DEFAULT_PROMPT = "A green fresh water pump running inside a cargo ship's machine room, the pump getting hotter and hotter until one of its bearings starts to glow red hot, cinematic"
OUTPUT_FILE = "out.mp4"

# Settings for p-video: https://docs.api.pruna.ai/guides/models/p-video
DEFAULTS = {
    "duration": 5,          # seconds (1-20)
    "resolution": "720p",   # "720p" or "1080p"
    "aspect_ratio": "16:9", # "16:9", "9:16", "1:1", ...
}


def _load_key() -> str:
    """Read the API key from PRUNA_API_KEY env var, or pruna_api_key.txt."""
    key = os.environ.get("PRUNA_API_KEY", "").strip()
    if not key and os.path.exists(_KEY_FILE):
        key = open(_KEY_FILE, encoding="utf-8").read().strip()
    if key.startswith("pru_PASTE_YOUR_API_KEY"):
        key = ""
    return key


def main() -> None:
    key = _load_key()
    if not key:
        sys.exit(
            f"Put your API key in {_KEY_FILE} or set PRUNA_API_KEY."
        )

    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    hdrs = {"apikey": key, "Model": "p-video", "Content-Type": "application/json"}
    r = requests.post(API_URL, headers=hdrs, json={"input": {"prompt": prompt, **DEFAULTS}})
    data = r.json()

    if not r.ok or data.get("status") == "failed":
        sys.exit(f"Request failed ({r.status_code}): {data}")

    # Video models usually take > 60s, so we get a prediction id and poll.
    if "generation_url" in data:
        gen_url = data["generation_url"]
    else:
        pred_id = data["id"]
        status_url = data.get("get_url", STATUS_URL.format(id=pred_id))
        print(f"Submitted. Polling {status_url}")
        while True:
            time.sleep(5)
            data = requests.get(status_url, headers={"apikey": key}).json()
            status = data.get("status")
            print(f"  status: {status}")
            if status == "succeeded":
                gen_url = data["generation_url"]
                break
            if status in ("failed", "canceled"):
                sys.exit(f"Generation {status}: {data.get('error') or data}")

    # generation_url may be relative; resolve against the API base.
    if gen_url.startswith("/"):
        gen_url = "https://api.pruna.ai" + gen_url

    print(f"Downloading {gen_url}")
    video = requests.get(gen_url, headers={"apikey": key})
    with open(OUTPUT_FILE, "wb") as f:
        f.write(video.content)
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
