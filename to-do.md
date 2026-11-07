# To-Do

> **Rule:** `data/` is read-only. Never edit, overwrite, regenerate, or delete
> anything inside it. See `skills/python-style.md` and `skill_data.md`.

## M1: Data exploration
- [x] Working implementations: `data_input`, `math`, `main` done;
  `src/ui.py` is still a matplotlib stub (unused; the dashboard is
  `src/web_ui.py`).
- [x] Set up Python environment / install pandas, matplotlib.
- [x] Load telemetry from the configured tier (full/starter) into a DataFrame.
- [x] Inspect channel names and data types.
- [x] Inspect asset tiers and counts (`main.py` prints instrumentation
  tiers + channel counts; 5 assets on starter tier: 3x T1_RETROFIT,
  1x T0_LEGACY, 1x T2_FULL, split train x3 / validation x1).
- [x] Save exploration script (`tests/test_data_input.py` — exploration
  facts land there and in `main.py` output).
- [x] Confirm all settings come from `config.toml` — no hard-coding.

### Build order (next steps, updated 2026-11-07)
1. FAR reduction toward < 2% (debounce is in; richer features next).
2. Mahalanobis score + logistic fault classifier (Layer 2).
3. Pilot monitor: rolling-envelope fallback so every asset gets scored.
4. Bench test on the UNO Q (install manual section 7).

### Findings (2026-11-07)
- [x] Record the data blocker in `plan.md`: `data/full` is missing the
  telemetry parquets / features_1min.parquet / vibration_snapshots
  (manifest.json claims them, they are not on disk). Only real telemetry
  is `data/starter/telemetry.csv.gz` (10 s grid).
- [x] Decide the stack rule: pure numpy/scipy/pandas — no sklearn.
- [x] Record the three-layer prediction architecture in `plan.md`
  (features -> detector -> SmolLM chain -> feedback loop).
- [x] Switch `config.toml` `data_dir` to `data/starter` until the full
  parquet files exist.

## M0: Unblock the data layer (pure numpy, prerequisite for everything)
- [x] `data_input.load_telemetry()`: read `telemetry.csv.gz` with pandas,
  parse `timestamp_utc` as UTC, sort by asset_id + timestamp.
- [x] Keep `quality_flags` as an int bitmask + helpers
  (`has_flag`, per-bit names from data_dictionary: 1 COMM_LOSS,
  2 OUT_OF_RANGE, 4 STALE, 8 BAD_SENSOR_STATUS, 16 STARTUP_INHIBIT).
- [x] Route missing full-tier parquets gracefully (clear error, fallback
  ready when files arrive).
- [x] `load_assets()` + per-asset channel mask from `channels_available`
  (T0 pumps have only 4 channels — honor instrumentation tiers).
- [x] Rework `split_channels()` for the wide-format telemetry
  (long-format `channel` column does not exist).
- [x] Verify end-to-end via `main.py` on the starter tier
  (301,393 rows, 5 assets; `tests/test_data_input.py` all pass).

## M2: Baseline analysis
- [x] Compute basic stats (mean, std, min, max) per asset/channel.
- [ ] Plot time series per asset/channel.
- [x] Identify normal vs event windows (`src/labels.py`: benign /
  fault_warming / fault_detectable / fault_undetectable / unknown).
- [x] Document baseline findings (`scripts/sanity_gate.py`, see KPI box
  under M4).

## M3: Feature engineering
- [x] Compute rolling mean/std per channel (`group_rolled`,
  `rolling_robust_z` in `src/math.py`).
- [ ] Compute vibration trend features.
- [ ] Compute pressure/flow ratios.
- [ ] Store feature dataset.

## M4: Model
- [x] Define prediction algorithm (anomaly/fault scoring logic for the
  LLM): deterministic z-score scoring defined + implemented; LLM-side
  verdict wiring tracked in the Layer 3 boxes below.
- [x] Label benign vs event windows (`src/labels.py`).
- [ ] Train lightweight anomaly/fault detector on benign windows —
  robust envelope detector done; Mahalanobis + classifier pending
  (Layer 2 boxes).
- [x] Validate on event windows (sanity gate evaluates every labeled
  event on train + validation assets).
- [ ] Record metrics (precision, recall, F1) — currently lead time +
  FAR are recorded; confusion-matrix metrics once a classifier exists.

### Layer 1 math (deterministic, numpy only)
- [x] Robust healthy envelope: median/MAD per asset x channel x operating
  mode (`robust_stats`, `modified_zscores` in `src/math.py`), with
  fleet-level fallback (`merged_stats`) for assets that are fully
  fault-labeled and alone in their profile.
- [x] Self-adaptive trailing z as second detection surface
  (`rolling_robust_z`) for assets with no clean envelope at all.
- [ ] Condition channel behavior on `operating_context.duty_demand_pct`.
- [x] Physics residuals from `assets.csv` curve parameters
  (`src/physics.py`): hydraulic residual (rated-affinity curve
  H(r,Q) = r^2*H0 - a*Q^2, head = dP*kPa/(SG*9.80665)), curve-inversion
  flow estimate for meter-less assets (with power-based speed-ratio
  estimate r=(P/P_rated)^(1/3) for VFD pumps lacking a speed channel),
  efficiency proxy (idle-masked), thermal first-order lag residuals
  (bearing/winding, tau from simulation_assumptions.md), per-asset
  `physics_quality` tag (exact/estimated/none). Gate rerun: detection
  KPIs unchanged (already saturated) but residuals now give the
  interpretable, curve-consistent evidence the fault-type vector and
  the SmolLM report need.
