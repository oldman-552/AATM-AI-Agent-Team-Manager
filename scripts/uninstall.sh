#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x scripts/stop.sh ]]; then
  scripts/stop.sh
fi
rm -rf -- .venv web/node_modules web/dist
printf 'Removed generated Python/Node environments and frontend build output.\n'
printf 'Preserved source, Git history, .env, and .aatm user data/database/logs.\n'
printf 'Delete preserved user data manually only after a verified backup.\n'
