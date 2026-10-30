"""
Acquisition-truth contract tests (P0 2026-10-22).

All payloads here are explicit FIXTURES: they emulate marketplace responses for
negative/acceptance tests and are never presented as real acquisition.

Covers acceptance items 1, 2, 3, 6, 7, 8, 9 of the acquisition-truth closure.
"""
import asyncio

import pytest

from app.mri_dashboard import acquisition_contract as C


# ── 1. SOURCE_BLOCKED never fabricates publications ─────────────────────────
def test_fixture_ml_blocked_normalises_to_source_blocked():
    # The frozen ML scraper emits stop_reason="BLOCKED" (log: "Blocked during
    # pagination on Page 1"); the contract must never read that as success.
    assert C.normalize_stop_reason("BLOCKED") == C.SOURCE_BLOCKED
    assert C.normalize_stop_reason("BLOCKED_PAGINATION") == C.SOURCE_BLOCKED
    assert C.resolve_outcome(0, C.normalize_stop_reason("BLOCKED")) == C.SOURCE_BLOCKED


def test_fixture_zero_records_is_not_found_only_when_source_was_readable():
    assert C.resolve_outcome(0, None) == C.NOT_FOUND
    assert C.resolve_outcome(0, C.SOURCE_BLOCKED) == C.SOURCE_BLOCKED
    assert C.resolve_outcome(0, C.EXTRACTOR_FAILURE) == C.EXTRACTOR_FAILURE


# ── 2. Page opened without extraction is never FOUND ────────────────────────
def test_fixture_page_opened_without_products_is_not_found():
    # Ripley logs "Page loaded OK" but returns products=[] + no failure reason.
    # Navigation alone is not extraction: the terminal outcome is NOT_FOUND.
    assert C.resolve_outcome(records_count=0, blocked_reason=None) == C.NOT_FOUND


def test_fixture_extractor_failure_is_not_success():
    assert C.normalize_stop_reason("EXTRACTOR_FAILURE") == C.EXTRACTOR_FAILURE
    assert C.resolve_outcome(0, C.EXTRACTOR_FAILURE) == C.EXTRACTOR_FAILURE


# ── 3. PERSISTED_VIEW is never a new acquisition ────────────────────────────
def test_persisted_view_is_never_live():
    view = C.view_metadata(execution_mode="DISCOVERY::Paris",
                           run_id="run_fixture", source="OPERATIONAL", live=False)
    assert view["view_kind"] == C.PERSISTED_VIEW
    assert view["live"] is False
    assert view["is_new_acquisition"] is False
    live = C.view_metadata(execution_mode="DISCOVERY", run_id="run_live", live=True)
    assert live["view_kind"] == "LIVE_MEMORY" and live["is_new_acquisition"] is True


# ── 6. Counters distinguish publications, SKUs, identity and category ──────
def test_summary_distinguishes_publications_and_skus():
    records = [
        {"observed_sku": "SKU-1", "commercial_identity": {"state": C.OFFICIAL_VERIFIED,
                                                          "condition": "NEW"},
         "official_kpi": True},
        {"observed_sku": "SKU-1", "commercial_identity": {"state": C.OFFICIAL_VERIFIED,
                                                          "condition": "NEW"},
         "official_kpi": True},  # same SKU observed twice
        {"observed_sku": "SKU-2", "commercial_identity": {"state": C.THIRD_PARTY_USED,
                                                          "condition": "USED"},
         "official_kpi": False},
    ]
    s = C.summarize_identities(records)
    assert s["records"] == 3
    assert s["unique_marketplace_ids"] == 2
    assert s["official_kpi_eligible"] == 2
    assert s["third_party_used"] == 1
    assert s["excluded_from_official_kpi"] == 1


# ── 7. Unverified seller is never turned into official ─────────────────────
def test_title_with_brand_is_not_official():
    identity = C.classify_commercial_identity(title="Polera Nicopoly Negra MK55PJULHG")
    assert identity["state"] == C.SELLER_UNVERIFIED
    assert identity["is_official"] is False


def test_unknown_seller_is_unverified_not_official():
    identity = C.classify_commercial_identity(title="Polera", brand="", vendor="", seller="")
    assert identity["state"] == C.SELLER_UNVERIFIED
    assert C.identity_is_official_kpi(identity) is False


def test_brand_field_alone_is_not_seller_proof():
    # CP3 (MRI-LIVE-RUNTIME-FIX-001): a brand/vendor field is evidence of brand
    # scope but NOT proof of an official seller.
    identity = C.classify_commercial_identity(title="Polera", brand="Nicopoly")
    assert identity["state"] == C.SELLER_UNVERIFIED
    assert C.identity_is_official_kpi(identity) is False


def test_explicit_official_seller_is_official():
    identity = C.classify_commercial_identity(title="Polera", seller="Nicopoly Oficial")
    assert identity["state"] == C.OFFICIAL_VERIFIED
    assert C.identity_is_official_kpi(identity) is True


