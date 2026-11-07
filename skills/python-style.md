# Python Coding Style Guide (vAInu)

Use these rules when writing or editing Python in this project.
Goals: readable, scalable, no hard-coding, minimal features, unified style.

## General
- Prefer clarity over cleverness. Code must be readable by humans.
- No extra features: implement only what is needed. Avoid speculative abstractions.
- Keep functions small and single-purpose.
- No hard-coded paths, magic numbers, or literals scattered in logic; use named constants or parameters with sensible defaults.
- Scale by composition: small modules, clear interfaces, no global state.

## Structure
- One responsibility per module: `data_input.py`, `math.py`, `ui.py`, `main.py`.
- `main.py` orchestrates; modules do the work.
- Keep public functions at module top level; private helpers prefixed with `_`.

## Naming
- snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants.
- Names describe intent, not implementation. Avoid abbreviations.

## Style
- PEP 8: 4-space indent, max ~88 chars per line.
- Type hints on public functions.
- Imports grouped: stdlib, third-party, local. One import per line when mixed.
- No unused imports or dead code.

## Comments & docs
- Every module has a docstring stating its responsibility.
- Every public function has a short docstring (what, params, returns).
- Comment *why*, not *what*. Keep comments concise and accurate.
- Keep TODOs explicit and actionable.

## Data handling
- Use pandas; never mutate input DataFrames in place unless documented.
- Validate inputs at boundaries (data_input); trust inside modules.
- Differentiate channels (pressure, temperature, vibration, flow) explicitly; no implicit coupling.
- Support both data tiers via config (full/starter); never hard-code tier paths.

## Math / algorithms
- Pure functions: input -> output, no side effects.
- No premature optimization; clarity first.

## UI
- Plotting helpers only; no business logic in UI.

## Testing
- Keep functions testable: deterministic, no hidden state.
- Add tests alongside new logic.