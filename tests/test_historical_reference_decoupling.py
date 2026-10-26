"""
Historical-reference decoupling tests (P0 2026-10-22).

Rule under test: `Actualización masiva de productos.xlsx`,
`Busquedas_Concretas_Visual_Auditor.csv` and `SVMP.xlsx` are OUTDATED
HISTORICAL REFERENCES. They are never an authority for current publications,
sellers, categories or absence, and their absence must not block MRI.

All marketplace payloads below are explicit FIXTURES.
"""
import asyncio
import re
from pathlib import Path

import pytest

from app.mri_dashboard import acquisition_contract as C


# ── 1. The three files are declared as reference-only, authority NONE ──────
def test_three_historical_references_are_declared_without_authority():
    status = C.historical_reference_status()
    assert set(status) == {"multivende_catalog", "search_intents", "svmp"}
    for key, meta in status.items():
        assert meta["role"] == "HISTORICAL_REFERENCE", key
        assert meta["authority"] == "NONE", key
        assert meta["usable_as_authority"] is False, key
        assert meta["present"] in (True, False), key
    # Filenames are exactly the three historical artifacts.
    names = {m["filename"] for m in status.values()}
    assert "Actualización masiva de productos.xlsx" in names
    assert "Busquedas_Concretas_Visual_Auditor.csv" in names
    assert "SVMP.xlsx" in names


# ── 2. Classification may never rest on the historical catalog alone ──────
def test_classification_basis_requires_observed_features():
    assert C.classification_basis({}) == "HISTORICAL_REFERENCE"
    assert C.classification_basis({"title": "Polera"}) == "OBSERVED_FEATURES"
    assert C.classification_basis({"observed_category": "Mujer > Poleras"}) == \
        "OBSERVED_FEATURES"


# ── 3. Multivende catalog matching alone cannot mark official/KPI ─────────
def test_catalog_match_alone_never_official():
    identity = C.classify_commercial_identity(title="", brand="", vendor="",
                                              seller="")
    assert identity["state"] == C.SELLER_UNVERIFIED
    assert C.identity_is_official_kpi(identity) is False
    assert identity["catalog_identity"] == "NOT_VERIFIED_AGAINST_REFERENCE"


# ── 4. MRI acquires + evaluates with ALL THREE files absent ───────────────
class _ObservedScraper:
    """FIXTURE: two publications with genuine observable features."""

    supports_pagination = False
    page = None

    async def start(self):
        return None

    async def stop(self):
        return None

    async def scrape_autonomous_category(self, url):
        return {
            "products": [
                {"title": "Polera Entallada Nicopoly Negra", "url": "https://www.paris.cl/p1.html",
                 "marketplace_sku": "MK55PJULHG", "price": 19990.0, "vendor": "Nicopoly",
                 "position_absolute": 1},
                {"title": "Pantalón Recto Nicopoly Beige", "url": "https://www.paris.cl/p2.html",
                 "marketplace_sku": "MKC5X5PH61", "price": 24990.0, "vendor": "Nicopoly",
                 "position_absolute": 2},
            ],
            "pages_traversed": 1,
            "stop_reason": "EXHAUSTION",
            "failure_type": None,
            "url": url,
        }


def _run_without_historical_files(monkeypatch):
    """Run a fixture discovery while EVERY historical reference is absent."""
    import uuid
    import app.loaders.multivende_loader as mut
    from app.mri_dashboard import mri_runner as R
    from app.mri_dashboard.category_manager import category_manager
    import app.mri_autonomous.recovery_runner as RR
    import app.mri_autonomous.storage_guard as SG

    # Fresh checkpoint dir per test so CP4 resume never reuses another test run.
    _cp_dir = Path("evidence_local_validation/acquisition_truth/_decoupling_cp") / uuid.uuid4().hex[:8]
    _cp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(SG.StorageConfig, "get_aux_dir",
                        classmethod(lambda cls: _cp_dir))

    # No Multivende xlsx anywhere: loader points to a non-existent path.
    loader = mut.MultivendeLoader(excel_path="Z:/nonexistent/cliente.xlsx")
    monkeypatch.setattr(mut, "get_multivende_loader", lambda: loader)

    seen = {}

    class _FakeRecRunner:
        def __init__(self, *a, **k):
            pass

        def persist_to_sqlite(self, payload, run_id, run_meta=None):
            seen["payload"] = payload
            seen["run_id"] = run_id
            seen["run_meta"] = run_meta
            return {"publications_materialized": len(payload.get("observations") or [])}

    monkeypatch.setattr(RR, "AcquisitionRecoveryRunner", _FakeRecRunner)
    monkeypatch.setattr(R, "get_scraper", lambda mkt: _ObservedScraper())
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
    asyncio.run(orch.run_discovery("Paris", max_pages=1,
                                   run_id="run_fixture_no_historical_refs", limit=2))
    return orch, seen


