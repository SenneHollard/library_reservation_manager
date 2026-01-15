#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="${VENV_PATH:-$HOME/venvs/libcal}"

APP_PATH="$PROJECT_ROOT/libcal_bot/app/app.py"
PORT="${PORT:-8765}"
ADDRESS="${ADDRESS:-127.0.0.1}"

# Activate venv
if [[ -f