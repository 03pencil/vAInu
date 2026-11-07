# Project Plan

## Goal

Pump sensors send telemetry to a logic box, which delivers it to an Arduino UNO Q. The UNO Q runs a local LLM and outputs analysed data. The Arduino only receives data from the pump logic circuit and outputs results elsewhere; it has no other inbound connections.

## Architecture

- Pump sensors -> logic box (collect/forward telemetry).
- Logic box -> Arduino UNO Q (single inbound data path; MCU receives, MPU runs LLM inference).
- Arduino UNO Q -> minimal web UI (served by MPU, local network) showing live values + predictions; no inbound from elsewhere.

## Hardware (BOM)

Minimal hardware only — see [`bom.md`](bom.md). Key notions:

- UNO Q board **provided** (Majos Hacking League); prefer the ABX00173 4 GB variant for SmolLM.
- Power must come from a dedicated 5 V / 3 A USB-C wall adapter, not a PC port.
- USB-A→C cable for one-time setup (ADB / App Lab) from the host PC.
- Wi-Fi is built in: no antenna, no hub, no monitor. Web UI runs headless.
- Logic box → MCU link is plain 3.3 V UART (TX/RX/GND jumper wires); level shifter only if the logic box outputs 5 V.
- Excluded on purpose: camera, bricks, display, SD, enclosure.

## Phases

1. Explore data: load starter telemetry with pandas, inspect channels, asset tiers.
2. Baseline analysis: compute simple stats, plots (matplotlib) per asset/channel.
3. Feature engineering: rolling stats, vibration trends, pressure/flow ratios.
4. Model: train a lightweight anomaly/fault detector on benign windows; validate on events.
5. Shrink to smoll for edge deployment (GGUF via llama.cpp) running on UNO Q MPU.
6. Deploy: App Lab app on UNO Q; MCU receives sensor data from logic box, MPU runs inference, outputs analysed data.
7. Test on hardware; iterate.

## Milestones

- M1: Data exploration notebook/script done.
- M2: Baseline model metrics on validation.
- M3: App Lab app running on UNO Q (receive -> infer -> output).
- M4: End-to-end demo: pumps -> logic box -> UNO Q -> minimal web UI.
