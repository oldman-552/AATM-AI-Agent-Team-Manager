#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for name in frontend backend; do
  pidfile=".aatm/run/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "$name is not recorded as running."
    continue
  fi
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "Stopped $name (PID $pid)."
  else
    echo "$name process (PID $pid) was already stopped."
  fi
  rm -f "$pidfile"
done
