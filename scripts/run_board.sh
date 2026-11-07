#!/usr/bin/env bash
# Run the vAInu pilot, narration and dashboard on the Arduino UNO Q (or any Linux host).
#
# Usage:
#   scripts/run_board.sh setup        create .venv and install pinned requirements
#   scripts/run_board.sh test         run every tests/test_*.py
#   scripts/run_board.sh pilot        replay the starter tier into pilot/
#   scripts/run_board.sh narrate      narrate new alarms (LLM if [llm] enabled = true)
#   scripts/run_board.sh dashboard    serve the web UI (foreground, Ctrl+C to stop)
#   scripts/run_board.sh all          setup, test, pilot, narrate, then dashboard
#   scripts/run_board.sh check        show Python, data, Ollama and [llm] status
#
# Options (before or after the command):
#   --data DIR    tier directory            (default: data/starter)
#   --host HOST   dashboard bind address    (default: 0.0.0.0)
#   --port PORT   dashboard port            (default: 8000)
#   --speed N     replay speed, 0 = fastest (default: 0)
#   --skip-tests  with "all": skip the test step
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY_MIN_MAJOR=3
PY_MIN_MINOR=11
VENV_PY="$ROOT/.venv/bin/python"
DATA="data/starter"
HOST="0.0.0.0"
PORT="8000"
SPEED="0"
SKIP_TESTS="no"
COMMAND=""

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      setup|test|pilot|narrate|dashboard|all|check) COMMAND="$1" ;;
      --data) DATA="${2:?--data needs a value}"; shift ;;
      --host) HOST="${2:?--host needs a value}"; shift ;;
      --port) PORT="${2:?--port needs a value}"; shift ;;
      --speed) SPEED="${2:?--speed needs a value}"; shift ;;
      --skip-tests) SKIP_TESTS="yes" ;;
      -h|--help|help) usage; exit 0 ;;
      *) die "unknown argument: $1 (see --help)" ;;
    esac
    shift
  done
  [[ -n "$COMMAND" ]] || { usage; exit 1; }
}

check_system_python() {
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+."
  python3 - <<EOF || die "Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+ is required (the code uses tomllib). Found: $(python3 --version 2>&1)"
import sys
sys.exit(0 if sys.version_info >= (${PY_MIN_MAJOR}, ${PY_MIN_MINOR}) else 1)
EOF
}

need_venv() {
  [[ -x "$VENV_PY" ]] || die "no .venv yet. Run: scripts/run_board.sh setup"
}

need_telemetry() {
  if [[ "$DATA" == "data/starter" && ! -f "$DATA/telemetry.csv.gz" ]]; then
    die "$DATA/telemetry.csv.gz is missing. Copy it from your PC (see arduino_uno_q_install.md, 7.2)."
  fi
}

llm_enabled() {
  need_venv
  "$VENV_PY" -c "
import sys; sys.path.insert(0, '.')
from src.config import get_llm_config
sys.exit(0 if get_llm_config()['enabled'] else 1)
"
}

cmd_setup() {
  log "Setup"
  check_system_python
  if [[ ! -x "$VENV_PY" ]]; then
    echo "Creating .venv ..."
    python3 -m venv .venv
  else
    echo ".venv already exists; updating packages."
  fi
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install -r requirements.txt
  echo "Setup done."
}

cmd_test() {
  need_venv
  log "Tests"
  local failed=0
  export VAINU_DATA_DIR="$DATA"
  for file in tests/test_*.py; do
    if "$VENV_PY" "$file" > /tmp/vainu_test.log 2>&1; then
      echo "ok    $file"
    else
      echo "FAIL  $file"
      sed 's/^/      /' /tmp/vainu_test.log | tail -15
      failed=1
    fi
  done
  [[ $failed -eq 0 ]] || die "some tests failed; fix them before running the pilot"
  echo "All tests passed."
}

cmd_pilot() {
  need_venv
  need_telemetry
  log "Pilot replay ($DATA, speed $SPEED)"
  "$VENV_PY" scripts/pilot_run.py --data "$DATA" --speed "$SPEED"
}

cmd_narrate() {
  need_venv
  log "Narration"
  if llm_enabled; then
    echo "[llm] enabled: checking Ollama first."
    if ! "$VENV_PY" scripts/narrate.py --check; then
      echo "Ollama is not ready. Start it with: sudo systemctl start ollama" >&2
      echo "Narration skipped; the pilot and dashboard still work." >&2
      return 0
    fi
    "$VENV_PY" scripts/narrate.py --data "$DATA" || {
      echo "Narration stopped early; finished records are kept." >&2
    }
  else
    echo "[llm] disabled in config.toml: writing template text only."
    "$VENV_PY" scripts/narrate.py --data "$DATA" --template-only
  fi
}

cmd_dashboard() {
  need_venv
  need_telemetry
  log "Dashboard on http://$HOST:$PORT  (no login: trusted network only)"
  exec "$VENV_PY" scripts/web_ui.py --data "$DATA" --host "$HOST" --port "$PORT"
}

cmd_check() {
  log "Status"
  check_system_python
  echo "Python:    $(python3 --version)"
  echo "Repo:      $ROOT"
  if [[ -x "$VENV_PY" ]]; then echo "venv:      ready"; else echo "venv:      missing (run setup)"; fi
  if [[ -f "$DATA/telemetry.csv.gz" ]]; then echo "telemetry: $DATA/telemetry.csv.gz"; else echo "telemetry: MISSING at $DATA"; fi
  if command -v ollama >/dev/null 2>&1; then
    if systemctl is-active --quiet ollama 2>/dev/null; then echo "ollama:    running"; else echo "ollama:    installed, not running"; fi
  else
    echo "ollama:    not installed"
  fi
  if [[ -x "$VENV_PY" ]]; then
    if llm_enabled; then echo "[llm]:     enabled"; else echo "[llm]:     disabled (template text only)"; fi
  fi
}

cmd_all() {
  cmd_setup
  if [[ "$SKIP_TESTS" == "no" ]]; then cmd_test; else echo "Skipping tests (--skip-tests)."; fi
  cmd_pilot
  cmd_narrate
  cmd_dashboard
}

parse_args "$@"

case "$COMMAND" in
  setup) cmd_setup ;;
  test) cmd_test ;;
  pilot) cmd_pilot ;;
  narrate) cmd_narrate ;;
  dashboard) cmd_dashboard ;;
  all) cmd_all ;;
  check) cmd_check ;;
esac
