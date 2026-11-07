#!/usr/bin/env bash
# Run the vAInu pilot, narration and dashboard on the Arduino UNO Q (or any Linux host).
#
# Usage:
#   scripts/run_board.sh setup        create .venv and install pinned requirements
#   scripts/run_board.sh test         run every tests/test_*.py
#   scripts/run_board.sh pilot        replay the data tier into pilot/
#   scripts/run_board.sh stream       live-style replay: one frame per line, paced (like the UART link)
#   scripts/run_board.sh narrate      narrate new alarms (LLM if [llm] enabled = true)
#   scripts/run_board.sh dashboard    serve the web UI (foreground, Ctrl+C to stop);
#                                     also runs the LED matrix animation in the background
#   scripts/run_board.sh led          run only the LED matrix animation (foreground)
#   scripts/run_board.sh all          setup, test, pilot, narrate, then dashboard
#   scripts/run_board.sh check        show Python, data, Ollama and [llm] status
#
# Options (before or after the command):
#   --data DIR    tier directory            (default: data/full)
#   --host HOST   dashboard bind address    (default: 10.20.3.13)
#   --port PORT   dashboard port            (default: 8000)
#   --speed N     replay speed, 0 = fastest (default: 1 for stream, 0 for pilot)
#   --skip-tests  with "all": skip the test step
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY_MIN_MAJOR=3
PY_MIN_MINOR=11
VENV_PY="$ROOT/.venv/bin/python"
DATA="data/starter"
HOST="10.20.3.13"
PORT="8000"
SPEED=""
SKIP_TESTS="no"
COMMAND=""

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^set -euo/{/^set -euo/d;p}' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      setup|test|pilot|stream|narrate|dashboard|led|all|check) COMMAND="$1" ;;
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

check_project_files() {
  local required=(
    scripts/pilot_run.py scripts/simulate_stream.py scripts/narrate.py scripts/web_ui.py
    src/config.py src/feed.py src/narration.py src/web_ui.py config.toml requirements.txt
  )
  local missing=()
  for file in "${required[@]}"; do
    [[ -f "$file" ]] || missing+=("$file")
  done
  if (( ${#missing[@]} > 0 )); then
    die "project is incomplete, missing: ${missing[*]}. Copy the whole project again (see the ssh steps)."
  fi
}

has_telemetry() {
  [[ -f "$DATA/telemetry.csv.gz" ]] || compgen -G "$DATA/telemetry/asset_id=*/day=*/part-*.parquet" >/dev/null
}

need_telemetry() {
  if ! has_telemetry; then
    die "no telemetry under $DATA. Copy the tier from your PC (see arduino_uno_q_install.md, 7.2)."
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
  log "Pilot replay ($DATA, speed ${SPEED:-0})"
  "$VENV_PY" scripts/pilot_run.py --data "$DATA" --speed "${SPEED:-0}"
}

cmd_stream() {
  need_venv
  need_telemetry
  log "Live-style stream ($DATA, speed ${SPEED:-1}; one frame per line)"
  "$VENV_PY" scripts/simulate_stream.py --data "$DATA" --speed "${SPEED:-1}" \
    | "$VENV_PY" scripts/pilot_run.py --stdin --data "$DATA"
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

cmd_led() {
  need_venv
  log "LED matrix animation (Ctrl+C to stop)"
  "$VENV_PY" scripts/led_matrix.py
}

cmd_dashboard() {
  need_venv
  need_telemetry
  log "LED matrix animation in the background (log: /tmp/vainu_led.log)"
  "$VENV_PY" scripts/led_matrix.py > /tmp/vainu_led.log 2>&1 &
  LED_PID=$!
  trap 'kill "$LED_PID" 2>/dev/null || true' EXIT
  log "Dashboard on http://$HOST:$PORT  (no login: trusted network only)"
  "$VENV_PY" scripts/web_ui.py --data "$DATA" --host "$HOST" --port "$PORT"
}

cmd_check() {
  log "Status"
  check_system_python
  if (check_project_files) 2>/dev/null; then echo "files:     complete"; else echo "files:     INCOMPLETE (copy the whole project again)"; fi
  echo "Python:    $(python3 --version)"
  echo "Repo:      $ROOT"
  if [[ -x "$VENV_PY" ]]; then echo "venv:      ready"; else echo "venv:      missing (run setup)"; fi
  if has_telemetry; then echo "telemetry: $DATA"; else echo "telemetry: MISSING at $DATA"; fi
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
  check_project_files
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
  stream) cmd_stream ;;
  narrate) cmd_narrate ;;
  dashboard) cmd_dashboard ;;
  led) cmd_led ;;
  all) cmd_all ;;
  check) cmd_check ;;
esac
