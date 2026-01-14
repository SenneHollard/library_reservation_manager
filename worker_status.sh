#!/usr/bin/env bash
set -euo pipefail

MODULE="libcal_bot.worker.scheduler_worker"
LOG_FILE="logs/worker.log"

echo "== Worker processes =="
ps aux | grep "${MODULE}" | grep -v grep || echo "No worker running."

echo
echo "== Last 80 log lines =="
[ -f "${LOG_FILE}" ] && tail -n 80 "${LOG_FILE}" || echo "No log file yet: ${LOG_FILE}"
