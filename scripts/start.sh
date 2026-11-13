#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python || ! -x web/node_modules/.bin/vite ]]; then
  echo "Dependencies are missing. Run scripts/install.sh first." >&2
  exit 1
fi

mkdir -p .aatm/logs .aatm/run
runtime_config="$(PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" .venv/bin/python -c 'from app.core.config import settings; print(settings.host); print(settings.port)')"
mapfile -t runtime_defaults <<< "$runtime_config"
HOST="${HOST:-${runtime_defaults[0]:-127.0.0.1}}"
PORT="${PORT:-${runtime_defaults[1]:-8000}}"
UI_HOST="${AATM_UI_HOST:-127.0.0.1}"
UI_PORT="${AATM_UI_PORT:-5173}"

start_service() {
  local name="$1"; shift
  local pidfile="$ROOT_DIR/.aatm/run/${name}.pid"
  local logfile="$ROOT_DIR/.aatm/logs/${name}.log"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name already running (PID $(cat "$pidfile"))."
    return
  fi
  rm -f "$pidfile"
  nohup "$@" >"$logfile" 2>&1 < /dev/null &
  echo "$!" > "$pidfile"
  echo "Started $name (PID $!). Log: .aatm/logs/${name}.log"
}

start_service backend .venv/bin/python -m uvicorn app.main:app --app-dir backend --host "$HOST" --port "$PORT"
(
  cd "$ROOT_DIR/web"
  # The auth token (if enabled) is read by the Vite process and injected into
  # proxied /api requests; it never reaches the browser bundle.
  AATM_API_TARGET="http://127.0.0.1:${PORT}" AATM_AUTH_TOKEN="${AATM_AUTH_TOKEN:-}" \
    # --strictPort: fail loudly instead of silently binding another port, which
    # used to make the printed UI URL wrong.
    start_service frontend ./node_modules/.bin/vite --host "$UI_HOST" --port "$UI_PORT" --strictPort
)
# --strictPort makes Vite fail rather than drift to another port. Wait briefly, then
# report the real state instead of printing a URL that may not be serving.
ui_ready=0
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null "http://$UI_HOST:$UI_PORT/" 2>/dev/null; then ui_ready=1; break; fi
  sleep 0.5
done
if [[ "$ui_ready" -eq 1 ]]; then
  printf '\nAATM UI:  http://%s:%s\nAATM API: http://%s:%s/api/v1/health\nStop with: scripts/stop.sh\n' "$UI_HOST" "$UI_PORT" "$HOST" "$PORT"
else
  echo "ERROR: the UI did not start on port $UI_PORT (usually the port is busy)." >&2
  echo "       Set AATM_UI_PORT to a free port and rerun, e.g. AATM_UI_PORT=5174 scripts/start.sh" >&2
  echo "       Frontend log: .aatm/logs/frontend.log" >&2
  exit 1
fi
