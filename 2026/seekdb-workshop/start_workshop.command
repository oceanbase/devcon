#!/bin/zsh
set -e
COURSE_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$COURSE_ROOT"
if ! .venv/bin/python scripts/setup_environment.py --check >/dev/null 2>&1; then
  WORKSHOP_BOOTSTRAP_PYTHON=
  for candidate in .runtime/python/bin/python3.12 .venv/bin/python python3.12 python3 python3.15 python3.14 python3.13 python3.11 python; do
    if "$candidate" -c 'import sys; raise SystemExit(sys.implementation.name != "cpython" or sys.version_info[0] != 3 or sys.version_info[:2] < (3, 11))' >/dev/null 2>&1; then
      WORKSHOP_BOOTSTRAP_PYTHON="$candidate"
      break
    fi
  done
  if [ -z "$WORKSHOP_BOOTSTRAP_PYTHON" ]; then
    printf '%s\n' 'CPython 3.11 or newer is required.'
    exit 1
  fi
  "$WORKSHOP_BOOTSTRAP_PYTHON" scripts/setup_environment.py
fi
exec .venv/bin/python scripts/launch_notebook.py "$@"
