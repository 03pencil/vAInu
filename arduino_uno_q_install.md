# Arduino UNO Q (ABX00173) — Install Manual

> Minimum install to get **SmolLM2 running on the UNO Q's MPU** (via Ollama),
> matching `bom.md` / `plan.md`. No cameras, bricks, monitor or case.
> Covers the host PC setup on **Linux, Windows and macOS**, then the identical
> board-side steps (they are the same for every host OS — only the host PC part
> differs).

**Note on the ordering code:** the 4 GB RAM / 32 GB eMMC board is **ABX00173**
(not "AB00173"). The 2 GB / 16 GB variant is ABX00162 and can only run the
smallest quantized SmolLM (see `bom.md`). This manual assumes ABX00173.

---

## 0. What you need

From `bom.md`:

| Item | Purpose |
|------|---------|
| Arduino UNO Q — ABX00173 (4 GB / 32 GB) | the board |
| USB-C **data** cable (USB-A → C is fine) | one-time setup from host PC |
| 5 V / 3 A USB-C wall adapter | power for LLM inference (not a PC port) |
| Wi-Fi network (2.4 or 5 GHz) | board joins it during setup; pulls the model |

No power supply is needed for the first session — the PC USB port powers the
board. A **data** cable is required; charge-only cables never enumerate
(the board never shows up).

Host PC software requirements (official): Windows 10 64-bit+, macOS 11+,
Debian "Bookworm"/Ubuntu 22.04+ (64-bit).

---

## 1. Host PC setup — Arduino App Lab

Download **Arduino App Lab** from <https://www.arduino.cc/en/software/#app-lab-section>
for your operating system. Install like any other desktop app.

### 1.1 Linux (Debian Bookworm+ / Ubuntu 22.04+)

Three steps (official Arduino docs, `docs.arduino.cc/software/app-lab/setup/linux/`):

1. **UI library:**

   ```bash
   sudo apt update
   sudo apt install libwebkit2gtk-4.1-0
   ```

2. **USB permissions:**

   ```bash
   sudo nano /etc/udev/rules.d/99-arduino-uno-q.rules
   ```

   Paste:

   ```
   SUBSYSTEM=="usb", ATTRS{idVendor}=="2341", MODE="0666", GROUP="dialout"
   SUBSYSTEM=="usb", ATTRS{idVendor}=="05c6", MODE="0666", GROUP="dialout"
   ```

   (2341 = normal Arduino USB mode, 05c6 = emergency download mode.)

   Reload and add your user to `dialout`:

   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   sudo usermod -a -G dialout $USER
   ```

   **Log out and back in** — the group change does not apply until you do.

3. Install App Lab:

   ```bash
   mkdir -p ~/Applications
   tar -xf ~/Downloads/ArduinoAppLab*.tar.gz -C ~/Applications
   ```

   Launch it with `~/Applications/<extracted-folder>/arduino-app-lab`.

### 1.2 Windows

1. Download the Windows installer from the software page and run it.
2. If Windows asks, **allow USB access** for App Lab.
3. Launch App Lab from the Start menu.
4. Nothing else to configure (adb/serial rules are a Linux-only concern).

### 1.3 macOS

1. Download the macOS package from the software page and install it.
2. Launch App Lab (Applications folder).
3. Nothing else to configure.

---

## 2. Board first setup (identical on all host OSes)

1. Start **Arduino App Lab** on the host PC.
2. Connect the UNO Q to the PC with the USB-C **data** cable
   (board side USB-C port). Boot takes a few seconds; the board may take up to
   **60 s** to appear. LED matrix: infinity symbol while booting, then a heart.
3. Click the **uno-q** tile with the "New Board" badge.

The wizard walks you through four steps:

1. **Keyboard layout + board name** — the name is also the network hostname.
2. **Wi-Fi** — pick your network, enter the password, wait for the green check.
3. **Linux password** — the password of the user `arduino` on the board.
   **Remember it** — you need it for SSH and `sudo` on the board.
4. **Updates** — click *Install updates* and wait. This pulls several packages
   and container images; it can take several minutes. Finish when it reports
   the board update succeeded.

After this, the board is on Wi-Fi and SSH is enabled.

---

## 3. Get a shell on the board

Two ways; use either.

### Option A — SSH (works from all host OSes)

All host OSes have a built-in SSH client (verify with `ssh -V`).
The host PC and the board must be on the **same Wi-Fi network**.

```bash
ssh arduino@<boardname>.local
```

- Use the board name you chose in Step 2.
- Type `yes` the first time, then enter the `arduino` password you set.

If `.local` (mDNS) does not resolve (common on some corporate or router setups),
open an ADB shell (Option B), run `hostname -I` on the board to get its IP, then use:

```bash
ssh arduino@<ip-address>
```

### Option B — ADB over USB

ADB gives shell access without any network. Install it on the host PC:

- **Linux:** `sudo apt-get install android-sdk-platform-tools`
- **Windows:** `winget install Google.PlatformTools`
- **macOS:** `brew install android-platform-tools`

Then:

```bash
adb devices      # board may take up to a minute to appear
adb shell
```

If the board has **not** been through the App Lab wizard yet, the shell asks
for a password — it is `arduino`. If you already did the wizard, use the
password you set. Exit with `exit`.

> `sudo` on the board asks for the `arduino` user's password (there is no
> passwordless sudo).

### Quick sanity check (inside the board shell)

```bash
cat /sys/firmware/devicetree/base/compatible | tr '\0' '\n'   # contains arduino,imola
free -h      # ~3.6 GB free RAM on the 4 GB board
df -h / /home/arduino
```

Expected: root partition `/` is **small (~10 GB)**; the big space
(~18 GB free) is on `/home/arduino`. That is exactly why Ollama below is
installed into `/home/arduino`.

---

## 4. Install Ollama on the board (the /home workaround)

**Do not** use the one-liner from ollama.com/download
(`curl -fsSL https://ollama.com/install.sh | sh`). It writes into `/usr`
(root partition), and the UNO Q's root partition is too small — the standard
install fails. Everything therefore goes into `/home/arduino` instead.

