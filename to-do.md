# To-Do

> `data/` is read-only. Never edit, overwrite, or delete anything inside it.

## Next up

1. Reduce false alarms on benign data (target under 2 %).
2. Add the Mahalanobis score and the logistic fault classifier.
3. Make the pilot score every asset, including PUMP-03, -04, and -08 (still `unknown`).
4. Board test step 2: run SmolLM on the UNO Q.

## Open tasks

### Data and features
- [ ] Plot time series per asset and channel.
- [ ] Vibration trend features.
- [ ] Pressure/flow ratios.
- [ ] Save the feature dataset.
- [ ] Condition channel behavior on duty demand.
- [ ] Fault-type likelihood vector from evidence channels.

### Detector
- [ ] Mahalanobis anomaly score (numpy only).
- [ ] Logistic-regression fault classifier (numpy only).
- [ ] Horizons: 10 min, 1 h, days. State-machine debounce.
- [ ] Precision, recall, and F1 once a classifier exists.

### SmolLM narration
- [ ] Situation-report serializer (fixed text from the pilot record).
- [ ] `scripts/narrate.py`: one SmolLM call per alarm, saved to `pilot/analysis.jsonl`.
- [ ] Validator: reject non-JSON, numbers that are not in the input, and labels outside the taxonomy.
- [ ] `[llm]` config section, off by default, with stub-server tests.
- [ ] Narration panel in the web UI.
- [ ] Later: measured fault-type choice against `events_train.csv`.
- [ ] Later: use `maintenance.csv` operator notes.

### Feedback loop
- [ ] Prediction log (inputs, score, time-to-limit, timestamp).
- [ ] Join outcomes: alarms, event deadlines, confirmed maintenance.
- [ ] Periodic recalibration and bias correction per fault type.
- [ ] Show early-warning lead time improving over time.

### Edge (SmolLM on the board)
- [ ] Export SmolLM to GGUF with llama.cpp.
- [ ] Quantize to the smallest usable size.
- [ ] Benchmark inference speed on the UNO Q.

### Board and deployment
- [ ] UART reader on the board. The current `UartFeed` is a stub until the logic box exists.
- [ ] Add physics channels and time-to-limit to the pilot monitor.
- [ ] Create the App Lab app skeleton.
- [ ] MCU receiver for logic-box data.
- [ ] Run inference on the MPU with the received data.
- [ ] Output analysed data from the UNO Q.
- [ ] Serve the web UI on the local network with live values and predictions.

### Testing and demo
- [ ] End-to-end test: pumps → logic box → UNO Q → web UI.
- [ ] Fix issues found on hardware.
- [ ] Re-run metrics after changes.
- [ ] Final demo.

### Open decision
- [ ] Choose the default data tier. `config.toml` points at `data/full`, which has no telemetry in this repo.

## Done

- Load and check the telemetry (starter tier), with quality flags and asset joins.
- Label benign and event windows.
- Robust healthy-range math, with a fleet fallback and a rolling surface.
- Physics residuals (pump curve, efficiency, thermal lag).
- Trend forecast to alarm and trip limits, with an uncertainty band.
- KPI gate and baseline numbers (see [`plan.md`](plan.md)).
- Pilot replay, with the UART frame format and parser ready.
- Web dashboard v1: asset status, values, deviations, chart, replay, pilot panel.
- Pinned requirements (pandas, numpy, scipy, pyarrow).
- Board test step 1 (2026-11-07): all tests pass on the UNO Q, and the dashboard is reachable on the local network.
- SmolLM model chosen: `smollm2:1.7b`. The earlier host chain (smollm2 → mistral → gemma4) is retired.