- [x] Trend extrapolation: trailing 6-24 h drift fit -> time-to-alarm /
  time-to-trip with uncertainty band (`src/trend.py`,
  `scripts/trend_forecast.py`, tests pass). Not yet part of the sanity-gate
  KPIs.
- [ ] Fault-type likelihood vector from evidence-channel signatures.

### Baseline KPI numbers (starter tier, 2026-11-07)
Recorded so later layers can be compared against them:
- [x] Sanity gate run: ALL 20 events detected (0 missed),
  10/10 deadline-bearing events caught before deadline, median lead
  1.6 h, best leads 119.7 h (PUMP-04 BEARING_WEAR), 100.2 h (IMBALANCE),
  38.3 h (PUMP-08 SUCTION_STRAINER_CLOGGING), 31.8 h (PUMP-06 clogging).
- [x] Benign false-alarm rate (z=3, smoothed over 60 samples):
  6.4% envelope surface only, 8.0% rolling surface only,
  13.4% union before physics features (738/5,504); 13.8% with the
  physics channels added (759/5,504) — negligible FAR cost for the
  interpretability gained.
- [ ] Reduce FAR (debounce/state machine, richer features) — target < 2%.

### Layer 2 detector (learned, numpy only)
- [ ] Mahalanobis anomaly score vs benign windows (numpy only).
- [ ] Hand-written logistic-regression fault classifier (GD/lstsq).
- [ ] Horizons: 10-min / 1 h / days (RUL-style); state-machine debounce.

### Layer 3 SmolLM chain
- [ ] Situation-report serializer (fixed ~200-token text format).
- [ ] Wire `~/chain_models.py` analysis mode -> structured JSON verdict
  constrained to the fault taxonomy from events_train.csv.
- [ ] Fuse `maintenance.csv operator_observation` free text.

### Feedback loop (improving over time)
- [ ] Prediction log (inputs, score, RUL claim, timestamp).
- [ ] Outcome joins: alarms (fast), events deadlines (medium),
  maintenance CONFIRMED (ground truth).
- [ ] Periodic recalibration + learned bias correction per fault type.
- [ ] KPI: early-warning lead time vs detectable_utc, shown improving.

## M5: Shrink for edge (GGUF)
- [ ] Export model to GGUF via llama.cpp.
- [ ] Quantize to smallest viable size.
- [ ] Benchmark inference speed on target hardware.
- [x] Clarified: GGUF applies to SmolLM itself; the detector is classical
  math/ML and runs as plain Python on the UNO Q MPU.

## M6: Deploy on UNO Q
- [x] Pilot replay path (no hardware): `src/feed.py` ReplayFeed on starter
  telemetry, `src/pilot.py` streaming monitor, `scripts/pilot_run.py`
  writes `pilot/state.json` + `pilot/predictions.jsonl`.
- [x] UART frame contract + parser (`src/feed.py` `parse_frame`, JSON line).
- [ ] UART reader on PC/MPU (`UartFeed` is a stub until the logic box exists).
- [ ] Pilot monitor: rolling-envelope fallback for assets with no clean
  envelope (PUMP-03/04/08 report `unknown` today).
- [ ] Pilot monitor: physics channels and trend time-to-limit.
- [x] Serve pilot state in the web UI: `/api/pilot` route and pilot panel
  in `src/web_ui.py`, reading `pilot/state.json`.
- [x] `requirements.txt` with pinned pandas / numpy / scipy (runtime).
- [x] Proofread `arduino_uno_q_install.md`; added section 7 (pilot test on
  the board).
- [x] Bench test on the UNO Q per `arduino_uno_q_install.md` section 7, step 1
  (no LLM) — 2026-11-07. Board `picool` (10.20.3.13), Python 3.13.5,
  3.6 GB RAM. Installed pinned requirements (pandas 3.1.1, numpy 2.5.4,
  scipy 1.18.1, pyarrow 26.0.1). All 38 tests pass on the board. Pilot
  replay: 1 min 43 s wall time, ~560 MB used, same results as the host run.
  Dashboard served on LAN at port 8000 and reachable from the PC.
  Issues found:
  - `config.toml` `data_dir` is `data/full`, which has no telemetry in this
    repo; the board test used `data/starter` through a board-only edit (not
    committed). Decide the default tier with the team.
  - Dashboard was first started in the foreground of an SSH session and
    stopped when the session closed; restarted with `nohup`.
  - PUMP-03, -04, -08 are still `unknown` after the envelope-fallback commit
    `946a8ea`.
- [x] Decide the SmolLM tag for the UNO Q: `smollm2:1.7b` (better structured
  output; fits the 4 GB board). `plan.md` / `skill_data.md` still name
  `smollm2:135m` for the host chain; update them when the SmolLM layer lands.
- [x] Board test step 1: pilot + web UI without LLM (manual section 7), 2026-11-07.
- [ ] Board test step 2: SmolLM layer on the board (Ollama install per manual
  sections 4–5, serializer, alarm-triggered call, JSON validation, fallback).
- [x] First local web UI prototype (`scripts/web_ui.py`, `src/web_ui.py`):
  asset status, latest values, top deviations, channel chart, replay;
  stdlib server only.
- [ ] Create App Lab app skeleton.
- [ ] Implement MCU receiver for sensor data from logic box.
- [ ] Wire MPU to run inference on received data.
- [ ] Output analysed data from UNO Q.
- [ ] Serve minimal web UI on local network (live values + predictions).

## M7: Test & iterate
- [ ] Test end-to-end: pumps -> logic box -> UNO Q -> web UI.
- [ ] Fix issues found during hardware test.
- [ ] Re-run metrics after changes.
- [ ] Finalize demo.