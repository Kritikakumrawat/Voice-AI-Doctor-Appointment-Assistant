#!/usr/bin/env bash
# macOS / Linux.  ./scripts/start-backend.sh [live]
set -euo pipefail
cd "$(dirname "$0")/../backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
if [ "${1:-}" = "live" ]; then pip install -r requirements-live.txt; export APP_MODE=live; else pip install -r requirements.txt; fi
python run.py
