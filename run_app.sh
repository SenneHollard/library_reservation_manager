#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="${VENV_PATH:-$HOME/venvs/libcal}"

APP_PATH="$PROJECT_ROOT/libcal_bot/app/app.py"
PORT="${PORT:-8765}"
ADDRESS="${ADDRESS:-127.0.0.1}"

# Activate venv
if [[ -f "$VENV_PATH/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_PATH/bin/activate"
else
  echo "ERROR: venv not found at: $VENV_PATH"
  echo "Create it with: python3 -m venv $VENV_PATH"
  exit 1
fi

cd "$PROJECT_ROOT"

# Ensure local imports work (fixes ModuleNotFoundError: libcal_bot)
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec streamlit run "$APP_PATH" --server.address "$ADDRESS" --server.port "$PORT"
