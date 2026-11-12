"""MRI-RUNTIME-RECOVERY-001 reproducers (fixtures; no network)."""
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import app.mri_dashboard.acquisition_contract as C


class _FlakyServer:
    """Ripley-like scraper whose Playwright start fails once then recovers."""

    supports_pagination = False
    page = None

    def __init__(self, products, failures=1):
        self._products = products
        self.failures = failures
        self.starts = 0

    async def start(self):
        self.starts += 1
        if self.starts <= self.failures:
            raise RuntimeError("TargetClosedError: profile locked")

    async def stop(self):
        return None

    async def scrape_autonomous_category(self, url):
        return {"products": list(self._products), "pages_traversed": 1,
                "stop_reason": "EXHAUSTION", "url": url}


def _harness(monkeypatch, tmp_aux, scraper, *, taxonomy, marketplace,
             run_id=None):
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
    monkeypatch.setattr(R, "get_scraper", lambda mkt: scraper)
    async def _fake_tax(mkt, **k):
        return taxonomy
    monkeypatch.setattr(T, "discover_taxonomy_async", _fake_tax)
    monkeypatch.setattr(category_manager, "get_categories",
                        lambda mkt: {"C1": {"name": "Moda", "url": "https://simple.ripley.cl/c1"}})
    monkeypatch.setattr(category_manager, "register_category", lambda *a, **k: None)

    orch = R.orchestrator
    orch.is_running = False
    orch.stop_requested = False
    orch.results = []
    orch.history = []
    orch.state = {"progress": 0, "total": 0}
    monkeypatch.setattr(orch, "_save_history", lambda: None)
    rid = run_id or f"run_rec_{uuid.uuid4().hex[:8]}"
    asyncio.run(orch.run_discovery(marketplace, max_pages=1, run_id=rid,
                                   full_audit=True))
    return orch, seen


def _aux():
    p = Path("evidence_local_validation/acquisition_truth/_recovery_cp")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _product(sku="SKU-1"):
    return {"title": "Polera Nicopoly", "marketplace_sku": sku, "url": "https://m/p1",
            "price": 1000, "vendor": "Nicopoly", "position_absolute": 1}


def test_ripley_browser_launch_retry_recovers(monkeypatch):
    scraper = _FlakyServer([_product()], failures=1)
    orch, seen = _harness(
        monkeypatch, _aux(), scraper, marketplace="Ripley",
        taxonomy={"marketplace": "Ripley", "status": "TAXONOMY_DISCOVERED",
                  "source": "NAVIGATION",
                  "categories": [{"category_id": "C1", "name": "Moda",
                                  "url": "https://simple.ripley.cl/c1"}]})
    assert scraper.starts == 2                 # un único reintento acotado
    assert orch.state["outcome"] == C.FOUND
    assert len(orch.results) == 1


def test_ripley_persistent_launch_failure_is_technical_not_not_found(monkeypatch):
    scraper = _FlakyServer([], failures=5)
    orch, _ = _harness(
        monkeypatch, _aux(), scraper, marketplace="Ripley",
        taxonomy={"marketplace": "Ripley", "status": "TAXONOMY_DISCOVERED",
                  "source": "NAVIGATION",
                  "categories": [{"category_id": "C1", "name": "Moda",
                                  "url": "https://m/c1"}]})
    assert scraper.starts == 2                 # nunca bucle infinito
    assert orch.state["outcome"] == C.EXTRACTOR_FAILURE
    assert "BROWSER_LAUNCH_FAILED" in (orch.state.get("error") or "")


def test_falabella_zero_ssr_observations_is_not_not_found(monkeypatch):
    import app.mri_autonomous.falabella_ssr_engine as FS
    import app.mri_dashboard.falabella_ssr_coverage as FB

    import app.mri_dashboard.falabella_autonomous as FBA
    monkeypatch.setattr(FS, "FalabellaSSREngine", lambda: object())
    monkeypatch.setattr(FBA, "run_full_audit", lambda *a, **k: {
        "marketplace": "Falabella", "complete": False,
        "surfaces": [{"surface": "brand:NICOPOLY", "terminal": "EXTRACTOR_FAILURE",
                      "cause": "payload shape mismatch", "pages_traversed": 1,
                      "cards": 0}],
        "observations": [], "cards_total": 0, "unique_product_ids": 0,
        "unique_sku_ids": 0, "build_id": None, "categories_discovered": 0,
        "categories_used": [], "pending_surfaces": ["brand:NICOPOLY"]})
    orch, _ = _harness(
        monkeypatch, _aux(), _FlakyServer([], failures=0), marketplace="Falabella",
        taxonomy={"marketplace": "Falabella", "status": "TAXONOMY_DISCOVERED",
                  "source": "SSR_NEXT_DATA",
                  "categories": [{"category_id": "C1", "name": "Moda",
                                  "url": "https://m/c1"}]})
    assert orch.state["outcome"] == C.EXTRACTOR_FAILURE
    assert orch.state["outcome"] != C.NOT_FOUND
    assert orch.state["acquisitions"][0]["acquisition_state"] == C.EXTRACTOR_FAILURE
    assert any("FALABELLA_SSR" in e.get("error", "") for e in orch.state["errors"])


