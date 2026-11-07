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

1. Explore data: load starter telemetry with pandas, inspect channels, asset tiers. — **DONE** (M0/M1 boxes in [`to-do.md`](to-do.md))
2. Baseline analysis: compute simple stats, plots (matplotlib) per asset/channel. — stats + labeled windows + KPI gate done; plots still pending
3. Feature engineering: rolling stats, vibration trends, pressure/flow ratios. — rolling robust z done; physics residuals / ratios pending (Layer 1)
4. Model: train a lightweight anomaly/fault detector on benign windows; validate on events. — robust envelope validated (20/20 events); learned detector pending
5. Shrink to smoll for edge deployment (GGUF via llama.cpp) running on UNO Q MPU. — applies to SmolLM itself; detector stays plain Python (see M5 in to-do)
6. Deploy: App Lab app on UNO Q; MCU receives sensor data from logic box, MPU runs inference, outputs analysed data.
7. Test on hardware; iterate.

## Milestones

- M1: Data exploration notebook/script done. — **done**
- M2: Baseline model metrics on validation. — baseline KPIs recorded (lead time + FAR)
- M3: App Lab app running on UNO Q (receive -> infer -> output).
- M4: End-to-end demo: pumps -> logic box -> UNO Q -> minimal web UI.

## Prediction architecture (three layers)

The LLM must not do the numeric forecasting itself. It sits on top as the
reasoning / narration layer:

```
telemetry -> feature math (numpy/pandas, deterministic)
          -> small detector (scores + time-to-limit forecast)
          -> compact situation report (templated text)
          -> SmolLM chain: diagnosis + recommendation + confidence (JSON)
          -> prediction log -> periodic retrain -> improving over time
```

Progress: layer 1 item 1 (healthy envelope + fleet fallback + rolling
second surface) is implemented and KPI-gated; layer 1 items 2-4, layer 2,
layer 3 and the feedback loop are pending — track them in
[`to-do.md`](to-do.md).

Stack rule: pure numpy/scipy/pandas (no sklearn). LLMs already available
locally via `python3 ~/chain_models.py <mode> "<text>"` (ollama:
smollm2:135m -> mistral -> gemma4:e2b).

### Layer 1 - predictive math (deterministic)

1. Adaptive healthy envelope: per asset x channel x operating_mode,
   robust median/MAD from benign windows + own recent history;
   z-score is mode-conditioned. IMPLEMENTED: robust_stats +
   modified_zscores + fleet fallback (merged_stats, profile-level) +
   self-adaptive rolling second surface (rolling_robust_z). PENDING:
   conditioning on `operating_context.duty_demand_pct` (load
   matters: normal at 60% demand differs from 90%).
2. Physics residuals (gold features, parameters come from `assets.csv`):
   - hydraulic residual: measured head vs pump-curve H(r,Q), up with
     DISCHARGE_RESTRICTION, down with IMPPELLER_WEAR
   - efficiency proxy: hydraulic power / motor_power_kw
   - strainer dP signal: suction pressure deviation
   - thermal rise with first-order lag (bearing/winding tau from
     simulation_assumptions.md)
3. Trend extrapolation -> time-to-limit (long-scale prediction): fit
   drift over trailing 6-24 h, solve crossing of alarm/trip limits,
   output tz + uncertainty band -> "vibration hits alarm in ~38 h".
4. Fault-type likelihood vector from evidence signatures
   (events `evidence_channels` = which channels light up per fault).

### Layer 2 - small learned detector

- Mahalanobis anomaly score vs benign windows (numpy, no deps).
- Fault classifier (logistic regression / GD) over 10-min window
  features, labeled via event interval joins.
- Horizons: 10-min (fast anomalies), 1 h (trends), days (RUL-style).
- State machine debouncing (ringing -> confirmed -> escalating).

### Layer 3 - SmolLM chain (reasoning + narration)

- Python summarizes windows into a fixed ~200-token report.
- chain_models.py analysis mode -> structured JSON verdict:
  {fault_suspected, evidence, recommended_action, urgency, confidence},
  constrained to the fault taxonomy from events_train.csv.
- Fuses free-text `maintenance.csv operator_observation` (may be wrong -
  demo of LLM judgment vs rule engine).

### Improving over time (feedback loop)

- Log every prediction (inputs, score, RUL claim, timestamp).
- Outcomes: alarms raised/cleared (fast), events end/deadline (medium),
  maintenance CONFIRMED diagnosis (slow ground truth).
- Periodic recalibration: refresh envelopes, refit classifier, learn
  trend->time-to-limit bias correction per fault type.
- KPI on the web UI: early-warning lead time (detection time vs
  detectable_utc) improving week over week.

### Data blocker (found 2026-11-07)

- `data/full` is missing the heavy files its manifest.json claims
  (telemetry parquets, features_1min.parquet, vibration_snapshots).
- Only real telemetry on disk: `data/starter/telemetry.csv.gz` (10 s grid).
- Therefore config.toml points at `data/starter` until full parquets arrive.
- Sparse channels (e.g. bearing temp every 300 s on T1 retrofit) are
  NaN-heavy; all math must mask NaN natively.

## Phase 1 - data foundation (pure numpy)

Status: DONE (2026-11-07). Delivered: real `load_telemetry` (UTC parse,
quality-flag bitmask, asset joins), `labels.py` labeled windows,
robust envelope math + fleet fallback in `math.py`, and the
`scripts/sanity_gate.py` KPI gate. Baseline: 20/20 events detected,
10/10 deadline events early (median lead 1.6 h), benign FAR 6.4 %.

1. `data_input.load_telemetry()`: read telemetry.csv.gz with pandas, UTC
   timestamp parsing, sorted by asset/time, quality_flags as int mask.
2. Asset/channel masks from `assets.channels_available`.
3. Labeled-window alignment: benign + event intervals -> derived label
   per row (benign / pre-event / active / post-repair).
4. First math: robust stats (median/MAD), rolling robust z-scores,
   10-min window aggregation (matches benchmark detectability).
5. Sanity gate: lead time vs detectable_utc + benign false-alarm rate
   reported for a few labeled events. These are the KPIs all later
   layers must beat.
