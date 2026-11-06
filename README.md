# vAInu - Pump Sensor Project

For the sinceAI 2026 Hackathon in Turku.

Arduino UNO Q based pump sensory project using local AI.

## Structure

- `data/` — pump telemetry dataset (full + starter tiers). Treat as the only data source.
- `skills/` — installed agent skills (ei-build-arduino-uno-q-app-lab) + project skill notes.
- `tests/` — tests.
- `skill_data.md` — instructions about the data and coding style.

## Infrastructure (local development)

- Local LLM chain via Ollama (`ollama serve` on localhost:11434):
  - `smollm2:135m` — fast sub-task model (extract numbers/facts).
  - `mistral` — mid reasoning step.
  - `gemma4:e2b` — main task model.
  - Chain script: `python3 ~/chain_models.py <mode> "<text>"` where mode is `code`, `data`, or `analysis`.
- Python venv: `.venv/` with `pandas`, `numpy`, `scipy`, `matplotlib` (use `.venv/bin/python`).

## Coding

Python / MicroPython, PEP 8, simple but effective. Uses matplotlib and pandas.
