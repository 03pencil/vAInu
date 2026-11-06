# Skill: Sensory Data (Pump Telemetry)

## Platform
- Target hardware: Arduino UNO Q (Linux MPU + STM32 MCU) running Arduino App Lab, with local AI on-device.
- Data source: only the `data/` folder (full + starter tiers) — fictional pump telemetry dataset; this is what we build on.

## Coding style
- Language: Python (and MicroPython where MCU-side).
- Follow generic Python best practices (PEP 8): clear names, small functions, type hints where helpful, docstrings, no clever one-liners.
- Keep it simple but effective.
- Libraries: matplotlib and pandas at minimum (plus standard library).

When working with this data:
- Telemetry is on a 1s (full) or 10s (starter) grid; rows absent during gateway outages.
- Always join on asset_id + timestamp.
- Respect instrumentation tiers: channels may be NULL per asset (see assets.channels_available).
- quality_flags bitmask: 1 COMM_LOSS, 2 OUT_OF_RANGE, 4 STALE, 8 BAD_SENSOR_STATUS, 16 STARTUP_INHIBIT.
- Events have detectable_utc (first 3-sigma exceedance) and action_deadline_utc (conventional limit).
- Only observable events are scored.
- Test labels are not public; do not leak.
- Use data_dictionary.csv as the source of truth for columns/units.
- Baseline predictions exist for comparison; submission format in submission_template.

## Local models (this machine)

- Chain: smollm2:135m (sub-task) -> mistral (mid) -> gemma4:e2b (main), via `python3 ~/chain_models.py <mode> "<text>"` (modes: code, data, analysis). Run with `.venv/bin/python` for data libs.
