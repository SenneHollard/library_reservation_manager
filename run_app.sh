#!/usr/bin/env bash
set -euo pipefail

# ---- Config ----
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${VENV_PATH:-$HOME/venvs/libcal}"
APP_PATH="$PROJECT_ROOT/libcal_bot/app/app.py"

PORT="${PORT:-8765}"
ADDRESS="${ADDRESS:-127.0.0.1}"

# Server-friendly defaults (can be overridden)
HEADLESS="${HEADLESS:-true}"
SLOW_MO="${SLOW_MO:-0}"

LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
LOG_FILE="$LOG_DIR/streamlit.log"

mkdir -p "$LOG_DIR"

echo "[run_app] project: $PROJECT_ROOT"
echo "[run_app] venv:    $VENV_PATH"
echo "[run_app] app:     $APP_PATH"
echo "[run_app] addr:    $ADDRESS:$PORT"
echo "[run_app] headless=$HEADLESS slow_mo=$SLOW_MO"
echo "[run_app] log:     $LOG_FILE"

# ---- Activate venv ----
if [[ -f "$VENV_PATH/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
else
  echo "ERROR: venv not found at: $VENV_PATH" >&2
  echo "Create it with: python3 -m venv $VENV_PATH" >&2
  exit 1
fi

cd "$PROJECT_ROOT"

# ---- Ensure local imports work ----
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# ---- Force headless environment on servers (if no DISPLAY) ----
# If there's no GUI display, Playwright headed mode must NOT be used.
if [[ -z "${DISPLAY:-}" ]]; then
  export HEADLESS="true"
  export SLOW_MO="0"
fi

# ---- Kill anything already listening on PORT (old Streamlit instance) ----
if command -v lsof >/dev/null 2>&1; then
  OLD_PIDS="$(lsof -ti tcp:"$PORT" || true)"
  if [[ -n "$OLD_PIDS" ]]; then
    echo "[run_app] killing processes on port $PORT: $OLD_PIDS"
    kill $OLD_PIDS || true
    sleep 0.5
    # still there? force kill
    OLD_PIDS="$(lsof -ti tcp:"$PORT" || true)"
    if [[ -n "$OLD_PIDS" ]]; then
      echo "[run_app] force killing: $OLD_PIDS"
      kill -9 $OLD_PIDS || true
    fi
  fi
else
  echo "[run_app] warning: lsof not found; cannot auto-kill port users"
fi

# ---- Start Streamlit (log to file) ----
# Using exec replaces this shell with streamlit process.
exec streamlit run "$APP_PATH" \
  --server.address "$ADDRESS" \
  --server.port "$PORT" \
  2>&1 | tee -a "$LOG_FILE"
