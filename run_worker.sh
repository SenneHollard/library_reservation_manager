#!/usr/bin/env bash
set -euo pipefail

# --- config ---
ENV_NAME="libcal"
LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/worker.log"
MODULE="libcal_bot.worker.scheduler_worker"

mkdir -p "${LOG_DIR}"

# Stop existing worker (if any)
pkill -f "${MODULE}" >/dev/null 2>&1 || true

# Activate conda env (works even if conda isn't initialized in non-interactive shells)
if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  conda activate "${ENV_NAME}"
fi

# Start worker detached
nohup python -m "${MODULE}" > "${LOG_FILE}" 2>&1 < /dev/null &

echo "✅ Worker started (PID=$!). Logs: ${LOG_FILE}"
