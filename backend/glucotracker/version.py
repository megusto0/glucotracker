from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

# Repo root is /media/megusto/storage/glucotracker/project
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _read_pyproject_version() -> str:
    pyproject = BACKEND_DIR / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return str(data.get("project", {}).get("version") or "0.11.0")
        except Exception:
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                m = re.match(r'^\s*version\s*=\s*["\']([^"\']+)["\']', line)
                if m:
                    return m.group(1)
    return "0.11.0"


@lru_cache(maxsize=1)
def get_version_info() -> dict[str, Any]:
    base_version = _read_pyproject_version()
    commit = os.getenv("GIT_COMMIT") or os.getenv("GLUCOTRACKER_COMMIT")
    commit_short = None
    commit_time = None
    commit_message = None
    branch = os.getenv("GIT_BRANCH") or os.getenv("GLUCOTRACKER_BRANCH")
    tag = None
    tag_distance = 0
    is_dirty = False
    git_cmd = shutil.which("git") or "/usr/bin/git"

    try:
        res = subprocess.run(
            [git_cmd, "--no-pager", "log", "-1", "--format=%H%n%h%n%cI%n%s"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if len(lines) >= 4:
                commit = lines[0]
                commit_short = lines[1]
                commit_time = lines[2]
                commit_message = lines[3]
    except Exception:
        pass

    if not branch:
        try:
            res = subprocess.run(
                [git_cmd, "--no-pager", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0:
                branch = res.stdout.strip()
        except Exception:
            pass

    try:
        res = subprocess.run(
            [git_cmd, "--no-pager", "describe", "--tags", "--always", "--long"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            desc = res.stdout.strip()
            m = re.match(r"^(.+)-(\d+)-g([0-9a-f]+)$", desc)
            if m:
                tag = m.group(1)
                tag_distance = int(m.group(2))
    except Exception:
        pass

    try:
        res = subprocess.run(
            [git_cmd, "--no-pager", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            is_dirty = bool(res.stdout.strip())
    except Exception:
        pass

    if not commit:
        git_dir = REPO_ROOT / ".git"
        head_file = git_dir / "HEAD"
        if head_file.exists():
            head_content = head_file.read_text().strip()
            if head_content.startswith("ref: "):
                ref_path = head_content[5:]
                branch = branch or ref_path.split("/")[-1]
                ref_file = git_dir / ref_path
                if ref_file.exists():
                    commit = ref_file.read_text().strip()
                elif (git_dir / "packed-refs").exists():
                    for line in (git_dir / "packed-refs").read_text().splitlines():
                        if line.endswith(ref_path):
                            commit = line.split()[0]
                            break
            else:
                commit = head_content

    if commit and not commit_short:
        commit_short = commit[:7]

    display_version = base_version
    if tag:
        clean_tag = tag.lstrip("v")
        if clean_tag:
            display_version = clean_tag

    full_version = (
        f"{display_version}+{commit_short}" if commit_short else display_version
    )
    if tag_distance > 0:
        full_version = f"{display_version}.dev{tag_distance}+{commit_short}"
    if is_dirty:
        full_version += ".dirty"

    return {
        "service": "glucotracker",
        "version": display_version,
        "full_version": full_version,
        "commit": commit,
        "commit_short": commit_short,
        "branch": branch or "main",
        "tag": tag,
        "tag_distance": tag_distance,
        "is_dirty": is_dirty,
        "commit_time": commit_time,
        "commit_message": commit_message,
    }


def main() -> None:
    info = get_version_info()
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
