"""Taxonomy wiring tests (MRI-CATEGORY-COVERAGE-002). FIXTURES only."""
import app.mri_dashboard.taxonomy as T


def test_paris_is_not_required_and_untouched():
    res = T.discover_taxonomy("Paris")
    assert res["status"] == T.NOT_REQUIRED
    assert res["categories"] == []


def test_ripley_without_open_page_is_blocked_not_faked():
    class NoPage:
        page = None
    res = T.discover_taxonomy("Ripley", scraper=NoPage())
    assert res["status"] == T.BLOCKED
    assert res["categories"] == []
    assert res["notes"]


def test_ripley_navigation_categories_are_deduplicated(monkeypatch):
    import app.mri_autonomous.category_discoverer as cd

    class Page:
        page = object()

    monkeypatch.setattr(cd, "discover_categories_from_page",
                        lambda page, mkt, hub, brand: [
                            "https://simple.ripley.cl/tienda/moda-mujer",
                            "https://simple.ripley.cl/tienda/moda-mujer",
                            "https://simple.ripley.cl/tienda/moda-hombre"])
    res = T.discover_taxonomy("Ripley", scraper=Page(), hub_url="https://h")
    assert res["status"] == T.DISCOVERED
    urls = [c["url"] for c in res["categories"]]
    assert len(urls) == 2 and len(set(urls)) == 2
    assert all(c["category_id"] and c["name"] for c in res["categories"])


def test_falabella_taxonomy_from_ssr_nodes(monkeypatch):
    import app.mri_autonomous.falabella_ssr_engine as fs

    class Node:
        category_id = "cat-1"
        name = "Moda Mujer"
        level = 2
        parent_id = "root"
        hierarchical_path = ["Moda", "Mujer"]
        canonical_url = "https://www.falabella.com/falabella-cl/category/cat-1"
        reported_count = 120
        children = []

    class Eng:
        def get_brand_catalog(self, brand_name="Nicopoly", page=1):
            return {"payload": True}

        def extract_taxonomy_tree(self, payload):
            return [Node(), Node()]          # duplicate must collapse

    monkeypatch.setattr(fs, "FalabellaSSREngine", Eng)
    res = T.discover_taxonomy("Falabella")
    assert res["status"] == T.DISCOVERED
    assert len(res["categories"]) == 1
    cat = res["categories"][0]
    assert cat["category_id"] == "cat-1"
    assert cat["parent_id"] == "root"
    assert cat["reported_count"] == 120


def test_falabella_engine_failure_is_blocked_not_silent(monkeypatch):
    import app.mri_autonomous.falabella_ssr_engine as fs

    class Eng:
        def __init__(self):
            raise RuntimeError("SSR unavailable")

    monkeypatch.setattr(fs, "FalabellaSSREngine", Eng)
    res = T.discover_taxonomy("Falabella")
    assert res["status"] == T.BLOCKED
    assert "SSR unavailable" in res["notes"][0]


def test_meli_uses_discovery_kernel(monkeypatch):
    import app.mri_dashboard.discovery_kernel as DK
    import app.mri_dashboard.taxonomy as T

    class Kernel:
        def discover(self, target):
            return DK.DiscoveryResult(target, "https://store.invalid", [
                {"name": "Poleras", "url": "https://store.invalid/listado/poleras/",
                 "source": "TEST", "acquisition": True},
            ], ["TEST"], state="DISCOVERED")

    monkeypatch.setattr(DK, "DiscoveryKernel", Kernel)
    res = T.discover_taxonomy("Mercado Libre")
    assert res["status"] == T.DISCOVERED
    names = {c["name"] for c in res["categories"]}
    assert names == {"Poleras"}
    assert all(c.get("acquisition", True) is True for c in res["categories"])


def test_summary_marks_scope_incomplete_when_any_market_pending():
    summary = T.summarize({
        "Ripley": {"status": T.DISCOVERED, "categories": [{"url": "u"}]},
        "Falabella": {"status": T.BLOCKED, "categories": []},
    })
    assert summary["complete_scope"] is False
    assert summary["pending"] == ["Falabella"]
    assert summary["discovered"][0]["marketplace"] == "Ripley"


def test_taxonomy_never_raises_for_unknown_marketplace():
    res = T.discover_taxonomy("Unknown Market")
    assert res["status"] == T.NOT_REQUIRED
