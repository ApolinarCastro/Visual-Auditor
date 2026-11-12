"""Verifiable build identity for MRI.

The build id is derived from the current commit plus whether tracked runtime
files are dirty. It is exposed in /api/version and printed at startup so it is
impossible to confuse an old process with a new one.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(_REPO), *args],
            stderr=subprocess.DEVNULL, text=True, timeout=4).strip()
    except Exception:
        return ""


def compute_build_id() -> str:
    commit = _git("rev-parse", "--short=12", "HEAD") or "NO_GIT"
    dirty = _git("status", "--porcelain", "--", "app", "tests", "run.py",
                 "open_mri_dashboard.ps1", "lanzar_mri_dashboard.bat")
    suffix = "-dirty" if dirty else ""
    return f"{commit}{suffix}"


def build_info() -> dict:
    commit = _git("rev-parse", "HEAD") or "NO_GIT"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "NO_BRANCH"
    build_id = compute_build_id()
    return {
        "build_id": build_id,
        "commit": commit,
        "branch": branch,
        "dirty": build_id.endswith("-dirty"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }


BUILD_ID = compute_build_id()
BUILD_FINGERPRINT = hashlib.sha256(BUILD_ID.encode()).hexdigest()[:16]
