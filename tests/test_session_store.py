"""Session Control: normalize, persist locally, never expose cookie values."""
from app.mri_dashboard import session_store as ss


def test_cookie_editor_array_is_normalized_for_playwright():
    raw = [
        {"name": "ssid", "value": "secret", "domain": ".mercadolibre.cl",
         "path": "/", "secure": True, "httpOnly": True,
         "sameSite": "no_restriction", "expirationDate": 4102444800},
        {"name": "expired", "value": "x", "domain": ".mercadolibre.cl",
         "expirationDate": 1},
        {"name": "other", "value": "x", "domain": ".example.com"},
    ]
    cookies = ss.normalize_cookies(raw, "Mercado Libre")
    assert len(cookies) == 1
    assert cookies[0]["name"] == "ssid"
    assert cookies[0]["sameSite"] == "None"
    assert cookies[0]["expires"] == 4102444800


def test_session_is_saved_locally_and_status_has_no_values(monkeypatch):
    import uuid
    from pathlib import Path
    d = Path("evidence_local_validation") / ("session_" + uuid.uuid4().hex[:8])
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ss, "_session_dir", lambda: d)
    result = ss.save_session("Ripley", [
        {"name": "cf_clearance", "value": "sensitive", "domain": ".ripley.cl",
         "expirationDate": 4102444800},
    ])
    assert result["count"] == 1
    status = ss.session_status("Ripley")
    assert status["exists"] is True
    assert status["cookie_count"] == 1
    assert "sensitive" not in str(status)
    assert ss.load_cookies("Ripley")[0]["name"] == "cf_clearance"
