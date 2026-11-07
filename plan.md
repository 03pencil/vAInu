# Project Plan

## Goal

Pump sensors send telemetry to a logic box, which delivers it to an Arduino UNO Q. The UNO Q runs a local LLM and outputs analysed data. The Arduino only receives data from the pump logic circuit and outputs results elsewhere; it has no other inbound connections.

## Challenge & evaluation

vAInu is built for **RETROFIT AI — Make Existing Machines Intelligent** (Since AI
Hackathon 2026, Turku; challenge owner Business Turku, technical sparring
partner Elomatic). Full rules live in the organizer package:
`/home/koodikone/since/BusinessTurku_SinceAI2026_FINAL_BUILDER_PUBLISH/RETROFIT_AI_PARTICIPANTS_2026/`
(`CHALLENGE_BRIEF.md`, `BENCHMARK_RULES.md`, `TECHNICAL_MODEL.md`,
`RETROFIT_FEASIBILITY.md`). The task: turn existing / low-cost sensor data from
an existing motor-driven cooling-water pump into an operator-assist layer that
detects developing issues early, explains evidence and uncertainty, and
recommends human-approved interventions — **no hardware writes, no production
control, read-only integration, advisory only**.

### Official judging criteria — how vAInu addresses each

| Criterion | Weight | vAInu workstream |
|---|---|---|
| Business usefulness | 25 % | Tie early-warning lead time and fault-type recall to avoided unplanned stops vs planned repairs (business-case logic in `RETROFIT_FEASIBILITY.md`: ~EUR 4.5 k installed, ~1 yr illustrative payback). Alerts must be actionable by a watchkeeper / maintenance planner: evidence + recommendation + stated uncertainty, not a bare score. |
| Technical validity & measured performance | 25 % | Measured composite score (below). Targets: beat baseline **B1 mode-aware z (78.0 validation)**. KPIs tracked in `scripts/sanity_gate.py` (lead time vs deadline, benign FAR) plus the benchmark scorer (F1, timeliness, fault-type recall, class recall, alert burden). |
| Reliability / safety | 20 % | Sensor-vs-machine fault separation (a drifting transmitter must not trigger a machine claim or hide a real fault); calibrated confidence; honest `UNKNOWN` when the cause is unclear; advisory-only; no claims of certified safety or class approval. |
| Low-cost retrofit feasibility & transfer | 20 % | Read-only integration (UNO Q receives from logic box, no other inbound), edge/offline detection with local buffering, per-tier detection strategies (T0 legacy / T1 retrofit / T2 full, ~EUR 2.1–3.1 k BOM per pump), transfer story to other rotating machines via profile + tier-aware envelopes. |
| Working demo & clarity | 10 % | Minimal web UI on the local network showing live values, predictions, evidence and uncertainty; short demo script; honest limitations (synthetic data, no field evidence). **The UI is built by a teammate** — this repo treats it as an interface contract: backend emits structured predictions (fault type / class / confidence / evidence), UI consumes them. |

### Measured performance target (composite score 0–100)

```
composite = 100 x (0.35 F1 + 0.20 timeliness + 0.25 fault-type recall
                    + 0.10 class recall + 0.10 alert burden)
```

- Reference baselines (validation split): B0 SCADA alarms 23.1, B1 mode-aware z
  **78.0**, B3 isolation forest 69.2. **Target: beat B1.**
- Submission format: `submission_template/predictions_template.csv` —
  `asset_id, alert_time_utc, event_class (MACHINE|SENSOR), fault_type,
  confidence (0-1), evidence, recommended_action`.
- Scoring semantics that shape the design: alerts < 5 min apart on one asset
  merge into a burst (a burst naming several fault types earns no fault-type
  credit); excess repeats (> 1 reminder per 12 h) count as false alerts;
  event windows start at detectable − 6 h; lead time = deadline − first alert.
- Hard rules: **causal operation only** (an alert at time t may use data
  timestamps <= t; organizers may re-run on test telemetry truncated at random
  cut points), no tuning or hand-labelling on test data. Train = PUMP-01..07,
  validation = PUMP-08/09, test = PUMP-10..12 (unlabeled).

### Constraints the challenge imposes on the architecture

- **Instrumentation tiers decide what is detectable.** T0 legacy pumps cannot
  see early bearing damage (no vibration channel); T1 retrofit updates the
  wireless vibration/temperature sensor only every 300 s, so short events can
  hide between samples; T2 full sees everything except direct seal leak.
  Detection strategy must be per-tier: on T0, avoid vibration-based claims
  and rely on hydraulic residuals; on T1, mask sparse NaNs natively.
- **Sensor-vs-machine firewall.** Fault taxonomy: MACHINE (BEARING_WEAR,
  SUCTION_STRAINER_CLOGGING, CAVITATION, DISCHARGE_RESTRICTION, MISALIGNMENT,
  IMBALANCE, IMPELLER_WEAR, AIR_ENTRAINMENT) vs SENSOR (SENSOR_DRIFT,
  SENSOR_STUCK, SENSOR_CALIBRATION_SHIFT, SENSOR_NOISE_SPIKES,
  COMMUNICATION_LOSS) vs UNKNOWN. Test data include a drifting suction
  transmitter masking a real clog — the detector must flag the channel as
  suspect instead of claiming a machine fault.
- **Operating-condition normalization.** Deviations must be judged per
  operating mode / duty demand / speed regime; start-up ramps, load changes,
  heavy weather and voltage sags are labeled benign windows and must not
  become alerts (they erode operator trust and cost points).
- **False-alert economy.** The composite penalizes alert burden; a low-
  confidence `UNKNOWN` alert is safer than a confidently wrong fault type.

Per-criteria tasks are tracked in [`to-do.md`](to-do.md).

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
6. Deploy: App Lab app on UNO Q; MCU receives sensor data from logic box, MPU runs inference, outputs analysed data. — **pilot replay path done** (`src/pilot.py`, `scripts/pilot_run.py`, pilot panel in the web UI); UART and board test pending (`arduino_uno_q_install.md` section 7).
7. Test on hardware; iterate.

## Milestones

- M1: Data exploration notebook/script done. — **done**
- M2: Baseline model metrics on validation. — baseline KPIs recorded (lead time + FAR)
- M3: App Lab app running on UNO Q (receive -> infer -> output). — **in progress**: replay pilot runs on the host; board bench test next.
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
2. Physics residuals (gold features, parameters come from `assets.csv`).
   IMPLEMENTED (`src/physics.py`): hydraulic residual from the
   affinity-scaled curve, curve-inversion flow estimate +
   power-based speed-ratio estimate, efficiency proxy, thermal lag
   residuals; wired into the gate as extra z channels.
   - hydraulic residual: measured head vs pump-curve H(r,Q), up with
     DISCHARGE_RESTRICTION, down with IMPPELLER_WEAR
   - efficiency proxy: hydraulic power / motor_power_kw
   - strainer dP signal: suction pressure deviation
   - thermal rise with first-order lag (bearing/winding tau from
     simulation_assumptions.md)
3. Trend extrapolation -> time-to-limit (long-scale prediction; implemented in `src/trend.py`): fit
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
