"""Build identity, single-instance lock and transparent cleanup."""
from pathlib import Path
from app.mri_dashboard.build_info import build_info
import app.mri_dashboard.instance_lock as IL


def test_build_info_is_verifiable():
    info = build_info()
    assert info["build_id"] and info["build_id"] != "NO_GIT"
    assert info["pid"] > 0
    assert isinstance(info["dirty"], bool)


def test_instance_lock_rejects_live_owner(monkeypatch):
    runtime = Path("evidence_local_validation/instance_lock_test")
    runtime.mkdir(parents=True, exist_ok=True)
    lockfile = runtime / "instance.lock"
    if lockfile.exists():
        lockfile.unlink()
    monkeypatch.setattr(IL, "_runtime_dir", lambda: runtime)
    monkeypatch.setattr(IL, "port_in_use", lambda port, host="127.0.0.1": False)
    first = IL.InstanceLock(port=65001, build_id="test")
    ok, info = first.acquire()
    assert ok and info["pid"] > 0
    second = IL.InstanceLock(port=65001, build_id="test")
    ok2, info2 = second.acquire()
    assert not ok2 and info2["reason"] == "INSTANCE_ALREADY_RUNNING"
    first.release()
    third = IL.InstanceLock(port=65001, build_id="test")
    ok3, _ = third.acquire()
    assert ok3
    third.release()


def test_cleanup_is_dry_run_by_default():
    from scripts.reset_discovery_state import run
    result = run(apply=False)
    assert result["mode"] == "DRY_RUN"
    assert all(t["deleted"] is False for t in result["targets"])
