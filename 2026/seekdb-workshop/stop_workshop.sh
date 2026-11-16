#!/bin/sh
set -e
WORKSHOP_STOP_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
"$WORKSHOP_STOP_ROOT/.venv/bin/python" "$WORKSHOP_STOP_ROOT/scripts/stop_workshop.py"
