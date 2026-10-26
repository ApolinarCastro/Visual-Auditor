"""
MRI-LIVE-RUNTIME-FIX-001 checkpoint tests (fixtures only, no network).

CP1 taxonomy is never silently converted into NOT_FOUND.
CP2 duplicate identifiers are collapsed WITH a traceable discard record.
CP3 sponsored slots never feed the organic/official KPI.
CP4 per-category checkpoint written during the scraper route + resume.
"""
import asyncio
import json
import uuid
from pathlib import Path

import app.mri_dashboard.acquisition_contract as C


# ── CP3 contract ──────────────────────────────────────────────────────────
def test_sponsored_slots_are_separated_from_organic():
    ad = ("https://click1.mercadolibre.cl/mclics/clicks/external/MLC/count?"
          "is_advertising=true&position=27")
    assert C.position_kind(ad) == "SPONSORED"
    assert C.position_kind("https://simple.ripley.cl/polera-mpm1?pos=2") == "ORGANIC"
    official = C.classify_commercial_identity(title="Polera", seller="Nicopoly Oficial")
    assert C.is_official_kpi_eligible(official, "SPONSORED") is False
    assert C.is_official_kpi_eligible(official, "ORGANIC") is True


def test_brand_field_never_grants_official():
    ident = C.classify_commercial_identity(title="Polera Nicopoly", brand="Nicopoly")
    assert ident["state"] == C.SELLER_UNVERIFIED
    assert C.is_official_kpi_eligible(ident, "ORGANIC") is False


# ── runner fixture harness ────────────────────────────────────────────────
class _Scraper:
    supports_pagination = False
    page = None

    def __init__(self, products):
        self._products = products

    async def start(self):
        return None

    async def stop(self):
        return None

    async def scrape_autonomous_category(self, url):
        return {"products": list(self._products), "pages_traversed": 2,
                "stop_reason": "EXHAUSTION", "url": url}


def _run(monkeypatch, tmp_aux, products, *, run_id=None, taxonomy_result, marketplace="Ripley"):
    import app.mri_autonomous.recovery_runner as RR
    import app.mri_autonomous.storage_guard as SG
    import app.mri_dashboard.mri_runner as R
    import app.mri_dashboard.taxonomy as T
    from app.mri_dashboard.category_manager import category_manager

    seen = {}

    class _FakeRec:
        def __init__(self, *a, **k):
            pass

        def persist_to_sqlite(self, payload, run_id, run_meta=None):
            seen["payload"] = payload
            seen["run_meta"] = run_meta
            return {}

    monkeypatch.setattr(RR, "AcquisitionRecoveryRunner", _FakeRec)
    monkeypatch.setattr(SG.StorageConfig, "get_aux_dir",
                        classmethod(lambda cls: Path(tmp_aux)))
    monkeypatch.setattr(R, "get_scraper", lambda mkt: _Scraper(products))
    async def _fake_tax(mkt, **k):
        return taxonomy_result
    monkeypatch.setattr(T, "discover_taxonomy_async", _fake_tax)
    monkeypatch.setattr(category_manager, "get_categories",
                        lambda mkt: {} if not products else {
                            "CAT1": {"name": "Moda", "url": "https://m/falabella/cat1"}})
    monkeypatch.setattr(category_manager, "register_category", lambda *a, **k: None)

    orch = R.orchestrator
    orch.is_running = False
    orch.stop_requested = False
    orch.results = []
    orch.history = []
    orch.state = {"progress": 0, "total": 0}
    monkeypatch.setattr(orch, "_save_history", lambda: None)
    rid = run_id or f"run_fixture_{uuid.uuid4().hex[:8]}"
    asyncio.run(orch.run_discovery(marketplace, max_pages=1,
                                   run_id=rid, full_audit=True))
    orch._fixture_run_id = rid
    return orch, seen


def test_cp1_missing_taxonomy_is_blocked_not_not_found(monkeypatch, tmp_path=None):
    aux = Path("evidence_local_validation/acquisition_truth/_runtime_fix_cp")
    aux.mkdir(parents=True, exist_ok=True)
    orch, seen = _run(
        monkeypatch, aux, [],
        taxonomy_result={"marketplace": "Ripley", "status": "TAXONOMY_BLOCKED",
                         "source": "SSR_NEXT_DATA", "categories": [],
                         "notes": ["HTTP 403 WAF"]})
    assert orch.state["outcome"] == C.SOURCE_BLOCKED
    assert orch.state["status_message"] == "TAXONOMY_BLOCKED"
    assert orch.state["taxonomy_blocked"]["Ripley"] == "HTTP 403 WAF"
    assert orch.results == []
    assert seen["run_meta"]["taxonomy_status"]["Ripley"] == "TAXONOMY_BLOCKED"
    assert seen["run_meta"]["taxonomy_cause"]["Ripley"] == "HTTP 403 WAF"
    assert seen["run_meta"]["terminal_state"] == C.SOURCE_BLOCKED


