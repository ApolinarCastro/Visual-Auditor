"""ScrapeGraphAI adapter policy tests (fixtures only, no network/LLM)."""
from app.mri_dashboard.scrapegraph_adapter import (
    ScrapeGraphExtractor, FIELDS, OK, DISABLED, UNAVAILABLE, INVALID_RESPONSE, ERROR,
)


def test_disabled_by_default_returns_nulls_without_touching_anything(monkeypatch):
    monkeypatch.delenv("SCRAPEGRAPHAI_ENABLED", raising=False)
    ext = ScrapeGraphExtractor()
    payload = ext.extract("<html>real acquired html</html>",
                          "https://www.paris.cl/p1.html", "Paris")
    assert ext.status()["enabled"] is False
    assert ext.available is False
    assert payload["extraction_status"] == DISABLED
    assert set(payload) >= set(FIELDS)
    for field in ("product_id", "title", "brand", "seller", "category",
                  "subcategory", "category_path"):
        assert payload[field] is None          # never invented


def test_unknown_fields_stay_null_and_owned_fields_are_not_overwritten():
    def backend(**kwargs):
        return {"product_id": "MK55PJULHG", "title": "Polera Nicopoly",
                "brand": None, "seller": "", "category": "Poleras",
                "marketplace": "FAKE", "product_url": "https://evil.example/x"}
    ext = ScrapeGraphExtractor(backend=backend, enabled_override=True)
    payload = ext.extract("<html/>", "https://www.paris.cl/p1.html", "Paris")
    assert payload["extraction_status"] == OK
    assert payload["product_id"] == "MK55PJULHG"
    assert payload["brand"] is None and payload["seller"] is None
    # Adapter-owned provenance wins over model output.
    assert payload["marketplace"] == "Paris"
    assert payload["product_url"] == "https://www.paris.cl/p1.html"
    assert payload["evidence_source"] == "https://www.paris.cl/p1.html"


def test_invalid_scalar_types_are_rejected_not_trusted():
    ext = ScrapeGraphExtractor(backend=lambda **k: {"title": {"nested": "x"},
                                                    "product_id": ["a"]},
                               enabled_override=True)
    payload = ext.extract("<html/>", "https://m/p", "Ripley")
    assert payload["extraction_status"] == INVALID_RESPONSE
    assert payload["title"] is None and payload["product_id"] is None


def test_backend_failure_degrades_without_raising():
    def boom(**kwargs):
        raise RuntimeError("LLM provider unreachable")
    ext = ScrapeGraphExtractor(backend=boom, enabled_override=True)
    payload = ext.extract("<html/>", "https://m/p", "Falabella")
    assert payload["extraction_status"] == ERROR
    assert "LLM provider unreachable" in payload["error"]


def test_missing_library_reports_unavailable_and_mri_continues(monkeypatch):
    monkeypatch.setenv("SCRAPEGRAPHAI_ENABLED", "true")
    ext = ScrapeGraphExtractor()          # no backend injected, library absent
    assert ext.available is False
    payload = ext.extract("<html/>", "https://m/p", "Mercado Libre")
    assert payload["extraction_status"] == UNAVAILABLE
    assert ext.status()["writes_official_results"] is False


def test_compare_marks_additional_fields_and_contradictions_without_applying():
    ai = {"product_id": "P1", "title": "Polera Negra", "brand": "Nicopoly",
          "category": "Poleras", "seller": None}
    current = {"product_id": "P1", "title": "Polera Negra Nicopoly",
               "brand": None, "category": "Poleras y Blusas"}
    result = ScrapeGraphExtractor.compare(ai, current)
    assert "brand" in result["additional_fields"]
    assert {c["field"] for c in result["contradictions"]} == {"title", "category"}
    assert result["auto_applied"] is False
    assert current["brand"] is None       # current extraction untouched


def test_no_artificial_identity_confirmation_from_brand_match():
    """Brand coincidence is evidence, not confirmed identity."""
    ai = {"brand": "Nicopoly", "seller": "Nicopoly"}
    current = {}
    result = ScrapeGraphExtractor.compare(ai, current)
    assert set(result["additional_fields"]) == {"brand", "seller"}
    # Identity confirmation remains an MRI rule, never the adapter's output.
    assert "identity_confirmed" not in result
