"""Preflight fail-closed + single-owner profile locks."""
import uuid
from pathlib import Path

from app.mri_autonomous.execution_preflight import _check_skills, run_preflight
from app.mri_autonomous.browser_profile_manager import ProfileLock, profile_status


def test_mandatory_skills_present_and_fail_closed():
    res = _check_skills()
    assert res["ok"] is True
    assert res["details"]["fail_closed"] is True


def test_profile_lock_single_owner_and_release():
    base = Path("evidence_local_validation/_profiles") / uuid.uuid4().hex[:8]
    base.mkdir(parents=True, exist_ok=True)
    lock = ProfileLock(base, run_id="run-a")
    lock.acquire()
    assert profile_status(base)["locked"] is True
    try:
        ProfileLock(base, run_id="run-b").acquire()
        raise AssertionError("segundo owner debía fallar")
    except RuntimeError as exc:
        assert "PROFILE_LOCKED" in str(exc)
    lock.release()
    assert profile_status(base)["locked"] is False


def test_preflight_reports_blockers_shape():
    report = run_preflight(check_auth=False)
    assert "checks" in report and "blockers" in report
    assert isinstance(report["blockers"], list)
