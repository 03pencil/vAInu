# To-Do

## M1: Data exploration
- [ ] Set up Python environment / install pandas, matplotlib.
- [ ] Load starter telemetry into a DataFrame.
- [ ] Inspect channel names and data types.
- [ ] Inspect asset tiers and counts.
- [ ] Save exploration notebook/script.

## M2: Baseline analysis
- [ ] Compute basic stats (mean, std, min, max) per asset/channel.
- [ ] Plot time series per asset/channel.
- [ ] Identify normal vs event windows.
- [ ] Document baseline findings.

## M3: Feature engineering
- [ ] Compute rolling mean/std per channel.
- [ ] Compute vibration trend features.
- [ ] Compute pressure/flow ratios.
- [ ] Store feature dataset.

## M4: Model
- [ ] Define prediction algorithm (anomaly/fault scoring logic for SmolLM).
- [ ] Label benign vs event windows.
- [ ] Train lightweight anomaly/fault detector on benign windows.
- [ ] Validate on event windows.
- [ ] Record metrics (precision, recall, F1).

## M5: Shrink for edge (GGUF)
- [ ] Export model to GGUF via llama.cpp.
- [ ] Quantize to smallest viable size.
- [ ] Benchmark inference speed on target hardware.

## M6: Deploy on UNO Q
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