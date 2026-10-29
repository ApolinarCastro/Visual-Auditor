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


def test_accepts_single_cookie_and_mercadolibre_com_domain():
    one = {"name": "ssid", "value": "x", "domain": ".mercadolibre.com",
           "expirationDate": 4102444800}
    assert len(ss.normalize_cookies(one, "Mercado Libre")) == 1
    assert len(ss.normalize_cookies('{"cookies":[{"name":"ssid","value":"x","domain":".mercadolibre.cl","expirationDate":4102444800}]}', "Mercado Libre")) == 1


def test_rejected_domain_diagnostic_is_actionable():
    import pytest
    try:
        ss.normalize_cookies([
            {"name": "x", "value": "y", "domain": ".ripley.cl", "expirationDate": 4102444800}
        ], "Mercado Libre")
    except ValueError as exc:
        assert "dominios_rechazados" in str(exc)
        assert "ripley.cl" in str(exc)
    else:
        raise AssertionError("se esperaba ValueError")


def test_marketplace_alias_accepts_chile_cookie_domain():
    assert ss.canonical_marketplace("mercadolibre") == "Mercado Libre"
    cookies = ss.normalize_cookies([
        {"name": "sid", "value": "x", "domain": ".mercadolibre.cl",
         "expirationDate": 4102444800},
        {"name": "art", "value": "y", "domain": ".articulo.mercadolibre.cl",
         "expirationDate": 4102444800},
    ], ss.canonical_marketplace("mercadolibre"))
    assert len(cookies) == 2