def test_falabella_ssr_payload_shape_produces_publications():
    from app.mri_dashboard import falabella_ssr_coverage as FB

    class _SSREngine:
        def get_category_catalog(self, category_id=None, slug=None, page=1):
            return {"props": {"pageProps": {
                "results": ([{"productId": "P1"}, {"productId": "P2"}]
                            if page == 1 else []),
                "pagination": {"count": 2}}}}

        def harvest_sample_publications(self, brand="NICOPOLY", max_items=48,
                                        page_payload=None):
            items = (page_payload or {}).get("props", {}).get("pageProps", {}).get(
                "results", [])
            pubs = [SimpleNamespace(
                publication_id=i["productId"], sku=i["productId"], title="Polera",
                canonical_url="https://www.falabella.com/p/" + i["productId"],
                sellers=["Nicopoly"], brand="Nicopoly", condition="NEW",
                source_file_path="/tmp/ssr.html", source_file_sha256="abc",
                evidence_type="SSR_NEXT_DATA") for i in items]
            return pubs, []

    res = FB.traverse_category(_SSREngine(), {"category_id": "C1", "name": "Moda",
                                             "url": "https://m/c1"})
    assert res["publications"] == 2
    assert res["terminal"] == FB.REPORTED_REACHED
    assert res["observations"][0]["evidence"]["source_file_sha256"] == "abc"


def test_meli_domain_discovery_shapes_are_parsed(monkeypatch):
    import app.mri_dashboard.discovery_kernel as DK
    import app.mri_dashboard.taxonomy as T

    class _Kernel:
        def discover(self, target):
            return DK.DiscoveryResult(target, "https://store.invalid", [
                {"name": "Poleras", "url": "https://store.invalid/listado/poleras/",
                 "source": "TEST", "acquisition": True},
                {"name": "Pantalones", "url": "https://store.invalid/listado/pantalones/",
                 "source": "TEST", "acquisition": True},
            ], ["TEST"], state="DISCOVERED")

    monkeypatch.setattr(DK, "DiscoveryKernel", _Kernel)
    res = T.discover_taxonomy("Mercado Libre")
    assert res["status"] == T.DISCOVERED
    names = {c["name"] for c in res["categories"]}
    assert names == {"Poleras", "Pantalones"}


def test_meli_no_discovered_categories_is_unavailable(monkeypatch):
    import app.mri_dashboard.discovery_kernel as DK
    import app.mri_dashboard.taxonomy as T

    class _Kernel:
        def discover(self, target):
            return DK.DiscoveryResult(target, None, [], ["NO_SURFACE"],
                                      state="STORE_BLOCKED")

    monkeypatch.setattr(DK, "DiscoveryKernel", _Kernel)
    res = T.discover_taxonomy("Mercado Libre")
    assert res["status"] == T.UNAVAILABLE
    assert not res["categories"]


def test_falabella_incomplete_ssr_can_never_be_audit_pass(monkeypatch):
    import app.mri_autonomous.falabella_ssr_engine as FS
    import app.mri_dashboard.falabella_ssr_coverage as FB

    import app.mri_dashboard.falabella_autonomous as FBA
    monkeypatch.setattr(FS, "FalabellaSSREngine", lambda: object())
    monkeypatch.setattr(FBA, "run_full_audit", lambda *a, **k: {
        "marketplace": "Falabella", "complete": False,
        "surfaces": [{"surface": "brand:NICOPOLY", "terminal": "PAGE_BOUND_REACHED",
                      "cause": "page safety bound 100 reached",
                      "pages_traversed": 100, "cards": 1}],
        "observations": [{"product_id": "P1", "sku_id": "S1",
                          "title": "Polera Nicopoly", "brand": "NICOPOLY",
                          "seller_id": "SC75ABC", "seller_name": "Nicopoly",
                          "category_gsc": "G08020501", "category_name": "Poleras Mujer",
                          "url": "https://www.falabella.com/falabella-cl/product/1/p",
                          "price": 19990.0, "surface": "brand:NICOPOLY",
                          "page": 1, "build_id": "abc", "position": 1,
                          "observed_at": "2026-10-26T12:00:00"}],
        "cards_total": 1, "unique_product_ids": 1, "unique_sku_ids": 1,
        "build_id": "abc", "categories_discovered": 0, "categories_used": [],
        "pending_surfaces": ["brand:NICOPOLY"]})
    orch, _ = _harness(
        monkeypatch, _aux(), _FlakyServer([], failures=0), marketplace="Falabella",
        taxonomy={"marketplace": "Falabella", "status": "TAXONOMY_DISCOVERED",
                  "source": "SSR_NEXT_DATA",
                  "categories": [{"category_id": "C1", "name": "Mujer",
                                  "url": "https://m/c1"}]})
    cov = orch.state.get("coverage") or {}
    assert orch.state["outcome"] == C.PARTIAL
    assert cov.get("acceptance") == "AUDIT_FAIL", cov
    assert cov.get("termination_condition") == "INCOMPLETE"
    assert any("Falabella SSR incompleto" in r for r in cov.get("acceptance_reasons") or [])
