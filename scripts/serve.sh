#!/usr/bin/env bash
# Local one-click launcher for the TransitTruth web UI (POSIX).
# Defaults to loopback only; never passes --allow-public.
#
# Usage:
#   ./scripts/serve.sh                 # http://127.0.0.1:8766
#   PORT=8800 ./scripts/serve.sh
#   OPEN=1 ./scripts/serve.sh          # auto-open browser
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT/backend"

LISTEN="${HOST:-127.0.0.1}"
PORT="${PORT:-8766}"
ARGS=(serve --host "$LISTEN" --port "$PORT")
[ "${OPEN:-0}" = "1" ] && ARGS+=(--open)
[ "${ALLOW_LOCAL:-0}" = "1" ] && ARGS+=(--allow-local)

# Prefer the repo venv if present; otherwise fall back to python3 on PATH.
if [ -x "$ROOT/.venv/bin/python" ]; then
    exec "$ROOT/.venv/bin/python" -m app.cli "${ARGS[@]}"
else
    exec python3 -m app.cli "${ARGS[@]}"
fi
