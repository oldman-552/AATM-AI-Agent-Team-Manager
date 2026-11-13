#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to update with local changes. Commit, stash, or back them up first." >&2
  exit 1
fi
git pull --ff-only
exec scripts/install.sh
