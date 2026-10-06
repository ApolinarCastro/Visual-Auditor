import json
from pathlib import Path

import pytest

from app.mri_autonomous.skill_policy import (
    MANIFEST_PATH,
    MandatorySkillPolicyError,
    require_mri_skills,
)


def test_mri_mandatory_skills_are_installed_and_loadable():
    result = require_mri_skills()
    assert result["fail_closed"] is True
    assert len(result["loaded"]) == 4


def test_manifest_declares_fail_closed():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["fail_closed"] is True
    assert set(manifest["required"]) == {
        "FDE_RUNTIME_ROOT_CAUSE.md",
        "AGENT_RUNTIME_EFFICIENCY.md",
        "MARKETPLACE_EXPERIENCE_REUSE.md",
        "KNOWLEDGE_TO_SKILL_DISTILLATION.md",
    }
