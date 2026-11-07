# Workflow — Board Access and Web App

Quick reference for reaching the Arduino UNO Q and the local dashboard.
Full setup steps are in [`arduino_uno_q_install.md`](arduino_uno_q_install.md).

## Arduino UNO Q (ABX00173)

| Item | Value |
|------|-------|
| IP address | `10.20.3.13` (from `~/.ssh/known_hosts`; confirm with `hostname -I` on the board) |
| mDNS name | `<boardname>.local` — the name chosen in the App Lab wizard (exemple; `uno-q.local` does not resolve) |
| SSH user | `arduino` |
| SSH | `ssh arduino@00.00.0.00` (or `ssh arduino@<boardname>.local`) |
| ADB fallback | `adb devices` then `adb shell` over USB-C data cable (password `arduino` if the wizard was not run) |
| Ollama API (board only) | `http://127.0.0.1:11434` |

Status: SSH key login currently **rejected** (`Permission denied (publickey,password)`).
Access needs either the `arduino` password or the host key authorized on the board
(`ssh-copy-id arduino@10.20.3.13`).

Do not store the password in this file or in git.

## Web app (dashboard)

The dashboard is a dependency-free local server (`scripts/web_ui.py`). It has **no
authentication**, so run it only on a trusted network.

**Start on the board** (from the project folder, e.g. `~/pump-sensor-project`):

```bash
.venv/bin/python scripts/web_ui.py --data data/full --host 10.20.3.13 --port 8000
```

Keep it running after you log out with `nohup` or a systemd service. A dashboard
started in a foreground SSH session stops when the session closes.

**Open from a PC on the same network:**

- `http://10.20.3.13:8000`
- `http://<boardname>.local:8000` (if mDNS works on your network)

**Local only (on the board itself):** `http://127.0.0.1:8000`

Port 8000 and the `--data` folder are the values from the install manual (section 7.6).
The pilot panel reads `pilot/state.json`, so run the pilot first:

```bash
.venv/bin/python scripts/pilot_run.py --speed 0
```

## Quick checklist

1. Board powered, on the same Wi-Fi as the PC.
2. `ssh arduino@10.20.3.13` works.
3. Ollama running: `sudo systemctl status ollama`.
4. Pilot run has written `pilot/state.json`.
5. Dashboard running on port 8000.
6. Open `http://10.20.3.13:8000` in a browser.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Board not found | Try the IP; `hostname -I` via ADB; check the data cable |
| `.local` name fails | Use the IP instead (mDNS blocked on some networks) |
| Dashboard page does not load | Confirm the server is running and bound to `10.20.3.13`, not `127.0.0.1` |
| Pilot panel empty | Run `pilot_run.py` first so `pilot/state.json` exists |
