"""Tests for OpenAPI export script."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def find_bash() -> str | None:
    """Find a local Bash executable for Windows or Unix test environments."""
    discovered = shutil.which("bash")
    if discovered is not None:
        return discovered

    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\sh.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def test_openapi_export_script_produces_docs_openapi_json() -> None:
    """The backend export script writes the generated OpenAPI document."""
    bash = find_bash()
    if bash is None:
        pytest.skip("bash is required to run export-openapi.sh")

    backend_dir = Path(__file__).resolve().parents[1]
    repo_dir = backend_dir.parent
    output = repo_dir / "docs" / "openapi.json"

    result = subprocess.run(
        [bash, "scripts/export-openapi.sh"],
        cwd=backend_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    assert str(output) in result.stdout.strip()
    assert output.exists()
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["info"]["title"] == "Glucotracker API"
    assert "/meals" in schema["paths"]