def test_mri_acquires_and_evaluates_without_the_three_files(monkeypatch):
    orch, seen = _run_without_historical_files(monkeypatch)
    results = orch.results
    assert orch.state["outcome"] == C.FOUND
    assert len(results) == 2
    # Acquisition happened from the (fixture) marketplace response, not files.
    assert seen["run_meta"]["terminal_state"] == C.FOUND
    assert seen["payload"]["observations"]
    for r in results:
        # Provenance preserved per observation.
        assert r["acquisition"]["run_id"] == "run_fixture_no_historical_refs"
        assert r["acquisition"]["adapter"] == "_ObservedScraper"
        assert r["acquisition"]["observed_url"] or r["acquisition"]["requested_url"]
        assert r["marketplace"] == "Paris"
        # Classification rests on observable features of the product.
        assert r["classification_basis"] == "OBSERVED_FEATURES"
        # Historical reference is present but declared powerless.
        assert r["historical_reference"]["role"] == "HISTORICAL_REFERENCE"
        assert r["historical_reference"]["authority"] == "NONE"
        assert r["catalog_reference"] == "CATALOG_REFERENCE_MISSING"
    # Absence of the reference catalog is reported, never blocking.
    assert orch.state["catalog_reference"]["status"] == "CATALOG_REFERENCE_MISSING"
    assert orch.state["historical_references"]["svmp"]["authority"] == "NONE"
    assert orch.state["historical_references"]["multivende_catalog"]["present"] is False


# ── 5. Reconciliation degrades to NO_VERIFICADO instead of crashing ───────
def test_reconciliation_treats_missing_catalog_as_optional():
    src = Path("app/mri_autonomous/recovery_runner.py").read_text(encoding="utf-8")
    assert "if CATALOG_PATH.exists():" in src, "reconcile must guard the historical file"
    assert "CATALOG_REFERENCE_MISSING" in src
    assert "Historical reference unreadable" in src
    assert "self.last_catalog_status" in src
    # The catalog is consumed inside the guarded block only (indent >= 16).
    for line in src.splitlines():
        if "openpyxl.load_workbook(CATALOG_PATH" in line:
            indent = len(line) - len(line.lstrip())
            assert indent >= 16, f"unguarded historical read: {line!r}"
            break
    else:
        raise AssertionError("guarded catalog load not found")


# ── 6. MRI modules do not import the historical sources ───────────────────
def test_mri_modules_do_not_import_svmp_or_search_intent_csv():
    forbidden = ("SVMP", "Busquedas_Concretas", "EXCEL_SOURCE")
    # acquisition_contract only DECLARES the three filenames as reference-only.
    declaration_files = {"app/mri_dashboard/acquisition_contract.py"}
    offenders = []
    for base in ("app/mri_autonomous", "app/mri_dashboard"):
        for path in Path(base).rglob("*.py"):
            rel = path.as_posix()
            if rel in declaration_files:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in forbidden:
                for line in text.splitlines():
                    if token not in line:
                        continue
                    low = line.lower()
                    if "no svmp" in low or "not use svmp" in low:
                        continue
                    if line.strip().startswith("#") or line.strip().startswith('"'):
                        continue
                    offenders.append(f"{rel}: {line.strip()[:90]}")
                    break
    assert offenders == [], f"MRI modules must stay free of historical sources: {offenders[:5]}"


# ── 7. Visual Auditor keeps its historical usage ──────────────────────────
def test_visual_auditor_historical_usage_is_preserved():
    from app.config import settings
    assert settings.EXCEL_SOURCE.name == "SVMP.xlsx"
    assert settings.MULTIVENDE_EXCEL_PATH.name == "Actualización masiva de productos.xlsx"
    va_src = Path("app/auditor/audit_runner.py").read_text(encoding="utf-8")
    assert "SVMP.xlsx" in va_src  # VA may still consume its historical task list
    # But VA code itself must be untouched by this closure (checked by git diff).
