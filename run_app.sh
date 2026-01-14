#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="libcal"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="libcal_bot/app/app.py"

# Activate conda env
if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  conda activate "${EN