# ── 8. Third-party used (Moda Circular) never contaminates the official KPI ─
def test_third_party_used_is_excluded_from_official_kpi():
    identity = C.classify_commercial_identity(
        title="Polera Nicopoly usada", seller="Vendedor particular",
        attributes={"category": "Moda Circular"})
    assert identity["state"] == C.THIRD_PARTY_USED
    assert identity["condition"] == "USED"
    assert C.identity_is_official_kpi(identity) is False


def test_used_official_item_is_flagged_not_kpi():
    identity = C.classify_commercial_identity(
        title="Polera Nicopoly usada", brand="Nicopoly",
        attributes={"condition": "usado"})
    assert identity["condition"] == "USED"
    assert C.identity_is_official_kpi(identity) is False


# ── 9. Missing reference catalog cannot create false positives ─────────────
def test_missing_catalog_is_declared_and_unverified():
    status = C.catalog_reference_status()
    assert status["status"] in ("AVAILABLE", "CATALOG_REFERENCE_MISSING", "UNKNOWN")
    if status["status"] == "CATALOG_REFERENCE_MISSING":
        assert status["path"]
        assert status["affects"]
        assert status["decisions_without_support"]
    identity = C.classify_commercial_identity(title="Polera Nicopoly")
    assert identity["catalog_identity"] == "NOT_VERIFIED_AGAINST_REFERENCE"


def test_multivende_missing_is_reported_once_per_run():
    from app.loaders.multivende_loader import MultivendeLoader
    loader = MultivendeLoader(excel_path="does/not/exist.xlsx")
    loader.reset_reference_check()
    assert loader.load_catalog() is False
    assert loader._missing_reported is True
    # Second attempt must be silent (no repeated filesystem probes / warnings).
    assert loader.load_catalog() is False
    assert loader.reference_available is False
    loader.reset_reference_check()
    assert loader._missing_reported is False


# ── Runner integration (fixture scraper, no network/browser) ───────────────
class _BlockedScraper:
    """FIXTURE: emulates the frozen ML scraper returning stop_reason=BLOCKED."""

    supports_pagination = False

    def __init__(self):
        self.page = None

    async def start(self):
        return None

    async def stop(self):
        return None

    async def scrape_autonomous_category(self, url):
        return {"products": [], "stop_reason": "BLOCKED",
                "pages_traversed": 0, "failure_type": "WAF_BLOCKED", "url": url}


def _run_fixture_discovery(monkeypatch, scraper):
    from app.mri_dashboard import mri_runner as R
    from app.mri_dashboard.category_manager import category_manager

    seen = {}

    class _FakeRecRunner:
        def __init__(self, *a, **k):
            pass

        def persist_to_sqlite(self, payload, run_id, run_meta=None):
            seen["payload"] = payload
            seen["run_id"] = run_id
            seen["run_meta"] = run_meta
            return {"publications_materialized": len(payload.get("observations") or [])}

    import app.mri_autonomous.recovery_runner as RR
    monkeypatch.setattr(RR, "AcquisitionRecoveryRunner", _FakeRecRunner)
    monkeypatch.setattr(R, "get_scraper", lambda mkt: scraper)

    # No filesystem / storage-guard dependency for this fixture-driven test.
    monkeypatch.setattr(category_manager, "get_categories",
                        lambda mkt: {"SEARCH_PARIS": {
                            "name": "Búsqueda Nicopoly",
                            "url": "https://www.paris.cl/search?q=nicopoly"}})
    monkeypatch.setattr(category_manager, "register_category", lambda *a, **k: None)

    orch = R.orchestrator
    orch.is_running = False
    orch.stop_requested = False
    orch.results = []
    orch.history = []
    orch.state = {"progress": 0, "total": 0}
    monkeypatch.setattr(orch, "_save_history", lambda: None)

    asyncio.run(orch.run_discovery("Paris", max_pages=1, run_id="run_fixture_blocked",
                                   limit=1))
    return orch, seen


def test_runner_blocked_run_is_source_blocked_and_always_persisted(monkeypatch, capsys):
    orch, seen = _run_fixture_discovery(monkeypatch, _BlockedScraper())
    assert orch.results == []
    assert orch.state["outcome"] == C.SOURCE_BLOCKED
    assert orch.state["status_message"] == C.SOURCE_BLOCKED
    assert orch.state["outcome"] != "COMPLETED"
    # The run row must be attempted even with zero publications (provenance).
    assert seen.get("run_id") == "run_fixture_blocked"
    assert seen["payload"]["terminal_state"] == C.SOURCE_BLOCKED
    assert seen["run_meta"]["terminal_state"] == C.SOURCE_BLOCKED
    assert seen["run_meta"]["execution_mode"].startswith("DISCOVERY::")
    assert seen["payload"]["observations"] == []
    # Acquisition evidence is published for inspection.
    assert orch.state["acquisitions"][0]["raw_stop_reason"] == "BLOCKED"
    assert orch.state["acquisitions"][0]["acquisition_state"] == C.SOURCE_BLOCKED
    assert orch.state["acquisitions"][0]["adapter"] == "_BlockedScraper"
