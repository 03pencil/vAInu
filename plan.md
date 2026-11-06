# Project Plan

## Goal

Build an Arduino UNO Q app that reads pump sensory data and runs local AI to detect anomalies/faults.

## Phases

1. Explore data: load starter telemetry with pandas, inspect channels, asset tiers.
2. Baseline analysis: compute simple stats, plots (matplotlib) per asset/channel.
3. Feature engineering: rolling stats, vibration trends, pressure/flow ratios.
4. Model: train a lightweight anomaly detector on benign windows; validate on events.
5. Deploy: port model to UNO Q via App Lab / Edge Impulse brick; MCU reads sensors, MPU runs inference.
6. Test on hardware; iterate.

## Forecasting goal (new)

- Learn from `data/` (full + starter tiers) to predict same kind of pump telemetry in the future.
- End goal: predicting model = small model (smoll) running on Arduino UNO Q.

### Proposed forecasting plan

1. Define prediction task: per-asset future telemetry values or faults/events.
2. Baseline forecasting: naive baselines + small temporal model on engineered features.
3. Validate out-of-sample.
4. Shrink to smoll for edge deployment (GGUF via llama.cpp).
5. End-to-end: MCU data -> MPU inference -> prediction -> alerts.

## Milestones

- M1: Data exploration notebook/script done.
- M2: Baseline model metrics on validation.
- M3: App Lab app running on UNO Q.
- M4: End-to-end demo.
