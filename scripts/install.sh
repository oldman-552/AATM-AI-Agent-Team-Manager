#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python_bin=""
for candidate in python3.15 python3.14 python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo "Python 3.11 or newer is required. Install it and rerun scripts/install.sh." >&2
  exit 1
fi
echo "Using Python $("$python_bin" --version 2>&1 | awk '{print $2}')"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 20+ and npm are required. Install them and rerun scripts/install.sh." >&2
  exit 1
fi
node -e 'const [major] = process.versions.node.split(".").map(Number); if (major < 20) process.exit(1); console.log(`Using Node.js ${process.versions.node}`)' || {
  echo "Node.js 20 or newer is required." >&2
  exit 1
}

if [[ ! -d .venv ]]; then
  "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt

if [[ -f web/package-lock.json ]]; then
  (cd web && npm ci)
else
  (cd web && npm install)
fi

mkdir -p .aatm/logs .aatm/run
printf '\nAATM dependencies installed. Start the application with scripts/start.sh.\n'
