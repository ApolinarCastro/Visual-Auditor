"""Generic discovery: brand-parametrized, no fixed category oracle."""
from pathlib import Path
from app.mri_dashboard.discovery_kernel import (
    DiscoveryKernel, DiscoveryTarget, MeliAdapter)


def test_store_resolution_is_brand_generic():
    a = MeliAdapter()
    assert a.resolve_store(DiscoveryTarget("Mercado Libre", "Brand One")) ==         "https://www.mercadolibre.cl/tienda/brand-one"
    assert a.resolve_store(DiscoveryTarget("Mercado Libre", "Otra Marca")) ==         "https://www.mercadolibre.cl/tienda/otra-marca"


def test_parent_route_is_reference_and_children_acquire():
    cats = [
        {"name": "Abrigos", "url": "https://x/tienda/b/listado/vestuario-calzado/abrigos/"},
        {"name": "Chaquetas", "url": "https://x/tienda/b/listado/vestuario-calzado/abrigos/chaquetas/"},
    ]
    out = MeliAdapter.hierarchy(cats)
    parent = next(c for c in out if c["name"] == "Abrigos")
    child = next(c for c in out if c["name"] == "Chaquetas")
    assert parent["acquisition"] is False
    assert child["acquisition"] is True


def test_validation_is_a_dynamic_snapshot(monkeypatch):
    import app.mri_dashboard.discovery_kernel as DK
    memory = Path("evidence_local_validation/discovery_memory_test.json")
    memory.parent.mkdir(parents=True, exist_ok=True)
    if memory.exists():
        memory.unlink()
    monkeypatch.setattr(DK, "_MEMORY", memory)
    adapter = MeliAdapter()
    target = DiscoveryTarget("Mercado Libre", "Brand One", "https://x/tienda/brand-one")
    first = adapter.validation_snapshot(target, [{"name": "Poleras"}])
    assert first["count"] == 1 and first["new"] == ["Poleras"]
    second = adapter.validation_snapshot(target, [{"name": "Poleras"}, {"name": "Blusas"}])
    assert second["count"] == 2 and second["new"] == ["Blusas"]
    third = adapter.validation_snapshot(target, [{"name": "Poleras"}])
    assert third["removed"] == ["Blusas"]
