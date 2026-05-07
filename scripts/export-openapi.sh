#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BACKEND_DIR="$REPO_ROOT/backend"
JSON_OUTPUT="$REPO_ROOT/docs/openapi.json"
YAML_OUTPUT="$REPO_ROOT/docs/openapi.yaml"

if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" - "$JSON_OUTPUT" "$YAML_OUTPUT" <<'PY'
import json
import sys
from pathlib import Path

import yaml

from glucotracker.main import app

json_output = Path(sys.argv[1])
yaml_output = Path(sys.argv[2])
schema = app.openapi()

json_output.parent.mkdir(parents=True, exist_ok=True)
json_output.write_text(
    json.dumps(schema, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
yaml_output.write_text(
    yaml.safe_dump(schema, allow_unicode=True, sort_keys=True),
    encoding="utf-8",
)
print(json_output)
print(yaml_output)
PY