Run these **inside the board shell**. Steps 4.2–4.6 follow the proven
A. Tinivelli (@ITinto) procedure for this exact board.

### 4.1 Clean up a failed standard install (only if you tried it)

```bash
sudo rm -rf /usr/local/lib/ollama
```

### 4.2 Prerequisite (tiny package, fits on the root partition)

The Ollama arm64 release is a `.tar.zst` archive — the board needs `zstd`:

```bash
sudo apt update
sudo apt install -y zstd
```

### 4.3 Download and extract into /home/arduino/ollama

```bash
sudo mkdir -p /home/arduino/ollama
curl -fsSL https://ollama.com/download/ollama-linux-arm64.tar.zst \
    | sudo tar x --zstd -C /home/arduino/ollama
```

(~1.6 GB download; give it a few minutes on Wi-Fi.)

### 4.4 Make the `ollama` command available system-wide

```bash
sudo ln -s /home/arduino/ollama/bin/ollama /usr/local/bin/ollama
```

### 4.5 Dedicated service user, models kept on the big partition

```bash
sudo useradd -r -s /bin/false -U -m -d /home/arduino/ollama ollama
sudo usermod -a -G ollama arduino
```

### 4.6 systemd service (non-interactive — safe over SSH/ADB)

Create the file without an editor:

```bash
sudo tee /etc/systemd/system/ollama.service > /dev/null <<'EOF'
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="PATH=/home/arduino/ollama/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
Environment="OLLAMA_MODELS=/home/arduino/ollama/models"
Environment="LD_LIBRARY_PATH=/home/arduino/ollama/lib/ollama"

[Install]
WantedBy=multi-user.target
EOF
```

Then:

```bash
sudo chown -R ollama:ollama /home/arduino/ollama
sudo systemctl daemon-reload
sudo systemctl enable ollama     # auto-start at boot
sudo systemctl start ollama
```

### 4.7 Verify

```bash
sudo systemctl status ollama     # must show: Active: active (running) ... green
ollama --version
```

If `status` is green and the version prints, the service is up and listening
on port 11434.

---

## 5. Install SmolLM

Still in the board shell, with Wi-Fi connected. The model is stored under
`/home/arduino/ollama/models` (the big partition) via the `OLLAMA_MODELS`
setting above.

**Main install (4 GB board, ABX00173):**

```bash
ollama pull smollm2:1.7b
```

- ~1.8 GB download. Use `ollama pull` for setup: it is non-interactive and safe
  over SSH. `ollama run <tag>` also pulls, but then opens a chat prompt; test it
  with e.g. `why do pumps fail?` and quit with `/bye`.
- **Model choice to settle before the board test:** `plan.md` and
  `skill_data.md` name `smollm2:135m` for the host chain. This section installs
  `smollm2:1.7b`. Pick one tag for the UNO Q and use it everywhere.

**Smaller variants** (all one tag swap, same command pattern `ollama run <tag>`):

| Tag | Size | Use when |
|-----|------|----------|
| `smollm2:1.7b` | 1.8 GB | **default for the 4 GB board** |
| `smollm2:1.7b-instruct-q4_K_M` | 1.1 GB | want less RAM/disk, faster replies |
| `smollm2:360m-instruct-q4_K_M` | 271 MB | quick smoke-test / tight space |
| `smollm2:135m-instruct-q4_K_M` | 105 MB | the 2 GB board variant (ABX00162) only |

After the model is pulled, **no internet is needed to run inference**.

### Check it

```bash
ollama list     # installed models
ollama ps       # shows 100% CPU while a model is loaded (no GPU/NPU — expected)
```

**Set expectations:** the QRB2210 (quad Cortex-A53) is an efficiency core.
Speed is not measured in this project yet: expect the 1.7b model to be slow
on this board (general estimates for ~1B models on this CPU are around 5 tokens/s).
That is fine for this project — SmolLM here is an occasional analysis layer
over pump telemetry, not a chatbot.

### API for the pump-sensor app

The service exposes an OpenAI-compatible endpoint on the board itself:

```
http://127.0.0.1:11434
```

