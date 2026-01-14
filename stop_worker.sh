#!/usr/bin/env bash
set -euo pipefail

MODULE="libcal_bot.worker.scheduler_worker"

pkill -f "${MODULE}" && echo "🛑 Worker stopped." || echo "ℹ️ No worker running."
