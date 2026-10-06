"""Fail-closed mandatory skill policy for MRI autonomous execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
MANIFEST_PATH = SKILLS_DIR / "MRI_MANDATORY_SKILLS.json"


class MandatorySkillPolicyError(RuntimeError):
    """MRI cannot execute when its mandatory operational knowledge is unavailable."""


def require_mri_skills() -> Dict[str, object]:
    if not MANIFEST_PATH.is_file():
        raise MandatorySkillPolicyError(
            f"MRI mandatory skill manifest missing: {MANIFEST_PATH}"
        )
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MandatorySkillPolicyError(
            f"MRI mandatory skill manifest unreadable: {exc}"
        ) from exc

    required = manifest.get("required")
    if manifest.get("fail_closed") is not True or not isinstance(required, list) or not required:
        raise MandatorySkillPolicyError(
            "MRI mandatory skill manifest must declare fail_closed=true and a non-empty required list"
        )

    loaded: List[str] = []
    for name in required:
        if not isinstance(name, str) or Path(name).name != name:
            raise MandatorySkillPolicyError(f"Invalid mandatory skill entry: {name!r}")
        path = SKILLS_DIR / name
        if not path.is_file():
            raise MandatorySkillPolicyError(f"Mandatory MRI skill missing: {path}")
        body = path.read_text(encoding="utf-8").strip()
        if not body:
            raise MandatorySkillPolicyError(f"Mandatory MRI skill empty: {path}")
        loaded.append(name)

    return {
        "policy_version": manifest.get("policy_version"),
        "mandatory_for": manifest.get("mandatory_for"),
        "loaded": loaded,
        "fail_closed": True,
    }
