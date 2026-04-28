#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BACKEND_DIR="$REPO_ROOT/backend"
OUTPUT="$REPO_ROOT/docs/openapi.json"

if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" - "$OUTPUT" <<'PY'
import json
import sys
from pathlib import Path

from glucotracker.main import app

output = Path(sys.argv[1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(output)
PY