def test_cp2_duplicate_identifier_is_discarded_with_trace(monkeypatch):
    aux = Path("evidence_local_validation/acquisition_truth/_runtime_fix_cp")
    aux.mkdir(parents=True, exist_ok=True)
    products = [
        {"title": "Polera Nicopoly", "marketplace_sku": "SKU-1",
         "url": "https://m/p1", "price": 1000, "vendor": "Nicopoly",
         "position_absolute": 1},
        {"title": "Polera Nicopoly", "marketplace_sku": "SKU-1",
         "url": "https://m/p2", "price": 1000, "vendor": "Nicopoly",
         "position_absolute": 9},
    ]
    orch, seen = _run(
        monkeypatch, aux, products,
        taxonomy_result={"marketplace": "Ripley", "status": "TAXONOMY_DISCOVERED",
                         "source": "NAVIGATION",
                         "categories": [{"category_id": "CAT1", "name": "Moda",
                                         "url": "https://m/falabella/cat1"}]})
    print('DEBUG_STATE', orch.state.get('outcome'), orch.state.get('error'),
          orch.state.get('failed_stage'), orch.state.get('taxonomy_status'))
    assert len(orch.results) == 2
    assert len(seen["payload"]["observations"]) == 1
    pers = orch.state["persistence"]
    assert pers["source_results"] == 2 and pers["stored_observations"] == 1
    assert pers["duplicates_collapsed"] == 1
    assert pers["discard_examples"][0]["publication_id"] == "SKU-1"
    assert pers["discard_examples"][0]["reason"] == "DUPLICATE_PUBLICATION_ID"


def test_cp4_checkpoint_written_per_category_and_resumable(monkeypatch):
    aux = Path("evidence_local_validation/acquisition_truth/_runtime_fix_cp")
    aux.mkdir(parents=True, exist_ok=True)
    products = [{"title": "Polera Nicopoly", "marketplace_sku": "SKU-77",
                 "url": "https://m/p77", "price": 1000, "vendor": "Nicopoly",
                 "position_absolute": 1}]
    orch, _ = _run(
        monkeypatch, aux, products,
        taxonomy_result={"marketplace": "Ripley", "status": "TAXONOMY_DISCOVERED",
                         "source": "SSR_NEXT_DATA",
                         "categories": [{"category_id": "CAT1", "name": "Moda",
                                         "url": "https://m/falabella/cat1"}]})
    cp = aux / f"mri_coverage_checkpoint_{orch._fixture_run_id}.json"
    assert cp.exists(), "per-category checkpoint must exist"
    data = json.loads(cp.read_text(encoding="utf-8"))
    cat = data["categories"]["https://m/falabella/cat1"]
    assert cat["pages_observed"] == 2
    assert cat["status"] == "COMPLETE"
    assert not list(aux.glob("*.tmp"))


def test_cp4_resume_skips_confirmed_category_and_keeps_checkpoint(monkeypatch):
    aux = Path('evidence_local_validation/acquisition_truth/_runtime_fix_cp')
    aux.mkdir(parents=True, exist_ok=True)
    rid = f'run_resume_{uuid.uuid4().hex[:8]}'
    tax = {'marketplace': 'Ripley', 'status': 'TAXONOMY_DISCOVERED',
           'source': 'NAVIGATION',
           'categories': [{'category_id': 'CAT1', 'name': 'Moda',
                           'url': 'https://m/falabella/cat1'}]}
    products = [{'title': 'Polera Nicopoly', 'marketplace_sku': 'SKU-9',
                 'url': 'https://m/p9', 'price': 1000, 'vendor': 'Nicopoly',
                 'position_absolute': 1}]
    first, _ = _run(monkeypatch, aux, products, run_id=rid, taxonomy_result=tax)
    assert len(first.results) == 1
    second, _ = _run(monkeypatch, aux, products, run_id=rid, taxonomy_result=tax)
    assert second.results == []          # categoria confirmada: no se re-adquiere
    data = json.loads((aux / f'mri_coverage_checkpoint_{rid}.json').read_text(encoding='utf-8'))
    assert data['categories']['https://m/falabella/cat1']['status'] == 'COMPLETE'
