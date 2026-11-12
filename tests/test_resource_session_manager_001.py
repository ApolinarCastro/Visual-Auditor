import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mri_dashboard import session_store
from app.mri_dashboard import resource_manager


def test_cookie_crud_masking_and_export(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_session_dir", lambda: tmp_path)
    mkt = "Falabella"
    assert session_store.load_cookies(mkt) == []
    created = session_store.upsert_cookie(mkt, {
        "name": "session_id", "value": "secret-value", "domain": ".falabella.com",
        "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax",
        "expirationDate": 4102444800})
    assert created["operation"] == "created"
    assert created["count"] == 1
    masked = session_store.list_cookies(mkt)
    assert masked[0]["value"] != "secret-value"
    assert masked[0]["httpOnly"] is True
    revealed = session_store.list_cookies(mkt, reveal=True)
    assert revealed[0]["value"] == "secret-value"
    updated = session_store.upsert_cookie(mkt, {
        "name": "session_id", "value": "new-value", "domain": ".falabella.com",
        "path": "/", "secure": True, "httpOnly": True})
    assert updated["operation"] == "updated"
    exported = session_store.export_cookies(mkt)
    assert exported["count"] == 1
    assert exported["cookies"][0]["value"] == "new-value"
    assert session_store.delete_cookie(mkt, "session_id", ".falabella.com", "/")["deleted"] == 1
    assert session_store.load_cookies(mkt) == []


def test_cookie_domain_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store, "_session_dir", lambda: tmp_path)
    try:
        session_store.upsert_cookie("Falabella", {
            "name": "x", "value": "1", "domain": ".ripley.cl", "path": "/"})
        assert False, "foreign domain must be rejected"
    except ValueError:
        pass


def test_resource_monitor_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(resource_manager, "TELEMETRY", tmp_path / "telemetry.jsonl")
    mon = resource_manager.ResourceMonitor("test-run", "Falabella", interval=0)
    mon.start()
    result = mon.stop()
    assert result["run_id"] == "test-run"
    assert result["marketplace"] == "Falabella"
    assert "measurement_status" in result
    assert (tmp_path / "telemetry.jsonl").exists()
    assert mon.summary()["samples"] >= 2