Python on the MPU (the pilot app, to-do M6) can POST to
`http://127.0.0.1:11434/api/generate` or `/v1/chat/completions`. Quick test
from the board shell:

```bash
curl http://localhost:11434/api/generate -d '{"model":"smollm2:1.7b","prompt":"Hello","stream":false}'
```

---

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Board never appears in App Lab | Wrong cable (charge-only) or Linux permission issue — check data cable first; on Linux confirm the udev rules and that you **logged out/in** after `usermod`. |
| `adb devices` shows nothing | Wait up to 60 s; try another USB port/cable. |
| `ssh: connect to host ...local port 22: ...` | mDNS blocked on your network — connect via ADB once, run `hostname -I` on the board, then `ssh arduino@<ip>`. |
| `ssh` refused before first setup | SSH is enabled **by the App Lab wizard**; do Step 2 first, or enable via ADB with `arduino-app-cli system network-mode enable` (check this command against current App Lab docs). |
| Standard Ollama install failed / `No space left` on `/` | Remove leftovers: `sudo rm -rf /usr/local/lib/ollama`; then use Section 4 (installs into `/home/arduino`). |
| `tar: zstd: Cannot exec` | Run `sudo apt install -y zstd` (4.2) and retry 4.3. |
| `sudo: a password is required` | Enter the `arduino` password you set in the wizard; run the installer steps from an interactive shell, not a non-interactive session. |
| Root partition full after updates | `df -h /` to confirm; avoid installing big packages on `/`; big things belong in `/home/arduino` (as done here). |

---

## 7. Pilot test on the board (replay, no sensors)

Goal: run the pilot monitor and the web dashboard on the UNO Q with the
fictional starter data. This does **not** use the logic-box UART link (not
built yet) and does **not** need Ollama. Run every command from the repo
root on the board unless marked as host.

### 7.1 Check Python on the board

```bash
python3 --version     # must be 3.11 or newer (the code uses tomllib)
```

If it is older, stop and tell the team before installing anything.

### 7.2 Copy the project (host)

Commit your changes first: `git archive` packs the last commit only.

```bash
git archive --format=tar HEAD | ssh arduino@<board>.local 'mkdir -p ~/pump-sensor-project && tar -xf - -C ~/pump-sensor-project'
scp data/starter/telemetry.csv.gz arduino@<board>.local:~/pump-sensor-project/data/starter/
```

`telemetry.csv.gz` is not in git (ignored by `.gitignore`), so copy it
explicitly, as above.

### 7.3 Install the pinned dependencies (board)

```bash
cd ~/pump-sensor-project
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

If pip has to build pandas or scipy from source (no arm64 wheel for this
Python), it can be slow or fail. Record the error and stop.

### 7.4 Run the tests (board)

```bash
for f in tests/test_*.py; do .venv/bin/python "$f" || break; done
```

All seven files should print PASS. Record any failure.

### 7.5 Run the pilot (board)

```bash
.venv/bin/python scripts/pilot_run.py --speed 0       # as fast as the board can go
```

`--speed N` replays N data-seconds per wall-second (for example `--speed 3600`
is one hour of data per second). The run writes `pilot/state.json` and
`pilot/predictions.jsonl`. Check with `cat pilot/state.json | head -40`.

### 7.6 Serve the dashboard on the LAN (board, second SSH session)

```bash
.venv/bin/python scripts/web_ui.py --data data/starter --host 0.0.0.0 --port 8000
```

From a PC on the same network, open `http://<board>.local:8000`, or use the
board's IP. The dashboard has **no authentication**: use it only on a trusted
network. The pilot panel reads `pilot/state.json`, so the pilot can run in the
first session while the dashboard runs in the second.

### 7.7 Record the result

Note these for the to-do: total wall time, `free -h` during the run, any
errors, and whether the pilot panel shows the expected statuses. Stop
services with Ctrl+C.

## Sources (not re-checked during the Nov 2026 proofread; re-check before relying on them)

- App Lab download & system requirements: arduino.cc/en/software (`#app-lab-section`)
- Linux setup (libwebkit2gtk, udev rules, dialout): docs.arduino.cc/software/app-lab/setup/linux/
- First setup wizard / SBC mode: docs.arduino.cc/tutorials/uno-q/ (user-manual, single-board-computer)
- SSH: docs.arduino.cc/tutorials/uno-q/ssh · ADB: docs.arduino.cc/tutorials/uno-q/adb
- Board resources & root-partition size: docs.arduino.cc/tutorials/uno-q/llama-cpp
- Ollama `/home` workaround for UNO Q: blog.tinivelli.com/installing-ollama-on-arduino-uno-q/
  (confirmed by projecthub.arduino.cc "Build Smarter with Claude Code & Ollama on UNO Q"
  and the UNO Q eMMC layout on forum.arduino.cc)
- SmolLM2 tags/sizes: ollama.com/library/smollm2 (checked when written: `1.7b` = 1.8 GB,
  `1.7b-instruct-q4_K_M` = 1.1 GB, `360m-instruct-q4_K_M` = 271 MB,
  `135m-instruct-q4_K_M` = 105 MB; arm64 release asset = `tar.zst` only)
