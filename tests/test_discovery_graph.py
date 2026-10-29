"""Learned route graph avoids repeated discovery without fixing categories."""
from pathlib import Path
import app.mri_dashboard.discovery_graph as G


def test_graph_persists_routes_and_reuses_them(monkeypatch):
    path = Path("evidence_local_validation/discovery_graph_test.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    monkeypatch.setattr(G, "_GRAPH", path)
    G.merge_discovered("Mercado Libre", "brand-one", "https://x/tienda/brand-one", [
        {"name": "Poleras", "url": "https://x/tienda/brand-one/listado/poleras/",
         "parent_url": None, "acquisition": True},
        {"name": "Abrigos", "url": "https://x/tienda/brand-one/listado/abrigos/",
         "parent_url": None, "acquisition": False},
    ], "TEST")
    learned = G.learned_categories("Mercado Libre", "brand-one")
    assert {c["name"] for c in learned} == {"Poleras", "Abrigos"}
    assert all(c["source"] == "GRAPH_CACHE" for c in learned)
    G.mark_hit("Mercado Libre", "brand-one")
    node = G.load_node("Mercado Libre", "brand-one")
    assert node["categories"]["Poleras"]["hits"] == 1


def test_graph_is_specific_to_brand(monkeypatch):
    path = Path("evidence_local_validation/discovery_graph_brand_test.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    monkeypatch.setattr(G, "_GRAPH", path)
    G.merge_discovered("Mercado Libre", "brand-one", None, [
        {"name": "Poleras", "url": "https://x/tienda/brand-one/listado/poleras/",
         "acquisition": True},
    ], "TEST")
    assert G.learned_categories("Mercado Libre", "brand-one")
    assert not G.learned_categories("Mercado Libre", "brand-two")
